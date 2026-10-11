"""Planned inventory, censoring and all-member cost controls; no model calls."""
import pytest

from scripts import software_organization_reporting_v047 as report


def plan():
    return [{"slot_id": f"{root}-{budget}-{condition}", "root_id": root,
             "condition": condition, "team_token_budget": budget, "sampling_seed": 471 + index}
            for budget, conditions in ((250000, report.CONDITIONS), (500000, report.BUDGET_CONDITIONS))
            for index, root in enumerate(report.ROOTS) for condition in conditions]


def result(unit, *, censored=False, tokens=100):
    return {**unit, "status": "closed", "R": 1, "R_joint": 1, "R_token": None if censored else 1,
            "Q_joint": 0.5, "Q_token": None if censored else 0.5,
            "submitted": True, "administrative_censoring": censored,
            "usage": {"total_tokens": tokens, "budget_charged_tokens": tokens, "uncertain_usage_attempts": 0}}


def test_all_44_slots_and_all_four_roots_remain_in_censored_and_unstarted_cells():
    units = plan()
    first = next(row for row in units if row["root_id"] == "LA" and row["condition"] == "S1" and row["team_token_budget"] == 250000)
    second = next(row for row in units if row["root_id"] == "HA" and row["condition"] == "S1" and row["team_token_budget"] == 250000)
    summary = report.aggregate_metrics(units, [result(first), result(second, censored=True, tokens=300)])
    cell = next(row for row in summary["cells"] if row["condition"] == "S1" and row["team_token_budget"] == 250000)
    assert len(summary["slots"]) == summary["planned_slots"] == 44
    assert cell["outcomes"]["R_token"]["identification_interval"] == [0.25, 1.0]
    assert cell["outcomes"]["R_joint"]["identification_interval"] == [0.5, 1.0]
    assert cell["outcomes"]["Q_token"]["identification_interval"] == [0.125, 0.875]
    assert cell["known_actual_tokens_all_planned_slots"] == 400
    assert cell["complete_actual_tokens_all_planned_slots"] is None
    assert cell["outcomes"]["R_token"]["mean"] is None
    assert cell["statuses"] == {"accepted_complete_delivery": 1, "administratively_censored": 1, "not_started": 2}


def test_joint_success_must_not_fill_administratively_censored_token_result():
    row = result(plan()[0], censored=True)
    row["R_token"] = 1
    with pytest.raises(ValueError, match="administrative_censoring"):
        report.outcome_values(row)


def test_unknown_attempt_reservation_is_not_actual_usage():
    row = {"status": "technical_unknown", "known_actual_total_tokens": 472582,
           "budget_charged_tokens": 489971, "uncertain_usage_attempts": 1}
    value = report.cost_values(row)
    assert value["known_actual_tokens"] == 472582
    assert value["complete_actual_tokens"] is None
    assert value["budget_charged_tokens"] == 489971


def test_first_and_last_submission_include_other_members_and_post_submit_cost():
    calls = [{"call_id": str(i), "member": "member_001" if i % 2 else "member_002",
              "experience_sequence": i * 10, "usage": {"prompt_tokens": i * 100, "completion_tokens": 5, "total_tokens": i * 100 + 5}}
             for i in range(1, 5)]
    submissions = [{"sequence": i, "call_id": call, "source_reference": {"object_id": "o", "version_id": "v" + call},
                    "fixed_patch_ids": ["p" + call], "actual_native_binding_verified": True}
                   for i, call in ((1, "2"), (2, "3"))]
    value = report.submission_costs(calls, submissions, final_submission=submissions[-1])
    assert value["first_fixed_submission"]["through_submission"]["total_tokens"] == 310
    assert value["final_fixed_submission"]["through_submission"]["total_tokens"] == 615
    assert value["after_first_submission_known_cost"]["total_tokens"] == 710
    assert value["complete_episode_cost"]["total_tokens"] == 1020
    absent = report.submission_costs(calls, [])
    assert absent["first_fixed_submission"] is None
    assert absent["no_submission_terminal_cost_retained"]["total_tokens"] == 1020


@pytest.mark.parametrize("change", ["subset", "duplicate", "seed"])
def test_plan_denominator_or_budget_pair_may_not_be_selected_after_results(change):
    units = plan()
    if change == "subset":
        units.pop()
    elif change == "duplicate":
        units[-1] = units[-2]
    else:
        units[-1]["sampling_seed"] += 1
    with pytest.raises(ValueError):
        report.aggregate_metrics(units, [])
