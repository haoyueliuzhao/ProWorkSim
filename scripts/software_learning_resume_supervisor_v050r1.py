"""Privately bind the original v050 supervisor to its one unstarted continuation."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import signal
import time
from types import SimpleNamespace

from proworksim.audit import code_identity
from scripts import software_learning_resume_v050r1 as host
from scripts import software_learning_supervisor_v050 as previous
from scripts.software_learning_development_resume_v049r2g import bind
from scripts.run_ne_v021 import write

VERSION = "software-learning-resume-supervisor-v0.50-r1"
SOURCE, WORKERS, LIMITS = host.SOURCE, host.WORKERS, host.LIMITS
GPU_ORDER = host.GPU_ORDER


def initial_states(plan):
    states = bind(previous.initial_states, host=host)(plan)
    states["s_star"].update(status="complete", attempted=False,
        original_complete_state_reused=True, elapsed_gpu_seconds=0,
        generation_slots_executed=0, original_report=host.reference(
            Path(plan["original_root"]) / "s_star/actual/report.json"))
    return states


def launch(argv, **kwargs):
    if argv[1:4] != ["-m", "scripts.software_learning_v050", "worker"]:
        raise ValueError("Only the inherited v050 worker command can be adapted")
    worker = argv[argv.index("--worker") + 1]
    if worker not in WORKERS or worker == "s_star":
        raise ValueError("Never launch the retained S* initializer or any extra worker")
    requested, actual = list(argv), list(argv)
    actual[2] = host.MODULE
    folder = Path(argv[argv.index("--output") + 1]).parent
    write(folder / "worker-launch.json", {"phase": "before_popen", "recorded_at": time.time(),
        "source": code_identity(), "requested_command": requested, "actual_command": actual,
        "physical_gpu": kwargs["env"]["CUDA_VISIBLE_DEVICES"],
        "scope": "Only the host module differs; original guards, slot budget, state and inventory remain bound."})
    # The supervisor stores this very list; subsequent publications match Popen.
    argv[2] = host.MODULE
    return previous.subprocess.Popen(argv, **kwargs)


def supervisor_function():
    dependencies = {"VERSION": VERSION, "host": host, "SOURCE": SOURCE, "WORKERS": WORKERS,
        "LIMITS": LIMITS, "initial_states": initial_states,
        "subprocess": SimpleNamespace(**{**vars(previous.subprocess), "Popen": launch})}
    for name in ("eligible_workers", "apply_support_gate", "apply_not_applicable", "read_direction",
                 "training_stop_reason", "task_stop_reason"):
        dependencies[name] = bind(getattr(previous, name), host=host, WORKERS=WORKERS, LIMITS=LIMITS)
    return bind(previous.supervise, **dependencies)


def supervise(root):
    return supervisor_function()(root)


def contract():
    return {"original_supervisor_code_object_identical": supervisor_function().__code__ is previous.supervise.__code__,
        "original_supervisor_globals_unchanged": previous.host is host.original,
        "gpu_preference": list(GPU_ORDER), "limits": copy.deepcopy(LIMITS),
        "reused_S_star_new_worker_cost": 0, "automatic_retries": False}


# Expose the unchanged dependency functions for finite CPU controls.
eligible_workers = bind(previous.eligible_workers, host=host)
apply_support_gate = bind(previous.apply_support_gate, host=host)
apply_not_applicable = bind(previous.apply_not_applicable, host=host)
training_stop_reason = previous.training_stop_reason
task_stop_reason = previous.task_stop_reason


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, host.original.received_signal)
    supervise(args.run_root)


if __name__ == "__main__":
    main()
