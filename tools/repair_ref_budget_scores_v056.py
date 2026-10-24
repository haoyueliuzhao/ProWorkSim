"""Repair only six frozen UTF-8 scoring failures, without rerunning generation."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

from proworksim import software_benchmark_patch_transport_v056 as transport
from proworksim import software_benchmark_queue_v056 as queue
from proworksim.software_benchmark_scorer_v054 import canonical
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.storage import atomic_write, digest, json_bytes

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs/software-benchmark-v056"
DEFAULT_ROOT = RUNS / "score-encoding-repair-r1"
DEFAULT_AUDIT = ROOT / "artifacts/software-benchmark-v056/score-encoding-repair-r1/audit.json"
QUEUE = RUNS / "queue-r2"
VERSION = "v056-six-score-encoding-repair-r1"
SCORER_MODULE = "proworksim.software_benchmark_scorer_r2_v056"


def load(value):
    return json.loads(checked(value).read_bytes())


def scorer_command(request):
    command = queue.scorer_argv(request)
    command[command.index("proworksim.software_benchmark_scorer_v056")] = SCORER_MODULE
    return command


def frozen_sources():
    return [reference(ROOT / path) for path in (
        "tools/repair_ref_budget_scores_v056.py",
        "src/proworksim/software_benchmark_patch_transport_v056.py",
        "src/proworksim/software_benchmark_scorer_r2_v056.py")]


def validate_plan(plan):
    if (plan.get("version") != VERSION or plan.get("concurrency") != 2
            or plan.get("model_calls") != 0 or len(plan.get("rows", [])) != 6):
        raise ValueError("Only the frozen six-score repair may run")
    for item in plan["sources"]:
        checked(item)
    checked(plan["scorer_manifest"])
    audit = load(plan["audit"])
    if {row["slot_id"] for row in plan["rows"]} != set(audit["allowlisted_slot_ids"]):
        raise ValueError("Repair panel differs from the six audited failures")
    return plan


def prepare(root, audit_path=DEFAULT_AUDIT):
    root = Path(root).resolve()
    if not root.is_relative_to(RUNS) or root == RUNS:
        raise ValueError("Use an independent v056 repair directory")
    if (root / "plan.json").exists():
        return validate_plan(load(reference(root / "plan.json")))
    root.mkdir(parents=True, exist_ok=True)
    audit_ref = reference(audit_path)
    audit = load(audit_ref)
    if (audit.get("version") != "v056-score-encoding-repair-audit-r1"
            or len(audit.get("rows", [])) != 6
            or len(set(audit["allowlisted_slot_ids"])) != 6):
        raise ValueError("Expected the independently audited six failures")
    with queue.lock(QUEUE / "coordinator.lock"):
        state_ref = reference(QUEUE / "state.json")
        state = load(state_ref)
        if (state.get("complete") is not True or any(job["status"] in {"running", "launch_intent"}
                for job in state["jobs"].values())):
            raise ValueError("Generation and the original scoring queue must have ended")
        pre = write_new(root / "pre-state.json", checked(state_ref).read_bytes())
    cpus = sorted(os.sched_getaffinity(0))
    if len(cpus) < 8:
        raise ValueError("Two scoring lanes require eight distinct host CPUs")
    # The manifest must describe the installed scorer runtime, not this host venv.
    command = scorer_command("unused")[:-4] + ["-c",
        "import json; from proworksim.software_benchmark_scorer_r2_v056 import installation_manifest; "
        "print(json.dumps(installation_manifest()))"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120, check=True)
    manifest = write_new(root / "scorer-manifest.json", json.loads(result.stdout))
    rows_by_id = {row["slot"]["slot_id"]: row for row in state["rows"]}
    rows = []
    for index, item in enumerate(audit["rows"]):
        slot = item["slot"]
        row = rows_by_id[slot["slot_id"]]
        if (row["slot"] != slot or row["generation"]["status"] != "closed"
                or row["score"]["status"] != "deferred"
                or row["score"]["dispatched_request"] != item["original_dispatched_request"]):
            raise ValueError("Audited scoring failure changed before preparation")
        folder = root / "slots" / digest(slot["slot_id"].encode())
        folder.mkdir(parents=True, exist_ok=False)
        record = {"slot_id": slot["slot_id"], "condition_id": slot["condition_id"],
                  "directory": str(folder), "lane": index % 2,
                  "original_request": item["original_dispatched_request"]}
        try:
            old = load(item["original_dispatched_request"])
            representation = transport.prepare_transport(old["native_candidate_lock"], folder / "transport")
            request = {**old, "scorer_manifest": manifest,
                "trusted_output_root": str(root / "official-output"),
                "receipt_output": str(folder / "receipt.json"),
                "quiescence_output": str(folder / "quiescence.json"),
                "scoring_cpuset_cpus": ",".join(map(str, cpus[(index % 2) * 4:(index % 2 + 1) * 4])),
                "scoring_recovery_of": item["original_dispatched_request"],
                "patch_transport": representation}
            record.update(status="prepared", request=write_new(folder / "request.json", request),
                          patch_transport=representation)
        except Exception as error:
            record.update(status="preparation_failed", error={"type": type(error).__name__, "message": str(error)})
            write_new(folder / "preparation-error.json", record)
        rows.append(record)
    plan = {"version": VERSION, "created_utc": queue.now(), "audit": audit_ref,
            "queue": str(QUEUE), "source_state": state_ref, "pre_state": pre,
            "scorer_manifest": manifest, "sources": frozen_sources(), "concurrency": 2,
            "per_score_cpus": 4, "host_timeout_seconds": 3600,
            "model_calls": 0, "candidate_content_changed": False, "rows": rows}
    write_new(root / "plan.json", plan)
    return validate_plan(plan)


def run_one(plan, row):
    folder = Path(row["directory"])
    if row["status"] != "prepared":
        return row
    completion = folder / "completion.json"
    if completion.exists():
        return load(reference(completion))
    if (folder / "started.json").exists():
        return {"slot_id": row["slot_id"], "status": "deferred", "reason": "Entered scorer is never automatically replayed"}
    start = time.monotonic()
    process = None
    result = {"version": VERSION, "slot_id": row["slot_id"], "request": row["request"],
              "started_utc": queue.now(), "model_calls": 0}
    try:
        validate_plan(plan)
        request = load(row["request"])
        transport.validate_transport(request["native_candidate_lock"], request["patch_transport"])
        # Retain the original 128-GiB floor plus two 64-GiB scoring reservations.
        if shutil.disk_usage(ROOT).free < 256 * queue.GIB:
            raise RuntimeError("Insufficient disk capacity for two scorers and the existing safety floor")
        available = next(int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()
                         if line.startswith("MemAvailable:"))
        if available < 160 * queue.GIB:
            raise RuntimeError("Insufficient memory for two 16-GiB scorers and 128-GiB safety margin")
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
            result["owned_process_group_stopped"] = True
        result.setdefault("returncode", process.returncode if process is not None else None)
    result.update(finished_utc=queue.now(), elapsed_seconds=time.monotonic() - start)
    write_new(completion, result)
    return result


def run(root):
    root = Path(root)
    plan = validate_plan(load(reference(root / "plan.json")))

    def lane(index):
        rows = [row for row in plan["rows"] if row["lane"] == index]
        outcomes = []
        quarantine = root / f"lane-{index}-quarantined.json"
        if quarantine.exists():
            return [{"lane": index, "status": "deferred", "reason": "Scoring lane remains quarantined"}]
        try:
            with queue.lock(RUNS / "queue-resource-locks" / f"grader-{index}.lock"):
                for row in rows:
                    outcome = run_one(plan, row)
                    outcomes.append(outcome)
                    if row["status"] != "prepared" or not (Path(row["directory"]) / "started.json").exists():
                        continue
                    # A failed scorer cannot release its lane without real resource evidence.
                    request = load(row["request"])
                    try:
                        quiet = load(reference(request["quiescence_output"]))
                        proved = (quiet.get("slot_id") == row["slot_id"]
                            and quiet.get("condition_id") == row["condition_id"]
                            and quiet.get("quiescent") is True and not quiet.get("cleanup_errors")
                            and quiet.get("create_result_unknown") is False)
                    except (OSError, ValueError, KeyError):
                        proved = False
                    if not proved:
                        write_new(quarantine, {"lane": index, "utc": queue.now(), "slot_id": row["slot_id"],
                            "reason": "Scorer process ended without trustworthy container quiescence",
                            "remaining_lane_slots_not_started": True})
                        break
        except Exception as error:
            outcomes.append({"lane": index, "status": "deferred", "error": str(error)})
        return outcomes

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(lane, index) for index in (0, 1)]
        outcomes = [item for future in futures for item in future.result()]
    path = root / "run-summary.json"
    if not path.exists():
        write_new(path, {"version": VERSION, "rows": outcomes, "model_calls": 0})
    return outcomes


def collect_outcomes(plan):
    results = []
    for row in plan["rows"]:
        if row["status"] != "prepared":
            continue
        folder = Path(row["directory"])
        try:
            completion = load(reference(folder / "completion.json"))
            if completion.get("returncode") != 0 or completion.get("request") != row["request"]:
                continue
            request = load(row["request"])
            pointer = reference(request["receipt_output"])
            paths = load(pointer)
            receipt, identity = load(paths["receipt"]), load(paths["identity"])
            quiet_ref = reference(request["quiescence_output"])
            quiet = load(quiet_ref)
            if (identity.get("slot_id") != row["slot_id"]
                    or identity.get("condition_id") != row["condition_id"]
                    or identity.get("native_candidate_lock") != request["native_candidate_lock"]
                    or identity.get("scoring_recovery_of") != row["original_request"]
                    or identity.get("patch_transport") != request["patch_transport"]
                    or digest(canonical(identity)) != receipt.get("identity_sha256")):
                raise ValueError("Recovery receipt identity differs from its candidate/request")
            results.append({"slot_id": row["slot_id"], "condition_id": row["condition_id"],
                "request": row["request"], "original_request": row["original_request"],
                "patch_transport": request["patch_transport"], "receipt": receipt,
                "receipt_pointer": pointer, "quiescence": quiet, "quiescence_reference": quiet_ref,
                "completion": reference(folder / "completion.json")})
        except Exception as error:
            path = folder / "reconciliation-error.json"
            if not path.exists():
                write_new(path, {"type": type(error).__name__, "message": str(error), "slot_id": row["slot_id"]})
    return results


def reconciled_state(state, prior, allowed_slot_ids, outcomes):
    """Pure merge: only proved official scoring can resolve an audited unknown."""
    if state != prior:
        raise ValueError("Original queue state changed during repair")
    value = copy.deepcopy(state)
    rows = {row["slot"]["slot_id"]: row for row in value["rows"]}
    changed, seen = [], set()
    for outcome in outcomes:
        slot_id = outcome["slot_id"]
        if slot_id not in allowed_slot_ids or slot_id in seen or slot_id not in rows:
            raise ValueError("Unexpected or duplicate recovery slot")
        seen.add(slot_id)
        row = rows[slot_id]
        receipt, quiet = outcome["receipt"], outcome["quiescence"]
        if (row["generation"]["status"] != "closed" or row["score"]["status"] != "deferred"
                or row["score"]["dispatched_request"] != outcome["original_request"]
                or row["slot"]["condition_id"] != outcome["condition_id"]
                or any(body.get("slot_id") != slot_id or body.get("condition_id") != outcome["condition_id"]
                       for body in (receipt, quiet))
                or receipt.get("scoring_recovery_of") != outcome["original_request"]
                or receipt.get("patch_transport") != outcome["patch_transport"]):
            raise ValueError("Recovery belongs to a different slot, condition or original candidate")
        if (receipt.get("status") != "official_report" or type(receipt.get("resolved")) is not bool
                or receipt.get("model_calls") != 0 or receipt.get("actor_feedback") is not False
                or receipt.get("candidate_changed") is not False
                or quiet.get("quiescent") is not True or quiet.get("cleanup_errors")
                or quiet.get("create_result_unknown") is not False):
            continue
        old_score = copy.deepcopy(row["score"])
        row.setdefault("prior_scoring_attempts", []).append(old_score)
        row["score"] = {**old_score, "status": "official_report", "resolved": receipt["resolved"],
            "request": outcome["request"], "dispatched_request": outcome["request"],
            "receipt": outcome["receipt_pointer"], "quiescence": outcome["quiescence_reference"],
            "quiescent": True, "scoring_revision": receipt.get("version"),
            "recovery_completion": outcome["completion"], "recovered_from": outcome["original_request"]}
        row["score"].pop("reason", None)
        row["score"].pop("job_id", None)
        changed.append(slot_id)
    resolved = [item for item in value["deferred"] if item.get("phase") == "score" and item.get("slot_id") in changed]
    value["deferred"] = [item for item in value["deferred"] if item not in resolved]
    value.setdefault("resolved_deferred", []).extend(resolved)
    return value, changed


def reconcile(root):
    root = Path(root)
    plan = validate_plan(load(reference(root / "plan.json")))
    if (root / "reconciliation.json").exists():
        return load(reference(root / "reconciliation.json"))
    outcomes = collect_outcomes(plan)
    with queue.lock(QUEUE / "coordinator.lock"):
        current_ref = reference(QUEUE / "state.json")
        current = load(current_ref)
        merged, changed = reconciled_state(current, load(plan["pre_state"]),
                                           set(load(plan["audit"])["allowlisted_slot_ids"]), outcomes)
        record = {"version": VERSION, "utc": queue.now(), "prior_state": current_ref,
            "retained_pre_state": plan["pre_state"], "updated_slot_ids": changed,
            "resolved_score_count": len(changed), "generation_restarted": False,
            "candidate_content_changed": False, "model_calls": 0,
            "new_scoring_revision": load(plan["scorer_manifest"])["version"],
            "analysis_output": str(root / "analysis-r2")}
        merged["updated_utc"] = record["utc"]
        merged.setdefault("score_recoveries", []).append(record)
        atomic_write(QUEUE / "state.json", json_bytes(merged))
        atomic_write(QUEUE / "status.json", json_bytes(queue.summary(merged)))
        with (QUEUE / "events.jsonl").open("a") as stream:
            stream.write(json.dumps({"utc": record["utc"], "kind": "encoding_score_reconciled",
                                    "slot_ids": changed, "model_calls": 0}) + "\n")
        record["post_state"] = reference(QUEUE / "state.json")
        write_new(root / "reconciliation.json", record)
    spec = importlib.util.spec_from_file_location("v056_repair_analysis", ROOT / "tools/analyze_ref_budget_results_v056.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.analyze(QUEUE / "state.json", root / "analysis-r2")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--phase", choices=("prepare", "run", "reconcile"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute == bool(args.phase):
        parser.error("Specify either --execute or one --phase")
    phases = ("prepare", "run", "reconcile") if args.execute else (args.phase,)
    for phase in phases:
        result = prepare(args.root, args.audit) if phase == "prepare" else globals()[phase](args.root)
        print(json.dumps({"phase": phase, "root": str(args.root),
                          "summary": result if phase == "reconcile" else "complete"}), flush=True)


if __name__ == "__main__":
    main()
