"""Independent API-backed host episode; no GPU owner, local proxy or old claim."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import subprocess
import threading
import time
from types import SimpleNamespace

from . import software_benchmark_runner_v054 as old
from .repository_sources_v054 import RepositorySources, capture_repository
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_episode_v054 import Episode
from .software_benchmark_native_closure_v054 import lock_native_candidate, lock_project_candidates
from .software_benchmark_rootfs_v055 import clone_prepared_rootfs
from .software_benchmark_resources_v054 import create_episode_resources, release_episode_resources
from .software_benchmark_rootfs_io_v055 import cleanup_episode_rootfs
from .software_benchmark_supervision_v054 import claim_nonce, launch_owned, start_watchdog, stop_owned
from .software_benchmark_network_v055 import (
    direct_environment_command, validate_actor_ready,
)
from .software_benchmark_public_tests_v055 import PublicTests
from .storage import atomic_write, digest, json_bytes

ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = ROOT / "runs/software-benchmark-v055"
VERSION = "v055-deepseek-episode-result-r1"
PUBLIC_SHA256 = "65d130536d04fda752b6ab36534ec657a8cd9bb0243b36067a1eb45413245aaf"


class ApiEpisode(Episode):
    """Reuse proven watchdog/candidate mechanics with separate API-only claims."""

    def __init__(self, config):
        slots = json.loads(checked(config["slots"]).read_bytes())
        matches = [row for row in slots["slots"] if row["slot_id"] == config["slot_id"]]
        permit = json.loads(checked(config["authorization"]).read_bytes())
        if (len(matches) != 1 or permit.get("execution_authorized") is not True
                or permit.get("slots_sha256") != config["slots"]["sha256"]
                or config["slot_id"] not in permit.get("slot_ids", [])):
            raise ValueError("A frozen v055 slot and explicit API budget authorization are required")
        self.slot = copy.deepcopy(matches[0])
        if (self.slot["arm"] != config["arm"] or self.slot["condition_id"] != config["condition_id"]
                or self.slot["instance_id"] != config["public_task"]["instance_id"]):
            raise ValueError("API episode identity differs from the planned slot")
        self.synthetic, self.clock = False, time.monotonic
        claims = RUN_ROOT / "episode-claims"
        claims.mkdir(parents=True, exist_ok=True)
        self.root = claims / digest(config["slot_id"].encode())
        self.root.mkdir(exist_ok=False)
        self.claim_id, self.phase = claim_nonce(), "claimed"
        self.lock, self.owner, self.snapshot = threading.RLock(), None, None
        self.scopes, self.started, self.inflight = [], None, None
        self.guard_path = self.root / "watchdog-guard.json"
        self.guard = {"claim_id": self.claim_id, "stop_requested": False, "request_deadline": None}
        write_new(self.root / "claim.json", {"version": VERSION, "claim_id": self.claim_id,
            "slot": self.slot, "slots": config["slots"], "configuration": config["configuration"],
            "authorization": config["authorization"], "resume_or_resample_permitted": False})
        self._save()

    def enter_api(self):
        if self.phase != "claimed" or {row["role"] for row in self.scopes} != {"actor", "controller"}:
            raise ValueError("Both fresh API controller and isolated actor scopes are required")
        self.started = time.monotonic()
        self.soft_at, self.hard_at = self.started + 5400, self.started + 6000
        value = {"claim_id": self.claim_id, "slot": self.slot, "started": self.started,
                 "soft_at": self.soft_at, "hard_at": self.hard_at,
                 "guard_path": str(self.guard_path), "provider_seed_supported": False,
                 "resume_or_resample_permitted": False}
        write_new(self.root / "entered.json", value)
        self.registry = self.root / "scope-registry.json"
        atomic_write(self.registry, json_bytes(self.scopes))
        self.watchdog, self.quiescence_path = start_watchdog({
            "claim_id": self.claim_id, "scopes": self.scopes, "hard_at": self.hard_at,
            "guard_path": str(self.guard_path), "scope_registry": str(self.registry)}, self.root)
        self.phase = "running"
        self._save()
        return value

    def accept_quiescence(self):
        if hasattr(self, "registry"):
            self.scopes = json.loads(self.registry.read_bytes())
        return super().accept_quiescence()




def score_requests(config, candidate_ref, output):
    """Condition identity is part of every request and scorer cache key."""
    lock = json.loads(checked(candidate_ref).read_bytes())
    endpoints = {"code": lock} if config["arm"] != "PROJECT" else {
        "code": json.loads(checked(lock["terminal_code"]).read_bytes()),
        **({"delivery": json.loads(checked(lock["last_legal_delivery"]).read_bytes())}
           if lock["last_legal_delivery"] else {})}
    requests = []
    for endpoint, selected in endpoints.items():
        patch = selected["patch_receipt"]
        if "path" in patch:
            patch = json.loads(checked(patch).read_bytes())
        request = {**config["scorer_request_base"], "instance_id": config["public_task"]["instance_id"],
            "arm": config["arm"], "condition_id": config["condition_id"],
            "thinking": config["thinking"], "slot_id": config["slot_id"],
            "endpoint": endpoint, "attempt": 1, "patch": patch["patch"],
            "baseline_tree_sha256": patch["base_tree_sha256"],
            "candidate_tree_sha256": patch["candidate_tree_sha256"],
            "episode_candidate_lock": candidate_ref,
            "config_sha256": config["configuration"]["sha256"],
            "model": config["model"],
            "receipt_output": str(output / ("official-" + endpoint + "-receipt.json")),
            "preparation_only": False, "actor_feedback": False}
        if config["arm"] != "PROJECT":
            request["native_candidate_lock"] = candidate_ref
        requests.append(write_new(output / ("official-" + endpoint + "-request.json"), request))
    return requests


def validate_config(config):
    if (config.get("version") != "v055-deepseek-slot-config-r1"
            or config.get("preparation_only") is not False
            or config.get("all_solver_admissions_passed") is not True
            or config["public_tasks"]["sha256"] != PUBLIC_SHA256):
        raise ValueError("Only qualified v055 configurations and unchanged public task text are accepted")
    tasks = json.loads(checked(config["public_tasks"]).read_bytes())
    if [row for row in tasks if row["instance_id"] == config["public_task"]["instance_id"]] != [config["public_task"]]:
        raise ValueError("Public task differs from the original complete Verified projection")
    condition = json.loads(checked(config["configuration"]).read_bytes())
    if any(condition[key] != config[key] for key in ("arm", "condition_id", "thinking")):
        raise ValueError("Six-condition identity changed")
    registry = json.loads(checked(config["public_test_registry"]).read_bytes())
    entries = [row for row in registry["entries"] if row["instance_id"] == config["public_task"]["instance_id"]]
    if (registry.get("planned_tasks") != 500 or entries != [config["public_test_entry"]]
            or not entries[0]["admitted"]
            or entries[0]["baseline_mapping"] != config["scorer_request_base"]["baseline_mapping"]):
        raise ValueError("Official baseline/public-test admission differs")
    for item in config["frozen_sources"]:
        checked(item)


def run(config, output):
    validate_config(config)
    output = Path(output).resolve()
    if not output.is_relative_to(RUN_ROOT):
        raise ValueError("v055 episodes require a separate trusted output root")
    output.mkdir(parents=True, exist_ok=False)
    result = {"version": VERSION, "slot_id": config["slot_id"], "condition_id": config["condition_id"],
              "status": "starting", "entered": False, "entered_model": None,
              "automatic_retry": False, "GPU_loads": 0, "hidden_feedback_to_actor": False}
    episode, resources, server, public_socket = None, None, None, None
    processes, tests = [], None
    try:
        from .software_benchmark_prewarm_v054 import qualified_paths
        prepared = qualified_paths(config["public_task"]["instance_id"],
            mapping_reference=config["scorer_request_base"]["baseline_mapping"],
            cache_root=Path(config["lazy_native_preparation"]["cache_root"]))
        config = {**config, "rootfs_environment": prepared["rootfs_environment"],
                  "environment": reference(prepared["environment"])}
        write_new(output / "native-preparation.json", prepared)
        episode = ApiEpisode(config)
        result["slot_claimed"] = True
        clone = clone_prepared_rootfs(config["rootfs_environment"], output / "actor")
        actor, task = Path(clone["rootfs"]), config["public_task"]
        environment = json.loads(checked(config["environment"]).read_bytes())
        public_environment = json.loads(Path(clone["environment_manifest"]).read_bytes())
        if public_environment["image_id"] != environment["image"]["image_id"]:
            raise ValueError("Actor clone differs from the admitted image")
        manifest = capture_repository(actor / "testbed", output / "public-source",
            task_id=task["instance_id"], problem_statement=task["problem_statement"],
            source_identity={**{key: task[key] for key in ("instance_id", "repo", "base_commit")},
                             "dataset_revision": config["dataset_revision"]},
            gitlinks=environment.get("gitlinks"))
        baseline = reference(manifest.parent / "initial-tree.json")
        config = {**config, "public_test_entry": {
            **config["public_test_entry"], "captured_source_manifest": reference(manifest)}}
        resources = create_episode_resources(episode.claim_id, output)
        worker, scope = launch_owned([str(ROOT / "tools/run_native_worker_mapped_v055.sh"),
            "--rootfs", str(actor), "--stdlib", config["stdlib"],
            "--environment-manifest", clone["environment_manifest"]],
            claim_id=episode.claim_id, role="actor", resources=resources, runtime_seconds=6300,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=(output / "worker.stderr").open("xb"))
        processes.append((worker, scope))
        episode.register_scope(scope)
        ready = old.read_frame(worker.stdout)
        write_new(output / "worker-ready.json", ready)
        write_new(output / "network-boundary.json", validate_actor_ready(ready))
        tests = PublicTests(episode, config, resources, output)
        # Keep UNIX paths well below Linux's 108-byte sockaddr_un bound even
        # when the episode/qualification root carries a long revision name.
        ipc = ROOT / "runs/v055-ipc"
        ipc.mkdir(mode=0o700, parents=True, exist_ok=True)
        public_socket = ipc / (episode.claim_id + ".sock")
        server, _ = old.control_server(tests, public_socket)
        child_config = {**{key: value for key, value in config.items() if key != "scorer_request_base"},
            "source_manifest": str(manifest), "public_test_socket": str(public_socket),
            "public_test_identity": tests.identity, "output": str(output),
            "ready": str(output / "worker-ready.json"), "start": str(output / "start.json")}
        write_new(output / "controller-config.json", child_config)
        controller_command = direct_environment_command([
            str(ROOT / "tools/run_native_sdk_controller_v055.sh"), config["sdk_runtime"], str(actor),
            str(ROOT / "tools/run_deepseek_controller_v055.py"),
            "--config", str(output / "controller-config.json")])
        controller, scope = launch_owned(controller_command, claim_id=episode.claim_id,
            role="controller", resources=resources, runtime_seconds=6300,
            stdin=worker.stdout, stdout=worker.stdin, stderr=(output / "controller.stderr").open("xb"))
        processes.append((controller, scope))
        episode.register_scope(scope)
        old.wait_file(output / "controller-ready.json", controller, timeout=120)
        write_new(output / "start.json", episode.enter_api())
        result["entered"] = True
        code = controller.wait(timeout=max(1, episode.hard_at - time.monotonic()) + 20)
        if code:
            raise RuntimeError("DeepSeek controller failed; original ledger/stderr retained")
        child = json.loads((output / "controller-result.json").read_bytes())
        if child["status"] not in {"closed", "budget_exhausted"}:
            raise RuntimeError("DeepSeek controller did not reach a trusted candidate boundary")
        result["entered_model"] = child.get("entered_model")
        result["controller_status"] = child["status"]
        episode.close_dispatch("api_controller_returned")
        episode.watchdog.wait(timeout=40)
        for process, _ in processes + tests.children:
            process.wait(timeout=20)
        episode.accept_quiescence()
        if config["arm"] == "PROJECT":
            from .software_benchmark_world_v054 import SoftwareCollaborationWorld
            world = SoftwareCollaborationWorld(output / "managed-world/world")
            provider = RepositorySources(manifest)
            world.source_provider = provider
            candidate = lock_project_candidates(episode, SimpleNamespace(
                world=world, case=world._software()["case"], source_provider=provider), output=output / "candidates")
        else:
            candidate = lock_native_candidate(episode, baseline_reference=baseline,
                public_worktree=actor / "testbed", public_task=task,
                dataset_revision=config["dataset_revision"], output=output / "candidates")
        requests = score_requests(config, candidate, output)
        proof = write_new(output / "cleanup-quiescence.json", {
            **json.loads(episode.quiescence_path.read_bytes()), "outer_launcher_reaped": True})
        cleanup = cleanup_episode_rootfs(actor, output, reference(clone["rootfs_manifest"]), proof,
            [candidate, baseline, reference(manifest), reference(output / "controller-result.json"), *requests])
        result.update(status="closed", candidate=candidate, scoring_requests=requests,
            controller_result=reference(output / "controller-result.json"),
            public_test_calls=tests.number, quiescence=reference(episode.quiescence_path),
            temporary_rootfs_cleanup=cleanup)
    except Exception as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)})
        if episode is not None and hasattr(episode, "watchdog") and episode.watchdog.poll() is None:
            episode.close_dispatch("api_runner_exception")
            episode.watchdog.wait(timeout=40)
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if public_socket is not None:
            public_socket.unlink(missing_ok=True)
        cleanup_errors = []
        stopped_scopes = []
        for process, scope in reversed(processes):
            try:
                stopped_scopes.append(stop_owned(scope))
                process.wait(timeout=20)
            except Exception as error:
                cleanup_errors.append({"unit": scope["unit"], "error": str(error)})
        if resources is not None:
            try:
                result["resource_release"] = release_episode_resources(resources)
            except Exception as error:
                cleanup_errors.append({"resource_release": str(error)})
        if cleanup_errors:
            result.update(status="technical_unknown", cleanup_errors=cleanup_errors)
        result["finally_stopped_scopes"] = stopped_scopes
        write_new(output / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run(json.loads(args.config.read_bytes()), args.output)
    print(json.dumps({key: result[key] for key in ("status", "slot_id", "condition_id")}))
    return 0 if result["status"] == "closed" else 75


if __name__ == "__main__":
    raise SystemExit(main())
