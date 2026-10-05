"""Strict offline admission-stop proofs; no new generation or archive repair."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from proworksim.member_views import member_view
from proworksim.staff_runtime import PolicyBoundaryError
from proworksim.storage import digest, json_bytes
from proworksim.team_budget_v033 import SharedTeamBudget
from test_online_support_v013 import declaration, rollout


def reseal(value, key):
    value[key] = digest(json_bytes({name: item for name, item in value.items() if name != key}))


def fixture(kind="tokens"):
    decl = declaration(active=("provider", "consumer"), slots=1)
    result = rollout(decl, "0")
    identity, window_id = decl["actor_identity"], decl["window_id"]
    for policy in result["manifest"]["policies"].values():
        policy["config"].update(backend_id="resident_direct", format_error_policy="format_feedback_budgeted_v033",
                                max_context_tokens=100, max_output_tokens=10)
    result["window"]["team_policy_fingerprint"] = digest(json_bytes(result["manifest"]["policies"]))
    result["manifest"].update(status="closed", identity={"instance_id": "explicit-fixture-world"})
    budget = SharedTeamBudget(members=list(result["members"]), team_id=window_id,
                              max_total_tokens=20 if kind == "tokens" else 500000)

    def reservation(request_sha, n):
        prepared = {"version": "resident-request-budget-v0.31r3", "original_request_sha256": request_sha,
                    "selected_request_sha256": request_sha, "rendered_prompt_sha256": digest(b"fixture prompt"),
                    "input_ids_sha256": digest(json_bytes([1, 2] if n == 2 else list(range(n)))),
                    "recipe_sha256": digest(b"fixture recipe"), "prompt_tokens": n, "reserved_output_tokens": 10,
                    "context_limit": 100, "fits": n + 10 <= 100, "actor_identity": identity, "window_id": window_id}
        reseal(prepared, "preparation_sha256")
        return {"request_bytes": 100, "input_token_reservation": n, "output_token_reservation": 10,
                "token_reservation": n + 10, "cost_reservation_usd": 0.0,
                "reservation_kind": "exact_resident_prompt", "preparation": prepared}

    for event in result["events"]:
        if event["kind"] != "model_response":
            continue
        call_id, member = event["payload"]["call_id"], event["worker_id"]
        start = next(item for item in result["events"] if item["kind"] == "model_call" and item["payload"]["call_id"] == call_id)
        budget.consume_decision(member, call_id)
        budget.reserve(member, call_id, reservation(start["payload"]["request_sha256"], 2))
        budget.begin_attempt(member, call_id)
        budget.settle(member, call_id, event["payload"]["response"])
    call_id, opportunity = "unattempted-shared-stop", "explicit-fixture-opportunity"
    config = result["manifest"]["policies"]["provider"]["config"]
    reserved = reservation(digest(b"unchanged rejected request"), 15 if kind == "tokens" else 95)
    start = {"sequence": len(result["events"]), "kind": "model_call", "worker_id": "provider", "payload": {
        "stage": "started", "worker_id": "provider", "call_id": call_id, "decision_id": call_id,
        "opportunity_id": opportunity, "decision_index": 2, "backend_id": "resident_direct",
        "weight_identity": identity, "model_revision": identity["policy_version"], "config": config,
        "request_sha256": reserved["preparation"]["original_request_sha256"],
        "context_selection": {"request_sha256": reserved["preparation"]["original_request_sha256"]},
        "reservation": reserved}}
    result["events"].append(copy.deepcopy(start))
    budget.consume_decision("provider", call_id)
    with pytest.raises(PolicyBoundaryError) as stopped:
        budget.reserve("provider", call_id, reserved)
    boundary = {"sequence": len(result["events"]), "kind": "model_boundary_error", "worker_id": "provider",
                "payload": {"status": stopped.value.status, "opportunity_id": opportunity, **stopped.value.details}}
    result["events"].append(boundary)
    termination = {"status": "bounded_work_closed", "execution_integrity_failure": None,
                   "role_stops": {"provider": stopped.value.status, "consumer": "completed"},
                   "team_budget": {"world_instance_id": "explicit-fixture-world", "model": budget.snapshot()}}
    result["manifest"]["termination"] = copy.deepcopy(termination)
    result["events"].append({"sequence": len(result["events"]), "kind": "run_boundary", "worker_id": None,
                             "payload": copy.deepcopy(termination)})
    return result


@pytest.mark.parametrize("kind", ["tokens", "context"])
def test_sealed_actual_admission_rejection_has_no_actor_target_and_preserves_archive(kind):
    result = fixture(kind)
    before = copy.deepcopy(result)
    view = member_view(result, "provider")
    assert result == before
    assert view["complete_semantic_trajectory"] and view["complete_actor_trajectory"]
    assert view["own_action_count"] == 1 and view["own_action_tokens"] == 1
    last = view["decisions"][-1]
    assert last["generation_status"] == "not_started_shared_admission_rejection"
    assert last["actor_required"] is False and last["actor_trainable"] is False
    assert last["actual_input"] is last["actual_response"] is last["tokens"] is None
    assert last["non_generation_evidence"]["limits"] == ["team_max_total_tokens" if kind == "tokens" else "context_capacity"]


@pytest.mark.parametrize("change", [
    "missing_boundary", "duplicate_boundary", "boundary_member", "boundary_opportunity", "start_actor",
    "start_config", "reservation", "broken_seal", "forged_capacity", "charged_rejection",
    "already_attempted", "started_attempt", "response_without_attempt", "world_action", "harness_action",
    "final_ledger", "world_instance", "final_integrity_failure", "missing_paid_response", "corrupt_paid_usage",
])
def test_missing_ambiguous_or_forged_evidence_never_hides_an_actor_record(change):
    result = fixture()
    start, boundary, end = result["events"][-3:]
    call_id = start["payload"]["call_id"]
    if change == "missing_boundary":
        result["events"].remove(boundary)
    elif change == "duplicate_boundary":
        result["events"].insert(-1, copy.deepcopy(boundary))
    elif change == "boundary_member":
        boundary["worker_id"] = "consumer"
    elif change == "boundary_opportunity":
        boundary["payload"]["opportunity_id"] = "unrelated"
    elif change == "start_actor":
        start["payload"]["weight_identity"] = {"version": "fabricated"}
    elif change == "start_config":
        start["payload"]["config"]["max_output_tokens"] += 1
    elif change == "reservation":
        start["payload"]["reservation"]["token_reservation"] += 1
    elif change == "broken_seal":
        boundary["payload"]["team_budget"]["charged_tokens"] += 1
    elif change == "forged_capacity":
        for value in (boundary["payload"]["team_budget"], end["payload"]["team_budget"]["model"],
                      result["manifest"]["termination"]["team_budget"]["model"]):
            value["limits"]["max_total_tokens"] = 500000
            value["available_tokens"] = 500000 - value["charged_tokens"]
            reseal(value, "state_sha256")
    elif change in {"charged_rejection", "already_attempted"}:
        for value in (boundary["payload"]["team_budget"], end["payload"]["team_budget"]["model"],
                      result["manifest"]["termination"]["team_budget"]["model"]):
            row = value["records"][call_id]
            if change == "charged_rejection":
                row["charge"] = {"charged_tokens": 0}
            else:
                row["attempt_started"] = True
            reseal(value, "state_sha256")
    elif change in {"started_attempt", "response_without_attempt", "world_action", "harness_action"}:
        kind = {"started_attempt": "model_attempt", "response_without_attempt": "model_response",
                "world_action": "tool_call", "harness_action": "harness_tool_call"}[change]
        result["events"].insert(-2, {"sequence": start["sequence"], "kind": kind, "worker_id": "provider",
                                   "payload": {"stage": "started", "call_id": call_id, "model_call_id": call_id}})
    elif change == "final_ledger":
        end["payload"]["team_budget"]["model"] = {}
    elif change == "world_instance":
        result["manifest"]["identity"]["instance_id"] = "another-world"
    elif change == "final_integrity_failure":
        for value in (end["payload"], result["manifest"]["termination"]):
            value["execution_integrity_failure"] = {"status": "execution_integrity_error"}
    elif change == "missing_paid_response":
        result["events"] = [event for event in result["events"]
                            if not (event["kind"] == "model_response" and event["worker_id"] == "consumer")]
    elif change == "corrupt_paid_usage":
        event = next(event for event in result["events"] if event["kind"] == "model_response")
        event["payload"]["response"]["usage"]["total_tokens"] += 1
    view = member_view(result, "provider")
    assert view["decisions"][-1]["actor_required"] is True
    assert view["decisions"][-1]["generation_status"] == "unknown_or_missing"
    assert not view["complete_semantic_trajectory"]


@pytest.mark.parametrize('change', [None, 'missing_stop', 'false_meter'])
def test_mixed_personal_exact_stop_and_peer_shared_stop_need_both_original_proofs(change):
    result = fixture()
    shared_start, shared_boundary, end = result['events'][-3:]
    config = result['manifest']['policies']['consumer']['config']
    config['budget'] = {'max_total_tokens': 20}
    result['window']['team_policy_fingerprint'] = digest(json_bytes(result['manifest']['policies']))
    personal_id, opportunity = 'personal-exact-preflight-stop', 'personal-opportunity'
    personal_start = copy.deepcopy(shared_start)
    personal_start['worker_id'] = 'consumer'
    personal_start['payload'].update(worker_id='consumer', call_id=personal_id, decision_id=personal_id,
                                     opportunity_id=opportunity, config=copy.deepcopy(config))
    personal_stop = {'kind': 'model_budget_stop', 'worker_id': 'consumer', 'payload': {
        'call_id': personal_id, 'limits': ['max_total_tokens_exact_reservation'],
        'reservation': copy.deepcopy(personal_start['payload']['reservation']),
        'meter': {'decisions': 2, 'http_attempts': 1, 'unknown_usage_attempts': 0,
                  'reported_prompt_tokens': 2, 'reported_completion_tokens': 1,
                  'reported_total_tokens': 3, 'budget_accounted_tokens': 3}}}
    personal_boundary = {'kind': 'model_boundary_error', 'worker_id': 'consumer', 'payload': {
        'model_call_id': personal_id, 'opportunity_id': opportunity,
        'status': 'model_budget_exhausted', 'limits': ['max_total_tokens_exact_reservation']}}
    result['events'][-3:-3] = [personal_start, personal_stop, personal_boundary]
    for index, event in enumerate(result['events']):
        event['sequence'] = index
    for value in (shared_boundary['payload']['team_budget'], end['payload']['team_budget']['model'],
                  result['manifest']['termination']['team_budget']['model']):
        value['records'][personal_id] = {'call_id': personal_id, 'member': 'consumer',
                                         'status': 'decision_consumed', 'attempt_started': False}
        value['decisions'] += 1
        value['remaining_decisions'] -= 1
        reseal(value, 'state_sha256')
    result['manifest']['termination']['role_stops']['consumer'] = 'model_budget_exhausted'
    end['payload']['role_stops']['consumer'] = 'model_budget_exhausted'
    if change == 'missing_stop':
        result['events'].remove(personal_stop)
    elif change == 'false_meter':
        personal_stop['payload']['meter']['budget_accounted_tokens'] += 1
    view = member_view(result, 'provider')
    assert view['decisions'][-1]['actor_required'] is (change is not None)
    assert view['complete_semantic_trajectory'] is (change is None)
    assert view['own_action_count'] == 1
    if change is None:
        own = member_view(result, 'consumer')
        assert own['decisions'][-1]['generation_status'] == 'not_started_budget_stop'
        assert own['complete_semantic_trajectory']


@pytest.mark.parametrize("candidate,actions", [("qwen3.5-9b", [22, 21]), ("devstral-small-2507", [21, 21])])
def test_saved_actual_v033_team_rejections_are_explained_without_original_file_changes(candidate, actions):
    project = Path(__file__).resolve().parents[1]
    diagnostics = project / 'runs/software-paired-o1-v033' / candidate / 'actual/diagnostics'
    if not (diagnostics / 'slot-1/team-rollout.json').is_file():
        pytest.skip('Original v033 archive is not present; synthetic negative controls still apply')
    frozen = project / 'runs/v033-frozen-source/src/proworksim/member_views.py'
    spec = importlib.util.spec_from_file_location('proworksim._frozen_member_view_control', frozen)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    for slot in ('slot-0', 'slot-1'):
        root = diagnostics / slot
        path = root / 'team-rollout.json'
        before = digest(path.read_bytes())
        result = json.loads(path.read_text())
        original_event_digest = digest(json_bytes(result['events']))
        for index, member in enumerate(result['members']):
            previous, view = old.member_view(result, member), member_view(result, member)
            if slot == 'slot-0':
                assert view == previous
                continue
            assert view['own_action_count'] == previous['own_action_count'] == actions[index]
            assert view['own_action_tokens'] == previous['own_action_tokens']
            assert view['complete_semantic_trajectory'] and view['complete_actor_trajectory']
            assert view['decisions'][:-1] == previous['decisions'][:-1]
            assert previous['decisions'][-1]['actor_required'] is True
            last = view['decisions'][-1]
            assert last['actor_required'] is False and last['non_generation_evidence']['generation_attempts'] == 0
            for key in ('call_id', 'actual_input', 'actual_response', 'tokens', 'actor_trainable', 'world_actions', 'behavior_metadata'):
                assert last[key] == previous['decisions'][-1][key]
        assert digest(json_bytes(result['events'])) == original_event_digest
        assert digest(path.read_bytes()) == before
        assert result['manifest']['termination']['team_budget']['model'] == json.loads((root / 'team-budget.json').read_text())['model']
