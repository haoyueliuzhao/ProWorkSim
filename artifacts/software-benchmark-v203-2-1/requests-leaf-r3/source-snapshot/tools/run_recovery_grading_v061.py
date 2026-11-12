"""Prepare and run only the selected v061 offline environment/score jobs."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import time

from proworksim import software_benchmark_dispatch_v061 as policy
from proworksim import software_benchmark_scorer_v061 as scorer
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

ROOT, BATCH_ROOT = policy.ROOT, policy.BATCH_ROOT
RUN_ROOT = policy.COORDINATOR_RUN_ROOT
VERSION = "v061-bounded-recovery-grading-coordinator-r1"


def load(ref):
    return json.loads(checked(ref).read_bytes())


def retain(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if json.loads(path.read_bytes()) != value:
            raise ValueError("Prepared immutable grading record changed: " + str(path))
        return reference(path)
    return write_new(path, value)


def fixed_python(arguments):
    return [
        str(ROOT / ".venv/bin/python"),
        "-B",
        str(ROOT / "tools/run_offline_scorer_v058.py"),
        *arguments,
    ]


def bootstrap_environment():
    """The host .venv bootstrap must not inherit the private Python 3.12 home."""
    value = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE"):
        value.pop(key, None)
    return value


def prepare_manifest():
    target = RUN_ROOT / "scorer-manifest.json"
    if target.exists():
        return reference(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    command = fixed_python(
        [
            "-c",
            "import json; from proworksim.software_benchmark_scorer_v061 import installation_manifest; print(json.dumps(installation_manifest()))",
        ]
    )
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, check=True, timeout=60,
                               env=bootstrap_environment())
    return write_new(target, json.loads(completed.stdout))


def selected_cpus(lane):
    return policy.cpu_set("grader", lane)


def prepare_controls():
    raise ValueError("The model-memory continuation reuses fourteen completed controls; do not prepare or replay them")


def _historical_prepare_controls_disabled():
    plan = policy.create_plan()
    manifest = prepare_manifest()
    requests = []
    tasks = sorted(
        plan["environments"], key=lambda name: (name != "scikit-learn__scikit-learn-14894", name)
    )
    for task in tasks:
        for index, kind in enumerate(("gold", "empty")):
            key = "control-" + task + "-" + kind
            folder = BATCH_ROOT / "grading" / key
            value = {
                "version": scorer.VERSION,
                "resource_key": key,
                "plan": reference(policy.PLAN_FILE),
                "original_config": plan["environments"][task]["original_config"],
                "patch_kind": kind,
                "limits": scorer.LIMITS,
                "scorer_manifest": manifest,
                "cpuset_cpus": selected_cpus(index),
                "directory": str(folder),
                "candidate_lock": None,
            }
            requests.append(retain(folder / "request.json", value))
    retain(
        BATCH_ROOT / "control-plan.json",
        {"version": VERSION, "plan": reference(policy.PLAN_FILE), "requests": requests},
    )
    return requests


def capacity_available():
    available = next(
        int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    return available >= 160 * 1024**3 and shutil.disk_usage(ROOT).free >= 256 * 1024**3


def run_request(request_ref, cancel_event=None):
    request = load(request_ref)
    operation = "v061.control" if request["resource_key"].startswith("control-") else "v061.score"
    policy.require_v061_allowed(operation)
    folder = Path(request["directory"])
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "completion.json").exists():
        return load(reference(folder / "completion.json"))
    if (folder / "started.json").exists():
        return {"status": "entered_attempt_not_replayed", "resource_key": request["resource_key"]}
    while not capacity_available():
        if cancel_event is not None and cancel_event.wait(5):
            return {"status": "not_started_cancelled", "resource_key": request["resource_key"]}
        if cancel_event is None:
            time.sleep(5)
    command = fixed_python(
        ["-m", "proworksim.software_benchmark_scorer_v061", "--request", request_ref["path"]]
    )
    started = {
        "version": VERSION,
        "request": request_ref,
        "resource_key": request["resource_key"],
        "started_unix": time.time(),
        "command": command,
    }
    write_new(folder / "started.json", started)
    process = None
    result = dict(started)
    try:
        with (
            (folder / "stdout.log").open("xb") as stdout,
            (folder / "stderr.log").open("xb") as stderr,
        ):
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
                env=bootstrap_environment(),
            )
            deadline = time.monotonic() + 3900
            while process.poll() is None:
                if cancel_event is not None and cancel_event.wait(1):
                    raise InterruptedError("Coordinator requested owned grader cancellation")
                if cancel_event is None:
                    time.sleep(1)
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(command, 3900)
            result["returncode"] = process.returncode
        result["status"] = "process_exited"
    except Exception as error:
        result.update(
            status="technical_unknown", error={"type": type(error).__name__, "message": str(error)}
        )
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=20)
        result["returncode"] = process.returncode if process else None
    result["finished_unix"] = time.time()
    write_new(folder / "completion.json", result)
    return result


def trustworthy_cleanup(request_ref):
    request = load(request_ref)
    folder = Path(request["directory"])
    if not (folder / "started.json").exists():
        return True
    try:
        quiet = load(reference(folder / "quiescence.json"))
        return (
            quiet.get("resource_key") == request["resource_key"]
            and quiet.get("quiescent") is True
            and quiet.get("cleanup_errors") == []
            and quiet.get("create_result_unknown") is False
        )
    except (OSError, ValueError, KeyError):
        return False


def qualify(task):
    plan_ref = reference(policy.PLAN_FILE)
    plan = load(plan_ref)
    controls = []
    for kind in ("gold", "empty"):
        folder = BATCH_ROOT / "grading" / ("control-" + task + "-" + kind)
        controls.append(
            {
                "patch_kind": kind,
                **{
                    name: reference(folder / (name + ".json"))
                    for name in ("receipt", "quiescence", "completion")
                },
            }
        )
    value = {
        "version": scorer.VERSION,
        "instance_id": task,
        "plan": plan_ref,
        "controls": controls,
        "passed": True,
        "model_calls": 0,
    }
    target = BATCH_ROOT / "qualifications" / (task + ".json")
    proposal = target.with_name(task + "-proposal.json")
    proposal_ref = retain(proposal, value)
    scorer.validate_qualification(
        proposal_ref, load(plan["environments"][task]["original_config"]), plan_ref
    )
    return retain(target, value)


def run_controls():
    policy.require_v061_allowed("v061.run")
    requests = prepare_controls()
    outcomes = []
    # One task pair at a time keeps qualification independent and snapshot recovery first.
    with ThreadPoolExecutor(max_workers=2) as executor:
        for offset in range(0, len(requests), 2):
            pair = requests[offset : offset + 2]
            outcomes.extend(f.result() for f in [executor.submit(run_request, ref) for ref in pair])
            if not all(trustworthy_cleanup(ref) for ref in pair):
                retain(
                    BATCH_ROOT / "grading-quarantined.json",
                    {"reason": "Unproven owned-container cleanup", "requests": pair},
                )
                break
            task = load(load(pair[0])["original_config"])["instance_id"]
            try:
                qualify(task)
            except (OSError, ValueError, KeyError, TypeError) as error:
                retain(
                    BATCH_ROOT / "qualifications" / (task + "-not-qualified.json"),
                    {"instance_id": task, "passed": False, "reason": str(error)},
                )
    return outcomes


def prepare_score(result_ref, *, lane=0):
    result = load(result_ref)
    plan = policy.create_plan()
    original_slot = result.get("original_slot_id") or result.get("slot", {}).get("slot_id")
    row = next((item for item in plan["rows"] if item["slot_id"] == original_slot), None)
    if row is None or result.get("measurement_kind") != row["measurement_kind"]:
        raise ValueError("Result does not belong to the original fourteen-slot recovery panel")
    task = row["instance_id"]
    qualification = reference(RUN_ROOT / "qualifications" / (task + ".json"))
    scorer.validate_qualification(
        qualification, load(row["original_config"]), reference(policy.PLAN_FILE)
    )
    key = "score-" + str(row["slot_index"])
    folder = BATCH_ROOT / "grading" / key
    request = {
        "version": scorer.VERSION,
        "resource_key": key,
        "plan": reference(policy.PLAN_FILE),
        "original_config": row["original_config"],
        "candidate_lock": result["candidate_lock"],
        "generation_result": result_ref,
        "measurement_kind": row["measurement_kind"],
        "original_slot_id": original_slot,
        "slot_id": row["recovery_slot_id"],
        "qualification": qualification,
        "limits": scorer.LIMITS,
        "scorer_manifest": prepare_manifest(),
        "cpuset_cpus": selected_cpus(lane),
        "directory": str(folder),
    }
    return retain(folder / "request.json", request)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-controls", action="store_true")
    parser.add_argument("--run-controls", action="store_true")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    if sum((args.prepare_controls, args.run_controls, bool(args.request), bool(args.result))) != 1:
        parser.error("Choose exactly one preparation or bounded execution mode")
    value = (
        prepare_controls()
        if args.prepare_controls
        else run_controls()
        if args.run_controls
        else run_request(reference(args.request))
        if args.request
        else prepare_score(reference(args.result))
    )
    print(json.dumps(value))


if __name__ == "__main__":
    main()
