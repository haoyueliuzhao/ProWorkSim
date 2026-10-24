"""Managed public tests with episode-bound IPC waiting and unchanged command limits."""
from __future__ import annotations

import fcntl
import json
import math
from pathlib import Path
import shlex
import subprocess
import threading
import time

from . import software_benchmark_runner_v054 as previous
from .repository_sources_v054 import tree_manifest
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_network_v055 import resource_semaphore, validate_actor_ready
from .software_benchmark_owner_ipc_v054 import OwnerClient, wire_json
from .software_benchmark_rootfs_v056 import clone_prepared_rootfs
from .software_benchmark_rootfs_io_v056 import cleanup_episode_rootfs, read_actor_bytes
from .software_benchmark_supervision_v054 import launch_owned, stop_owned
from .storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v056-public-test-episode-deadline-r1"
COMMAND_SECONDS = 1800


class DeadlinePublicTestClient(OwnerClient):
    """One IPC operation includes queue/clone/test/cleanup, bounded by hard_at."""

    def __init__(self, socket_path, identity, *, hard_at, guard_path, clock=time.monotonic):
        if (identity.get("version") != VERSION or not math.isfinite(float(hard_at))
                or not Path(socket_path).is_absolute() or not Path(guard_path).is_absolute()):
            raise ValueError("Bind the v056 public-test host and an absolute finite episode deadline")
        super().__init__(socket_path, identity, timeout=1)
        self.hard_at, self.guard_path, self.clock = float(hard_at), Path(guard_path), clock
        self._deadline_lock = threading.Lock()
        self.last_admission = None

    def call(self, operation, **arguments):
        with self._deadline_lock:
            if operation != "run_public_tests":
                raise ValueError("The public-test channel cannot invoke model or hidden grading operations")
            guard = json.loads(self.guard_path.read_bytes())
            if guard.get("claim_id") != self.identity.get("claim_id"):
                raise ValueError("Public-test IPC and host deadline belong to different episodes")
            remaining = self.hard_at - self.clock()
            if guard.get("stop_requested") or remaining <= 0:
                raise TimeoutError("Episode hard boundary closed before public-test IPC dispatch")
            self.timeout = remaining
            self.last_admission = {"hard_at": self.hard_at, "remaining_seconds": remaining,
                                   "socket_timeout_seconds": remaining, "fixed_1860_cap": False}
            # Original sequence/peer authentication and permanent failure poison
            # remain intact. A timeout never reconnects or replays the operation.
            return super().call(operation, **arguments)


class PublicTestRunner:
    """Source-provider callback used explicitly by the v056 managed assembly."""

    def __init__(self, *, socket_path, identity, hard_at, guard_path, output):
        self.client = DeadlinePublicTestClient(socket_path, identity, hard_at=hard_at,
                                               guard_path=guard_path)
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.number = 0
        write_new(self.output / "binding.json", {"version": VERSION,
            "socket_path": str(socket_path), "identity": identity, "hard_at": hard_at,
            "guard_path": str(guard_path), "command_limit_seconds": COMMAND_SECONDS,
            "fixed_1860_cap": False, "automatic_retry": False})

    def __call__(self, *, files, entry_metadata, task, run_root):
        self.number += 1
        bundle = write_new(self.output / f"input-{self.number:04d}.json",
                           {"files": files, "entry_metadata": entry_metadata})
        started = time.monotonic()
        record = {"version": VERSION, "task_id": task["task_id"], "bundle": bundle,
                  "started_monotonic": started, "automatic_retry": False,
                  "command_limit_seconds": COMMAND_SECONDS, "hidden_grading": False}
        try:
            result = self.client.call("run_public_tests", bundle=bundle)
            record["status"] = "returned"
            return result
        except Exception as error:
            record.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)})
            raise
        finally:
            record.update(ended_monotonic=time.monotonic(), admission=self.client.last_admission)
            write_new(self.output / f"rpc-{self.number:04d}.json", record)


def bind_public_test_runner(prepared, *, socket_path, identity, hard_at, guard_path, output):
    callback = PublicTestRunner(socket_path=socket_path, identity=identity, hard_at=hard_at,
                                guard_path=guard_path, output=output)
    prepared.source_provider.runner = callback
    prepared.world.source_provider = prepared.source_provider
    return callback


class PublicTests(previous.PublicTests):
    """New host namespace; all test child lifetimes still end at the episode hard limit."""

    def __init__(self, episode, config, resources, root):
        super().__init__(episode, config, resources, root)
        self.identity.update(version=VERSION, command_limit_seconds=COMMAND_SECONDS,
                             ipc_budget_policy="remaining_episode_hard_deadline")

    def run(self, bundle_ref):
        self.number += 1
        output = self.root / ("public-test-" + str(self.number))
        output.mkdir()
        phases = {"queued_at": time.monotonic(), "episode_hard_at": self.episode.hard_at,
                  "command_limit_seconds": COMMAND_SECONDS}
        try:
            with resource_semaphore(ROOT / "runs/software-benchmark-v056/resource-locks",
                    name="public_tests", capacity=8, deadline=self.episode.hard_at,
                    cancelled=lambda: self.episode.guard["stop_requested"]):
                phases["capacity_acquired_at"] = time.monotonic()
                return self._run_isolated(bundle_ref, output, phases)
        except Exception as error:
            phases["error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        finally:
            phases["returned_or_failed_at"] = time.monotonic()
            write_new(output / "phase-times.json", {"version": VERSION, **phases})

    def _run_isolated(self, bundle_ref, output, phases):
        phases["clone_started_at"] = time.monotonic()
        clone = clone_prepared_rootfs(self.config["rootfs_environment"], output / "actor")
        actor = Path(clone["rootfs"])
        bundle = json.loads(checked(bundle_ref).read_bytes())
        subprocess.run(["sudo", "-n", "/usr/bin/python3",
            str(ROOT / "tools/prepare_public_tree_replacement_v056.py"),
            "--manifest", clone["rootfs_manifest"], "--sha256", clone["rootfs_manifest_sha256"]],
            check=True, capture_output=True, text=True)
        previous.replace_public_tree(actor / "testbed", bundle, output / "candidate-tree")
        phases["clone_ready_at"] = time.monotonic()
        entry = self.config["public_test_entry"]
        if entry["source"] != "public_repository" or entry["cwd"] != "/testbed" or not entry["admitted"]:
            raise ValueError("Only the independently admitted public test entry is available")
        ordinal, suffix = self.number, ""
        while ordinal:
            ordinal, letter = divmod(ordinal - 1, 26)
            suffix = chr(ord("a") + letter) + suffix
        role = "publictest" + suffix
        with (self.episode.root / "scope-registry.lock").open("a") as guard_lock:
            fcntl.flock(guard_lock, fcntl.LOCK_EX)
            guard = json.loads(self.episode.guard_path.read_bytes())
            remaining = self.episode.hard_at - time.monotonic()
            if guard["stop_requested"] or remaining <= 0:
                raise TimeoutError("Episode ended before public-test process dispatch")
            process, scope = launch_owned([
                str(ROOT / "tools/run_native_worker_mapped_v056.sh"), "--rootfs", str(actor),
                "--stdlib", self.config["stdlib"], "--environment-manifest", clone["environment_manifest"]],
                claim_id=self.episode.claim_id, role=role, resources=self.resources,
                runtime_seconds=remaining, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=(output / "worker.stderr").open("xb"))
            scopes = json.loads(self.episode.registry.read_bytes())
            scopes.append(scope)
            atomic_write(self.episode.registry, json_bytes(scopes))
        self.children.append((process, scope))
        try:
            ready = previous.read_frame(process.stdout,
                timeout=max(.01, min(120, self.episode.hard_at - time.monotonic())))
            validate_actor_ready(ready)
            write_new(output / "worker-ready.json", ready)
            phases["worker_ready_at"] = time.monotonic()
            remaining = self.episode.hard_at - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Episode ended before the public command could begin")
            command_timeout = min(COMMAND_SECONDS, remaining)
            command = " ".join(shlex.quote(value) for value in entry["argv"])
            command += " > /tmp/v056-public-stdout 2> /tmp/v056-public-stderr"
            phases.update(command_dispatched_at=time.monotonic(), command_timeout_seconds=command_timeout)
            process.stdin.write(wire_json({"id": 1, "tool": "terminal",
                "action": {"command": command, "timeout": command_timeout}}))
            process.stdin.flush()
            observed = previous.read_frame(process.stdout,
                timeout=max(.01, min(command_timeout + 5, self.episode.hard_at - time.monotonic())))
            phases["command_returned_at"] = time.monotonic()
            code = observed["observation"].get("exit_code")
            process.stdin.write(wire_json({"id": 2, "op": "close"}))
            process.stdin.flush()
            previous.read_frame(process.stdout,
                timeout=max(.01, min(10, self.episode.hard_at - time.monotonic())))
        finally:
            phases["stop_started_at"] = time.monotonic()
            stopped = stop_owned(scope)
            process.wait(timeout=20)
            phases["quiet_at"] = time.monotonic()
        stdout = read_actor_bytes(actor, "tmp/v056-public-stdout")
        stderr = read_actor_bytes(actor, "tmp/v056-public-stderr")
        stdout_ref, stderr_ref = write_new(output / "stdout.bin", stdout), write_new(output / "stderr.bin", stderr)
        quiescence = write_new(output / "quiescence.json", {**stopped, "outer_launcher_reaped": True})
        execution = {"executed": True, "command_executed": True, "returncode": code,
            "scope": "public_repository_tests", "hidden_grader_called": False,
            "input_tree_sha256": tree_manifest(bundle["files"], bundle["entry_metadata"])["tree_sha256"],
            "technical_unknown": code is None, "common_resource_slice": self.resources["slice"]}
        receipt = write_new(output / "execution.json", {**execution, "input_bundle": bundle_ref,
            "stdout": stdout_ref, "stderr": stderr_ref, "public_entry": entry,
            "worker_ready": ready, "terminal_response": observed})
        if code is not None:
            phases["cleanup_started_at"] = time.monotonic()
            execution["temporary_rootfs_cleanup"] = cleanup_episode_rootfs(actor, self.root,
                reference(clone["rootfs_manifest"]), quiescence,
                [bundle_ref, stdout_ref, stderr_ref, receipt])
            phases["cleanup_finished_at"] = time.monotonic()
        return {"execution": execution, "groups": {"repository_tests": {
            "executed": True, "passed": code == 0, "status": "passed" if code == 0 else "failed",
            "tests": [], "execution": execution}}, "passed": code == 0, "tests": [],
            "output": (stdout + b"\n" + stderr).decode("utf-8", errors="replace")}
