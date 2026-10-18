"""Independent gated32-slot HOLD host. Importing this module opens no task data."""
from __future__ import annotations

import argparse
import ast
import copy
import inspect
import os
from pathlib import Path
import shutil
import sys
import time
from types import FunctionType

from proworksim.online_training import sha_file
from proworksim.software_holdout_collector_v051 import NATIVE_CONTRACT
from proworksim.software_holdout_measurement_v051 import CONDITIONS, state_binding
from proworksim.storage import read_json
from scripts import software_calibration_v051_cal2 as base
from scripts.software_calibration_v051 import checked, ref, sealed, unseal, write

VERSION = "software-holdout-host-v0.51"
MODULE = "scripts.software_holdout_v051"
PURPOSE = "held_out_checkpoint_evaluation"
HOLD_IDS = tuple(f"hold-{repo}-{i}" for repo in ("funcy", "python-slugify", "iniconfig", "dominate") for i in (1, 2))
CONTRACT = copy.deepcopy(NATIVE_CONTRACT)
LIMITS = copy.deepcopy(base.LIMITS)
GPU_PREFERENCE = list(range(8))
CHECKS = {"cal2_closure_explained", "common_implementation_frozen_before_HOLD_material",
    "fixed_inventory_bound", "source_qualification_closed", "initial_input_qualification_closed",
    "readonly_states_bound", "measurement_controls", "host_controls", "resource_policy_bound"}


def inventory(metadata):
    rows = [copy.deepcopy(row) for row in metadata["rows"] if row["partition"] == "HOLD"]
    if len(rows) != 32 or len({r["slot_id"] for r in rows}) != 32:
        raise ValueError("Keep all original32 HOLD rows; never filter the logical panel")
    conditions = list(CONDITIONS)
    for i, case in enumerate(HOLD_IDS):
        order = conditions[i % 4:] + conditions[:i % 4]
        for row, condition in zip(rows[i * 4:i * 4 + 4], order, strict=True):
            if (row["task_id"] != case or row["condition"] != condition or row["slot_id"] != f"v051-{case}-{condition}"
                    or row["seed"] != 202610170561 + i
                    or row["first_member"] != ("member_001" if i % 2 == 0 else "member_002")
                    or row["condition_order_for_task"] != order or row["generation_tokens"] != 500000
                    or row["decisions"] != 128 or row["attempts"] != 128 or row["project_public_tests"] != 32):
                raise ValueError("Frozen HOLD task/condition/seed/order/budget changed")
    states = metadata.get("states", {})
    if set(states) != set(CONDITIONS) or any(states[c].get("historical_steps") != ([4, 4] if c == "S_star" else [5, 5])
            for c in CONDITIONS):
        raise ValueError("Freeze the exact four saved-state metadata entries")
    if len({states[c]["actor_identity"]["adapter_sha256"] for c in CONDITIONS}) != 4:
        raise ValueError("The four retained actor states must remain distinct")
    return rows


def qualification_partition(admission, source, inputs):
    rows = admission.get("task_qualification", [])
    if len(rows) != 8 or [row.get("task_id") for row in rows] != list(HOLD_IDS):
        raise ValueError("Explicit qualification status for all eight original tasks is required")
    source_ids, input_ids = source.get("qualified_case_ids"), inputs.get("qualified_case_ids")
    for values in (source_ids, input_ids):
        if not isinstance(values, list) or values != [case for case in HOLD_IDS if case in values]:
            raise ValueError("Qualification must use unique original task order, without replacement")
    if not set(input_ids) <= set(source_ids):
        raise ValueError("Source-blocked tasks cannot undergo initial-input qualification")
    qualified, blocked = [], {}
    for row in rows:
        case = row["task_id"]
        source_ok, input_ok = case in source_ids, case in input_ids
        if (row.get("source_status") != ("qualified" if source_ok else "source_blocked")
                or row.get("input_status") != ("qualified" if input_ok else "input_blocked" if source_ok else "not_run_source_blocked")
                or row.get("dispatch_eligible") is not (source_ok and input_ok)):
            raise ValueError("Task eligibility must be the exact source/input intersection, never score selection")
        if source_ok and input_ok:
            qualified.append(case)
        else:
            if not row.get("reason"):
                raise ValueError("Blocked tasks retain an explicit source/input reason")
            blocked[case] = copy.deepcopy(row)
    if admission.get("qualified_case_ids") != qualified:
        raise ValueError("Dispatch list differs from the declared task qualifications")
    return qualified, blocked


def gate_records(admission, *, source, inputs, common, references):
    if (admission.get("version") != "v051-holdout-model-admission-v1" or admission.get("released") is not True
            or admission.get("purpose") != PURPOSE or admission.get("unresolved_blockers") != []
            or not isinstance(admission.get("checks"), dict) or set(admission["checks"]) != CHECKS
            or any(value is not True for value in admission["checks"].values())
            or any(admission.get(key) != references[key] for key in references)):
        raise ValueError("Independent post-CAL2 HOLD source/input/model admission is required")
    resources = admission.get("resources", {})
    if (resources.get("allowed_gpu_indices") != GPU_PREFERENCE or resources.get("max_residents") != 4
            or resources.get("idle_only_admission") is not False):
        raise ValueError("Preserve authorized all-GPU capacity sharing with maximum4 residents")
    if (common.get("version") != "v051-holdout-common-implementation-freeze-v1"
            or common.get("frozen_before_business_material") is not True
            or not common.get("source_root") or not common.get("source_files")
            or source.get("common_implementation_freeze") != references["common_implementation_freeze"]
            or source.get("source_access_release") != references["source_access_release"]
            or inputs.get("common_implementation_freeze") != references["common_implementation_freeze"]
            or inputs.get("source_qualification") != references["source_qualification"]
            or source.get("fixture_only") is not False or inputs.get("fixture_only") is not False):
        raise ValueError("Use the sole pre-material common implementation and formal qualification receipts")
    return qualification_partition(admission, source, inputs)


def initial_states(rows, qualified_case_ids):
    return {row["slot_id"]: {"status": "not_started" if row["task_id"] in qualified_case_ids else "source_or_input_blocked",
                             "attempts": []} for row in rows}


def inventory_state_closed(state):
    return state["status"] in {"complete", "source_or_input_blocked"}


def prepare(root, *, project_root, admission_path=None):
    """Not invoked during common-code preparation; all content gates precede access."""
    from proworksim.audit import code_identity
    project, root = Path(project_root).resolve(), Path(root).resolve()
    if root.exists():
        raise FileExistsError("HOLD requires a fresh independently gated root")
    admission_path = Path(admission_path or project / "docs/experiments/software-holdout-v051-model-admission.json").resolve()
    admission = read_json(admission_path)
    if admission.get("version") != "v051-holdout-model-admission-v1" or admission.get("released") is not True:
        raise ValueError("HOLD model admission is not released; do not open business material")
    keys = ("common_implementation_freeze", "source_access_release", "source_qualification", "initial_inputs", "resource_policy", "inventory")
    references = {key: copy.deepcopy(admission[key]) for key in keys}
    paths = {key: checked(value) for key, value in references.items()}
    common, source, inputs = (read_json(paths[key]) for key in
                              ("common_implementation_freeze", "source_qualification", "initial_inputs"))
    qualified, blocked = gate_records(admission, source=source, inputs=inputs, common=common, references=references)
    metadata = read_json(paths["inventory"])
    rows = inventory(metadata)
    manifest = source["adapter_manifest"]
    manifest_path = Path(manifest["path"])
    manifest_path = manifest_path if manifest_path.is_absolute() else project / manifest_path
    manifest_reference = ref(manifest_path)
    if any(manifest_reference[key] != manifest[key] for key in ("sha256", "bytes")):
        raise ValueError("Qualified adapter manifest source changed")
    source_root = Path(source["source_root"])
    source_root = source_root if source_root.is_absolute() else project / source_root
    identity = code_identity()
    if identity.get("code_dirty") is not False:
        raise ValueError("Commit final admission/protocol metadata before preparing model inventory")
    common_source = Path(common["source_root"])
    for name, sha in common["source_files"].items():
        if sha_file(common_source / name) != sha:
            raise ValueError("Pre-material common source changed: " + name)
    # The common snapshot, not a main checkout edited after reading held-out data.
    root.mkdir(parents=True)
    shutil.copytree(common_source, root / "source")
    evidence = []
    for index, path in enumerate([admission_path, *paths.values()]):
        target = root / "evidence" / f"{index:02d}-{path.name}"
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(path, target)
        evidence.append({"original": ref(path), "frozen_copy": ref(target)})
    states = copy.deepcopy(metadata["states"])
    for authorization in states.values():
        checked(authorization["checkpoint"])
    _, adaptation = supervisor_binding()
    model = project / "runs/assets/models/Qwen3.5-9B-c20223623576"
    plan = sealed({"version": VERSION, "created_at": time.time(), "purpose": PURPOSE,
        "project_root": str(project), "source_root": str(root / "source"), "source_files": common["source_files"],
        "source_commit": common["source_commit"], "prepare_metadata_commit": identity,
        "model_admission": ref(admission_path), "admission_references": references, "evidence": evidence,
        "rows": rows, "states": states, "qualified_case_ids": qualified, "blocked_cases": blocked,
        "qualification_states": initial_states(rows, qualified), "repository_source_root": str(source_root.resolve()),
        "adapter_manifest": manifest_reference, "model_path": str(model),
        "model_manifest": ref(model / "proworksim-manifest.json"), "contract": CONTRACT, "limits": LIMITS,
        "native_python": str(project / "runs/v016-sdk/resident-venv/bin/python"),
        "runtime_dependency_path": str(project / "runs/v030-runtime-deps"),
        "resource_modules": [ref(project / "artifacts/software-learning-v050/resume-r6-source/scripts" / (name + ".py"))
            for name in ("software_learning_resources_v050r3", "software_learning_resources_v050r5")],
        "gpu_preference": GPU_PREFERENCE, "idle_only_admission": False, "fresh_resident_per_slot": True,
        "worker_module": MODULE, "supervisor_adaptation": adaptation,
        "maximum_slots": 32, "maximum_actual_tokens": 16000000, "maximum_decisions": 4096,
        "maximum_attempts": 4096, "maximum_public_project_tests": 1024,
        "dispatch_eligible_slots": 4 * len(qualified), "dispatch_token_bound": 2000000 * len(qualified),
        "blocked_budget_transferred": False, "old_costs_transferred": False,
        "maximum_parameter_updates": 0, "maximum_backward_calls": 0, "new_qualification_calls": 0,
        "model_retries": False, "pre_model_resource_only_retries": True, "automatic_successors": False})
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    plan = unseal(read_json(Path(root) / "plan.json"))
    if (plan.get("version") != VERSION or plan.get("purpose") != PURPOSE or plan.get("contract") != CONTRACT
            or plan.get("limits") != LIMITS or plan.get("gpu_preference") != GPU_PREFERENCE
            or plan.get("fresh_resident_per_slot") is not True or plan.get("worker_module") != MODULE):
        raise ValueError("HOLD frozen scientific or resource contract changed")
    for name, sha in plan["source_files"].items():
        if sha_file(Path(plan["source_root"]) / name) != sha:
            raise ValueError("HOLD common source changed: " + name)
    refs = plan["admission_references"]
    for value in [plan["model_admission"], *refs.values(), plan["adapter_manifest"], plan["model_manifest"],
                  *[value["frozen_copy"] for value in plan["evidence"]]]:
        checked(value)
    metadata = read_json(Path(refs["inventory"]["path"]))
    if inventory(metadata) != plan["rows"] or metadata["states"] != plan["states"]:
        raise ValueError("Original32 inventory or condition-to-checkpoint mapping changed")
    common = read_json(Path(refs["common_implementation_freeze"]["path"]))
    qualified, blocked = gate_records(read_json(Path(plan["model_admission"]["path"])),
        source=read_json(Path(refs["source_qualification"]["path"])), inputs=read_json(Path(refs["initial_inputs"]["path"])),
        common=common, references=refs)
    if (qualified != plan["qualified_case_ids"] or blocked != plan["blocked_cases"]
            or common["source_files"] != plan["source_files"]
            or plan["qualification_states"] != initial_states(plan["rows"], qualified)):
        raise ValueError("Qualified subset or pre-material common source changed")
    return plan


def classify_closed(row, *, result, accounting, guard, episode_guard, measurement):
    reasons = []
    if (accounting.get("all_started_settled") is not True or accounting.get("integrity_errors")
            or accounting.get("known_actual_tokens", 0) > row["generation_tokens"]):
        reasons.append("native_generation_or_accounting_unresolved")
    if guard.get("passed") is not True or not all(episode_guard.get(k) is True
            for k in ("learning_unchanged", "rng_restored_exactly")):
        reasons.append("terminal_actor_or_rng_guard_unresolved")
    if (type(result.get("F")) is not int or result["F"] not in (0, 1)
            or result.get("F") != result.get("R_joint") or result.get("status") != "closed"
            or result.get("heldout_condition") != row["condition"]):
        reasons.append("fixed_submission_F_unknown_or_wrong_state")
    if (measurement.get("decision") != "continue"
            or measurement.get("fixed_endpoint_binding", {}).get("status") != "verified"
            or measurement.get("native_accounting", {}).get("formal_model_admission_eligible") is not True):
        reasons.append("mechanical_measurement_not_formal_continue")
    if (result.get("mutable_terminal_working_tree_assessed") is not False
            or any(key in result for key in ("R_code", "terminal_code", "Q_task_terminal"))):
        reasons.append("unapproved_mutable_terminal_tree_endpoint")
    return {"decision": "global_pause" if reasons else "continue", "reasons": reasons,
        "F_used_for_selection": False, "no_submit_F0_must_still_pass_mechanics": True}


def worker(root, slot_id, attempt):
    root, output = Path(root).resolve(), Path(attempt).resolve()
    plan = frozen(root)
    rows = [row for row in plan["rows"] if row["slot_id"] == slot_id]
    if len(rows) != 1 or rows[0]["task_id"] not in plan["qualified_case_ids"] or output.exists():
        raise ValueError("Only a fresh independently qualified original HOLD slot may start")
    if Path(sys.executable).resolve() != Path(plan["native_python"]).resolve():
        raise ValueError("Use the frozen native interpreter")
    row = rows[0]
    directory = root / "slots" / slot_id
    if directory.exists():
        raise FileExistsError("An entered HOLD model slot is never replayed")
    output.mkdir(parents=True)
    res, startup = base.resource_modules(plan)
    binding = res.binding_from_env()
    if binding["gpu_index"] not in plan["gpu_preference"]:
        raise ValueError("GPU outside the declared current scope")
    base.phase(output, "reservation")
    try:
        startup.acquire_startup_cache(output / "startup", binding,
            identity={"plan": ref(root / "plan.json"), "slot_id": slot_id})
    except startup.StartupResourceUnavailable:
        write(output / "report.json", {"status": "pre_model_resource_unavailable", "model_loader_entered": False,
            "generation_calls": 0, "slot_id": slot_id, "source_plan": ref(root / "plan.json")})
        return 75
    directory.mkdir(parents=True, exist_ok=False)
    write(directory / "started.json", {"row": row, "attempt": str(output), "pid": os.getpid(), "at": time.time(),
        "source_plan": ref(root / "plan.json"), "scope": "Entered before load; no post-loader retry"})
    base.phase(output, "loading")
    try:
        from proworksim.software_calibration_runtime_v051 import load_actor
        from proworksim.repository_sources_holdout_v051 import RepositorySources
        from proworksim.software_holdout_repo_tests_v051 import run_repository_tests
        from proworksim.software_holdout_world_v051 import build_software_collaboration_case, case_spec
        from proworksim.software_holdout_collector_v051 import collect_episode
        from proworksim.software_holdout_measurement_v051 import measure_slot
        authorization = plan["states"][row["condition"]]
        owner = load_actor(plan["model_path"], manifest=plan["model_manifest"]["path"], contract=CONTRACT,
            path="project", output=output / "resident", checkpoint=authorization["checkpoint"]["path"],
            checkpoint_authorization=authorization)
        base.phase(output, "preparation")
        episode_started = None
        def runner(**kwargs):
            base.phase(output, "scoring", episode_started_at=episode_started)
            try:
                return run_repository_tests(**kwargs)
            finally:
                base.phase(output, "episode", episode_started_at=episode_started)
        provider = RepositorySources(plan["repository_source_root"], runner=runner,
            expected_manifest_sha256=plan["adapter_manifest"]["sha256"])
        case = case_spec(row["task_id"], provider=provider, first_member=row["first_member"])
        prepared = build_software_collaboration_case(case, output / "prepared", provider=provider)
        original_generate = owner.generate_native
        def generation(record):
            base.phase(output, "generation", episode_started_at=episode_started)
            try:
                with res.native_cache_context(owner, output / "native-cache", binding):
                    return original_generate(record)
            finally:
                base.phase(output, "episode", episode_started_at=episode_started)
        owner.generate_native = generation
        episode_started = time.time()
        base.phase(output, "episode", episode_started_at=episode_started)
        result = collect_episode(owner, prepared, output / "episode", sampling_seed=row["seed"], slot_id=slot_id,
            heldout_condition=row["condition"], checkpoint_authorization=authorization)
        closed = time.time()
        if closed - episode_started >= LIMITS["episode_seconds"]:
            raise TimeoutError("HOLD episode including its unique final fixed assessment exceeded hard bound")
        base.phase(output, "measurement", episode_started_at=episode_started, episode_closed_at=closed)
        accounting = base.native_accounting(output / "resident")
        measurement = measure_slot(result, output / "measurement.json", provider=provider,
            state_authorizations=plan["states"], allow_cpu_fixture=False)
        state_binding(result, plan["states"])
        episode_guard = read_json(output / "episode/evaluation-guard.json")
        guard = owner.verify_evaluation_guard()
        verdict = classify_closed(row, result=result, accounting=accounting, guard=guard,
            episode_guard=episode_guard, measurement=measurement)
        report = {"version": VERSION, "status": "closed" if verdict["decision"] == "continue" else "paused",
            "row": row, "source_plan": ref(root / "plan.json"), "result": result,
            "accounting": accounting, "measurement": measurement, "guard": guard,
            "episode_guard": episode_guard, "verdict": verdict,
            "episode_started_at": episode_started, "episode_closed_at": closed,
            "new_backward_calls": 0, "new_parameter_updates": 0}
        write(output / "report.json", report)
        write(directory / "closed.json", {"report": ref(output / "report.json"), "decision": verdict["decision"]})
        return 0
    except BaseException as error:
        write(output / "interruption.json", {"version": VERSION, "row": row,
            "error": {"type": type(error).__name__, "message": str(error)}, "at": time.time(),
            "model_retry_allowed": False, "formal_F": None})
        raise


def ledger(root, rows):
    plan = read_json(Path(root) / "plan.json")
    totals = {"known_actual_tokens": 0, "uncertain_reservation_tokens": 0,
              "started_generations": 0, "complete_generations": 0}
    outcomes, errors = [], []
    for row in rows:
        folder = Path(root) / "slots" / row["slot_id"]
        started, closed = folder / "started.json", folder / "closed.json"
        blocked = row["task_id"] not in plan["qualified_case_ids"]
        if blocked and (started.exists() or closed.exists()):
            raise ValueError("A source/input-blocked task acquired execution artifacts")
        outcome = {"slot_id": row["slot_id"], "started": started.exists(), "closed": closed.exists(),
            "qualification_status": "source_or_input_blocked" if blocked else "qualified", "F": None, "Q_joint": None}
        if started.exists():
            account = base.native_accounting(Path(read_json(started)["attempt"]) / "resident")
            for key in totals:
                totals[key] += account[key]
            errors.extend(account["integrity_errors"])
        if closed.exists():
            report = read_json(checked(read_json(closed)["report"]))
            outcome.update(raw_F=report["result"].get("F"), decision=report["verdict"]["decision"])
            if report["verdict"]["decision"] == "continue":
                outcome.update(F=report["result"].get("F"), Q_joint=report["result"].get("Q_joint"))
        outcomes.append(outcome)
    return {**totals, "ledger_tokens": totals["known_actual_tokens"] + totals["uncertain_reservation_tokens"],
        "complete_actual_tokens": totals["known_actual_tokens"] if not totals["uncertain_reservation_tokens"] and not errors else None,
        "integrity_errors": errors, "outcomes": outcomes, "logical_inventory": 32,
        "blocked_slots": sum(r["qualification_status"] == "source_or_input_blocked" for r in outcomes),
        "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_calls": 0}


def supervisor_binding():
    """Reuse resource/process control only; new worker and F measurement are separate."""
    values = dict(base.__dict__)
    values.update(VERSION=VERSION, frozen=frozen, ledger=ledger, classify_closed=classify_closed,
                  LIMITS=LIMITS, initial_states=initial_states, inventory_state_closed=inventory_state_closed)
    old_completion = base.worker_completion
    values["worker_completion"] = FunctionType(old_completion.__code__, values, old_completion.__name__,
                                               old_completion.__defaults__, old_completion.__closure__)
    values["worker_completion"].__kwdefaults__ = old_completion.__kwdefaults__
    tree = ast.parse(inspect.getsource(base.supervise))
    changed = {"worker_module": 0, "initial_states": 0, "inventory_terminal": 0}
    class Bind(ast.NodeTransformer):
        def visit_Constant(self, node):
            if node.value == "scripts.software_calibration_v051_cal2":
                changed["worker_module"] += 1
                return ast.copy_location(ast.Constant(MODULE), node)
            return node
        def visit_Assign(self, node):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "states":
                changed["initial_states"] += 1
                node.value = ast.parse('initial_states(plan["rows"], plan["qualified_case_ids"])', mode="eval").body
                return node
            return self.generic_visit(node)
        def visit_Compare(self, node):
            if (isinstance(node.left, ast.Subscript) and isinstance(node.left.value, ast.Name)
                    and node.left.value.id == "s" and isinstance(node.left.slice, ast.Constant)
                    and node.left.slice.value == "status" and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq)
                    and len(node.comparators) == 1 and isinstance(node.comparators[0], ast.Constant)
                    and node.comparators[0].value == "complete"):
                changed["inventory_terminal"] += 1
                return ast.copy_location(ast.Call(func=ast.Name(id="inventory_state_closed", ctx=ast.Load()),
                                                   args=[ast.Name(id="s", ctx=ast.Load())], keywords=[]), node)
            return self.generic_visit(node)
    tree = Bind().visit(tree)
    if changed != {"worker_module": 1, "initial_states": 1, "inventory_terminal": 2}:
        raise ValueError("Generic supervisor source changed; refuse broader control rewriting")
    ast.fix_missing_locations(tree)
    exec(compile(tree, "<v051-HOLD-resource-supervisor>", "exec"), values)
    return values["supervise"], {"source": ref(Path(base.__file__)), "rebindings": changed,
        "model_world_measurement_algorithms_changed_by_AST": False,
        "old_module_globals_modified": False, "blocked_slots_are_not_completed_samples": True}


def supervise(root):
    plan = frozen(root)
    if (Path(root) / "supervisor.json").exists():
        raise FileExistsError("A started HOLD inventory cannot be replayed")
    if not plan["qualified_case_ids"]:
        stamp = time.time()
        result = {"version": VERSION, "status": "complete", "started_at": stamp, "ended_at": stamp,
            "observer_pid": os.getpid(), "plan": ref(Path(root) / "plan.json"),
            "states": initial_states(plan["rows"], []), "ledger": ledger(root, plan["rows"]),
            "gpu_worker_seconds": 0, "all_tasks_source_or_input_blocked": True,
            "resource_queries": 0, "formal_sample_completeness": False}
        write(Path(root) / "supervisor.json", result)
        return result
    function, _ = supervisor_binding()
    return function(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "supervise", "worker"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--admission", type=Path)
    parser.add_argument("--slot")
    parser.add_argument("--attempt", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        if args.project_root is None:
            parser.error("prepare requires explicit --project-root; never infer it from a frozen snapshot")
        prepare(args.root, project_root=args.project_root, admission_path=args.admission)
    elif args.command == "supervise":
        supervise(args.root)
    else:
        raise SystemExit(worker(args.root, args.slot, args.attempt))


if __name__ == "__main__":
    main()
