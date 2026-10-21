"""One zero-worker CPU control for cache readiness, cooldown and deferred closure."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from proworksim import software_benchmark_queue_v055 as queue  # noqa: E402
from proworksim.software_benchmark_candidates_v054 import reference, write_new  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disk-admission-only", action="store_true")
    args = parser.parse_args()
    coordinator = object.__new__(queue.Coordinator)
    coordinator.plan = {"generation_concurrency": 32, "scoring_concurrency": 4,
                        "preparation_concurrency": 2, "maximum_api_concurrency": 64}
    coordinator.template = {"lazy_native_preparation": {"cache_root": "/tmp"}}
    coordinator.registry = {name: {"baseline_mapping": {}} for name in ("ready", "pending", "failed")}
    rows = [{"slot": {"instance_id": name, "slot_id": name + ":" + condition},
             "generation": {"status": "pending"}, "scores": []}
            for name in coordinator.registry for condition in sorted(queue.CONDITIONS)]
    initial = {"rows": rows, "preparation": {name: {"readiness": {"status": "unknown"}, "attempts": []}
               for name in coordinator.registry}, "exceptions": [], "dispatch_stopped": False}
    budget = {"halted": None, "can_admit_minimum_request": True, "inflight_count": 0,
              "admission_wait_seconds": 0}
    coordinator.ledger = SimpleNamespace(snapshot=lambda: dict(budget))
    coordinator.save = lambda: None
    dispatched, preparations = [], []

    def launch(row, record, *, kind, request=None):
        dispatched.append((row["slot"]["instance_id"], kind))
        record["status"] = "running"

    def prepare(name):
        preparations.append(name)
        coordinator.state["preparation"][name]["worker"] = {"status": "running"}

    coordinator.launch, coordinator.launch_preparation = launch, prepare
    coordinator.collect = lambda *args, **kwargs: None
    with TemporaryDirectory(prefix="v055-cache-gate-") as temporary:
        fake_root = Path(temporary)
        legacy = fake_root / "runs/software-benchmark-v054/formal-queue-r1/state.json"
        legacy.parent.mkdir(parents=True)
        legacy.write_text('{"rows": []}')
        with (patch.object(queue, "ROOT", fake_root), patch.object(queue.os, "cpu_count", return_value=176),
              patch.object(queue, "host_capacity", return_value={"admit": True, "memory_available_bytes": 900 * 1024**3}),
              patch.object(queue.shutil, "disk_usage", return_value=SimpleNamespace(free=900 * 1024**3)),
              patch("proworksim.software_benchmark_prewarm_v054.preparation_state",
                    side_effect=lambda name, **_: {"instance_id": name, "status": {
                        "ready": "qualified", "pending": "pending", "failed": "failed"}[name]})):
            if args.disk_admission_only:
                coordinator.state = deepcopy(initial)
                coordinator.state["rows"][0]["scores"] = [{"status": "pending", "request": {"fixture": True}}]
                with patch.object(queue.shutil, "disk_usage", return_value=SimpleNamespace(free=99 * 1024**3)):
                    assert coordinator.tick() is False
                assert dispatched == [("ready", "score")] and preparations == []
                assert coordinator.state["dispatch_stopped"] is False
                receipt = {"version": "v055-environment-queue-disk-control-r2", "passed": True,
                    "inherited_readiness_cooldown_and_deferred_closure_control": reference(
                        ROOT / "runs/software-benchmark-v055/environment-queue-control-r1.json"),
                    "prior_three_controls_repeated": False,
                    "below_100GiB_blocks_new_generation_and_preparation": True,
                    "existing_scoring_proceeds_at_low_water": True,
                    "actual_workers_started": 0, "model_calls": 0, "grader_calls": 0,
                    "source": reference(ROOT / "src/proworksim/software_benchmark_queue_v055.py")}
                ref = write_new(ROOT / "runs/software-benchmark-v055/environment-queue-control-r2.json", receipt)
                print(json.dumps({"passed": True, "new_disk_gate_case": 1, "model_calls": 0, "receipt": ref}))
                return
            coordinator.state = deepcopy(initial)
            assert coordinator.tick() is False
            assert dispatched == [("ready", "generation")] * 6 and preparations == ["pending"]
            assert all(row["generation"]["status"] == "pending" for row in coordinator.state["rows"]
                       if row["slot"]["instance_id"] in {"pending", "failed"})
            for row in coordinator.state["rows"]:
                if row["slot"]["instance_id"] != "failed":
                    row["generation"]["status"] = "closed"
            coordinator.state["preparation"]["pending"].update(
                readiness={"status": "qualified"}, worker={"status": "qualified"})
            assert coordinator.tick() is True
            assert coordinator.state["status"] == "primary_finished_with_deferred_environment"
            coordinator.state = deepcopy(initial)
            budget["admission_wait_seconds"] = 30
            coordinator.state["rows"][0]["scores"] = [{"status": "pending", "request": {"fixture": True}}]
            dispatched.clear()
            preparations.clear()
            assert coordinator.tick() is False
            assert dispatched == [("ready", "score")]
            assert coordinator.state["dispatch_stopped"] is False
    receipt = {"version": "v055-environment-queue-control-r1", "passed": True,
        "ready_tasks_only_enter_generation": True, "unprepared_tasks_remain_unclaimed_pending": True,
        "failed_environment_deferred_until_primary_finishes": True,
        "cooldown_does_not_block_official_scoring_or_end_budget": True,
        "actual_workers_started": 0, "model_calls": 0, "grader_calls": 0,
        "source": reference(ROOT / "src/proworksim/software_benchmark_queue_v055.py")}
    ref = write_new(ROOT / "runs/software-benchmark-v055/environment-queue-control-r1.json", receipt)
    print(json.dumps({"passed": True, "model_calls": 0, "receipt": ref}))


if __name__ == "__main__":
    main()
