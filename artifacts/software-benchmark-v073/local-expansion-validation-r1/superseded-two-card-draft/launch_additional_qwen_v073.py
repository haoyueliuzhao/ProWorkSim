"""Freeze newly available GPU bindings, then reuse the validated v071 launcher."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import time
from types import FunctionType

from proworksim import software_benchmark_dispatch_v066 as policy
from proworksim import software_benchmark_ref_resident_v066 as resident
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = policy.ROOT
OUT = ROOT / "artifacts/software-benchmark-v073/local-expansion-r1"
BINDING = OUT / "gpu-bindings.json"
VERSION = "v073-capacity-selected-two-original-Qwen-residents-r1"
DELEGATE_SOURCE = ROOT / "tools/launch_additional_qwen_v071.py"
PREFERRED_GPU_INDICES = (7, 0)


def original_launcher():
    spec = importlib.util.spec_from_file_location("v073_frozen_v071_launcher", DELEGATE_SOURCE)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def choose_targets(cards, active):
    used = {item["gpu_uuid"] for item in active}
    eligible = [card for card in cards if card["gpu_index"] in range(8) and card["gpu_uuid"] not in used]
    priority = {number: index for index, number in enumerate(PREFERRED_GPU_INDICES)}
    eligible.sort(key=lambda card: (priority.get(card["gpu_index"], 2), -card["free_mib"], card["gpu_index"]))
    if len({card["gpu_uuid"] for card in eligible}) != len(eligible):
        raise ValueError("Ambiguous capacity observation contains duplicate GPU UUIDs")
    if len(eligible) < 2:
        raise policy.ResourceBusy("Two distinct GPUs must meet the unchanged original capacity gate before binding")
    return {index: {"gpu_index": card["gpu_index"], "gpu_uuid": card["gpu_uuid"]}
            for index, card in zip((4, 5), eligible[:2], strict=True)}


def bind_launcher(targets):
    """Clone every local function into one namespace; never modify frozen globals."""
    base = original_launcher()
    namespace = {**vars(base), "OUT": OUT, "VERSION": VERSION,
                 "TARGETS": targets, "__file__": str(Path(__file__).resolve())}
    for name, function in vars(base).items():
        if isinstance(function, FunctionType) and function.__globals__ is vars(base):
            copied = FunctionType(function.__code__, namespace, function.__name__,
                                  function.__defaults__, function.__closure__)
            copied.__kwdefaults__ = function.__kwdefaults__
            copied.__annotations__ = dict(function.__annotations__)
            namespace[name] = copied
    return namespace


def load_bindings():
    value = policy.load(reference(BINDING))
    if (value.get("version") != VERSION or value.get("source") != reference(__file__)
            or value.get("delegate_source") != reference(DELEGATE_SOURCE)
            or value.get("existing_scope") != reference(policy.AUTHORIZATION_FILE)):
        raise ValueError("The exact capacity-selected GPU binding changed")
    targets = {int(index): target for index, target in value["targets"].items()}
    if (set(targets) != {4, 5} or len({t["gpu_uuid"] for t in targets.values()}) != 2
            or any(type(t["gpu_index"]) is not int or t["gpu_index"] not in range(8)
                   or not resident.GPU_UUID.fullmatch(t["gpu_uuid"]) for t in targets.values())):
        raise ValueError("Only two distinct exact original GPU identities may be bound")
    return targets


def prepare(indices=None):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("Only the original ordinary-user deployment is authorized")
    policy.require_v066_allowed("v066.model.start")
    if not BINDING.exists():
        base = original_launcher()
        active = base.active_original_residents()
        base.validate_active(active)
        if not base.BASELINE_INDICES <= {item["index"] for item in active}:
            raise ValueError("Original models 1 and 3 must still form the preparation baseline")
        if not all(base.unused_identity(index) for index in (4, 5)):
            raise ValueError("Only the two unconsumed original residency identities may be rebound")
        cards = resident.gpu_capacity()
        targets = choose_targets(cards, active)
        OUT.mkdir(parents=True, exist_ok=True)
        write_new(BINDING, {"version": VERSION, "prepared_unix": time.time(),
            "source": reference(__file__), "delegate_source": reference(DELEGATE_SOURCE),
            "existing_scope": reference(policy.AUTHORIZATION_FILE), "targets": targets,
            "capacity_observation": cards, "preferred_gpu_indices": list(PREFERRED_GPU_INDICES),
            "shared_resource_or_model_limits_changed": False,
            "old_v071_grants_modified": False, "services_started": 0})
    value = bind_launcher(load_bindings())["prepare"](indices)
    value["gpu_bindings"] = reference(BINDING)
    return value


def launch(indices=None):
    return bind_launcher(load_bindings())["launch"](indices)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--launch", action="store_true")
    parser.add_argument("--index", type=int, action="append", choices=(4, 5))
    args = parser.parse_args()
    print(json.dumps(prepare(args.index) if args.prepare else launch(args.index), ensure_ascii=False))
