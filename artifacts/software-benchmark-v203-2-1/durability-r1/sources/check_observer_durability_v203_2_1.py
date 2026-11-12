"""Actual user-process crash/concurrency controls; no model/API/Docker/services.

Run once per fresh evidence directory. Workers terminate only themselves with
os._exit; recovery projects journal observations and never dispatches world calls.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from proworksim.software_observer_journal_v203_2_1 import (  # noqa: E402
    ObservationConflict, ObserverJournal, inspect_export,
)
from proworksim.software_passive_observer_v203_2 import ObservedPort  # noqa: E402


MODE_EXIT = 73


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def worker(mode, database, identity):
    if mode == "world-before-write":
        # Independent durable world witness precedes a receipt capture failure.
        with (database.parent / "world-actions.jsonl").open("ab") as stream:
            stream.write(b'{"action":"actual_cpu_world_mutation","calls":1}\n')
            stream.flush()
            os.fsync(stream.fileno())
    with ObserverJournal(database, timeout=5) as journal:
        if mode.startswith("crash-") or mode == "world-before-write":
            stage = {"crash-before-write": "before_write",
                     "crash-uncommitted": "after_insert_before_commit",
                     "crash-after-durable": "after_commit",
                     "crash-projection": "before_projection_commit",
                     "world-before-write": "before_write"}[mode]
            journal._fault = lambda where: os._exit(MODE_EXIT) if where == stage else None
            journal.append("RECEIPT", "receipt:task", {"actor": "cpu", "task_id": "task", "value": 1})
            journal.save_projection("default", 1, {"task": 1}, expected_cursor=0)
        elif mode == "normal-close":
            journal.append("RECEIPT", "receipt:task", {"actor": "cpu", "task_id": "task", "value": 1})
            journal.save_projection("default", 1, {"task": 1}, expected_cursor=0)
        elif mode == "producer":
            for ordinal in range(40):
                journal.append("RECEIPT", f"producer:{identity}:{ordinal}",
                               {"actor": identity, "ordinal": ordinal})
        elif mode == "duplicate":
            journal.append("RECEIPT", "receipt:shared", {"value": 1})
        elif mode == "partial-export":
            seen = 0
            def die_after_second_record(stage):
                nonlocal seen
                if stage == "export_after_record":
                    seen += 1
                    if seen == 2:
                        os._exit(MODE_EXIT)
            journal._fault = die_after_second_record
            journal.export(database.parent / "export.jsonl")
        elif mode == "recover":
            checkpoint = journal.load_projection()
            state = checkpoint["state"] or {}
            through = checkpoint["cursor"]
            for row in journal.pending():
                state[row["payload"].get("task_id", row["key"])] = row["payload"].get("value", 1)
                through = row["sequence"]
            journal.save_projection("default", through, state, expected_cursor=checkpoint["cursor"])
            save(database.parent / "recovered.json", {"projection": journal.load_projection(),
                                                       "integrity": journal.integrity(),
                                                       "world_actions_dispatched": 0})


def launch(mode, database, identity="one"):
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", mode,
               "--database", str(database), "--identity", identity]
    return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def wait(process, expected=0):
    stdout, stderr = process.communicate(timeout=40)
    if process.returncode != expected:
        raise AssertionError({"returncode": process.returncode, "expected": expected,
                              "stdout": stdout, "stderr": stderr})
    return {"pid": process.pid, "exit_code": process.returncode, "stdout": stdout, "stderr": stderr}


def process_case(run, name, expected_rows, expected_pending):
    directory = run / name
    directory.mkdir(parents=True)
    database = directory / "observer.sqlite"
    original = wait(launch(name, database), 0 if name == "normal-close" else MODE_EXIT)
    with ObserverJournal(database) as journal:
        before = journal.integrity(expected_records=1)
        assert before["durable_records"] == expected_rows
        assert before["default_pending"] == expected_pending
    recovered = wait(launch("recover", database))
    proof = json.loads((directory / "recovered.json").read_text())
    assert proof["integrity"]["default_pending"] == 0
    assert proof["integrity"]["durable_records"] == expected_rows
    world_calls = 0
    if name == "world-before-write":
        world_calls = len((directory / "world-actions.jsonl").read_text().splitlines())
        assert world_calls == 1 and expected_rows == 0
    return {"passed": True, "original_process": original, "recovery_process": recovered,
            "before_recovery": before, "after_recovery": proof,
            "independent_world_calls": world_calls,
            "world_action_replay_count": 0,
            "loss_before_durable_commit_is_guaranteed_recoverable": False}


class CpuWorldPort:
    def __init__(self):
        self.calls = 0
        self.response = {"ok": True, "result": {"cpu_effect": "performed_once"}}

    def call(self, tool, **kwargs):
        self.calls += 1
        return self.response


class FailingObserverAdapter:
    """Use the frozen real wrapper with a failing durable sink, no retry queue."""
    def __init__(self, journal):
        self.journal = journal
        self.faults = deque(maxlen=8)

    def intent(self, actor, tool, arguments, key):
        self.journal.append("INTENT", "intent:" + key, {"actor": actor, "tool": tool, "arguments": arguments})

    def receipt(self, actor, tool, arguments, response, key):
        self.journal.append("RECEIPT", "receipt:" + key, {"actor": actor, "tool": tool,
                                                       "arguments": arguments, "response": response})


def main(artifact, run):
    artifact.mkdir(parents=True, exist_ok=False)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    parent_cpu = time.process_time()
    children_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    protocol = {"version": "v203.2.1", "runtime": "local ordinary-user CPU processes",
                "new_model_API_calls": 0, "docker_objects": 0, "services_created": 0,
                "process_termination": "workers call os._exit(73) only on themselves",
                "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in [Path(__file__), ROOT / "src/proworksim/software_observer_journal_v203_2_1.py"]},
                "planned_producers": 4, "records_per_producer": 40,
                "durability_limit": "No claim for crash before commit, storage loss or power failure",
                "order_limit": "Serialized journal commit order; not a claim of causal total order of independent world actions",
                "resource_limit": "At most four short CPU workers; no network, GPU, Docker or host configuration"}
    save(artifact / "protocol.json", protocol)
    cases = {}
    for name, count, pending in [("normal-close", 1, 0), ("crash-before-write", 0, 0),
                                  ("crash-uncommitted", 0, 0), ("crash-after-durable", 1, 1),
                                  ("crash-projection", 1, 1), ("world-before-write", 0, 0)]:
        cases[name] = process_case(run, name, count, pending)

    database = run / "multiprocess" / "observer.sqlite"
    with ObserverJournal(database):
        pass
    processes = [launch("producer", database, str(i)) for i in range(4)]
    process_receipts = [wait(process) for process in processes]
    with ObserverJournal(database) as journal:
        records = list(journal.records())
        assert [row["sequence"] for row in records] == list(range(1, 161))
        for actor in range(4):
            assert [row["payload"]["ordinal"] for row in records if row["payload"]["actor"] == str(actor)] == list(range(40))
        proof = journal.integrity(expected_records=160)
        assert proof["status"] == "ok" and proof["expected_count_matches"]
        save(artifact / "multiprocess-order.json", [{"sequence": row["sequence"], "key": row["key"]} for row in records])
        cases["multiprocess-serialized-order"] = {"passed": True, "processes": process_receipts,
                                                   "proof": proof, "per_producer_order_preserved": True,
                                                   "cross_producer_wall_clock_order_claimed": False}

    database = run / "duplicates" / "observer.sqlite"
    with ObserverJournal(database):
        pass
    processes = [launch("duplicate", database, str(i)) for i in range(4)]
    duplicate_receipts = [wait(process) for process in processes]
    with ObserverJournal(database) as journal:
        try:
            journal.append("RECEIPT", "receipt:shared", {"value": 2})
        except ObservationConflict:
            pass
        else:
            raise AssertionError("Conflicting bytes were accepted")
        proof = journal.integrity(expected_records=1)
        assert proof["durable_records"] == 1 and proof["known_conflicting_appends"] == 1
        cases["concurrent-duplicate-and-conflict"] = {"passed": True, "processes": duplicate_receipts, "proof": proof}

    database = run / "partial-export" / "observer.sqlite"
    target = database.parent / "export.jsonl"
    with ObserverJournal(database) as journal:
        journal.append("RECEIPT", "first", {"value": 1})
        journal.export(target)
        original = target.read_bytes()
        journal.append("RECEIPT", "second", {"value": 2})
        journal.append("RECEIPT", "third", {"value": 3})
    process = wait(launch("partial-export", database), MODE_EXIT)
    partials = list(target.parent.glob("export.jsonl.partial-*"))
    assert len(partials) == 1 and target.read_bytes() == original
    incomplete = inspect_export(partials[0])
    assert incomplete["status"] == "partial" and incomplete["complete_records"] == 2
    partials[0].rename(target.parent / "interrupted-export.partial.jsonl")
    with ObserverJournal(database) as journal:
        journal.export(target)
    complete = inspect_export(target)
    assert complete["status"] == "complete" and complete["complete_records"] == 3
    cases["partial-export-process-exit"] = {"passed": True, "process": process,
                                              "incomplete_export": incomplete, "reexport": complete,
                                              "previous_complete_export_survived": True}

    database = run / "fail-open" / "observer.sqlite"
    with ObserverJournal(database, timeout=0.02) as journal:
        adapter = FailingObserverAdapter(journal)
        world = CpuWorldPort()
        port = ObservedPort(world, "cpu", adapter)
        # A held writer lock models an unavailable durable sink using real SQLite.
        import sqlite3
        blocker = sqlite3.connect(database, isolation_level=None)
        blocker.execute("BEGIN IMMEDIATE")
        try:
            response = port.call("cpu_mutation", request_key="same")
        finally:
            blocker.rollback()
            blocker.close()
        assert response is world.response and world.calls == 1 and len(adapter.faults) == 2
        assert journal.integrity()["durable_records"] == 0
        # Observer-only retry with the already obtained bytes cannot call the world.
        adapter.receipt("cpu", "cpu_mutation", {}, response, "same")
        assert world.calls == 1
        cases["unavailable-observer-fail-open"] = {"passed": True, "world_calls": world.calls,
                                                     "original_result_identity_retained": True,
                                                     "bounded_fault_capacity": adapter.faults.maxlen,
                                                     "faults": list(adapter.faults),
                                                     "missing_intent_not_hidden_by_receipt_recovery": True,
                                                     "proof": journal.integrity(expected_records=2)}

    database = run / "cost" / "observer.sqlite"
    samples = []
    tracemalloc.start()
    cpu_start = time.process_time()
    elapsed_start = time.perf_counter()
    memory_checkpoints = {}
    with ObserverJournal(database) as journal:
        for ordinal in range(1024):
            before = time.perf_counter_ns()
            journal.append("RECEIPT", str(ordinal), {"value": ordinal, "padding": "x" * 4096})
            if ordinal < 256:
                samples.append((time.perf_counter_ns() - before) / 1e6)
            if ordinal + 1 in (128, 1024):
                current, peak = tracemalloc.get_traced_memory()
                memory_checkpoints[str(ordinal + 1)] = {"python_current_bytes": current, "python_peak_bytes": peak}
        storage_open = {path.name: path.stat().st_size for path in database.parent.iterdir() if path.is_file()}
        pending_count = journal.integrity()["default_pending"]
    elapsed = time.perf_counter() - elapsed_start
    cpu = time.process_time() - cpu_start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    ordered = sorted(samples)
    cost = {"records": 1024, "payload_padding_bytes": 4096, "timed_append_samples": len(samples),
            "append_latency_ms": {"median": statistics.median(samples), "p95": ordered[int(0.95 * (len(ordered) - 1))],
                                  "max": max(samples)},
            "wall_seconds": elapsed, "parent_cpu_seconds": cpu, "python_peak_bytes": peak,
            "memory_checkpoints": memory_checkpoints, "sqlite_cache_limit_kib": 2048,
            "pending_records_on_disk": pending_count, "in_memory_pending_records": 0,
            "storage_bytes_before_close": storage_open,
            "storage_bytes_after_close": {path.name: path.stat().st_size for path in database.parent.iterdir() if path.is_file()},
            "peak_rss_kib_process_lifetime": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "method_limits": ["Python tracemalloc excludes SQLite native pages; configured SQLite cache and lifetime RSS also reported",
                              "Local ordinary-user single-run timing with tracing enabled; not a production speedup estimate",
                              "Append cost excludes payload acquisition and downstream state projection"]}
    assert pending_count == 1024
    children_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    summary = {"passed": True, "case_count": len(cases), "cases": cases, "cost": cost,
               "total_wall_seconds": time.perf_counter() - started,
               "parent_cpu_seconds": time.process_time() - parent_cpu,
               "child_cpu_seconds": (children_after.ru_utime + children_after.ru_stime
                                     - children_before.ru_utime - children_before.ru_stime),
               "new_model_API_calls": 0, "world_actions_replayed": 0,
               "evidence_scope": "CPU journal durability/atomicity only; not real-model observation completeness",
               "task_completeness": {"normal_close": "1/1 expected receipt durable, projection complete",
                                     "after_durable_commit": "1/1 expected receipt recovered in fresh process",
                                     "before_commit": "0/1 expected receipt; partial by external expected manifest",
                                     "fail_open": "1/2 expected observation records; missing intent remains partial"},
               "limitations": ["Crashes before the durable commit can lose observations; never retry world actions to fill them",
                               "SQLite FULL/process tests do not demonstrate disk failure or power-loss recovery",
                               "Commit order across producers is a capture order, not a proof of world causal order",
                               "Matching record counts do not establish full task-level evidence coverage"]}
    save(artifact / "summary.json", summary)
    save(artifact / "cost.json", cost)
    print(json.dumps({"passed": True, "cases": len(cases), "summary": str(artifact / "summary.json")}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--identity", default="one")
    parser.add_argument("--artifact-dir", type=Path,
                        default=ROOT / "artifacts/software-benchmark-v203-2-1/durability-r1")
    parser.add_argument("--run-dir", type=Path,
                        default=ROOT / "runs/software-benchmark-v203-2-1/durability-r1")
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.database, args.identity)
    else:
        main(args.artifact_dir, args.run_dir)
