"""Closed v062 capability-probe plan and owned resource authorization.

Preparation is ordinary-file-only. Every execution entry requires a new exact
approved grant; the incident hold and all completed historical grants remain.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_shared_server_hold_v057 import SharedServerHold, read_hold
from .software_benchmark_ref_plan_v062 import retain
from .software_benchmark_rescore_policy_v060 import (
    validate_ipv4_targets as validate_ipv4_targets,
    validate_connect_target as validate_connect_target,
)

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v062-scoped-capability-probe-r1"
BATCH_ROOT = ROOT / "runs/software-benchmark-v062/capability-probe-r1-20261026"
PLAN_FILE = BATCH_ROOT / "plan.json"
COORDINATOR_RUN_ROOT = BATCH_ROOT / "coordinator"
AUTHORIZATION_FILE = ROOT / "config/v062-capability-authorization.json"
CPU_POOL_FILE = BATCH_ROOT / "host-cpu-pool.json"
PANEL_FILE = ROOT / "artifacts/software-benchmark-v062/preparation-r1/panel.json"
SOURCE_STATE = ROOT / "runs/software-benchmark-v060/original-ca-rescore-r1-20261025/requests-rescore/measurement-state.json"
OPERATIONS = frozenset("v062." + name for name in (
    "run", "model.start", "actor.create", "actor.start", "controller.create", "controller.start",
    "volume.create", "score", "control", "grader.create", "grader.start", "transport", "resolve", "model.bridge"))
SOURCE_PATHS = (
    'runs/software-benchmark-v062/sdk-bundle-r1/manifest.json',
    'config/v057-shared-server-hold.json',
    'config/v058-offline-rescore-authorization.json',
    'config/v059-tls-diagnostic-authorization.json',
    'config/v060-real-tls-rescore-authorization.json',
    'config/v061-recovery-authorization.json',
    'src/proworksim/repository_sources_v054.py',
    'src/proworksim/software_benchmark_baseline_v054.py',
    'src/proworksim/software_benchmark_candidates_v054.py',
    'src/proworksim/software_benchmark_dispatch_v062.py',
    'src/proworksim/software_benchmark_docker_actor_v062.py',
    'src/proworksim/software_benchmark_episode_v062.py',
    'src/proworksim/software_benchmark_exact_transport_v054.py',
    'src/proworksim/software_benchmark_exact_transport_v057.py',
    'src/proworksim/software_benchmark_gpu_lease_v054.py',
    'src/proworksim/software_benchmark_grading_environment_v058.py',
    'src/proworksim/software_benchmark_grading_environment_v060.py',
    'src/proworksim/software_benchmark_grading_environment_v062.py',
    'src/proworksim/software_benchmark_grading_qualification_v058.py',
    'src/proworksim/software_benchmark_grading_qualification_v060.py',
    'src/proworksim/software_benchmark_model_capacity_v062.py',
    'src/proworksim/software_benchmark_model_fifo_v062.py',
    'src/proworksim/software_benchmark_native_artifact_v054.py',
    'src/proworksim/software_benchmark_native_binding_v054.py',
    'src/proworksim/software_benchmark_native_control_v062.py',
    'src/proworksim/software_benchmark_native_execution_v057.py',
    'src/proworksim/software_benchmark_native_rootfs_v054.py',
    'src/proworksim/software_benchmark_native_v054.py',
    'src/proworksim/software_benchmark_native_worker_v054.py',
    'src/proworksim/software_benchmark_network_v055.py',
    'src/proworksim/software_benchmark_public_context_v062.py',
    'src/proworksim/software_benchmark_ref_budget_v056.py',
    'src/proworksim/software_benchmark_ref_budget_v062.py',
    'src/proworksim/software_benchmark_ref_deployment_v054.py',
    'src/proworksim/software_benchmark_ref_host_v061.py',
    'src/proworksim/software_benchmark_ref_plan_v062.py',
    'src/proworksim/software_benchmark_ref_resident_v062.py',
    'src/proworksim/software_benchmark_ref_service_v056.py',
    'src/proworksim/software_benchmark_requests_offline_v062.py',
    'src/proworksim/software_benchmark_requests_tls_v062.py',
    'src/proworksim/software_benchmark_rescore_policy_v060.py',
    'src/proworksim/software_benchmark_scorer_r5_v054.py',
    'src/proworksim/software_benchmark_scorer_r6_v055.py',
    'src/proworksim/software_benchmark_scorer_v054.py',
    'src/proworksim/software_benchmark_scorer_v056.py',
    'src/proworksim/software_benchmark_scorer_v058.py',
    'src/proworksim/software_benchmark_scorer_v062.py',
    'src/proworksim/software_benchmark_sdk_bundle_v061.py',
    'src/proworksim/software_benchmark_sdk_bundle_v062.py',
    'src/proworksim/software_benchmark_shared_server_hold_v057.py',
    'src/proworksim/software_benchmark_snapshot_recovery_v061.py',
    'src/proworksim/software_benchmark_supervision_v054.py',
    'src/proworksim/software_benchmark_tcp_transport_v060.py',
    'src/proworksim/software_benchmark_tcp_transport_v062.py',
    'src/proworksim/software_benchmark_tls_transport_v059.py',
    'src/proworksim/storage.py',
    'tools/bridge_ref_model_fifo_v062.py',
    'tools/launch_ref_capability_v062.py',
    'tools/prepare_capability_authorization_v062.py',
    'tools/run_capability_grading_v062.py',
    'tools/run_native_worker_docker_v062.py',
    'tools/run_offline_scorer_v058.py',
    'tools/run_ref_capability_v062.py',
    'tools/run_ref_controller_v062.py',
    'tools/serve_ref_capability_v062.py',
)
CONSTRAINTS = {
    "fresh_generation_slots": 174,
    "original_snapshot_slots": 0,
    "generation_token_upper_bound": 1240000000,
    "maximum_actor_containers": 178,
    "maximum_controller_containers": 178,
    "maximum_control_containers": 100,
    "maximum_score_containers": 174,
    "maximum_containers": 630,
    "maximum_named_volumes": 178,
    "zero_model_diagnostic_pairs": 4,
    "initial_zero_model_diagnostic_pairs": 2,
    "conditional_zero_model_repair_pairs": 2,
    "maximum_model_residents": 2,
    "minimum_free_gpu_mib": 50176,
    "gpu_memory_utilization": 0.6,
    "model_resident_memory_bytes": 96 * 1024**3,
    "model_resident_cpu_quota_percent": 1200,
    "model_resident_tasks_max": 2048,
    "model_resident_swap_bytes": 0,
    "new_owned_user_units": [
        "proworksim-v062-model-0.service",
        "proworksim-v062-model-1.service",
        "proworksim-v062-ref-development.service",
    ],
    "coordinator_memory_bytes": 16 * 1024**3,
    "coordinator_cpu_quota_percent": 400,
    "host_cpu_boundary": "fixed per-process affinity; optional quota when delegated; no shared controller changes",
    "minimum_captured_cpu_pool": 48,
    "coordinator_tasks_max": 512,
    "coordinator_swap_bytes": 0,
    "coordinator_restart": "no",
    "coordinator_stop_timeout_seconds": 420,
    "coordinator_kill_mode": "mixed",
    "existing_shared_services_changed": False,
    "neutral_model_preparation_calls": 2,
    "neutral_model_preparation_total_tokens": 4096,
    "active_actor_limit": 2,
    "active_controller_limit": 2,
    "active_grader_limit": 2,
    "maximum_active_containers": 6,
    "maximum_active_generation_episodes": 2,
    "maximum_episodes_per_model_resident": 2,
    "inflight_episode_migration": False,
    "actor_cpu": 4,
    "actor_memory_bytes": 16 * 1024**3,
    "controller_cpu": 2,
    "controller_memory_bytes": 4 * 1024**3,
    "grader_cpu": 4,
    "grader_memory_bytes": 16 * 1024**3,
    "pids_limit": 512,
    "controller_pids_limit": 256,
    "swap_bytes": 0,
    "container_network": "none",
    "container_cap_add": [],
    "container_cap_drop": ["ALL"],
    "no_new_privileges": True,
    "privileged": False,
    "host_bind_mounts": False,
    "host_devices_or_gpu_in_containers": False,
    "published_ports": False,
    "public_network": False,
    "named_volumes": "new per-slot local-driver volumes only; actor /testbed rw, controller /testbed ro",
    "host_namespaces_or_mount_configuration_changed": False,
    "daemon_start_or_restart": False,
    "automatic_replay": False,
    "actor_hard_seconds": 23400,
    "actor_lifecycle_seconds": 24000,
    "diagnostic_lifecycle_seconds": 180,
    "diagnostic_host_address_space_bytes": 16 * 1024**3,
    "diagnostic_host_visible_cpus": 4,
    "diagnostic_container_cpu_overlap": "zero-model deployment control only; actor/controller share four visible CPUs",
    "grader_test_seconds": 1800,
    "grader_lifecycle_seconds": 3600,
    "historical_results_overwritten": False,    "requests_private_grader_cap_add": ["NET_ADMIN", "NET_BIND_SERVICE"],
    "requests_private_capability_tasks": ["psf__requests-1766", "psf__requests-1921", "psf__requests-2931", "psf__requests-5414"],
    "requests_extra_hosts": {"httpbin.org": "127.0.0.1"},
    "requests_host_network_changes": False,
    "maximum_real_tls_sessions": 10,
    "real_tls_payload_bytes_per_session": 67108864,
    "real_tls_all_sessions_payload_bytes": 671088640,
    "disk_minimum_free_bytes": 137438953472,
    "automatic_environment_retries": False,
}


def load(ref):
    value = json.loads(checked(ref).read_bytes())
    if not isinstance(value, dict):
        raise ValueError("An immutable object is required")
    return value


def sources():
    return [reference(ROOT / path) for path in SOURCE_PATHS]


def capture_host_cpu_pool():
    """Freeze the ordinary preparer's allowed CPUs without changing any affinity."""
    if CPU_POOL_FILE.exists():
        value = json.loads(CPU_POOL_FILE.read_bytes())
    else:
        cpus = sorted(os.sched_getaffinity(0))
        value = {"version": "v062-fixed-host-cpu-pool-r1", "cpus": cpus,
                 "read_only_capture": True, "host_configuration_changed": False}
        _validate_cpu_pool(value)
        CPU_POOL_FILE.parent.mkdir(parents=True, exist_ok=True)
        write_new(CPU_POOL_FILE, value)
    _validate_cpu_pool(value)
    return reference(CPU_POOL_FILE)


def _validate_cpu_pool(value):
    cpus = value.get("cpus")
    if (value.get("version") != "v062-fixed-host-cpu-pool-r1" or not isinstance(cpus, list)
            or len(cpus) < 48 or len(cpus) > 4096 or any(type(cpu) is not int or cpu < 0 for cpu in cpus)
            or cpus != sorted(set(cpus)) or value.get("read_only_capture") is not True
            or value.get("host_configuration_changed") is not False):
        raise ValueError("A fixed inventory of at least 48 allowed CPUs is required")
    return cpus


def host_cpu_pool():
    plan = json.loads(PLAN_FILE.read_bytes())
    ref = plan.get("host_cpu_pool")
    if not isinstance(ref, dict) or Path(ref.get("path", "")).resolve() != CPU_POOL_FILE.resolve():
        raise ValueError("The reviewed plan does not bind its fixed host CPU pool")
    return _validate_cpu_pool(load(ref))


def cpu_set(role, index=0):
    partitions = {("coordinator", 0): (0, 4), ("actor", 0): (4, 8), ("controller", 0): (8, 10),
        ("actor", 1): (10, 14), ("controller", 1): (14, 16),
        ("grader", 0): (16, 20), ("grader", 1): (20, 24),
        ("model", 0): (24, 36), ("model", 1): (36, 48)}
    if type(index) is not int or (role, index) not in partitions:
        raise ValueError("Unknown fixed capability CPU partition")
    start, end = partitions[role, index]
    return ",".join(map(str, host_cpu_pool()[start:end]))




def create_plan():
    """Derive new configs without executing old configurations or grants."""
    panel = load(reference(PANEL_FILE))
    source_ref = panel["sources"]["latest_v060_source_state"]
    if source_ref != reference(SOURCE_STATE):
        raise ValueError("Frozen source-state identity changed")
    state = load(source_ref)
    source_rows = {(r["slot"]["instance_id"], r["slot"]["condition_id"]): r for r in state["rows"]}
    rows, environments, resources = [], {}, {}
    for index, slot in enumerate(panel["slots"]):
        condition = "REF_B10000K" if slot["condition_id"] == "FIX10M" else "REF_B5000K"
        old_row = source_rows[slot["instance_id"], condition]
        config_ref = state["jobs"][old_row["generation"]["job_id"]]["payload"]["config"]
        original = load(config_ref)
        if any(original.get(k) != old_row["slot"][k] for k in ("slot_id", "instance_id", "condition_id", "seed")):
            raise ValueError("Original configuration differs from its source slot")
        configuration = copy.deepcopy(original)
        configuration.update(version="v062-ref-capability-config-r1", slot_index=index,
            slot_id=slot["slot_id"], seed=slot["seed"], source_slot_id=old_row["slot"]["slot_id"],
            source_configuration=config_ref, execution_arm=slot["condition_id"],
            replicate=slot["repeat_index"], measurement_kind="capability_probe")
        derived_ref = retain(BATCH_ROOT / "configs" / (str(index) + ".json"), configuration)
        entry = {"slot_index": index, "slot_id": slot["slot_id"],
            "source_slot_id": old_row["slot"]["slot_id"], "instance_id": slot["instance_id"],
            "repo": slot["repo"], "condition_id": condition, "execution_arm": slot["condition_id"],
            "seed": slot["seed"], "replicate": slot["repeat_index"], "configuration": derived_ref,
            "generation_token_upper_bound": slot["input_plus_output_tokens"],
            "measurement_kind": "capability_probe"}
        rows.append(entry)
        base = original["scorer_request_base"]
        image_id = base["image"]["image_id"]
        actor_image = load(base["baseline_mapping"])["actor_image_id"]
        for role in ("actor", "controller", "score", "volume"):
            resources[role + "-" + str(index)] = {"role": role, "instance_id": slot["instance_id"],
                "slot_id": slot["slot_id"], "image_id": image_id if role == "score" else actor_image}
        environments.setdefault(slot["instance_id"], {"configuration": derived_ref, "image_id": image_id})
    for task, environment in environments.items():
        for kind in ("gold", "empty"):
            resources["control-" + task + "-" + kind] = {"role": "control", "instance_id": task,
                "patch_kind": kind, "image_id": environment["image_id"]}
    for number, arm in ((1, "BASE5M"), (2, "FIX5M"), (3, "BASE5M"), (4, "FIX5M")):
        first = next(row for row in rows if row["execution_arm"] == arm)
        for role in ("actor", "controller", "volume"):
            resources[f"diagnostic-{number}-{role}"] = {
                **resources[f"{role}-{first['slot_index']}"], "diagnostic": True,
                "diagnostic_index": number, "model_calls": 0, "execution_arm": arm,
                "repair_of": number - 2 if number > 2 else None}
    if (len(rows) != 174 or len(environments) != 50 or len(resources) != 808
            or sum(row["generation_token_upper_bound"] for row in rows) != 1240000000):
        raise ValueError("Frozen development panel or resource ceiling changed")
    body = {"version": VERSION, "root": str(BATCH_ROOT), "panel": reference(PANEL_FILE),
        "source_state": source_ref, "host_cpu_pool": capture_host_cpu_pool(), "rows": rows,
        "environments": environments, "resources": resources, "constraints": CONSTRAINTS,
        "historical_results_preserved": True, "training": False, "model_calls_during_preparation": 0}
    retain(PLAN_FILE, body)
    return body


def require_v062_allowed(operation, *, slot_id=None, instance_id=None):
    if operation not in OPERATIONS:
        raise SharedServerHold("Operation outside v062 capability scope")
    try:
        auth = json.loads(AUTHORIZATION_FILE.read_bytes())
    except (OSError, ValueError) as error:
        raise SharedServerHold("v062 specific Docker authorization is unavailable") from error
    if (auth.get("version") != VERSION or auth.get("status") != "approved"
            or not isinstance(auth.get("explicit_rootful_authorization"), str)
            or not auth["explicit_rootful_authorization"].strip()
            or auth.get("automatic_release") is not False or auth.get("constraints") != CONSTRAINTS):
        raise SharedServerHold("v062 specific Docker authorization is pending or closed")
    hold = read_hold()
    if hold.get("hold") is not True or hold.get("release_authorization") is not None:
        raise SharedServerHold("The incident-wide hold must remain unchanged")
    for name in ("v058-offline-rescore-authorization.json", "v059-tls-diagnostic-authorization.json",
                 "v060-real-tls-rescore-authorization.json", "v061-recovery-authorization.json"):
        if json.loads((ROOT / "config" / name).read_bytes()).get("status") != "completed":
            raise SharedServerHold("Previous limited grants must remain closed")
    if auth.get("sources") != sources() or auth.get("plan") != reference(PLAN_FILE):
        raise SharedServerHold("Reviewed v062 sources or panel changed")
    plan = load(auth["plan"])
    if (plan.get("version") != VERSION or plan.get("root") != str(BATCH_ROOT)
            or plan.get("constraints") != CONSTRAINTS or len(plan.get("rows", [])) != 174
            or plan.get("panel") != reference(PANEL_FILE)):
        raise SharedServerHold("Unrecognized fixed capability plan")
    host_cpu_pool()
    proposal = load(auth["proposal"])
    if (proposal.get("version") != VERSION or proposal.get("plan") != auth["plan"]
            or proposal.get("constraints") != CONSTRAINTS or proposal.get("sources") != auth["sources"]
            or proposal.get("operations") != sorted(OPERATIONS)):
        raise SharedServerHold("Reviewed proposal differs from the effective v062 grant")
    if instance_id is not None and instance_id not in plan["environments"]:
        raise SharedServerHold("Task outside the fixed fifty-task panel")
    if slot_id is not None:
        matches = [r for r in plan["rows"] if r["slot_id"] == slot_id]
        if len(matches) != 1 or instance_id not in (None, matches[0]["instance_id"]):
            raise SharedServerHold("Slot outside the fixed 174-slot panel")
        checked(matches[0]["configuration"])
    if operation in {"v062.transport", "v062.resolve"} and instance_id not in {
            "psf__requests-1766", "psf__requests-1921"}:
        raise SharedServerHold("Real TLS transport is limited to two Requests graders")
    return auth


def validate_reserved_diagnostic(spec):
    """A spare pair requalifies revised sources; it never repeats current evidence."""
    index, previous_index = spec["diagnostic_index"], spec["repair_of"]
    if (index, previous_index) not in {(3, 1), (4, 2)}:
        raise ValueError("Unknown reserved diagnostic identity")
    arm = "BASE" if index == 3 else "FIX"
    current_sources = sources()
    attempts = BATCH_ROOT / "diagnostic-attempts"
    intent = load(reference(attempts / f"{index}-intent.json"))
    prior_record = load(reference(attempts / f"{previous_index}.json"))
    prior_sources = prior_record.get("sources")
    prior_result_ref = reference(BATCH_ROOT / f"diagnostic-{previous_index}" / "result.json")
    if (not current_sources or intent.get("sources") != current_sources or intent.get("arm") != arm
            or intent.get("index") != index or prior_record.get("arm") != arm
            or prior_record.get("diagnostic_index") != previous_index
            or prior_record.get("result") != prior_result_ref
            or not isinstance(prior_sources, list) or not prior_sources or prior_sources == current_sources):
        raise ValueError("Reserved diagnostic requires stored intent for changed sources and the exact predecessor")
    previous = load(prior_result_ref)
    quiet = load(previous["quiescence"])
    if (previous.get("measurement_kind") != "zero_model_diagnostic"
            or previous.get("model_calls") != 0 or previous.get("execution_arm") != spec["execution_arm"]
            or quiet.get("quiescent") is not True or quiet.get("cleanup_errors") != []
            or quiet.get("create_result_unknown") is not False):
        raise ValueError("Reserved diagnostic requires a zero-model, fully quiescent predecessor")
    qualification_paths = [BATCH_ROOT / "diagnostic-qualifications" / arm / f"{number}.json"
                           for number in (previous_index, index)]
    qualification_paths.append(BATCH_ROOT / f"diagnostic-qualification-{arm}.json")
    for path in qualification_paths:
        if path.exists():
            qualification = load(reference(path))
            if qualification.get("arm") == arm and qualification.get("sources") == current_sources:
                result = load(qualification["result"])
                if result.get("passed") is True or result.get("diagnostic_passed") is True:
                    raise ValueError("This protocol already has a current-source passed qualification")
    return {"prior_attempt": reference(attempts / f"{previous_index}.json"),
            "current_intent": reference(attempts / f"{index}-intent.json"),
            "prior_passed": previous.get("passed") is True or previous.get("diagnostic_passed") is True}


def claim_resource(key):
    """Consume one exact resource identity before create; retries cannot expand scope."""
    auth = require_v062_allowed("v062.run")
    plan = load(auth["plan"])
    if key not in plan["resources"]:
        raise ValueError("Resource is not in the fixed capability plan")
    spec = plan["resources"][key]
    if spec.get("repair_of") is not None:
        validate_reserved_diagnostic(spec)
    role = spec["role"]
    group = "grader" if role in ("score", "control") else role
    directory = BATCH_ROOT / "resource-claims"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / "allocation.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        claim = directory / (key + ".json")
        if claim.exists():
            raise ValueError("This planned creation attempt was already consumed")
        lease = None
        if role != "volume":
            for number in range(CONSTRAINTS["active_" + group + "_limit"]):
                candidate = directory / ("active-" + group + "-" + str(number) + ".json")
                if not candidate.exists():
                    lease = candidate
                    break
            if lease is None:
                raise ValueError("All active capacity in this capability role is occupied")
        body = {
            "version": VERSION,
            "key": key,
            "spec": spec,
            "authorization": reference(AUTHORIZATION_FILE),
            "plan": auth["plan"],
            "lease": str(lease) if lease else None,
            "docker_name": "pws-v062-"
            + hashlib.sha256((str(BATCH_ROOT) + ":" + key).encode()).hexdigest()[:24],
        }
        data = json.dumps(body, sort_keys=True).encode() + b"\n"
        for path in (claim, *([lease] if lease else [])):
            with path.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return reference(claim)


def release_resource(claim_ref, *, quiescent):
    """Only release capacity after owned-object cleanup; the creation claim remains."""
    if quiescent is not True:
        return False
    value = load(claim_ref)
    directory = (BATCH_ROOT / "resource-claims").resolve()
    if (
        Path(claim_ref["path"]).resolve().parent != directory
        or value.get("version") != VERSION
        or Path(claim_ref["path"]).name != value.get("key", "") + ".json"
    ):
        raise ValueError("Unexpected resource claim")
    if value["lease"] is None:
        return True
    lease = Path(value["lease"])
    if lease.parent.resolve() != directory or not lease.name.startswith("active-"):
        raise ValueError("Unexpected capacity lease")
    with (directory / "allocation.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not lease.exists():
            return True
        if lease.read_bytes() != Path(claim_ref["path"]).read_bytes():
            raise ValueError("Capacity lease belongs to another creation attempt")
        lease.unlink()
    return True
