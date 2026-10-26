from collections import Counter

import pytest

from proworksim.software_benchmark_ref_plan_v062 import (
    ARMS, build_panel, resource_plan, retain,
)


def panel_inputs():
    public = [{"instance_id": f"repo{index % 12}__task-{index}", "repo": f"org/repo{index % 12}",
               "base_commit": "a" * 40, "problem_statement": "public issue",
               "patch": "DO NOT EXPORT", "test_patch": "DO NOT EXPORT"} for index in range(50)]
    original = {"task_ids": [row["instance_id"] for row in public],
                "repository_counts": dict(Counter(row["repo"] for row in public))}
    slots = [{"instance_id": row["instance_id"], "repo": row["repo"]} for row in public]
    return original, slots, public


def test_fixed_panel_and_public_projection():
    panel = build_panel(*panel_inputs())
    assert panel["planned_episodes"] == 174
    assert panel["aggregate_input_output_token_upper_bound"] == 1_240_000_000
    assert Counter(row["condition_id"] for row in panel["slots"]) == {"BASE5M": 50, "FIX5M": 50, "FIX10M": 74}
    assert panel["repeat_task_ids"] == panel["task_ids"][:12]
    for task in panel["task_ids"]:
        primary = [row for row in panel["slots"] if row["instance_id"] == task and row["repeat_index"] == 0]
        assert set(row["condition_id"] for row in primary) == set(ARMS)
        assert len({row["seed"] for row in primary}) == 1
    assert all(set(row) == {"instance_id", "repo", "base_commit", "problem_statement"} for row in panel["public_tasks"])
    assert len({row["slot_id"] for row in panel["slots"]}) == 174


def test_full_resource_ceiling_and_no_implicit_qualification():
    panel = build_panel(*panel_inputs())
    rows = [{"instance_id": task, "historical_evidence_available": index < 11}
            for index, task in enumerate(panel["task_ids"])]
    plan = resource_plan(panel, {"maximum_new_control_containers": 100,
                                "mandatory_new_control_containers": 78, "rows": rows})
    assert plan["maximum_containers"] == 626
    assert plan["minimum_containers_if_all_eleven_qualifications_reusable"] == 604
    assert plan["maximum_named_volumes"] == 176
    assert plan["maximum_active_containers"] == 6
    assert plan["maximum_cpu"] == 48 and plan["maximum_memory_gib"] == 280
    assert len(plan["resources"]) == 802
    assert len({row["resource_key"] for row in plan["resources"]}) == 802
    assert Counter(row["role"] for row in plan["resources"]) == {
        "actor": 176, "controller": 176, "volume": 176, "score": 174, "control": 100}


def test_panel_cannot_shrink_and_preparation_cannot_overwrite(tmp_path):
    original, slots, public = panel_inputs()
    original["task_ids"].pop()
    with pytest.raises(ValueError, match="fifty"):
        build_panel(original, slots, public)
    path = tmp_path / "panel.json"
    first = retain(path, {"seed": 1})
    assert retain(path, {"seed": 1}) == first
    with pytest.raises(ValueError, match="immutable"):
        retain(path, {"seed": 2})
