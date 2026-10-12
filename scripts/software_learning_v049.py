"""One bounded strict-O1 Gamma1 E1-to-E2 learning window, no automatic successor."""
from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import signal
import time

from proworksim.audit import code_identity
from proworksim.storage import digest, json_bytes, read_json
from scripts import software_organization_v048 as inherited
from scripts.run_ne_v021 import read, reference, write
from scripts.software_development_v028 import task

VERSION = "software-learning-window-v0.49"
SOURCE = Path(__file__).resolve().parents[1]
DESIGN = SOURCE / "docs/experiments/software-learning-v049-design.json"
CONTROLS = SOURCE / "docs/experiments/software-learning-v049-cpu-controls.json"
GPU_ORDER = (3, 4, 5, 7)
WORKERS = ("s0", "collect-LA", "collect-LB", "update-B", "update-Q_plus", "update-Q_minus",
           "dev-B", "dev-Q_plus", "dev-Q_minus")
LIMITS = {**copy.deepcopy(inherited.LIMITS), "max_new_episodes": 20,
    "max_new_actor_steps": 3, "max_new_critic_steps": 3, "max_new_backward_calls": None,
    "task_seconds": {"loading": 900, "episode": 6000, "boundary": 600, "training_step": 900}}
checked = inherited.checked


def source_files():
    files = inherited.source_files()
    paths = [p for p in (SOURCE / "examples/software-organization-v049").rglob("*")
             if p.is_file() and "__pycache__" not in p.parts]
    paths += [DESIGN, CONTROLS, SOURCE / "docs/experiments/software-learning-v049-protocol.md",
              SOURCE / "docs/reference/audit-v048-next-v049-learning.md"]
    files.update({str(p.relative_to(SOURCE)): digest(p.read_bytes()) for p in sorted(paths)})
    return files


def frozen(root):
    plan = read_json(Path(root) / "plan.json")
    if (plan.get("version") != VERSION or plan.get("plan_sha256") != digest(json_bytes(
            {k: v for k, v in plan.items() if k != "plan_sha256"}))
            or plan["source"] != code_identity() or plan["source_files"] != source_files()
            or plan["design"] != reference(DESIGN) or plan["limits"] != LIMITS
            or plan["workers"] != list(WORKERS) or plan["gpu_preference"] != list(GPU_ORDER)):
        raise ValueError("Frozen v049 implementation, inventory or resource identity changed")
    return plan


def prepare(root, *, parent_plan=SOURCE / "runs/software-organization-v048/plan.json"):
    from proworksim.software_mapper_v049 import mapping_spec
    from proworksim.software_organization_tasks_v049 import source_manifest, source_partition

    root = Path(root).resolve()
    if root.exists():
        raise FileExistsError("New bounded inventory cannot overwrite or retry another run")
    source = code_identity()
    if source["code_dirty"] is not False:
        raise ValueError("Commit complete implementation and protocol before any resident/model work")
    parent = read_json(parent_plan)
    if parent["plan_sha256"] != digest(json_bytes({k: v for k, v in parent.items() if k != "plan_sha256"})):
        raise ValueError("Historical frozen plan seal changed")
    design = read_json(DESIGN)
    controls = read_json(CONTROLS)
    if (controls.get("sha256") != digest(json_bytes({k: v for k, v in controls.items() if k != "sha256"}))
            or controls.get("passed") is not True or controls.get("design_sha256") != reference(DESIGN)["sha256"]
            or controls.get("new_9b_model_calls") != 0 or controls.get("new_gpu_workers") != 0):
        raise ValueError("The finite new CPU controls must close before any model worker")
    carry = ("data_root", "native_python", "native_python_prefix", "runtime_dependency_path",
        "common", "model_references", "original_plan", "original_expected_actor_identity",
        "expected_actor_identity", "expected_capacity_recipe_sha256", "expected_capacity_profile_sha256",
        "qualification_capacity_binding", "reused_model_qualification")
    plan = {**{key: copy.deepcopy(parent[key]) for key in carry}, "version": VERSION,
        "created_at": time.time(), "source": source, "source_files": source_files(),
        "source_root": str(SOURCE), "parent_plan": reference(parent_plan), "design": reference(DESIGN),
        "cpu_controls": reference(CONTROLS),
        "inventory": design, "workers": list(WORKERS), "limits": copy.deepcopy(LIMITS),
        "gpu_preference": list(GPU_ORDER), "mapper_specification": mapping_spec(),
        "task_source_manifest": source_manifest(), "source_partition": source_partition(),
        "training_reward": "formal_R_joint_under_shared_token_and_time_policy",
        "development_F": "equal_weight_four_formal_R_joint; token_only_counterfactual_keeps_null_if_censored",
        "prior_artifact_roots": inherited.support.dense._artifact_roots([
            *parent["prior_artifact_roots"], Path(parent_plan).parent, SOURCE / "artifacts/software-learning-v049"]),
        "new_qualification_calls": 0, "new_qualification_tokens": 0,
        "automatic_retries": False, "automatic_successors": [], "old_queues_remain_paused": True,
        "scope": "New8 O1 training collection; reliable B and at most one supported bidirectional true H1 intervention; four new development units per executed branch."}
    plan["plan_sha256"] = digest(json_bytes(plan))
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    return plan


def _load_owner(plan, output):
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.software_learning_v036 import migrate_software_owner, restore_common
    from proworksim.software_learning_v049 import migrate_o1_owner
    from scripts.software_organization_capacity_qualification_v046 import apply_capacity_binding

    task(output, "load-original-numerical-owner", "loading")
    sample = inherited.allowed_resources()
    write(output / "preload-resources.json", sample)
    gpu = int(os.environ["CUDA_VISIBLE_DEVICES"])
    if gpu not in [c["index"] for c in inherited.available_cards(plan, sample)]:
        raise RuntimeError("Assigned allowed GPU capacity changed before loading")
    refs = plan["model_references"]
    saved, old_plan = read_json(checked(refs["owner"])), read_json(checked(refs["plan"]))
    model_plan = read_json(checked(old_plan["prior_model_plan"]))
    owner = DeterministicCandidateActor.from_candidate(model_plan["model"], manifest=checked(model_plan["manifest"]),
        profile=model_plan["runtime_profile"], recipe=saved["recipe"], output=output / "resident")
    write(output / "original-coordinate-binding.json", migrate_software_owner(owner, expected_steps=None))
    task(output, "restore-common-and-bind-capacity-coordinates", "boundary")
    common = read_json(checked(plan["common"]))
    restored = restore_common(owner, checked(common["common"]).parent)
    if (restored["state_sha256"] != common["state_tensor_digest"]
            or restored["rng_sha256"] != common["training_rng_sha256"]
            or restored["actor_identity"] != plan["original_expected_actor_identity"]
            or (owner.actor_steps, owner.critic_steps) != (3, 3)):
        raise ValueError("Original complete common3/3 restore failed")
    write(output / "common-restore.json", restored)
    original_plan = read_json(checked(plan["original_plan"]))
    binding = apply_capacity_binding(owner, original_plan=original_plan, common_restore=restored)
    identity = inherited.capacity_admission.validate_capacity_binding(binding, original_plan)
    if (identity != plan["expected_actor_identity"]
            or binding["capacity_recipe_sha256"] != plan["expected_capacity_recipe_sha256"]
            or binding["capacity_profile_sha256"] != plan["expected_capacity_profile_sha256"]):
        raise ValueError("Original native capacity qualification identity changed")
    write(output / "capacity-binding.json", binding)
    migrate_o1_owner(owner, output / "o1-coordinate-binding.json")
    return owner


def _case(unit):
    from proworksim.software_organization_tasks_v049 import TASK_LABELS
    from proworksim.software_organization_v049 import case_spec
    return case_spec(next(key for key, label in TASK_LABELS.items() if label == unit["root"]),
                     first_member=unit["first_member"], purpose=unit["purpose"])


def _new_prepared(unit, folder):
    from proworksim.software_organization_v049 import build_software_collaboration_case
    return build_software_collaboration_case(_case(unit), folder)


def _init_s0(owner, plan, root, output):
    from proworksim.software_context_v048 import CANDIDATE_SHA256, VERSION as PRESENTATION
    from proworksim.software_learning_v049 import save_s0_checkpoint, VERSION as BRIDGE
    from proworksim.software_organization_runtime_v049 import VERSION as RUNTIME
    from proworksim.software_runtime_v033 import SDK_CONTEXT_SELECTION
    from proworksim.software_training_v049 import declare_window, policy_spec, situation_id, situation_fingerprint

    expected_recipe = {"actor_lr": 1e-5, "critic_lr": .001, "clip": .2, "gradient_clip": 1.0,
        "critic_coefficient": .5, "epochs": 1, "credit_assignment": "terminal_mc", "gamma": 1.0,
        "entropy_coefficient": 0.0, "kl_coefficient": 0.0, "max_length": 18432,
        "max_output_tokens": 2048, "post_update_max_decisions": 6, "diagnostic_max_groups": 0,
        "members": ["member_001", "member_002", "software_inactive"]}
    if (any(owner.recipe.get(key) != value for key, value in expected_recipe.items())
            or owner.recipe.get("lora") != {"r": 8, "alpha": 16, "dropout": 0.0,
                                            "target_modules": ["q_proj", "v_proj"]}):
        raise ValueError("The inherited complete-window H1 recipe differs from the precollection freeze")
    write(output / "recipe-binding.json", {"original_actual_recipe": copy.deepcopy(owner.recipe),
        "design_recipe_matches": True, "recipe_sha256": digest(json_bytes(owner.recipe)),
        "H": 1, "forward_backward_and_optimizer_counts_are_separate": True})
    s0 = save_s0_checkpoint(owner, output / "checkpoint")
    write(root / "s0.json", s0)
    slots, prepared_by_root = [], {}
    for unit in plan["inventory"]["training_slots"]:
        if unit["root"] not in prepared_by_root:
            prepared_by_root[unit["root"]] = _new_prepared(unit, output / ("declaration-case-" + unit["root"]))
        prepared = prepared_by_root[unit["root"]]
        slots.append({"slot_id": unit["slot_id"], "xi_id": situation_id(prepared.case),
            "xi_fingerprint": situation_fingerprint(prepared), "active_members": unit["members"],
            "policies": policy_spec(owner, prepared), "mapping_spec_id": plan["mapper_specification"]["spec_id"]})
    gamma = {"gamma_version": "software-information-v0.49", "source_usage": "policy_training",
        "collection_mode": "current_policy_collection", "optimizer_update_allowed": True,
        "harness": "openhands_v16", "runtime_version": RUNTIME, "presentation_version": PRESENTATION,
        "sdk_context_selection": SDK_CONTEXT_SELECTION, "mapper_specification": plan["mapper_specification"],
        "mapper_spec_sha256": digest(json_bytes(plan["mapper_specification"])),
        "design_sha256": plan["design"]["sha256"], "learning_bridge_version": BRIDGE,
        "training_reward": plan["training_reward"],
        "presentation_identity": {"candidate_sha256": CANDIDATE_SHA256, "presentation_version": PRESENTATION}, "s0": s0}
    declaration = declare_window(plan["inventory"]["learning"]["training_window_id"],
        actor_identity=owner.freeze_identity(), gamma_identity=gamma, slot_specs=slots, min_class_count=2)
    write(root / "declaration.json", declaration)
    write(root / "precollection-binding.json", {"version": VERSION, "created_at": time.time(),
        "declaration": reference(root / "declaration.json"), "s0": reference(root / "s0.json"),
        "source": plan["source"], "all_training_and_development_inventory_frozen": True,
        "new_model_calls": 0, "new_parameter_updates": 0})
    return {"s0": s0, "declaration": reference(root / "declaration.json")}


def _restored_state(owner, root, branch, output):
    folder = root / ("s0" if branch == "S0" else "update-" + branch) / "actual/checkpoint"
    restored = owner.restore_checkpoint(folder)
    write(output / "loaded-state.json", {"branch": branch, "checkpoint": reference(folder / "checkpoint.json"),
        "restored": restored, "actor_identity": owner.freeze_identity(),
        "actor_steps": owner.actor_steps, "critic_steps": owner.critic_steps})
    return restored


def _collect(owner, plan, root, worker, output, *, development=False):
    from proworksim.software_organization_runtime_v049 import collect_episode
    from proworksim.software_organization_measurement_v049 import measure_slot
    from proworksim.software_training_v049 import export_software_episode

    branch = worker.removeprefix("dev-") if development else "S0"
    restored = _restored_state(owner, root, branch, output)
    declaration = read_json(root / "declaration.json")
    units = plan["inventory"]["development_units_shared_by_branches"] if development else [
        row for row in plan["inventory"]["training_slots"] if row["root"] == worker.removeprefix("collect-")]
    guard = owner.capture_evaluation_state()
    if not development:
        owner.begin_window(declaration["window_id"])
    rows, entries, terminal = [], [], "complete"
    for original in units:
        if list((root / "mechanism-stops").glob("*.json")):
            terminal = "paused_before_next_slot"
            break
        unit = copy.deepcopy(original)
        sid = unit.get("slot_id", unit.get("unit_id"))
        if development:
            sid += "-" + branch
        unit["slot_id"] = sid
        folder = output / "episodes" / sid
        task(output, sid + "-prepare", "boundary")
        prepared = _new_prepared(unit, folder / "prepared")
        learning_binding = {"branch": branch, "loaded_checkpoint_state_digest": restored["state_tensor_digest"],
            "declaration_sha256": digest(json_bytes(declaration)), "design_sha256": plan["design"]["sha256"]}
        task(output, sid, "episode")
        row = collect_episode(owner, prepared, folder, sampling_seed=unit["sampling_seed"], slot_id=sid,
            manage_owner_window=development, learning_binding=learning_binding)
        task(output, sid + "-evidence", "boundary")
        measurement = measure_slot(row, folder / "mechanical-measurement.json")
        rows.append({**unit, **row, "mechanical_measurement": reference(folder / "mechanical-measurement.json")})
        write(output / "progress.json", rows)
        if not development:
            entry, details = export_software_episode(prepared, folder / "episode", row["assessment"],
                declaration=declaration, slot_id=sid, captured=read_json(folder / "public-capture.json"), runtime_row=row)
            write(folder / "training-entry.json", entry)
            write(folder / "training-export.json", details)
            entries.append(entry)
        if measurement["decision"] != "continue":
            terminal = measurement["decision"]
            write(root / "mechanism-stops" / (sid + ".json"), {"kind": terminal,
                "worker": worker, "slot_id": sid, "measurement": reference(folder / "mechanical-measurement.json")})
            break
    if not development:
        owner.finish_evaluation(entries, output / "collection-boundary")
    frozen_guard = owner.finish_evaluation_guard(guard)
    write(output / "collection-guard.json", frozen_guard)
    if not frozen_guard["learning_unchanged"] or not frozen_guard["rng_restored_exactly"]:
        raise ValueError("Episode collection changed the loaded learning state")
    if entries:
        write(output / "entries.json", entries)
    return {"rows": rows, "status": terminal, "state_loaded_for_collection": restored,
            "collection_guard": reference(output / "collection-guard.json")}


def _update(owner, plan, root, worker, output):
    from proworksim.online_training import prepare_window
    from proworksim.software_learning_v049 import software_feature_function, update_software_window, bind_composition
    from proworksim.software_allocation_v049 import build_support_report, select_direction
    from scripts.software_allocation_v036 import training_progress

    branch = worker.removeprefix("update-")
    _restored_state(owner, root, "S0", output)
    declaration = read_json(root / "declaration.json")
    entries = []
    for group in ("LA", "LB"):
        entries.extend(read_json(root / ("collect-" + group) / "actual/entries.json"))
    if [row["slot_id"] for row in entries] != [row["slot_id"] for row in declaration["slots"]]:
        raise ValueError("All eight original slots in frozen order are required")
    owner.begin_window(declaration["window_id"])
    admission = prepare_window(entries, owner.freeze_identity(), declaration["window_id"], owner.recipe, software_feature_function)
    base = build_support_report(entries, declaration, admission=admission, design=plan["inventory"])
    write(output / "support-before-update.json", base)
    weights = {row["slot_id"]: dict.fromkeys(row["active_members"], 1.0) for row in entries}
    direction = None
    if branch != "B":
        direction = read_json(root / "direction.json")
        if direction.get("seal_sha256") != digest(json_bytes({key: value for key, value in direction.items() if key != "seal_sha256"})):
            raise ValueError("Predevelopment direction envelope seal changed")
        core = direction["direction"]
        if (core.get("seal_sha256") != digest(json_bytes({key: value for key, value in core.items() if key != "seal_sha256"}))
                or core.get("source_support_artifact_sha256") != reference(root / "support.json")["sha256"]
                or core.get("declaration_sha256") != digest(json_bytes(declaration))
                or core.get("design_sha256") != plan["design"]["sha256"]):
            raise ValueError("Original sealed support/direction source binding changed")
        if direction["selected"] is not True or direction["reliable_base_material"] is not True:
            raise ValueError("Q branches require the predevelopment actual supported direction")
        weights = direction["plus_weights" if branch == "Q_plus" else "minus_weights"]
        if not isinstance(core.get("selected"), dict) or weights != core["plus_weights_by_slot" if branch == "Q_plus" else "minus_weights_by_slot"]:
            raise ValueError("Q branch differs from its single sealed supported direction")
    binding = {"declaration_sha256": digest(json_bytes(declaration)), "design_sha256": plan["design"]["sha256"],
        "mapper_spec_sha256": declaration["gamma_identity"]["mapper_spec_sha256"],
        "support_artifact_sha256": reference(root / "support.json")["sha256"] if direction else digest(json_bytes(base)),
        "selected_direction_artifact_sha256": reference(root / "direction.json")["sha256"] if direction else None}
    composition = bind_composition(entries, declaration, weights, binding=binding)
    write(output / "composition-before-update.json", composition)
    task(output, "actual-input-admission", "boundary")
    with training_progress(owner, output):
        report = update_software_window(owner, entries, output / "update", declaration=declaration,
            request_evidence_root=root, composition=composition, observe_support_gradients=branch == "B")
    task(output, "save-updated-complete-state-and-support", "boundary")
    legitimate = {"updated", "zero_step_zero_actor_advantage_or_gradient", "zero_step_no_admitted_own_actions"}
    if report["status"] not in legitimate:
        raise ValueError("Original training admission or update did not complete: " + report["status"])
    if branch != "B":
        baseline = read_json(checked(direction["B_update"]))
        if (report.get("advantages") != baseline.get("advantages")
                or report.get("old_critic_values") != baseline.get("old_critic_values")
                or report.get("rewards") != baseline.get("rewards")
                or read_json(output / "update/admission.json") != admission):
            raise ValueError("Matched branch changed original admission, frozen advantages, critic or rewards")
    checkpoint = owner.save_checkpoint(output / "checkpoint")
    if branch == "B":
        support = build_support_report(entries, declaration, admission=admission, design=plan["inventory"], learner_report=report)
        write(root / "support.json", support)
        grad_path = output / "update/support-gradients.pt"
        if grad_path.exists():
            gradients = owner.torch.load(grad_path, map_location="cpu", weights_only=True)
            core = select_direction(support, gradients, gradient_receipt=read_json(output / "update/support-gradients.json"), torch=owner.torch)
        else:
            if admission["decisions"]:
                raise ValueError("Completed B with admitted material lacks its required original gradient observation")
            core = {"selected": None, "status": "no_admitted_base_material", "epsilon": None,
                "source_support_artifact_sha256": reference(root / "support.json")["sha256"],
                "declaration_sha256": digest(json_bytes(declaration)), "design_sha256": plan["design"]["sha256"],
                "plus_weights_by_slot": None, "minus_weights_by_slot": None, "baseline_weights_by_slot": weights,
                "development_results_read": False, "additional_samples": 0, "additional_backwards": 0}
            core["seal_sha256"] = digest(json_bytes(core))
        direction = {"version": VERSION, "selected": core["selected"] is not None,
            "reliable_base_material": bool(admission["decisions"]), "direction": core,
            "epsilon": core["epsilon"], "plus_weights": core["plus_weights_by_slot"],
            "minus_weights": core["minus_weights_by_slot"], "baseline_weights": core["baseline_weights_by_slot"],
            "B_update": reference(output / "update/report.json"), "support": reference(root / "support.json"),
            "frozen_before_any_development": True, "created_at": time.time()}
        direction["seal_sha256"] = digest(json_bytes(direction))
        write(root / "direction.json", direction)
    return {"branch": branch, "update_report": reference(output / "update/report.json"),
        "checkpoint": checkpoint, "new_actor_steps": report["actor_optimizer_steps"],
        "new_critic_steps": report["critic_optimizer_steps"], "new_backward_decisions": report["backward_decisions_completed"]}


def run_worker(root, worker, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    plan = frozen(root)
    inherited.validate_worker_interpreter(plan)
    if (worker not in WORKERS or output != root / worker / "actual"
            or os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, GPU_ORDER))):
        raise ValueError("Require original authorized worker/output and one allowed physical GPU")
    supervisor = read(root / "supervisor.json") or {}
    own = supervisor.get("states", {}).get(worker, {})
    # The supervisor writes immediately after spawn. Source/interpreter/resource
    # checks above are independent; readiness is fixed by the host dependency graph.
    if own.get("status") not in {"not_started", "running"}:
        raise ValueError("Worker is not a fresh supervisor-owned task")
    output.mkdir(parents=True, exist_ok=False)
    owner = None
    report = {"version": VERSION, "worker": worker, "status": "loading", "started_at": time.time(),
        "source_before": code_identity(), "success_boundary": False, "new_actor_steps": 0, "new_critic_steps": 0}
    write(output / "report.json", report)
    try:
        owner = _load_owner(plan, output)
        if worker == "s0":
            result = _init_s0(owner, plan, root, output)
        elif worker.startswith("collect-"):
            result = _collect(owner, plan, root, worker, output)
        elif worker.startswith("update-"):
            result = _update(owner, plan, root, worker, output)
        else:
            result = _collect(owner, plan, root, worker, output, development=True)
        report.update(result)
        report["status"] = result.get("status", "complete")
        report["success_boundary"] = report["status"] == "complete"
    except BaseException as error:
        report.update(status="execution_error", error={"type": type(error).__name__, "message": str(error)})
        write(root / "mechanism-stops" / (worker + "-execution.json"),
            {"kind": "execution_fault", "worker": worker, "error": report["error"], "observed_at": time.time()})
        raise
    finally:
        if owner is not None:
            report.update(final_actor_identity=owner._make_identity(), actor_steps=owner.actor_steps, critic_steps=owner.critic_steps)
        report.update(ended_at=time.time(), source_after=code_identity())
        write(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "supervise", "worker"))
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--worker", choices=WORKERS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, interrupted)
    if args.command == "prepare":
        prepare(args.run_root)
    elif args.command == "supervise":
        from scripts.software_learning_supervisor_v049 import supervise
        supervise(args.run_root)
    else:
        run_worker(args.run_root, args.worker, args.output)


if __name__ == "__main__":
    main()
