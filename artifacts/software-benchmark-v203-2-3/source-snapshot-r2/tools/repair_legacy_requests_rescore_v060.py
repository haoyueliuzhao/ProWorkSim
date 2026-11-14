"""Regrade eligible fixed requests candidates after independent task admission.

All two affected tasks and all four budget conditions are selected before any
new model-candidate score is seen. No model, actor, or generation queue is run.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

from proworksim import software_benchmark_grading_environment_v060 as environment
from proworksim import software_benchmark_grading_qualification_v060 as qualification
from proworksim import software_benchmark_queue_v056 as queue
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_ref_budget_v056 import BUDGETS
from proworksim.software_benchmark_scorer_v054 import canonical
from proworksim.software_benchmark_rescore_policy_v060 import require_v060_rescore_allowed
from proworksim.storage import digest, json_bytes

ROOT = Path(__file__).resolve().parents[1]
OLD_RUNS = ROOT / "runs/software-benchmark-v056"
RUNS = ROOT / "runs/software-benchmark-v060"
QUEUE = OLD_RUNS / "queue-r2"
BATCH_ROOT = RUNS / "original-ca-rescore-r1-20261025"
DEFAULT_ROOT = BATCH_ROOT / "requests-rescore"
VERSION = "v060-eight-requests-task-qualified-rescore-r1"
SCORER = "proworksim.software_benchmark_scorer_v060"


def load(value):
    return json.loads(checked(value).read_bytes())


def retain(path, body):
    """Unentered preparation can be resumed only with identical immutable bytes."""
    path = Path(path)
    if path.exists():
        expected = body if isinstance(body, bytes) else json_bytes(body)
        if path.read_bytes() != expected:
            raise ValueError("Existing preparation evidence differs: " + str(path))
        return reference(path)
    return write_new(path, body)


def scorer_command(request):
    return [str(ROOT / ".venv/bin/python"), "-B", str(ROOT / "tools/run_offline_scorer_v058.py"),
            "-m", SCORER, "--request", str(request)]


def frozen_sources():
    return [reference(ROOT / path) for path in (
        "tools/repair_legacy_requests_rescore_v060.py",
        "src/proworksim/software_benchmark_scorer_v060.py",
        "src/proworksim/software_benchmark_grading_environment_v060.py",
        "src/proworksim/software_benchmark_grading_qualification_v060.py",
        "src/proworksim/software_benchmark_shared_server_hold_v057.py",
        "config/v057-shared-server-hold.json",
        "src/proworksim/software_benchmark_rescore_policy_v060.py",
        "config/v059-tls-diagnostic-authorization.json",
        "tools/run_offline_scorer_v058.py",
        "src/proworksim/software_benchmark_queue_v056.py",
        "tools/analyze_ref_budget_results_v056.py")]


def task_qualifications(summary, originals):
    """Only independently verified tasks are eligible; other planned tasks remain explicit."""
    results = {}
    for task in environment.PROFILES:
        candidate = summary.get("tasks", {}).get(task, {})
        try:
            if candidate.get("status") != "qualified":
                raise ValueError(candidate.get("reason", "No passing task qualification"))
            if not environment.PROFILES[task]["admission_enabled"]:
                raise ValueError("Task retains unresolved fixed-test environment requirements")
            same_task = [request for request in originals if request["instance_id"] == task]
            if not same_task:
                raise ValueError("Task absent from fixed original panel")
            for original in same_task:
                admitted = qualification.validate_qualification(candidate["qualification"], original)
            results[task] = {"status": "qualified", "qualification": candidate["qualification"],
                             "environment_revision": admitted["environment_revision"]}
        except (ValueError, KeyError, OSError, TypeError) as error:
            results[task] = {"status": "not_qualified", "reason": str(error)}
    return results


def validate_plan(plan, *, audit_admission=True):
    if (Path(plan.get("root", "/")).resolve() != DEFAULT_ROOT.resolve()
            or plan.get("version") != VERSION or plan.get("concurrency") != 2
            or plan.get("model_calls") != 0 or len(plan.get("rows", [])) != 8
            or set(plan.get("tasks", [])) != set(environment.PROFILES)
            or plan.get("sources") != frozen_sources()):
        raise ValueError("The full two-task, four-budget panel must remain visible")
    expected = {(task, condition) for task in environment.PROFILES for condition in BUDGETS}
    if {(r["instance_id"], r["condition_id"]) for r in plan["rows"]} != expected:
        raise ValueError("The fixed eight-slot panel is incomplete")
    for source in plan["sources"]:
        checked(source)
    checked(plan["scorer_manifest"])
    for row in plan["rows"]:
        if row["admission_status"] == "not_qualified":
            if row["request"] is not None:
                raise ValueError("An unqualified task cannot have a dispatched request")
            continue
        if row["admission_status"] != "qualified":
            raise ValueError("Unknown task admission status")
        if not environment.PROFILES[row["instance_id"]]["admission_enabled"]:
            raise ValueError("A blocked task cannot enter the scoring queue")
        request = load(row["request"])
        if (request["environment_revision"] != row["environment_revision"]
                or request["environment_qualification"] != row["environment_qualification"]
                or request["scoring_recovery_of"] != row["original_request"]
                or request["patch"] != row["original_patch"]
                or request["native_candidate_lock"] != row["native_candidate_lock"]):
            raise ValueError("Request must bind its own admitted task and original candidate")
        if audit_admission:
            admitted = qualification.validate_qualification(row["environment_qualification"], load(row["original_request"]))
            if admitted["environment_revision"] != row["environment_revision"]:
                raise ValueError("Task qualification uses a different environment")
    return plan


def _prepare(root, qualification_path):
    root = Path(root).resolve()
    if root != DEFAULT_ROOT.resolve():
        raise ValueError("Use an independent v060 rescore directory")
    if (root / "plan.json").exists():
        return validate_plan(load(reference(root / "plan.json")))
    if qualification_path is None:
        raise ValueError("A completed per-task qualification summary is required")
    qualification_ref = reference(qualification_path)
    root.mkdir(parents=True, exist_ok=True)
    with queue.lock(QUEUE / "coordinator.lock"):
        state_ref = reference(QUEUE / "state.json")
        state = load(state_ref)
        if not state.get("complete") or any(job["status"] in {"running", "launch_intent"}
                                             for job in state["jobs"].values()):
            raise ValueError("Original generation/scoring queue must be terminal")
        selected = [row for row in state["rows"] if row["slot"]["instance_id"] in environment.PROFILES]
        if len(selected) != 8:
            raise ValueError("All eight original slots must remain present")
        for row in selected:
            if (row["generation"]["status"] != "closed" or row["score"]["status"] != "official_report"
                    or type(row["score"].get("resolved")) is not bool):
                raise ValueError("An affected slot is not the original closed, scored candidate")
        admissions = task_qualifications(load(qualification_ref), [load(row["score"]["dispatched_request"]) for row in selected])
        pre = retain(root / "pre-state.json", checked(state_ref).read_bytes())
    cpus = sorted(os.sched_getaffinity(0))
    if len(cpus) < 8:
        raise ValueError("Two independent four-CPU grading lanes are required")
    command = scorer_command("unused")[:-4] + ["-c",
        "import json; from proworksim.software_benchmark_scorer_v060 import installation_manifest; "
        "print(json.dumps(installation_manifest()))"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120, check=True)
    manifest = retain(root / "scorer-manifest.json", json.loads(result.stdout))
    rows = []
    for index, row in enumerate(sorted(selected, key=lambda value: value["slot"]["slot_index"])):
        slot = row["slot"]
        original_ref = row["score"]["dispatched_request"]
        original = load(original_ref)
        # These eight already had official reports; no patch encoding change is needed.
        checked(original["patch"]).read_bytes().decode("utf-8", "strict")
        folder = root / "slots" / digest(slot["slot_id"].encode())
        folder.mkdir(parents=True, exist_ok=True)
        admission = admissions[slot["instance_id"]]
        request = None
        if admission["status"] == "qualified":
            request = {**original, "scorer_manifest": manifest,
                "trusted_output_root": str(root / "official-output"),
                "receipt_output": str(folder / "receipt.json"),
                "quiescence_output": str(folder / "quiescence.json"),
                "scoring_cpuset_cpus": ",".join(map(str, cpus[(index % 2) * 4:(index % 2 + 1) * 4])),
                "scoring_recovery_of": original_ref,
                "environment_revision": admission["environment_revision"],
                "environment_qualification": admission["qualification"],
                "network_resolution": reference(root.parent / "resolution.json")}
        rows.append({"slot_id": slot["slot_id"], "instance_id": slot["instance_id"],
            "condition_id": slot["condition_id"], "directory": str(folder), "lane": index % 2,
            "original_request": original_ref, "old_resolved": row["score"]["resolved"],
            "original_patch": original["patch"], "native_candidate_lock": original["native_candidate_lock"],
            "admission_status": admission["status"], "admission_reason": admission.get("reason"),
            "environment_revision": admission.get("environment_revision"),
            "environment_qualification": admission.get("qualification"),
            "request": retain(folder / "request.json", request) if request is not None else None})
    plan = {"version": VERSION, "created_utc": queue.now(), "root": str(root), "tasks": sorted(environment.PROFILES),
        "selection_basis": "four environment-affected tasks crossed with all four frozen budgets; independent of model score",
        "source_state": state_ref, "pre_state": pre, "task_qualification_summary": qualification_ref,
        "task_admissions": admissions, "scorer_manifest": manifest,
        "sources": frozen_sources(), "concurrency": 2, "per_score_cpus": 4,
        "model_calls": 0, "candidate_content_changed": False, "rows": rows}
    write_new(root / "plan.json", plan)
    return validate_plan(plan, audit_admission=False)


def prepare(root, qualification_path):
    return _prepare(root, qualification_path)


def run_one(plan, row):
    if row.get("admission_status") == "not_qualified":
        return {"slot_id": row["slot_id"], "status": "not_qualified", "reason": row.get("admission_reason")}
    require_v060_rescore_allowed("v060.rescore.run_one", instance_id=row.get("instance_id"))
    folder = Path(row["directory"])
    if (folder / "completion.json").exists():
        return load(reference(folder / "completion.json"))
    if (folder / "started.json").exists():
        return {"slot_id": row["slot_id"], "status": "deferred", "reason": "Entered scoring attempt is not replayed"}
    result = {"version": VERSION, "slot_id": row["slot_id"], "request": row["request"],
              "started_utc": queue.now(), "model_calls": 0}
    process, start = None, time.monotonic()
    try:
        # Full controls were admitted before scheduling; the scorer validates
        # them again at its own process boundary. Here only frozen bytes need checking.
        validate_plan(plan, audit_admission=False)
        if shutil.disk_usage(ROOT).free < 256 * queue.GIB:
            raise RuntimeError("Preserve 128-GiB disk floor plus two 64-GiB reservations")
        available = next(int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()
                         if line.startswith("MemAvailable:"))
        if available < 160 * queue.GIB:
            raise RuntimeError("Preserve 128-GiB RAM margin beyond two 16-GiB graders")
        argv = scorer_command(row["request"]["path"])
        write_new(folder / "started.json", {**result, "command": argv, "lane": row["lane"]})
        with (folder / "stdout.log").open("xb") as stdout, (folder / "stderr.log").open("xb") as stderr:
            process = subprocess.Popen(argv, cwd=ROOT, stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            result["returncode"] = process.wait(timeout=3900)
        result["status"] = "process_exited"
    except Exception as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)})
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=20)
        result.setdefault("returncode", process.returncode if process is not None else None)
    result.update(finished_utc=queue.now(), elapsed_seconds=time.monotonic() - start)
    write_new(folder / "completion.json", result)
    return result


def run(root):
    require_v060_rescore_allowed("v060.run")
    root = Path(root)
    plan = validate_plan(load(reference(root / "plan.json")))
    if (root / "run-summary.json").exists():
        return load(reference(root / "run-summary.json"))["rows"]

    def lane(index):
        rows = [row for row in plan["rows"] if row["lane"] == index]
        results = []
        quarantine = root / f"lane-{index}-quarantined.json"
        if quarantine.exists():
            return [{"lane": index, "status": "deferred", "reason": "Grading lane remains quarantined"}]
        with queue.lock(OLD_RUNS / "queue-resource-locks" / f"grader-{index}.lock"):
            for row in rows:
                results.append(run_one(plan, row))
                folder = Path(row["directory"])
                if not (folder / "started.json").exists():
                    continue
                try:
                    quiet = load(reference(folder / "quiescence.json"))
                    proved = (quiet.get("slot_id") == row["slot_id"]
                        and quiet.get("condition_id") == row["condition_id"]
                        and quiet.get("quiescent") is True and not quiet.get("cleanup_errors")
                        and quiet.get("create_result_unknown") is False)
                except (OSError, ValueError, KeyError):
                    proved = False
                if not proved:
                    write_new(quarantine, {"lane": index, "slot_id": row["slot_id"], "utc": queue.now(),
                        "reason": "Owned grader resource quiescence not proved", "remaining_lane_slots_not_started": True})
                    break
        return results

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(lane, index) for index in (0, 1)]
        results = []
        for index, future in enumerate(futures):
            try:
                results.extend(future.result())
            except Exception as error:
                results.append({"lane": index, "status": "deferred", "error": str(error)})
    retain(root / "run-summary.json", {"version": VERSION, "rows": results, "model_calls": 0,
                                     "host_listener_started": False})
    return results


def collect_outcomes(plan):
    results = []
    for row in plan["rows"]:
        folder = Path(row["directory"])
        outcome = {key: row[key] for key in (
            "slot_id", "instance_id", "condition_id", "original_request", "original_patch", "native_candidate_lock", "request")}
        outcome.update(environment_revision=row["environment_revision"],
                       environment_qualification=row["environment_qualification"], known=False)
        if row["admission_status"] != "qualified":
            outcome["error"] = {"type": "TaskNotQualified", "message": row.get("admission_reason")}
            results.append(outcome)
            continue
        try:
            completion_ref = reference(folder / "completion.json")
            completion = load(completion_ref)
            outcome["completion"] = completion_ref
            if completion.get("returncode") != 0 or completion.get("request") != row["request"]:
                raise ValueError("New grader did not finish normally")
            request = load(row["request"])
            pointer = reference(request["receipt_output"])
            paths = load(pointer)
            receipt, identity = load(paths["receipt"]), load(paths["identity"])
            quiet_ref = reference(request["quiescence_output"])
            quiet = load(quiet_ref)
            if (identity.get("slot_id") != row["slot_id"] or identity.get("condition_id") != row["condition_id"]
                    or identity.get("native_candidate_lock") != row["native_candidate_lock"]
                    or identity.get("scoring_recovery_of") != row["original_request"]
                    or identity.get("environment_revision") != row["environment_revision"]
                    or identity.get("environment_qualification") != row["environment_qualification"]
                    or digest(canonical(identity)) != receipt.get("identity_sha256")):
                raise ValueError("New grader identity differs from its immutable candidate or environment")
            outcome.update(receipt=receipt, receipt_pointer=pointer, identity=paths["identity"],
                           quiescence=quiet, quiescence_reference=quiet_ref, known=True)
        except Exception as error:
            outcome["error"] = {"type": type(error).__name__, "message": str(error)}
        results.append(outcome)
    return results


def admission_module():
    spec = importlib.util.spec_from_file_location('v060_admission', ROOT / 'tools/check_legacy_requests_environment_v060.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_batch():
    """Pure preparation: freeze the four controls and eight original candidate references."""
    BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    admission_module().prepare(BATCH_ROOT / 'environment-admission')
    state = load(reference(QUEUE / 'state.json'))
    selected = [row for row in state['rows'] if row['slot']['instance_id'] in environment.PROFILES]
    expected = {(task, condition) for task in environment.PROFILES for condition in BUDGETS}
    if {(r['slot']['instance_id'], r['slot']['condition_id']) for r in selected} != expected or len(selected) != 8:
        raise ValueError('Fixed two-task by four-budget panel differs')
    candidates = []
    for row in sorted(selected, key=lambda r: r['slot']['slot_index']):
        ref = row['score']['dispatched_request']
        request = load(ref)
        checked(request['patch']).read_bytes().decode('utf-8', 'strict')
        candidates.append({'slot_id': row['slot']['slot_id'], 'instance_id': row['slot']['instance_id'],
            'condition_id': row['slot']['condition_id'], 'original_request': ref,
            'original_patch': request['patch'], 'native_candidate_lock': request['native_candidate_lock']})
    result = {'version': VERSION, 'root': str(BATCH_ROOT), 'controls': reference(BATCH_ROOT / 'environment-admission/plan.json'),
        'candidates': candidates, 'sources': frozen_sources(), 'model_calls': 0, 'containers_planned': 12,
        'concurrency': 2, 'approved': False, 'state': reference(QUEUE / 'state.json')}
    retain(BATCH_ROOT / 'preflight-plan.json', result)
    return result


def execute_batch():
    authorization = require_v060_rescore_allowed('v060.run')
    prepare_batch()
    retain(BATCH_ROOT / 'authorization-used.json', authorization)
    if (BATCH_ROOT / 'resolution.json').exists():
        raise ValueError('Entered batch is not automatically replayed')
    write_new(BATCH_ROOT / 'resolution.json', environment.freeze_resolution())
    controls = admission_module()
    controls.execute(BATCH_ROOT / 'environment-admission')
    summary = controls.collect_qualifications(BATCH_ROOT / 'environment-admission')
    qualification_path = BATCH_ROOT / 'qualification-summary.json'
    write_new(qualification_path, summary)
    prepare(DEFAULT_ROOT, qualification_path)
    return run(DEFAULT_ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--collect', action='store_true')
    args = parser.parse_args()
    if sum((args.prepare, args.execute, args.collect)) != 1:
        parser.error('Choose exactly one of --prepare, --execute, --collect')
    if args.prepare:
        result = prepare_batch()
    elif args.execute:
        result = execute_batch()
    else:
        plan = validate_plan(load(reference(DEFAULT_ROOT / 'plan.json')))
        result = {'rows': collect_outcomes(plan), 'model_calls': 0}
        retain(DEFAULT_ROOT / 'collection-preview.json', result)
    print(json.dumps({'phase': 'prepare' if args.prepare else 'execute' if args.execute else 'collect',
                      'root': str(BATCH_ROOT), 'complete': True}), flush=True)


if __name__ == '__main__':
    main()
