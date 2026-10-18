"""Two compact final-report contracts; no original report or experiment is run."""
import copy

import pytest

from scripts import software_calibration_v051_cal2_final_report as report


def panel():
    old, inventory, new = [], [], []
    old_unknown = {"v051-cal2-boltons-1-R", "v051-cal2-boltons-1-P", "v051-cal2-boltons-1-U",
                   "v051-cal2-boltons-2-P", "v051-cal2-boltons-2-U", "v051-cal2-boltons-2-R"}
    for i, task in enumerate(report.base.TASKS):
        for c in (("R", "P", "U"), ("P", "U", "R"), ("U", "R", "P"))[i % 3]:
            name = f"v051-{task}-{c}"
            frozen = {"slot_id": name, "task_id": task, "condition": c, "seed": 202610170551 + i,
                "generation_tokens": 500000, "decisions": 128, "attempts": 128,
                "project_public_tests": None if c == "R" else 32}
            pending = name in report.PENDING
            unknown = name in old_unknown
            row = {**frozen, "status": "not_started" if pending else "technical_unknown" if unknown else "closed",
                "source_bound": not pending and not unknown, "slot_entered": not pending,
                "R_code": None if pending or unknown else 0, "raw_R_code": None if pending or unknown else 0,
                "Q_terminal": None if pending or unknown else .5, "raw_Q_terminal": None if pending or unknown else .5,
                "R_joint_applicable": c != "R", "R_joint": None if c == "R" or pending or unknown else 0,
                "raw_R_joint": None if c == "R" or pending else 0, "R_token": None,
                "administrative_censoring": False, "binding_issues": [], "terminal_tests": {},
                "report_source": {"path": "/old/" + name, "sha256": "old", "bytes": 1}}
            old.append(row)
            if pending:
                inventory.append(frozen)
                new.append({**copy.deepcopy(row), "status": "closed", "source_bound": True, "slot_entered": True,
                    "R_code": 1, "raw_R_code": 1, "Q_terminal": 1., "raw_Q_terminal": 1.,
                    "R_joint": 1 if c != "R" else None, "raw_R_joint": 1 if c != "R" else None,
                    "report_source": {"path": "/new/" + name, "sha256": "new", "bytes": 2}})
    return old, inventory, new


def test_compaction_keeps_metrics_and_exact_origin_without_raw_bodies():
    old, _, _ = panel()
    row = old[0]
    large = "x" * 200000
    row.update(measurement={"raw": large}, raw_stop_reason={"status": "stopped", "deep": large},
               accounting={"rows": [{"body": large}], "known_actual_tokens": 11})
    row["terminal_tests"] = {"execution": {"output": large}, "frozen_test_count": 412, "not_run_count": 3}
    source = {"path": "/immutable/stage.json", "sha256": "s", "bytes": 45031062}
    value = report.compact_row(row, origin={"report": source, "json_pointer": "/rows/0"})
    assert len(report.base.common.json_bytes(value)) < 6000
    assert value["origin_row"]["report"] == source
    assert value["R_code"] is None
    assert value["terminal_tests"]["frozen_test_count"] == 412
    assert value["generation_accounting_summary"]["known_actual_tokens"] == 11
    assert "execution" not in value["terminal_tests"]
    previous = {"version": report.PREDECESSOR_VERSION, "host_status": "paused", "root": "/r2",
                "plan": {"sha256": "plan"}, "supervisor": {"sha256": "supervisor"}, "environment_audit": {"sha256": "audit"}}
    plan = {"predecessor_root": "/r2", "predecessor_references": {"predecessor_stage_report": source,
        "predecessor_plan": previous["plan"], "predecessor_supervisor": previous["supervisor"],
        "environment_audit": previous["environment_audit"]}}
    report.verify_predecessor(previous, plan, source)
    with pytest.raises(ValueError, match="exactly bound"):
        report.verify_predecessor(previous, plan, {**source, "sha256": "changed"})


def test_seven_only_merge_preserves_unknowns_and_counts_stage_fee_once():
    old, inventory, new = panel()
    before = copy.deepcopy(old)
    new[-1].update(status="not_started", source_bound=False, slot_entered=False,
        R_code=None, raw_R_code=None, Q_terminal=None, raw_Q_terminal=None, R_joint=None, raw_R_joint=None)
    rows = report.merge_rows(old, inventory, new, predecessor_reference={"path": "/stage", "sha256": "s", "bytes": 1})
    assert old == before and len(rows) == 18
    assert sum(r["status"] == "technical_unknown" for r in rows) == 6
    assert rows[-1]["status"] == "not_started" and rows[-1]["R_code"] is None
    metrics = report.base.endpoint_metrics(rows, "R_code")
    assert metrics["P_minus_R"]["mean"] is None and metrics["U_minus_P"]["mean"] is None
    def cost(tokens, calls):
        return {"known_actual_tokens": tokens, "uncertain_reservation_tokens": 0,
            "unknown_reservation_amount_count": 0, "started_generations": calls, "complete_generations": calls,
            "source_bound_complete_generations": calls, "prepared_without_generation": 0,
            "complete_actual_tokens": tokens}
    value = report.combine_billing(cost(2904643, 275), cost(60, 6), new_fee={"complete_actual_tokens": 60}, rows=rows)
    assert value["complete_actual_tokens"] == 2904703 and value["complete_generations"] == 281
    assert value["unstarted_slots"] == 1
    with pytest.raises(ValueError, match="exact seven"):
        report.merge_rows(old, [inventory[1], *inventory[1:]], new, predecessor_reference={})
