"""Qualified native r2 controller routing around the unchanged v055 host runner."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from proworksim import software_benchmark_runner_v055 as original
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_bytes())
    activation_ref = config["solver_activation"]
    activation = json.loads(checked(activation_ref).read_bytes())
    if (config["arm"] not in {"REF", "MATCH"} or activation.get("admitted") is not True
            or activation.get("version") != "v055-native-solver-activation-r2"
            or set(activation.get("arms", [])) != {"REF", "MATCH"}
            or activation["runtime_revision"] != config["runtime_revision"]):
        raise ValueError("Only independently qualified native REF/MATCH r2 may enter")
    for item in activation["files"]:
        checked(item)
    entry = checked(activation["controller_entrypoint"])
    if (activation["controller_entrypoint"] not in activation["files"]
            or entry.name != "run_deepseek_controller_v055_r2.py"):
        raise ValueError("Actual r2 controller entry is not in its immutable source seal")
    if json.loads(checked(activation["qualification"]).read_bytes()).get("passed") is not True:
        raise ValueError("The native r2 qualification did not pass")
    previous = original.direct_environment_command
    routed = []

    def direct_with_r2_controller(command):
        command = list(map(str, command))
        old_entry = str(original.ROOT / "tools/run_deepseek_controller_v055.py")
        if command.count(old_entry) != 1:
            raise ValueError("Unexpected original controller invocation; no broad argv rewrite")
        command[command.index(old_entry)] = str(entry)
        routed.append(command)
        return previous(command)

    # This is a private once-only episode process, never the shared coordinator
    # or an existing model worker. Every other host-runner function is original.
    original.direct_environment_command = direct_with_r2_controller
    intent = write_new(args.output.parent / "solver-routing.json", {
        "version": "v055-native-controller-routing-r2", "solver_activation": activation_ref,
        "config": reference(args.config), "controller_entrypoint": activation["controller_entrypoint"],
        "runtime_revision": activation["runtime_revision"], "original_runner_implementation_unchanged": True,
        "model_calls_by_wrapper": 0, "original_slot_and_budget_unchanged": True})
    try:
        result = original.run(config, args.output)
    finally:
        original.direct_environment_command = previous
    if result["status"] == "closed" and len(routed) != 1:
        raise RuntimeError("A closed native r2 episode requires its one exact controller routing")
    write_new(args.output.parent / "solver-routing-result.json", {
        "routing_intent": intent, "result": reference(args.output / "result.json"),
        "actual_controller_routing_count": len(routed), "runtime_revision": activation["runtime_revision"]})
    print(json.dumps({key: result[key] for key in ("status", "slot_id", "condition_id")}))
    return 0 if result["status"] == "closed" else 75


if __name__ == "__main__":
    raise SystemExit(main())
