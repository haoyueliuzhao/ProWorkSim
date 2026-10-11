"""Bound dispatch/closure controls with fake clocks; zero model/GPU calls."""
import copy
from types import SimpleNamespace

import pytest

from proworksim.software_organization_runtime_v047 import DispatchDeadline
from scripts import measure_organization_budget_v047 as proof
from scripts import software_organization_stop_policy_v047 as policy
from tests.test_measure_organization_budget_v046 import capacity_binding, seal


def fixture(*, censored=False, R=0, submitted=False):
    cap = capacity_binding()
    clock = SimpleNamespace(value=100.0)
    events = []
    def emit(kind, payload):
        events.append({"sequence": len(events) + 1, "kind": kind, "payload": copy.deepcopy(payload), "worker_id": "member_001"})
    deadline = DispatchDeadline(clock=lambda: clock.value, sink=emit)
    deadline.require_dispatch("member_001", "call-1")
    emit("model_attempt", {"call_id": "call-1", "stage": "started", "dispatch_boundary": "v047_exact_native_transport_entry"})
    clock.value += 1
    deadline.returned("call-1", completed=True)
    usage = {"decisions": 1, "attempts": 1, "total_tokens": 200, "budget_charged_tokens": 200, "uncertain_usage_attempts": 0}
    model = seal({"limits": {"max_decisions": 128, "max_attempts": 128, "max_total_tokens": 250000},
        "binding": {"window_id": "organization-v047:fixture", "recipe_sha256": cap["capacity_recipe_sha256"],
                    "actor_identity": cap["capacity_actor_identity"]}, "members": ["member_001"],
        "records": {"call-1": {"call_id": "call-1", "member": "member_001", "stage_id": "free", "status": "settled",
            "attempt_started": True, "dispatch_started": True, "charge": {"charged_tokens": 200, "usage_status": "reported_actual_trace"}}},
        "decisions": 1, "attempts": 1, "charged_tokens": 200, "held_tokens": 0,
        "available_tokens": 249800, "remaining_decisions": 127, "remaining_attempts": 127}, "state_sha256")
    if censored:
        clock.value = 5500
        assert not deadline.admit_new_work("before_member_opportunity")
    delivery = {"source_reference": {"object_id": "fixed", "version_id": "v1"}} if submitted else None
    deadline.lock_submission(delivery)
    deadline.begin_assessment()
    deadline.mark_closed()
    receipt = deadline.snapshot(SimpleNamespace(snapshot=lambda: model))
    team = {"slot_id": "fixture", "model": model, "tests": {"limit": 32, "used": 0, "remaining": 32, "records": []}}
    row = {"version": "software-organization-runtime-v0.47", "slot_id": "fixture", "condition": "S1",
        "team_token_budget": 250000, "actor_identity": cap["capacity_actor_identity"], "status": "closed",
        "R": R, "R_joint": R, "R_token": None if censored else R, "Q_joint": float(R), "Q_token": None if censored else float(R),
        "submitted": submitted, "administrative_censoring": censored, "deadline_receipt": receipt,
        "assessment": {"status": "evaluable", "R": R, "submitted": submitted, "delivery": delivery},
        "boundary": {"team_budget": team, "role_stops": {}, "terminal_details": {}}, "team_budget": team,
        "usage": usage, "actor_updates": 0, "critic_updates": 0, "new_backward_calls": 0}
    feedback = {"version": "organization-feedback-opportunities-v0.47", "slot_id": "fixture", "status": "measured", "episode_closed": True,
                "mechanism_gate_inputs": {"resolved": True, "actual_generated_requests": 1, "requests_verified_under_v044": 1}, "feedback_records": []}
    evidence = {"version": "software-organization-runtime-v0.47", "team_budget": team, "total_usage": usage, "original_attempts": [{"call_id": "call-1"}]}
    guard = {"learning_unchanged": True, "rng_restored_exactly": True, "software_binding_unchanged": True,
             "actor_identity_unchanged": True, "learning_before_sha256": "a", "learning_after_sha256": "a",
             "rng_before_sha256": "b", "rng_after_restore_sha256": "b"}
    return dict(row=row, feedback=feedback, team_budget=team, evidence=evidence, guard=guard, events=events, capacity_binding=cap)


@pytest.mark.parametrize(("censored", "R", "submitted"), [(False, 0, False), (False, 0, True), (False, 1, True), (True, 0, False), (True, 1, True)])
def test_known_safe_joint_close_continues_without_using_R_for_stop_selection(censored, R, submitted):
    data = fixture(censored=censored, R=R, submitted=submitted)
    before = copy.deepcopy(data)
    outcome = policy.assess_records(**data)
    assert outcome["decision"] == "continue", outcome
    assert outcome["administrative_close"]["token_outcomes_censored"] is censored
    assert data == before


@pytest.mark.parametrize("mutation", ["late_dispatch", "false_uncensor", "unknown_charge", "old_window", "old_feedback", "wrong_phase", "guard"])
def test_new_safe_close_does_not_release_identity_phase_usage_or_dispatch_violations(mutation):
    data = fixture(censored=True, R=1, submitted=True)
    if mutation == "late_dispatch":
        data["row"]["deadline_receipt"]["dispatches"]["call-1"]["dispatched_at"] = 5500
    elif mutation == "false_uncensor":
        data["row"]["R_token"] = 1
    elif mutation == "unknown_charge":
        data["row"]["usage"]["uncertain_usage_attempts"] = 1
    elif mutation == "old_window":
        data["team_budget"]["model"]["binding"]["window_id"] = "organization-v045:fixture"
        seal(data["team_budget"]["model"], "state_sha256")
    elif mutation == "old_feedback":
        data["feedback"]["version"] = "organization-feedback-opportunities-v0.46"
    elif mutation == "wrong_phase":
        data["team_budget"]["model"]["records"]["call-1"]["stage_id"] = "select"
        seal(data["team_budget"]["model"], "state_sha256")
    else:
        data["guard"]["rng_restored_exactly"] = False
    assert policy.assess_records(**data)["decision"] == "global_pause"


def test_missing_close_evidence_remains_pending_not_known_zero():
    data = fixture()
    data["row"].pop("deadline_receipt")
    assert policy.assess_records(**data)["decision"] == "measurement_pending"


def test_phase_allowance_binding_uses_new_identity_and_frozen_quotas():
    data = fixture()
    assert proof.validate_stage_accounting(data["row"], data["team_budget"])["passed"] is True
