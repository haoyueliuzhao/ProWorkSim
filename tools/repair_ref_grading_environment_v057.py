"""Regrade sixteen immutable requests candidates after full environment admission.

All four affected tasks and all four budget conditions are selected before any
new model-candidate score is seen. No model, actor, or generation queue is run.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import csv
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

from proworksim import software_benchmark_grading_environment_v057 as environment
from proworksim import software_benchmark_grading_qualification_v057 as qualification
from proworksim import software_benchmark_grader_nat_v057 as nat
from proworksim import software_benchmark_queue_v056 as queue
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_ref_budget_v056 import BUDGETS
from proworksim.software_benchmark_scorer_v054 import canonical
from proworksim.software_benchmark_shared_server_hold_v057 import require_experiment_dispatch_allowed
from proworksim.storage import atomic_write, digest, json_bytes

ROOT = Path(__file__).resolve().parents[1]
OLD_RUNS = ROOT / "runs/software-benchmark-v056"
RUNS = ROOT / "runs/software-benchmark-v057"
QUEUE = OLD_RUNS / "queue-r2"
DEFAULT_ROOT = RUNS / "requests-rescore-r1"
VERSION = "v057-sixteen-requests-environment-rescore-r2-private-nat"
SCORER = "proworksim.software_benchmark_scorer_v057"


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
    argv = queue.scorer_argv(request)
    argv[argv.index("proworksim.software_benchmark_scorer_v056")] = SCORER
    return argv


def frozen_sources():
    return [reference(ROOT / path) for path in (
        "tools/repair_ref_grading_environment_v057.py",
        "src/proworksim/software_benchmark_scorer_v057.py",
        "src/proworksim/software_benchmark_grading_environment_v057.py",
        "src/proworksim/software_benchmark_grading_qualification_v057.py",
        "src/proworksim/software_benchmark_grader_nat_v057.py",
        "src/proworksim/software_benchmark_queue_v056.py",
        "tools/analyze_ref_budget_results_v056.py")]


def qualified_requests(qualification_ref, originals):
    """One full eight-control audit, then compare each frozen candidate environment."""
    admitted = qualification.validate_qualification(qualification_ref, originals[0])
    controls = {item["instance_id"]: load(item["original_request"])
                for item in admitted["controls"] if item["patch_kind"] == "gold"}
    for original in originals:
        control = controls[original["instance_id"]]
        if any(original[key] != control[key] for key in ("image", "dataset", "baseline_mapping", "scorer_manifest")):
            raise ValueError("A fixed candidate differs from its admitted environment")
    return admitted


def validate_plan(plan, *, audit_admission=True):
    if (plan.get("version") != VERSION or plan.get("concurrency") != 2
            or plan.get("model_calls") != 0 or len(plan.get("rows", [])) != 16
            or set(plan.get("tasks", [])) != set(environment.PROFILES)):
        raise ValueError("Only four admitted requests tasks by four budget conditions may run")
    expected = {(task, condition) for task in environment.PROFILES for condition in BUDGETS}
    if {(row["instance_id"], row["condition_id"]) for row in plan["rows"]} != expected:
        raise ValueError("The fixed sixteen-slot environment panel is incomplete")
    for source in plan["sources"]:
        checked(source)
    checked(plan["scorer_manifest"])
    checked(plan["environment_qualification"])
    registry = load(plan["grading_nat_registry"])
    if (registry.get("version") != nat.VERSION or registry.get("ready") is not True
            or Path(plan["grading_nat_registry"]["path"]).resolve()
            != Path(plan["root"]).resolve() / "grading-nat/registry.json"):
        raise ValueError("The frozen model-scoring plan needs its own private NAT registry")
    for row in plan["rows"]:
        if load(row["request"]).get("grading_network_lane") != {
                "registry": plan["grading_nat_registry"], "lane": row["lane"]}:
            raise ValueError("A scoring request differs from its bound runtime NAT lane")
    if audit_admission:
        qualified_requests(plan["environment_qualification"], [load(row["original_request"]) for row in plan["rows"]])
    return plan


def _prepare(root, qualification_path):
    root = Path(root).resolve()
    if not root.is_relative_to(RUNS) or root == RUNS:
        raise ValueError("Use an independent v057 rescore directory")
    if (root / "plan.json").exists():
        return validate_plan(load(reference(root / "plan.json")))
    if qualification_path is None:
        raise ValueError("Completed four-gold/four-empty qualification is required")
    qualification_ref = reference(qualification_path)
    root.mkdir(parents=True, exist_ok=True)
    with queue.lock(QUEUE / "coordinator.lock"):
        state_ref = reference(QUEUE / "state.json")
        state = load(state_ref)
        if not state.get("complete") or any(job["status"] in {"running", "launch_intent"}
                                             for job in state["jobs"].values()):
            raise ValueError("Original generation/scoring queue must be terminal")
        selected = [row for row in state["rows"] if row["slot"]["instance_id"] in environment.PROFILES]
        if len(selected) != 16:
            raise ValueError("All sixteen original slots must remain present")
        for row in selected:
            if (row["generation"]["status"] != "closed" or row["score"]["status"] != "official_report"
                    or type(row["score"].get("resolved")) is not bool):
                raise ValueError("An affected slot is not the original closed, scored candidate")
        admitted = qualified_requests(qualification_ref, [load(row["score"]["dispatched_request"]) for row in selected])
        pre = retain(root / "pre-state.json", checked(state_ref).read_bytes())
    cpus = sorted(os.sched_getaffinity(0))
    if len(cpus) < 8:
        raise ValueError("Two independent four-CPU grading lanes are required")
    command = scorer_command("unused")[:-4] + ["-c",
        "import json; from proworksim.software_benchmark_scorer_v057 import installation_manifest; "
        "print(json.dumps(installation_manifest()))"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120, check=True)
    manifest = retain(root / "scorer-manifest.json", json.loads(result.stdout))
    registry_ref = nat.start_registry(root / "grading-nat")
    registry = nat.validate_registry(registry_ref)
    old_registry = load(admitted["nat_registry"])
    if (registry_ref == admitted["nat_registry"]
            or registry["source_manifest"] != old_registry["source_manifest"]
            or {lane["keeper_id"] for lane in registry["lanes"]}
            & {lane["keeper_id"] for lane in old_registry["lanes"]}):
        raise ValueError("Runtime NAT must use the admitted profile with fresh owned keepers")
    rows = []
    for index, row in enumerate(sorted(selected, key=lambda value: value["slot"]["slot_index"])):
        slot = row["slot"]
        original_ref = row["score"]["dispatched_request"]
        original = load(original_ref)
        # These sixteen already had official reports; no patch encoding change is needed.
        checked(original["patch"]).read_bytes().decode("utf-8", "strict")
        folder = root / "slots" / digest(slot["slot_id"].encode())
        folder.mkdir(parents=True, exist_ok=True)
        request = {**original, "scorer_manifest": manifest,
            "trusted_output_root": str(root / "official-output"),
            "receipt_output": str(folder / "receipt.json"),
            "quiescence_output": str(folder / "quiescence.json"),
            "scoring_cpuset_cpus": ",".join(map(str, cpus[(index % 2) * 4:(index % 2 + 1) * 4])),
            "scoring_recovery_of": original_ref,
            "environment_revision": admitted["environment_revision"],
            "environment_qualification": qualification_ref,
            "grading_network_lane": {"registry": registry_ref, "lane": index % 2}}
        rows.append({"slot_id": slot["slot_id"], "instance_id": slot["instance_id"],
            "condition_id": slot["condition_id"], "directory": str(folder), "lane": index % 2,
            "original_request": original_ref, "old_resolved": row["score"]["resolved"],
            "original_patch": original["patch"], "native_candidate_lock": original["native_candidate_lock"],
            "request": retain(folder / "request.json", request)})
    plan = {"version": VERSION, "created_utc": queue.now(), "root": str(root), "tasks": sorted(environment.PROFILES),
        "selection_basis": "four environment-affected tasks crossed with all four frozen budgets; independent of model score",
        "source_state": state_ref, "pre_state": pre, "environment_qualification": qualification_ref,
        "environment_revision": admitted["environment_revision"], "scorer_manifest": manifest,
        "grading_nat_registry": registry_ref,
        "sources": frozen_sources(), "concurrency": 2, "per_score_cpus": 4,
        "model_calls": 0, "candidate_content_changed": False, "rows": rows}
    write_new(root / "plan.json", plan)
    return validate_plan(plan, audit_admission=False)


def prepare(root, qualification_path):
    require_experiment_dispatch_allowed("sixteen_rescore.prepare")
    root = Path(root).resolve()
    try:
        return _prepare(root, qualification_path)
    except BaseException:
        # A failed unentered preparation owns no graders; clean only its new
        # runtime network, using the helper's exact CID/unit ownership checks.
        network = root / "grading-nat"
        if ((network / "intent.json").exists() and not (root / "plan.json").exists()
                and not any((root / "slots").glob("*/started.json"))):
            try:
                receipt = nat.close_registry(network)
                write_new(root / f"preparation-network-cleanup-{time.time_ns()}.json", {"cleanup": receipt})
            except Exception as error:
                write_new(root / f"preparation-network-unresolved-{time.time_ns()}.json", {
                    "error": {"type": type(error).__name__, "message": str(error)},
                    "network_root": str(network), "unrelated_resources_affected": False})
        raise


def run_one(plan, row):
    require_experiment_dispatch_allowed("sixteen_rescore.run_one")
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
        nat.validate_registry(plan["grading_nat_registry"])
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
            result["returncode"] = process.wait(timeout=3600)
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


def cleanup_runtime_network(root, plan):
    """Release fresh owned NAT only when every entered candidate scorer is quiet."""
    unresolved = []
    for row in plan["rows"]:
        folder = Path(row["directory"])
        if not (folder / "started.json").exists():
            continue
        try:
            proof = load(reference(folder / "quiescence.json"))
            if (proof.get("slot_id") != row["slot_id"]
                    or proof.get("condition_id") != row["condition_id"]
                    or proof.get("quiescent") is not True or proof.get("cleanup_errors")
                    or proof.get("create_result_unknown") is not False):
                unresolved.append(row["slot_id"])
        except (OSError, ValueError, KeyError):
            unresolved.append(row["slot_id"])
    if unresolved:
        return {"quiescent": False, "deferred": True,
                "reason": "At least one scorer lacks resource quiescence evidence",
                "unresolved_slots": unresolved, "registry": plan["grading_nat_registry"]}
    try:
        closed = nat.close_registry(Path(root) / "grading-nat")
        return {"quiescent": load(closed).get("quiescent") is True,
                "registry": plan["grading_nat_registry"], "cleanup": closed}
    except Exception as error:
        return {"quiescent": False, "deferred": True, "registry": plan["grading_nat_registry"],
                "error": {"type": type(error).__name__, "message": str(error)}}


def run(root):
    require_experiment_dispatch_allowed("sixteen_rescore.run")
    root = Path(root)
    plan = validate_plan(load(reference(root / "plan.json")))
    if (root / "run-summary.json").exists():
        return load(reference(root / "run-summary.json"))["rows"]
    nat.validate_registry(plan["grading_nat_registry"])

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
    cleanup = cleanup_runtime_network(root, plan)
    retain(root / "runtime-network-closure.json", cleanup)
    retain(root / "run-summary.json", {"version": VERSION, "rows": results, "model_calls": 0,
                                     "runtime_network_cleanup": cleanup})
    return results


def collect_outcomes(plan):
    results = []
    for row in plan["rows"]:
        folder = Path(row["directory"])
        outcome = {key: row[key] for key in (
            "slot_id", "instance_id", "condition_id", "original_request", "original_patch", "native_candidate_lock", "request")}
        outcome.update(environment_revision=plan["environment_revision"],
                       environment_qualification=plan["environment_qualification"],
                       grading_network_lane={"registry": plan["grading_nat_registry"], "lane": row["lane"]},
                       known=False)
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
                    or identity.get("environment_revision") != plan["environment_revision"]
                    or identity.get("environment_qualification") != plan["environment_qualification"]
                    or identity.get("grading_network_lane") != outcome["grading_network_lane"]
                    or digest(canonical(identity)) != receipt.get("identity_sha256")):
                raise ValueError("New grader identity differs from its immutable candidate or environment")
            outcome.update(receipt=receipt, receipt_pointer=pointer, identity=paths["identity"],
                           quiescence=quiet, quiescence_reference=quiet_ref, known=True)
        except Exception as error:
            outcome["error"] = {"type": type(error).__name__, "message": str(error)}
        results.append(outcome)
    return results


def reconciled_state(state, prior, allowed_slot_ids, outcomes):
    """Replace only verified same-candidate scores; uncertain repair never invents success."""
    if state != prior:
        raise ValueError("Original queue state changed during environment repair")
    value = copy.deepcopy(state)
    rows = {row["slot"]["slot_id"]: row for row in value["rows"]}
    changed, unresolved, seen = [], [], set()
    for outcome in outcomes:
        slot_id = outcome["slot_id"]
        if slot_id not in allowed_slot_ids or slot_id in seen or slot_id not in rows:
            raise ValueError("Unexpected or duplicate environment-repair slot")
        seen.add(slot_id)
        row = rows[slot_id]
        if (row["generation"]["status"] != "closed" or row["score"]["status"] != "official_report"
                or type(row["score"].get("resolved")) is not bool
                or row["score"]["dispatched_request"] != outcome["original_request"]
                or row["slot"]["condition_id"] != outcome["condition_id"]
                or row["slot"]["instance_id"] != outcome["instance_id"]):
            raise ValueError("Repair belongs to a different original slot or score")
        known = outcome.get("known") is True
        receipt, quiet = outcome.get("receipt", {}), outcome.get("quiescence", {})
        if known:
            if (any(body.get("slot_id") != slot_id or body.get("condition_id") != outcome["condition_id"]
                    for body in (receipt, quiet))
                    or receipt.get("scoring_recovery_of") != outcome["original_request"]
                    or receipt.get("original_patch") != outcome["original_patch"]
                    or receipt.get("native_candidate_lock") != outcome["native_candidate_lock"]
                    or receipt.get("environment_revision") != outcome["environment_revision"]
                    or receipt.get("environment_qualification") != outcome["environment_qualification"]):
                raise ValueError("Receipt does not bind the original candidate and qualified environment")
            if (receipt.get("grading_network_lane") != outcome["grading_network_lane"]
                    or quiet.get("grading_network_lane") != outcome["grading_network_lane"]):
                raise ValueError("Receipt or cleanup belongs to a different runtime grading network")
            known = (receipt.get("status") == "official_report" and type(receipt.get("resolved")) is bool
                and receipt.get("model_calls") == 0 and receipt.get("actor_feedback") is False
                and receipt.get("candidate_changed") is False and quiet.get("quiescent") is True
                and not quiet.get("cleanup_errors") and quiet.get("create_result_unknown") is False)
        if not known:
            row["environment_review"] = {"status": "unresolved", "original_score_preserved": True,
                "environment_revision": outcome["environment_revision"], "request": outcome["request"],
                "completion": outcome.get("completion"), "diagnostic": outcome.get("error"),
                "new_receipt": outcome.get("receipt_pointer"),
                "old_score_not_confirmed_in_repaired_environment": True}
            unresolved.append(slot_id)
            continue
        old = copy.deepcopy(row["score"])
        row.setdefault("prior_scoring_attempts", []).append(old)
        row["score"] = {**old, "status": "official_report", "resolved": receipt["resolved"],
            "request": outcome["request"], "dispatched_request": outcome["request"],
            "receipt": outcome["receipt_pointer"], "quiescence": outcome["quiescence_reference"],
            "quiescent": True, "scoring_revision": receipt["version"],
            "environment_revision": outcome["environment_revision"],
            "environment_qualification": outcome["environment_qualification"],
            "grading_network_lane": outcome["grading_network_lane"],
            "recovered_from": outcome["original_request"], "recovery_completion": outcome["completion"]}
        row["score"].pop("job_id", None)
        row["score"].pop("reason", None)
        row.pop("environment_review", None)
        changed.append({"slot_id": slot_id, "old_resolved": old["resolved"], "new_resolved": receipt["resolved"]})
    if seen != allowed_slot_ids:
        raise ValueError("Every one of the fixed sixteen slots needs a result or an explicit unresolved record")
    return value, changed, unresolved


def reconcile(root):
    root = Path(root)
    plan = validate_plan(load(reference(root / "plan.json")))
    if (root / "reconciliation.json").exists():
        return load(reference(root / "reconciliation.json"))
    outcomes = collect_outcomes(plan)
    retain(root / "collected-outcomes.json", {"version": VERSION, "rows": outcomes})
    with queue.lock(QUEUE / "coordinator.lock"):
        current_ref = reference(QUEUE / "state.json")
        current = load(current_ref)
        merged, changed, unresolved = reconciled_state(current, load(plan["pre_state"]),
            {row["slot_id"] for row in plan["rows"]}, outcomes)
        strata = {"repaired_environment_official_reports": len(changed),
            "original_environment_other_official_reports": sum(
                row["score"]["status"] == "official_report" and row["slot"]["instance_id"] not in environment.PROFILES
                for row in merged["rows"]),
            "environment_repair_unresolved": len(unresolved),
            "unchanged_generation_unknown": sum(row["generation"]["status"] == "deferred" for row in merged["rows"]),
            "homogeneous_full_panel_environment": False}
        record = {"version": VERSION, "utc": queue.now(), "prior_state": current_ref,
            "retained_pre_state": plan["pre_state"], "environment_revision": plan["environment_revision"],
            "environment_qualification": plan["environment_qualification"],
            "grading_nat_registry": plan["grading_nat_registry"],
            "runtime_network_closure": reference(root / "runtime-network-closure.json"),
            "score_changes": changed, "unresolved_slots": unresolved, "scoring_environment_strata": strata,
            "generation_restarted": False, "candidate_content_changed": False, "model_calls": 0,
            "new_scoring_revision": load(plan["scorer_manifest"])["version"],
            "analysis_output": str(root / "analysis-r1")}
        merged["updated_utc"] = record["utc"]
        merged.setdefault("score_recoveries", []).append(record)
        atomic_write(QUEUE / "state.json", json_bytes(merged))
        status = queue.summary(merged)
        status["scoring_environment_strata"] = strata
        atomic_write(QUEUE / "status.json", json_bytes(status))
        with (QUEUE / "events.jsonl").open("a") as stream:
            stream.write(json.dumps({"utc": record["utc"], "kind": "requests_environment_scores_reconciled",
                "updated_slots": [row["slot_id"] for row in changed], "unresolved_slots": unresolved,
                "model_calls": 0}) + "\n")
        record["post_state"] = reference(QUEUE / "state.json")
        write_new(root / "reconciliation.json", record)
    spec = importlib.util.spec_from_file_location("v057_environment_analysis", ROOT / "tools/analyze_ref_budget_results_v056.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.analyze(QUEUE / "state.json", root / "analysis-r1")
    summary_path = root / "analysis-r1/summary.json"
    summary = json.loads(summary_path.read_bytes())
    summary.update(scoring_environment_strata=strata, environment_repair=reference(root / "reconciliation.json"))
    atomic_write(summary_path, json_bytes(summary))
    with (root / "analysis-r1/scoring-environments.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("slot_id", "condition_id", "score_status", "resolved",
            "environment_revision", "environment_review_pending"), lineterminator="\n")
        writer.writeheader()
        for row in merged["rows"]:
            writer.writerow({"slot_id": row["slot"]["slot_id"], "condition_id": row["slot"]["condition_id"],
                "score_status": row["score"]["status"], "resolved": row["score"].get("resolved"),
                "environment_revision": row["score"].get("environment_revision", {}).get("sha256", "original-v056"),
                "environment_review_pending": row.get("environment_review", {}).get("status") == "unresolved"})
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--phase", choices=("prepare", "run", "reconcile"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute == bool(args.phase):
        parser.error("Specify either --execute or one --phase")
    for phase in (("prepare", "run", "reconcile") if args.execute else (args.phase,)):
        value = prepare(args.root, args.qualification) if phase == "prepare" else globals()[phase](args.root)
        print(json.dumps({"phase": phase, "root": str(args.root),
            "summary": value if phase == "reconcile" else "complete"}), flush=True)


if __name__ == "__main__":
    main()
