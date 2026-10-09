"""Only new v039 timing, controller/source separation and diagnostic controls."""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim.model_policy import CONTROL_TOOLS
from proworksim.software_organization_v039 import (
    CASE_IDS, MEMBERS, PROJECT, build_software_collaboration_case, case_spec, diagnostic_case_spec,
)
from proworksim.software_organization_runtime_v039 import (
    WAIT_DESCRIPTION, SharedTeamBudget, build_runtime, close_runtime, collect_episode,
    diagnostic_outcome, organization_evidence, run_fragment,
)
from proworksim.team_budget_v033 import V033PolicyBoundaryError
from test_software_organization_runtime_v038 import CPUOwner, ScriptedSDKTransport, ScriptedWorker, action


def setup(tmp_path, script, *, condition="X3", worker_factory=ScriptedWorker, case=None):
    owner = CPUOwner(script)
    owner.begin_window("v039-cpu-control")
    owner.transport = SimpleNamespace(script=script)
    prepared = build_software_collaboration_case(case or case_spec(CASE_IDS[0], condition=condition), tmp_path / "case")
    runtime, captured, interfaces = build_runtime(owner, prepared, tmp_path / "runtime", worker_factory=worker_factory)
    return owner, prepared, runtime, captured, interfaces


def notes(n=4):
    return [action("work_note", key="cpu", text="Private control note " + str(i)) for i in range(n)]


def test_x3_intervenes_once_after_eighth_action_before_next_call_without_budget_or_output_grant(tmp_path):
    script = {MEMBERS[0]: notes(), MEMBERS[1]: notes(3) + [action("create_task", task_id="before-birth", description="Eighth real action") ]}
    owner, prepared, runtime, _, _ = setup(tmp_path, script)
    try:
        boundary = run_fragment(prepared, runtime)
        control = boundary["external_intervention"]
        assert control["status"] == "implemented" and control["attempts"] == 1
        assert control["observed_team_decisions"] == control["observed_model_attempts"] == 8
        assert control["shared_budget_before"] == control["shared_budget_after"]
        events = prepared.world.state["software_events"]
        created = next(e for e in events if e["kind"] == "task_created")
        birth = next(e for e in events if e["kind"] == "member_spawned")
        assert birth["sequence"] > created["sequence"] and birth["actor_id"] == "operator"
        assert boundary["outcomes"][8]["worker_id"] == "member_003"
        assert runtime.policies["member_003"].transport is owner.transport
        pop = next(row for row in runtime.population_trace if row["cause"] == "external_neutral_member_created")
        assert pop["cumulative_births"] == 3 and pop["output_participants"] == list(MEMBERS[:2])
        evidence = organization_evidence(prepared, runtime)
        assert evidence["member_lifecycle"]["external_births"] == 1
        assert evidence["member_lifecycle"]["member_requested_births"] == 0
        assert evidence["total_usage"]["completion_tokens"] == evidence["total_usage"]["attempts"]
        assert evidence["controller_cost"]["model_calls"] == evidence["controller_cost"]["generated_tokens"] == 0
        assert boundary["version"].endswith("0.39") and boundary["base_runtime_provenance"]["version"].endswith("0.38")
        assert not [e for e in runtime.recorder.events if e.get("worker_id") == "operator"]
    finally:
        close_runtime(runtime)


class PreGenerationBoundaryWorker(ScriptedWorker):
    def step(self, observation, *, opportunity, model_identity):
        if self.role_id == MEMBERS[1] and self.meter["decisions"] == 0:
            self.meter["decisions"] += 1
            self.team_budget.consume_decision(self.role_id, "cpu-capacity-decision-no-generation")
            raise V033PolicyBoundaryError("model_budget_exhausted", "CPU declared context boundary",
                memory=self.snapshot(), details={"budget_kind": "context_capacity"})
        return super().step(observation, opportunity=opportunity, model_identity=model_identity)


def test_x3_counts_team_decisions_including_no_generation_not_model_calls(tmp_path):
    _, prepared, runtime, _, _ = setup(tmp_path, {MEMBERS[0]: notes(8)}, worker_factory=PreGenerationBoundaryWorker)
    try:
        boundary = run_fragment(prepared, runtime)
        control = boundary["external_intervention"]
        assert control["status"] == "implemented" and control["observed_team_decisions"] == 8
        assert control["observed_model_attempts"] == 7
        assert runtime.birth_records["member_003"]["shared_budget_at_session_birth"]["decisions"] == 8
    finally:
        close_runtime(runtime)


@pytest.mark.parametrize("stop", ["staff_done", "staff_wait"])
@pytest.mark.parametrize("at_trigger", [False, True])
def test_external_event_does_not_reanimate_a_naturally_closed_team(tmp_path, stop, at_trigger):
    script = {member: (notes(3) if at_trigger else []) + [action(stop, reason="CPU natural closure")]
              for member in MEMBERS[:2]}
    _, prepared, runtime, _, _ = setup(tmp_path, script)
    try:
        boundary = run_fragment(prepared, runtime)
        control = boundary["external_intervention"]
        assert control["status"] == "skipped" and control["reason"] == "natural_terminal"
        assert control["trigger_reached"] is at_trigger
        assert runtime.team_budget.snapshot()["decisions"] == (8 if at_trigger else 2)
        assert len(runtime.labels) == 2 and prepared.world._software()["external_birth_executed"] is False
        assert sum(e["kind"] == "external_intervention_disposition" for e in runtime.recorder.events) == 1
    finally:
        close_runtime(runtime)


def test_external_event_skips_full_live_capacity_once_without_evicting_or_delaying(tmp_path):
    script = {MEMBERS[0]: [action("spawn_member", briefing="Neutral CPU member") for _ in range(2)] + notes(5),
              MEMBERS[1]: notes(6), "member_003": notes(6), "member_004": notes(6)}
    _, prepared, runtime, _, _ = setup(tmp_path, script)
    try:
        boundary = run_fragment(prepared, runtime)
        assert boundary["external_intervention"]["status"] == "skipped"
        assert boundary["external_intervention"]["reason"] == "live_capacity"
        assert boundary["external_intervention"]["observed_team_decisions"] == 8
        assert len(runtime.labels) == 4 and boundary["controller_cost"]["world_actions"] == 0
        assert all(e.get("origin") != "external_controller" for e in prepared.world.state["software_events"])
    finally:
        close_runtime(runtime)


def test_external_event_skips_exhausted_shared_resources_without_reset(tmp_path):
    _, prepared, runtime, _, _ = setup(tmp_path, {MEMBERS[0]: notes(5), MEMBERS[1]: notes(5)})
    budget = SharedTeamBudget(members=runtime.labels, team_id="v039-cpu-control", max_decisions=8)
    runtime.team_budget = budget
    prepared.world.model_budget_snapshot = budget.snapshot
    for worker in runtime.policies.values():
        worker.team_budget = budget
    try:
        boundary = run_fragment(prepared, runtime)
        assert boundary["external_intervention"]["reason"] == "no_shared_resources"
        assert budget.snapshot()["decisions"] == 8 and budget.snapshot()["remaining_decisions"] == 0
        assert len(runtime.labels) == 2
    finally:
        close_runtime(runtime)


def test_external_event_skips_cumulative_birth_cap_even_with_free_live_capacity(tmp_path):
    script = {member: notes(6) for member in (MEMBERS[0], MEMBERS[1], "member_006")}
    _, prepared, runtime, _, _ = setup(tmp_path, script)
    world = prepared.world
    try:
        # Explicit CPU fixture transitions, not a model experiment or hidden
        # preparation in collect_episode. Register every real fixture birth.
        for retiring in (None, None, "member_003", "member_004"):
            if retiring:
                assert world.session(retiring, PROJECT).call("retire_member", reason="CPU fixture frees one live position")["ok"]
                runtime.sync_members()
            assert world.session(MEMBERS[0], PROJECT).call("spawn_member", briefing="CPU cap fixture only")["ok"]
            runtime.sync_members()
        assert world.session("member_005", PROJECT).call("retire_member", reason="CPU fixture leaves live capacity")["ok"]
        runtime.sync_members()
        assert len(world._software()["registry"]) == 6 and len(world.live_members()) == 3
        boundary = run_fragment(prepared, runtime)
        assert boundary["external_intervention"]["reason"] == "cumulative_birth_limit"
        assert boundary["external_intervention"]["observed_team_decisions"] == 8
        assert boundary["controller_cost"]["world_actions"] == 0
        assert len(runtime.labels) == 6
    finally:
        close_runtime(runtime)


class ObservationEnvelopeWorker(ScriptedWorker):
    def __init__(self, *args, **kwargs):
        sink = kwargs["event_sink"]
        def emit(kind, payload):
            if kind == "model_attempt":
                payload = copy.deepcopy(payload)
                message = payload["request"]["messages"][0]
                message["content"] = json.dumps({"observation": json.loads(message["content"])})
            sink(kind, payload)
        kwargs["event_sink"] = emit
        super().__init__(*args, **kwargs)


def test_probe1_reports_actual_birth_reply_and_parent_input_separately(tmp_path):
    script = {MEMBERS[0]: [action("spawn_member", briefing="Send a root_goal reply to member_001"),
                           action("staff_wait", reason="CPU reply observed")],
              MEMBERS[1]: [action("staff_wait", reason="CPU control waits")],
              "member_003": [action("send_message", recipient=MEMBERS[0], task_id="root_goal", body="Real CPU fixture reply") ]}
    _, prepared, runtime, _, _ = setup(tmp_path, script, case=diagnostic_case_spec("birth-message"),
                                      worker_factory=ObservationEnvelopeWorker)
    try:
        run_fragment(prepared, runtime)
        result = diagnostic_outcome(prepared, runtime)
        assert result["all_goals_met"] is True
        assert result["goals"]["member_requested_birth_executed"] is True
        assert result["goals"]["child_reply_executed"] and result["goals"]["reply_reached_parent_actual_input"]
        assert result["business_R"] is None and result["autonomous_behavior_evidence"] is False
    finally:
        close_runtime(runtime)


def test_probe2_retired_setup_identity_never_samples_and_exact_snapshot_birth_has_diagnostic_goals(tmp_path):
    case = diagnostic_case_spec("replacement-patch")
    prepared = build_software_collaboration_case(case, tmp_path / "case")
    path = prepared.world._software()["diagnostic_setup"]["path"]
    owner = CPUOwner({MEMBERS[0]: [action("spawn_member", briefing="Read exact initialized file and reply",
        patch_id="patch-1", replaces=MEMBERS[1])], "member_003": [action("read_file", path=path, start_line=1, max_lines=60)]})
    owner.begin_window("v039-probe-cpu")
    owner.transport = SimpleNamespace(script=owner.script)
    runtime, _, _ = build_runtime(owner, prepared, tmp_path / "runtime", worker_factory=ScriptedWorker)
    try:
        run_fragment(prepared, runtime)
        result = diagnostic_outcome(prepared, runtime)
        assert result["all_goals_met"] is True and result["business_R"] is None
        assert result["autonomous_behavior_evidence"] is False
        assert runtime.policies[MEMBERS[1]].meter["decisions"] == 0
        assert runtime.team_budget.snapshot()["limits"]["max_total_tokens"] == 150000
        child_obs = json.dumps(runtime.policies["member_003"].observations)
        assert prepared.world._software()["diagnostic_setup"]["private_marker"] not in child_obs
    finally:
        close_runtime(runtime)


def test_unfinished_diagnostic_is_closed_false_without_business_acceptance_or_retry(tmp_path, monkeypatch):
    from proworksim import software_organization_tasks_v039 as source
    monkeypatch.setattr(source, "assess_files", lambda *a, **k: pytest.fail("No business acceptance in interface probe"))
    prepared = build_software_collaboration_case(diagnostic_case_spec("birth-message"), tmp_path / "case")
    owner = CPUOwner({})
    result = collect_episode(owner, prepared, tmp_path / "collection", sampling_seed=39, slot_id="cpu-probe-once",
        worker_factory=ScriptedWorker, transport_factory=lambda owner, path: SimpleNamespace(script=owner.script))
    assert result["status"] == "closed" and result["R"] is None
    assert result["purpose"] == "interface_diagnostic" and result["outcome_type"] == "interface_control"
    assert result["diagnostic"]["all_goals_met"] is False and result["diagnostic"]["automatic_retry"] is False
    assert owner.phase == "idle" and owner.learning["backward_calls"] == 0
    assert (tmp_path / "collection/evaluation-guard.json").exists()


def test_real_sdk_v039_wait_text_changes_only_new_instances_and_controller_has_no_output(tmp_path):
    pytest.importorskip("openhands.sdk")
    original_controls = copy.deepcopy(CONTROL_TOOLS)
    owner = CPUOwner({MEMBERS[0]: notes(), MEMBERS[1]: notes()})
    owner.begin_window("v039-real-sdk-cpu")
    owner.transport = ScriptedSDKTransport(owner)
    prepared = build_software_collaboration_case(case_spec(condition="X3"), tmp_path / "case")
    runtime, _, _ = build_runtime(owner, prepared, tmp_path / "runtime")
    try:
        assert CONTROL_TOOLS == original_controls
        assert next(row for row in runtime.policies[MEMBERS[0]].definitions if row["name"] == "staff_wait")["description"] == WAIT_DESCRIPTION
        boundary = run_fragment(prepared, runtime)
        assert runtime.policies[MEMBERS[0]].agent.tools_map["staff_wait"].description == WAIT_DESCRIPTION
        assert boundary["execution_integrity_failure"] is None
        assert boundary["external_intervention"]["status"] == "implemented"
        for request in owner.transport.requests:
            wait = next(item["function"] for item in request["tools"] if item["function"]["name"] == "staff_wait")
            assert wait["description"] == WAIT_DESCRIPTION and "actual world wait tool" not in wait["description"]
        assert CONTROL_TOOLS == original_controls
        evidence = organization_evidence(prepared, runtime)
        assert evidence["total_usage"]["attempts"] == len(owner.transport.requests)
        assert evidence["total_usage"]["completion_tokens"] == len(owner.transport.requests)
    finally:
        close_runtime(runtime)
