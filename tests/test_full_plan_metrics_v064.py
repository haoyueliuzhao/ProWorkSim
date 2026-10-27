import copy
import json
from pathlib import Path

import pytest

from proworksim import software_benchmark_full_plan_v064 as plan_module
from proworksim import software_benchmark_usage_metrics_v064 as metrics

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def inputs():
    identity = json.loads((ROOT / "artifacts/software-benchmark-v054/manifests/identities.json").read_bytes())
    public = json.loads((ROOT / "artifacts/software-benchmark-v054/source/public-tasks.json").read_bytes())
    return identity, public


@pytest.fixture(scope="module")
def plan(inputs):
    return plan_module.build_plan(*inputs)


def call(name="call-1", *, cost="0.012", detailed=True):
    usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
    if detailed:
        usage.update(completion_tokens_details={"reasoning_tokens": 5},
                     prompt_cache_hit_tokens=80, prompt_cache_miss_tokens=20)
    return metrics.normalize_usage_call(name, "agent", usage, accounted_cost_cny=cost)


def record(row, *, result=True, complete=True, state="closed", calls=None, unresolved=None):
    return {"slot_id": row["slot_id"], "entered": True, "generation_state": state,
            "code_result": result, "code_status": "scored" if result is not None else "technical_unknown",
            "delivery_result": None, "usage_capture_complete": complete,
            "calls": [call()] if calls is None else calls,
            "unresolved_calls": [] if unresolved is None else unresolved}


def test_complete_fixed_matrix_seed_and_denominators(plan, inputs):
    assert plan["planned_distinct_tasks"] == 500
    assert len(plan["rows"]) == 6000 and len(plan["groups"]) == 12
    assert plan["aggregate_input_output_token_upper_bound"] == 45_000_000_000
    assert plan["api_input_output_token_upper_bound"] == 22_500_000_000
    assert plan["api_total_budget_cny"] == "1500.00"
    expected = {row["instance_id"] for row in inputs[0]["tasks"]}
    assert set(plan["task_ids"]) == expected
    for group in plan["groups"]:
        selected = [row for row in plan["rows"] if row["group_id"] == group]
        assert len(selected) == 500 and {row["instance_id"] for row in selected} == expected
    for offset in range(0, 6000, 12):
        block = plan["rows"][offset:offset + 12]
        assert len({row["seed"] for row in block}) == 1
        assert len({row["slot_id"] for row in block}) == 12
    assert all(row["provider_seed_sent"] is (row["model_key"] == "QWEN") for row in plan["rows"])
    assert plan_module.build_plan(*inputs) == plan


def test_matrix_rejects_shrunk_or_leaking_public_projection(inputs):
    identity, public = inputs
    with pytest.raises(ValueError, match="500"):
        plan_module.build_plan(identity, public[:-1])
    contaminated = copy.deepcopy(public)
    contaminated[0]["patch"] = "hidden answer"
    with pytest.raises(ValueError, match="only the five public fields"):
        plan_module.build_plan(identity, contaminated)


def test_full_group_actual_mean_counts_reasoning_cache_only_once(plan):
    group_id = "DEEPSEEK_REF_B5000K"
    rows = [row for row in plan["rows"] if row["group_id"] == group_id]
    report = metrics.summarize(plan, [record(row) for row in rows], preparation_calls=[call("prep")])
    group = report["groups"][group_id]
    usage = group["all_planned"]
    assert usage["actual_average_tokens_full_planned_group"] == 120
    assert usage["actual_average_prompt_tokens_full_planned_group"] == 100
    assert usage["actual_average_completion_tokens_full_planned_group"] == 20
    assert usage["actual_prompt_tokens_final_usage_episodes"]["mean"] == 100
    assert usage["actual_completion_tokens_final_usage_episodes"]["mean"] == 20
    counts = usage["known_usage_all_entered_including_unknown_outcomes"]
    assert counts["input_plus_output_tokens"] == 60_000
    assert counts["reasoning_tokens_known"] == 2500
    assert counts["prompt_cache_hit_tokens_known"] == 40_000
    assert group["code_outcomes"]["full_group_completion_rate"] == 1
    assert group["delivery"] is None
    assert report["groups"]["QWEN_REF_B5000K"]["all_planned"]["actual_average_tokens_full_planned_group"] is None
    assert report["api_money"]["episode_cost_cny_known"] == "6.000"
    assert report["api_money"]["preparation_cost_cny_known"] == "0.012"


def test_partial_unknown_and_reservation_never_become_zero_actual_samples(plan):
    group_id = "DEEPSEEK_PROJECT_B7500K"
    row = next(row for row in plan["rows"] if row["group_id"] == group_id)
    value = record(row, result=None, complete=False, state="technical_unknown", calls=[call(detailed=False)],
                   unresolved=[{"call_id": "timeout-2", "reserved_tokens": 900,
                                "reserved_cost_cny": "0.50"}])
    report = metrics.summarize(plan, [value])
    group = report["groups"][group_id]
    usage = group["all_planned"]
    assert usage["entered_episodes"] == 1 and usage["unentered_episodes"] == 499
    assert usage["usage_final_episodes"] == 0
    assert usage["actual_tokens_final_usage_episodes"]["mean"] is None
    assert usage["actual_average_tokens_full_planned_group"] is None
    assert usage["known_tokens_divided_by_entered_lower_bound"] == 120
    assert usage["uncertain_reserved_tokens_not_actual"] == 900
    assert usage["known_usage_all_entered_including_unknown_outcomes"]["reasoning_tokens_if_all_reported"] is None
    assert group["code_outcomes"]["unresolved"] == 0
    assert group["code_outcomes"]["unknown_or_pending"] == 500
    assert report["api_money"]["total_accounted_cost_cny_known"] == "0.012"
    assert report["api_money"]["unresolved_reserved_cost_cny_not_actual"] == "0.50"
    assert report["api_money"]["remaining_cap_is_complete_accounting"] is False


def test_cost_of_known_usage_is_retained_when_outcome_unknown_and_delivery_separate(plan):
    row = next(row for row in plan["rows"] if row["group_id"] == "QWEN_PROJECT_B10000K")
    value = record(row, result=None, state="technical_unknown", calls=[call(cost=None)])
    value["delivery_result"] = False
    report = metrics.summarize(plan, [value])
    group = report["groups"][row["group_id"]]
    assert group["all_planned"]["actual_tokens_final_usage_episodes"]["mean"] == 120
    assert group["delivery"]["failed"] == 1
    assert group["code_outcomes"]["unresolved"] == 0
    assert group["monetary_cost_applicable"] is False


def test_duplicate_old_slots_and_inconsistent_usage_are_rejected(plan):
    row = plan["rows"][0]
    value = record(row)
    with pytest.raises(ValueError, match="Historical, foreign or duplicate"):
        metrics.summarize(plan, [value, value])
    with pytest.raises(ValueError, match="Historical, foreign or duplicate"):
        metrics.summarize(plan, [{**value, "slot_id": value["slot_id"].replace("v064:", "v062:")}])
    with pytest.raises(ValueError, match="counted once"):
        metrics.summarize(plan, [record(row, calls=[call(), call()])])
    with pytest.raises(ValueError, match="Reasoning is a subset"):
        metrics.validate_call({**call(), "reasoning_tokens": 21})
    with pytest.raises(ValueError, match="cache hit plus miss"):
        metrics.validate_call({**call(), "prompt_cache_miss_tokens": 21})
    with pytest.raises(ValueError, match="cannot be marked complete"):
        metrics.summarize(plan, [record(row, unresolved=[{"call_id": "u", "reserved_tokens": 20,
                                                        "reserved_cost_cny": None}])])


def test_budget_unstarted_kept_and_known_cost_breach_reported(plan):
    row = next(row for row in plan["rows"] if row["model_key"] == "DEEPSEEK")
    unstarted = {"slot_id": row["slot_id"], "entered": False, "generation_state": "not_started",
                 "not_started_reason": "api_monetary_budget_exhausted", "usage_capture_complete": False,
                 "calls": [], "unresolved_calls": [], "code_result": None, "delivery_result": None}
    report = metrics.summarize(plan, [unstarted], preparation_calls=[call("prep", cost="1500.01")])
    group = report["groups"][row["group_id"]]
    assert group["all_planned"]["planned_episodes"] == 500
    assert group["all_planned"]["unentered_reasons"]["api_monetary_budget_exhausted"] == 1
    assert group["all_planned"]["actual_average_tokens_full_planned_group"] is None
    assert report["api_money"]["known_plus_reserved_within_cap"] is False
