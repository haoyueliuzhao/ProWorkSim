"""Exact owned-resource identities and combined CPU/RAM admission for v064.

This module only prepares files and claims. Docker/service/GPU operations remain
in separately frozen callers. The shared-host hold is never released here.
"""
from __future__ import annotations

from collections import Counter
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

from .software_benchmark_full_plan_v064 import retain, VERSION as MATRIX_VERSION
from .software_benchmark_shared_server_hold_v057 import SharedServerHold, read_hold
from .software_benchmark_rescore_policy_v060 import (
    validate_ipv4_targets as validate_ipv4_targets,
    validate_connect_target as validate_connect_target,
)

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v064-scoped-full-verified-runtime-r1"
BATCH_ROOT = ROOT / "runs/software-benchmark-v064/full-verified-r1"
PLAN_FILE = BATCH_ROOT / "plan.json"
CONFIG_INDEX_FILE = BATCH_ROOT / "config-index.json"
SOURCE_INDEX_FILE = BATCH_ROOT / "runtime-sources.json"
COORDINATOR_RUN_ROOT = BATCH_ROOT / "coordinator"
GRADING_ROOT = BATCH_ROOT / "grading"
CPU_POOL_FILE = BATCH_ROOT / "host-cpu-pool.json"
MATRIX_FILE = ROOT / "artifacts/software-benchmark-v064/preparation-r1/plan.json"
AUTHORIZATION_FILE = ROOT / "config/v064-full-verified-authorization.json"
PROPOSAL_FILE = ROOT / "artifacts/software-benchmark-v064/runtime-authorization-r1/proposal.json"
GIB = 1024**3
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
TLS_TASKS = frozenset(("psf__requests-1766", "psf__requests-1921"))
OPERATIONS = frozenset("v064." + name for name in (
    "run", "model.start", "model.bridge", "api.request", "actor.create", "actor.start",
    "controller.create", "controller.start", "volume.create", "score", "delivery.score",
    "control", "grader.create", "grader.start", "transport", "resolve",
))
CONSTRAINTS = {
    "fresh_generation_slots": 6000,
    "generation_token_upper_bound": 45_000_000_000,
    "api_generation_token_upper_bound": 22_500_000_000,
    "api_total_budget_cny": "1500.00",
    "maximum_actor_containers": 6004,
    "maximum_controller_containers": 6004,
    "maximum_control_containers": 1000,
    "maximum_code_score_containers": 6000,
    "maximum_delivery_score_containers": 3000,
    "maximum_score_containers": 9000,
    "maximum_containers": 22008,
    "maximum_named_volumes": 6004,
    "zero_model_diagnostic_pairs": 4,
    "initial_zero_model_diagnostic_pairs": 2,
    "conditional_zero_model_repair_pairs": 2,
    "maximum_model_residents": 6,
    "minimum_free_gpu_mib": 50176,
    "physical_gpus": list(range(8)),
    "gpu_memory_utilization": 0.6,
    "required_model_context": 131072,
    "model_resident_memory_bytes": 96 * GIB,
    "model_resident_cpu_quota_percent": 1200,
    "model_resident_tasks_max": 2048,
    "model_resident_swap_bytes": 0,
    "neutral_model_preparation_calls": 6,
    "neutral_model_preparation_total_tokens": 12288,
    "api_neutral_preparation_calls": 2,
    "api_neutral_preparation_total_tokens": 8192,
    "free_api_metadata_requests": 2,
    "minimum_captured_cpu_pool": 176,
    "maximum_combined_reserved_cpu": 152,
    "maximum_combined_reserved_memory_bytes": 832 * GIB,
    "coordinator_memory_bytes": 16 * GIB,
    "coordinator_cpu_quota_percent": 400,
    "coordinator_tasks_max": 512,
    "coordinator_swap_bytes": 0,
    "coordinator_restart": "no",
    "coordinator_stop_timeout_seconds": 420,
    "coordinator_kill_mode": "mixed",
    "new_owned_user_units": ["proworksim-v064-full-verified.service"] + [
        f"proworksim-v064-model-{index}.service" for index in range(6)],
    "active_actor_limit": 12,
    "active_controller_limit": 12,
    "active_grader_limit": 4,
    "maximum_active_generation_episodes": 12,
    "maximum_active_containers": 28,
    "maximum_episodes_per_model_resident": 2,
    "generation_pair_reserved_cpu": 6,
    "generation_pair_reserved_memory_bytes": 20 * GIB,
    "generation_pair_payload_spool_bytes": 4 * GIB,
    "payload_spool_reservation_is_filesystem_quota": False,
    "actor_cpu": 4,
    "actor_memory_bytes": 16 * GIB,
    "controller_cpu": 2,
    "controller_memory_bytes": 4 * GIB,
    "grader_cpu": 4,
    "grader_memory_bytes": 16 * GIB,
    "pids_limit": 512,
    "controller_pids_limit": 256,
    "swap_bytes": 0,
    "memory_minimum_free_bytes": 128 * GIB,
    "disk_minimum_free_bytes": 128 * GIB,
    "container_network": "none",
    "container_cap_add": [],
    "container_cap_drop": ["ALL"],
    "no_new_privileges": True,
    "privileged": False,
    "host_bind_mounts": False,
    "host_devices_or_gpu_in_containers": False,
    "published_ports": False,
    "actor_external_network": False,
    "model_api_network": "trusted host direct TLS to official DeepSeek API only; no proxy or search",
    "named_volumes": "new per-episode local-driver volume; actor /testbed rw, controller /testbed ro",
    "host_namespaces_or_mount_configuration_changed": False,
    "daemon_start_or_restart": False,
    "existing_shared_services_changed": False,
    "automatic_replay": False,
    "inflight_episode_migration": False,
    "actor_hard_seconds": 23400,
    "actor_lifecycle_seconds": 24000,
    "diagnostic_lifecycle_seconds": 180,
    "diagnostic_host_address_space_bytes": 16 * GIB,
    "diagnostic_host_visible_cpus": 4,
    "grader_test_seconds": 1800,
    "grader_lifecycle_seconds": 3600,
    "historical_results_overwritten": False,
    "requests_private_capability_tasks": ["psf__requests-1766", "psf__requests-1921", "psf__requests-2931", "psf__requests-5414"],
    "requests_private_grader_cap_add": ["NET_ADMIN", "NET_BIND_SERVICE"],
    "requests_extra_hosts": {"httpbin.org": "127.0.0.1"},
    "requests_host_network_changes": False,
    "maximum_real_tls_sessions": 40,
    "real_tls_connections_per_session": 512,
    "real_tls_payload_bytes_per_session": 64 * 1024**2,
    "real_tls_all_sessions_payload_bytes": 40 * 64 * 1024**2,
    "automatic_environment_retries": False,
    "previous_runtime_must_be_quiescent": True,
}
MANDATORY_SOURCE_PATHS = (
    "src/proworksim/software_benchmark_dispatch_v064.py",
    "src/proworksim/software_benchmark_full_plan_v064.py",
    "src/proworksim/software_benchmark_candidates_v054.py",
    "src/proworksim/software_benchmark_shared_server_hold_v057.py",
    "config/v057-shared-server-hold.json",
)
_FILE_CACHE = {}
_JSON_CACHE = {}


class ResourceBusy(RuntimeError):
    """No new creation claim was consumed; wait without replaying an attempt."""


def _file(path):
    path = Path(path).resolve()
    info = path.stat()
    signature = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    key = str(path)
    # Filesystem timestamp resolution is not an integrity boundary: a same-size
    # rewrite can preserve mtime and share the observed ctime tick. Hash bytes;
    # cache parsed JSON only after this exact check, never trust metadata alone.
    raw = path.read_bytes()
    after = path.stat()
    if signature != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError("Immutable input changed during read")
    ref = {"path": key, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    cached = _FILE_CACHE.get(key)
    if cached is None or cached[2] != ref:
        _JSON_CACHE.pop(key, None)
    current = (signature, raw, ref)
    _FILE_CACHE[key] = current
    return current


def reference(path):
    return dict(_file(path)[2])


def checked(ref):
    _checked_contents(ref)
    return Path(ref["path"])


def _checked_contents(ref):
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256", "bytes"}:
        raise ValueError("An immutable input differs from its frozen identity")
    value = _file(ref["path"])
    if value[2] != ref:
        raise ValueError("An immutable input differs from its frozen identity")
    return value


def load(ref):
    value = json.loads(_checked_contents(ref)[1])
    if not isinstance(value, dict):
        raise ValueError("Expected an immutable JSON object")
    return value


def _cached_json(ref):
    content = _checked_contents(ref)
    key = str(Path(ref["path"]).resolve())
    if key not in _JSON_CACHE:
        value = json.loads(content[1])
        if not isinstance(value, dict):
            raise ValueError("Expected an immutable JSON object")
        _JSON_CACHE[key] = value
    return _JSON_CACHE[key]


def sources():
    """An explicit complete source index must be prepared after integration."""
    index_ref = reference(SOURCE_INDEX_FILE)
    index = _cached_json(index_ref)
    files = index.get("files")
    if index.get("version") != "v064-runtime-sources-r1" or not isinstance(files, list) or not files:
        raise ValueError("No complete v064 runtime source index has been sealed")
    paths = [str(Path(item["path"]).resolve()) for item in files]
    if len(paths) != len(set(paths)) or not all(Path(path).is_relative_to(ROOT.resolve()) for path in paths):
        raise ValueError("Runtime sources must have unique project-owned paths")
    if not {str((ROOT / path).resolve()) for path in MANDATORY_SOURCE_PATHS} <= set(paths):
        raise ValueError("The runtime source index omits its mandatory guards")
    for item in files:
        checked(item)
    return [index_ref, *copy.deepcopy(files)]


def _validate_cpu_pool(value):
    cpus = value.get("cpus")
    if (value.get("version") != "v064-fixed-host-cpu-pool-r1" or not isinstance(cpus, list)
            or len(cpus) < 176 or len(cpus) > 4096 or cpus != sorted(set(cpus))
            or any(type(cpu) is not int or cpu < 0 for cpu in cpus)
            or value.get("read_only_capture") is not True or value.get("host_configuration_changed") is not False):
        raise ValueError("A read-only fixed pool of at least 176 allowed logical CPUs is required")
    return cpus


def capture_host_cpu_pool():
    if CPU_POOL_FILE.exists():
        _validate_cpu_pool(load(reference(CPU_POOL_FILE)))
    else:
        value = {"version": "v064-fixed-host-cpu-pool-r1", "cpus": sorted(os.sched_getaffinity(0)),
                 "read_only_capture": True, "host_configuration_changed": False}
        _validate_cpu_pool(value)
        retain(CPU_POOL_FILE, value)
    return reference(CPU_POOL_FILE)


def host_cpu_pool():
    plan = _cached_json(reference(PLAN_FILE))
    ref = plan.get("host_cpu_pool")
    if not isinstance(ref, dict) or Path(ref.get("path", "")).resolve() != CPU_POOL_FILE.resolve():
        raise ValueError("The runtime plan must bind its own fixed CPU inventory")
    return _validate_cpu_pool(_cached_json(ref))


def cpu_set(role, index=0):
    if type(index) is not int or index < 0:
        raise ValueError("A fixed CPU lane index is required")
    if role == "coordinator" and index == 0:
        start, end = 0, 4
    elif role in {"actor", "controller"} and index < 12:
        start = 4 + index * 6 + (4 if role == "controller" else 0)
        end = start + (2 if role == "controller" else 4)
    elif role == "grader" and index < 4:
        start, end = 76 + index * 4, 80 + index * 4
    elif role == "model" and index < 6:
        start, end = 92 + index * 12, 104 + index * 12
    else:
        raise ValueError("Unknown fixed v064 CPU partition")
    return ",".join(map(str, host_cpu_pool()[start:end]))


def create_plan():
    """Bind complete executable configs; absent configs are not readiness."""
    matrix_ref, config_ref = reference(MATRIX_FILE), reference(CONFIG_INDEX_FILE)
    matrix, configs = load(matrix_ref), load(config_ref)
    if (matrix.get("version") != MATRIX_VERSION or len(matrix.get("rows", [])) != 6000
            or configs.get("version") != "v064-runtime-config-index-r1" or len(configs.get("rows", [])) != 6000):
        raise ValueError("The complete matrix and all six thousand executable configurations are required")
    indexed = {entry["slot_index"]: entry for entry in configs["rows"]}
    if set(indexed) != set(range(6000)) or len(configs["rows"]) != len(indexed):
        raise ValueError("Duplicate or missing executable configuration index")
    rows, environments, resources = [], {}, {}
    for slot in matrix["rows"]:
        binding = indexed[slot["slot_index"]]
        config = load(binding["configuration"])
        for key in ("slot_id", "instance_id", "condition_id", "seed"):
            if config.get(key) != slot[key]:
                raise ValueError("Executable configuration differs from the frozen paired slot")
        if (config.get("measurement_kind") != "full_verified_comparison"
                or not isinstance(config.get("source_slot_id"), str)):
            raise ValueError("Executable full-comparison identity or baseline lineage differs")
        if not all(isinstance(binding.get(key), str) and IMAGE.fullmatch(binding[key])
                   for key in ("actor_image_id", "image_id")):
            raise ValueError("Each configuration requires pinned actor and grader image IDs")
        row = {**slot, "configuration": binding["configuration"], "execution_arm": slot["arm"],
               "measurement_kind": config["measurement_kind"], "source_slot_id": config["source_slot_id"]}
        rows.append(row)
        for role in ("actor", "controller", "volume", "score"):
            key = f"{role}-{slot['slot_index']}"
            resources[key] = {"role": role, "slot_id": slot["slot_id"], "instance_id": slot["instance_id"],
                              "image_id": binding["image_id"] if role == "score" else binding["actor_image_id"],
                              "endpoint": "code" if role == "score" else None}
        if slot["arm"] == "PROJECT":
            resources[f"delivery-score-{slot['slot_index']}"] = {
                "role": "delivery_score", "slot_id": slot["slot_id"], "instance_id": slot["instance_id"],
                "image_id": binding["image_id"], "endpoint": "delivery",
                "skip_when_no_legal_delivery": True, "same_tree_can_reuse_own_code_result": True}
        task = slot["instance_id"]
        previous = environments.setdefault(task, {"configuration": binding["configuration"],
            "image_id": binding["image_id"], "actor_image_id": binding["actor_image_id"]})
        if any(previous[key] != binding[key] for key in ("image_id", "actor_image_id")):
            raise ValueError("Conditions must use the same actual task environment image identities")
    for task, env in environments.items():
        for kind in ("gold", "empty"):
            resources[f"control-{task}-{kind}"] = {"role": "control", "instance_id": task,
                "patch_kind": kind, "image_id": env["image_id"], "endpoint": "environment_control"}
    for number, arm in ((1, "REF"), (2, "PROJECT"), (3, "REF"), (4, "PROJECT")):
        row = next(row for row in rows if row["arm"] == arm and row["model_key"] == "QWEN")
        for role in ("actor", "controller", "volume"):
            resources[f"diagnostic-{number}-{role}"] = {
                **resources[f"{role}-{row['slot_index']}"], "diagnostic": True,
                "diagnostic_index": number, "model_calls": 0, "execution_arm": arm,
                "repair_of": number - 2 if number > 2 else None}
    for index in range(6):
        resources[f"model-{index}"] = {"role": "model", "model_index": index, "model_key": "QWEN"}
    expected = {"actor": 6004, "controller": 6004, "volume": 6004, "score": 6000,
                "delivery_score": 3000, "control": 1000, "model": 6}
    if (dict(Counter(item["role"] for item in resources.values())) != expected or len(environments) != 500
            or sum(row["generation_token_upper_bound"] for row in rows) != 45_000_000_000):
        raise ValueError("The complete resource scope differs from the new experiment")
    value = {"version": VERSION, "root": str(BATCH_ROOT), "matrix": matrix_ref,
             "configurations": config_ref, "host_cpu_pool": capture_host_cpu_pool(),
             "rows": rows, "environments": environments, "resources": resources,
             "resource_role_counts": expected, "constraints": CONSTRAINTS,
             "historical_results_preserved": True, "training": False, "model_calls_during_preparation": 0}
    retain(PLAN_FILE, value)
    return value


def previous_runtimes_closed():
    """No overlap with the bounded predecessor batches; no service operations."""
    paths = (
        ROOT / "runs/software-benchmark-v062/capability-probe-r1-20261026/coordinator-r2/run-summary.json",
        ROOT / "runs/software-benchmark-v063/diagnostic-rescore-r1/coordinator/run-summary.json",
    )
    for index, path in enumerate(paths):
        if not path.is_file():
            raise SharedServerHold("Previous v062/v063 runtime has not finished; preparation may continue")
        value = _cached_json(reference(path))
        if index == 0:
            if (value.get("failure") is not None or len(value.get("generation", {})) != 174
                    or value.get("unentered_generation") or value.get("unentered_controls")
                    or value.get("unentered_scores") or not value.get("resident_closure")
                    or any(item.get("owned_unit_stopped") is not True for item in value["resident_closure"])):
                raise SharedServerHold("The previous GPU batch lacks complete closure")
        elif value.get("status") != "closed" or len(value.get("completions", [])) != 3:
            raise SharedServerHold("The supplementary grading batch lacks complete closure")
    # v062's coordinator only emits successful closure after all owned workers
    # have returned trusted cleanup; v063's runner rejects each unproven cleanup.
    return [reference(path) for path in paths]


def require_v064_allowed(operation, *, slot_id=None, instance_id=None):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise SharedServerHold("v064 host processes must remain ordinary-user processes")
    if operation not in OPERATIONS:
        raise SharedServerHold("Operation outside v064 experiment scope")
    try:
        auth = _cached_json(reference(AUTHORIZATION_FILE))
    except (OSError, ValueError) as error:
        raise SharedServerHold("The v064 resource grant has not been sealed") from error
    if (auth.get("version") != VERSION or auth.get("status") != "approved"
            or not isinstance(auth.get("explicit_rootful_authorization"), str)
            or not auth["explicit_rootful_authorization"].strip()
            or auth.get("automatic_release") is not False or auth.get("constraints") != CONSTRAINTS):
        raise SharedServerHold("The exact v064 grant is pending, changed or closed")
    hold = read_hold()
    if hold.get("hold") is not True or hold.get("release_authorization") is not None:
        raise SharedServerHold("The incident-wide hold must remain unchanged")
    if (auth.get("sources") != sources() or auth.get("plan") != reference(PLAN_FILE)
            or auth.get("proposal") != reference(PROPOSAL_FILE)):
        raise SharedServerHold("Approved sources or plan changed")
    plan, proposal = _cached_json(auth["plan"]), _cached_json(auth["proposal"])
    if (plan.get("version") != VERSION or plan.get("root") != str(BATCH_ROOT)
            or plan.get("constraints") != CONSTRAINTS or len(plan.get("rows", [])) != 6000
            or plan.get("matrix") != reference(MATRIX_FILE)
            or plan.get("configurations") != reference(CONFIG_INDEX_FILE)
            or proposal.get("version") != VERSION or proposal.get("plan") != auth["plan"]
            or proposal.get("sources") != auth["sources"] or proposal.get("constraints") != CONSTRAINTS
            or proposal.get("operations") != sorted(OPERATIONS)):
        raise SharedServerHold("The sealed execution proposal differs from the approved scope")
    host_cpu_pool()
    if instance_id is not None and instance_id not in plan["environments"]:
        raise SharedServerHold("Task outside the complete fixed 500")
    if slot_id is not None:
        row = next((row for row in plan["rows"] if row["slot_id"] == slot_id), None)
        if row is None or instance_id not in (None, row["instance_id"]):
            raise SharedServerHold("Episode outside the fixed six thousand paired runs")
        checked(row["configuration"])
    if operation in {"v064.transport", "v064.resolve"} and instance_id not in TLS_TASKS:
        raise SharedServerHold("Grading-only real TLS is restricted to the two fixed Requests tasks")
    previous_runtimes_closed()
    return copy.deepcopy(auth)


def validate_reserved_diagnostic(spec):
    number, prior = spec.get("diagnostic_index"), spec.get("repair_of")
    if (number, prior) not in {(3, 1), (4, 2)}:
        raise ValueError("Unexpected reserved diagnostic")
    arm = "REF" if number == 3 else "PROJECT"
    folder = BATCH_ROOT / "diagnostic-attempts"
    intent = load(reference(folder / f"{number}-intent.json"))
    previous = load(reference(folder / f"{prior}.json"))
    source_manifest = sources()
    result_ref = reference(BATCH_ROOT / f"diagnostic-{prior}/result.json")
    if (intent.get("sources") != source_manifest or intent.get("arm") != arm
            or intent.get("index") != number or previous.get("arm") != arm
            or previous.get("diagnostic_index") != prior or previous.get("result") != result_ref
            or not previous.get("sources") or previous["sources"] == source_manifest):
        raise ValueError("A spare diagnostic requires changed sources and the exact previous zero-model attempt")
    result = load(result_ref)
    quiet = load(result["quiescence"])
    if (result.get("measurement_kind") != "zero_model_diagnostic" or result.get("model_calls") != 0
            or quiet.get("quiescent") is not True or quiet.get("cleanup_errors") != []
            or quiet.get("create_result_unknown") is not False):
        raise ValueError("The preceding deployment control is not fully quiet and zero-model")
    for path in (BATCH_ROOT / f"diagnostic-qualification-{arm}.json",
                 BATCH_ROOT / "diagnostic-qualifications" / arm / f"{prior}.json",
                 BATCH_ROOT / "diagnostic-qualifications" / arm / f"{number}.json"):
        if path.exists():
            qualification = load(reference(path))
            if qualification.get("sources") == source_manifest:
                known = load(qualification["result"])
                if known.get("passed") is True or known.get("diagnostic_passed") is True:
                    raise ValueError("The current sources already have a passed deployment control")


def physical_capacity():
    available = next(int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()
                     if line.startswith("MemAvailable:"))
    disk = shutil.disk_usage(ROOT).free
    return {"memory_available_bytes": available, "disk_free_bytes": disk,
            "passed": available >= CONSTRAINTS["memory_minimum_free_bytes"]
                      and disk >= CONSTRAINTS["disk_minimum_free_bytes"]}


def _budget(active, cpu, memory, spool=0):
    used_cpu = 4 + sum(item["reserved_cpu"] for item in active)
    used_memory = 16 * GIB + sum(item["reserved_memory_bytes"] for item in active)
    if (used_cpu + cpu > CONSTRAINTS["maximum_combined_reserved_cpu"]
            or used_memory + memory > CONSTRAINTS["maximum_combined_reserved_memory_bytes"]):
        raise ResourceBusy("Combined owned CPU/RAM reservations have no capacity")
    physical = physical_capacity()
    reserved_spool = sum(item.get("reserved_spool_bytes", 0) for item in active) + spool
    if (not physical["passed"]
            or physical["memory_available_bytes"] < CONSTRAINTS["memory_minimum_free_bytes"] + memory
            or physical["disk_free_bytes"] < CONSTRAINTS["disk_minimum_free_bytes"] + reserved_spool):
        raise ResourceBusy("Shared-host memory/disk floor prevents new dispatch")
    return {"reserved_cpu_after": used_cpu + cpu, "reserved_memory_bytes_after": used_memory + memory,
            "reserved_payload_spool_bytes_after": reserved_spool, "spool_is_filesystem_quota": False,
            "physical_at_admission": physical}


def _pair_actor_key(key, spec):
    return f"diagnostic-{spec['diagnostic_index']}-actor" if spec.get("diagnostic") else "actor-" + key.rsplit("-", 1)[1]


def _write_claim(path, value):
    data = json.dumps(value, sort_keys=True).encode() + b"\n"
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return data


def claim_resource(key, *, lane=None):
    """Reserve actor+controller capacity before either container is created."""
    auth = require_v064_allowed("v064.run")
    plan = _cached_json(auth["plan"])
    if key not in plan["resources"]:
        raise ValueError("Unplanned v064 resource")
    spec = plan["resources"][key]
    if spec.get("repair_of") is not None:
        validate_reserved_diagnostic(spec)
    role = spec["role"]
    directory = BATCH_ROOT / "resource-claims"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / "allocation.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        claim = directory / (key + ".json")
        if claim.exists():
            raise ValueError("The exact creation/residency identity was already consumed")
        active = [load(reference(path)) for path in directory.glob("active-*.json")]
        lease = None
        parent_actor = None
        reserved_cpu = reserved_memory = reserved_spool = 0
        admission = None
        if role == "volume":
            # Callers claim the actor pair first; disk allocation must not race
            # a later CPU/RAM rejection after a volume has already been created.
            parent_actor = _pair_actor_key(key, spec)
            actor = load(reference(directory / (parent_actor + ".json")))
            lease = Path(actor["lease"])
            if (not lease.exists() or load(reference(lease)).get("key") != parent_actor
                    or (directory / (parent_actor + ".released.json")).exists()):
                raise ResourceBusy("An active whole-pair reservation must precede volume creation")
            selected_lane = actor["lane"]
            lease = None
        elif role == "controller":
            parent_actor = _pair_actor_key(key, spec)
            actor = load(reference(directory / (parent_actor + ".json")))
            lease = Path(actor["lease"])
            if (not lease.exists() or load(reference(lease)).get("key") != parent_actor
                    or (directory / (parent_actor + ".released.json")).exists()):
                raise ValueError("Controller cannot outlive or replace its actor-pair reservation")
            selected_lane = actor["lane"]
            lease = None
        else:
            group, count, reserved_cpu, reserved_memory = {
                "actor": ("actor", 12, 6, 20 * GIB),
                "score": ("grader", 4, 4, 16 * GIB),
                "delivery_score": ("grader", 4, 4, 16 * GIB),
                "control": ("grader", 4, 4, 16 * GIB),
                "model": ("model", 6, 12, 96 * GIB),
            }[role]
            if role == "model":
                if lane not in (None, spec["model_index"]):
                    raise ValueError("Model service index fixes its lane")
                lane = spec["model_index"]
            if lane is not None and (type(lane) is not int or lane not in range(count)):
                raise ValueError("Requested resource lane is outside its exact scope")
            lanes = range(count) if lane is None else [lane]
            selected_lane = next((number for number in lanes if not (directory / f"active-{group}-{number}.json").exists()), None)
            if selected_lane is None:
                raise ResourceBusy("Every capacity lane in this role is occupied")
            reserved_spool = CONSTRAINTS["generation_pair_payload_spool_bytes"] if role == "actor" else 0
            admission = _budget(active, reserved_cpu, reserved_memory, reserved_spool)
            lease = directory / f"active-{group}-{selected_lane}.json"
        if lane is not None and selected_lane != lane:
            raise ValueError("Requested lane differs from the existing whole-pair reservation")
        value = {"version": VERSION, "key": key, "spec": copy.deepcopy(spec),
                 "authorization": reference(AUTHORIZATION_FILE), "plan": auth["plan"],
                 "lease": str(lease) if lease else None, "lane": selected_lane,
                 "parent_actor_key": parent_actor, "reserved_cpu": reserved_cpu,
                 "reserved_memory_bytes": reserved_memory, "admission": admission,
                 "reserved_spool_bytes": reserved_spool,
                 "docker_name": "pws-v064-" + hashlib.sha256((str(BATCH_ROOT) + ":" + key).encode()).hexdigest()[:24]}
        data = _write_claim(claim, value)
        if lease is not None:
            with lease.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return reference(claim)


def release_resource(claim_ref, *, quiescent):
    """Keep whole-pair reservation until both declared containers are quiet."""
    if quiescent is not True:
        return False
    value = load(claim_ref)
    directory = (BATCH_ROOT / "resource-claims").resolve()
    if (Path(claim_ref["path"]).resolve() != directory / (value.get("key", "") + ".json")
            or value.get("version") != VERSION):
        raise ValueError("Foreign resource claim")
    with (directory / "allocation.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        marker = directory / (value["key"] + ".released.json")
        retain(marker, {"version": VERSION, "claim": claim_ref, "quiescent": True})
        role = value["spec"]["role"]
        if role == "volume":
            return True
        owner = value
        if role == "controller":
            owner = load(reference(directory / (value["parent_actor_key"] + ".json")))
        if role in {"actor", "controller"}:
            controller_key = owner["key"].removesuffix("actor") + "controller" if owner["spec"].get("diagnostic") else owner["key"].replace("actor-", "controller-", 1)
            if not (directory / (owner["key"] + ".released.json")).exists():
                return True
            if ((directory / (controller_key + ".json")).exists()
                    and not (directory / (controller_key + ".released.json")).exists()):
                return True
        lease = Path(owner["lease"])
        if lease.parent.resolve() != directory or not lease.name.startswith("active-"):
            raise ValueError("Foreign capacity lease")
        if lease.exists():
            if lease.read_bytes() != checked(reference(directory / (owner["key"] + ".json"))).read_bytes():
                raise ValueError("Another resource owns this capacity lane")
            lease.unlink()
        return True


def reserve_model(index):
    return claim_resource(f"model-{index}", lane=index)


def release_model(claim_ref, *, quiescent):
    value = load(claim_ref)
    if value["spec"]["role"] != "model":
        raise ValueError("Not a model residency reservation")
    return release_resource(claim_ref, quiescent=quiescent)
