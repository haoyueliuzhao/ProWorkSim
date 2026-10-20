import copy

import pytest

from proworksim.software_panel_v053 import (
    build_inventory, canonical_bytes, freeze_panel, near_duplicate, sha256, source_record,
)


def raw(repo=0, item=0, family="func_basic"):
    slug = f"owner__repo{repo}.1234abcd"
    return {
        "instance_id": f"{slug}.{family}__id{item}",
        "repo": "swesmith/" + slug, "image_name": "official/" + slug,
        "problem_statement": "Restore the documented behavior.",
        "FAIL_TO_PASS": [f"tests/test_mod.py::test_{item}"],
        "PASS_TO_PASS": ["tests/test_mod.py::test_unchanged"],
        "patch": (f"diff --git a/mod{item}.py b/mod{item}.py\n"
                  f"--- a/mod{item}.py\n+++ b/mod{item}.py\n"
                  "@@ -1 +1 @@ def compute():\n-return 1\n+return 0\n"),
    }


def fixture():
    rows = [raw(repo, item, "func_basic" if item % 2 else "func_pm_op_swap")
            for repo in range(21) for item in range(12)]
    inventory, _ = build_inventory(
        rows, source_manifest={"revision": "fixed"},
        official_profile_slugs={f"owner__repo{repo}.1234abcd" for repo in range(21)},
    )
    admission = {
        "inventory_sha256": sha256(canonical_bytes(inventory)), "model_runs_started": 0,
        "repositories": [{"repository": repo["repository"], "admitted": True,
                          "qualified_task_ids": repo["candidate_task_ids"]}
                         for repo in inventory["repositories"]],
    }
    return rows, inventory, admission


def test_order_independent_panel_and_fixed_repetition_denominators():
    rows, inventory, admission = fixture()
    reversed_inventory, _ = build_inventory(
        list(reversed(rows)), source_manifest={"revision": "fixed"},
        official_profile_slugs={f"owner__repo{repo}.1234abcd" for repo in range(21)},
    )
    assert reversed_inventory == inventory
    panel = freeze_panel(inventory, admission)
    assert len(panel["tasks"]) == len(set(panel["main_task_ids"])) == 200
    assert len(set(panel["repeat_task_ids"])) == 40
    assert len(panel["slots"]) == len({row["seed"] for row in panel["slots"]}) == 280
    assert [row["repeat_index"] for row in panel["slots"]].count(1) == 200
    assert {row["task_id"] for row in panel["slots"][200:]} == set(panel["repeat_task_ids"])
    assert panel["generation_token_cap"] == 140_000_000


def test_rejection_is_preserved_and_missing_earlier_admission_cannot_be_skipped():
    _, inventory, admission = fixture()
    rejected = admission["repositories"][0]
    rejected.update(admitted=False, reason="official_image_unavailable")
    panel = freeze_panel(inventory, admission)
    assert panel["pre_model_environment_rejections"] == [rejected]
    assert rejected["repository"] not in {row["repository"] for row in panel["tasks"]}
    del admission["repositories"][0]
    with pytest.raises(ValueError, match="lacks admission"):
        freeze_panel(inventory, admission)


def test_frozen_inventory_and_zero_model_start_are_required():
    _, inventory, admission = fixture()
    admission["model_runs_started"] = 1
    with pytest.raises(ValueError, match="before every model"):
        freeze_panel(inventory, admission)
    admission["model_runs_started"] = 0
    admission["inventory_sha256"] = "incorrect"
    with pytest.raises(ValueError, match="Bind admissions"):
        freeze_panel(inventory, admission)


def test_common_fault_and_unresolved_source_cannot_be_skipped_for_twenty_others():
    _, inventory, admission = fixture()
    admission["paused_common_system_fault"] = True
    with pytest.raises(ValueError, match="common system fault"):
        freeze_panel(inventory, admission)
    admission["paused_common_system_fault"] = False
    admission["repositories"][0].update(admitted=None, reason="registry_timeout")
    with pytest.raises(ValueError, match="admission is unresolved"):
        freeze_panel(inventory, admission)


def test_near_duplicate_variants_and_distinct_tests():
    left = source_record(raw())
    variant = copy.deepcopy(raw())
    variant["patch"] = variant["patch"].replace("+return 0", "+return None")
    right = source_record(variant)
    assert near_duplicate(left, right)
    variant["FAIL_TO_PASS"] = ["tests/test_mod.py::test_other"]
    assert not near_duplicate(left, source_record(variant))
    variant["patch"] = raw()["patch"].replace("-return 1", "-return    1")
    assert near_duplicate(left, source_record(variant))


def test_incomplete_repository_and_test_overlap_rejected_before_model():
    row = raw()
    row["PASS_TO_PASS"] = list(row["FAIL_TO_PASS"])
    with pytest.raises(ValueError, match="disjoint"):
        source_record(row)
    rows, _, _ = fixture()
    inventory, _ = build_inventory(rows[:9], source_manifest={}, official_profile_slugs=set())
    assert inventory["eligible_repository_count"] == 0


def test_official_pr_mined_ids_are_included_as_a_distinct_proxy_family():
    row = raw()
    row["instance_id"] = "owner__repo0.1234abcd.pr_5947"
    assert source_record(row)["mutation_family"] == "pr_mined"
