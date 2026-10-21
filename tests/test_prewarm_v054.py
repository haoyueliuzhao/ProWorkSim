"""One CPU-only state control; initializer is a programmed filesystem fixture."""
import fcntl
import json
from pathlib import Path

from proworksim import software_benchmark_native_lazy_v054 as native
from proworksim import software_benchmark_prewarm_v054 as warm
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def test_two_task_horizon_shared_cache_and_global_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(warm, "ROOT", tmp_path)
    root = tmp_path / "runs/software-benchmark-v054/prewarm"
    cache = tmp_path / "runs/software-benchmark-v054/native-lazy-cache"
    root.mkdir(parents=True)
    (cache / "locks").mkdir(parents=True)

    def artifact(name, value):
        return write_new(root / name, value)

    mapping = artifact("mapping.json", {"fixture_only": True})
    slots = [{"slot_id": name, "instance_id": name, "slot_index": index}
             for index, name in enumerate(("a", "b", "c", "d"), 1)]
    rows = [{"slot": slot, "generation": {"status": "pending"}} for slot in slots]
    queue = root / "queue.json"
    queue.write_text(json.dumps({"rows": rows}))
    registry = artifact("registry.json", {"entries": [{"instance_id": slot["instance_id"],
                    "baseline_mapping": mapping} for slot in slots]})
    policy = artifact("policy.json", {"version": warm.VERSION, "root": str(root),
        "workers": 1, "maximum_unused_prepared_tasks": 2, "minimum_disk_free_bytes": 64 * 1024**3,
        "queue_state_path": str(queue), "cache_root": str(cache), "registry": registry,
        "slots": artifact("slots.json", {"slots": slots}), "source_manifest": artifact("source.json", {"files": []}),
        "public_tasks": artifact("public.json", []), "stdlib": str(root),
        "docker_socket": "unix://" + str(tmp_path / "runs/software-panel-v053/docker/docker.sock"),
        "model_loading_authorized": False, "model_generation_authorized": False,
        "formal_claims_authorized": False, "hidden_grader_authorized": False,
        "automatic_retry_failed_preparation": False})
    calls = []

    def initializer(instance, **kwargs):
        calls.append(instance)
        assert kwargs["mapping_reference"] == mapping
        if instance == "d":
            raise RuntimeError("Programmed public initialization failure; no real command executed")
        path = cache / instance / mapping["sha256"][:16]
        path.mkdir(parents=True)
        (cache / "locks" / (instance + ".lock")).touch(exist_ok=True)
        references = {key: write_new(path / (key + ".json"), {"fixture_only": True, "field": key})
                      for key in warm.PATH_FIELDS}
        write_new(path / "lazy-preparation.json", {"status": "qualified", "baseline_mapping": mapping,
            "slot_claimed": False, "model_calls": 0, **references})
        return {key: item["path"] for key, item in references.items()}

    monkeypatch.setattr(native, "ensure_native_instance", initializer)
    monkeypatch.setattr(warm.shutil, "disk_usage", lambda _: type("Space", (), {"free": 100 * 1024**3})())
    runner = warm.Prewarmer(policy)
    with (cache / "locks/a.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert runner.tick() and calls == []
        assert warm.preparation_state("a", mapping_reference=mapping, cache_root=cache)["status"] == "preparing"
    assert runner.tick() and calls == ["a"]
    with (cache / "locks/a.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        paths = warm.qualified_paths("a", mapping_reference=mapping, cache_root=cache)
        assert set(paths) == set(warm.PATH_FIELDS)
        assert all(Path(path).is_file() for path in paths.values())
    assert runner.tick() and calls == ["a", "b"]
    assert runner.tick() and calls == ["a", "b"]  # The third cold task stays untouched.
    rows[0]["generation"]["status"] = "running"
    queue.write_text(json.dumps({"rows": rows}))
    assert runner.tick() and calls == ["a", "b", "c"]
    rows[1]["generation"]["status"] = "running"
    queue.write_text(json.dumps({"rows": rows}))
    assert runner.tick() is False and calls == ["a", "b", "c", "d"]
    health = warm.prewarm_health(policy)
    assert health["status"] == "failed" and len(health["failures"]) == 1
    assert runner.tick() is False and calls == ["a", "b", "c", "d"]
    for row in warm._events(runner.policy):
        assert row["model_calls"] == row["GPU_loads"] == row["formal_claims"] == row["hidden_grader_calls"] == 0
        assert reference(row["event_reference"]["path"]) == row["event_reference"]
