"""Independent twelve-slot raw OpenHands/managed-S1 bridge; no training."""
from __future__ import annotations

import argparse
import ast
import copy
from functools import cache
import inspect
import os
from pathlib import Path
import shutil
import sys
import time
from types import FunctionType

from proworksim.online_training import sha_file
from proworksim.storage import digest, read_json
from scripts import software_calibration_v051_cal2 as original_host
from scripts.software_calibration_v051 import checked, ref, resource_modules, sealed, unseal, write

VERSION = "software-openhands-bridge-host-v0.52"
MODULE = "scripts.software_bridge_v052"
PURPOSE = "native_openhands_managed_s1_bridge"
CONTRACT = copy.deepcopy(original_host.CONTRACT)
LIMITS = copy.deepcopy(original_host.LIMITS)
GPU_PREFERENCE = list(range(8))
TASKS = tuple(f"cal2-{repository}-{index}" for repository in ("boltons", "parse", "xmltodict") for index in (1, 2))
CHECKS = {"all16_old_HOLD_readonly_process_audit_closed", "same_final_test_environment_bound",
    "all6_original_source_tasks_qualified", "all12_actual_initial_inputs_bound",
    "official_Agent_Conversation_tools_bound", "native_interface_controls",
    "sole_pre_scoring_candidate_controls", "managed_assessment_controls", "host_controls",
    "raw_same_provider_assets_and_resource_policy_bound"}
phase = original_host.phase
native_accounting = original_host.native_accounting


def inventory(design):
    rows = copy.deepcopy(design.get("rows", []))
    if len(rows) != 12 or len({row["slot_id"] for row in rows}) != 12:
        raise ValueError("Exactly the original six tasks paired under two conditions are required")
    for index, task in enumerate(TASKS):
        order = ["OH_ref", "PS1"] if index % 2 == 0 else ["PS1", "OH_ref"]
        for row, condition in zip(rows[index * 2:index * 2 + 2], order, strict=True):
            if (row.get("task_id") != task or row.get("condition") != condition
                    or row.get("slot_id") != f"v052-{task}-{condition}"
                    or row.get("seed") != 202610180521 + index
                    or row.get("condition_order_for_task") != order
                    or row.get("first_member") != "member_001"
                    or row.get("generation_tokens") != 500000
                    or row.get("decisions") != 128 or row.get("attempts") != 128
                    or row.get("project_public_tests") != (32 if condition == "PS1" else None)):
                raise ValueError("Frozen v052 task/seed/order/budget changed")
    if design.get("contract") != CONTRACT or design.get("purpose") != PURPOSE:
        raise ValueError("The shared numerical contract or bridge purpose changed")
    return rows


def gate_records(admission, design, source, inputs):
    if (admission.get("version") != "v052-openhands-bridge-model-admission-v1"
            or admission.get("released") is not True or admission.get("purpose") != PURPOSE
            or admission.get("unresolved_blockers") != []
            or set(admission.get("checks", {})) != CHECKS
            or any(value is not True for value in admission["checks"].values())):
        raise ValueError("Separate source/input/control model admission is required")
    if (source.get("completed") is not True or source.get("passed") is not True
            or source.get("qualified_case_ids") != list(TASKS)
            or source.get("fixture_only") is not False
            or inputs.get("completed") is not True or inputs.get("passed") is not True
            or inputs.get("fixture_only") is not False
            or inputs.get("actual_initial_SDK_requests") != 12 or inputs.get("new_model_calls") != 0
            or inputs.get("design") != admission["design"]
            or source.get("runtime_manifest") != admission["test_runtime"]
            or any(inputs.get(key) != admission[key] for key in
                   ("source_qualification", "test_runtime", "reference_runtime"))):
        raise ValueError("All six source tasks and twelve actual initial requests must qualify")
    resources = admission.get("resources", {})
    if (resources.get("allowed_gpu_indices") != GPU_PREFERENCE
            or resources.get("max_residents") != 4 or resources.get("idle_only_admission") is not False):
        raise ValueError("Preserve the authorized all-GPU capacity gate and maximum four residents")
    return inventory(design)


def prepare(root, *, project_root, admission_path=None):
    from proworksim.audit import code_identity

    project, root = Path(project_root).resolve(), Path(root).resolve()
    if root.exists():
        raise FileExistsError("A new bridge inventory needs a fresh run root")
    admission_path = Path(admission_path or project / "docs/experiments/software-bridge-v052-model-admission.json").resolve()
    admission = read_json(admission_path)
    keys = ("design", "source_qualification", "initial_inputs", "test_runtime", "reference_runtime",
            "hold_process_audit", "resource_policy", "controls")
    references = {key: copy.deepcopy(admission[key]) for key in keys}
    paths = {key: checked(reference) for key, reference in references.items()}
    source = read_json(paths["source_qualification"])
    rows = gate_records(admission, read_json(paths["design"]), source, read_json(paths["initial_inputs"]))
    identity = code_identity()
    if identity.get("code_dirty") is not False:
        raise ValueError("Commit implementation, controls and admission before model preparation")
    root.mkdir(parents=True)
    snapshot, source_files = root / "source", {}
    for name in ("src", "scripts"):
        for path in sorted((project / name).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            relative = path.relative_to(project)
            target = snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            source_files[str(relative)] = sha_file(target)
    evidence = []
    for index, path in enumerate((admission_path, *paths.values())):
        destination = root / "evidence" / f"{index:02d}-{path.name}"
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(path, destination)
        evidence.append({"original": ref(path), "frozen_copy": ref(destination)})
    source_root = Path(source["source_root"])
    source_root = source_root if source_root.is_absolute() else project / source_root
    manifest_path = Path(source["adapter_manifest"]["path"])
    manifest_path = manifest_path if manifest_path.is_absolute() else project / manifest_path
    if any(ref(manifest_path)[key] != source["adapter_manifest"][key] for key in ("sha256", "bytes")):
        raise ValueError("Qualified source manifest changed")
    resource_source = project / "artifacts/software-learning-v050/resume-r6-source/scripts"
    _, adaptation = supervisor_binding()
    model = project / "runs/assets/models/Qwen3.5-9B-c20223623576"
    plan = sealed({"version": VERSION, "purpose": PURPOSE, "created_at": time.time(),
        "project_root": str(project), "source_commit": identity, "source_root": str(snapshot),
        "source_files": source_files, "model_admission": ref(admission_path),
        "admission_references": references, "evidence": evidence, "rows": rows,
        "repository_source_root": str(source_root.resolve()), "adapter_manifest": ref(manifest_path),
        "test_runtime": references["test_runtime"], "reference_runtime": references["reference_runtime"],
        "model_path": str(model), "model_manifest": ref(model / "proworksim-manifest.json"),
        "native_python": str(project / "runs/v016-sdk/resident-venv/bin/python"),
        "runtime_dependency_path": str(project / "runs/v030-runtime-deps"),
        "resource_modules": [ref(resource_source / (name + ".py")) for name in
            ("software_learning_resources_v050r3", "software_learning_resources_v050r5")],
        "contract": CONTRACT, "limits": LIMITS, "gpu_preference": GPU_PREFERENCE,
        "idle_only_admission": False, "fresh_resident_per_slot": True, "worker_module": MODULE,
        "supervisor_adaptation": adaptation, "maximum_slots": 12, "maximum_actual_tokens": 6000000,
        "maximum_decisions": 1536, "maximum_attempts": 1536, "maximum_public_project_tests": 192,
        "maximum_parameter_updates": 0, "maximum_backward_calls": 0, "new_qualification_calls": 0,
        "model_retries": False, "pre_model_resource_only_retries": True,
        "old_costs_transferred": False, "old_budget_transferred": False, "automatic_successors": False})
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    root = Path(root)
    plan = unseal(read_json(root / "plan.json"))
    if (plan.get("version") != VERSION or plan.get("purpose") != PURPOSE
            or plan.get("contract") != CONTRACT or plan.get("limits") != LIMITS
            or plan.get("gpu_preference") != GPU_PREFERENCE or plan.get("idle_only_admission") is not False
            or plan.get("fresh_resident_per_slot") is not True or plan.get("worker_module") != MODULE):
        raise ValueError("Frozen bridge execution or resource identity changed")
    for name, sha in plan["source_files"].items():
        if sha_file(Path(plan["source_root"]) / name) != sha:
            raise ValueError("Bridge source snapshot changed: " + name)
    for reference in (plan["model_admission"], *plan["admission_references"].values(), plan["adapter_manifest"],
                      plan["model_manifest"], *plan["resource_modules"], *[item["frozen_copy"] for item in plan["evidence"]]):
        checked(reference)
    references = plan["admission_references"]
    rows = gate_records(read_json(checked(plan["model_admission"])), read_json(checked(references["design"])),
        read_json(checked(references["source_qualification"])), read_json(checked(references["initial_inputs"])))
    if rows != plan["rows"]:
        raise ValueError("Frozen twelve-slot panel changed")
    return plan


def classify_closed(row, *, result, accounting, guard, episode_guard, measurement):
    reasons = []
    if (accounting.get("all_started_settled") is not True or accounting.get("integrity_errors")
            or accounting.get("known_actual_tokens", 0) > row["generation_tokens"]):
        reasons.append("native_generation_or_accounting_unresolved")
    if guard.get("passed") is not True or not all(episode_guard.get(key) is True for key in
            ("learning_unchanged", "rng_restored_exactly", "software_binding_unchanged", "actor_identity_unchanged")):
        reasons.append("per_episode_raw_actor_or_rng_guard_unresolved")
    if type(result.get("R_code")) is not int or result["R_code"] not in (0, 1):
        reasons.append("sole_terminal_code_outcome_unknown")
    if row["condition"] == "PS1":
        if (result.get("calibration_condition") != "P" or result.get("slot_id") != row["slot_id"]
                or type(result.get("R_joint")) is not int or result["R_joint"] not in (0, 1)):
            reasons.append("managed_P_mapping_or_fixed_delivery_unknown")
    elif row["condition"] == "OH_ref":
        if result.get("R_joint") is not None or result.get("project_delivery_endpoint") != "not_applicable":
            reasons.append("native_reference_acquired_project_delivery_endpoint")
    else:
        reasons.append("undeclared_condition")
    if measurement.get("decision") != "continue":
        reasons.append("episode_mechanical_measurement_not_continue")
    if any(result.get(key, 0) != 0 for key in ("actor_updates", "critic_updates", "new_backward_calls")):
        reasons.append("unexpected_learning_update")
    return {"decision": "global_pause" if reasons else "continue", "reasons": reasons,
        "selected_by_reward": False, "code_zero_is_not_a_pause_reason": True}


def worker(root, slot_id, attempt):
    root, output = Path(root).resolve(), Path(attempt).resolve()
    plan = frozen(root)
    matches = [row for row in plan["rows"] if row["slot_id"] == slot_id]
    if len(matches) != 1 or output.exists():
        raise ValueError("One new frozen bridge slot and fresh attempt directory are required")
    if Path(sys.executable).resolve() != Path(plan["native_python"]).resolve():
        raise ValueError("Use the frozen native interpreter")
    row = matches[0]
    directory = root / "slots" / slot_id
    if directory.exists():
        raise FileExistsError("An entered v052 slot is never replayed")
    output.mkdir(parents=True)
    res, startup = resource_modules(plan)
    binding = res.binding_from_env()
    if binding["gpu_index"] not in plan["gpu_preference"]:
        raise ValueError("GPU outside current authorization")
    phase(output, "reservation")
    try:
        startup.acquire_startup_cache(output / "startup", binding,
            identity={"plan": ref(root / "plan.json"), "slot_id": slot_id})
    except startup.StartupResourceUnavailable:
        write(output / "report.json", {"status": "pre_model_resource_unavailable",
            "model_loader_entered": False, "generation_calls": 0, "slot_id": slot_id,
            "source_plan": ref(root / "plan.json")})
        return 75
    directory.mkdir(parents=True)
    write(directory / "started.json", {"row": row, "attempt": str(output), "pid": os.getpid(),
        "at": time.time(), "source_plan": ref(root / "plan.json"),
        "scope": "Entered before model load; no loader/model replay after entry"})
    phase(output, "loading")
    try:
        from proworksim.software_bridge_sources_v052 import RepositorySources, run_repository_tests
        from proworksim.software_calibration_runtime_v051 import load_actor

        owner = load_actor(plan["model_path"], manifest=plan["model_manifest"]["path"],
            contract=CONTRACT, path="project", output=output / "resident", checkpoint=None)
        phase(output, "preparation")
        episode_started = None

        def runner(**kwargs):
            phase(output, "scoring", episode_started_at=episode_started)
            try:
                return run_repository_tests(**kwargs)
            finally:
                phase(output, "episode", episode_started_at=episode_started)

        provider = RepositorySources(plan["repository_source_root"], runtime_manifest=plan["test_runtime"]["path"],
            expected_manifest_sha256=plan["adapter_manifest"]["sha256"], runner=runner)
        source = provider.build_case(row["task_id"])
        original_generate = owner.generate_native

        def generation(record):
            phase(output, "generation", episode_started_at=episode_started)
            try:
                with res.native_cache_context(owner, output / "native-cache", binding):
                    return original_generate(record)
            finally:
                phase(output, "episode", episode_started_at=episode_started)

        owner.generate_native = generation
        if row["condition"] == "OH_ref":
            from proworksim.software_bridge_openhands_v052 import collect_episode
            from proworksim.software_bridge_sources_v052 import grade_locked_candidate, lock_final_candidate
            from proworksim.software_calibration_v051_mini import prepare_buggy_worktree

            origin = prepare_buggy_worktree(source["files"], directory / "native-worktree",
                receipt_path=directory / "worktree-origin.json")
            task_source = {**source, "task_id": row["task_id"], "runner_spec": provider.runner_spec(row["task_id"]),
                "workspace_origin": origin, "reference_runtime": plan["reference_runtime"]}
            episode_started = time.time()
            phase(output, "episode", episode_started_at=episode_started)
            result = collect_episode(owner=owner, task_source=task_source, provider=provider, slot_id=slot_id,
                sampling_seed=row["seed"], worktree=directory / "native-worktree", episode_folder=output / "episode")
            candidate_ref = result["candidate_files"]
            candidate = read_json(checked(candidate_ref))
            lock = lock_final_candidate(provider=provider, task_id=row["task_id"], candidate_files=candidate,
                run_root=output / "terminal-code")
            grade = grade_locked_candidate(provider=provider, lock_reference=lock)
            result.update(R_code=grade["R_code"], Q_task_terminal=grade["Q_task"], R_joint=None,
                project_delivery_endpoint="not_applicable", terminal_code=grade,
                host_final_evaluation_attempts=grade["new_evaluation_attempts"],
                host_final_test_executions=grade["new_test_executions"])
        else:
            from proworksim.software_bridge_managed_v052 import collect_episode
            from proworksim.software_calibration_world_v051 import build_software_collaboration_case

            prepared = build_software_collaboration_case(row["task_id"], output / "prepared", provider=provider)
            episode_started = time.time()
            phase(output, "episode", episode_started_at=episode_started)
            result = collect_episode(owner, prepared, output / "episode", sampling_seed=row["seed"], slot_id=slot_id)
        episode_closed = time.time()
        if episode_closed - episode_started >= LIMITS["episode_seconds"]:
            raise TimeoutError("Episode and unique closing assessment exceeded the hard bound")
        phase(output, "measurement", episode_started_at=episode_started, episode_closed_at=episode_closed)
        accounting = native_accounting(output / "resident")
        if row["condition"] == "OH_ref":
            from proworksim.software_bridge_openhands_v052 import measure_closed
            measurement = measure_closed(result, row=row, owner_identity=owner.freeze_identity(), accounting=accounting)
            write(output / "measurement.json", measurement)
        else:
            from proworksim.software_calibration_measurement_v051 import measure_slot
            measurement = measure_slot(result, output / "measurement.json", provider=provider)
            if result.get("usage", {}).get("total_tokens") != accounting["known_actual_tokens"]:
                measurement = {**measurement, "decision": "global_pause", "native_usage_mismatch": True}
                write(output / "native-usage-mismatch.json", measurement)
        guard = owner.verify_evaluation_guard()
        episode_guard = read_json(output / "episode/evaluation-guard.json")
        verdict = classify_closed(row, result=result, accounting=accounting, guard=guard,
            episode_guard=episode_guard, measurement=measurement)
        report = {"version": VERSION, "status": "closed" if verdict["decision"] == "continue" else "paused",
            "row": row, "source_plan": ref(root / "plan.json"), "result": result,
            "accounting": accounting, "measurement": measurement, "guard": guard,
            "episode_guard": episode_guard, "verdict": verdict,
            "episode_started_at": episode_started, "episode_closed_at": episode_closed,
            "new_backward_calls": 0, "new_parameter_updates": 0}
        write(output / "report.json", report)
        write(directory / "closed.json", {"report": ref(output / "report.json"), "decision": verdict["decision"]})
        return 0
    except BaseException as error:
        write(output / "interruption.json", {"version": VERSION, "row": row,
            "error": {"type": type(error).__name__, "message": str(error)}, "at": time.time(),
            "model_retry_allowed": False, "formal_outcome": None})
        raise


def ledger(root, rows):
    totals = {"known_actual_tokens": 0, "uncertain_reservation_tokens": 0,
        "started_generations": 0, "complete_generations": 0}
    outcomes, errors = [], []
    for row in rows:
        folder = Path(root) / "slots" / row["slot_id"]
        started, closed = folder / "started.json", folder / "closed.json"
        outcome = {"slot_id": row["slot_id"], "condition": row["condition"], "started": started.exists(),
            "closed": closed.exists(), "R_code": None, "Q_task_terminal": None, "R_joint": None}
        if started.exists():
            usage = native_accounting(Path(read_json(started)["attempt"]) / "resident")
            for key in totals:
                totals[key] += usage[key]
            errors.extend(usage["integrity_errors"])
        if closed.exists():
            report = read_json(checked(read_json(closed)["report"]))
            outcome["decision"] = report["verdict"]["decision"]
            outcome["raw_outcomes"] = {key: report["result"].get(key) for key in ("R_code", "Q_task_terminal", "R_joint")}
            if report.get("status") == "closed" and outcome["decision"] == "continue":
                outcome.update(outcome["raw_outcomes"])
        outcomes.append(outcome)
    return {**totals, "ledger_tokens": totals["known_actual_tokens"] + totals["uncertain_reservation_tokens"],
        "complete_actual_tokens": totals["known_actual_tokens"] if not totals["uncertain_reservation_tokens"] and not errors else None,
        "integrity_errors": errors, "outcomes": outcomes, "logical_inventory": 12,
        "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_calls": 0}


@cache
def supervisor_binding():
    """Reuse the closed resource/process host; change only its worker module."""
    namespace = dict(original_host.__dict__)
    namespace.update(VERSION=VERSION, LIMITS=LIMITS, frozen=frozen, ledger=ledger, classify_closed=classify_closed)
    function = original_host.worker_completion
    completion = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    completion.__kwdefaults__ = function.__kwdefaults__
    namespace["worker_completion"] = completion
    source = inspect.getsource(original_host.supervise)
    tree = ast.parse(source)
    changes = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == "scripts.software_calibration_v051_cal2":
            node.value = MODULE
            changes += 1
    if changes != 1:
        raise ValueError("Original supervisor worker-module site changed")
    ast.fix_missing_locations(tree)
    exec(compile(tree, "<v052-resource-host-worker-module-only>", "exec"), namespace)
    return namespace["supervise"], {"version": VERSION, "original_source_sha256": digest(source.encode()),
        "changed_worker_module_literals": changes,
        "adapted_AST_sha256": digest(ast.dump(tree, include_attributes=False).encode()),
        "worker_completion_code_unchanged": completion.__code__ is function.__code__,
        "resource_process_deadline_algorithms_changed": False, "old_globals_changed": False}


def supervise(root):
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
            parser.error("prepare requires --project-root")
        prepare(args.root, project_root=args.project_root, admission_path=args.admission)
    elif args.command == "supervise":
        supervise(args.root)
    else:
        raise SystemExit(worker(args.root, args.slot, args.attempt))


if __name__ == "__main__":
    main()
