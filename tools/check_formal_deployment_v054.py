"""One narrow synthetic deployment control: authenticated HTTP and inherited lease lifetime."""
from __future__ import annotations

import argparse
import fcntl
import http.server
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from proworksim.software_benchmark_candidates_v054 import reference, write_new  # noqa: E402
from proworksim.software_benchmark_lease_handoff_v054 import (  # noqa: E402
    LeaseHandoff, drain_own_model_cgroup, receive_leases,
)
from proworksim.software_benchmark_ref_deployment_v054 import AuthenticatedLoopbackHTTP  # noqa: E402
from proworksim.software_benchmark_exact_transport_v054 import HTTPFailure  # noqa: E402
from proworksim.software_benchmark_supervision_v054 import (  # noqa: E402
    launch_owned, process_identity, stop_owned,
)


def wait_path(path, process):
    deadline = time.monotonic() + 15
    while not path.exists():
        if process.poll() is not None or time.monotonic() >= deadline:
            raise RuntimeError("Synthetic deployment control did not become ready")
        time.sleep(.01)


def busy(path):
    with path.open("a+b") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True


def lease_host(folder):
    handles = [path.open("a+b") for path in (folder / "physical.lock", folder / "global.lock")]
    for handle in handles:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    handoff = LeaseHandoff(folder / "lease.sock", [SimpleNamespace(handles=handles)])
    write_new(folder / "host-ready.json", handoff.owner)
    while True:
        time.sleep(1)


def lease_worker(folder):
    owner, descriptors = receive_leases(folder / "lease.sock")
    # A separate descendant survives its immediate parent until the cgroup drain.
    descendant = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    write_new(folder / "worker-ready.json", {"descendant": descendant.pid, "lease_descriptors": len(descriptors)})
    while True:
        try:
            alive = process_identity(owner["owner"]["pid"]) == owner["owner"]
        except FileNotFoundError:
            alive = False
        if not alive:
            break
        time.sleep(.01)
    write_new(folder / "host-dead.json", {"inherited_leases_still_held": True})
    # The driver observes this intentional finite window before cleanup starts.
    time.sleep(.4)
    proof = drain_own_model_cgroup()
    descendant.wait(timeout=5)
    write_new(folder / "descendants-quiet.json", proof)
    for descriptor in descriptors:
        os.close(descriptor)
    return 0


def control(folder):
    folder.mkdir(parents=True, exist_ok=False)
    requests = []
    key = "synthetic-local-auth-only-" + "x" * 32
    (folder / "key.private").write_text(key)
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            payload = self.rfile.read(int(self.headers["Content-Length"]))
            requests.append({"path": self.path, "payload": json.loads(payload)})
            accepted = self.headers.get("Authorization") == "Bearer " + key
            body = json.dumps({"authorized": accepted, "echo": json.loads(payload)}).encode()
            self.send_response(200 if accepted else 401)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_):
            pass
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    transport = AuthenticatedLoopbackHTTP(f"http://127.0.0.1:{server.server_port}", folder / "key.private")
    assert transport.post("/tokenize", {"synthetic": True})["authorized"]
    transport.key = "incorrect-local-test-key"
    try:
        transport.post("/v1/chat/completions", {"synthetic": True})
        raise AssertionError("Unauthorized response accepted")
    except HTTPFailure as error:
        assert error.evidence["http_status"] == 401
    finally:
        server.shutdown()
        server.server_close()
    assert len(requests) == 2
    host = subprocess.Popen([sys.executable, __file__, "--lease-host", str(folder)])
    worker = scope = None
    try:
        wait_path(folder / "host-ready.json", host)
        worker, scope = launch_owned([sys.executable, __file__, "--lease-worker", str(folder)],
            claim_id=uuid.uuid4().hex, role="model", runtime_seconds=30,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=(folder / "worker.stderr").open("xb"))
        wait_path(folder / "worker-ready.json", worker)
        assert busy(folder / "physical.lock")
        host.kill()
        host.wait(timeout=5)
        wait_path(folder / "host-dead.json", worker)
        assert busy(folder / "physical.lock") and busy(folder / "global.lock")
        worker.wait(timeout=10)
        assert worker.returncode == 0
        assert not busy(folder / "physical.lock") and not busy(folder / "global.lock")
        quiet = json.loads((folder / "descendants-quiet.json").read_text())
        assert quiet["other_processes_remaining"] == 0
        stopped = stop_owned(scope)
        return write_new(folder / "receipt.json", {
            "status": "passed", "checks": ["authenticated_loopback_HTTP", "401_not_retried",
                "same_flock_descriptions_transferred", "host_death_keeps_GPU_global_locks_busy",
                "owned_model_descendants_exit_before_lease_release"],
            "actual_model_calls": 0, "actual_GPU_loads": 0, "formal_slots_claimed": 0,
            "HTTP_fixture_requests": len(requests), "quiescence": quiet, "stopped": stopped,
            "sources": [reference(ROOT / "src/proworksim/software_benchmark_lease_handoff_v054.py"),
                        reference(ROOT / "src/proworksim/software_benchmark_ref_deployment_v054.py"),
                        reference(__file__)]})
    finally:
        if host.poll() is None:
            host.send_signal(signal.SIGKILL)
            host.wait(timeout=5)
        if scope is not None:
            stop_owned(scope)
            worker.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lease-host", type=Path)
    parser.add_argument("--lease-worker", type=Path)
    args = parser.parse_args()
    if args.lease_host:
        return lease_host(args.lease_host)
    if args.lease_worker:
        return lease_worker(args.lease_worker)
    print(json.dumps(control(args.output)))


if __name__ == "__main__":
    raise SystemExit(main())
