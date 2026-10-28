"""Launch each unused original Qwen identity as soon as one allowed GPU fits."""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

from proworksim import software_benchmark_dispatch_v066 as policy
from proworksim import software_benchmark_ref_resident_v066 as resident
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = policy.ROOT
OUT = ROOT / "artifacts/software-benchmark-v073/local-expansion-r1"
AUTH = OUT / "authorization.json"
VERSION = "v073-live-capacity-two-original-Qwen-residents-r2"
DELEGATE_SOURCE = ROOT / "tools/launch_additional_qwen_v071.py"
INDICES = (4, 5)
ALLOWED_GPUS = tuple(range(8))
PREFERRED_GPUS = (7, 0)
MAX_LIVE = 4


def original_launcher():
    spec = importlib.util.spec_from_file_location("v073_frozen_v071_launcher", DELEGATE_SOURCE)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def ordinary_user():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("Only the original ordinary-user model lifecycle is authorized")


def selected_indices(indices=None):
    values = list(INDICES if indices is None else indices)
    if not values or len(values) != len(set(values)) or any(type(i) is not int or i not in INDICES for i in values):
        raise ValueError("Only the original unused model identities 4 and 5 may be selected")
    return values


def choose_card(cards, active):
    used = {item["gpu_uuid"] for item in active}
    eligible = [card for card in cards if card["gpu_index"] in ALLOWED_GPUS
                and card["gpu_uuid"] not in used and card["free_mib"] >= resident.MINIMUM_FREE_MIB
                and resident.GPU_UUID.fullmatch(card["gpu_uuid"])]
    if len({card["gpu_uuid"] for card in eligible}) != len(eligible):
        raise ValueError("Ambiguous capacity observation contains duplicate GPU UUIDs")
    priority = {number: index for index, number in enumerate(PREFERRED_GPUS)}
    eligible.sort(key=lambda card: (priority.get(card["gpu_index"], 2), -card["free_mib"], card["gpu_index"]))
    return eligible[0] if eligible else None


def fixed_authority():
    return {"status": "approved", "version": VERSION, "source": reference(__file__),
        "existing_scope": reference(policy.AUTHORIZATION_FILE),
        "predecessor_launcher": reference(DELEGATE_SOURCE),
        "original_resident_source": reference(resident.__file__),
        "allowed_new_model_indices": list(INDICES), "allowed_gpu_indices": list(ALLOWED_GPUS),
        "preferred_gpu_indices": list(PREFERRED_GPUS), "maximum_live_residents": MAX_LIVE,
        "maximum_new_residents": 2, "original_physical_identity_total": 6,
        "memory_GiB_per_resident": 96, "CPU_per_resident": 12,
        "combined_CPU_memory_cap": [152, 832], "minimum_free_mib": resident.MINIMUM_FREE_MIB,
        "gpu_memory_utilization": 0.6, "context": 131072, "maximum_output": 32768,
        "original_server_arguments": {str(i): resident.server_arguments(resident.PORTS[i]) for i in INDICES},
        "gpu_selection": "inside_original_allocation_lock_immediately_before_make_spec",
        "one_available_card_is_sufficient": True, "existing_units_restarted": False,
        "successful_launches_rolled_back": False, "shared_host_configuration_changed": False}


def validate_authorization():
    value = policy.load(reference(AUTH))
    if any(value.get(key) != expected for key, expected in fixed_authority().items()):
        raise ValueError("The exact capacity-based ordinary-user residency authority changed")
    return reference(AUTH)


def prepare():
    """Seal capability scope without querying GPUs or reserving any resource."""
    ordinary_user()
    policy.require_v066_allowed("v066.model.start")
    base = original_launcher()
    base.validate_active(base.active_original_residents())
    if AUTH.exists():
        return {"authorization": validate_authorization(), "status": "already_prepared", "services_started": 0}
    if not all(base.unused_identity(index) for index in INDICES):
        raise ValueError("Both original identities must be unused when first authorizing this supplement")
    OUT.mkdir(parents=True, exist_ok=True)
    ref = write_new(AUTH, {**fixed_authority(), "prepared_unix": time.time(),
        "user_authorization": "按实际容量立即使用允许显卡提升本地并发；仅原未消费身份4/5、最终最多四驻留",
        "new_neutral_probe_max_calls_per_resident": 1, "new_neutral_probe_max_tokens_per_resident": 2048,
        "readiness_and_cleanup": "unchanged original resident lifecycle and primary coordinator"})
    return {"authorization": ref, "services_started": 0, "GPU_queries": 0, "resource_reservations_created": 0}


def launch_one(index):
    ordinary_user()
    selected_indices([index])
    policy.require_v066_allowed("v066.model.start")
    auth_ref = validate_authorization()
    base = original_launcher()
    with (resident.RUNS / "allocation.lock").open("a+b") as allocation:
        fcntl.flock(allocation, fcntl.LOCK_EX)
        active = base.active_original_residents()
        base.validate_active(active)
        if not base.unused_identity(index):
            return {"index": index, "status": "identity_already_consumed_no_replay"}
        if len(active) >= MAX_LIVE:
            raise policy.ResourceBusy("The four-live-resident ceiling is occupied")
        card = choose_card(resident.gpu_capacity(), active)
        if card is None:
            raise policy.ResourceBusy("No allowed unowned GPU currently meets original capacity; identity remains unused")
        if not resident.shared_capacity_for(1):
            raise policy.ResourceBusy("Original shared memory/disk floor prevents this resident")
        spec = resident.make_spec(index, card)
        command = resident.unit_command(spec)
        folder = Path(spec["root"])
        write_new(folder / "unit-launch-intent.json", {"supplement": auth_ref,
            "specification": reference(folder / "spec.json"), "command": command,
            "actual_GPU_capacity_observation": card, "actual_gpu_uuid": card["gpu_uuid"],
            "existing_units_restarted": False, "other_successful_launches_rolled_back": False})
        try:
            response = subprocess.run(command, env=resident.user_manager_environment(),
                                      capture_output=True, text=True, timeout=30)
            value = {"status": "launch_requested" if response.returncode == 0 else "launch_failed_identity_consumed",
                "returncode": response.returncode, "stdout": response.stdout, "stderr": response.stderr}
        except Exception as error:
            value = {"status": "launch_outcome_unknown_identity_consumed",
                     "error": {"type": type(error).__name__, "message": str(error)}}
        value.update(index=index, unit=spec["unit"], supplement=auth_ref,
                     actual_gpu_index=card["gpu_index"], actual_gpu_uuid=card["gpu_uuid"],
                     model_readiness_not_claimed=True, successful_other_launches_unchanged=True)
        write_new(folder / "unit-launch-result.json", value)
        return value


def launch(indices=None):
    ordinary_user()
    outcomes = {}
    for index in selected_indices(indices):
        try:
            outcomes[str(index)] = launch_one(index)
        except policy.ResourceBusy as error:
            outcomes[str(index)] = {"status": "waiting_for_capacity", "reason": str(error),
                                   "identity_unconsumed": original_launcher().unused_identity(index)}
        except Exception as error:
            outcomes[str(index)] = {"status": "launch_blocked", "error": str(error),
                                   "identity_unconsumed": original_launcher().unused_identity(index)}
    return {"version": VERSION, "residents": outcomes, "maximum_live_residents": MAX_LIVE,
            "existing_services_stopped_or_restarted": False, "successful_launch_rollback": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--launch", action="store_true")
    parser.add_argument("--index", type=int, action="append", choices=INDICES)
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else launch(args.index), ensure_ascii=False))
