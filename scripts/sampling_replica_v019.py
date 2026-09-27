"""One declared read-only sampling child; no learner or optimizer is created."""

import argparse
import os
from pathlib import Path
import time

from proworksim.audit import code_identity
from proworksim.harness_collection import close_prepared_slot, prepare_slot, run_prepared_slot
from proworksim.harness_parallel_v019 import (
    POLL_SECONDS,
    VERSION,
    checked,
    persist_result,
    validate_barrier,
    write,
)
from proworksim.storage import read_json


def run(config):
    from proworksim.sampling_replica_v019 import load_replica

    control, output = Path(config["control"]), Path(config["output"])
    before = code_identity()
    if before != config["source"]:
        raise ValueError("Sampling replica source differs before loading")
    load_started = time.time()
    owner = load_replica(config["snapshot_path"], control / "resident")
    load_seconds = time.time() - load_started
    if owner.freeze_identity() != config["actor_identity"] or owner.window_id != config["window_spec"]["window_id"]:
        raise ValueError("Sampling replica actual actor/window differs")
    initial_guard = owner.verify_sampling_identity()
    resource_before = owner._resource_guard()
    if initial_guard.get("passed") is not True:
        raise ValueError("Sampling replica initial identity guard failed")
    prepared = []
    complete = False
    sampling_started = None
    try:
        for index in config["indices"]:
            prepared.append(prepare_slot(owner, config["window_spec"],
                                         config["window_spec"]["slots"][index], index, output))
        write(control / "prepared.json", {
            "version": VERSION, "actor_identity": owner.freeze_identity(),
            "window_id": owner.window_id, "source": before, "guard": initial_guard,
            "slots": [{"index": item["index"], "spec": item["spec"]} for item in prepared],
        })
        start_path = control / "start.json"
        while not start_path.exists():
            if (control / "abort.json").exists() or os.getppid() != config["parent_pid"]:
                raise RuntimeError("Parent stopped before declaration; replica never sampled")
            time.sleep(POLL_SECONDS)
        start = read_json(start_path)
        checked(start["prepared"], control / "prepared.json")
        declaration = checked(start["declaration"], output / "declaration.json")
        validate_barrier(declaration, config, prepared)
        sampling_started = time.time()
        for item in prepared:
            if (control / "abort.json").exists() or os.getppid() != config["parent_pid"]:
                raise RuntimeError("Parent stopped; remaining assigned slots are not sampled")
            result = run_prepared_slot(owner, item, declaration)
            persist_result(item, result, 1)
        complete = True
    finally:
        for item in prepared:
            close_prepared_slot(item)
        final_guard = owner.verify_sampling_identity()
        after = code_identity()
        write(control / "guard.json", {
            "version": VERSION, "passed": complete and final_guard.get("passed") is True and before == after,
            "actor_identity": owner.freeze_identity(), "source_before": before, "source_after": after,
            "initial": initial_guard, "final": final_guard,
            "cold_model_load_seconds": load_seconds,
            "sampling_seconds": time.time() - sampling_started if sampling_started else None,
            "resource_before": resource_before, "resource_after": owner._resource_guard(),
            "optimizer_owned": False, "all_assigned_slots_attempted_once": complete,
        })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config = read_json(Path(args.config))
    try:
        run(config)
    except BaseException as error:
        write(Path(config["control"]) / "interruption.json",
              {"type": type(error).__name__, "message": str(error)})
        raise


if __name__ == "__main__":
    main()
