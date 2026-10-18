"""One CAL2 r2 continuation: fourteen unopened slots plus one proved unexposed R.

Old stages and scores are immutable. The original worker/supervisor algorithms
run in a private namespace with a new frozen-plan reader, host version and one
worker-module literal replacement; model, world, budget and stop rules persist.
"""
from __future__ import annotations

import argparse
import ast
import copy
import inspect
from pathlib import Path
import shutil
from types import FunctionType
import time

from proworksim.online_training import sha_file
from proworksim.storage import digest, read_json
from scripts import software_calibration_v051_cal2 as base

VERSION = "software-calibration-cal2-resume-r2-v0.51"
MODULE = "scripts.software_calibration_v051_cal2_resume"
ORIGINAL = base.SOURCE / "runs/software-calibration-v051-cal2"
RESUME_ROOT = base.SOURCE / "runs/software-calibration-v051-cal2-r2"
ORIGINAL_REPORT = base.DOCS / "software-calibration-v051-cal2-initial-stage.json"
ZERO_R_AUDIT = base.ASSETS / "cal2-R-initial-tree-audit/report.json"
RELEASE = base.DOCS / "software-calibration-v051-cal2-r2-release.json"
ADMISSION = base.DOCS / "software-calibration-v051-cal2-r2-admission.json"
ZERO_R = "v051-cal2-boltons-1-R"
EXCLUDED = frozenset({"v051-cal2-boltons-1-P", "v051-cal2-boltons-1-U", "v051-cal2-boltons-2-P"})
RELEASE_CHECKS = {"preserve_original_fault_and_costs", "exclude_three_generated_trajectories",
    "one_zero_generation_R_exception", "retain_original_rows_seeds_budgets", "no_old_rescore_or_replay",
    "source_fault_fully_bound", "no_completed_score_reconstructed"}
ADMISSION_CHECKS = {"source_fault_fully_bound", "zero_generation_R_exception_bound",
    "runtime_repairs_controlled", "inherited_source_and_CPU_evidence_reused", "resume_host_controls",
    "original_scientific_contract_unchanged", "current_resource_policy_bound"}
REPAIRABLE_SOURCE = frozenset({"src/proworksim/software_calibration_v051_mini.py",
                             "src/proworksim/software_calibration_repo_tests_v051.py"})


def select_rows(rows, supervisor, audit):
    """No outcome selection; only one exact zero-exposure implementation fault."""
    ids = [row["slot_id"] for row in rows]
    states = supervisor.get("states", {})
    if (len(ids) != 18 or len(set(ids)) != 18 or set(states) != set(ids)
            or supervisor.get("status") != "paused" or supervisor.get("ended_at") is None):
        raise ValueError("The original eighteen-slot paused inventory must be fully closed")
    unopened = []
    for name in ids:
        state, attempts = states[name], states[name].get("attempts", [])
        if state.get("status") == "not_started" and attempts == []:
            unopened.append(name)
        elif (name not in EXCLUDED | {ZERO_R} or state.get("status") != "stopped"
                or len(attempts) != 1 or attempts[0].get("ended_at") is None
                or type(attempts[0].get("exit_code")) is not int
                or attempts[0].get("seconds", 0) <= 0):
            raise ValueError("No running, restarted or other entered slot can join r2")
    if len(unopened) != 14 or set(unopened) != set(ids) - EXCLUDED - {ZERO_R}:
        raise ValueError("Only the original fourteen wholly unopened slots are eligible")
    for name in EXCLUDED:
        account = states[name]["attempts"][0].get("report", {}).get("accounting", {})
        if account.get("started_generations", 0) <= 0 or account.get("complete_generations", 0) <= 0:
            raise ValueError("Bind and permanently exclude all three exposed trajectories")
    zero_row = next(row for row in rows if row["slot_id"] == ZERO_R)
    interruption = audit.get("interruption", {})
    expected_predicates = {"worktree_path_match": True, "source_initial_map_sha_match": True,
        "read_worktree_map_sha_match": False, "commit_count_one": True, "no_remotes": True}
    if (audit.get("version") != "v051-cal2-R-boltons1-readonly-initial-tree-diagnosis-v1"
            or audit.get("read_only_originals") is not True
            or any(audit.get(key) is not True for key in ("initial_document_matches_manifest", "frozen_mini_matches_plan",
                "source_and_native_worktree_raw_bytes_identical", "owner_loaded_raw_release"))
            or audit.get("initial_file_count") != 112 or audit.get("observed_file_count") != 112
            or audit.get("raw_byte_differences") != [] or audit.get("rejection_predicates") != expected_predicates
            or audit.get("initial_map_sha256") != audit.get("origin_initial_map_sha256")
            or any(audit.get(key) != 0 for key in ("native_generation_prepared", "native_generation_started",
                "native_generation_complete", "native_generation_fault", "actual_model_generation_tokens"))
            or audit.get("actual_call_files") != [] or audit.get("native_episode_files") != []
            or any(audit.get(key) is not False for key in ("native_model_ledger_exists", "native_trajectory_exists",
                "native_evaluation_guard_exists"))
            or interruption.get("row") != zero_row
            or interruption.get("error") != {"type": "ValueError", "message": "Native case lacks its exact fresh buggy-only initial worktree binding"}):
        raise ValueError("The sole R exception requires exact zero native exposure and the bound CRLF fault")
    differences = audit.get("frozen_read_worktree_differences", [])
    if ({row.get("path") for row in differences} != {"LICENSE", "docs/make.bat"}
            or len(differences) != 2 or not all(row.get("equal_after_universal_newline_conversion") is True for row in differences)):
        raise ValueError("No other R worktree difference qualifies for the exception")
    selected = [copy.deepcopy(row) for row in rows if row["slot_id"] in set(unopened) | {ZERO_R}]
    if len(selected) != 15 or sum(row["condition"] != "R" for row in selected) != 9:
        raise ValueError("The r2 inventory must be six R and nine P/U slots")
    return selected


def historical_reference(item, old_plan, *, repository_root=base.SOURCE):
    """Resolve a historical main-tree source reference to its original snapshot."""
    original = copy.deepcopy(item)
    path = Path(item["path"])
    path = path if path.is_absolute() else Path(repository_root) / path
    try:
        relative = str(path.relative_to(repository_root))
    except ValueError:
        relative = None
    if relative in old_plan["source_files"]:
        if item["sha256"] != old_plan["source_files"][relative]:
            raise ValueError("Historical reference does not match the original source manifest")
        resolved = base.ref(Path(old_plan["source_root"]) / relative)
        kind = "original_frozen_source_snapshot"
    else:
        copies = [row["frozen_copy"] for row in old_plan.get("evidence", [])
                  if Path(row["original"]["path"]) == path and row["original"]["sha256"] == item["sha256"]]
        resolved = base.ref(base.checked(copies[0])) if copies else base.ref(path)
        kind = "original_frozen_document_copy" if copies else "unchanged_original_evidence"
    if any(resolved[key] != item[key] for key in ("sha256", "bytes")):
        raise ValueError("Historical evidence content changed: " + str(path))
    return {"original_reference": original, "resolved_reference": resolved, "binding": kind}


def gates(release, admission, *, references):
    if (release.get("version") != "v051-cal2-r2-dispatch-release-v1" or release.get("stage") != "CAL2-r2"
            or release.get("released") is not True or release.get("unresolved_blockers") != []
            or not base.required_checks(release.get("checks"), RELEASE_CHECKS)
            or any(release.get(key) != references[key] for key in
                ("original_plan", "original_supervisor", "original_stage_report", "zero_generation_R_audit", "resource_policy"))):
        raise ValueError("A separately authored exact r2 exception/continuation release is required")
    if (admission.get("version") != "v051-cal2-r2-compound-admission-v1" or admission.get("stage") != "CAL2-r2"
            or admission.get("released") is not True or admission.get("unresolved_blockers") != []
            or not base.required_checks(admission.get("checks"), ADMISSION_CHECKS)
            or any(admission.get(key) != references[key] for key in ("resume_release", "source_qualified", "resource_policy"))
            or not admission.get("control_references")):
        raise ValueError("An independent repaired-runtime and r2 host compound admission is required")


def algorithm_binding():
    """Clone functions without mutating the imported original host module."""
    namespace = dict(base.__dict__)
    namespace.update(VERSION=VERSION, frozen=frozen)
    worker = FunctionType(base.worker.__code__, namespace, base.worker.__name__, base.worker.__defaults__, base.worker.__closure__)
    worker.__kwdefaults__ = base.worker.__kwdefaults__
    source = inspect.getsource(base.supervise)
    tree = ast.parse(source)
    changed = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == "scripts.software_calibration_v051_cal2":
            node.value = MODULE
            changed += 1
    if changed != 1:
        raise ValueError("The original supervisor worker-module literal must occur exactly once")
    ast.fix_missing_locations(tree)
    exec(compile(tree, "<CAL2-r2-sole-worker-module-rebinding>", "exec"), namespace)
    return worker, namespace["supervise"], {"base_host": base.ref(Path(base.__file__)),
        "worker_code_unchanged": True, "supervisor_source_sha256": digest(source.encode()),
        "supervisor_AST_sha256": digest(ast.dump(tree, include_attributes=False).encode()),
        "AST_constant_replacements": 1, "old_worker_module": "scripts.software_calibration_v051_cal2",
        "new_worker_module": MODULE, "global_rebindings": ["VERSION", "frozen"],
        "old_module_globals_modified": False}


def prepare(root):
    from proworksim.audit import code_identity

    root = Path(root).resolve()
    if root != RESUME_ROOT.resolve():
        raise ValueError("The one authorized r2 inventory has one predeclared root")
    if root.exists():
        raise FileExistsError("r2 requires a fresh independent root")
    identity = code_identity()
    if identity.get("code_dirty") is not False:
        raise ValueError("Commit r2 source and independent gates before freezing")
    old = base.unseal(read_json(ORIGINAL / "plan.json"))
    supervisor, report, audit = map(read_json, (ORIGINAL / "supervisor.json", ORIGINAL_REPORT, ZERO_R_AUDIT))
    original_rows = base.inventory(read_json(base.checked(old["inventory"])))
    if old["rows"] != original_rows or old["contract"] != base.CONTRACT or old["limits"] != base.LIMITS:
        raise ValueError("Original scientific inventory or execution contract differs")
    refs = {"original_plan": base.ref(ORIGINAL / "plan.json"), "original_supervisor": base.ref(ORIGINAL / "supervisor.json"),
        "original_stage_report": base.ref(ORIGINAL_REPORT), "zero_generation_R_audit": base.ref(ZERO_R_AUDIT),
        "resource_policy": base.ref(base.RESOURCE_POLICY), "source_qualified": base.ref(base.SOURCE_QUALIFIED),
        "resume_release": base.ref(RELEASE)}
    if (supervisor.get("plan") != refs["original_plan"] or report.get("plan") != refs["original_plan"]
            or report.get("supervisor") != refs["original_supervisor"]
            or report.get("host_status") != "paused" or report.get("new_scoring_calls") != 0
            or audit.get("sources", {}).get("plan") != refs["original_plan"]):
        raise ValueError("Bind original closed stages and zero-R audit without rescoring")
    if (supervisor.get("ledger", {}).get("known_actual_tokens") != 227876
            or supervisor["ledger"].get("complete_generations") != 22
            or report.get("billing", {}).get("known_actual_tokens") != 227876
            or report["billing"].get("complete_generations") != 22):
        raise ValueError("Preserve the original unique cost inventory exactly once")
    selected = select_rows(original_rows, supervisor, audit)
    release, admission = map(read_json, (RELEASE, ADMISSION))
    gates(release, admission, references=refs)
    prior_refs = [old[key] for key in ("inventory", "source_qualified", "cal1_release", "compound_admission",
        "resource_policy_reference", "model_manifest", "mini_manifest")]
    prior_refs += old["upstream_evidence"] + [r["frozen_copy"] for r in old["evidence"]]
    prior_refs += list(audit["sources"].values())
    mapped = [historical_reference(item, old) for item in prior_refs]
    for name, sha in old["source_files"].items():
        if sha_file(Path(old["source_root"]) / name) != sha:
            raise ValueError("Original source snapshot changed: " + name)
        current = base.SOURCE / name
        if name.startswith("src/") and name not in REPAIRABLE_SOURCE and sha_file(current) != sha:
            raise ValueError("Undeclared scientific/runtime source change: " + name)
    if sha_file(Path(base.__file__)) != old["source_files"]["scripts/software_calibration_v051_cal2.py"]:
        raise ValueError("The inherited worker/supervisor source must be the original host bytes")
    controls = admission["control_references"]
    controls = list(controls.values()) if isinstance(controls, dict) else controls
    for item in controls:
        base.checked(item)
    for name in REPAIRABLE_SOURCE | {"src/proworksim/software_calibration_shell_v051.py"}:
        if base.ref(base.SOURCE / name) not in controls:
            raise ValueError("Compound admission must bind each repaired runtime/helper source: " + name)
    for item in old["S_star"]["checkpoint"], old["S_star"]["state_file_reference_from_original_metadata"]:
        base.checked(item)
    # Absence checks are restricted to the already audited original R/empty slots.
    r_attempt = Path(supervisor["states"][ZERO_R]["attempts"][0]["output"])
    for path in (r_attempt / "resident/calls", r_attempt / "episode"):
        if path.is_symlink() or path.exists() and (not path.is_dir() or any(path.iterdir())):
            raise ValueError("The original R has acquired native material or a non-directory path; exception forbidden")
    for row in selected:
        if row["slot_id"] != ZERO_R and ((ORIGINAL / "slots" / row["slot_id"]).exists()
                or (ORIGINAL / "workers" / row["slot_id"]).exists()):
            raise ValueError("An originally unopened slot now has an execution artifact")
    root.mkdir(parents=True)
    snapshot, sources = root / "source", {}
    for folder in ("src", "scripts"):
        for path in sorted((base.SOURCE / folder).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            relative = path.relative_to(base.SOURCE)
            target = snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            sources[str(relative)] = sha_file(target)
    evidence = []
    for path in (RELEASE, ADMISSION, ORIGINAL_REPORT, ZERO_R_AUDIT, base.SOURCE_QUALIFIED, base.RESOURCE_POLICY):
        destination = root / "evidence" / path.name
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(path, destination)
        evidence.append({"original": base.ref(path), "frozen_copy": base.ref(destination)})
    _, _, adaptation = algorithm_binding()
    plan = copy.deepcopy(old)
    plan.update(version=VERSION, created_at=time.time(), source_commit=identity, source_root=str(snapshot), source_files=sources,
        rows=selected, original_rows=original_rows, original_root=str(ORIGINAL), original_references=refs,
        historical_evidence=mapped, original_compound_admission=old["compound_admission"],
        compound_admission=base.ref(ADMISSION), resume_release=base.ref(RELEASE), control_references=controls,
        upstream_evidence=[r["resolved_reference"] for r in mapped], evidence=evidence,
        worker_module=MODULE, algorithm_adaptation=adaptation, maximum_slots=15, maximum_actual_tokens=7500000,
        maximum_decisions=1920, maximum_attempts=1920, maximum_public_project_tests=288,
        one_time_first_exposure_exception={"slot_id": ZERO_R, "original_attempt_preserved": True,
            "actual_model_state_reused": False, "original_loader_worker_seconds": supervisor["states"][ZERO_R]["attempts"][0]["seconds"],
            "scope": "Only this proved zero-preparation/zero-generation R may receive its first model exposure once in r2; no general post-loader retry"},
        excluded_exposed_slots=sorted(EXCLUDED), old_costs_not_transferred={"source": refs["original_stage_report"],
            "known_actual_tokens": 227876, "complete_generations": 22,
            "gpu_worker_seconds": report["worker_cost"]["gpu_worker_seconds"],
            "scope": "Historical costs remain once in the original stage and eventual unique merged report; r2 ledger contains only new work"},
        old_remaining_budget_transfer=0, old_terminal_code_unknowns_retained=True, old_scores_reconstructed=False)
    plan.pop("sha256", None)
    plan = base.sealed(plan)
    base.write(root / "plan.json", plan)
    return plan


def frozen(root):
    plan = base.unseal(read_json(Path(root) / "plan.json"))
    if (plan.get("version") != VERSION or plan.get("contract") != base.CONTRACT or plan.get("limits") != base.LIMITS
            or plan.get("gpu_preference") != list(range(8)) or plan.get("idle_only_admission") is not False
            or plan.get("fresh_resident_per_slot") is not True or plan.get("worker_module") != MODULE
            or [plan.get(k) for k in ("maximum_slots", "maximum_actual_tokens", "maximum_decisions", "maximum_attempts", "maximum_public_project_tests")]
                != [15, 7500000, 1920, 1920, 288] or plan.get("old_remaining_budget_transfer") != 0):
        raise ValueError("Frozen r2 inventory or unchanged scientific/resource contract differs")
    for name, sha in plan["source_files"].items():
        if sha_file(Path(plan["source_root"]) / name) != sha:
            raise ValueError("r2 source snapshot changed: " + name)
    for item in [*plan["original_references"].values(), plan["compound_admission"],
                 *plan["control_references"], *plan["upstream_evidence"],
                 plan["S_star"]["checkpoint"], plan["S_star"]["state_file_reference_from_original_metadata"],
                 *[r["frozen_copy"] for r in plan["evidence"]]]:
        base.checked(item)
    refs = plan["original_references"]
    gates(read_json(base.checked(plan["resume_release"])), read_json(base.checked(plan["compound_admission"])), references=refs)
    old = base.unseal(read_json(base.checked(refs["original_plan"])))
    supervisor = read_json(base.checked(refs["original_supervisor"]))
    audit = read_json(base.checked(refs["zero_generation_R_audit"]))
    if (old["rows"] != plan["original_rows"] or old["S_star"] != plan["S_star"]
            or select_rows(old["rows"], supervisor, audit) != plan["rows"]
            or plan.get("excluded_exposed_slots") != sorted(EXCLUDED)):
        raise ValueError("Original unique inventory, state or exclusions changed")
    return plan


def worker(root, slot_id, attempt):
    function, _, _ = algorithm_binding()
    return function(root, slot_id, attempt)


def supervise(root):
    _, function, _ = algorithm_binding()
    return function(root)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "supervise", "worker"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--slot")
    parser.add_argument("--attempt", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.root)
    elif args.command == "supervise":
        supervise(args.root)
    else:
        raise SystemExit(worker(args.root, args.slot, args.attempt))


if __name__ == "__main__":
    main()
