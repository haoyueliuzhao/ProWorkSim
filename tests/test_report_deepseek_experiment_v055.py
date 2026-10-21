"""One synthetic full-inventory control; no API, worker, scorer or world reads."""
import importlib.util
import json
from pathlib import Path
import sqlite3


def test_full_denominators_unknown_and_budget_censoring(tmp_path):
    source = Path(__file__).resolve().parents[1] / "tools/report_deepseek_experiment_v055.py"
    spec = importlib.util.spec_from_file_location("v055_readonly_report", source)
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)

    def write(name, value):
        path = tmp_path / name
        path.write_bytes(report.canonical(value))
        return report.reference(path)

    slots = [{"slot_id": f"v055-{condition}-repo__task-{index}", "condition_id": condition,
              "instance_id": f"repo__task-{index}"}
             for index in range(500) for condition in report.CONDITIONS]
    slots_ref = write("slots.json", {"slots": slots})
    prep_ids = [f"prep-{i}" for i in range(12)]
    admission = write("admission.json", {"neutral": {"request_ids": prep_ids}})
    ledger_path = tmp_path / "ledger.sqlite3"
    policy = {"model": "deepseek-flash", "cap_nanoyuan": 2000 * report.NANOYUAN}
    usage = {"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100,
             "prompt_cache_hit_tokens": 60, "prompt_cache_miss_tokens": 20,
             "completion_tokens_details": {"reasoning_tokens": 7}}
    with sqlite3.connect(ledger_path) as db:
        db.execute("CREATE TABLE metadata(name TEXT,value TEXT)")
        db.execute("INSERT INTO metadata VALUES ('policy',?)", (json.dumps(policy),))
        db.execute("""CREATE TABLE requests(request_id TEXT,slot_id TEXT,condition TEXT,status TEXT,
            reserved_nanoyuan INTEGER,settled_nanoyuan INTEGER,settled_peak_nanoyuan INTEGER,
            usage_json TEXT,tariff_basis_json TEXT)""")
        for index, name in enumerate(prep_ids):
            condition = report.CONDITIONS[index % 6]
            db.execute("INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?)",
                       (name, name, condition.replace("-", "_").upper(), "settled", 3000000000,
                        100000, 200000, json.dumps(usage), '{"basis":"off_peak_fixture"}'))
        slot = slots[0]
        db.execute("INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?)",
                   ("formal-unknown", slot["slot_id"], slot["condition_id"], "uncertain",
                    2100000000, None, None, None, None))
    plan_ref = write("plan.json", {"version": "v055-six-condition-queue-r1", "budget_cny": 2000,
                    "conditions": dict.fromkeys(report.CONDITIONS, {}), "slots": slots_ref,
                    "admission": admission, "queue_root": str(tmp_path), "ledger_path": str(ledger_path)})
    rows = [{"slot": slot, "generation": {"status": "pending"}, "scores": []} for slot in slots]
    for index in (0, 6):
        row = rows[index]
        row["generation"] = {"status": "closed"}
        request = write(f"code-{index}.json", {"slot_id": row["slot"]["slot_id"],
            "condition_id": row["slot"]["condition_id"], "model": "deepseek-flash",
            "preparation_only": False, "endpoint": "code"})
        row["scores"] = [{"request": request, "status": "official_report", "resolved": index == 0}]
    rows[12]["generation"] = {"status": "technical_unknown"}
    rows[18]["generation"] = {"status": "running"}
    project = rows[4]
    lock = write("candidate-lock.json", {"task_id": project["slot"]["instance_id"],
        "locked_before_grading": True, "submitted": False, "last_legal_delivery": None})
    result = write("result.json", {"status": "closed", "candidate": lock})
    project["generation"] = {"status": "closed", "result": result, "administratively_censored": True}
    write("state.json", {"plan": plan_ref, "rows": rows, "dispatch_stopped": True,
          "stop_reason": "shared_budget_or_accounting_gate", "status": "budget_closed_with_pending"})
    ledger_before = ledger_path.read_bytes()
    value = report.create_report(plan_ref)
    assert ledger_path.read_bytes() == ledger_before
    assert value["planned_formal_episodes"] == 3000
    for condition in value["conditions"].values():
        assert condition["planned_tasks"] == 500
        assert sum(condition["execution_state_counts"].values()) == 500
        assert sum(condition["official_code"][key] for key in ("resolved", "failed", "unknown")) == 500
        assert condition["official_code"]["full_panel_point_estimate"] is None
    native = value["conditions"]["REF-nonthinking"]
    assert native["official_code"]["resolved"] == 1
    assert native["official_code"]["failed"] == 1
    assert native["official_code"]["unknown"] == 498
    assert native["execution_state_counts"]["global_budget_censored"] == 496
    assert native["technical_unknown_tasks"] == 1
    assert native["project_delivery"] == {"applicable": False, "not_applicable": 500}
    project = value["conditions"]["PROJECT-nonthinking"]
    assert project["project_delivery"]["no_legal_submission"] == 1
    assert project["official_code"]["failed"] == 0
    assert project["official_code"]["unknown"] == 500
    assert value["preparation"]["actual"]["requests"] == 12
    assert value["preparation"]["actual"]["known_total_tokens"] == 1200
    assert value["global_api_cost_including_preparation"]["uncertain_reserved_cny"] == 2.1
    assert value["global_api_cost_including_preparation"]["complete_actual_tokens"] is None
    assert value["unattributed_ledger_entries"]["requests"] == 0
    assert value["warnings"] == []
    assert "3000" in report.markdown(value)
