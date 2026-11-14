"""Once-only Qwen REF episodes with independent claims and external model residency."""
from __future__ import annotations

import argparse
import copy
import ipaddress
import json
from pathlib import Path
import subprocess
import threading
import time
from urllib.parse import urlparse

from . import software_benchmark_runner_v054 as host
from .repository_sources_v054 import capture_repository
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_episode_v054 import Episode
from .software_benchmark_native_closure_v054 import lock_native_candidate
from .software_benchmark_network_v055 import direct_environment_command, validate_actor_ready
from .software_benchmark_ref_budget_v056 import validate_condition
from .software_benchmark_resources_v054 import create_episode_resources, release_episode_resources
from .software_benchmark_rootfs_v056 import clone_prepared_rootfs
from .software_benchmark_rootfs_io_v056 import cleanup_episode_rootfs
from .software_benchmark_supervision_v054 import claim_nonce, launch_owned, start_watchdog, stop_owned
from .storage import atomic_write, digest, json_bytes

ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = ROOT / "runs/software-benchmark-v056"
VERSION = "v056-qwen-ref-episode-result-r1"
CONFIG_VERSION = "v056-ref-budget-slot-config-r1"
PUBLIC_SHA256 = "65d130536d04fda752b6ab36534ec657a8cd9bb0243b36067a1eb45413245aaf"
MODEL = "Qwen/Qwen3.5-9B"


def planned_slot(config):
    slots = json.loads(checked(config["slots"]).read_bytes())
    permit = json.loads(checked(config["authorization"]).read_bytes())
    matches = [row for row in slots["slots"] if row["slot_id"] == config["slot_id"]]
    if (slots.get("version") != "v056-ref-budget-slots-r1" or len(matches) != 1
            or permit.get("version") != "v056-ref-budget-authorization-r1"
            or permit.get("execution_authorized") is not True
            or permit.get("slots_sha256") != config["slots"]["sha256"]
            or config["slot_id"] not in permit.get("slot_ids", [])):
        raise ValueError("A frozen v056 slot and matching explicit authorization are required")
    slot = matches[0]
    if (slot["arm"] != "REF" or slot["condition_id"] != config["condition_id"]
            or slot["instance_id"] != config["public_task"]["instance_id"]
            or config.get("seed", slot["seed"]) != slot["seed"]):
        raise ValueError("Episode differs from the predeclared Qwen REF slot")
    return copy.deepcopy(slot)


def validate_config(config):
    if (config.get("version") != CONFIG_VERSION or config.get("arm") != "REF"
            or config.get("model") != MODEL or config.get("thinking") is not True
            or config.get("preparation_only") is not False
            or config.get("all_solver_admissions_passed") is not True
            or config["public_tasks"]["sha256"] != PUBLIC_SHA256):
        raise ValueError("Only qualified, explicitly authorized Qwen REF v056 slots may run")
    tasks = json.loads(checked(config["public_tasks"]).read_bytes())
    if [row for row in tasks if row["instance_id"] == config["public_task"]["instance_id"]] != [config["public_task"]]:
        raise ValueError("Public task differs from the fixed complete Verified projection")
    condition = json.loads(checked(config["configuration"]).read_bytes())
    limits = validate_condition(condition)
    if (condition["condition_id"] != config["condition_id"]
            or condition.get("formal_execution_authorized") is not True
            or condition["dataset_revision"] != config["dataset_revision"]):
        raise ValueError("Condition or dataset identity changed")
    model = condition["model"]
    if (model.get("name") != MODEL or model.get("raw_release") is not True
            or model.get("adapter") is not None
            or model.get("revision") != "c202236235762e1c871ad0ccb60c8ee5ba337b9a"
            or model.get("manifest", {}).get("sha256")
            != "030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6"):
        raise ValueError("Budget comparison requires the original frozen raw Qwen checkpoint")
    slot = planned_slot(config)
    if slot.get("input_plus_output_tokens") != limits["input_plus_output_tokens"]:
        raise ValueError("The slot and frozen condition disagree on total token budget")
    registry = json.loads(checked(config["public_test_registry"]).read_bytes())
    entries = [row for row in registry["entries"] if row["instance_id"] == slot["instance_id"]]
    if (registry.get("planned_tasks") != 500 or entries != [config["public_test_entry"]]
            or not entries[0]["admitted"]
            or entries[0]["baseline_mapping"] != config["scorer_request_base"]["baseline_mapping"]):
        raise ValueError("The independently admitted official baseline/public-test identity changed")
    if not config.get("frozen_sources"):
        raise ValueError("New v056 runtime source references are required")
    for item in config["frozen_sources"]:
        checked(item)
    endpoint = urlparse(config["ref_endpoint"])
    if (endpoint.scheme != "http" or endpoint.username or endpoint.password
            or endpoint.query or endpoint.fragment
            or not ipaddress.ip_address(endpoint.hostname).is_loopback
            or endpoint.port != config["model_identity_value"].get("port")
            or config["model_identity_value"].get("service_admission_complete") is not True):
        raise ValueError("Only the admitted external loopback REF resident may serve this episode")
    key = Path(config["ref_api_key_file"])
    if not key.is_absolute() or not key.is_file():
        raise ValueError("The trusted controller needs its existing resident credential file")
    return condition, slot


def prepared_paths(config):
    """Consume a qualified template; never repair or reuse an evicted payload implicitly."""
    if "lazy_native_preparation" in config:
        from .software_benchmark_prewarm_v054 import qualified_paths
        values = qualified_paths(config["public_task"]["instance_id"],
            mapping_reference=config["scorer_request_base"]["baseline_mapping"],
            cache_root=Path(config["lazy_native_preparation"]["cache_root"]))
        paths = {key: str(Path(value).resolve()) for key, value in values.items()}
    else:
        receipt = json.loads(checked(config["preparation_receipt"]).read_bytes())
        if (receipt.get("status") != "qualified" or receipt.get("slot_claimed") is not False
                or receipt.get("model_calls") != 0
                or receipt.get("baseline_mapping") != config["scorer_request_base"]["baseline_mapping"]):
            raise ValueError("A bound zero-model qualified preparation receipt is required")
        paths = {key: str(checked(receipt[key])) for key in
                 ("rootfs_environment", "rootfs_manifest", "environment", "qualification")}
        for key in ("rootfs_environment", "environment"):
            if key in config:
                supplied = checked(config[key]) if isinstance(config[key], dict) else Path(config[key]).resolve()
                if supplied != Path(paths[key]):
                    raise ValueError("Explicit environment differs from its qualified preparation")
    manifest = json.loads(Path(paths["rootfs_manifest"]).read_bytes())
    payload = Path(manifest["prepared_root"])
    if not payload.is_dir() or payload.is_symlink():
        raise ValueError("Qualified metadata has no live payload; prepare a new cache generation")
    return paths


class RefBudgetEpisode(Episode):
    """The episode owns writers, while model residency belongs to the separate pool."""

    def __init__(self, config, *, condition=None):
        self.slot = planned_slot(config)
        self.condition = condition or json.loads(checked(config["configuration"]).read_bytes())
        self.limits = copy.deepcopy(validate_condition(self.condition))
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
            "authorization": config["authorization"], "environment": config["environment"],
            "external_model_residency": True, "resume_or_resample_permitted": False})
        self._save()

    def _save(self):
        atomic_write(self.root / "state.json", json_bytes({
            "version": VERSION, "claim_id": self.claim_id, "slot_id": self.slot["slot_id"],
            "condition_id": self.slot["condition_id"], "phase": self.phase,
            "started": self.started, "inflight": self.inflight,
            "entered": (self.root / "entered.json").exists(),
            "external_model_residency": True, "model_attempts_inferred": False,
        }))
        atomic_write(self.guard_path, json_bytes(self.guard))

    def enter_ref(self):
        if self.phase != "claimed" or {row["role"] for row in self.scopes} != {"actor", "controller"}:
            raise ValueError("Both fresh controller and isolated actor scopes are required")
        self.started = self.clock()
        self.soft_at = self.started + self.limits["soft_seconds"]
        self.hard_at = self.started + self.limits["hard_seconds"]
        value = {"version": VERSION, "claim_id": self.claim_id, "slot": self.slot,
                 "seed": self.slot["seed"], "started": self.started, "soft_at": self.soft_at,
                 "hard_at": self.hard_at, "guard_path": str(self.guard_path),
                 "episode_limits": self.limits, "external_model_residency": True,
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
    lock = json.loads(checked(candidate_ref).read_bytes())
    if (lock.get("endpoint") != "terminal_code" or lock.get("lock_before_grading") is not True
            or lock["slot"]["slot_id"] != config["slot_id"]
            or lock["slot"].get("condition_id") != config["condition_id"]):
        raise ValueError("Scoring requires this slot's unique pre-grading terminal candidate")
    patch = lock["patch_receipt"]
    if "path" in patch:
        patch = json.loads(checked(patch).read_bytes())
    identity = {"slot_id": config["slot_id"], "condition_id": config["condition_id"],
                "configuration_sha256": config["configuration"]["sha256"],
                "candidate_tree_sha256": patch["candidate_tree_sha256"]}
    run_id = "v056-" + config["condition_id"].lower() + "-" + digest(json_bytes(identity))[:24]
    request = {**config["scorer_request_base"], "version": "v056-ref-budget-score-request-r1",
        **identity, "run_id": run_id, "instance_id": config["public_task"]["instance_id"],
        "arm": "REF", "thinking": True, "endpoint": "code", "attempt": 1,
        "patch": patch["patch"], "baseline_tree_sha256": patch["base_tree_sha256"],
        "episode_candidate_lock": candidate_ref, "native_candidate_lock": candidate_ref,
        "config_sha256": config["configuration"]["sha256"], "model": MODEL,
        "receipt_output": str(Path(output) / "official-code-receipt.json"),
        "preparation_only": False, "actor_feedback": False}
    return [write_new(Path(output) / "official-code-request.json", request)]


def run(config, output):
    output = Path(output).resolve()
    if not output.is_relative_to(RUN_ROOT.resolve()):
        raise ValueError("v056 episodes require their independent trusted output root")
    output.mkdir(parents=True, exist_ok=False)
    result = {"version": VERSION, "slot_id": config.get("slot_id"),
        "condition_id": config.get("condition_id"), "status": "starting", "entered": False,
        "entered_model": None, "automatic_retry": False, "GPU_loads": 0,
        "external_resident_stopped": False, "hidden_feedback_to_actor": False}
    episode, resources, processes = None, None, []
    try:
        condition, slot = validate_config(config)
        prepared = prepared_paths(config)
        config = {**config, "seed": slot["seed"], "episode_limits": condition["episode_limits"],
                  "rootfs_environment": prepared["rootfs_environment"],
                  "environment": reference(prepared["environment"])}
        write_new(output / "native-preparation.json", prepared)
        episode = RefBudgetEpisode(config, condition=condition)
        result["slot_claimed"] = True
        clone = clone_prepared_rootfs(config["rootfs_environment"], output / "actor")
        actor, task = Path(clone["rootfs"]), config["public_task"]
        environment = json.loads(checked(config["environment"]).read_bytes())
        public_environment = json.loads(Path(clone["environment_manifest"]).read_bytes())
        if public_environment["image_id"] != environment["image"]["image_id"]:
            raise ValueError("Fresh actor clone differs from its admitted image")
        manifest = capture_repository(actor / "testbed", output / "public-source",
            task_id=task["instance_id"], problem_statement=task["problem_statement"],
            source_identity={**{key: task[key] for key in ("instance_id", "repo", "base_commit")},
                             "dataset_revision": config["dataset_revision"]},
            gitlinks=environment.get("gitlinks"))
        baseline = reference(manifest.parent / "initial-tree.json")
        resources = create_episode_resources(episode.claim_id, output)
        lifetime = condition["episode_limits"]["hard_seconds"] + 300
        worker, scope = launch_owned([str(ROOT / "tools/run_native_worker_mapped_v056.sh"),
            "--rootfs", str(actor), "--stdlib", config["stdlib"],
            "--environment-manifest", clone["environment_manifest"]],
            claim_id=episode.claim_id, role="actor", resources=resources, runtime_seconds=lifetime,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=(output / "worker.stderr").open("xb"))
        processes.append((worker, scope))
        episode.register_scope(scope)
        ready = host.read_frame(worker.stdout)
        write_new(output / "worker-ready.json", ready)
        network = validate_actor_ready(ready)
        network.update(version="v056-ref-network-boundary-r1",
                       model_route="trusted_host_authenticated_loopback_resident")
        write_new(output / "network-boundary.json", network)
        child_config = {**{key: value for key, value in config.items() if key != "scorer_request_base"},
            "source_manifest": str(manifest), "output": str(output),
            "ready": str(output / "worker-ready.json"), "start": str(output / "start.json")}
        write_new(output / "controller-config.json", child_config)
        command = direct_environment_command([str(ROOT / "tools/run_native_sdk_controller_v054.sh"),
            config["sdk_runtime"], str(actor), str(ROOT / "tools/run_ref_budget_controller_v056.py"),
            "--config", str(output / "controller-config.json")])
        controller, scope = launch_owned(command, claim_id=episode.claim_id,
            role="controller", resources=resources, runtime_seconds=lifetime,
            stdin=worker.stdout, stdout=worker.stdin, stderr=(output / "controller.stderr").open("xb"))
        processes.append((controller, scope))
        episode.register_scope(scope)
        host.wait_file(output / "controller-ready.json", controller, timeout=120)
        write_new(output / "start.json", episode.enter_ref())
        result["entered"] = True
        code = controller.wait(timeout=max(1, episode.hard_at - time.monotonic()) + 20)
        if code:
            raise RuntimeError("Qwen REF controller failed; original ledger and stderr retained")
        child = json.loads((output / "controller-result.json").read_bytes())
        if child.get("status") not in {"closed", "budget_exhausted"}:
            raise RuntimeError("Controller did not reach a trusted candidate boundary")
        result["controller_status"] = child["status"]
        episode.close_dispatch("ref_budget_controller_returned")
        episode.watchdog.wait(timeout=40)
        for process, _ in processes:
            process.wait(timeout=20)
        episode.accept_quiescence()
        candidate = lock_native_candidate(episode, baseline_reference=baseline,
            public_worktree=actor / "testbed", public_task=task,
            dataset_revision=config["dataset_revision"], output=output / "candidates")
        requests = score_requests(config, candidate, output)
        result.update(candidate=candidate, scoring_requests=requests, candidate_locked=True,
                      quiescence=reference(episode.quiescence_path))
        proof = write_new(output / "cleanup-quiescence.json", {
            **json.loads(episode.quiescence_path.read_bytes()), "outer_launcher_reaped": True})
        cleanup = cleanup_episode_rootfs(actor, output, reference(clone["rootfs_manifest"]), proof,
            [candidate, baseline, reference(manifest), reference(output / "controller-result.json"), *requests])
        result.update(status="closed", temporary_rootfs_cleanup=cleanup,
                      native_public_tests_via_actor_RPC=True, managed_public_test_callbacks=0)
    except Exception as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)})
        if episode is not None and hasattr(episode, "watchdog") and episode.watchdog.poll() is None:
            try:
                episode.close_dispatch("ref_budget_runner_exception")
                episode.watchdog.wait(timeout=40)
            except Exception as close_error:
                result["exception_closure_error"] = str(close_error)
    finally:
        stopped, cleanup_errors = [], []
        for process, scope in reversed(processes):
            try:
                stopped.append(stop_owned(scope))
                process.wait(timeout=20)
            except Exception as error:
                cleanup_errors.append({"unit": scope["unit"], "error": str(error)})
        if resources is not None:
            try:
                result["resource_release"] = release_episode_resources(resources)
            except Exception as error:
                cleanup_errors.append({"resource_release": str(error)})
        child_path = output / "controller-result.json"
        if child_path.exists():
            result["controller_result"] = reference(child_path)
            try:
                child = json.loads(child_path.read_bytes())
                attempts = child.get("ledger", {}).get("attempts")
                if type(attempts) is int:
                    result["entered_model"] = attempts > 0
            except (ValueError, TypeError):
                result["controller_result_unreadable"] = True
        elif not result["entered"]:
            result["entered_model"] = False
        if cleanup_errors:
            result.update(status="technical_unknown", cleanup_errors=cleanup_errors)
        result["finally_stopped_scopes"] = stopped
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
