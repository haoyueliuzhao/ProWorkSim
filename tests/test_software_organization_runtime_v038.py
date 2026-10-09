"""CPU scripted gateway controls only; no model weights, training or performance evidence."""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim.software_organization_v038 import (
    CASE_IDS, build_software_collaboration_case, case_spec, material,
)
from proworksim.software_organization_runtime_v038 import (
    SharedTeamBudget, build_runtime, close_runtime, collect_episode, organization_evidence, run_fragment,
)
from proworksim.storage import digest, json_bytes


class ScriptedWorker:
    """Synthetic CPU tool producer using the real runtime, ports and shared ledger."""
    def __init__(self, role_id, tools, config, *, transport, team_budget, execute,
                 event_sink, directory, context_selection):
        self.role_id, self.config, self.team_budget = role_id, config, team_budget
        self.script = transport.script.get(role_id, [])
        self.transport, self.execute, self.event_sink = transport, execute, event_sink
        self.observations, self.results, self.meter = [], [], {"decisions": 0}
        self.closed = False

    def step(self, observation, *, opportunity, model_identity):
        self.observations.append(copy.deepcopy(observation))
        index = self.meter["decisions"]
        self.meter["decisions"] += 1
        call_id = self.role_id + "-cpu-control-" + str(index)
        self.team_budget.consume_decision(self.role_id, call_id)
        request = {"messages": [{"role": "user", "content": json.dumps(observation)}]}
        prepared = {"version": "resident-request-budget-v0.31r3", "window_id": self.team_budget.snapshot()["team_id"],
            "actor_identity": model_identity, "prompt_tokens": 2, "reserved_output_tokens": 1,
            "context_limit": 100, "fits": True, "input_ids_sha256": digest(json_bytes([1, 2])),
            **{key: digest(key.encode()) for key in ("original_request_sha256", "selected_request_sha256",
                "rendered_prompt_sha256", "recipe_sha256")}}
        prepared["preparation_sha256"] = digest(json_bytes(prepared))
        self.team_budget.reserve(self.role_id, call_id, {"token_reservation": 3,
            "reservation_kind": "exact_resident_prompt", "preparation": prepared})
        self.team_budget.begin_attempt(self.role_id, call_id)
        body = {"id": call_id, "actor_identity": model_identity, "online_window_id": prepared["window_id"],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            "token_trace": {"input_ids": [1, 2], "output_ids": [3], "fixture_only": True}}
        self.team_budget.settle(self.role_id, call_id, body)
        self.event_sink("model_attempt", {"call_id": call_id, "stage": "finished", "request": request,
            "response": {"body": body}, "status": "success", "fixture_only": True})
        action, arguments = self.script[index] if index < len(self.script) else ("staff_done", {"reason": "CPU script complete"})
        result = self.execute(action, arguments, {"model_call_id": call_id, "decision_id": call_id,
                                                  "model_tool_call_id": call_id + "-tool"})
        self.results.append(result)
        return {"kind": {"staff_done": "done", "staff_wait": "wait"}.get(action, "act"),
                "reason": arguments.get("reason", ""), "memory": self.snapshot()}

    def snapshot(self):
        return {"meter": self.meter, "fixture_only": True, "observations": len(self.observations)}

    def close(self):
        self.closed = True


def build(tmp_path, script, *, condition="O3", first_member=None):
    case = case_spec(CASE_IDS[0], condition=condition, first_member=first_member)
    prepared = build_software_collaboration_case(case, tmp_path / "world-case")
    identity = {"policy_version": "scripted-cpu-control-only", "adapter_sha256": "no-model-weights"}
    owner = SimpleNamespace(window_id="organization-cpu-control", recipe={"temperature": 0.7,
        "max_output_tokens": 2048, "max_length": 16384,
        "members": ["member_a", "member_b", "software_inactive"]},
        transport=SimpleNamespace(script=script), freeze_identity=lambda: copy.deepcopy(identity))
    runtime, captured, interfaces = build_runtime(owner, prepared, tmp_path / "runtime", worker_factory=ScriptedWorker)
    return prepared, runtime, captured, interfaces


def action(name, **arguments):
    return name, arguments


def test_birth_registration_keeps_consumed_shared_pool_and_no_identity_reuse():
    budget = SharedTeamBudget(members=["member_001", "member_002"], team_id="cpu-control",
                              require_exact_resident=False)
    budget.consume_decision("member_001", "first")
    budget.reserve("member_001", "first", {"token_reservation": 100})
    budget.begin_attempt("member_001", "first")
    budget.settle("member_001", "first", {"id": "response-1", "usage": {
        "prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}})
    before = budget.snapshot()
    after = budget.register_member("member_003")
    for key in ("limits", "records", "charged_tokens", "remaining_decisions", "remaining_attempts", "available_tokens"):
        assert after[key] == before[key]
    assert after["members"] == ["member_001", "member_002", "member_003"]
    with pytest.raises(ValueError, match="registered again"):
        budget.register_member("member_003")
    with pytest.raises(ValueError, match="six"):
        budget.register_member("member_a")
    restored = SharedTeamBudget.from_snapshot(after)
    restored.register_member("member_004")
    assert restored.snapshot()["charged_tokens"] == 30
    assert restored.snapshot()["remaining_decisions"] == 127


def test_dynamic_birth_builds_empty_private_session_and_correct_fair_successor(tmp_path):
    secret = "private-parent-only-token-z98"
    briefing = "Inspect the public contract and choose whether any work is useful."
    prepared, runtime, captured, interfaces = build(tmp_path, {
        "member_001": [action("work_note", key="secret", text=secret),
                       action("spawn_member", briefing=briefing)],
        "member_002": [action("staff_wait", reason="Wait for reachable work")],
    })
    try:
        boundary = run_fragment(prepared, runtime)
        order = [row["worker_id"] for row in boundary["outcomes"]]
        assert order[:4] == ["member_001", "member_002", "member_001", "member_003"]
        assert set(runtime.labels) == set(captured) == set(interfaces) == {"member_001", "member_002", "member_003"}
        child = runtime.policies["member_003"]
        assert child.transport is runtime.policies["member_001"].transport
        assert child.team_budget is runtime.policies["member_001"].team_budget
        assert secret not in json.dumps(child.observations)
        assert secret not in child.config["task"] and briefing in child.config["task"]
        assert runtime.ports["member_003"].notes == {}
        assert runtime.ports["member_001"].notes == {"secret": secret}
        record = runtime.birth_records["member_003"]
        assert record["shared_budget_at_session_birth"]["decisions"] == 3
        assert record["shared_budget_at_session_birth"]["remaining_decisions"] == 125
        assert record["private_history_copied"] is False and record["new_budget_granted"] is False
        for observation in child.observations:
            rendered = json.dumps(observation)
            assert '"member_a"' not in rendered and '"member_b"' not in rendered and "software_inactive" not in rendered
    finally:
        close_runtime(runtime)


def test_waiting_ignores_private_work_and_wakes_only_after_real_addressed_message(tmp_path):
    prepared, runtime, _, _ = build(tmp_path, {
        "member_001": [action("staff_wait", reason="Await an actual message")],
        "member_002": [action("work_note", key="private", text="Does not wake partner"),
                       action("send_message", recipient="member_001", task_id="root_goal", body="Real reachable work")],
    }, condition="O1")
    try:
        boundary = run_fragment(prepared, runtime)
        order = [row["worker_id"] for row in boundary["outcomes"]]
        assert order[:4] == ["member_001", "member_002", "member_002", "member_001"]
        wakes = [row for row in runtime.recorder.events if row["kind"] == "role_reactivated"]
        assert len(wakes) == 1 and wakes[0]["worker_id"] == "member_001"
        sequences = wakes[0]["payload"]["event_sequences"]
        events = prepared.world.store.load()["software_events"]
        assert [row["kind"] for row in events if row["sequence"] in sequences] == ["work_message"]
        assert wakes[0]["payload"]["budget_reset"] is False
    finally:
        close_runtime(runtime)


def test_done_is_permanent_and_two_waiters_close_without_synthetic_wake(tmp_path):
    prepared, runtime, _, _ = build(tmp_path, {
        "member_001": [action("staff_done", reason="Permanent exit")],
        "member_002": [action("send_message", recipient="member_001", task_id="root_goal", body="Cannot revive")],
    }, condition="O1")
    try:
        boundary = run_fragment(prepared, runtime)
        assert [row["worker_id"] for row in boundary["outcomes"]].count("member_001") == 1
        assert prepared.world._software()["registry"]["member_001"]["status"] == "retired"
        assert runtime.policies["member_002"].results[0]["ok"] is False
        assert not [row for row in runtime.recorder.events if row["kind"] == "role_reactivated"]
    finally:
        close_runtime(runtime)
    prepared, runtime, _, _ = build(tmp_path / "waiters", {
        member: [action("staff_wait", reason="No actual future event")]
        for member in ("member_001", "member_002")}, condition="O1")
    try:
        boundary = run_fragment(prepared, runtime)
        assert boundary["closure_reason"] == "no_reachable_future_events"
        assert boundary["opportunities"] == 2
        assert set(boundary["waiting_members"]) == {"member_001", "member_002"}
    finally:
        close_runtime(runtime)


def test_birth_briefing_is_not_child_output_when_child_has_no_opportunity(tmp_path):
    prepared, runtime, _, _ = build(tmp_path, {
        "member_001": [action("spawn_member", briefing="This is parent output and child input only")],
    })
    try:
        # Reach the last decision with a real, explicitly synthetic control ledger.
        # No replayed or fabricated child attempt is added to either evidence stream.
        for index in range(127):
            runtime.team_budget.consume_decision("member_001", "past-control-" + str(index))
        boundary = run_fragment(prepared, runtime)
        assert boundary["closure_reason"] == "shared_team_pool_exhausted"
        assert runtime.labels == ["member_001", "member_002", "member_003"]
        assert runtime.policies["member_003"].meter["decisions"] == 0
        evidence = organization_evidence(prepared, runtime)
        assert evidence["member_lifecycle"]["cumulative_births"] == 3
        assert evidence["member_lifecycle"]["actual_output_participants"] == 1
        assert evidence["member_lifecycle"]["participating_members"] == ["member_001"]
        assert evidence["usage_by_member"]["member_003"]["completion_tokens"] == 0
        assert evidence["total_usage"]["completion_tokens"] == 1
        assert evidence["total_usage"]["attempts"] == 1
        assert evidence["training_eligible"] is False and evidence["admission_eligible"] is False
    finally:
        close_runtime(runtime)


def test_four_members_get_fair_opportunities_from_declared_first_member(tmp_path):
    members = [f"member_{index:03d}" for index in range(1, 5)]
    prepared, runtime, _, _ = build(tmp_path, {
        member: [action("work_note", key="cpu", text="Independent private session")]
        for member in members}, condition="O2", first_member="member_003")
    try:
        boundary = run_fragment(prepared, runtime)
        order = [row["worker_id"] for row in boundary["outcomes"]]
        assert order == ["member_003", "member_004", "member_001", "member_002"] * 2
        assert all(runtime.policies[member].meter["decisions"] == 2 for member in members)
        assert runtime.team_budget.snapshot()["decisions"] == 8
    finally:
        close_runtime(runtime)


def test_recorded_submission_does_not_stop_remaining_member_work(tmp_path):
    prepared, runtime, _, _ = build(tmp_path, {
        "member_001": [action("create_task", task_id="cpu-task", description="CPU-chosen task"),
                       action("claim_task", task_id="cpu-task"),
                       action("write_file", path="policy.py", text=material(CASE_IDS[0])["files"]["policy.py"] + "\n# CPU continuation witness\n"),
                       action("run_tests"),
                       action("fix_patch", task_ids=["cpu-task"], message="CPU fixed baseline witness"),
                       action("submit_integration", message="CPU fixed submission, not acceptance"),
                       action("work_note", key="after", text="Work continues after a submission event")],
        "member_002": [action("staff_wait", reason="Await work")],
    }, condition="O1")
    try:
        boundary = run_fragment(prepared, runtime)
        assert boundary["opportunities"] >= 8
        assert runtime.policies["member_001"].results[5]["ok"] is True
        assert len(prepared.world._software()["deliveries"]) == 1
        assert runtime.ports["member_001"].notes["after"] == "Work continues after a submission event"
    finally:
        close_runtime(runtime)


def test_session_birth_without_actual_world_spawn_is_rejected(tmp_path):
    prepared, runtime, _, _ = build(tmp_path, {})
    try:
        prepared.world._software()["registry"]["member_003"] = {
            "status": "live", "born_by": "member_001", "briefing": "No real birth event"}
        with pytest.raises(ValueError, match="exactly one original"):
            runtime.sync_members()
    finally:
        close_runtime(runtime)


class CPUOwner:
    """No tensors/weights; exercise only collection state and protected counters."""
    def __init__(self, script):
        self.script, self.phase, self.busy = script, "idle", False
        self.window_id = None
        self.recipe = {"temperature": 0.7, "max_output_tokens": 2048, "max_length": 16384,
                       "members": ["member_a", "member_b", "software_inactive"]}
        self.learning = {"actor_steps": 3, "critic_steps": 3, "backward_calls": 0}

    def freeze_identity(self):
        return {"policy_version": "synthetic-no-tensor-cpu-owner", "adapter_sha256": "no-weights"}

    def capture_evaluation_state(self):
        assert self.phase == "idle"
        return copy.deepcopy(self.learning)

    def begin_window(self, window_id):
        assert self.phase == "idle"
        self.window_id, self.phase = window_id, "collecting"

    def reseed(self, seed, *, label):
        self.seed = seed

    def finish_evaluation(self, entries, output):
        assert self.phase == "collecting"
        self.phase = "idle"

    def finish_evaluation_guard(self, before):
        return {"learning_unchanged": before == self.learning, "rng_restored_exactly": True,
                "fixture_only": True, "no_tensors_or_rng_constructed": True}


@pytest.mark.parametrize("assessment_unknown", [False, True])
def test_cpu_collection_closes_guard_and_marks_technical_assessment_unknown(tmp_path, monkeypatch, assessment_unknown):
    from proworksim import software_organization_v038 as world_module
    owner = CPUOwner({})
    prepared = build_software_collaboration_case(case_spec(CASE_IDS[0]), tmp_path / "case")
    if assessment_unknown:
        monkeypatch.setattr(world_module, "assess_software_collaboration", lambda *args, **kwargs: {
            "status": "unknown", "R": None, "submitted": False, "complete_delivery": None})
    result = collect_episode(owner, prepared, tmp_path / "collection", sampling_seed=38,
        slot_id="explicit-cpu-control", worker_factory=ScriptedWorker,
        transport_factory=lambda owner, directory: SimpleNamespace(script=owner.script))
    assert owner.phase == "idle"
    assert owner.learning == {"actor_steps": 3, "critic_steps": 3, "backward_calls": 0}
    assert result["status"] == ("technical_unknown" if assessment_unknown else "closed")
    assert result["R"] is None if assessment_unknown else result["R"] == 0
    assert result["training_eligible"] is False and result["admission_eligible"] is False
    assert result["usage"]["attempts"] == 2 and result["member_lifecycle"]["live_at_end"] == 0
    assert (tmp_path / "collection/episode/experience.json").exists()
    assert (tmp_path / "collection/evaluation-guard.json").exists()


class ScriptedSDKTransport:
    """Sealed synthetic token fixture for the real SDK; no tokenizer/model/GPU."""
    def __init__(self, owner):
        self.owner, self.script, self.requests, self.calls = owner, owner.script, [], {}
        self.pending = None

    def prepare_for_budget(self, request):
        sha = digest(json_bytes(request))
        self.pending = {"version": "resident-request-budget-v0.31r3", "window_id": self.owner.window_id,
            "actor_identity": self.owner.freeze_identity(), "prompt_tokens": 2,
            "reserved_output_tokens": request["max_tokens"], "context_limit": 16384, "fits": True,
            "original_request_sha256": sha, "selected_request_sha256": sha,
            "rendered_prompt_sha256": digest(b"synthetic-cpu-no-tokenizer"),
            "input_ids_sha256": digest(json_bytes([1, 2])), "recipe_sha256": digest(json_bytes(self.owner.recipe))}
        self.pending["preparation_sha256"] = digest(json_bytes(self.pending))
        return copy.deepcopy(self.pending)

    def discard_prepared_request(self, request):
        self.pending = None

    def complete(self, request, **kwargs):
        assert self.pending["original_request_sha256"] == digest(json_bytes(request))
        self.pending = None
        self.requests.append(copy.deepcopy(request))
        payload = next(json.loads(message["content"]) for message in reversed(request["messages"])
                       if message["role"] == "user" and '"observation"' in message["content"])
        member = payload["observation"]["actor_id"]
        index = self.calls.get(member, 0)
        self.calls[member] = index + 1
        actions = self.script.get(member, [])
        name, arguments = actions[index] if index < len(actions) else action("staff_done", reason="CPU control complete")
        identifier = "sdk-cpu-" + str(len(self.requests))
        body = {"id": identifier, "object": "chat.completion", "created": 0,
            "model": "explicit-cpu-not-generated", "actor_identity": self.owner.freeze_identity(),
            "online_window_id": self.owner.window_id,
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None, "tool_calls": [{"id": identifier + "-tool", "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)}}]}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            "token_trace": {"input_ids": [1, 2], "output_ids": [3], "fixture_only": True}}
        return {"http_status": 200, "body": body, "raw_body": json.dumps(body)}


def test_real_sdk_dynamic_birth_keeps_private_events_isolated(tmp_path):
    pytest.importorskip("openhands.sdk")
    owner = CPUOwner({"member_001": [action("work_note", key="secret", text="sdk-parent-secret"),
                                      action("spawn_member", briefing="Only this actual briefing is transferred")],
                      "member_002": [action("staff_wait", reason="Wait for a real event")]})
    owner.begin_window("cpu-real-sdk-organization")
    owner.transport = ScriptedSDKTransport(owner)
    prepared = build_software_collaboration_case(case_spec(CASE_IDS[0], condition="O3"), tmp_path / "case")
    runtime, _, _ = build_runtime(owner, prepared, tmp_path / "runtime")
    try:
        assert not owner.transport.requests
        boundary = run_fragment(prepared, runtime)
        assert boundary["execution_integrity_failure"] is None
        assert len(runtime.policies) == 3
        child = runtime.policies["member_003"]
        assert child.conversation is not runtime.policies["member_001"].conversation
        assert child.transport is runtime.policies["member_001"].transport
        child_requests = []
        for request in owner.transport.requests:
            payload = next(json.loads(message["content"]) for message in reversed(request["messages"])
                           if message["role"] == "user" and '"observation"' in message["content"])
            if payload["observation"]["actor_id"] == "member_003":
                child_requests.append(request)
        assert child_requests and "sdk-parent-secret" not in json.dumps(child_requests)
        assert "Only this actual briefing is transferred" in json.dumps(child_requests)
        evidence = organization_evidence(prepared, runtime)
        assert evidence["total_usage"]["attempts"] == len(owner.transport.requests)
        assert evidence["total_usage"]["completion_tokens"] == len(owner.transport.requests)
    finally:
        close_runtime(runtime)
