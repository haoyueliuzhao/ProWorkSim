"""Executable one-slot host runner. Preparation slots are distinct from formal evaluation."""
from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
from pathlib import Path
import selectors
import shlex
import shutil
import socketserver
import subprocess
import threading
import time
from types import SimpleNamespace

from .repository_sources_v054 import RepositorySources, capture_repository, tree_manifest
from .software_benchmark_candidates_v054 import checked, materialize_tree, reference, write_new
from .software_benchmark_episode_v054 import Episode
from .software_benchmark_gpu_lease_v054 import GpuLease
from .software_benchmark_lease_handoff_v054 import LeaseHandoff
from .software_benchmark_native_closure_v054 import lock_native_candidate, lock_project_candidates
from .software_benchmark_native_rootfs_v054 import clone_prepared_rootfs
from .software_benchmark_owner_ipc_v054 import OwnerClient, wire_json
from .software_benchmark_resources_v054 import create_episode_resources, release_episode_resources
from .software_benchmark_ref_deployment_v054 import RefPortReservation
from .software_benchmark_rootfs_io_v054 import cleanup_episode_rootfs, read_actor_bytes
from .software_benchmark_supervision_v054 import launch_owned, start_watchdog, stop_owned
from .storage import atomic_write, digest, json_bytes

ROOT = Path(__file__).resolve().parents[2]
VERSION = "software-benchmark-single-slot-runner-v054"


def wait_file(path, process, *, timeout=300):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if Path(path).is_file():
            return json.loads(Path(path).read_text())
        if process.poll() is not None:
            raise RuntimeError("Preparation process exited before ready: " + str(path))
        time.sleep(0.1)
    raise TimeoutError("Preparation readiness timed out: " + str(path))


def read_frame(reader, timeout=60):
    data = bytearray()
    deadline = time.monotonic() + timeout
    with selectors.DefaultSelector() as selector:
        selector.register(reader.fileno(), selectors.EVENT_READ)
        while time.monotonic() < deadline:
            if not selector.select(max(0, deadline - time.monotonic())):
                break
            block = os.read(reader.fileno(), 65536)
            if not block:
                raise RuntimeError("Native worker exited before a complete frame")
            data.extend(block)
            if b"\n" in data:
                return json.loads(data.split(b"\n", 1)[0])
            if len(data) > 16 * 1024**2:
                raise ValueError("Native worker response exceeded the complete frame limit")
    raise TimeoutError("Native worker frame timed out")


def replace_public_tree(worktree, bundle, staging):
    """Replace candidate payload while retaining only admitted nested Git controls."""
    from .software_benchmark_gitlinks_v054 import NESTED_GIT_CONTROL, discover_gitlinks
    links = discover_gitlinks(worktree) if (worktree / ".gitmodules").is_file() else []
    saved = None
    if links:
        saved = subprocess.run([
            os.sys.executable, "-I", "-c", NESTED_GIT_CONTROL, "stage", str(worktree),
            json.dumps([item["path"] for item in links])], check=True,
            capture_output=True, text=True).stdout.strip()
    try:
        for child in worktree.iterdir():
            if child.name != ".git":
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        materialize_tree(bundle["files"], bundle["entry_metadata"], staging)
        for child in staging.iterdir():
            shutil.move(str(child), worktree / child.name)
    finally:
        if saved is not None:
            subprocess.run([os.sys.executable, "-I", "-c", NESTED_GIT_CONTROL,
                            "restore", str(worktree), saved], check=True)


class HostEpisode(Episode):
    """The supervisor stays outside writers; numerical window operations use attested IPC."""
    def enter_remote(self, client, *, ref_seed=None):
        if self.phase != "claimed" or {row["role"] for row in self.scopes} != {"actor", "controller", "model"}:
            raise ValueError("A complete fresh scope inventory is required")
        self.started = time.monotonic()
        self.soft_at, self.hard_at = self.started + 5400, self.started + 6000
        write_new(self.root / "entered.json", {"claim_id": self.claim_id, "slot": self.slot,
                  "started": self.started, "soft_at": self.soft_at, "hard_at": self.hard_at,
                  "resume_or_resample_permitted": False})
        self.phase = "entering"
        self._save()
        self.registry = self.root / "scope-registry.json"
        atomic_write(self.registry, json_bytes(self.scopes))
        self.watchdog, self.quiescence_path = start_watchdog({
            "claim_id": self.claim_id, "scopes": self.scopes, "hard_at": self.hard_at,
            "guard_path": str(self.guard_path), "scope_registry": str(self.registry),
        }, self.root)
        if self.slot["arm"] == "REF":
            if ref_seed != self.slot["seed"]:
                raise ValueError("REF seed differs from the planned slot")
            begun = {"seed": ref_seed, "window_id": None}
        else:
            if not self.synthetic and (
                    client.identity.get("actual_CalibrationActor") is not True
                    or client.identity.get("original_generate_native") is not True
                    or client.identity.get("programmed_fixture_only") is not False
                    or client.identity.get("capacity_smoke_only") is not False):
                raise ValueError("Formal runner requires the unchanged real model owner service")
            claim = json.loads((self.root / "claim.json").read_text())
            begun = client.call("begin", slot=self.slot, claim_id=self.claim_id,
                                started=self.started, authorization=claim["authorization"])
        write_new(self.root / "seed.json", begun)
        self.phase = "running"
        self._save()
        return {"claim_id": self.claim_id, "started": self.started, "soft_at": self.soft_at,
                "hard_at": self.hard_at, "guard_path": str(self.guard_path), **begun}

    def accept_quiescence(self):
        if hasattr(self, "registry"):
            self.scopes = json.loads(self.registry.read_text())
        return super().accept_quiescence()


class PublicTests:
    """Host-only managed run_tests callback; no public bash tool is added."""
    def __init__(self, episode, config, resources, root):
        self.episode, self.config, self.resources, self.root = episode, config, resources, root
        self.number, self.children = 0, []
        self.identity = {"version": "v054-public-test-host-v1", "claim_id": episode.claim_id}

    def run(self, bundle_ref):
        self.number += 1
        output = self.root / ("public-test-" + str(self.number))
        output.mkdir()
        clone = clone_prepared_rootfs(self.config["rootfs_environment"], output / "actor")
        actor = Path(clone["rootfs"])
        bundle = json.loads(checked(bundle_ref).read_text())
        # All writes happen in a fresh test clone, while its processes are absent.
        worktree = actor / "testbed"
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
                [str(ROOT / "tools/run_native_worker_mapped_v054.sh"),
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


def control_server(public_tests, socket_path):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            request = json.loads(self.rfile.readline(1024**2))
            try:
                if (request["operation"] != "run_public_tests"
                        or request["identity_sha256"] != digest(json_bytes(public_tests.identity))):
                    raise ValueError("Only this episode's fixed public tests are exposed")
                result = public_tests.run(request["arguments"]["bundle"])
                body = {"result": result}
            except BaseException as error:
                body = {"error": {"type": type(error).__name__, "message": str(error)}}
            self.wfile.write(wire_json({"sequence": request["sequence"],
                "identity_sha256": digest(json_bytes(public_tests.identity)), **body}))
    server = socketserver.UnixStreamServer(str(socket_path), Handler)
    os.chmod(socket_path, 0o600)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def score_requests(config, candidate_ref, output):
    """Only prepare host-only official requests after candidate lock; no actor feedback."""
    lock = json.loads(checked(candidate_ref).read_text())
    endpoints = {"code": lock} if config["arm"] != "PROJECT" else {
        "code": json.loads(checked(lock["terminal_code"]).read_text()),
        **({"delivery": json.loads(checked(lock["last_legal_delivery"]).read_text())}
           if lock["last_legal_delivery"] else {}),
    }
    requests = []
    for endpoint, selected in endpoints.items():
        patch = selected["patch_receipt"]
        if "path" in patch:
            patch = json.loads(checked(patch).read_text())
        request = {**config["scorer_request_base"], "instance_id": config["public_task"]["instance_id"],
                   "arm": config["arm"], "endpoint": endpoint, "attempt": 1,
                   "patch": patch["patch"], "baseline_tree_sha256": patch["base_tree_sha256"],
                   "candidate_tree_sha256": patch["candidate_tree_sha256"],
                   "episode_candidate_lock": candidate_ref,
                   "config_sha256": config["configuration"]["sha256"],
                   "preparation_only": config["preparation_only"], "actor_feedback": False}
        if config["arm"] != "PROJECT":
            request["native_candidate_lock"] = candidate_ref
        requests.append(write_new(output / ("official-" + endpoint + "-request.json"), request))
    return requests


def _run(config, output, leases):
    synthetic = config["preparation_only"]
    if not synthetic:
        if (config.get("all_solver_admissions_passed") is not True
                or config["slots"]["sha256"]
                != "55899d0b83a5bab1082bccb50496fb6c1d7111ecb951fc4d61c222be19d88676"):
            raise ValueError("Formal runner requires the original frozen 1,500-slot panel and admission")
        public = config["public_tasks"]
        if public["sha256"] != "65d130536d04fda752b6ab36534ec657a8cd9bb0243b36067a1eb45413245aaf":
            raise ValueError("Formal task text must come from the fixed public projection")
        rows = json.loads(checked(public).read_text())
        matching = [row for row in rows if row["instance_id"] == config["public_task"]["instance_id"]]
        if matching != [config["public_task"]]:
            raise ValueError("Formal problem or repository identity was rewritten")
        if config["arm"] == "PROJECT":
            registry = json.loads(checked(config["public_test_registry"]).read_text())
            entries = [row for row in registry["entries"]
                       if row["instance_id"] == config["public_task"]["instance_id"]]
            if (registry.get("planned_tasks") != 500 or len(entries) != 1
                    or entries[0] != config["public_test_entry"] or not entries[0]["admitted"]
                    or entries[0]["baseline_mapping"] != config["scorer_request_base"]["baseline_mapping"]):
                raise ValueError("Formal PROJECT needs its fixed complete-panel public test entry")
        from .software_benchmark_source_freeze_v054 import verify_sources
        from .software_benchmark_service_factory_v054 import condition_reference, validate_service
        if config["configuration"] != condition_reference(config["arm"]):
            raise ValueError("Only the frozen arm condition can enter a formal slot")
        condition = json.loads(checked(config["configuration"]).read_text())
        verify_sources(condition["source_manifest"])
        service = json.loads(checked(config["model_service"]).read_text())
        validate_service(service, config["arm"])
        if (config["model_command"] != service["command"]
                or config["gpu_uuid"] != service["gpu_uuid"]):
            raise ValueError("Runner service differs from its factory-built declaration")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    if config.get("lazy_native_preparation"):
        try:
            from .software_benchmark_native_lazy_v054 import ensure_native_instance
            prepared = ensure_native_instance(
                instance_id=config["public_task"]["instance_id"],
                mapping_reference=config["scorer_request_base"]["baseline_mapping"],
                cache_root=Path(config["lazy_native_preparation"]["cache_root"]),
                stdlib=Path(config["stdlib"]), public_tasks_reference=config["public_tasks"],
                docker_socket=config["scorer_request_base"]["docker_socket"])
            config = {**config, "rootfs_environment": prepared["rootfs_environment"],
                      "environment": reference(prepared["environment"])}
            write_new(output / "native-preparation.json", prepared)
        except BaseException as error:
            result = {"version": VERSION, "slot_id": config["slot_id"],
                      "preparation_only": synthetic, "status": "preparation_not_ready",
                      "slot_claimed": False, "entered": False, "model_calls": 0, "GPU_loads": 0,
                      "error": {"type": type(error).__name__, "message": str(error)}}
            write_new(output / "result.json", result)
            return result
    if not synthetic:
        reason = "gpu_lease_busy"
        try:
            leases.append(GpuLease(config["gpu_uuid"]))
            write_new(output / "gpu-lease.json", leases[-1].receipt)
            if config["arm"] == "REF":
                reason = "ref_port_busy"
                leases.append(RefPortReservation())
                reservation = write_new(output / "ref-port-reservation.json", leases[-1].receipt)
                config = {**config, "model_command": [*config["model_command"],
                          "--host-preclaim", reservation["path"]]}
            reason = "gpu_capacity_gate"
            from tools.prepare_model_capacity_v054 import eligible, gpu_rows
            eligible_cards = eligible(gpu_rows(), "REF" if config["arm"] == "REF" else "MATCH")
            if not any(card["uuid"] == config["gpu_uuid"] for card in eligible_cards):
                raise BlockingIOError("Original free-memory capacity gate is not currently met")
        except (BlockingIOError, OSError) as error:
            if not isinstance(error, BlockingIOError) and error.errno not in {errno.EADDRINUSE, errno.EAGAIN}:
                raise
            result = {"version": VERSION, "slot_id": config["slot_id"], "preparation_only": False,
                      "status": "resource_not_ready", "reason_code": reason,
                      "slot_claimed": False, "entered": False, "model_calls": 0, "GPU_loads": 0,
                      "error": {"type": type(error).__name__, "message": str(error)}}
            write_new(output / "result.json", result)
            return result
    episode = HostEpisode(
        config["slots"], config["slot_id"], binding={"configuration": config["configuration"],
        "environment": config["environment"], "owner": config["owner_admission"]},
        authorization=config.get("authorization"), synthetic=synthetic,
        synthetic_claim_root=output / "synthetic-claims" if synthetic else None)
    if (config["arm"] != episode.slot["arm"]
            or config["seed"] != episode.slot["seed"]
            or config["public_task"]["instance_id"] != episode.slot["instance_id"]):
        raise ValueError("Task/arm differs from claimed slot")
    clone = clone_prepared_rootfs(config["rootfs_environment"], output / "actor")
    actor = Path(clone["rootfs"])
    task = config["public_task"]
    environment = json.loads(checked(config["environment"]).read_text())
    public_environment = json.loads(Path(clone["environment_manifest"]).read_text())
    if public_environment["image_id"] != environment["image"]["image_id"]:
        raise ValueError("Public source clone differs from this task's admitted Actor image")
    manifest = capture_repository(
        actor / "testbed", output / "public-source", task_id=task["instance_id"],
        problem_statement=task["problem_statement"], source_identity={
            **{key: task[key] for key in ("instance_id", "repo", "base_commit")},
            "dataset_revision": config["dataset_revision"]}, gitlinks=environment.get("gitlinks"))
    baseline = reference(manifest.parent / "initial-tree.json")
    config = {**config, "public_test_entry": {
        **config["public_test_entry"], "captured_source_manifest": reference(manifest)}}
    resources = create_episode_resources(episode.claim_id, output)
    processes, owner_client, server, public_socket, handoff = [], None, None, None, None
    result = {"version": VERSION, "slot_id": config["slot_id"], "preparation_only": synthetic,
              "formal_execution_authorized": not synthetic, "counted_as_model_result": False,
              "formal_generation_episode": not synthetic,
              "slot_claimed": True, "entered": False,
              "model_calls": 0 if synthetic else None, "status": "starting"}
    try:
        # Service fallback includes bounded preparation; the separately armed
        # episode watchdog still enforces exactly 6,000 seconds from entry.
        service_lifetime = 6000 + config.get("model_start_timeout", 600) + 180
        worker, actor_scope = launch_owned(
            [str(ROOT / "tools/run_native_worker_mapped_v054.sh"), "--rootfs", str(actor),
             "--stdlib", config["stdlib"], "--environment-manifest", clone["environment_manifest"],
             *(["--preparation-only"] if synthetic else [])],
            claim_id=episode.claim_id, role="actor", resources=resources,
            runtime_seconds=service_lifetime,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=(output / "worker.stderr").open("xb"))
        processes.append((worker, actor_scope))
        episode.register_scope(actor_scope)
        ready = read_frame(worker.stdout)
        write_new(output / "worker-ready.json", ready)
        if not synthetic:
            lease_path = ROOT / "runs/v054-gpu" / (episode.claim_id[:12] + "-lease.sock")
            handoff = LeaseHandoff(lease_path, leases)
            config = {**config, "model_command": [*config["model_command"], "--host-lease", str(lease_path)]}
        model, model_scope = launch_owned(
            config["model_command"], claim_id=episode.claim_id, role="model",
            runtime_seconds=service_lifetime,
            stdin=subprocess.DEVNULL, stdout=(output / "model.stdout").open("xb"),
            stderr=(output / "model.stderr").open("xb"))
        processes.append((model, model_scope))
        episode.register_scope(model_scope)
        wait_file(config["model_ready"], model, timeout=config.get("model_start_timeout", 600))
        if handoff is not None and (handoff.error is not None or not handoff.sent):
            raise RuntimeError("Model did not inherit the physical/global deployment leases")
        identity = json.loads(Path(config["model_identity"]).read_text())
        if config["arm"] != "REF":
            owner_client = OwnerClient(config["model_socket"], identity)
        tests = PublicTests(episode, config, resources, output)
        ipc_directory = ROOT / "runs/software-benchmark-v054/ipc"
        ipc_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        public_socket = ipc_directory / (episode.claim_id + ".sock")
        server, thread = control_server(tests, public_socket)
        child_config = {**{key: value for key, value in config.items() if key != "scorer_request_base"},
                        "source_manifest": str(manifest), "model_identity_value": identity,
                        "public_test_socket": str(public_socket),
                        "public_test_identity": tests.identity, "output": str(output),
                        "ready": str(output / "worker-ready.json"), "start": str(output / "start.json")}
        write_new(output / "controller-config.json", child_config)
        controller, controller_scope = launch_owned([
            str(ROOT / "tools/run_native_sdk_controller_v054.sh"), config["sdk_runtime"], str(actor),
            str(ROOT / "tools/run_benchmark_controller_v054.py"),
            "--config", str(output / "controller-config.json")],
            claim_id=episode.claim_id, role="controller", resources=resources,
            stdin=worker.stdout, stdout=worker.stdin,
            stderr=(output / "controller.stderr").open("xb"))
        processes.append((controller, controller_scope))
        episode.register_scope(controller_scope)
        wait_file(output / "controller-ready.json", controller, timeout=120)
        start = episode.enter_remote(owner_client, ref_seed=episode.slot["seed"])
        result["entered"] = True
        write_new(output / "start.json", start)
        returned = controller.wait(timeout=max(1, episode.hard_at - time.monotonic()) + 20)
        if returned:
            raise RuntimeError("Controller failed; see retained receipt/ledger and stderr")
        child = json.loads((output / "controller-result.json").read_text())
        if child["status"] != "closed":
            raise RuntimeError("Controller did not close normally")
        if owner_client is not None:
            write_new(output / "owner-finish.json", owner_client.call("finish", entries=[child]))
        episode.close_dispatch("controller_returned_and_owner_guard_closed")
        episode.watchdog.wait(timeout=40)
        for process, _ in processes + tests.children:
            process.wait(timeout=15)
        episode.accept_quiescence()
        if config["arm"] == "PROJECT":
            from .software_benchmark_world_v054 import SoftwareCollaborationWorld
            world = SoftwareCollaborationWorld(output / "managed-world/world")
            provider = RepositorySources(manifest)
            world.source_provider = provider
            prepared = SimpleNamespace(world=world, case=world._software()["case"], source_provider=provider)
            candidate = lock_project_candidates(episode, prepared, output=output / "candidates")
        else:
            candidate = lock_native_candidate(
                episode, baseline_reference=baseline, public_worktree=actor / "testbed", public_task=task,
                dataset_revision=config["dataset_revision"], output=output / "candidates")
        requests = score_requests(config, candidate, output)
        cleanup_proof = write_new(output / "cleanup-quiescence.json", {
            **json.loads(episode.quiescence_path.read_text()), "outer_launcher_reaped": True})
        cleanup = cleanup_episode_rootfs(actor, output, reference(clone["rootfs_manifest"]),
            cleanup_proof, [candidate, baseline, reference(manifest),
                            reference(output / "controller-result.json"), *requests])
        result.update(status="closed_candidate_and_official_requests_ready", candidate=candidate,
                      official_requests=requests, controller_result=reference(output / "controller-result.json"),
                      quiescence=reference(episode.quiescence_path), resource_slice=resources,
                      public_test_calls=tests.number, hidden_feedback_to_actor=False,
                      temporary_rootfs_cleanup=cleanup)
    except BaseException as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)},
                      entered=(episode.root / "entered.json").exists(), automatic_retry=False)
        if hasattr(episode, "watchdog") and episode.watchdog.poll() is None:
            episode.close_dispatch("host_runner_exception")
            episode.watchdog.wait(timeout=40)
        raise
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if public_socket is not None:
            public_socket.unlink(missing_ok=True)
        for process, scope in reversed(processes):
            stop_owned(scope)
            process.wait(timeout=20)
        if handoff is not None:
            handoff.close()
        try:
            result["resource_release"] = release_episode_resources(resources)
        finally:
            write_new(output / "result.json", result)
    return result


def run(config, output):
    """Hold physical GPU/global and REF singleton leases across the entire episode."""
    leases = []
    try:
        return _run(config, output, leases)
    except BaseException as error:
        output = Path(output).resolve()
        if not (output / "result.json").exists():
            from .software_benchmark_episode_v054 import DEFAULT_CLAIMS
            claim = DEFAULT_CLAIMS / digest(config["slot_id"].encode())
            output.mkdir(parents=True, exist_ok=True)
            write_new(output / "result.json", {
                "version": VERSION, "slot_id": config["slot_id"],
                "preparation_only": config["preparation_only"], "status": "technical_unknown",
                "slot_claimed": claim.exists(), "entered": (claim / "entered.json").exists(),
                "automatic_retry": False, "error": {"type": type(error).__name__, "message": str(error)}})
        raise
    finally:
        for lease in reversed(leases):
            lease.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(json.loads(args.config.read_text()), args.output)
    print(json.dumps({key: result[key] for key in ("status", "slot_id", "preparation_only")}))
    return 0 if result["status"] == "closed_candidate_and_official_requests_ready" else 75


if __name__ == "__main__":
    raise SystemExit(main())
