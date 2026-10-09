"""Real SDK + v034 selector CPU controls. No tokenizer/model/GPU is loaded."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.software_context_v034 import SoftwareContextTransport
from proworksim.software_organization_runtime_v040 import (
    apply_process_contract, build_runtime, close_runtime, error_policy_summary, organization_evidence, run_fragment,
)
from proworksim.software_organization_v040 import (
    CASE_IDS, MEMBERS, PROJECT, build_software_collaboration_case, case_spec, material,
)
from proworksim.storage import digest
from test_software_organization_runtime_v038 import CPUOwner, action


ORIGINAL = json.loads((Path(__file__).parent / "fixtures/v040_original_work_done.json").read_text())


def tokenize(text, **kwargs):
    """Deterministic synthetic 64-character blocks; never model token evidence."""
    return {"input_ids": [int(digest(text[index:index + 64].encode())[:7], 16)
                          for index in range(0, len(text), 64)]}


class SelectedCPUTransport:
    def __init__(self, owner, *, mutate=None):
        self.owner, self.mutate, self.requests, self.responses, self.calls = owner, mutate, [], [], {}

    def complete(self, request, **kwargs):
        self.requests.append(copy.deepcopy(request))
        payload = next(json.loads(message["content"]) for message in reversed(request["messages"])
                       if message["role"] == "user" and '"observation"' in message["content"])
        member = payload["observation"]["actor_id"]
        index = self.calls.get(member, 0)
        self.calls[member] = index + 1
        script = self.owner.script.get(member, [])
        name, arguments = script[index] if index < len(script) else action("staff_done", reason="CPU fixture complete")
        identifier = "explicit-cpu-v040-" + str(len(self.requests))
        choice = {"index": 0, "finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
            "tool_calls": [{"id": identifier + "-tool", "type": "function", "function": {
                "name": name, "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments)}}]}}
        output_ids = [3]
        if name == "original_work_done_fixture":
            choice, output_ids = copy.deepcopy(ORIGINAL["choice"]), ORIGINAL["original_output_ids"]
        input_ids = tokenize(self.owner.prepare_request(request)[0])["input_ids"]
        body = {"id": identifier, "object": "chat.completion", "created": 0,
            "model": "explicit-cpu-not-generated", "actor_identity": self.owner.freeze_identity(),
            "online_window_id": self.owner.window_id, "choices": [choice],
            "usage": {"prompt_tokens": len(input_ids), "completion_tokens": len(output_ids),
                      "total_tokens": len(input_ids) + len(output_ids)},
            "token_trace": {"input_ids": input_ids, "output_ids": output_ids, "fixture_only": True}}
        if name == "original_work_done_fixture":
            body.update(raw_generated_text=ORIGINAL["raw_generated_text"],
                cpu_fixture_source={"sha256": ORIGINAL["source_response_sha256"],
                    "path": ORIGINAL["source_response_path"], "scope": ORIGINAL["scope"]})
        if self.mutate:
            self.mutate(body)
        self.responses.append(copy.deepcopy(body))
        return {"http_status": 200, "body": body, "raw_body": json.dumps(body)}


def setup(tmp_path, script, *, worker_factory=None, mutate=None, prepare=None):
    pytest.importorskip("openhands.sdk")
    owner = CPUOwner(script)
    owner.begin_window("explicit-v040-sdk-cpu-control")
    owner.prepare_request = lambda request: (json.dumps(request, ensure_ascii=False, sort_keys=True), None, None)
    owner.tokenizer = tokenize
    owner.transport = SelectedCPUTransport(owner, mutate=mutate)
    selector = SoftwareContextTransport(owner, tmp_path / "raw-transport")
    facade = SimpleNamespace(window_id=owner.window_id, recipe=owner.recipe,
                             freeze_identity=owner.freeze_identity, transport=selector)
    prepared = build_software_collaboration_case(case_spec(CASE_IDS[0], condition="PB"), tmp_path / "case")
    if prepare:
        prepare(prepared)
    runtime, captured, interfaces = build_runtime(facade, prepared, tmp_path / "runtime", worker_factory=worker_factory)
    return owner, prepared, runtime, captured, interfaces


def fixed_submission(prepared):
    """CPU setup only; it claims no model-produced implementation or success."""
    session = prepared.world.session(MEMBERS[0], PROJECT)
    path = next(path for path in prepared.case["editable_paths"] if path != "test_member.py")
    for name, arguments in [action("create_task", task_id="cpu-task", description="Explicit CPU fixture"),
            action("claim_task", task_id="cpu-task"),
            action("write_file", path=path, text=material(CASE_IDS[0])["files"][path] + "\n# CPU fixed-tree witness\n"),
            action("run_tests"), action("fix_patch", task_ids=["cpu-task"], message="CPU fixture fixed tree"),
            action("submit_integration", message="CPU fixture submission, not a success claim")]:
        result = session.call(name, **arguments)
        assert result["ok"], result


@pytest.mark.parametrize("after_submission", [False, True])
def test_original_work_done_rejection_keeps_cost_and_fixed_tree_then_new_legal_decision(tmp_path, after_submission):
    owner, prepared, runtime, _, _ = setup(tmp_path, {
        MEMBERS[0]: [action("original_work_done_fixture"), action("work_note", key="corrected", text="New legal decision")],
        MEMBERS[1]: [action("staff_done", reason="CPU permanent retirement")]},
        prepare=fixed_submission if after_submission else None)
    before_files = copy.deepcopy(prepared.world._bundle(MEMBERS[0])[2])
    before_deliveries = copy.deepcopy(prepared.world._software()["deliveries"])
    witnessed = []

    def checkpoint(outcome):
        if any(event["kind"] == "preexecution_action_rejection" for event in runtime.recorder.events) and not witnessed:
            witnessed.append(copy.deepcopy(outcome))
            assert runtime.policies[MEMBERS[0]]._executions == 0
            assert runtime.ports[MEMBERS[0]].notes == {}
            assert prepared.world._bundle(MEMBERS[0])[2] == before_files
            assert prepared.world._software()["deliveries"] == before_deliveries
            assert prepared.world._software()["registry"][MEMBERS[0]]["status"] == "live"
    try:
        boundary = run_fragment(prepared, runtime, on_opportunity=checkpoint)
        assert witnessed and boundary["execution_integrity_failure"] is None
        assert runtime.ports[MEMBERS[0]].notes == {"corrected": "New legal decision"}
        assert prepared.world._bundle(MEMBERS[0])[2] == before_files
        assert prepared.world._software()["deliveries"] == before_deliveries
        summary = error_policy_summary(runtime)
        assert summary["recoverable_unknown_names"] == 1 and summary["process_violation"] is False
        assert summary["unknown_name_rejections"][0]["tool_name"] == "work_done"
        assert runtime.team_budget.snapshot()["decisions"] == len(owner.transport.requests) == 4
        assert runtime.policies[MEMBERS[0]].meter["decisions"] == 3
        assert runtime.policies[MEMBERS[1]].meter["decisions"] == 1
        evidence = organization_evidence(prepared, runtime)
        assert evidence["total_usage"]["completion_tokens"] == ORIGINAL["original_completion_tokens"] + 3
        assert evidence["total_usage"]["attempts"] == 4
        raw = json.loads((tmp_path / "raw-transport/request-00001/response.json").read_text())["body"]
        assert raw["choices"][0] == ORIGINAL["choice"] and raw["raw_generated_text"] == ORIGINAL["raw_generated_text"]
        next_selected = json.loads((tmp_path / "raw-transport/request-00003/selected-request.json").read_text())
        text = json.dumps(next_selected)
        assert "public_format_feedback" in text and "work_done" in text and "No tool was executed" in text
        assert '"name": "work_done"' not in text
        assert [body["choices"][0]["message"]["tool_calls"][0]["function"]["name"]
                for body in owner.transport.responses] == ["work_done", "staff_done", "work_note", "staff_done"]
    finally:
        close_runtime(runtime)


@pytest.mark.parametrize("invalid", [action("work_note", key="missing-text"), ("work_note", "{invalid-json")])
def test_ordinary_argument_failure_is_budgeted_feedback_and_allows_correction(tmp_path, invalid):
    owner, prepared, runtime, _, _ = setup(tmp_path, {MEMBERS[0]: [invalid, action("work_note", key="fixed", text="Valid later input")]})
    try:
        boundary = run_fragment(prepared, runtime)
        assert boundary["execution_integrity_failure"] is None
        policy = error_policy_summary(runtime)
        assert policy["recoverable_argument_errors"] == 1 and policy["recoverable_unknown_names"] == 0
        assert runtime.ports[MEMBERS[0]].notes == {"fixed": "Valid later input"}
        assert runtime.team_budget.snapshot()["decisions"] == len(owner.transport.requests) == 4
        assert "public_format_feedback" in (tmp_path / "raw-transport/request-00003/selected-request.json").read_text()
    finally:
        close_runtime(runtime)


def test_controller_request_is_process_violation_with_raw_success_kept_and_formal_zero(tmp_path):
    owner, prepared, runtime, _, _ = setup(tmp_path, {MEMBERS[0]: [action("controller_add_neutral_member", completed_team_decisions=8)]})
    try:
        boundary = run_fragment(prepared, runtime)
        assert boundary["execution_integrity_failure"] is None and len(runtime.labels) == 2
        assert len(prepared.world._software()["registry"]) == 2 and len(owner.transport.requests) == 3
        policy = error_policy_summary(runtime)
        assert policy["process_violation_count"] == 1 and policy["recoverable_unknown_names"] == 0
        raw = {"status": "evaluable", "R": 1, "passed": True, "submitted": True, "complete_delivery": True,
               "content_correct": True, "required_process_satisfied": True}
        result = apply_process_contract(raw, boundary, runtime)
        assert result["R"] == 0 and result["passed"] is False and result["complete_delivery"] is False
        assert result["raw_fixed_tree_R"] == 1 and result["raw_fixed_tree_passed"] is True and raw["R"] == 1
        unknown = apply_process_contract(raw, {"execution_integrity_failure": {"status": "execution_integrity_error"}}, runtime)
        assert unknown["status"] == "unknown" and unknown["R"] is None
        selected = (tmp_path / "raw-transport/request-00003/selected-request.json").read_text()
        assert "process violation" in selected and "public_format_feedback" in selected
    finally:
        close_runtime(runtime)


def test_split_selected_inputs_and_natural_child_use_same_policy_without_private_inheritance(tmp_path):
    pytest.importorskip("openhands.sdk")
    from proworksim.harness_policy_v040 import OrganizationHarnessWorker
    owner, prepared, runtime, _, _ = setup(tmp_path, {
        MEMBERS[0]: [action("work_note", key="secret", text="parent-private-z97"),
                     action("spawn_member", briefing="Only explicit neutral briefing")],
        MEMBERS[1]: [action("staff_wait", reason="Await an actual event")],
        MEMBERS[2]: [action("work_done", reason="CPU child unknown name")]})
    try:
        boundary = run_fragment(prepared, runtime)
        assert boundary["execution_integrity_failure"] is None
        assert len(runtime.policies) == 3
        assert all(type(worker) is OrganizationHarnessWorker for worker in runtime.policies.values())
        requests = {}
        for request in owner.transport.requests:
            observation = next(json.loads(message["content"])["observation"] for message in reversed(request["messages"])
                               if message["role"] == "user" and '"observation"' in message["content"])
            requests.setdefault(observation["actor_id"], []).append(request)
        facts = prepared.world._software()
        for member in MEMBERS[:2]:
            absent = set(facts["initial_diagnostics"]) - set(facts["initial_diagnostic_assignments"][member])
            assert all(identifier not in json.dumps(requests[member]) for identifier in absent)
        child = requests[MEMBERS[2]]
        assert len(child) == 2 and "parent-private-z97" not in json.dumps(child)
        assert "Only explicit neutral briefing" in json.dumps(child)
        assert all(identifier not in json.dumps(child) for identifier in facts["initial_diagnostics"])
        assert "public_format_feedback" in json.dumps(child[1])
        birth = runtime.birth_records[MEMBERS[2]]
        assert birth["new_budget_granted"] is False and birth["private_history_copied"] is False
        assert birth["shared_budget_at_session_birth"]["decisions"] == 3
        assert error_policy_summary(runtime)["recoverable_unknown_names"] == 1
    finally:
        close_runtime(runtime)


@pytest.mark.parametrize("mode", ["missing_native_id", "reserved_fields", "reused_native_id", "wrong_actor"])
def test_native_identity_reserved_fields_and_record_mismatch_remain_critical(tmp_path, mode):
    def mutate(body):
        if mode == "missing_native_id":
            body["choices"][0]["message"]["tool_calls"][0]["id"] = ""
        elif mode == "wrong_actor":
            body["actor_identity"] = {"policy_version": "unadmitted-actor"}
        elif mode == "reused_native_id":
            body["choices"][0]["message"]["tool_calls"][0]["id"] = "same-native-id"
    script = [action("work_done", **({"request_key": "forbidden-runtime-override"} if mode == "reserved_fields" else {}))]
    if mode == "reused_native_id":
        script = [action("work_note", key="before", text="Valid first call"), action("work_done")]
    _, prepared, runtime, _, _ = setup(tmp_path, {MEMBERS[0]: script}, mutate=mutate)
    try:
        boundary = run_fragment(prepared, runtime)
        assert boundary["execution_integrity_failure"] is not None
        assert error_policy_summary(runtime)["recoverable_unknown_names"] == 0
    finally:
        close_runtime(runtime)


def test_inherited_default_unknown_name_boundary_stays_critical(tmp_path):
    pytest.importorskip("openhands.sdk")
    from proworksim.harness_sdk import HarnessWorker
    _, prepared, runtime, _, _ = setup(tmp_path, {MEMBERS[0]: [action("work_done")]}, worker_factory=HarnessWorker)
    try:
        boundary = run_fragment(prepared, runtime)
        assert boundary["execution_integrity_failure"]["status"] == "model_permission_error"
        assert error_policy_summary(runtime)["recoverable_unknown_names"] == 0
    finally:
        close_runtime(runtime)
