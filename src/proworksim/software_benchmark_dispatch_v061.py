"""Closed, bounded dispatch for the fourteen explicitly selected recovery slots.

The incident-wide hold stays set. This separate grant cannot start old queues,
change host settings, or reuse completed v058/v059/v060 grants.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_shared_server_hold_v057 import SharedServerHold, read_hold

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v061-scoped-unknown-recovery-r1"
BATCH_ROOT = ROOT / "runs/software-benchmark-v061/unknown-recovery-r1-20261025"
AUTHORIZATION_FILE = ROOT / "config/v061-recovery-authorization.json"
PLAN_FILE = BATCH_ROOT / "plan.json"
SOURCE_STATE = (
    ROOT
    / "runs/software-benchmark-v060/original-ca-rescore-r1-20261025/requests-rescore/measurement-state.json"
)
EXPECTED_INDICES = frozenset((2, 3, 4, 5, 6, 7, 9, 10, 157, 163, 166, 167, 169, 170))
SNAPSHOT_INDEX = 163
OPERATIONS = frozenset(
    (
        "v061.run",
        "v061.model.start",
        "v061.actor.create",
        "v061.actor.start",
        "v061.controller.create",
        "v061.controller.start",
        "v061.volume.create",
        "v061.score",
        "v061.control",
        "v061.grader.create",
        "v061.grader.start",
        "v061.transport",
        "v061.model.bridge",
    )
)
SOURCE_PATHS = (
    "src/proworksim/software_benchmark_dispatch_v061.py",
    "src/proworksim/software_benchmark_scorer_v061.py",
    "src/proworksim/software_benchmark_docker_actor_v061.py",
    "tools/run_native_worker_docker_v061.py",
    "tools/run_unknown_recovery_v061.py",
    "tools/launch_unknown_recovery_v061.py",
    "tools/prepare_unknown_recovery_authorization_v061.py",
    "src/proworksim/software_benchmark_ref_host_v061.py",
    "src/proworksim/software_benchmark_ref_resident_v061.py",
    "src/proworksim/software_benchmark_recovery_episode_v061.py",
    "tools/run_model_python_v061.py",
    "tools/serve_ref_recovery_v061.py",
    "src/proworksim/software_benchmark_model_fifo_v061.py",
    "src/proworksim/software_benchmark_ref_budget_v061.py",
    "src/proworksim/software_benchmark_ref_budget_v056.py",
    "tools/bridge_ref_model_fifo_v061.py",
    "tools/run_ref_budget_controller_v061.py",
    "src/proworksim/software_benchmark_snapshot_recovery_v061.py",
    "src/proworksim/software_benchmark_sdk_bundle_v061.py",
    "tools/prepare_sdk_bundle_v061.py",
    "runs/software-benchmark-v061/sdk-bundle-r3/manifest.json",
    "src/proworksim/software_benchmark_native_worker_v054.py",
    "src/proworksim/software_benchmark_network_v055.py",
    "src/proworksim/software_benchmark_tls_transport_v059.py",
    "tools/run_recovery_grading_v061.py",
    "tools/run_offline_scorer_v058.py",
    "src/proworksim/software_benchmark_scorer_v054.py",
    "src/proworksim/software_benchmark_scorer_v056.py",
    "src/proworksim/software_benchmark_scorer_v058.py",
    "src/proworksim/software_benchmark_grading_environment_v058.py",
    "src/proworksim/software_benchmark_shared_server_hold_v057.py",
    "config/v057-shared-server-hold.json",
    "config/v058-offline-rescore-authorization.json",
    "config/v059-tls-diagnostic-authorization.json",
    "config/v060-real-tls-rescore-authorization.json",
)
CONSTRAINTS = {
    "fresh_generation_slots": 13,
    "original_snapshot_slots": 1,
    "generation_token_upper_bound": 89000000,
    "maximum_actor_containers": 16,
    "maximum_controller_containers": 16,
    "maximum_control_containers": 14,
    "maximum_score_containers": 14,
    "maximum_containers": 60,
    "maximum_named_volumes": 16,
    "zero_model_diagnostic_pairs": 3,
    "maximum_model_residents": 2,
    "minimum_free_gpu_mib": 66560,
    "model_resident_memory_bytes": 96 * 1024**3,
    "model_resident_cpu_quota_percent": 1200,
    "model_resident_tasks_max": 2048,
    "model_resident_swap_bytes": 0,
    "new_owned_user_units": [
        "proworksim-v061-model-0.service",
        "proworksim-v061-model-1.service",
        "proworksim-v061-recovery.service",
    ],
    "coordinator_memory_bytes": 16 * 1024**3,
    "coordinator_cpu_quota_percent": 400,
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
    "original_thirteen_results_overwritten": False,
}


def load(ref):
    value = json.loads(checked(ref).read_bytes())
    if not isinstance(value, dict):
        raise ValueError("An immutable object is required")
    return value


def sources():
    return [reference(ROOT / path) for path in SOURCE_PATHS]


def create_plan():
    """Ordinary-file preparation only; never calls Docker, DNS or a model."""
    state = json.loads(SOURCE_STATE.read_bytes())
    selected = [row for row in state["rows"] if row["score"].get("status") != "official_report"]
    if {row["slot"]["slot_index"] for row in selected} != EXPECTED_INDICES or len(selected) != 14:
        raise ValueError("Only the exact fourteen retained unknown slots are eligible")
    rows, resources, environments = [], {}, {}
    for row in sorted(selected, key=lambda item: item["slot"]["slot_index"]):
        slot = row["slot"]
        config_ref = state["jobs"][row["generation"]["job_id"]]["payload"]["config"]
        config = load(config_ref)
        if any(
            config.get(key) != slot[key]
            for key in ("slot_id", "instance_id", "condition_id", "seed")
        ):
            raise ValueError("Original generation configuration differs from its selected slot")
        same_snapshot = slot["slot_index"] == SNAPSHOT_INDEX
        entry = {
            **slot,
            "original_config": config_ref,
            "measurement_kind": "original_terminal_snapshot_recovery"
            if same_snapshot
            else "fresh_generation_recovery",
            "recovery_slot_id": slot["slot_id"] if same_snapshot else slot["slot_id"] + ":v061-r1",
            "generation_token_upper_bound": 0
            if same_snapshot
            else slot["input_plus_output_tokens"],
        }
        rows.append(entry)
        image = config["scorer_request_base"]["image"]["image_id"]
        actor_image = load(config["scorer_request_base"]["baseline_mapping"])["actor_image_id"]
        for role in ("score",) if same_snapshot else ("actor", "controller", "score", "volume"):
            key = role + "-" + str(slot["slot_index"])
            resources[key] = {
                "role": role,
                "instance_id": slot["instance_id"],
                "original_slot_id": slot["slot_id"],
                "image_id": image if role == "score" else actor_image,
            }
        environments.setdefault(
            slot["instance_id"], {"original_config": config_ref, "image_id": image}
        )
    for task, item in environments.items():
        for kind in ("gold", "empty"):
            resources["control-" + task + "-" + kind] = {
                "role": "control",
                "instance_id": task,
                "patch_kind": kind,
                "image_id": item["image_id"],
            }
    first = rows[0]
    for diagnostic_index in range(1, 4):
        for role in ("actor", "controller", "volume"):
            resources["diagnostic-" + str(diagnostic_index) + "-" + role] = {
                **resources[role + "-" + str(first["slot_index"])],
                "diagnostic": True,
                "diagnostic_index": diagnostic_index,
                "model_calls": 0,
            }
    if (
        sum(row["generation_token_upper_bound"] for row in rows) != 89000000
        or len(environments) != 7
    ):
        raise ValueError("Fixed recovery panel or budget differs")
    body = {
        "version": VERSION,
        "root": str(BATCH_ROOT),
        "source_state": reference(SOURCE_STATE),
        "rows": rows,
        "environments": environments,
        "resources": resources,
        "constraints": CONSTRAINTS,
        "original_unknowns_preserved": True,
        "old_completed_results_replayed": False,
        "training": False,
    }
    BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    if PLAN_FILE.exists():
        if json.loads(PLAN_FILE.read_bytes()) != body:
            raise ValueError("An already prepared recovery plan differs")
    else:
        write_new(PLAN_FILE, body)
    return body


def require_v061_allowed(operation, *, original_slot_id=None, instance_id=None):
    if operation not in OPERATIONS:
        raise SharedServerHold("Operation outside v061 recovery scope")
    try:
        auth = json.loads(AUTHORIZATION_FILE.read_bytes())
    except (OSError, ValueError) as error:
        raise SharedServerHold("v061 specific Docker authorization is unavailable") from error
    if (
        auth.get("version") != VERSION
        or auth.get("status") != "approved"
        or not isinstance(auth.get("explicit_rootful_authorization"), str)
        or not auth["explicit_rootful_authorization"].strip()
        or auth.get("automatic_release") is not False
        or auth.get("constraints") != CONSTRAINTS
    ):
        raise SharedServerHold("v061 specific Docker authorization is pending or closed")
    hold = read_hold()
    if hold.get("hold") is not True or hold.get("release_authorization") is not None:
        raise SharedServerHold("The incident-wide hold must remain unchanged")
    for name in (
        "v058-offline-rescore-authorization.json",
        "v059-tls-diagnostic-authorization.json",
        "v060-real-tls-rescore-authorization.json",
    ):
        if json.loads((ROOT / "config" / name).read_bytes()).get("status") != "completed":
            raise SharedServerHold("Previous limited grants must remain closed")
    if auth.get("sources") != sources() or auth.get("plan") != reference(PLAN_FILE):
        raise SharedServerHold("v061 reviewed sources or selected panel changed")
    plan = load(auth["plan"])
    if (
        plan.get("version") != VERSION
        or plan.get("root") != str(BATCH_ROOT)
        or plan.get("constraints") != CONSTRAINTS
    ):
        raise SharedServerHold("Unrecognized fixed recovery plan")
    proposal = load(auth["proposal"])
    if (
        proposal.get("version") != VERSION
        or proposal.get("plan") != auth["plan"]
        or proposal.get("constraints") != CONSTRAINTS
        or proposal.get("sources") != auth["sources"]
        or proposal.get("operations") != sorted(OPERATIONS)
    ):
        raise SharedServerHold("The reviewed proposal differs from the effective grant")
    if instance_id is not None and instance_id not in plan["environments"]:
        raise SharedServerHold("Task outside the seven selected original instances")
    if original_slot_id is not None:
        matches = [r for r in plan["rows"] if r["slot_id"] == original_slot_id]
        if len(matches) != 1 or instance_id not in (None, matches[0]["instance_id"]):
            raise SharedServerHold("Slot outside the fourteen selected original endpoints")
    return auth


def claim_resource(key):
    """Consume one exact resource identity before create; retries cannot expand scope."""
    auth = require_v061_allowed("v061.run")
    plan = load(auth["plan"])
    if key not in plan["resources"]:
        raise ValueError("Resource is not in the fixed recovery plan")
    spec = plan["resources"][key]
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
                raise ValueError("All active capacity in this recovery role is occupied")
        body = {
            "version": VERSION,
            "key": key,
            "spec": spec,
            "authorization": reference(AUTHORIZATION_FILE),
            "plan": auth["plan"],
            "lease": str(lease) if lease else None,
            "docker_name": "pws-v061-"
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
