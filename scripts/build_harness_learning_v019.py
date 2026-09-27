"""Bind unchanged v0.18 work budgets to measured prefix/replica execution."""

import argparse
import copy
from pathlib import Path

from proworksim.candidate_runtime_v019 import candidate_profile
from proworksim.storage import json_bytes, read_json
from scripts.build_harness_learning_v018 import (
    build_protocols as previous_protocols,
    support_protocol as previous_support,
)
from scripts.build_harness_study_v016 import ref

VERSION = "harness-direct-learning-v0.19"
PARALLEL = {
    "version": "fixed-window-two-replicas-v0.19",
    "replicas": 2,
    "partition": "alternate_slots_last_slot_on_parent",
    "rank_formula": "(global_index + 1 - slot_count) % 2",
    "merge_order": "original_slot_order",
    "parameter_updates": "parent_once_after_complete_window",
    "replica_optimizer": False,
}


def optimized_profile(h1, optimized_devices=None):
    original = h1["runtime"]["profile"]
    return candidate_profile(
        original["candidate_id"], dtype=original["dtype"],
        devices=original["devices"] if optimized_devices is None else optimized_devices
    )


def _stage(protocol, h1, admission, *, parallel, replicas=2, optimized_devices=None):
    if type(replicas) is not int or replicas not in (1, 2):
        raise ValueError("Declare one or two sampling replicas before any migration work")
    result = copy.deepcopy(protocol)
    result.update(
        version=VERSION,
        stage="H2_v019" if parallel else "ID_support_v019",
        experiment_id=protocol["experiment_id"].replace("v018", "v019"),
        runtime={"kind": "qwen_hybrid_optimized", "profile": optimized_profile(h1, optimized_devices)},
        sampling_replicas=replicas if parallel else 1,
        optimization_admission=copy.deepcopy(admission),
        numeric_gate="Explicit optimized runtime profile; unchanged full-original-input max logprob tolerance .02 / mean .002. No profile fallback or outcome-driven tolerance change.",
        collector="proworksim.harness_parallel_v019:collect_window" if parallel and replicas == 2
        else "proworksim.harness_collection:collect_window",
        execution_revision={
            "scope": f"New Gamma: explicit optimized profile and {replicas if parallel else 1} fixed current-policy sampling process(es). Original worlds, slots, seeds, budgets, rewards and probability tolerances are unchanged.",
            "learning": "One parent actor/critic/optimizer; original full-input probability replay, one update only after complete window. No replica optimizer or asynchronous policy updates.",
            "resources": "Every sampler uses the explicitly benchmarked device count; it cannot change after sampling starts. Projects run after learning ends on the parent lane.",
            "support": "Separate final-current-policy density remains serial, sixteen fixed slots in one window, zero updates and no O4.",
        },
    )
    if not parallel:
        result["pilot_sampling_replicas"] = replicas
    if parallel and replicas == 2:
        result["parallel_collection"] = copy.deepcopy(PARALLEL)
    for window in result["windows"]:
        window["window_id"] = window["window_id"].replace("v018", "v019")
        window["stage"] = window["stage"].replace("v018", "v019")
        window["sampling_replicas"] = replicas if parallel else 1
        if parallel and replicas == 2:
            window["parallel_collection"] = copy.deepcopy(PARALLEL)
    gate = result.get("launch_gate")
    if gate:
        gate["version"] = gate["version"].replace("v0.18", "v0.19")
    return result


def build_protocols(h1, harness, selection_ref, optimization_admission, *, replicas=2,
                    optimized_devices=None):
    return tuple(
        _stage(p, h1, optimization_admission, parallel=True, replicas=replicas,
               optimized_devices=optimized_devices)
        for p in previous_protocols(h1, harness, selection_ref)
    )


def support_protocol(h1, harness, selection_ref, optimization_admission, *, replicas=2,
                     optimized_devices=None):
    return _stage(
        previous_support(h1, harness, selection_ref), h1, optimization_admission, parallel=False,
        replicas=replicas, optimized_devices=optimized_devices
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--optimization-admission", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replicas", type=int, choices=(1, 2), required=True)
    parser.add_argument("--devices", type=int, help="Explicit benchmarked devices per sampler; default keeps the H1 count")
    parser.add_argument("--completed-pilot", type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError("New protocol output required")
    from proworksim.harness_admission import checked_ref, require
    from proworksim.harness_learning_admission import validate_h2_launch

    selection = read_json(args.selection)
    choice = selection.get("selected")
    require(selection.get("status") == "selected" and isinstance(choice, dict),
            "Final original H1 selection required")
    require(checked_ref(choice.get("protocol_ref")) == args.protocol.resolve(),
            "Protocol is not the original actually selected H1 launch")
    h1 = read_json(args.protocol)
    admission = ref(args.optimization_admission)
    migration, pilot = build_protocols(h1, choice["harness"], ref(args.selection), admission,
                                       replicas=args.replicas, optimized_devices=args.devices)
    owner = read_json(Path(choice["run_root"]) / "resident/owner.json")
    base = owner["base_identity"]
    validate_h2_launch(migration, model_path=base["path"],
                       weight_manifest=checked_ref(base["manifest"]))
    density = support_protocol(h1, choice["harness"], ref(args.selection), admission,
                               replicas=args.replicas, optimized_devices=args.devices)
    if args.completed_pilot is not None:
        root = args.completed_pilot.resolve()
        density["launch_gate"] = {
            "version": "id-support-density-v0.19", "state": "admitted",
            "pilot_report": ref(root / "online/report.json"),
        }
        validate_h2_launch(density, model_path=base["path"],
                           weight_manifest=checked_ref(base["manifest"]),
                           restore_checkpoint=root / "online/window-5/checkpoint")
    args.output.mkdir(parents=True)
    for name, body in [("migration", migration), ("pilot-planned", pilot),
                       ("support-density-planned", density)]:
        (args.output / (name + ".json")).write_bytes(json_bytes(body))
    print(json_bytes({"status": "generated_not_started", "migration": 8, "pilot": 118,
                      "later_support_density": 16, "auto_O4": False,
                      "optimization_admission": admission, "sampling_replicas": args.replicas,
                      "devices_per_sampler": migration["runtime"]["profile"]["devices"]}).decode())


if __name__ == "__main__":
    main()
