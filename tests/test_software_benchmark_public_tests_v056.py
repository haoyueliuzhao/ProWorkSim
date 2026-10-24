"""Real Unix IPC deadline controls plus host lifecycle failure preservation."""
from contextlib import contextmanager
import io
import json
import socketserver
import threading
import time
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_public_tests_v056 as module
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.storage import json_bytes


@contextmanager
def socket_server(tmp_path, *, delay=0., error=None):
    requests = []

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            request = json.loads(self.rfile.readline())
            requests.append(request)
            time.sleep(delay)
            body = {"error": error} if error else {"result": {"public_test": "completed"}}
            self.wfile.write(module.wire_json({"sequence": request["sequence"],
                "identity_sha256": request["identity_sha256"], **body}))

    path = tmp_path / "public.sock"
    server = socketserver.UnixStreamServer(str(path), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield path, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def client(tmp_path, socket_path, *, hard_at, clock=time.monotonic):
    guard = tmp_path / "guard.json"
    guard.write_bytes(json_bytes({"claim_id": "cpu-control", "stop_requested": False}))
    return module.DeadlinePublicTestClient(socket_path, {"version": module.VERSION, "claim_id": "cpu-control"},
        hard_at=hard_at, guard_path=guard, clock=clock)


def test_real_ipc_wait_covers_host_work_until_remaining_hard_boundary(tmp_path):
    with socket_server(tmp_path, delay=.12) as (path, requests):
        rpc = client(tmp_path, path, hard_at=5000., clock=lambda: 1000.)
        result = rpc.call("run_public_tests", bundle={"cpu_fixture": True})
        assert result == {"public_test": "completed"} and len(requests) == 1
        assert rpc.last_admission["socket_timeout_seconds"] == 4000 > 1860
        assert rpc.last_admission["fixed_1860_cap"] is False
        assert rpc.sequence == 1


def test_expired_or_cross_episode_deadline_never_dispatches(tmp_path):
    with socket_server(tmp_path) as (path, requests):
        rpc = client(tmp_path, path, hard_at=9., clock=lambda: 10.)
        with pytest.raises(TimeoutError, match="before public-test IPC dispatch"):
            rpc.call("run_public_tests", bundle={})
        assert rpc.sequence == 0 and requests == []
        rpc.guard_path.write_bytes(json_bytes({"claim_id": "other-episode", "stop_requested": False}))
        with pytest.raises(ValueError, match="different episodes"):
            rpc.call("run_public_tests", bundle={})
        assert requests == []


def test_quiescence_failure_is_not_a_test_failure_and_cannot_be_replayed(tmp_path):
    error = {"type": "TimeoutError", "message": "Failed to prove that every episode descendant exited"}
    with socket_server(tmp_path, error=error) as (path, requests):
        rpc = client(tmp_path, path, hard_at=time.monotonic() + 3)
        with pytest.raises(RuntimeError, match="Failed to prove"):
            rpc.call("run_public_tests", bundle={})
        with pytest.raises(RuntimeError, match="cannot replay"):
            rpc.call("run_public_tests", bundle={})
        assert len(requests) == 1 and rpc.failed is True


@pytest.mark.parametrize("remaining, expected_command_timeout", [(4000., 1800), (500., 500.)])
def test_host_keeps_command_cap_records_phases_and_reaps_before_cleanup(tmp_path, monkeypatch,
                                                                      remaining, expected_command_timeout):
    now = 1000.
    episode_root = tmp_path / "episode"
    episode_root.mkdir()
    guard = episode_root / "guard.json"
    guard.write_bytes(json_bytes({"stop_requested": False}))
    registry = episode_root / "scopes.json"
    registry.write_bytes(json_bytes([]))
    episode = SimpleNamespace(root=episode_root, hard_at=now + remaining,
        guard_path=guard, guard={"stop_requested": False}, registry=registry, claim_id="1" * 32)
    config = {"rootfs_environment": "synthetic", "stdlib": "synthetic", "public_test_entry": {
        "source": "public_repository", "cwd": "/testbed", "admitted": True, "argv": ["python", "-m", "pytest"]}}
    calls = []
    process = SimpleNamespace(stdin=io.BytesIO(), stdout=object(), wait=lambda **_: calls.append("reaped"))
    scope = {"claim_id": episode.claim_id, "unit": "cpu-control", "role": "publictesta"}
    frames = iter([{"type": "ready"}, {"observation": {"exit_code": 0}}, {"closed": True}])

    def clone(_environment, destination):
        root = destination / "rootfs"
        (root / "tmp").mkdir(parents=True)
        (root / "tmp/v056-public-stdout").write_bytes(b"synthetic output")
        (root / "tmp/v056-public-stderr").write_bytes(b"")
        manifest = destination / "rootfs-manifest.json"
        manifest.write_bytes(json_bytes({"prepared_root": str(root)}))
        return {"rootfs": str(root), "rootfs_manifest": str(manifest),
                "rootfs_manifest_sha256": reference(manifest)["sha256"], "environment_manifest": "synthetic"}

    @contextmanager
    def capacity(*_args, **_kwargs):
        yield

    def cleanup(*_args):
        assert calls == ["stopped", "reaped"]
        calls.append("cleaned")
        return {"synthetic_cleanup": True}

    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: now))
    monkeypatch.setattr(module, "resource_semaphore", capacity)
    monkeypatch.setattr(module, "clone_prepared_rootfs", clone)
    monkeypatch.setattr(module.subprocess, "run", lambda *_, **__: None)
    monkeypatch.setattr(module.previous, "replace_public_tree", lambda *_, **__: None)
    monkeypatch.setattr(module, "launch_owned", lambda *_, **__: (process, scope))
    monkeypatch.setattr(module.previous, "read_frame", lambda *_, **__: next(frames))
    monkeypatch.setattr(module, "validate_actor_ready", lambda _: {"synthetic": True})
    monkeypatch.setattr(module, "stop_owned", lambda _: calls.append("stopped") or {"populated": False})
    monkeypatch.setattr(module, "cleanup_episode_rootfs", cleanup)
    bundle = write_new(tmp_path / "bundle.json", {"files": {"main.py": "value = 1\n"},
        "entry_metadata": {"main.py": {"kind": "file", "encoding": "utf-8", "mode": "100644"}}})
    host = module.PublicTests(episode, config, {"slice": "synthetic"}, episode_root)
    result = host.run(bundle)
    assert result["passed"] is True and calls == ["stopped", "reaped", "cleaned"]
    sent = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
    assert sent[0]["action"]["timeout"] == expected_command_timeout
    assert sent[1]["op"] == "close"
    phases = json.loads((episode_root / "public-test-1/phase-times.json").read_bytes())
    for key in ("queued_at", "capacity_acquired_at", "clone_started_at", "clone_ready_at",
                "worker_ready_at", "command_dispatched_at", "command_returned_at", "stop_started_at",
                "quiet_at", "cleanup_started_at", "cleanup_finished_at", "returned_or_failed_at"):
        assert key in phases
    assert phases["command_limit_seconds"] == 1800
