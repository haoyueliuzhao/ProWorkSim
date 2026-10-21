"""One bounded CPU control for dynamic dispatch, drain and invariant transition."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest


def module(name, relative):
    base = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(name, base / relative)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_dynamic_pool_dispatch_drain_and_budget_preservation(tmp_path):
    queue = module("proworksim.dynamic_queue_control", "src/proworksim/software_benchmark_queue_v054.py")
    drain = module("dynamic_drain_control", "tools/drain_formal_queue_v054.py")
    migration = module("dynamic_migration_control", "tools/resume_formal_preclaim_v054.py")
    rows = [{"slot": {"slot_index": index, "slot_id": str(index), "arm": arm},
             "generation": {"status": "pending"}, "scores": {}}
            for index, arm in enumerate(("MATCH", "PROJECT", "REF", "MATCH"), 1)]
    pool = {key: {"declaration": {"gpu_index": gpu, "mode": mode}}
            for key, gpu, mode in (("mp0", 0, "MATCH_PROJECT"), ("mp6", 6, "MATCH_PROJECT"), ("ref7", 7, "REF"))}
    assignments = []
    for _ in range(3):
        row, resident, observed = queue.select_pool_slot(rows, pool)
        gpu = observed["declaration"]["gpu_index"]
        assignments.append((row["slot"]["slot_index"], resident, gpu))
        row["generation"].update(status="intent", resident_id=resident, physical_gpu=gpu)
    assert assignments == [(1, "mp0", 0), (2, "mp6", 6), (3, "ref7", 7)]
    assert queue.select_pool_slot(rows, pool) is None
    pool["mp2"] = {"declaration": {"gpu_index": 2, "mode": "MATCH_PROJECT"}}
    assert queue.select_pool_slot(rows, pool)[1] == "mp2"
    assert queue.select_pool_slot(rows, pool, maximum_active=3) is None
    assert not drain.boundary({"rows": rows}, 4, "hrtimer_nanosleep")
    for row in rows[:3]:
        row["generation"]["status"] = "running"
    assert drain.boundary({"rows": rows}, 4, "hrtimer_nanosleep")
    assert not drain.boundary({"rows": rows}, 28, "hrtimer_nanosleep")
    assert not drain.boundary({"rows": rows}, 4, "do_wait")

    original = Path("/data0/zhuxinrui/projects/ProWorkSim")
    staged = Path(__file__).resolve().parents[1]
    old = {"authorization": migration.reference(original / "config/v054-formal-authorization-r1.json"),
           "plan": migration.reference(original / "config/v054-formal-execution-plan-r2.json")}
    new = {"authorization": migration.reference(staged / "config/v054-formal-authorization-r2-dynamic-pool.json"),
           "plan": migration.reference(staged / "config/v054-formal-execution-plan-r3-dynamic-pool.json"),
           "resident_pool_policy": {"path": "explicit-fixed-policy", "sha256": "synthetic-policy"}}
    assert migration.verify_resource_revision(old, new)["fixed_slots_and_budget_unchanged"]
    unauthorized = json.loads(Path(new["authorization"]["path"]).read_text())
    unauthorized["aggregate_input_output_token_upper_bound"] += 1
    bad = tmp_path / "changed-budget.json"
    bad.write_text(json.dumps(unauthorized))
    with pytest.raises(ValueError, match="authorization"):
        migration.verify_resource_revision(old, {**new, "authorization": migration.reference(bad)})

    all_rows = [{"slot": {"slot_id": str(i), "arm": arm}, "generation": {"status": "closed"},
                 "scores": {"code": {"status": "official_report", "resolved": False}}}
                for i, arm in enumerate(["REF"] * 500 + ["MATCH"] * 500 + ["PROJECT"] * 500)]
    assert queue.ref_completion_evidence({"rows": all_rows})["eligible"]
    all_rows[0]["scores"]["code"]["status"] = "technical_unknown"
    assert not queue.ref_completion_evidence({"rows": all_rows})["eligible"]
    state = {"bindings": {"sha256": "previous"}, "rows": [
        {"slot": {"slot_id": "finished"}, "generation": {"status": "closed", "old_config": "preserved"},
         "scores": {"code": {"status": "official_report", "resolved": False}}},
        {"slot": {"slot_id": "unused"}, "generation": {"status": "pending", "attempts": []}, "scores": {}}],
        "faults": [{"original": "retained"}]}
    before = copy.deepcopy(state)
    resumed = migration.resumed_state(state, {"sha256": "new-pool"}, set(), {"sha256": "transition"})
    assert state == before and resumed["rows"][0]["generation"] == before["rows"][0]["generation"]
    assert resumed["rows"][0]["original_execution_bindings"] == before["bindings"]
    assert resumed["rows"][1]["next_execution_bindings"] == {"sha256": "new-pool"}
    assert resumed["faults"] == before["faults"]


def test_same_cold_instance_waits_until_prior_worker_claimed():
    queue = module("proworksim.dynamic_queue_cold_control", "src/proworksim/software_benchmark_queue_v054.py")
    first = {"slot": {"slot_id": "first", "arm": "MATCH", "instance_id": "cold-A"},
             "generation": {"status": "running", "resident_id": "mp0", "physical_gpu": 0, "claimed": False}}
    second = {"slot": {"slot_id": "same-task", "arm": "PROJECT", "instance_id": "cold-A"},
              "generation": {"status": "pending"}}
    third = {"slot": {"slot_id": "next-task", "arm": "MATCH", "instance_id": "cold-B"},
             "generation": {"status": "pending"}}
    free = {"mp2": {"declaration": {"gpu_index": 2, "mode": "MATCH_PROJECT"}}}
    assert queue.select_pool_slot([first, second, third], free)[0] is third
    first["generation"]["claimed"] = True
    assert queue.select_pool_slot([first, second, third], free)[0] is second


def test_unqualified_preparation_never_claims_and_failure_is_not_skipped():
    queue = module("proworksim.dynamic_queue_prewarm_control", "src/proworksim/software_benchmark_queue_v054.py")
    rows = [{"slot": {"slot_id": name, "instance_id": name, "arm": "MATCH"},
             "generation": {"status": "pending"}} for name in ("cold", "ready")]
    free = {"mp2": {"declaration": {"gpu_index": 2, "mode": "MATCH_PROJECT"}}}
    selected = queue.select_pool_slot(rows, free, is_prepared=lambda row: row["slot"]["instance_id"] == "ready")
    assert selected[0] is rows[1] and all(row["generation"]["status"] == "pending" for row in rows)
    assert queue.select_pool_slot(rows, free, is_prepared=lambda row: False) is None

    def failed(_):
        raise RuntimeError("immutable preparation failure")
    with pytest.raises(RuntimeError, match="preparation failure"):
        queue.select_pool_slot(rows, free, is_prepared=failed)
