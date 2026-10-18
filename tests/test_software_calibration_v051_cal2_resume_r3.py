"""Three pure r3 host controls; no old trajectory/test/model is executed."""
import copy
from pathlib import Path

import pytest

from proworksim.storage import read_json
from scripts import software_calibration_v051_cal2 as base
from scripts import software_calibration_v051_cal2_resume as r2
from scripts import software_calibration_v051_cal2_resume_r3 as r3


def fixture():
    rows = base.inventory(read_json(Path(__file__).resolve().parents[1] /
        "docs/experiments/software-calibration-v051-repository-inventory.json"))
    preceding = [row for row in rows if row["slot_id"] not in r2.EXCLUDED]
    states = {row["slot_id"]: ({"status": "not_started", "attempts": []} if row["slot_id"] in r3.PENDING
        else {"status": "complete", "attempts": [{"ended_at": 2, "exit_code": 0}]}) for row in preceding}
    return rows, preceding, {"status": "paused", "ended_at": 3, "states": states}


def test_only_exact_unopened_seven_keep_original_order_seed_and_budget():
    rows, preceding, supervisor = fixture()
    before = copy.deepcopy((rows, preceding, supervisor))
    selected = r3.select_rows(rows, preceding, supervisor)
    assert [row["slot_id"] for row in selected] == list(r3.PENDING)
    assert selected == [row for row in rows if row["slot_id"] in r3.PENDING]
    assert sum(row["condition"] == "R" for row in selected) == 2
    assert sum(row["generation_tokens"] for row in selected) == 3500000
    assert sum(row["decisions"] for row in selected) == sum(row["attempts"] for row in selected) == 896
    assert sum(row["project_public_tests"] or 0 for row in selected) == 160
    assert (rows, preceding, supervisor) == before


def test_running_predecessor_or_any_reentered_slot_is_rejected_without_exception():
    rows, preceding, original = fixture()
    for edit in (lambda s: s.update(status="running"), lambda s: s.pop("ended_at"),
            lambda s: s.update(active_workers=[123]),
            lambda s: s["states"][r2.ZERO_R].update(status="not_started", attempts=[]),
            lambda s: s["states"][r3.PENDING[0]].update(attempts=[{"ended_at": 2, "exit_code": 75}]),
            lambda s: s["states"][r2.ZERO_R].update(status="running")):
        changed = copy.deepcopy(original)
        edit(changed)
        with pytest.raises(ValueError):
            r3.select_rows(rows, preceding, changed)
    changed_rows = copy.deepcopy(rows)
    changed_rows[0]["seed"] += 1
    with pytest.raises(ValueError, match="original ordered"):
        r3.select_rows(changed_rows, preceding, original)


def test_both_historical_source_snapshots_and_new_worker_module_are_exact(tmp_path):
    main, one, two = (tmp_path / name for name in ("main", "r1", "r2"))
    name = "src/runner.py"
    for path in (main, one, two):
        (path / "src").mkdir(parents=True)
    (main / name).write_text("r1 = True\n")
    (one / name).write_bytes((main / name).read_bytes())
    first = base.ref(main / name)
    (main / name).write_text("r2 = True\n")
    (two / name).write_bytes((main / name).read_bytes())
    second = base.ref(main / name)
    (main / name).write_text("r3 = True\n")
    plans = [{"source_root": str(path), "source_files": {name: ref["sha256"]}, "evidence": []}
             for path, ref in ((two, second), (one, first))]
    for item, path in ((first, one), (second, two)):
        binding = r3.historical_reference(item, plans, repository_root=main)
        assert binding["resolved_reference"] == base.ref(path / name)
    with pytest.raises(ValueError, match="neither original snapshot"):
        r3.historical_reference(base.ref(main / name), plans, repository_root=main)
    old_frozen = base.frozen
    worker, supervisor, proof = r3.algorithm_binding()
    assert worker.__code__ is base.worker.__code__
    assert worker.__globals__["frozen"] is supervisor.__globals__["frozen"] is r3.frozen
    assert r3.MODULE in supervisor.__code__.co_consts
    assert proof["AST_constant_replacements"] == 1 and proof["global_rebindings"] == ["VERSION", "frozen"]
    assert base.frozen is old_frozen
