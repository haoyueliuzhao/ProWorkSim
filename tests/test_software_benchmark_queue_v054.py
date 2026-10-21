"""Narrow CPU controls for persistent dispatch and independent trusted grading."""
import json
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_queue_v054 as queue


def coordinator(root):
    value = object.__new__(queue.Coordinator)
    value.root = root
    value.bindings_ref = {"path": str(root / "binding.json"), "sha256": "synthetic", "bytes": 0}
    value.state = {"status": "running", "rows": [], "faults": []}
    return value


def test_cpu_durable_intent_no_replay_and_order(tmp_path):
    """An accepted-but-unacknowledged launch survives restart without another launch."""
    rows = [{"slot": {"slot_index": i, "slot_id": str(i), "arm": arm},
             "generation": {"status": "pending", "attempts": []}, "scores": {},
             "delivery": {"status": "not_applicable"}}
            for i, arm in enumerate(("MATCH", "PROJECT", "REF"), 1)]
    value = coordinator(tmp_path)
    value.state["rows"] = rows
    calls = []

    class AcceptedButUnacknowledged:
        def launch(self, unit, job):
            saved = queue.read(tmp_path / "state.json")
            assert saved["rows"][0]["generation"]["status"] == "intent"
            calls.append((unit, job))
            return SimpleNamespace(returncode=1, stdout="", stderr="transport lost after acceptance")

        def active(self, unit):
            return unit == calls[0][0]

    value.system = AcceptedButUnacknowledged()
    value.start_job(rows[0]["generation"], kind="generation", directory=tmp_path / "job", argv=["unused"])
    assert value.state["status"] == "paused_technical_unknown"
    persisted = queue.read(tmp_path / "state.json")
    resumed = coordinator(tmp_path)
    resumed.state, resumed.system = persisted, value.system
    assert resumed.completion(resumed.state["rows"][0]["generation"]) is None
    assert len(calls) == 1
    assert queue.head_slot(resumed.state["rows"]) is None  # No jumping to REF.
    resumed.state["rows"][0]["generation"]["claimed"] = True
    assert queue.head_slot(resumed.state["rows"])["slot"]["slot_index"] == 2
    value.system.active = lambda unit: False
    resumed.completion(resumed.state["rows"][0]["generation"])
    assert resumed.state["rows"][0]["generation"]["status"] == "technical_unknown"
    assert len(calls) == 1

    result = {"status": "resource_not_ready", "reason_code": "gpu_lease_busy",
              "slot_claimed": False, "entered": False, "model_calls": 0, "GPU_loads": 0}
    assert queue.generation_outcome(75, result, False) == "resource_wait"
    assert queue.generation_outcome(75, result, True) == "technical_unknown"
    assert queue.generation_outcome(75, {**result, "model_calls": 1}, False) == "technical_unknown"
    assert queue.generation_outcome(75, {**result, "status": "preparation_not_ready"}, False) == "technical_unknown"


def test_cpu_two_grader_leases_and_result_identity(tmp_path, monkeypatch):
    """A third actual child cannot start; a completed worker cannot rerun."""
    monkeypatch.setattr(queue, "QUEUE", tmp_path)
    binding = queue.write_new(tmp_path / "binding.json", {"frozen_files": []})
    jobroot = tmp_path / "worker"
    jobroot.mkdir()
    sentinel = tmp_path / "child-ran"
    job = queue.write_new(jobroot / "job.json", {"kind": "score", "bindings": binding,
        "argv": ["/usr/bin/python3", "-c", "from pathlib import Path; Path(" + repr(str(sentinel)) + ").touch()"]})
    first = queue.lock_file(tmp_path / "locks/grader-0.lock")
    second = queue.lock_file(tmp_path / "locks/grader-1.lock")
    try:
        assert queue.command_worker(job) == 1
        assert not sentinel.exists()
    finally:
        first.close()
        second.close()
    with pytest.raises(ValueError, match="never be replayed"):
        queue.command_worker(job)

    # Determinate official false is a completed model result, while missing
    # output or a mismatched candidate must pause without calling the grader.
    record = {"slot": {"arm": "PROJECT", "instance_id": "synthetic", "slot_id": "test"},
              "generation": {"status": "closed"}, "scores": {}, "delivery": {"status": "awaiting_official_report"}}
    value = coordinator(tmp_path / "controller")
    value.state["rows"] = [record]
    root = tmp_path / "official"
    run_id = "v054-PROJECT-delivery-" + "a" * 40
    output = root / run_id
    output.mkdir(parents=True)
    request = {"trusted_output_root": str(root), "candidate_tree_sha256": "tree", "patch": {"sha256": "patch"}}
    request_ref = queue.write_new(tmp_path / "request.json", request)
    score = {"status": "running", "request": request_ref, "worker_directory": str(jobroot)}
    record["scores"]["delivery"] = score
    (jobroot / "stdout.log").write_text(json.dumps({"run_id": run_id}) + "\n")
    identity = {"arm": "PROJECT", "endpoint": "delivery", "instance_id": "synthetic",
                "candidate_tree_sha256": "tree", "patch_sha256": "patch"}
    queue.atomic(output / "identity.json", identity)
    queue.atomic(output / "receipt.json", {"status": "official_report", "resolved": False,
        "preparation_only": False, "actor_feedback": False, "run_id": run_id})
    value.complete_score(record, "delivery", {"returncode": 0})
    assert score["status"] == "official_report" and record["delivery"]["R_delivery"] == 0
    assert value.state["status"] == "running"
    identity["candidate_tree_sha256"] = "another-candidate"
    queue.atomic(output / "identity.json", identity)
    value.complete_score(record, "delivery", {"returncode": 0})
    assert score["status"] == "technical_unknown"
    assert value.state["status"] == "paused_technical_unknown"
