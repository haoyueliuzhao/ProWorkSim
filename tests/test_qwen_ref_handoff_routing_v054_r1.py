"""Zero-model controls for the new host/episode route; no formal state writes."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import run_qwen_ref_handoff_v054_r5 as host  # noqa: E402
import run_benchmark_episode_ref_handoff_v054_r1 as worker  # noqa: E402


def example():
    return ({"path": "/sealed/host.json", "sha256": "a" * 64, "bytes": 1},
            {"pool_overlay": {"path": "/sealed/overlay.json", "sha256": "b" * 64, "bytes": 2},
             "episode_wrapper": str(ROOT / host.EPISODE_TOOL)})


def test_exact_generation_entry_preserves_all_episode_arguments():
    ref, revision = example()
    original = [str(host.base.HOST_PYTHON), str(ROOT / "tools/run_benchmark_episode_v054.py"),
                "--config", "/immutable/config with spaces.json", "--output", "/unstarted/episode"]
    result, changed = host.route_new_worker(original, kind="generation", revision_ref=ref, revision=revision)
    assert changed and result[:2] == [original[0], revision["episode_wrapper"]]
    assert result[result.index("--") + 1:] == original[2:]
    assert original[1] == str(ROOT / "tools/run_benchmark_episode_v054.py")
    assert result[2:10] == ["--host-revision", ref["path"], "--host-sha256", ref["sha256"],
                            "--overlay", revision["pool_overlay"]["path"],
                            "--overlay-sha256", revision["pool_overlay"]["sha256"]]


@pytest.mark.parametrize("kind,argv", [
    ("generation", ["/usr/bin/env", "PYTHONPATH=/frozen/kernel/src:/frozen/kernel",
                    str(host.base.HOST_PYTHON), "/frozen/kernel/tools/run_benchmark_episode_v054.py", "--config", "same"]),
    ("score", [str(host.base.HOST_PYTHON), str(ROOT / "tools/run_benchmark_episode_v054.py"), "--config", "same"]),
    ("generation", ["/different/python", str(ROOT / "tools/run_benchmark_episode_v054.py")]),
    ("generation", [str(host.base.HOST_PYTHON), "/different/run_benchmark_episode_v054.py"]),
])
def test_gpu6_and_nonmatching_routes_unchanged(kind, argv):
    ref, revision = example()
    result, changed = host.route_new_worker(argv, kind=kind, revision_ref=ref, revision=revision)
    assert not changed and result == argv


def test_worker_installs_overlay_then_forwards_original_arguments(monkeypatch):
    ref, revision = example()
    overlay = revision["pool_overlay"]
    calls = []
    monkeypatch.setattr(worker, "reference", lambda path: ref if str(path) == ref["path"] else overlay)
    monkeypatch.setattr(host, "validate_revision", lambda value, initial: revision)
    monkeypatch.setattr(host.pool_overlay, "install", lambda value: calls.append(("install", value)))

    def original_main():
        assert calls == [("install", overlay)]
        calls.append(("run", sys.argv[1:]))
        return 17

    monkeypatch.setitem(sys.modules, "proworksim.software_benchmark_runner_v054", SimpleNamespace(main=original_main))
    before = sys.argv
    args = ["--host-revision", ref["path"], "--host-sha256", ref["sha256"],
            "--overlay", overlay["path"], "--overlay-sha256", overlay["sha256"],
            "--", "--config", "/same/config.json", "--output", "/same/episode"]
    assert worker.main(args) == 17
    assert calls[-1] == ("run", args[9:])
    assert sys.argv is before


def test_start_job_changes_only_matching_generation_and_delegates(monkeypatch):
    ref, revision = example()
    coordinator = object.__new__(host.HandoffCoordinator)
    coordinator.handoff_revision_ref, coordinator.handoff_revision = ref, revision
    calls = []
    monkeypatch.setattr(host.previous.VolumeCoordinator, "start_job",
        lambda self, record, **kwargs: calls.append((record.copy(), kwargs)))
    record = {"status": "pending", "seed_marker": 123}
    argv = [str(host.base.HOST_PYTHON), str(ROOT / "tools/run_benchmark_episode_v054.py"),
            "--config", "same", "--output", "same"]
    coordinator.start_job(record, kind="generation", directory=Path("/unstarted/worker"), argv=argv)
    assert record["status"] == "pending" and record["seed_marker"] == 123
    assert record["ref_handoff_host_revision"] == ref
    assert calls[0][1]["argv"][1] == revision["episode_wrapper"]
    other = {"status": "pending"}
    coordinator.start_job(other, kind="score", directory=Path("/unstarted/score"), argv=argv)
    assert other == {"status": "pending"} and calls[1][1]["argv"] == argv
