"""CAL2 r3: only seven wholly unopened slots; no retry/exposure exception."""
from __future__ import annotations

import argparse
import ast
import copy
import inspect
from pathlib import Path
import shutil
import time
from types import FunctionType

from proworksim.audit import code_identity
from proworksim.online_training import sha_file
from proworksim.storage import digest, read_json
from scripts import software_calibration_v051_cal2 as base
from scripts import software_calibration_v051_cal2_resume as previous

VERSION = "software-calibration-cal2-resume-r3-v0.51"
MODULE = "scripts.software_calibration_v051_cal2_resume_r3"
PREDECESSOR = base.SOURCE / "runs/software-calibration-v051-cal2-r2"
RESUME_ROOT = base.SOURCE / "runs/software-calibration-v051-cal2-r3"
RELEASE = base.DOCS / "software-calibration-v051-cal2-r3-release.json"
ADMISSION = base.DOCS / "software-calibration-v051-cal2-r3-admission.json"
ENVIRONMENT_AUDIT = base.ASSETS / "cal2-r2-first-execution-audit/report.json"
PENDING = (
    "v051-cal2-parse-2-U", "v051-cal2-xmltodict-1-P", "v051-cal2-xmltodict-1-U",
    "v051-cal2-xmltodict-1-R", "v051-cal2-xmltodict-2-U", "v051-cal2-xmltodict-2-R",
    "v051-cal2-xmltodict-2-P")
RELEASE_CHECKS = {"predecessor_fully_closed", "only_seven_wholly_unstarted", "exclude_all_entered_slots",
    "preserve_original_faults_scores_costs", "source_environment_fault_bound", "no_old_rescore_or_replay",
    "environment_validity_overlay_bound"}
ADMISSION_CHECKS = {"runtime_repairs_controlled", "inherited_source_and_CPU_evidence_reused",
    "resume_host_controls", "original_scientific_contract_unchanged", "current_resource_policy_bound",
    "environment_validity_layer_bound"}
REPAIRED = "src/proworksim/software_calibration_repo_tests_v051.py"


def select_rows(original_rows, predecessor_rows, supervisor):
    """Every entered r2 slot is excluded regardless of score, failure or exposure."""
    states = supervisor.get("states", {})
    ids = [row["slot_id"] for row in predecessor_rows]
    if (len(original_rows) != 18 or len(ids) != 15 or len(set(ids)) != 15 or set(states) != set(ids)
            or supervisor.get("status") != "paused" or supervisor.get("ended_at") is None
            or supervisor.get("active") or supervisor.get("active_workers")):
        raise ValueError("The predecessor must be terminal paused with no active workers")
    if predecessor_rows != [r for r in original_rows if r["slot_id"] not in previous.EXCLUDED]:
        raise ValueError("The original ordered eighteen-to-fifteen inventory changed")
    unopened = []
    for name in ids:
        state = states[name]
        if state.get("status") == "not_started" and state.get("attempts") == []:
            unopened.append(name)
            continue
        attempts = state.get("attempts", [])
        if (state.get("status") not in {"complete", "stopped"} or not attempts
                or any(a.get("ended_at") is None or type(a.get("exit_code")) is not int for a in attempts)):
            raise ValueError("No running or incompletely closed predecessor attempt is eligible")
    if tuple(unopened) != PENDING:
        raise ValueError("Only the seven exact not_started/empty-attempt slots may enter r3")
    selected = [copy.deepcopy(row) for row in original_rows if row["slot_id"] in PENDING]
    if ([r["slot_id"] for r in selected] != list(PENDING) or sum(r["condition"] == "R" for r in selected) != 2
            or sum(r["condition"] != "R" for r in selected) != 5):
        raise ValueError("Keep original order, two R and five P/U conditions")
    return selected


def historical_reference(item, plans, *, repository_root=base.SOURCE):
    """Resolve each old main-tree SHA against the matching r2 or r1 snapshot."""
    path = Path(item["path"])
    path = path if path.is_absolute() else Path(repository_root) / path
    try:
        relative = str(path.relative_to(repository_root))
    except ValueError:
        relative = None
    matches = [plan for plan in plans if plan["source_files"].get(relative) == item["sha256"]]
    if matches:
        return previous.historical_reference(item, matches[0], repository_root=repository_root)
    if any(relative in plan["source_files"] for plan in plans):
        raise ValueError("Historical source SHA matches neither original snapshot")
    for plan in plans:
        if any(Path(row["original"]["path"]) == path and row["original"]["sha256"] == item["sha256"]
               for row in plan.get("evidence", [])):
            return previous.historical_reference(item, plan, repository_root=repository_root)
    return previous.historical_reference(item, plans[0], repository_root=repository_root)


def gates(release, admission, references):
    if (release.get("version") != "v051-cal2-r3-dispatch-release-v1" or release.get("stage") != "CAL2-r3"
            or release.get("released") is not True or release.get("unresolved_blockers") != []
            or not base.required_checks(release.get("checks"), RELEASE_CHECKS)
            or any(release.get(k) != references[k] for k in ("predecessor_plan", "predecessor_supervisor",
                "predecessor_pause", "predecessor_stage_report", "environment_audit", "resource_policy"))):
        raise ValueError("A separate terminal-predecessor/seven-slot r3 release is required")
    if (admission.get("version") != "v051-cal2-r3-compound-admission-v1" or admission.get("stage") != "CAL2-r3"
            or admission.get("released") is not True or admission.get("unresolved_blockers") != []
            or not base.required_checks(admission.get("checks"), ADMISSION_CHECKS)
            or any(admission.get(k) != references[k] for k in ("resume_release", "source_qualified", "resource_policy", "environment_audit"))
            or not admission.get("control_references")):
        raise ValueError("An independent r3 runtime/environment/host admission is required")


def algorithm_binding():
    namespace = dict(base.__dict__)
    namespace.update(VERSION=VERSION, frozen=frozen)
    worker = FunctionType(base.worker.__code__, namespace, base.worker.__name__, base.worker.__defaults__, base.worker.__closure__)
    worker.__kwdefaults__ = base.worker.__kwdefaults__
    source = inspect.getsource(base.supervise)
    tree, changed = ast.parse(source), 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == "scripts.software_calibration_v051_cal2":
            node.value = MODULE
            changed += 1
    if changed != 1:
        raise ValueError("The inherited supervisor must have one worker-module literal")
    ast.fix_missing_locations(tree)
    exec(compile(tree, "<CAL2-r3-sole-worker-module-rebinding>", "exec"), namespace)
    return worker, namespace["supervise"], {"base_host": base.ref(Path(base.__file__)),
        "worker_code_unchanged": True, "supervisor_source_sha256": digest(source.encode()),
        "supervisor_AST_sha256": digest(ast.dump(tree, include_attributes=False).encode()),
        "AST_constant_replacements": 1, "worker_module": MODULE,
        "global_rebindings": ["VERSION", "frozen"], "old_module_globals_modified": False}


def prepare(root):
    root = Path(root).resolve()
    if root != RESUME_ROOT.resolve() or root.exists():
        raise ValueError("r3 has one predeclared fresh root and no entered-slot exception")
    identity = code_identity()
    if identity.get("code_dirty") is not False:
        raise ValueError("Commit r3 source and independent gates before freezing")
    old = base.unseal(read_json(PREDECESSOR / "plan.json"))
    earlier = base.unseal(read_json(base.checked(old["original_references"]["original_plan"])))
    supervisor, pause, release, admission = map(read_json, (PREDECESSOR / "supervisor.json", PREDECESSOR / "pause.json", RELEASE, ADMISSION))
    audit = read_json(ENVIRONMENT_AUDIT)
    original = base.inventory(read_json(base.checked(old["inventory"])))
    if old["original_rows"] != original or old["contract"] != base.CONTRACT or old["limits"] != base.LIMITS:
        raise ValueError("The original scientific inventory and execution contract must persist")
    selected = select_rows(original, old["rows"], supervisor)
    stage_ref = copy.deepcopy(release["predecessor_stage_report"])
    stage = read_json(base.checked(stage_ref))
    refs = {"predecessor_plan": base.ref(PREDECESSOR / "plan.json"),
        "predecessor_supervisor": base.ref(PREDECESSOR / "supervisor.json"),
        "predecessor_pause": base.ref(PREDECESSOR / "pause.json"), "predecessor_stage_report": stage_ref,
        "environment_audit": base.ref(ENVIRONMENT_AUDIT), "resource_policy": base.ref(base.RESOURCE_POLICY),
        "source_qualified": base.ref(base.SOURCE_QUALIFIED), "resume_release": base.ref(RELEASE)}
    if supervisor.get("plan") != refs["predecessor_plan"] or pause.get("kind") != "source_bound_runner_environment_failure":
        raise ValueError("Bind the exact closed r2 environment-failure pause")
    if (stage.get("version") != "software-calibration-v051-cal2-r2-unique-report-v1"
            or Path(stage.get("root", "")).resolve() != PREDECESSOR.resolve()
            or stage.get("plan") != refs["predecessor_plan"] or stage.get("supervisor") != refs["predecessor_supervisor"]
            or stage.get("host_status") != "paused" or len(stage.get("rows", [])) != 18
            or [r.get("slot_id") for r in stage["rows"]] != [r["slot_id"] for r in original]
            or [r.get("slot_id") for r in stage["rows"] if r.get("status") == "not_started"] != list(PENDING)):
        raise ValueError("Bind the terminal unique eighteen-slot report and exact unopened seven")
    if (audit.get("version") != "v051-cal2-r2-first-execution-audit-v1"
            or audit.get("read_only_originals") is not True or audit.get("confirmed_infrastructure_mismatch") is not True
            or audit.get("sources", {}).get("plan") != refs["predecessor_plan"]
            or {row.get("slot_id") for row in audit.get("affected_slots", [])} != {
                "v051-cal2-boltons-1-R", "v051-cal2-boltons-2-R", "v051-cal2-boltons-2-U"}):
        raise ValueError("The source-bound environment audit must preserve the original invalid scores")
    gates(release, admission, refs)
    prior_refs = [old[k] for k in ("inventory", "source_qualified", "cal1_release", "compound_admission",
        "resume_release", "resource_policy_reference", "model_manifest", "mini_manifest")]
    prior_refs += old["upstream_evidence"] + old["control_references"] + list(old["original_references"].values())
    prior_refs += [r["frozen_copy"] for r in old["evidence"]]
    unique = {(r["path"], r["sha256"]): r for r in prior_refs}
    mapped = [historical_reference(item, [old, earlier]) for item in unique.values()]
    for name, sha in old["source_files"].items():
        if sha_file(Path(old["source_root"]) / name) != sha:
            raise ValueError("The original r2 snapshot changed: " + name)
        if name.startswith("src/") and name != REPAIRED and sha_file(base.SOURCE / name) != sha:
            raise ValueError("Only the disclosed repository runner source may change from r2: " + name)
    if sha_file(Path(base.__file__)) != old["source_files"]["scripts/software_calibration_v051_cal2.py"]:
        raise ValueError("The inherited base worker/supervisor must retain r2 bytes")
    controls = admission["control_references"]
    controls = list(controls.values()) if isinstance(controls, dict) else controls
    for item in controls:
        base.checked(item)
    if base.ref(base.SOURCE / REPAIRED) not in controls:
        raise ValueError("Compound admission must bind the newly controlled runner source")
    for row in selected:
        for kind in ("slots", "workers"):
            if (PREDECESSOR / kind / row["slot_id"]).exists():
                raise ValueError("A supposedly unopened slot has a predecessor execution artifact")
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
    for path in (RELEASE, ADMISSION, ENVIRONMENT_AUDIT, Path(stage_ref["path"]), base.SOURCE_QUALIFIED, base.RESOURCE_POLICY):
        destination = root / "evidence" / path.name
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(path, destination)
        evidence.append({"original": base.ref(path), "frozen_copy": base.ref(destination)})
    _, _, adaptation = algorithm_binding()
    plan = copy.deepcopy(old)
    for key in ("sha256", "one_time_first_exposure_exception", "excluded_exposed_slots", "old_costs_not_transferred"):
        plan.pop(key, None)
    plan.update(version=VERSION, created_at=time.time(), source_commit=identity, source_root=str(snapshot), source_files=sources,
        rows=selected, original_rows=original, predecessor_rows=old["rows"], predecessor_root=str(PREDECESSOR),
        predecessor_references=refs, historical_evidence=mapped, prior_compound_admission=old["compound_admission"],
        compound_admission=base.ref(ADMISSION), resume_release=base.ref(RELEASE), control_references=controls,
        upstream_evidence=[r["resolved_reference"] for r in mapped], evidence=evidence, worker_module=MODULE,
        algorithm_adaptation=adaptation, maximum_slots=7, maximum_actual_tokens=3500000,
        maximum_decisions=896, maximum_attempts=896, maximum_public_project_tests=160,
        excluded_entered_slots=[r["slot_id"] for r in old["rows"] if r["slot_id"] not in PENDING],
        first_exposure_or_loader_retry_exceptions=False, old_remaining_budget_transfer=0,
        preserved_prior_cost_sources=[stage_ref],
        original_stage_lineage_reference=old["original_references"]["original_stage_report"],
        prior_cost_scope="The sole cost source is the merged r1+r2 stage report; the original stage is lineage only and is never added again. r3 ledger contains only new work",
        old_terminal_code_unknowns_retained=True, old_scores_reconstructed=False,
        environment_validity_audit=refs["environment_audit"])
    plan = base.sealed(plan)
    base.write(root / "plan.json", plan)
    return plan


def frozen(root):
    plan = base.unseal(read_json(Path(root) / "plan.json"))
    if (plan.get("version") != VERSION or plan.get("contract") != base.CONTRACT or plan.get("limits") != base.LIMITS
            or plan.get("gpu_preference") != list(range(8)) or plan.get("idle_only_admission") is not False
            or plan.get("fresh_resident_per_slot") is not True or plan.get("worker_module") != MODULE
            or [plan.get(k) for k in ("maximum_slots", "maximum_actual_tokens", "maximum_decisions", "maximum_attempts", "maximum_public_project_tests")]
                != [7, 3500000, 896, 896, 160] or plan.get("old_remaining_budget_transfer") != 0
            or plan.get("first_exposure_or_loader_retry_exceptions") is not False
            or "one_time_first_exposure_exception" in plan):
        raise ValueError("Frozen r3 scientific contract, seven-slot limits or no-retry policy differs")
    for name, sha in plan["source_files"].items():
        if sha_file(Path(plan["source_root"]) / name) != sha:
            raise ValueError("r3 source snapshot changed: " + name)
    for item in [*plan["predecessor_references"].values(), plan["compound_admission"],
                 *plan["control_references"], *plan["upstream_evidence"],
                 plan["S_star"]["checkpoint"], plan["S_star"]["state_file_reference_from_original_metadata"],
                 *[r["frozen_copy"] for r in plan["evidence"]]]:
        base.checked(item)
    refs = plan["predecessor_references"]
    gates(read_json(base.checked(plan["resume_release"])), read_json(base.checked(plan["compound_admission"])), refs)
    old = base.unseal(read_json(base.checked(refs["predecessor_plan"])))
    supervisor = read_json(base.checked(refs["predecessor_supervisor"]))
    if (old["original_rows"] != plan["original_rows"] or old["rows"] != plan["predecessor_rows"]
            or old["S_star"] != plan["S_star"]
            or select_rows(plan["original_rows"], old["rows"], supervisor) != plan["rows"]):
        raise ValueError("Original rows, state or exact unopened seven-slot selection changed")
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
