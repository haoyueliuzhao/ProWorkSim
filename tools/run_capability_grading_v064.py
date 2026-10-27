"""Prepare and run only the full v064 offline environment/score jobs."""

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

from proworksim import software_benchmark_dispatch_v064 as policy
from proworksim import software_benchmark_scorer_v064 as scorer
from proworksim import software_benchmark_grading_environment_v064 as environment
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

ROOT, BATCH_ROOT = policy.ROOT, policy.BATCH_ROOT
RUN_ROOT = policy.COORDINATOR_RUN_ROOT
VERSION = "v064-bounded-capability-grading-coordinator-r1"


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
            "import json; from proworksim.software_benchmark_scorer_v064 import installation_manifest; print(json.dumps(installation_manifest()))",
        ]
    )
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, check=True, timeout=60,
                               env=bootstrap_environment())
    return write_new(target, json.loads(completed.stdout))


def selected_cpus(lane):
    return policy.cpu_set("grader", lane)


def prepare_reused_qualifications():
    """Audit old public initialization and gold/empty proofs without model scores."""
    plan = policy.load(policy.reference(policy.PLAN_FILE))
    decisions = []
    for task in plan["environments"]:
        historical = []
        old_controls = policy.ROOT / "runs/software-benchmark-v062/capability-probe-r1-20261026/coordinator-r2/qualifications" / (task + ".json")
        if old_controls.exists():
            old = load(reference(old_controls))
            historical.append({"kind": "gold_empty", "record": reference(old_controls),
                "passed": old.get("passed") is True, "version": old.get("version")})
        old_task = policy.ROOT / "runs/software-benchmark-v054/native-lazy-cache" / task
        for path in sorted(old_task.glob("*/lazy-preparation.json")):
            old = load(reference(path))
            ref = old.get("qualification")
            if not isinstance(ref, dict):
                continue
            qualification = load(ref)
            historical.append({"kind": "public_initialization_only", "preparation": reference(path),
                "record": ref, "passed": qualification.get("passed") is True,
                "hidden_grader_called": qualification.get("hidden_grader_called"),
                "benchmark_tests_run": qualification.get("benchmark_tests_run")})
        decisions.append({"instance_id": task, "historical_evidence": historical,
            "reuse_admitted": False, "new_gold_empty_controls_required": True,
            "reasons": ["new scorer and scoped global capacity/ownership path differ from historical versions",
                        "diagnostic raw-byte preservation and dual-endpoint validation are now part of the fixed scorer",
                        "no exact whole-path equivalence proof exists; public initialization is not a gold/empty qualification"],
            "model_scores_read_or_used": False})
    retain(RUN_ROOT / "qualification-reuse-decisions.json", {
        "version": VERSION, "plan": reference(policy.PLAN_FILE),
        "new_scorer_source": reference(scorer.__file__), "new_limits": scorer.LIMITS,
        "decisions": decisions, "admitted_reuses": 0,
        "required_new_controls": 1000, "model_calls": 0, "old_grants_reopened": False})
    return {}


def prepare_controls():
    plan = policy.load(policy.reference(policy.PLAN_FILE))
    manifest = prepare_manifest()
    reused = prepare_reused_qualifications()
    requests = []
    for task in plan["environments"]:
        if task in reused:
            continue
        for kind in ("gold", "empty"):
            key = "control-" + task + "-" + kind
            folder = policy.GRADING_ROOT / key
            value = {"version": scorer.VERSION, "resource_key": key,
                "instance_id": task, "slot_id": None, "plan": reference(policy.PLAN_FILE),
                "configuration": plan["environments"][task]["configuration"],
                "patch_kind": kind, "limits": scorer.LIMITS, "scorer_manifest": manifest,
                "cpuset_cpus": None, "directory": str(folder), "candidate_lock": None,
                **environment.request_fields(task)}
            requests.append(retain(folder / "request.json", value))
    retain(RUN_ROOT / "control-plan.json", {"version": VERSION,
        "plan": reference(policy.PLAN_FILE), "requests": requests,
        "historical_reuses": reused, "controls_are_new_scoring_identity": True})
    return requests


def capacity_available():
    available = next(
        int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    return available >= 144 * 1024**3 and shutil.disk_usage(ROOT).free >= 128 * 1024**3


def run_request(request_ref, stop_event=None):
    request = load(request_ref)
    operation = "v064.control" if request["resource_key"].startswith("control-") else "v064.delivery.score" if request["resource_key"].startswith("delivery-score-") else "v064.score"
    policy.require_v064_allowed(operation)
    folder = Path(request["directory"])
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "completion.json").exists():
        return load(reference(folder / "completion.json"))
    if (folder / "started.json").exists():
        return {"status": "entered_attempt_not_replayed", "resource_key": request["resource_key"]}
    claim_ref = None
    while claim_ref is None:
        if stop_event is not None and stop_event.is_set():
            return {"status": "not_started_cancelled", "resource_key": request["resource_key"]}
        if capacity_available():
            try:
                claim_ref = policy.claim_resource(request["resource_key"])
            except policy.ResourceBusy:
                pass
        if claim_ref is not None:
            break
        if stop_event is not None and stop_event.wait(5):
            return {"status": "not_started_cancelled", "resource_key": request["resource_key"]}
        if stop_event is None:
            time.sleep(5)
    retain(folder / "capacity-claim.json", {"prepared_request": request_ref, "claim": claim_ref})
    command = fixed_python(
        ["-m", "proworksim.software_benchmark_scorer_v064", "--request", request_ref["path"]]
    )
    started = {
        "version": VERSION,
        "request": request_ref,
        "resource_key": request["resource_key"],
        "started_unix": time.time(),
        "command": command, "capacity_claim": claim_ref,
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
    if process is None:
        policy.release_resource(claim_ref, quiescent=True)
        write_new(folder / "quiescence.json", {"version": scorer.VERSION, "resource_key": request["resource_key"],
            "quiescent": True, "cleanup_errors": [], "create_result_unknown": False,
            "owned_container_ids": [], "proof": "No scoring subprocess was created", "model_calls": 0})
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
        folder = policy.GRADING_ROOT / ("control-" + task + "-" + kind)
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
    policy.require_v064_allowed("v064.run")
    requests = prepare_controls()
    outcomes = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        for offset in range(0, len(requests), 4):
            batch = requests[offset:offset + 4]
            outcomes.extend(f.result() for f in [executor.submit(run_request, ref) for ref in batch])
            if not all(trustworthy_cleanup(ref) for ref in batch):
                retain(RUN_ROOT / "grading-quarantined.json", {
                    "reason": "Unproven owned-container cleanup", "requests": batch})
                break
            for task in dict.fromkeys(load(ref)["instance_id"] for ref in batch):
                try:
                    qualify(task)
                except (OSError, ValueError, KeyError, TypeError) as error:
                    retain(RUN_ROOT / "qualifications" / (task + "-not-qualified.json"), {
                        "instance_id": task, "passed": False, "reason": str(error)})
    return outcomes


def prepare_score(result_ref, *, endpoint="code"):
    if endpoint not in {"code", "delivery"}:
        raise ValueError("Only fixed code/delivery endpoints are planned")
    result = load(result_ref)
    plan = policy.load(policy.reference(policy.PLAN_FILE))
    row = next((row for row in plan["rows"] if row["slot_id"] == result.get("slot_id")), None)
    if (row is None or result.get("measurement_kind") != "full_verified_comparison"
            or result.get("configuration") != row["configuration"] or result.get("status") != "closed"):
        raise ValueError("Result does not belong to the frozen complete paired experiment")
    task = row["instance_id"]
    qualification = reference(RUN_ROOT / "qualifications" / (task + ".json"))
    config = load(row["configuration"])
    scorer.validate_qualification(qualification, config, reference(policy.PLAN_FILE))
    field = "candidate_lock" if endpoint == "code" else "delivery_candidate_lock"
    if endpoint == "delivery":
        if row["arm"] != "PROJECT":
            raise ValueError("REF has no project-delivery scoring endpoint")
        proof = scorer.validate_project_delivery(result, config, Path(result_ref["path"]).parent)
        if not proof["submitted"]:
            raise ValueError("Absent legal delivery is recorded without starting a grader")
    key = ("score-" if endpoint == "code" else "delivery-score-") + str(row["slot_index"])
    folder = policy.GRADING_ROOT / key
    value = {"version": scorer.VERSION, "resource_key": key, "instance_id": task,
        "plan": reference(policy.PLAN_FILE), "configuration": row["configuration"],
        "candidate_lock": result[field], "generation_result": result_ref,
        "measurement_kind": row["measurement_kind"], "source_slot_id": row["source_slot_id"],
        "slot_id": row["slot_id"], "qualification": qualification, "limits": scorer.LIMITS,
        "scorer_manifest": prepare_manifest(), "cpuset_cpus": None,
        "directory": str(folder), "patch_kind": None,
        "delivery_evidence": result.get("delivery_evidence") if endpoint == "delivery" else None,
        **environment.request_fields(task)}
    return retain(folder / "request.json", value)


def delivery_disposition(result_ref, code_request_ref=None):
    """Decide the separate delivery endpoint without scoring or choosing code."""
    result = load(result_ref)
    plan_ref = reference(policy.PLAN_FILE)
    plan = policy.load(plan_ref)
    row = next((row for row in plan["rows"] if row["slot_id"] == result.get("slot_id")), None)
    if row is None:
        raise ValueError("Foreign generation result")
    if row["arm"] != "PROJECT":
        return {"status": "not_applicable", "resolved": None, "scoring_request": None}
    config = load(row["configuration"])
    # Reuse the same generation identity/cleanup check used for real scoring.
    scorer._generation_result({"generation_result": result_ref, "slot_id": row["slot_id"]}, config, plan)
    proof = scorer.validate_project_delivery(result, config, Path(result_ref["path"]).parent)
    key = "delivery-score-" + str(row["slot_index"])
    output = RUN_ROOT / "delivery-endpoints" / (str(row["slot_index"]) + ".json")
    base = {"version": VERSION, "slot_id": row["slot_id"], "instance_id": row["instance_id"],
        "resource_key": key, "generation_result": result_ref, "plan": plan_ref,
        "delivery_evidence": result["delivery_evidence"], "legal_submission": proof["submitted"],
        "model_calls": 0, "actor_feedback": False, "new_containers": 0}
    if not proof["submitted"]:
        return {"status": "no_legal_delivery", "resolved": False, "scoring_request": None,
                "receipt": retain(output, {**base, "status": "no_legal_delivery", "resolved": False})}
    if not proof["same_tree"]:
        return {"status": "requires_separate_official_score", "resolved": None,
                "scoring_request": prepare_score(result_ref, endpoint="delivery")}
    if code_request_ref is None:
        return {"status": "waiting_for_own_code_score", "resolved": None, "scoring_request": None}
    request = load(code_request_ref)
    folder = Path(request["directory"])
    if not (folder / "receipt.json").exists() or not (folder / "completion.json").exists():
        return {"status": "waiting_for_own_code_score", "resolved": None, "scoring_request": None}
    receipt, completion, quiet = (load(reference(folder / (name + ".json")))
                                  for name in ("receipt", "completion", "quiescence"))
    identity = load(receipt["identity"])
    code_lock = load(result["candidate_lock"])
    delivery_lock = load(result["delivery_candidate_lock"])
    if (request.get("resource_key") != "score-" + str(row["slot_index"])
            or request.get("generation_result") != result_ref or request.get("slot_id") != row["slot_id"]
            or request.get("candidate_lock") != result["candidate_lock"]
            or identity.get("request") != code_request_ref
            or identity.get("candidate_lock") != result["candidate_lock"]
            or identity.get("configuration") != row["configuration"]
            or identity.get("endpoint") != "code"
            or identity.get("plan") != plan_ref or identity.get("scorer_manifest") != prepare_manifest()
            or receipt.get("version") != scorer.VERSION or receipt.get("resource_key") != request["resource_key"]
            or receipt.get("slot_id") != row["slot_id"]
            or code_lock["tree_sha256"] != delivery_lock["tree_sha256"]
            or code_lock["patch_receipt"]["base_tree_sha256"] != delivery_lock["patch_receipt"]["base_tree_sha256"]
            or completion.get("returncode") != 0 or quiet.get("quiescent") is not True
            or quiet.get("resource_key") != request["resource_key"]
            or quiet.get("cleanup_errors") != [] or quiet.get("create_result_unknown") is not False):
        raise ValueError("Delivery reuse requires this slot's exact same-tree, qualified, quietly completed code score")
    known = receipt.get("status") == "official_report" and type(receipt.get("resolved")) is bool
    if known:
        report = receipt["official_result"][1][row["instance_id"]]
        if (report.get("resolved") is not receipt["resolved"]
                or report.get("patch_successfully_applied") is not True or report.get("infra_failure")):
            raise ValueError("The reusable official report is not a consistent actual test result")
    status = "same_tree_official_result_reused" if known else "technical_unknown"
    value = {**base, "status": status, "resolved": receipt["resolved"] if known else None,
             "code_scoring_receipt": reference(folder / "receipt.json"),
             "code_candidate_lock": result["candidate_lock"],
             "delivery_candidate_lock": result["delivery_candidate_lock"], "same_tree": True}
    return {"status": status, "resolved": value["resolved"], "scoring_request": None,
            "receipt": retain(output, value)}


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
