"""Add up to two original unused Qwen residents without restarting live work."""
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
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = policy.ROOT
OUT = ROOT / "artifacts/software-benchmark-v071/local-expansion-r1"
VERSION = "v071-two-additional-original-Qwen-residents-r1"
PREDECESSOR = ROOT / "tools/launch_additional_qwen_v070.py"
TARGETS = {
    4: {"gpu_index": 1, "gpu_uuid": "GPU-1e059756-8c2e-bbd9-7aba-7e08af2be25c"},
    5: {"gpu_index": 5, "gpu_uuid": "GPU-1201ff43-02be-5111-36db-e33818319c6b"},
}
BASELINE_INDICES = {1, 3}
MAX_LIVE = 4


def _predecessor():
    spec = importlib.util.spec_from_file_location("v071_original_additional_launcher", PREDECESSOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def active_original_residents():
    # Preserve v070's conservative rule: a resident leaves the active set only
    # after both child-exit proof and the original reservation-release marker.
    return _predecessor().active_original_residents()


def selected_indices(indices=None):
    selected = list(TARGETS) if indices is None else list(indices)
    if not selected or len(set(selected)) != len(selected) or any(type(i) is not int or i not in TARGETS for i in selected):
        raise ValueError("Only original unused model identities 4 and 5 may be selected")
    return selected


def authorization_file(index):
    return OUT / f"model-{index}-authorization.json"


def unused_identity(index):
    return not ((resident.RUNS / f"model-{index}").exists()
                or (policy.BATCH_ROOT / "resource-claims" / f"model-{index}.json").exists())


def ordinary_user():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("Only the existing ordinary-user model lifecycle is authorized")


def validate_active(active):
    indices = [item["index"] for item in active]
    if (len(indices) != len(set(indices)) or len(indices) > MAX_LIVE
            or not set(indices) <= BASELINE_INDICES | set(TARGETS)):
        raise ValueError("Unproven predecessor cleanup or an unexpected residency prevents this supplement")
    uuids = [item["gpu_uuid"] for item in active]
    if len(uuids) != len(set(uuids)):
        raise ValueError("Original live model GPU ownership is ambiguous")
    return indices


def validate_authorization(index, value):
    expected = TARGETS[index]
    if (value.get("status") != "approved" or value.get("version") != VERSION
            or value.get("source") != reference(__file__)
            or value.get("predecessor_launcher") != reference(PREDECESSOR)
            or value.get("original_resident_source") != reference(resident.__file__)
            or value.get("existing_scope") != reference(policy.AUTHORIZATION_FILE)
            or value.get("index") != index or value.get("gpu_index") != expected["gpu_index"]
            or value.get("gpu_uuid") != expected["gpu_uuid"]
            or value.get("unit") != resident.unit_name(index)
            or value.get("maximum_live_residents") != MAX_LIVE
            or value.get("maximum_new_residents") != 2
            or value.get("memory_GiB") != 96 or value.get("CPU") != 12
            or value.get("original_shared_CPU_memory_cap") != [152, 832]
            or value.get("original_server_arguments") != resident.server_arguments(resident.PORTS[index])):
        raise ValueError("The exact additional residency grant changed")
    baseline = value.get("baseline_residents", {})
    if set(baseline) != {str(i) for i in BASELINE_INDICES}:
        raise ValueError("The original live baseline was not bound")
    for baseline_index, ref in baseline.items():
        if checked(ref) != resident.RUNS / f"model-{baseline_index}" / "spec.json":
            raise ValueError("A baseline reference belongs to another resident")
    return value


def prepare(indices=None):
    """Read capacity and write each exact grant; do not reserve or start anything."""
    ordinary_user()
    policy.require_v066_allowed("v066.model.start")
    selected = selected_indices(indices)
    active = active_original_residents()
    active_indices = validate_active(active)
    if not BASELINE_INDICES <= set(active_indices):
        raise ValueError("Prepare against the original live models 1 and 3")
    cards = resident.gpu_capacity()
    result = {}
    for index in selected:
        path = authorization_file(index)
        if path.exists():
            value = validate_authorization(index, policy.load(reference(path)))
            result[str(index)] = {"status": "already_prepared", "authorization": reference(path),
                                  "identity_unconsumed": unused_identity(index), "gpu_index": value["gpu_index"]}
            continue
        if not unused_identity(index):
            result[str(index)] = {"status": "identity_already_consumed_no_replay"}
            continue
        target = TARGETS[index]
        card = next((c for c in cards if all(c[k] == v for k, v in target.items())), None)
        value = {"status": "approved", "version": VERSION, "prepared_unix": time.time(),
            "user_authorization": "提高本地实验并发；容量满足即可使用空闲显卡；仅新增至四个驻留匹配四个任务future",
            "existing_scope": reference(policy.AUTHORIZATION_FILE), "source": reference(__file__),
            "predecessor_launcher": reference(PREDECESSOR),
            "original_resident_source": reference(resident.__file__),
            "index": index, **target, "unit": resident.unit_name(index),
            "baseline_residents": {str(i): reference(resident.RUNS / f"model-{i}" / "spec.json")
                                   for i in sorted(BASELINE_INDICES)},
            "card_at_preparation": card, "capacity_required_again_at_launch": True,
            "maximum_live_residents": MAX_LIVE, "maximum_new_residents": 2,
            "original_physical_identity_total": 6, "memory_GiB": 96, "CPU": 12,
            "original_shared_CPU_memory_cap": [152, 832],
            "original_server_arguments": resident.server_arguments(resident.PORTS[index]),
            "original_model_context": 131072, "original_output_limit": 32768,
            "gpu_memory_utilization": 0.6,
            "new_neutral_probe_max_calls": 1, "new_neutral_probe_max_tokens": 2048,
            "model_visible_configuration_changed": False, "existing_model_or_episode_restarted": False,
            "host_configuration_changed": False, "temporary_capacity_failure_consumes_identity": False,
            "successful_launch_rolled_back_for_other_failure": False,
            "coordinator": "original v068 primary discovers ready.json; its four-task ceiling remains unchanged",
            "cleanup": "unchanged original resident lifecycle and primary shutdown own this exact unit"}
        OUT.mkdir(parents=True, exist_ok=True)
        ref = write_new(path, value)
        result[str(index)] = {"status": "prepared", "authorization": ref,
                              "capacity_observed": card is not None, "identity_unconsumed": True}
    return {"version": VERSION, "residents": result, "resource_reservations_created": 0,
            "services_started": 0, "existing_services_changed": False}


def launch_one(index):
    ordinary_user()
    selected_indices([index])
    policy.require_v066_allowed("v066.model.start")
    auth_ref = reference(authorization_file(index))
    validate_authorization(index, policy.load(auth_ref))
    # Share the resident allocator's original lock, including its ordinary
    # coordinator caller.  The physical reservation still uses the original
    # aggregate CPU/RAM allocation lock inside make_spec.
    with (resident.RUNS / "allocation.lock").open("a+b") as allocation:
        fcntl.flock(allocation, fcntl.LOCK_EX)
        active = active_original_residents()
        validate_active(active)
        if not unused_identity(index):
            return {"status": "identity_already_consumed_no_replay", "index": index}
        if len(active) >= MAX_LIVE:
            raise policy.ResourceBusy("The four-live-resident ceiling is already occupied")
        target = TARGETS[index]
        if target["gpu_uuid"] in {item["gpu_uuid"] for item in active}:
            raise policy.ResourceBusy("The selected GPU UUID already has an active owned resident")
        card = next((c for c in resident.gpu_capacity() if all(c[k] == v for k, v in target.items())), None)
        if card is None:
            raise policy.ResourceBusy("GPU capacity changed; retain the unused identity for a later attempt")
        if not resident.shared_capacity_for(1):
            raise policy.ResourceBusy("Shared memory/disk floor does not allow this additional resident")
        spec = resident.make_spec(index, card)
        command = resident.unit_command(spec)
        folder = Path(spec["root"])
        write_new(folder / "unit-launch-intent.json", {"supplement": auth_ref,
            "specification": reference(folder / "spec.json"), "command": command,
            "existing_model_units_restarted": False, "other_new_launches_rolled_back": False})
        try:
            answer = subprocess.run(command, env=resident.user_manager_environment(),
                                    capture_output=True, text=True, timeout=30)
            result = {"status": "launch_requested" if answer.returncode == 0 else "launch_failed_identity_consumed",
                "returncode": answer.returncode, "stdout": answer.stdout, "stderr": answer.stderr}
        except Exception as error:
            result = {"status": "launch_outcome_unknown_identity_consumed",
                      "error": {"type": type(error).__name__, "message": str(error)}}
        result.update(index=index, unit=spec["unit"], supplement=auth_ref,
                      model_readiness_not_claimed=True, successful_other_launches_unchanged=True)
        write_new(folder / "unit-launch-result.json", result)
        return result


def launch(indices=None):
    """Attempt independent grants; never undo an already accepted launch."""
    ordinary_user()
    outcomes = {}
    for index in selected_indices(indices):
        try:
            outcomes[str(index)] = launch_one(index)
        except policy.ResourceBusy as error:
            outcomes[str(index)] = {"status": "waiting_for_capacity", "reason": str(error),
                                   "identity_unconsumed": unused_identity(index)}
        except Exception as error:
            outcomes[str(index)] = {"status": "launch_blocked", "error": str(error),
                                   "identity_unconsumed": unused_identity(index)}
    return {"version": VERSION, "residents": outcomes, "maximum_live_residents": MAX_LIVE,
            "existing_services_stopped_or_restarted": False, "successful_launch_rollback": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--launch", action="store_true")
    parser.add_argument("--index", action="append", type=int, choices=sorted(TARGETS))
    arguments = parser.parse_args()
    print(json.dumps(prepare(arguments.index) if arguments.prepare else launch(arguments.index), ensure_ascii=False))
