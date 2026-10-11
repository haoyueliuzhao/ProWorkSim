"""Finite stage accounting controls; no tokenizer/model/GPU is constructed."""

import copy

import pytest

from proworksim.stage_budget_v047 import (
    StageBudgetBoundaryError,
    StageTeamBudget,
    StageTestBudget,
    stage_plan,
)
from proworksim.team_budget_v033 import V033PolicyBoundaryError
from proworksim.tool_outcomes import ToolRejection


M1, M2, M3, M4 = [f"member_{i:03d}" for i in range(1, 5)]


def budget(condition="I2", total=250000):
    plan = stage_plan(condition, total)
    state = {
        "stage_index": 0,
        "stage_id": plan[0]["stage_id"],
        "finished_members": [],
        "closed": False,
    }
    value = StageTeamBudget(
        stage_provider=lambda: state,
        stage_plan=plan,
        members=[f"member_{i:03d}" for i in range(1, int(condition[1]) + 1)],
        team_id="v047-cpu",
        max_total_tokens=total,
        require_exact_resident=False,
    )
    return value, state, plan


def advance(state, plan, index):
    state.update(stage_index=index, stage_id=plan[index]["stage_id"], finished_members=[])


def actual(value, member, call_id, reserved, used):
    value.consume_decision(member, call_id)
    value.reserve(member, call_id, {"token_reservation": reserved})
    value.begin_attempt(member, call_id)
    value.mark_dispatched(member, call_id)
    return value.settle(
        member,
        call_id,
        {
            "id": "response-" + call_id,
            "usage": {"prompt_tokens": used, "completion_tokens": 0, "total_tokens": used},
        },
    )


@pytest.mark.parametrize("condition", ["S1", "D2", "D4", "I2", "I4", "P2", "P4"])
@pytest.mark.parametrize("total", [250000, 500000])
def test_frozen_stage_allocations_sum_to_exact_one_team_budget(condition, total):
    plan = stage_plan(condition, total)
    assert {key: sum(row["limits"][key] for row in plan) for key in plan[0]["limits"]} == {
        "max_total_tokens": total,
        "max_decisions": 128,
        "max_attempts": 128,
        "max_test_runs": 32,
    }
    assert plan[-1]["submit_allowed"]
    assert not any(row["submit_allowed"] for row in plan[:-1])


def test_independent_equal_subpools_do_not_borrow_but_selector_gets_all_unused():
    value, state, plan = budget()
    actual(value, M1, "first", 80000, 60000)
    assert value.stage_snapshot(M1)["available_tokens"] == 27500
    assert value.stage_snapshot(M2)["available_tokens"] == 87500
    value.consume_decision(M1, "over")
    with pytest.raises(StageBudgetBoundaryError) as caught:
        value.reserve(M1, "over", {"token_reservation": 27501})
    assert caught.value.status == "stage_budget_exhausted"
    row = value.snapshot()["records"]["over"]
    assert row["status"] == "admission_rejected" and row["budget_kind"] == "stage_budget"
    assert row["attempt_started"] is False and value.snapshot()["held_tokens"] == 0
    actual(value, M2, "second", 10000, 9000)
    advance(state, plan, 1)
    assert value.stage_snapshot(M1)["available_tokens"] == 250000 - 69000
    assert value.stage_snapshot(M1)["remaining_decisions"] == 125
    actual(value, M1, "selection", 170000, 160000)
    assert value.snapshot()["charged_tokens"] == 229000
    assert value.snapshot()["records"]["selection"]["stage_id"] == "select"


def test_i4_decisions_are_per_generator_and_final_reserve_is_not_consumed():
    value, state, plan = budget("I4")
    for index in range(22):
        value.consume_decision(M1, f"dec-{index}")
    with pytest.raises(StageBudgetBoundaryError):
        value.consume_decision(M1, "too-many")
    assert value.snapshot()["decisions"] == 22
    assert value.stage_snapshot(M2)["remaining_decisions"] == 22
    advance(state, plan, 1)
    assert value.stage_snapshot(M1)["remaining_decisions"] == 106


def test_pipeline_all_dimensions_only_release_forward():
    value, state, plan = budget("P4")
    test = StageTestBudget(stage_provider=lambda: state, stage_plan=plan)
    actual(value, M1, "p1", 80000, 70000)
    for _ in range(3):
        test.consume(M1)
    with pytest.raises(StageBudgetBoundaryError):
        value.consume_decision(M2, "premature")
    for index, member in enumerate((M2, M3, M4), start=1):
        advance(state, plan, index)
        assert (
            value.stage_snapshot(member)["available_tokens"]
            == sum(r["limits"]["max_total_tokens"] for r in plan[: index + 1]) - 70000
        )
        assert test.stage_snapshot(member)["remaining"] == 8 * (index + 1) - 3
    with pytest.raises(StageBudgetBoundaryError):
        value.consume_decision(M1, "backward")
    assert value.snapshot()["charged_tokens"] == 70000
    assert test.snapshot()["used"] == 3


def test_native_tests_have_equal_i_subpools_and_no_hidden_reset(tmp_path):
    _, state, plan = budget("I4")
    test = StageTestBudget(
        tmp_path / "test-budget.json", stage_provider=lambda: state, stage_plan=plan
    )
    for _ in range(6):
        test.consume(M2)
    with pytest.raises(ToolRejection):
        test.consume(M2)
    assert test.stage_snapshot(M1)["remaining"] == 6
    advance(state, plan, 1)
    assert test.stage_snapshot(M1)["remaining"] == 26
    assert test.snapshot()["used"] == 6
    assert all(row["stage_id"] == "generate" for row in test.snapshot()["records"])


def test_pending_attempt_blocks_transition_and_unknown_charge_carries_forward():
    value, state, plan = budget("P2")
    value.consume_decision(M1, "pending")
    value.reserve(M1, "pending", {"token_reservation": 1000})
    value.begin_attempt(M1, "pending")
    value.mark_dispatched(M1, "pending")
    with pytest.raises(ValueError):
        value.assert_transition_ready()
    value.cleanup(M1, "pending")
    value.assert_transition_ready()
    advance(state, plan, 1)
    assert value.stage_snapshot(M2)["available_tokens"] == 249000
    assert (
        value.snapshot()["records"]["pending"]["charge"]["usage_status"]
        == "uncertain_attempt_charged_reservation"
    )


def test_proven_predispatch_cancel_is_not_attempt_and_cannot_cancel_sent_call():
    value, _, _ = budget("S1")
    value.consume_decision(M1, "cancel")
    value.reserve(M1, "cancel", {"token_reservation": 1000})
    value.begin_attempt(M1, "cancel")
    value.cancel_before_dispatch(M1, "cancel")
    value.cleanup(M1, "cancel")
    snap = value.snapshot()
    assert (snap["decisions"], snap["attempts"], snap["charged_tokens"], snap["held_tokens"]) == (
        1,
        0,
        0,
        0,
    )
    actual(value, M1, "sent", 1000, 900)
    before = copy.deepcopy(value.snapshot()["records"]["sent"])
    with pytest.raises(V033PolicyBoundaryError):
        value.cancel_before_dispatch(M1, "sent")
    assert value.snapshot()["records"]["sent"] == before


def test_cross_stage_reservation_is_integrity_failure():
    value, state, plan = budget()
    value.consume_decision(M1, "original-phase")
    advance(state, plan, 1)
    with pytest.raises(V033PolicyBoundaryError) as caught:
        value.reserve(M1, "original-phase", {"token_reservation": 10})
    assert caught.value.status == "execution_integrity_error"


def test_finished_unavailable_and_retired_member_cannot_take_stage_allowance():
    value, state, _ = budget("I2")
    for field in ("finished_members", "unavailable_members"):
        state[field] = [M1]
        with pytest.raises(StageBudgetBoundaryError):
            value.consume_decision(M1, "not-live-" + field)
        state[field] = []
    state["live_members"] = [M2]
    with pytest.raises(StageBudgetBoundaryError):
        value.consume_decision(M1, "retired")
    assert value.snapshot()["decisions"] == 0


def test_exact_context_rejection_keeps_priority_over_local_stage_allowance():
    from proworksim.storage import digest, json_bytes

    value, _, _ = budget("I4")
    value._state["require_exact_resident"] = True
    prompt, output = 17000, 2048
    preparation = {
        "version": "resident-request-budget-v0.31r3",
        "prompt_tokens": prompt,
        "reserved_output_tokens": output,
        "context_limit": 18432,
        "fits": False,
        "window_id": "v047-cpu",
        "actor_identity": {"frozen": "cpu-control"},
    }
    for key in (
        "original_request_sha256",
        "selected_request_sha256",
        "rendered_prompt_sha256",
        "input_ids_sha256",
        "recipe_sha256",
    ):
        preparation[key] = "a" * 64
    preparation["preparation_sha256"] = digest(json_bytes(preparation))
    value.consume_decision(M1, "overflow")
    with pytest.raises(V033PolicyBoundaryError) as caught:
        value.reserve(
            M1,
            "overflow",
            {
                "token_reservation": prompt + output,
                "reservation_kind": "exact_resident_prompt",
                "preparation": preparation,
            },
        )
    assert caught.value.status == "model_budget_exhausted"
    row = value.snapshot()["records"]["overflow"]
    assert row["budget_kind"] == "context_capacity" and not row["attempt_started"]
    assert value.snapshot()["charged_tokens"] == value.snapshot()["held_tokens"] == 0
