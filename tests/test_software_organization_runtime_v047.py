"""Finite v047 host/real-SDK CPU controls; no weights, model, or GPU evidence."""
import json
from types import SimpleNamespace

import pytest

from proworksim.software_context_v044 import SoftwareContextTransport
from proworksim.software_organization_runtime_v047 import (
    AdministrativeSoftDeadline, DispatchDeadline, HardDeadlineReached, NativeDispatchGate,
    collect_episode, outcome_metrics,
)
from proworksim.software_organization_v047 import (
    CASE_IDS, MEMBERS, build_software_collaboration_case, case_spec, material,
)
from proworksim.stage_budget_v047 import StageTeamBudget, stage_plan
from test_software_organization_runtime_v038 import CPUOwner, action
from test_software_organization_runtime_v040 import SelectedCPUTransport, tokenize


class Clock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


class TimedTransport(SelectedCPUTransport):
    def __init__(self, owner, clock, *, after_call=None, failure=None):
        super().__init__(owner)
        self.clock, self.after_call, self.failure = clock, after_call or {}, failure

    def complete(self, request, **kwargs):
        if self.failure is not None:
            raise self.failure
        result = super().complete(request, **kwargs)
        if len(self.requests) in self.after_call:
            self.clock.value = self.after_call[len(self.requests)]
        return result


def cpu_collection(tmp_path, condition, script, *, clock=None, after_call=None,
                   transport_factory=None, failure=None, owner_factory=CPUOwner):
    pytest.importorskip("openhands.sdk")
    clock = clock or Clock()
    owner = owner_factory(script)
    owner.recipe["max_length"] = 18432
    owner.prepare_request = lambda request: (json.dumps(request, ensure_ascii=False, sort_keys=True), None, None)
    owner.tokenizer = tokenize
    owner.transport = TimedTransport(owner, clock, after_call=after_call, failure=failure)
    prepared = build_software_collaboration_case(case_spec(CASE_IDS[0], condition=condition,
        team_token_budget=250000), tmp_path / "case")
    folder = tmp_path / "collection"
    kwargs = dict(sampling_seed=47, slot_id="explicit-v047-cpu-" + condition, clock=clock,
        soft_seconds=5, hard_seconds=10,
        transport_factory=transport_factory or (lambda o, d: SoftwareContextTransport(o, d, evidence_kind="cpu_programmed_fixture")))
    return owner, prepared, folder, kwargs


def events(folder):
    return [json.loads(line) for line in (folder / "experience.jsonl").read_text().splitlines()]


def make_gate(clock):
    plan = stage_plan("S1", 250000)
    state = {"stage_index": 0, "stage_id": "free", "finished_members": [], "closed": False}
    budget = StageTeamBudget(stage_provider=lambda: state, stage_plan=plan,
        members=[MEMBERS[0]], team_id="organization-v047:cpu-gate", max_total_tokens=250000,
        require_exact_resident=False)
    budget.consume_decision(MEMBERS[0], "call")
    budget.reserve(MEMBERS[0], "call", {"token_reservation": 10})
    budget.begin_attempt(MEMBERS[0], "call")
    calls, confirmed, cancelled = [], [], []
    direct = SimpleNamespace(complete=lambda request, **kwargs: calls.append(request) or {"body": {}})
    deadline = DispatchDeadline(clock=clock, soft_seconds=5, hard_seconds=10)
    gate = NativeDispatchGate(direct, deadline)
    gate.context = SimpleNamespace(_turn={"member_id": MEMBERS[0], "association": {"call_id": "call"}})
    worker = SimpleNamespace(confirm_native_dispatch=confirmed.append, cancel_pending_dispatch=cancelled.append)
    gate.runtime = SimpleNamespace(team_budget=budget, policies={MEMBERS[0]: worker})
    return gate, budget, calls, confirmed, cancelled


@pytest.mark.parametrize("at,error", [(5, AdministrativeSoftDeadline), (10, HardDeadlineReached)])
def test_final_gate_cancels_only_undispatched_holds_without_unknown_charge(at, error):
    clock = Clock()
    gate, budget, calls, confirmed, cancelled = make_gate(clock)
    clock.value = at
    with pytest.raises(error):
        gate.complete({"fixture": True}, timeout_seconds=600)
    value = budget.snapshot()
    assert calls == confirmed == [] and cancelled == ["call"]
    assert value["decisions"] == 1 and value["attempts"] == value["charged_tokens"] == value["held_tokens"] == 0
    assert value["records"]["call"]["status"] == "cancelled_before_dispatch"
    assert gate.deadline.dispatches == {}


def test_soft_time_passage_without_work_prevention_is_not_censoring():
    clock = Clock()
    deadline = DispatchDeadline(clock=clock, soft_seconds=5, hard_seconds=10)
    clock.value = 6
    deadline.check_hard("natural_close")
    assert deadline.snapshot()["actual_soft_cutoff_triggered"] is False
    assert deadline.snapshot()["cutoff_prevented_remaining_work"] is False


@pytest.mark.parametrize("censored", [False, True])
def test_joint_private_quality_and_token_estimand_are_distinct(censored):
    assessment = {"status": "evaluable", "R": 1, "submitted": True,
        "independent_acceptance": {"checks": [{"passed": True}, {"passed": False}, {"passed": True}]},
        "public_acceptance": {"tests": [{"passed": True}] * 20}}
    result = outcome_metrics(assessment, administratively_censored=censored)
    assert result["R_joint"] == 1 and result["Q_joint"] == 2 / 3
    assert result["R_token"] == (None if censored else 1)
    assert result["Q_token"] == (None if censored else 2 / 3)


def test_no_delivery_unknown_and_process_invalid_quality_never_invent_workspace_score():
    absent = outcome_metrics({"status": "evaluable", "R": 0, "submitted": False}, administratively_censored=False)
    unknown = outcome_metrics({"status": "unknown", "R": None, "submitted": False}, administratively_censored=False)
    invalid = outcome_metrics({"status": "evaluable", "R": 0, "submitted": True, "process_violation": True,
        "independent_acceptance": {"checks": [{"passed": True}]}}, administratively_censored=False)
    assert absent["Q_joint"] == absent["Q_token"] == 0 and absent["raw_content_score"] is None
    assert unknown["R_joint"] is unknown["Q_joint"] is unknown["Q_token"] is None
    assert invalid["Q_joint"] == 0 and invalid["raw_content_score"] == 1


def test_native_s1_closes_original_guard_and_preserves_personal500k(tmp_path):
    owner, prepared, folder, kwargs = cpu_collection(tmp_path, "S1", {MEMBERS[0]: [
        action("work_note", key="note", text="CPU synthetic output"), action("staff_done", reason="Done")]})
    result = collect_episode(owner, prepared, folder, **kwargs)
    assert result["version"] == "software-organization-runtime-v0.47"
    assert owner.window_id.startswith("organization-v047:") and owner.phase == "idle"
    assert result["team_token_budget"] == 250000
    assert result["R_joint"] == result["R_token"] == 0 and result["Q_joint"] == result["Q_token"] == 0
    receipt = result["deadline_receipt"]
    assert receipt["closed_before_hard_deadline"] and receipt["all_dispatched_attempts_settled"]
    assert receipt["final_submission_locked"] and receipt["unique_final_acceptance"]
    saved = events(folder)
    assert not [e for e in saved if e["kind"] == "organization_work_opportunity_v045"]
    assert len([e for e in saved if e["kind"] == "organization_work_opportunity_v047"]) == 4
    started = [e for e in saved if e["kind"] == "model_attempt" and e["payload"]["stage"] == "started"]
    dispatch = [e for e in saved if e["kind"] == "organization_model_dispatch_v047" and e["payload"]["stage"] == "started"]
    assert len(started) == len(dispatch) == result["usage"]["attempts"] == 2
    assert all(e["payload"]["actual_generation_started"] is True for e in started)
    model_calls = [e for e in saved if e["kind"] == "model_call" and e["payload"]["stage"] == "started"]
    assert all(e["payload"]["config"]["budget"]["max_total_tokens"] == 500000 for e in model_calls)
    assert result["usage"]["total_tokens"] == sum(b["usage"]["total_tokens"] for b in owner.transport.responses)
    guard = json.loads((folder / "evaluation-guard.json").read_text())
    assert all(guard[k] for k in ("learning_unchanged", "rng_restored_exactly", "software_binding_unchanged", "actor_identity_unchanged"))


@pytest.mark.parametrize("location", ["prepare", "complete"])
def test_native_prepare_crossing_soft_cutoff_has_no_actual_attempt_or_charge(tmp_path, location):
    clock = Clock()

    class CrossCutoffContext(SoftwareContextTransport):
        def prepare_for_budget(self, request):
            value = super().prepare_for_budget(request)
            if location == "prepare":
                clock.value = 5
            return value

        def complete(self, request, **kwargs):
            if location == "complete":
                clock.value = 5
            return super().complete(request, **kwargs)

    owner, prepared, folder, kwargs = cpu_collection(tmp_path, "S1", {}, clock=clock,
        transport_factory=lambda o, d: CrossCutoffContext(o, d, evidence_kind="cpu_programmed_fixture"))
    result = collect_episode(owner, prepared, folder, **kwargs)
    assert owner.transport.requests == []
    assert result["status"] == "closed" and result["R_joint"] == 0 and result["R_token"] is None
    assert result["usage"]["decisions"] == 1
    assert result["usage"]["attempts"] == result["usage"]["total_tokens"] == result["usage"]["budget_charged_tokens"] == 0
    assert result["usage"]["uncertain_usage_attempts"] == 0
    row = next(iter(result["team_budget"]["model"]["records"].values()))
    assert row["status"] == "cancelled_before_dispatch" and row["attempt_started"] is False
    saved = events(folder)
    assert not [e for e in saved if e["kind"] == "model_attempt" and e["payload"]["stage"] == "started"]
    assert result["deadline_receipt"]["cancelled_before_dispatch"][0]["decision_retained"]


def test_soft_cutoff_settles_one_returned_legal_action_without_model_wrapup(tmp_path):
    owner, prepared, folder, kwargs = cpu_collection(tmp_path, "S1", {MEMBERS[0]: [
        action("work_note", key="in_flight", text="Legal returned CPU action"), action("staff_done", reason="Must not run")]}, after_call={1: 6})
    result = collect_episode(owner, prepared, folder, **kwargs)
    assert len(owner.transport.requests) == 1 and result["usage"]["attempts"] == 1
    assert result["R_joint"] == 0 and result["R_token"] is result["Q_token"] is None
    saved = events(folder)
    notes = [e for e in saved if e["kind"] == "harness_tool_call" and e["payload"]["action"] == "work_note"]
    assert len(notes) == 1 and notes[0]["payload"]["response"]["ok"]
    assert result["deadline_receipt"]["no_new_dispatch_after_cutoff"]


@pytest.mark.parametrize("condition,call_count", [("I2", 2), ("P2", 1), ("P4", 1)])
def test_soft_cutoff_does_not_open_selector_or_pipeline_successor(tmp_path, condition, call_count):
    script = {member: [action("finish_stage", reason="Synthetic stage finished")] for member in MEMBERS[:4]}
    owner, prepared, folder, kwargs = cpu_collection(tmp_path, condition, script, after_call={call_count: 6})
    result = collect_episode(owner, prepared, folder, **kwargs)
    assert len(owner.transport.requests) == call_count
    assert result["architecture"]["stage_index"] == 0
    assert result["deadline_receipt"]["stage_transitions"] == []
    assert result["administrative_censoring"] is True and result["R_token"] is None


def test_independent_selector_reuses_existing001_session_without_retirement_reset(tmp_path):
    owner, prepared, folder, kwargs = cpu_collection(tmp_path, "I2", {
        MEMBERS[0]: [action("finish_stage", reason="Candidate end"), action("staff_done", reason="Selector end")],
        MEMBERS[1]: [action("finish_stage", reason="Other candidate end")]})
    result = collect_episode(owner, prepared, folder, **kwargs)
    assert len(owner.transport.requests) == 3
    assert result["architecture"]["stage_id"] == "select"
    assert result["usage_by_member"][MEMBERS[0]]["attempts"] == 2
    assert result["member_lifecycle"]["cumulative_births"] == 2
    assert result["R_joint"] == result["R_token"] == 0
    stages = [r["stage_id"] for r in result["team_budget"]["model"]["records"].values()]
    assert stages == ["generate", "generate", "select"]
    saved = events(folder)
    births = [e for e in saved if e["kind"] == "organization_session_born"]
    assert len(births) == 2


def test_retired001_cannot_return_as_independent_selector(tmp_path):
    owner, prepared, folder, kwargs = cpu_collection(tmp_path, "I2", {
        MEMBERS[0]: [action("staff_done", reason="Permanent retirement")],
        MEMBERS[1]: [action("finish_stage", reason="Other candidate end")]})
    result = collect_episode(owner, prepared, folder, **kwargs)
    assert len(owner.transport.requests) == 2 and result["usage_by_member"][MEMBERS[0]]["attempts"] == 1
    assert result["member_lifecycle"]["registry"][MEMBERS[0]]["status"] == "retired"
    assert result["R_token"] == 0


def test_pipeline_predecessor_retirement_does_not_remove_later_member(tmp_path):
    owner, prepared, folder, kwargs = cpu_collection(tmp_path, "P2", {
        MEMBERS[0]: [action("staff_done", reason="Permanent end of implementation")],
        MEMBERS[1]: [action("staff_done", reason="No submission")]})
    result = collect_episode(owner, prepared, folder, **kwargs)
    assert len(owner.transport.requests) == 2 and result["architecture"]["stage_id"] == "review_revise_submit"
    assert result["member_lifecycle"]["cumulative_births"] == 2


def test_dispatched_transport_failure_keeps_uncertain_charge_and_unknown_result(tmp_path):
    owner, prepared, folder, kwargs = cpu_collection(tmp_path, "S1", {}, failure=RuntimeError("Synthetic unavailable response"))
    result = collect_episode(owner, prepared, folder, **kwargs)
    assert result["status"] == "technical_unknown" and result["R_joint"] is result["R_token"] is None
    assert result["usage"]["attempts"] == result["usage"]["uncertain_usage_attempts"] == 1
    assert result["usage"]["budget_charged_tokens"] > 0 and result["usage"]["total_tokens"] == 0
    assert result["boundary"]["execution_integrity_failure"]
    assert result["deadline_receipt"]["all_dispatched_attempts_settled"]


def test_hard_deadline_after_response_does_not_execute_late_tool_or_write_formal_R(tmp_path):
    owner, prepared, folder, kwargs = cpu_collection(tmp_path, "S1", {MEMBERS[0]: [
        action("work_note", key="too_late", text="Must not execute")]}, after_call={1: 10})
    with pytest.raises(HardDeadlineReached):
        collect_episode(owner, prepared, folder, **kwargs)
    assert len(owner.transport.responses) == 1
    assert not (folder / "slot-result.json").exists() and not (folder / "evaluation-guard.json").exists()
    saved = events(folder)
    assert not [e for e in saved if e["kind"] == "harness_tool_call" and e["payload"]["action"] == "work_note"]
    assert json.loads((folder / "interruption.json").read_text())["type"] == "HardDeadlineReached"


def test_last_fixed_candidate_is_only_candidate_assessed_after_exact_test_and_submission(tmp_path):
    files = material(CASE_IDS[0])["files"]
    path = next(name for name in files if name.endswith(".py") and name not in {"test_member.py", "test_visible.py"})
    script = {MEMBERS[0]: [action("write_file", path=path, text=files[path] + "\n# Explicit CPU fixture edit\n"),
        action("run_tests"), action("fix_patch", task_ids=[], message="Fixed synthetic candidate"),
        action("submit_integration", message="One actual fixed submission"), action("staff_done", reason="End")]}
    owner, prepared, folder, kwargs = cpu_collection(tmp_path, "S1", script)
    result = collect_episode(owner, prepared, folder, **kwargs)
    assert result["submitted"] is True and result["deadline_receipt"]["final_assessment_calls"] == 1
    assert result["assessment"]["delivery"] == result["deadline_receipt"]["locked_submission"]
    assert result["team_budget"]["tests"]["used"] == 1
    assert result["private_checks_total"] > 0 and result["Q_joint"] == result["private_checks_passed"] / result["private_checks_total"]
    assert result["Q_token"] == result["Q_joint"]


def test_real_stage_reservation_refusal_preserves_selector_and_never_becomes_service_fault(tmp_path, monkeypatch):
    original = StageTeamBudget.stage_snapshot

    def no_generator_tokens_for_001(self, member=None):
        value = original(self, member)
        if value["stage_id"] == "generate" and member == MEMBERS[0]:
            # Finite host-boundary fixture: published phase allowance is zero;
            # no model output or charged historical call is invented.
            value["available_tokens"] = 0
        return value

    monkeypatch.setattr(StageTeamBudget, "stage_snapshot", no_generator_tokens_for_001)
    owner, prepared, folder, kwargs = cpu_collection(tmp_path, "I2", {
        MEMBERS[0]: [action("staff_done", reason="Actual selector call after phase refusal")],
        MEMBERS[1]: [action("finish_stage", reason="Other candidate finished")]})
    result = collect_episode(owner, prepared, folder, **kwargs)
    records = list(result["team_budget"]["model"]["records"].values())
    assert records[0]["status"] == "admission_rejected" and records[0]["budget_kind"] == "stage_budget"
    assert records[0]["attempt_started"] is False and "charge" not in records[0]
    assert result["boundary"]["execution_integrity_failure"] is None
    assert result["usage"]["decisions"] == 3 and result["usage"]["attempts"] == len(owner.transport.requests) == 2
    assert result["usage_by_member"][MEMBERS[0]]["attempts"] == 1
    assert records[-1]["member"] == MEMBERS[0] and records[-1]["stage_id"] == "select"
    assert result["status"] == "closed" and result["R_token"] == 0


def test_inflight_natural_permanent_done_after_soft_is_not_administratively_censored(tmp_path):
    owner, prepared, folder, kwargs = cpu_collection(tmp_path, "S1", {
        MEMBERS[0]: [action("staff_done", reason="Natural last action")]}, after_call={1: 6})
    result = collect_episode(owner, prepared, folder, **kwargs)
    assert len(owner.transport.requests) == 1
    assert result["administrative_censoring"] is False and result["R_token"] == result["R_joint"] == 0
    assert result["deadline_receipt"]["actual_soft_cutoff_triggered"] is False
    assert result["deadline_receipt"]["closed_before_hard_deadline"] is True
