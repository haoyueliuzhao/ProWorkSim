"""v033 CPU trust/accounting controls; scripted responses are not model behavior."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.model_policy import FORMAT_FEEDBACK_BUDGETED_V033, normalize_config
from proworksim.staff_runtime import PolicyBoundaryError
from proworksim.storage import digest, json_bytes
from proworksim.team_budget_v033 import SharedTeamBudget

IDENTITY = {"policy_version": "explicit-cpu-control", "adapter_sha256": "not-model-weights"}
WINDOW = "v033-explicit-cpu-window"


def ledger(**kwargs):
    return SharedTeamBudget(members=["member_a", "member_b"], team_id=WINDOW, **kwargs)


def exact_reservation(prompt_tokens=100, output_tokens=2048):
    prepared = {"version": "resident-request-budget-v0.31r3", "window_id": WINDOW,
                "actor_identity": IDENTITY, "prompt_tokens": prompt_tokens,
                "reserved_output_tokens": output_tokens, "context_limit": 16384,
                "fits": prompt_tokens + output_tokens <= 16384,
                "input_ids_sha256": digest(json_bytes(list(range(prompt_tokens)))),
                **{key: digest(key.encode()) for key in ("original_request_sha256", "selected_request_sha256",
                                                       "rendered_prompt_sha256", "recipe_sha256")}}
    prepared["preparation_sha256"] = digest(json_bytes(prepared))
    return {"token_reservation": prompt_tokens + output_tokens,
            "reservation_kind": "exact_resident_prompt", "preparation": prepared}


def body(call_id, *, prompt_tokens=100, output_tokens=3):
    return {"id": call_id, "actor_identity": IDENTITY, "online_window_id": WINDOW,
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": output_tokens,
                      "total_tokens": prompt_tokens + output_tokens},
            "token_trace": {"input_ids": list(range(prompt_tokens)), "output_ids": [8] * output_tokens,
                            "fixture_only": True}}


def reserve(budget, member, call_id):
    budget.consume_decision(member, call_id)
    budget.reserve(member, call_id, exact_reservation())


def test_v033_policy_declares_no_separate_format_retirement_and_preserves_old_policy():
    current = normalize_config({"format_error_policy": FORMAT_FEEDBACK_BUDGETED_V033})
    assert current["format_limits"] == {"max_total": None, "max_consecutive": None}
    assert normalize_config(current) == current
    assert normalize_config({"format_error_policy": "format_feedback_continue"})["format_limits"] == {
        "max_total": 4, "max_consecutive": 2}


def test_shared_token_reservations_are_atomic_across_both_members():
    budget = ledger(max_total_tokens=3000)
    def attempt(member):
        try:
            reserve(budget, member, member + "-call")
            return "reserved"
        except PolicyBoundaryError as error:
            assert error.details["limits"] == ["team_max_total_tokens"]
            return "rejected"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, ["member_a", "member_b"])) == ["rejected", "reserved"]
    snapshot = budget.snapshot()
    assert snapshot["decisions"] == 2 and snapshot["attempts"] == 0
    assert snapshot["held_tokens"] == 2148 and snapshot["charged_tokens"] == 0


def test_one_member_can_use_more_than_64_decisions_and_other_member_uses_same_remainder():
    budget = ledger()
    for index in range(65):
        call_id = "a-" + str(index)
        reserve(budget, "member_a", call_id)
        budget.begin_attempt("member_a", call_id)
        budget.settle("member_a", call_id, body(call_id))
    reserve(budget, "member_b", "b-0")
    budget.begin_attempt("member_b", "b-0")
    budget.settle("member_b", "b-0", body("b-0"))
    snapshot = budget.snapshot()
    assert snapshot["decisions"] == snapshot["attempts"] == 66
    assert snapshot["charged_tokens"] == 66 * 103 and snapshot["held_tokens"] == 0
    assert snapshot["remaining_decisions"] == 62


def test_settlement_cleanup_and_restore_never_double_charge_or_replay_a_call():
    budget = ledger()
    reserve(budget, "member_a", "finished")
    budget.begin_attempt("member_a", "finished")
    charge = budget.settle("member_a", "finished", body("finished"))
    assert budget.settle("member_a", "finished", body("finished")) == charge
    budget.cleanup("member_a", "finished")
    reserve(budget, "member_b", "pre-generation")
    reserve(budget, "member_a", "uncertain")
    budget.begin_attempt("member_a", "uncertain")
    restored = SharedTeamBudget.from_snapshot(budget.snapshot())
    snapshot = restored.snapshot()
    assert snapshot["charged_tokens"] == 103 + 2148 and snapshot["held_tokens"] == 0
    assert snapshot["attempts"] == 2
    assert snapshot["records"]["pre-generation"]["status"] == "cancelled_before_attempt"
    assert snapshot["records"]["uncertain"]["charge"]["usage_status"] == "uncertain_attempt_charged_reservation"
    assert SharedTeamBudget.from_snapshot(snapshot).snapshot() == snapshot
    with pytest.raises(PolicyBoundaryError, match="reused"):
        restored.consume_decision("member_a", "finished")
    assert restored.snapshot()["charged_tokens"] == 103 + 2148


@pytest.mark.parametrize("change", ["input_ids", "actor_identity", "online_window_id", "usage"])
def test_actual_record_mismatch_stays_blocking_and_never_releases_unaccounted_attempt(change):
    budget = ledger()
    reserve(budget, "member_a", "bad")
    budget.begin_attempt("member_a", "bad")
    response = body("bad")
    if change == "input_ids":
        response["token_trace"]["input_ids"][0] = 999
    elif change == "actor_identity":
        response[change] = {"policy_version": "unadmitted"}
    elif change == "online_window_id":
        response[change] = "another-window"
    else:
        response[change]["total_tokens"] += 1
    with pytest.raises(PolicyBoundaryError) as stopped:
        budget.settle("member_a", "bad", response)
    assert stopped.value.status == "execution_integrity_error"
    budget.cleanup("member_a", "bad")
    assert budget.snapshot()["charged_tokens"] == 2148
    assert budget.snapshot()["held_tokens"] == 0
    with pytest.raises(PolicyBoundaryError):
        budget.consume_decision("member_b", "later")


def test_snapshot_and_request_binding_tampering_are_rejected():
    budget = ledger()
    saved = budget.snapshot()
    saved["charged_tokens"] += 1
    with pytest.raises(ValueError, match="checksum"):
        SharedTeamBudget.from_snapshot(saved)
    budget.consume_decision("member_a", "bad-preflight")
    prepared = exact_reservation()
    prepared["preparation"]["input_ids_sha256"] = "0" * 64
    with pytest.raises(PolicyBoundaryError, match="sealed"):
        budget.reserve("member_a", "bad-preflight", prepared)
    assert budget.snapshot()["attempts"] == budget.snapshot()["charged_tokens"] == 0


def test_true_context_overflow_is_uncharged_capacity_boundary_and_other_member_can_continue():
    budget = ledger()
    budget.consume_decision('member_a', 'overflow')
    with pytest.raises(PolicyBoundaryError) as stopped:
        budget.reserve('member_a', 'overflow', exact_reservation(prompt_tokens=16380))
    assert stopped.value.status == 'model_budget_exhausted'
    assert stopped.value.details['budget_kind'] == 'context_capacity'
    assert stopped.value.details['limits'] == ['context_capacity']
    snapshot = budget.snapshot()
    assert snapshot['attempts'] == snapshot['charged_tokens'] == snapshot['held_tokens'] == 0
    assert snapshot['integrity_failure'] is None
    assert snapshot['records']['overflow']['status'] == 'admission_rejected'
    reserve(budget, 'member_b', 'fits')
    budget.begin_attempt('member_b', 'fits')
    budget.settle('member_b', 'fits', body('fits'))
    snapshot = budget.snapshot()
    assert snapshot['decisions'] == 2 and snapshot['attempts'] == 1
    assert snapshot['charged_tokens'] == 103 and snapshot['integrity_failure'] is None


def test_forged_context_fits_bit_remains_critical_even_with_resealed_payload():
    budget = ledger()
    budget.consume_decision('member_a', 'forged')
    reservation = exact_reservation()
    prepared = reservation['preparation']
    prepared['fits'] = False
    prepared['preparation_sha256'] = digest(json_bytes({key: value for key, value in prepared.items()
                                                      if key != 'preparation_sha256'}))
    with pytest.raises(PolicyBoundaryError) as stopped:
        budget.reserve('member_a', 'forged', reservation)
    assert stopped.value.status == 'execution_integrity_error'
    assert budget.snapshot()['integrity_failure']
    assert budget.snapshot()['attempts'] == budget.snapshot()['charged_tokens'] == 0


@pytest.mark.parametrize("limit", ["decisions", "attempts"])
def test_shared_limits_are_not_multiplied_by_member_count(limit):
    budget = ledger(**{"max_" + limit: 1})
    reserve(budget, "member_a", "first")
    budget.begin_attempt("member_a", "first")
    budget.settle("member_a", "first", body("first"))
    with pytest.raises(PolicyBoundaryError) as stopped:
        reserve(budget, "member_b", "second")
    assert stopped.value.details["limits"] == ["team_max_" + limit]
    assert budget.snapshot()["attempts"] == 1


class NativeCPUOwner:
    """Actual frozen tokenizer/renderer, deliberately scripted no-weight output."""
    def __init__(self, candidate, outputs):
        from proworksim.candidate_runtime_v015 import prepare_candidate_prompt, parse_candidate_generated
        from proworksim.candidate_runtime_v030 import MistralNativeTokenizer
        from proworksim.native_codecs_v031 import prepare_code_request, parse_code_response
        root = Path(__file__).resolve().parents[1]
        historical = 'v030' if candidate == 'qwen3.5-9b' else 'v031'
        old = json.loads((root / f'runs/software-model-selection-{historical}' / candidate / 'actual/resident/owner.json').read_text())
        self.identity = {**IDENTITY, 'candidate': candidate}
        self.window_id, self.requests, self.outputs = WINDOW, [], list(outputs)
        self.recipe = {'max_length': 16384, 'max_output_tokens': 2048, 'candidate': candidate}
        if candidate == 'qwen3.5-9b':
            from transformers import AutoTokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(old['base_identity']['path'], local_files_only=True, trust_remote_code=False)
            self.render = lambda request: prepare_candidate_prompt(request, self.tokenizer, old['inference_profile'])
            self.parse = lambda raw, request: parse_candidate_generated(raw, request)
        else:
            self.tokenizer = MistralNativeTokenizer(old['base_identity']['path'])
            self.render = lambda request: prepare_code_request(request, self.tokenizer, candidate)
            self.parse = lambda raw, request: parse_code_response(raw, request, candidate)
        self.candidate = candidate
        self.transport = SimpleNamespace(complete=self.complete)

    def prepare_request(self, request):
        return self.render(request)

    def freeze_identity(self):
        return copy.deepcopy(self.identity)

    def complete(self, request, **_):
        self.requests.append(copy.deepcopy(request))
        rendered, _, _ = self.render(request)
        inputs = self.tokenizer(rendered, add_special_tokens=False)['input_ids']
        value = self.outputs.pop(0)
        if self.candidate == 'qwen3.5-9b':
            raw = '<tool_call><function=write_note><parameter=text>' + value + '</parameter></function></tool_call>'
        else:
            raw = '[TOOL_CALLS]write_note[ARGS]{"text":' + value + '}</s>'
        message, error = self.parse(raw, request)
        outputs = (self.tokenizer(raw, add_special_tokens=False)['input_ids']
                   if self.candidate == 'qwen3.5-9b' else self.tokenizer.encode_text(raw))
        response = {'id': self.candidate + '-scripted-' + str(len(self.requests)), 'object': 'chat.completion',
                    'created': 0, 'model': 'explicit-cpu-not-generated', 'actor_identity': self.freeze_identity(),
                    'online_window_id': self.window_id, 'protocol_parse_error': error,
                    'choices': [{'index': 0, 'finish_reason': 'tool_calls' if message.get('tool_calls') else 'stop',
                                 'message': message}],
                    'usage': {'prompt_tokens': len(inputs), 'completion_tokens': len(outputs), 'total_tokens': len(inputs) + len(outputs)},
                    'token_trace': {'input_ids': inputs, 'output_ids': outputs, 'fixture_only': True}}
        return {'http_status': 200, 'body': response, 'raw_body': json.dumps(response)}


def sdk_config(owner):
    return {'model': 'explicit-cpu-not-generated', 'backend_id': 'resident_direct', 'api_key_env': None,
            'base_url': 'http://127.0.0.1', 'weight_identity': owner.freeze_identity(),
            'model_revision': owner.identity['policy_version'], 'max_context_tokens': 16384,
            'max_output_tokens': 2048, 'format_error_policy': FORMAT_FEEDBACK_BUDGETED_V033,
            'retry': {'max_attempts': 1, 'retry_statuses': [], 'backoff_seconds': []},
            'budget': {'max_decisions': 128, 'max_http_attempts': 128, 'max_total_tokens': 500000, 'max_cost_usd': 0},
            'pricing': {'input_miss_per_million': 0, 'input_hit_per_million': 0, 'output_per_million': 0}}


@pytest.mark.parametrize('candidate', ['qwen3.5-9b', 'devstral-small-2507'])
def test_both_actual_native_preparations_share_budget_and_recover_after_five_schema_errors(tmp_path, candidate):
    pytest.importorskip('openhands.sdk')
    from proworksim.harness_sdk import HarnessWorker
    from proworksim.software_context_v028 import SoftwareContextTransport
    owner = NativeCPUOwner(candidate, ['42'] * 5 + ['"recovered"', '"member-b"'])
    budget, executed, events = ledger(max_attempts=7), [], []
    transport = SoftwareContextTransport(owner, tmp_path / 'transport')
    tools = [{'name': 'write_note', 'description': 'CPU protocol fixture only.',
              'parameters': {'type': 'object', 'properties': {'text': {'type': 'string', 'minLength': 3}},
                             'required': ['text'], 'additionalProperties': False}}]
    # Qwen's string wire retains text literally, while Mistral uses JSON string
    # values; use one common minimum length constraint to reject literal 42 too.
    workers = [HarnessWorker(role, tools, sdk_config(owner), transport,
                lambda *args: executed.append(args) or {'ok': True, 'fixture_only': True},
                event_sink=lambda kind, payload: events.append((kind, copy.deepcopy(payload))),
                directory=tmp_path / role, team_budget=budget) for role in ('member_a', 'member_b')]
    try:
        for index in range(5):
            rejected = workers[0].step({}, {'run_id': 'cpu-native', 'opportunity_id': str(index)})
            assert rejected['kind'] == 'protocol_rejection' and rejected['executed'] is False
            assert not executed
        assert workers[0].format_errors == {'total': 5, 'consecutive': 5}
        assert workers[0].step({}, {'run_id': 'cpu-native', 'opportunity_id': 'recovered'})['executed']
        assert workers[1].step({}, {'run_id': 'cpu-native', 'opportunity_id': 'other-member'})['executed']
        snapshot = budget.snapshot()
        assert snapshot['decisions'] == snapshot['attempts'] == len(owner.requests) == 7
        assert snapshot['charged_tokens'] == sum(worker.meter['reported_total_tokens'] for worker in workers)
        assert snapshot['held_tokens'] == 0 and len(executed) == 2
        feedback = [row['feedback'] for kind, row in events if kind == 'model_format_feedback']
        assert len(feedback) == 5 and all(row['continues_on_later_opportunity'] for row in feedback)
        assert all(row['format_limits'] == {'max_total': None, 'max_consecutive': None} for row in feedback)
        assert all(row['world_action_executed'] is False for row in feedback)
        assert all(row['version'] == 'public-format-feedback-v0.33' for row in feedback)
        for row in snapshot['records'].values():
            assert row['reservation']['preparation']['original_request_sha256']
            assert row['charge']['usage_status'] == 'reported_actual_trace'
        assert SharedTeamBudget.from_snapshot(snapshot).snapshot() == snapshot
        with pytest.raises(PolicyBoundaryError) as stopped:
            workers[1].step({}, {'run_id': 'cpu-native', 'opportunity_id': 'shared-attempt-limit'})
        assert stopped.value.status == 'team_budget_exhausted'
        assert stopped.value.details['limits'] == ['team_max_attempts']
        assert len(owner.requests) == 7 and transport._prepared is None
        assert budget.snapshot()['attempts'] == 7 and budget.snapshot()['held_tokens'] == 0
    finally:
        for worker in workers:
            worker.close()


def test_sdk_new_protocol_keeps_unauthorized_tools_terminal(tmp_path):
    pytest.importorskip('openhands.sdk')
    from proworksim.harness_sdk import HarnessWorker
    class Transport:
        def complete(self, request, **_):
            response = {'id': 'permission-fixture', 'object': 'chat.completion', 'created': 0,
                        'model': 'fixture', 'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
                        'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {'role': 'assistant',
                            'content': None, 'tool_calls': [{'id': 'forbidden-call', 'type': 'function',
                                'function': {'name': 'outside_gateway', 'arguments': '{}'}}]}}]}
            return {'http_status': 200, 'body': response, 'raw_body': json.dumps(response)}
    config = {'model': 'fixture', 'api_key_env': None, 'base_url': 'http://127.0.0.1',
              'format_error_policy': FORMAT_FEEDBACK_BUDGETED_V033,
              'retry': {'max_attempts': 1, 'backoff_seconds': []}}
    worker = HarnessWorker('member_a', [], config, Transport(),
                           lambda *_: pytest.fail('An unauthorized tool cannot execute'), directory=tmp_path)
    try:
        with pytest.raises(PolicyBoundaryError) as stopped:
            worker.step({}, {'run_id': 'cpu', 'opportunity_id': '1'})
        assert stopped.value.status == 'model_permission_error'
        assert worker.format_errors == {'total': 0, 'consecutive': 0}
    finally:
        worker.close()


def test_sdk_transport_integrity_failure_is_blocking_and_charged_once(tmp_path):
    pytest.importorskip('openhands.sdk')
    from proworksim.harness_sdk import HarnessWorker
    from proworksim.software_context_v028 import SoftwareContextTransport
    owner = NativeCPUOwner('qwen3.5-9b', ['"unused"'])
    def corrupted_transport(request, **_):
        raise ValueError('Actual resident tokenized prompt differs from admission')
    owner.transport = SimpleNamespace(complete=corrupted_transport)
    budget = ledger()
    transport = SoftwareContextTransport(owner, tmp_path / 'transport')
    worker = HarnessWorker('member_a', [], sdk_config(owner), transport,
                           lambda *_: pytest.fail('Integrity failure cannot execute'),
                           directory=tmp_path / 'sdk', team_budget=budget)
    try:
        with pytest.raises(PolicyBoundaryError) as stopped:
            worker.step({}, {'run_id': 'cpu-integrity', 'opportunity_id': '1'})
        assert stopped.value.status == 'execution_integrity_error'
        snapshot = budget.snapshot()
        assert snapshot['attempts'] == snapshot['decisions'] == 1
        record = next(iter(snapshot['records'].values()))
        assert snapshot['charged_tokens'] == record['reservation']['token_reservation']
        assert snapshot['charged_tokens'] == worker.meter['budget_accounted_tokens']
        budget.cleanup('member_a', record['call_id'])
        assert budget.snapshot()['charged_tokens'] == snapshot['charged_tokens']
        assert worker.format_errors == {'total': 0, 'consecutive': 0}
        assert transport._prepared is None
    finally:
        worker.close()
