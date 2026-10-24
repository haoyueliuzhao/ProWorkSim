"""Durable dispatch, resource backpressure and local-fault queue controls; no models."""
import json
import os
from pathlib import Path

import pytest

from proworksim import software_benchmark_queue_v056 as module
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def slot(index):
    return {"slot_id": f"synthetic-slot-{index}", "instance_id": f"synthetic-task-{index}",
            "condition_id": "REF_B0500K", "arm": "REF"}


def queue(tmp_path):
    value = module.Queue.__new__(module.Queue)
    value.root = tmp_path
    value.binding_ref = {"path": "/synthetic/binding", "sha256": "a" * 64, "bytes": 0}
    value.state = module.initial_state(value.binding_ref, [slot(1), slot(2), slot(3)])
    value.rows = {row["slot"]["slot_id"]: row for row in value.state["rows"]}
    value.children = {}
    value.plan = {"common_limits": {"hard_seconds": 10}}
    return value


def finished_job(value, index, kind, returncode=0):
    row = value.rows[slot(index)["slot_id"]]
    job_id = f"{kind}-{index}"
    folder = value.root / job_id
    folder.mkdir()
    intent = write_new(folder / "job.json", {"slot_id": row["slot"]["slot_id"]})
    write_new(folder / "completion.json", {"job": intent, "returncode": returncode, "status": "process_exited"})
    payload = {"output": str(folder / "episode"), "receipt_output": str(folder / "pointer.json"),
               "quiescence_output": str(folder / "quiescence.json")}
    (folder / "episode").mkdir()
    job = {"kind": kind, "status": "running", "directory": str(folder), "job": intent,
           "slot_id": row["slot"]["slot_id"], "instance_id": row["slot"]["instance_id"],
           "resident": f"resident-{index}", "grader": index - 1,
           "reservation_bytes": 64 * module.GIB, "intent_unix": 0, "payload": payload}
    value.state["jobs"][job_id] = job
    row["generation" if kind == "generation" else "score"].update(status="running", job_id=job_id)
    return row, job, folder


def test_frozen_ready_selection_and_disk_memory_limits():
    state = module.initial_state({}, [slot(1), slot(2), slot(3)])
    state["rows"][0]["generation"]["status"] = "deferred"
    # A deferred earlier slot cannot hold the independent ready task behind it.
    selected = module.selected_pending(state["rows"], {"synthetic-task-2", "synthetic-task-3"}, ["gpu4", "gpu7"], 1)
    assert [(row["slot"]["slot_id"], resident) for row, resident in selected] == [("synthetic-slot-2", "gpu4")]
    settings = dict(free_bytes=300 * module.GIB, reserved_bytes=128 * module.GIB,
                    requested_bytes=64 * module.GIB, floor_bytes=128 * module.GIB,
                    available_memory=1024 * module.GIB, memory_reservation=64 * module.GIB,
                    load_one=1, cpu_count=64)
    assert module.resource_gate(**settings)["admitted"] is False
    settings["free_bytes"] = 320 * module.GIB
    assert module.resource_gate(**settings)["admitted"] is True
    settings["available_memory"] = 100 * module.GIB
    assert module.resource_gate(**settings)["admitted"] is False


def test_bad_generation_evidence_is_deferred_while_other_candidate_enters_scoring(tmp_path, monkeypatch):
    value = queue(tmp_path)
    monkeypatch.setattr(module, "alive", lambda _: False)
    bad, bad_job, bad_folder = finished_job(value, 1, "generation")
    (bad_folder / "episode/result.json").write_text("malformed")
    good, _, folder = finished_job(value, 2, "generation")
    request = write_new(folder / "request.json", {"slot_id": good["slot"]["slot_id"], "condition_id": "REF_B0500K"})
    write_new(folder / "episode/result.json", {"slot_id": good["slot"]["slot_id"], "condition_id": "REF_B0500K",
        "status": "closed", "candidate_locked": True, "scoring_requests": [request],
        "resource_release": {"released": True}})
    value.refresh_jobs()
    assert bad["generation"]["status"] == "deferred"
    assert bad["score"]["status"] == "not_applicable"
    assert bad_job["resident"] in value.state["quarantined_residents"]
    assert good["generation"]["status"] == "closed"
    assert good["score"]["status"] == "pending"
    assert value.rows["synthetic-slot-3"]["generation"]["status"] == "pending"
    # The persisted state still adopts exact same slots after the coordinator returns.
    saved = json.loads((tmp_path / "state.json").read_text())
    assert [row["slot"] for row in saved["rows"]] == [slot(1), slot(2), slot(3)]


def test_failed_scorer_with_real_quiescence_does_not_exhaust_grading_pool(tmp_path, monkeypatch):
    value = queue(tmp_path)
    monkeypatch.setattr(module, "alive", lambda _: False)
    row, _, folder = finished_job(value, 1, "score", returncode=1)
    write_new(folder / "quiescence.json", {"slot_id": row["slot"]["slot_id"], "condition_id": "REF_B0500K",
        "quiescent": True, "cleanup_errors": [], "owned_container_ids": []})
    value.rows["synthetic-slot-2"]["score"]["status"] = "pending"
    value.refresh_jobs()
    assert row["score"]["status"] == "deferred" and row["score"]["quiescent"] is True
    assert value.state["quarantined_graders"] == {}
    assert value.rows["synthetic-slot-2"]["score"]["status"] == "pending"


def test_missing_quiescence_retains_resource_reservation(tmp_path, monkeypatch):
    value = queue(tmp_path)
    monkeypatch.setattr(module, "alive", lambda _: False)
    monkeypatch.setattr(module, "RUNS", tmp_path)
    row, _, _ = finished_job(value, 1, "score", returncode=1)
    value.refresh_jobs()
    assert row["score"]["status"] == "deferred"
    assert "0" in value.state["quarantined_graders"]
    assert value.reserved()[0] == 64 * module.GIB


def test_running_identity_is_adopted_without_relaunch(tmp_path, monkeypatch):
    value = queue(tmp_path)
    row, job, folder = finished_job(value, 1, "generation")
    (folder / "completion.json").unlink()
    identity = {"pid": os.getpid(), "start_ticks": 123}
    write_new(folder / "started.json", {"job": job["job"], "host_process": identity})
    monkeypatch.setattr(module, "alive", lambda item: item == identity)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **k: pytest.fail("Must not replay adopted worker"))
    value.refresh_jobs()
    assert row["generation"]["status"] == "running"
    assert job["host_process"] == identity and job["status"] == "running"


def test_launch_intent_is_durable_before_process_can_execute(tmp_path, monkeypatch):
    value = queue(tmp_path)
    monkeypatch.setattr(module, "RUNS", tmp_path)
    seen = []

    def launch(argv, **kwargs):
        state = json.loads((tmp_path / "state.json").read_text())
        assert state["rows"][0]["generation"]["status"] == "running"
        assert len(state["jobs"]) == 1
        entry = next(iter(state["jobs"].values()))
        assert entry["status"] == "launch_intent"
        assert Path(entry["job"]["path"]).is_file()
        seen.append(argv)
        return type("Process", (), {"pid": 900000})()

    monkeypatch.setattr(module.subprocess, "Popen", launch)
    monkeypatch.setattr(module, "process_identity", lambda pid: {"pid": pid, "start_ticks": 100})
    value.start_job("generation", "first", ["never-executed"], row=value.state["rows"][0],
                    instance_id="synthetic-task-1", resident="gpu4", reservation=64 * module.GIB)
    assert len(seen) == 1
    assert len(value.state["jobs"]) == 1


def test_command_worker_records_one_cpu_subprocess_and_rejects_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "RUNS", tmp_path)
    folder = tmp_path / "worker"
    folder.mkdir()
    sources = write_new(tmp_path / "sources.json", {"files": []})
    binding = write_new(tmp_path / "binding.json", {"frozen_sources": sources})
    job = write_new(folder / "job.json", {"version": module.VERSION, "binding": binding,
        "argv": [str(module.ROOT / ".venv/bin/python"), "-c", "import time; time.sleep(.05)"],
        "timeout_seconds": 2, "resource_lock": str(tmp_path / "resource.lock")})
    module.command_worker(job)
    completion = json.loads((folder / "completion.json").read_text())
    assert completion["returncode"] == 0 and completion["job"] == reference(folder / "job.json")
    with pytest.raises(ValueError, match="never replayed"):
        module.command_worker(job)
