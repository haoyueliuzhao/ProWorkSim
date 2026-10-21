"""v055 public tests: original semantics with separate clone/helper namespace."""
import fcntl
import json
from pathlib import Path
import shlex
import subprocess
import time
from . import software_benchmark_runner_v054 as old
from .repository_sources_v054 import tree_manifest
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_owner_ipc_v054 import wire_json
from .software_benchmark_rootfs_v055 import clone_prepared_rootfs
from .software_benchmark_rootfs_io_v055 import cleanup_episode_rootfs, read_actor_bytes
from .software_benchmark_supervision_v054 import launch_owned, stop_owned
from .software_benchmark_network_v055 import resource_semaphore, validate_actor_ready
from .storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[2]
read_frame, replace_public_tree = old.read_frame, old.replace_public_tree


class PublicTests(old.PublicTests):
    def run(self, bundle_ref):
        with resource_semaphore(ROOT / "runs/software-benchmark-v055/resource-locks",
                                name="public_tests", capacity=8, deadline=self.episode.hard_at,
                                cancelled=lambda: self.episode.guard["stop_requested"]):
            return self._run_isolated(bundle_ref)

    def _run_isolated(self, bundle_ref):
        self.number += 1
        output = self.root / ("public-test-" + str(self.number))
        output.mkdir()
        clone = clone_prepared_rootfs(self.config["rootfs_environment"], output / "actor")
        actor = Path(clone["rootfs"])
        bundle = json.loads(checked(bundle_ref).read_text())
        # All writes happen in a fresh test clone, while its processes are absent.
        worktree = actor / "testbed"
        subprocess.run(["sudo", "-n", "/usr/bin/python3",
            str(ROOT / "tools/prepare_public_tree_replacement_v055.py"),
            "--manifest", clone["rootfs_manifest"], "--sha256", clone["rootfs_manifest_sha256"]],
            check=True, capture_output=True, text=True)
        replace_public_tree(worktree, bundle, output / "candidate-tree")
        entry = self.config["public_test_entry"]
        if entry["source"] != "public_repository" or entry["cwd"] != "/testbed" or not entry["admitted"]:
            raise ValueError("Managed tests require an independently admitted public entry")
        ordinal, suffix = self.number, ""
        while ordinal:
            ordinal, letter = divmod(ordinal - 1, 26)
            suffix = chr(ord("a") + letter) + suffix
        role = "publictest" + suffix
        with (self.episode.root / "scope-registry.lock").open("a") as guard_lock:
            fcntl.flock(guard_lock, fcntl.LOCK_EX)
            guard = json.loads(self.episode.guard_path.read_text())
            if guard["stop_requested"] or time.monotonic() >= self.episode.hard_at:
                raise RuntimeError("Episode ended before a new public test could start")
            process, scope = launch_owned(
                [str(ROOT / "tools/run_native_worker_mapped_v055.sh"),
                 "--rootfs", str(actor), "--stdlib", self.config["stdlib"],
                 "--environment-manifest", clone["environment_manifest"],
                 *(["--preparation-only"] if self.episode.synthetic else [])],
                claim_id=self.episode.claim_id, role=role, resources=self.resources,
                runtime_seconds=max(1, self.episode.hard_at - time.monotonic()),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=(output / "worker.stderr").open("xb"))
            scopes = json.loads(self.episode.registry.read_text())
            scopes.append(scope)
            atomic_write(self.episode.registry, json_bytes(scopes))
        self.children.append((process, scope))
        try:
            ready = read_frame(process.stdout)
            if ready.get("type") != "ready":
                raise ValueError("Fresh public test worker did not initialize")
            validate_actor_ready(ready)
            command = " ".join(shlex.quote(value) for value in entry["argv"])
            command += " > /tmp/v054-public-stdout 2> /tmp/v054-public-stderr"
            process.stdin.write(wire_json({"id": 1, "tool": "terminal", "action": {
                "command": command, "timeout": min(1800, max(1, self.episode.hard_at - time.monotonic()))}}))
            process.stdin.flush()
            observed = read_frame(process.stdout, timeout=min(1805, self.episode.hard_at - time.monotonic()))
            code = observed["observation"].get("exit_code")
            process.stdin.write(wire_json({"id": 2, "op": "close"}))
            process.stdin.flush()
            read_frame(process.stdout, timeout=10)
        finally:
            stopped = stop_owned(scope)
            process.wait(timeout=20)
        # Any unsafe/oversized output raises before cleanup and preserves the clone.
        stdout = read_actor_bytes(actor, "tmp/v054-public-stdout")
        stderr = read_actor_bytes(actor, "tmp/v054-public-stderr")
        stdout_ref = write_new(output / "stdout.bin", stdout)
        stderr_ref = write_new(output / "stderr.bin", stderr)
        quiescence = write_new(output / "quiescence.json", {**stopped, "outer_launcher_reaped": True})
        execution = {"executed": True, "command_executed": True, "returncode": code,
                     "scope": "public_repository_tests", "hidden_grader_called": False,
                     "input_tree_sha256": tree_manifest(bundle["files"], bundle["entry_metadata"])["tree_sha256"],
                     "technical_unknown": code is None, "common_resource_slice": self.resources["slice"]}
        execution_ref = write_new(output / "execution.json", {
            **execution, "input_bundle": bundle_ref, "stdout": stdout_ref, "stderr": stderr_ref,
            "public_entry": entry, "worker_ready": ready, "terminal_response": observed})
        if code is not None:
            cleanup = cleanup_episode_rootfs(actor, self.root, reference(clone["rootfs_manifest"]),
                quiescence, [bundle_ref, stdout_ref, stderr_ref, execution_ref])
            execution["temporary_rootfs_cleanup"] = cleanup
        return {"execution": execution,
                "groups": {"repository_tests": {"executed": True, "passed": code == 0,
                    "status": "passed" if code == 0 else "failed", "tests": [], "execution": execution}},
                "passed": code == 0, "tests": [],
                "output": (stdout + b"\n" + stderr).decode("utf-8", errors="replace")}

