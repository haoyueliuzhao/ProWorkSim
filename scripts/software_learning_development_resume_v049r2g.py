"""Resource-only continuation of the two original, never-started DB slots.

Reuse frozen r2 function code with private dependency dictionaries. No historical
module globals or source bytes are changed, including the nested v048/v037 GPU
filters. The original supervisor's one literal worker module is translated at
its process-launch boundary; every other argument and guard remains intact.
"""
from __future__ import annotations

import argparse
import copy
import signal
import sys
import time
from pathlib import Path
from types import FunctionType, SimpleNamespace

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import worker_identity
from proworksim.storage import digest, read_json
from scripts import software_learning_development_resume_v049r2 as prior
from scripts import software_learning_development_resume_supervisor_v049r2 as prior_supervisor
from scripts import software_organization_v048 as inherited
from scripts.run_ne_v021 import reference, write

VERSION = "software-learning-original-B-development-resume-v0.49-r2g"
MODULE = "scripts.software_learning_development_resume_v049r2g"
SOURCE, WORKERS, LIMITS = prior.SOURCE, prior.WORKERS, prior.LIMITS
PROTOCOL = SOURCE / "docs/experiments/software-learning-v049-development-resume-r2g-protocol.md"
CONTROLS = SOURCE / "docs/experiments/software-learning-v049-development-resume-r2g-cpu-controls.json"


def bind(function, **dependencies):
    """Keep the exact inherited code and isolate only named global dependencies."""
    bound = FunctionType(function.__code__, {**function.__globals__, **dependencies},
                         function.__name__, function.__defaults__, function.__closure__)
    bound.__kwdefaults__ = function.__kwdefaults__
    return bound


def gpu_scope(indices):
    indices = tuple(indices)
    if (not indices or any(type(i) is not int or i < 0 for i in indices)
            or tuple(sorted(set(indices))) != indices):
        raise ValueError("Freeze unique physical GPU indices in ascending order")
    return indices


def resources(indices):
    indices = gpu_scope(indices)
    return SimpleNamespace(
        allowed_resources=bind(inherited.allowed_resources, GPU_ORDER=indices),
        worker_env=bind(inherited.worker_env, GPU_ORDER=indices),
        available_cards=bind(inherited.available_cards, GPU_ORDER=indices))


def source_files():
    files = prior.source_files()
    for path in (Path(__file__), SOURCE / "tests/test_software_learning_development_resume_v049r2g.py", PROTOCOL, CONTROLS):
        files[str(path.relative_to(SOURCE))] = digest(path.read_bytes())
    return files


def waiting_receipt(root):
    """Reject any attempted slot; a stopped resource wait is not model work."""
    root = Path(root).resolve()
    plan, supervisor = read_json(root / "plan.json"), read_json(root / "supervisor.json")
    prior._check_seal(plan, "plan_sha256")
    if (plan.get("version") != prior.VERSION or plan.get("workers") != list(WORKERS)
            or plan.get("limits") != LIMITS or plan.get("new_budget_caps") != prior.budget_caps()
            or plan.get("gpu_preference") != list(prior.GPU_ORDER)
            or supervisor.get("source") != plan["source"] or not supervisor.get("ended_at")
            or supervisor.get("status") not in {"interrupted", "closed_with_unknowns"}
            or set(supervisor.get("states", {})) != set(WORKERS)
            or any(supervisor.get(key, 0) != 0 for key in ("closed_worker_gpu_seconds", "running_worker_gpu_seconds"))):
        raise ValueError("Require the terminal original r2 resource wait with zero GPU-worker cost")
    observer = supervisor.get("observer_pid")
    if observer and worker_identity(observer).get("alive") is not False:
        raise ValueError("The original waiting supervisor must no longer be alive")
    for name, state in supervisor["states"].items():
        if (state.get("attempted") is not False or state.get("pid") or state.get("started_at")
                or state.get("elapsed_gpu_seconds", 0) != 0 or (root / name).exists()):
            raise ValueError("An attempted/prepared DB slot cannot be replayed through a resource revision")
    prior.previous.original_source_agreement(plan, SOURCE)
    return {"root": str(root), "plan": reference(root / "plan.json"),
            "supervisor": reference(root / "supervisor.json"),
            "retained_waiting_files": [reference(path) for path in sorted(root.rglob("*")) if path.is_file()],
            "new_model_workers": 0, "new_model_calls": 0, "gpu_worker_seconds": 0}


def prepare(root, *, waiting_root, controls=CONTROLS):
    root, waiting_root = Path(root).resolve(), Path(waiting_root).resolve()
    if root.exists() or root in waiting_root.parents or waiting_root in root.parents:
        raise FileExistsError("Use a new independent resource-continuation root")
    source = code_identity()
    if source.get("code_dirty") is not False:
        raise ValueError("Commit the resource adapter and protocol before model work")
    receipt = waiting_receipt(waiting_root)
    old = read_json(waiting_root / "plan.json")
    proof = read_json(controls)
    prior._check_seal(proof, "sha256")
    indices = gpu_scope(proof["gpu_preference"])
    if (proof.get("passed") is not True or proof.get("waiting_receipt") != receipt
            or any(proof.get(k) != 0 for k in ("new_model_calls", "new_gpu_workers", "new_backward_calls"))):
        raise ValueError("Require the finite resource controls bound to the untouched waiting evidence")
    plan = copy.deepcopy(old)
    plan.update(version=VERSION, created_at=time.time(), source=source, source_files=source_files(),
                gpu_preference=list(indices), resource_resume_of=receipt,
                resource_cpu_controls=reference(controls), resource_protocol=reference(PROTOCOL),
                prior_artifact_roots=prior.original.inherited.support.dense._artifact_roots(
                    [*old["prior_artifact_roots"], waiting_root]))
    plan.pop("plan_sha256")
    plan = prior._seal(plan, "plan_sha256")
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    raw = read_json(Path(root) / "plan.json")
    indices = gpu_scope(raw["gpu_preference"])
    plan = bind(prior.frozen, VERSION=VERSION, GPU_ORDER=indices, source_files=source_files)(root)
    receipt = waiting_receipt(plan["resource_resume_of"]["root"])
    if receipt != plan["resource_resume_of"]:
        raise ValueError("Original resource wait evidence changed")
    old = read_json(prior.checked(receipt["plan"]))
    changed = {"version", "created_at", "source", "source_files", "gpu_preference", "plan_sha256",
               "resource_resume_of", "resource_cpu_controls", "resource_protocol", "prior_artifact_roots"}
    if {k: v for k, v in plan.items() if k not in changed} != {k: v for k, v in old.items() if k not in changed}:
        raise ValueError("A resource revision cannot change the scientific inventory or model contract")
    control = read_json(prior.checked(plan["resource_cpu_controls"]))
    if (control.get("gpu_preference") != list(indices) or control.get("waiting_receipt") != receipt
            or plan["resource_protocol"] != reference(PROTOCOL)):
        raise ValueError("Frozen resource authorization changed")
    return plan


def worker_function(indices):
    provider = resources(indices)
    dependency = SimpleNamespace(**{**vars(inherited), **vars(provider)})
    loader = bind(prior.original._load_owner, inherited=dependency)
    original = SimpleNamespace(**{**vars(prior.original), "_load_owner": loader})
    return bind(prior.run_worker, VERSION=VERSION, GPU_ORDER=gpu_scope(indices),
                frozen=frozen, original=original)


def launch(argv, **kwargs):
    old_module = "scripts.software_learning_development_resume_v049r2"
    if len(argv) < 4 or argv[1:4] != ["-m", old_module, "worker"]:
        raise ValueError("Only the inherited DB worker launch may use this resource adapter")
    requested, actual = list(argv), list(argv)
    actual[2] = MODULE
    output = Path(argv[argv.index("--output") + 1])
    write(output.parent / "worker-launch.json", {
        "phase": "before_popen", "recorded_at": time.time(), "source": code_identity(),
        "requested_command": requested, "actual_command": actual,
        "physical_gpu": kwargs["env"]["CUDA_VISIBLE_DEVICES"],
        "scope": "Translate only the inherited r2 DB worker module to the frozen r2g resource adapter. "
                 "The inherited prelaunch intent names r2; this receipt records the actual Popen command. "
                 "This prelaunch record does not itself claim that a process started.",
    })
    # The inherited supervisor stores this same list in states.command. Keep
    # its next publication consistent with the actual command, also on failure.
    argv[2] = MODULE
    return prior_supervisor.subprocess.Popen(argv, **kwargs)


def supervisor_function(indices):
    provider = resources(indices)
    process = SimpleNamespace(**{**vars(prior_supervisor.subprocess), "Popen": launch})
    return bind(prior_supervisor.supervise, VERSION=VERSION + "-supervisor",
                host=sys.modules[__name__], subprocess=process, **vars(provider))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "supervise", "worker"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--waiting-root", type=Path)
    parser.add_argument("--controls", type=Path, default=CONTROLS)
    parser.add_argument("--worker", choices=WORKERS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, prior.received_signal)
    if args.command == "prepare":
        if args.waiting_root is None:
            parser.error("prepare requires --waiting-root")
        prepare(args.run_root, waiting_root=args.waiting_root, controls=args.controls)
    else:
        plan = frozen(args.run_root)
        if args.command == "supervise":
            supervisor_function(plan["gpu_preference"])(args.run_root)
        else:
            if args.worker is None or args.output is None:
                parser.error("worker requires --worker and --output")
            worker_function(plan["gpu_preference"])(args.run_root, args.worker, args.output)


if __name__ == "__main__":
    main()
