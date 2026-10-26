"""Prepare and run only the selected v062 offline environment/score jobs."""

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

from proworksim import software_benchmark_dispatch_v062 as policy
from proworksim import software_benchmark_scorer_v062 as scorer
from proworksim import software_benchmark_grading_environment_v062 as environment
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

ROOT, BATCH_ROOT = policy.ROOT, policy.BATCH_ROOT
RUN_ROOT = policy.COORDINATOR_RUN_ROOT
VERSION = "v062-bounded-capability-grading-coordinator-r1"


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
    environment.prepare()
    target.parent.mkdir(parents=True, exist_ok=True)
    command = fixed_python(
        [
            "-c",
            "import json; from proworksim.software_benchmark_scorer_v062 import installation_manifest; print(json.dumps(installation_manifest()))",
        ]
    )
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, check=True, timeout=60,
                               env=bootstrap_environment())
    return write_new(target, json.loads(completed.stdout))


def selected_cpus(lane):
    return policy.cpu_set("grader", lane)


def prepare_reused_qualifications():
    """Record concrete identity changes; never select controls by model scores."""
    source = reference(ROOT / "artifacts/software-benchmark-v062/preparation-r1/qualification-inventory.json")
    decisions = []
    for row in load(source)["rows"]:
        if not row["historical_evidence_available"]:
            continue
        reasons = [
            "new unified grader routes wrappers and validates request/candidate/source identities under v062 claims",
            "new scorer includes task-specific capability selection and bounded lifecycle cleanup branches",
            "no sealed whole-path CPU equivalence evidence for the new creator/start/evaluation/cleanup composition",
        ]
        if row["instance_id"] in environment.OFFLINE_TASKS:
            reasons.append("historical nominal and actual PidsLimit=16384; new exact limit=512")
            reasons.append("offline fixture now uses owned named claims, labels, watchdog and unknown-create handling")
        if row["instance_id"] in environment.TLS_TASKS:
            reasons.append("historical request limits claim PidsLimit=16384 although observed container=512; new identity binds512 directly")
            reasons.append("transport and original-CA checks now compose with the v062 quota/claim/watchdog cleanup path")
        decisions.append({"instance_id": row["instance_id"], "historical_qualification": row["qualification"],
            "historical_control_identities": row["historical_control_identities"], "reuse_admitted": False,
            "reasons": reasons, "new_gold_empty_controls_required": True, "model_scores_used": False})
    retain(RUN_ROOT / "qualification-reuse-decisions.json", {
        "version": VERSION, "source_inventory": source, "new_scorer_source": reference(scorer.__file__),
        "new_limits": scorer.LIMITS, "decisions": decisions, "admitted_reuses": 0,
        "unconditional_control_count": 78, "conditional_controls_now_required": 22,
        "model_calls": 0, "old_grants_reopened": False})
    return {}


def prepare_controls():
    plan = policy.create_plan()
    manifest = prepare_manifest()
    reused = prepare_reused_qualifications()
    requests = []
    for task in plan["environments"]:
        if task in reused:
            continue
        for lane, kind in enumerate(("gold", "empty")):
            key = "control-" + task + "-" + kind
            folder = BATCH_ROOT / "grading" / key
            value = {"version": scorer.VERSION, "resource_key": key,
                "instance_id": task, "slot_id": None, "plan": reference(policy.PLAN_FILE),
                "configuration": plan["environments"][task]["configuration"],
                "patch_kind": kind, "limits": scorer.LIMITS, "scorer_manifest": manifest,
                "cpuset_cpus": selected_cpus(lane), "directory": str(folder), "candidate_lock": None,
                **environment.request_fields(task)}
            requests.append(retain(folder / "request.json", value))
    retain(BATCH_ROOT / "control-plan.json", {"version": VERSION,
        "plan": reference(policy.PLAN_FILE), "requests": requests,
        "historical_reuses": reused, "controls_are_new_scoring_identity": True})
    return requests


def capacity_available():
    available = next(
        int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    return available >= 160 * 1024**3 and shutil.disk_usage(ROOT).free >= 256 * 1024**3


def run_request(request_ref, stop_event=None):
    request = load(request_ref)
    operation = "v062.control" if request["resource_key"].startswith("control-") else "v062.score"
    policy.require_v062_allowed(operation)
    folder = Path(request["directory"])
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "completion.json").exists():
        return load(reference(folder / "completion.json"))
    if (folder / "started.json").exists():
        return {"status": "entered_attempt_not_replayed", "resource_key": request["resource_key"]}
    while not capacity_available():
        if stop_event is not None and stop_event.wait(5):
            return {"status": "not_started_cancelled", "resource_key": request["resource_key"]}
        if stop_event is None:
            time.sleep(5)
    command = fixed_python(
        ["-m", "proworksim.software_benchmark_scorer_v062", "--request", request_ref["path"]]
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
                if stop_event is not None and stop_event.wait(1):
                    raise InterruptedError("Coordinator requested owned grader cancellation")
                if stop_event is None:
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
                "initial_container": reference(folder / "official-output/initial-container.json"),
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
    target = RUN_ROOT / "qualifications" / (task + ".json")
    proposal = target.with_name(task + "-proposal.json")
    proposal_ref = retain(proposal, value)
    scorer.validate_qualification(
        proposal_ref, load(plan["environments"][task]["configuration"]), plan_ref
    )
    return retain(target, value)


def run_controls():
    policy.require_v062_allowed("v062.run")
    requests = prepare_controls()
    outcomes = []
    # One task pair at a time keeps qualification independent and snapshot capability first.
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
            task = load(load(pair[0])["configuration"])["instance_id"]
            try:
                qualify(task)
            except (OSError, ValueError, KeyError, TypeError) as error:
                retain(
                    RUN_ROOT / "qualifications" / (task + "-not-qualified.json"),
                    {"instance_id": task, "passed": False, "reason": str(error)},
                )
    return outcomes


def prepare_score(result_ref, *, lane=0):
    result = load(result_ref)
    plan = policy.create_plan()
    row = next((row for row in plan["rows"] if row["slot_id"] == result.get("slot_id")), None)
    if (row is None or result.get("measurement_kind") != "capability_probe"
            or result.get("configuration") != row["configuration"]):
        raise ValueError("Result does not belong to the frozen capability panel")
    task = row["instance_id"]
    qualification = reference(RUN_ROOT / "qualifications" / (task + ".json"))
    scorer.validate_qualification(qualification, load(row["configuration"]), reference(policy.PLAN_FILE))
    key = "score-" + str(row["slot_index"])
    folder = BATCH_ROOT / "grading" / key
    value = {"version": scorer.VERSION, "resource_key": key, "instance_id": task,
        "plan": reference(policy.PLAN_FILE), "configuration": row["configuration"],
        "candidate_lock": result["candidate_lock"], "generation_result": result_ref,
        "measurement_kind": row["measurement_kind"], "source_slot_id": row["source_slot_id"],
        "slot_id": row["slot_id"], "qualification": qualification, "limits": scorer.LIMITS,
        "scorer_manifest": prepare_manifest(), "cpuset_cpus": selected_cpus(lane),
        "directory": str(folder), "patch_kind": None, **environment.request_fields(task)}
    return retain(folder / "request.json", value)


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
