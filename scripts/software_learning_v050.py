"""One new B4/4 current-policy sensitivity window, with a CPU support gate."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import os
from pathlib import Path
import signal
import time
from types import SimpleNamespace

from proworksim.audit import code_identity
from proworksim.storage import digest, json_bytes, read_json
from scripts import software_learning_v049 as original
from scripts.software_learning_development_resume_v049r2g import bind, resources
from scripts.run_ne_v021 import read, reference, write
from scripts.software_development_v028 import task

VERSION = "software-learning-window-v0.50"
SOURCE = Path(__file__).resolve().parents[1]
DESIGN = SOURCE / "docs/experiments/software-learning-v050-design.json"
CONTROLS = SOURCE / "docs/experiments/software-learning-v050-cpu-controls.json"
GPU_ORDER = tuple(range(8))
BRANCHES = ("S_star", "B", "Q_plus", "Q_minus")
COLLECTION = tuple(f"collect-{i}" for i in range(3))
UPDATES = ("update-B", "update-Q_plus", "update-Q_minus")
DEVELOPMENT = tuple(f"dev-{branch}-{i}" for branch in BRANCHES for i in range(2))
WORKERS = ("s_star", *COLLECTION, *UPDATES, *DEVELOPMENT)
LIMITS = {**copy.deepcopy(original.LIMITS), "max_new_episodes": 56,
    "max_parallel_model_instances": 3, "max_new_backward_calls": 9216,
    "update_worker_seconds": 172800, "aggregate_update_worker_seconds": 518400,
    "max_admitted_rows_per_update": 3072, "max_forward_calls_per_update": 6150,
    "max_actor_backward_calls_per_update": 3072, "max_critic_backward_calls_per_update": 3072}
checked = original.checked


def seal(value, key="sha256"):
    if key in value:
        raise ValueError("A sealed value cannot be resealed implicitly")
    return {**value, key: digest(json_bytes(value))}


def check_seal(value, key="sha256"):
    if value.get(key) != digest(json_bytes({k: v for k, v in value.items() if k != key})):
        raise ValueError("Frozen artifact seal changed")
    return value


def source_files():
    files = original.source_files()
    for base in ("examples/software-organization-v049", "examples/software-learning-v050"):
        for p in (SOURCE / base).rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:
                files[str(p.relative_to(SOURCE))] = digest(p.read_bytes())
    for p in (DESIGN, CONTROLS, SOURCE / "docs/experiments/software-learning-v050-protocol.md",
              SOURCE / "docs/reference/audit-v049-next-v050.md"):
        files[str(p.relative_to(SOURCE))] = digest(p.read_bytes())
    return files


def validate_inventory(design):
    training, development = design["training_slots"], design["development_units_shared_by_branches"]
    if (len(training) != 24 or len(development) != 8 or design["development_states"] != list(BRANCHES) or design["branches"] != ["B", "Q_plus", "Q_minus"]
            or [u["root"] for u in training] != ["LA"] * 12 + ["LB"] * 12
            or [u["sampling_seed"] for u in training] != list(range(202610130501, 202610130525))
            or [u["root"] for u in development] != ["DA", "DA", "DB", "DB", "DC", "DC", "DD", "DD"]
            or [u["sampling_seed"] for u in development] != list(range(202610130601, 202610130609))):
        raise ValueError("Freeze the single original v050 24+32 inventory before collection")
    if len({u["slot_id"] for u in training}) != 24 or len({u["unit_id"] for u in development}) != 8:
        raise ValueError("Every declared slot must be unique")
    for rows, purpose in ((training, "policy_training"), (development, "policy_development")):
        if any(u.get("members") != ["member_001", "member_002"] or u.get("purpose") != purpose
               or u.get("generation_token_cap") != 500000 or u.get("first_member") not in u["members"] for u in rows):
            raise ValueError("Stable O1 purpose, members or budget changed")
    return design


def worker_units(plan, worker):
    if worker in COLLECTION:
        shard = COLLECTION.index(worker)
        return [copy.deepcopy(u) for i, u in enumerate(plan["inventory"]["training_slots"]) if i % 3 == shard]
    if worker in DEVELOPMENT:
        branch, shard = worker[4:].rsplit("-", 1)
        return [{**copy.deepcopy(u), "slot_id": u["unit_id"] + "-" + branch}
                for i, u in enumerate(plan["inventory"]["development_units_shared_by_branches"]) if i // 4 == int(shard)]
    return []


def prepare(root, *, parent_plan=SOURCE / "runs/software-learning-v049-resume-r1/plan.json"):
    from proworksim.software_mapper_v050 import mapping_spec
    from proworksim.software_organization_tasks_v050 import source_manifest, source_partition

    root, parent_plan = Path(root).resolve(), Path(parent_plan).resolve()
    if root.exists():
        raise FileExistsError("A new window cannot overwrite or retry another inventory")
    source = code_identity()
    if source.get("code_dirty") is not False:
        raise ValueError("Commit all new implementation, materials and protocol before model work")
    parent = check_seal(read_json(parent_plan), "plan_sha256")
    design = validate_inventory(read_json(DESIGN))
    control = check_seal(read_json(CONTROLS))
    if (control.get("passed") is not True or control.get("design_sha256") != reference(DESIGN)["sha256"]
            or control.get("new_9b_model_calls") != 0 or control.get("new_gpu_workers") != 0):
        raise ValueError("Bound finite CPU controls must pass before any new worker")
    folder = parent_plan.parent / "update-B/actual"
    report = read_json(folder / "report.json")
    update = read_json(checked(report["update_report"]))
    checkpoint = read_json(folder / "checkpoint/checkpoint.json")
    checked(checkpoint["state"])
    declared_star = design["S_star"]
    if (declared_star["checkpoint"]["path"] != str(folder / "checkpoint/checkpoint.json")
            or declared_star["checkpoint"]["sha256"] != reference(folder / "checkpoint/checkpoint.json")["sha256"]
            or any(declared_star.get(k) != checkpoint.get(k) for k in ("state", "state_tensor_digest", "actor_identity", "actor_steps", "critic_steps"))):
        raise ValueError("The current checkpoint must equal the precollection S_star design binding")
    if (report.get("status") != "complete" or report.get("success_boundary") is not True
            or report.get("source_before") != report.get("source_after") or report.get("source_after") != parent["source"]
            or report.get("checkpoint") != checkpoint or checkpoint.get("serialized_reload_exact") is not True
            or (checkpoint.get("actor_steps"), checkpoint.get("critic_steps")) != (4, 4)
            or update.get("status") != "updated" or update.get("stage") != "complete"
            or update.get("actor_optimizer_steps") != 1 or update.get("critic_optimizer_steps") != 1):
        raise ValueError("S_star must bind the completed original v049 B4/4 state")
    carry = ("data_root", "native_python", "native_python_prefix", "runtime_dependency_path", "common",
        "model_references", "original_plan", "original_expected_actor_identity", "expected_actor_identity",
        "expected_capacity_recipe_sha256", "expected_capacity_profile_sha256", "qualification_capacity_binding",
        "reused_model_qualification")
    plan = {**{k: copy.deepcopy(parent[k]) for k in carry}, "version": VERSION, "created_at": time.time(),
        "source": source, "source_root": str(SOURCE), "source_files": source_files(), "parent_plan": reference(parent_plan),
        "design": reference(DESIGN), "inventory": design, "cpu_controls": reference(CONTROLS),
        "workers": list(WORKERS), "limits": copy.deepcopy(LIMITS), "gpu_preference": list(GPU_ORDER),
        "s_star_checkpoint": reference(folder / "checkpoint/checkpoint.json"),
        "s_star_worker_report": reference(folder / "report.json"), "s_star_update_report": report["update_report"],
        "s_star_recipe": copy.deepcopy(update["recipe"]), "mapper_specification": mapping_spec(),
        "task_source_manifest": source_manifest(), "source_partition": source_partition(),
        "training_reward": "formal_R_joint_under_shared_token_and_time_policy",
        "development_F": "equal_weight_eight_formal_R_joint; any unknown retains null",
        "prior_artifact_roots": original.inherited.support.dense._artifact_roots([
            *parent["prior_artifact_roots"], parent_plan.parent]),
        "new_qualification_calls": 0, "new_qualification_tokens": 0, "automatic_retries": False,
        "automatic_successors": [], "old_queues_remain_paused": True,
        "generation_budget": {"slots": 56, "total_tokens": 28000000, "decisions": 7168, "attempts": 7168, "tests": 1792},
        "training_budget": {"branches": 3, "per_branch_admitted_rows": 3072, "per_branch_forward_formula": "2*N+6",
            "per_branch_actor_backward": 3072, "per_branch_critic_backward": 3072,
            "per_branch_actor_optimizer": 1, "per_branch_critic_optimizer": 1,
            "per_branch_worker_seconds": 172800, "aggregate_worker_seconds": 518400}}
    root.mkdir(parents=True, exist_ok=False)
    plan = seal(plan, "plan_sha256")
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    plan = check_seal(read_json(Path(root) / "plan.json"), "plan_sha256")
    if (plan.get("version") != VERSION or plan.get("source") != code_identity()
            or plan.get("source_files") != source_files() or plan.get("design") != reference(DESIGN)
            or plan.get("limits") != LIMITS or plan.get("workers") != list(WORKERS)
            or plan.get("gpu_preference") != list(GPU_ORDER) or plan.get("inventory") != read_json(DESIGN)):
        raise ValueError("Frozen v050 implementation, inventory or resources changed")
    validate_inventory(plan["inventory"])
    from proworksim.software_organization_tasks_v050 import source_manifest, source_partition
    if plan.get("task_source_manifest") != source_manifest() or plan.get("source_partition") != source_partition():
        raise ValueError("Frozen six-root source identity or partition changed")
    for key in ("cpu_controls", "s_star_checkpoint", "s_star_worker_report", "s_star_update_report"):
        checked(plan[key])
    return plan


def _load_owner(plan, output):
    provider = resources(GPU_ORDER)
    dependencies = SimpleNamespace(**{**vars(original.inherited), **vars(provider)})
    return bind(original._load_owner, inherited=dependencies)(plan, output)


def _restored_state(owner, root, branch, output):
    plan = read_json(Path(root) / "plan.json")
    checkpoint_path = (checked(plan["s_star_checkpoint"]) if branch == "S_star"
                       else Path(root) / ("update-" + branch) / "actual/checkpoint/checkpoint.json")
    expected = read_json(checkpoint_path)
    task(output, "restore-complete-" + branch, "boundary")
    restored = owner.restore_checkpoint(checkpoint_path.parent)
    steps = (owner.actor_steps, owner.critic_steps)
    admissible = steps == (4, 4) if branch == "S_star" else all(step in (4, 5) for step in steps)
    if (restored != expected or owner.freeze_identity() != expected["actor_identity"]
            or steps != (expected["actor_steps"], expected["critic_steps"]) or not admissible):
        raise ValueError("Restore exact complete independent branch state")
    write(Path(output) / "loaded-state.json", {"branch": branch, "checkpoint": reference(checkpoint_path),
        "restored": restored, "actor_identity": owner.freeze_identity(),
        "actor_steps": owner.actor_steps, "critic_steps": owner.critic_steps})
    return restored


def _new_prepared(unit, folder):
    from proworksim.software_organization_tasks_v050 import TASK_LABELS
    from proworksim.software_organization_v050 import build_software_collaboration_case, case_spec
    case = case_spec(next(k for k, label in TASK_LABELS.items() if label == unit["root"]),
                     first_member=unit["first_member"], purpose=unit["purpose"])
    return build_software_collaboration_case(case, folder)


def _init_s_star(owner, plan, root, output):
    from proworksim.software_context_v048 import CANDIDATE_SHA256, VERSION as PRESENTATION
    from proworksim.software_learning_v050 import bind_s_star_checkpoint, VERSION as BRIDGE
    from proworksim.software_organization_runtime_v050 import VERSION as RUNTIME
    from proworksim.software_runtime_v033 import SDK_CONTEXT_SELECTION
    from proworksim.software_training_v050 import declare_window, policy_spec, situation_id, situation_fingerprint
    _restored_state(owner, root, "S_star", output)
    if owner.recipe != plan["s_star_recipe"]:
        raise ValueError("The retained H1 recipe must remain exact")
    s_star = bind_s_star_checkpoint(owner, checked(plan["s_star_checkpoint"]).parent)
    write(root / "s_star.json", s_star)
    prepared_roots, slots = {}, []
    for unit in plan["inventory"]["training_slots"]:
        if unit["root"] not in prepared_roots:
            prepared_roots[unit["root"]] = _new_prepared(unit, output / ("declaration-case-" + unit["root"]))
        prepared = prepared_roots[unit["root"]]
        slots.append({"slot_id": unit["slot_id"], "xi_id": situation_id(prepared.case),
            "xi_fingerprint": situation_fingerprint(prepared), "active_members": unit["members"],
            "policies": policy_spec(owner, prepared), "mapping_spec_id": plan["mapper_specification"]["spec_id"]})
    gamma = {"gamma_version": "software-information-v0.50", "source_usage": "policy_training",
        "collection_mode": "current_policy_collection", "optimizer_update_allowed": True,
        "harness": "openhands_v16", "runtime_version": RUNTIME, "presentation_version": PRESENTATION,
        "sdk_context_selection": SDK_CONTEXT_SELECTION, "mapper_specification": plan["mapper_specification"],
        "mapper_spec_sha256": digest(json_bytes(plan["mapper_specification"])),
        "design_sha256": plan["design"]["sha256"], "learning_bridge_version": BRIDGE,
        "training_reward": plan["training_reward"], "s_star": s_star,
        "presentation_identity": {"candidate_sha256": CANDIDATE_SHA256, "presentation_version": PRESENTATION}}
    declaration = declare_window(plan["inventory"]["learning"]["training_window_id"],
        actor_identity=owner.freeze_identity(), gamma_identity=gamma, slot_specs=slots, min_class_count=2)
    write(root / "declaration.json", declaration)
    write(root / "precollection-binding.json", seal({"version": VERSION,
        "declaration": reference(root / "declaration.json"), "s_star": reference(root / "s_star.json"),
        "source": plan["source"], "all_training_and_development_inventory_frozen": True,
        "new_model_calls": 0, "new_parameter_updates": 0}))
    return {"s_star": s_star, "declaration": reference(root / "declaration.json")}


def _collect(owner, plan, root, worker, output):
    from proworksim.software_organization_runtime_v050 import collect_episode
    from proworksim.software_organization_measurement_v050 import measure_slot
    from proworksim.software_training_v050 import export_software_episode
    development = worker in DEVELOPMENT
    branch = worker[4:].rsplit("-", 1)[0] if development else "S_star"
    restored = _restored_state(owner, root, branch, output)
    declaration = read_json(root / "declaration.json")
    guard = owner.capture_evaluation_state()
    if not development:
        owner.begin_window(declaration["window_id"])
    rows, entries, terminal = [], [], "complete"
    for unit in worker_units(plan, worker):
        if list((root / "mechanism-stops").glob("*.json")):
            terminal = "paused_before_next_slot"
            break
        sid, folder = unit["slot_id"], output / "episodes" / unit["slot_id"]
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
        if measurement["decision"] != "continue":
            terminal = measurement["decision"]
            write(root / "mechanism-stops" / (sid + ".json"), {"kind": terminal, "worker": worker,
                "slot_id": sid, "measurement": reference(folder / "mechanical-measurement.json")})
            break
        if not development:
            entry, details = export_software_episode(prepared, folder / "episode", row["assessment"],
                declaration=declaration, slot_id=sid, captured=read_json(folder / "public-capture.json"), runtime_row=row)
            write(folder / "training-entry.json", entry)
            write(folder / "training-export.json", details)
            entries.append(entry)
    if not development:
        owner.finish_evaluation(entries, output / "collection-boundary")
    frozen_guard = owner.finish_evaluation_guard(guard)
    write(output / "collection-guard.json", frozen_guard)
    if not frozen_guard["learning_unchanged"] or not frozen_guard["rng_restored_exactly"]:
        raise ValueError("Frozen collection changed learning state or failed RNG restoration")
    if entries:
        write(output / "entries.json", entries)
    return {"rows": rows, "status": terminal, "state_loaded_for_collection": restored,
            "collection_guard": reference(output / "collection-guard.json")}


def materialize_entries(plan, root):
    root = Path(root)
    by_slot, sources = {}, []
    for worker in COLLECTION:
        rows = read_json(root / worker / "actual/entries.json")
        if [row["slot_id"] for row in rows] != [u["slot_id"] for u in worker_units(plan, worker)]:
            raise ValueError("Each source shard must supply exactly its own eight entries")
        for entry in rows:
            sid = entry["slot_id"]
            if sid in by_slot:
                raise ValueError("Duplicate source slot")
            folder = root / worker / "actual/episodes" / sid
            if entry != read_json(folder / "training-entry.json"):
                raise ValueError("Shard entry differs from its durable original export")
            by_slot[sid] = entry
            sources.append({"slot_id": sid, "entry": reference(folder / "training-entry.json"),
                "source_result": reference(folder / "slot-result.json"),
                "source_manifest": reference(folder / "episode/manifest.json")})
    order = [unit["slot_id"] for unit in plan["inventory"]["training_slots"]]
    return [by_slot[sid] for sid in order], sorted(sources, key=lambda row: order.index(row["slot_id"]))


def training_compute_receipt(admission, *, started_at=None):
    rows = admission.get("decisions")
    if not isinstance(rows, list) or len(rows) > LIMITS["max_admitted_rows_per_update"]:
        raise ValueError("Admitted training rows exceed the frozen compute budget or have unknown shape")
    return {"started_at": time.time() if started_at is None else started_at, "ended_at": None,
        "maximum_seconds": LIMITS["update_worker_seconds"], "admitted_rows": len(rows),
        "forward_upper": 2 * len(rows) + 6, "actor_backward_upper": len(rows),
        "critic_backward_upper": len(rows), "actor_steps_upper": 1, "critic_steps_upper": 1}


def run_support_gate(root):
    from proworksim.software_learning_v050 import prepare_training_admission
    from proworksim.software_allocation_v050 import build_support_report, pretraining_support_gate
    root = Path(root).resolve()
    plan = frozen(root)
    if (root / "support-gate.json").exists():
        raise FileExistsError("The pretraining support decision is made once, never resampled")
    entries, sources = materialize_entries(plan, root)
    declaration = read_json(root / "declaration.json")
    admission = prepare_training_admission(entries, declaration, plan["s_star_recipe"])
    training_compute_receipt(admission)
    support = build_support_report(entries, declaration, admission=admission, design=plan["inventory"])
    gate = pretraining_support_gate(support)
    if type(gate.get("run_B50")) is not bool:
        raise ValueError("Support-only gate needs an explicit binary release")
    write(root / "entries.json", entries)
    write(root / "source-registry.json", seal({"version": VERSION, "sources": sources,
        "declaration": reference(root / "declaration.json"), "slot_count": 24, "old_material_included": False}))
    write(root / "pretraining-admission.json", admission)
    write(root / "support-before-training.json", support)
    envelope = seal({"version": VERSION, "run_B50": gate["run_B50"], "gate": gate,
        "entries": reference(root / "entries.json"), "registry": reference(root / "source-registry.json"),
        "support": reference(root / "support-before-training.json"), "admission": reference(root / "pretraining-admission.json"),
        "source": plan["source"], "new_model_calls": 0, "new_backward_calls": 0,
        "development_results_read": False})
    write(root / "support-gate.json", envelope)
    return envelope


def load_materialized_entries(plan, root):
    gate = check_seal(read_json(Path(root) / "support-gate.json"))
    if gate["run_B50"] is not True:
        raise ValueError("No training or development after no reliable multi-class support")
    entries = read_json(checked(gate["entries"]))
    current, sources = materialize_entries(plan, root)
    registry = check_seal(read_json(checked(gate["registry"])))
    if current != entries or sources != registry["sources"]:
        raise ValueError("Current-policy sources changed after the unique CPU support gate")
    return entries


@contextmanager
def training_progress(owner, output):
    """Observe native calls and enforce the frozen forward cap before dispatch."""
    output = Path(output)
    original_call = owner.learning_logprobs
    had_override = "learning_logprobs" in owner.__dict__
    old_override = owner.__dict__.get("learning_logprobs")
    receipt_path = output / "training-compute.json"
    receipt = read_json(receipt_path)
    receipt.update(native_forward_started=0, native_forward_completed=0, native_gradient_forward_started=0,
                   native_no_grad_forward_started=0)
    write(receipt_path, receipt)

    def observed(*args, **kwargs):
        if receipt["native_forward_started"] >= receipt["forward_upper"]:
            raise RuntimeError("Frozen forward computation budget exhausted before another dispatch")
        receipt["native_forward_started"] += 1
        field = "native_gradient_forward_started" if owner.torch.is_grad_enabled() else "native_no_grad_forward_started"
        receipt[field] += 1
        write(receipt_path, receipt)
        count = receipt["native_forward_started"]
        task(output, f"learning-forward-{count:06d}", "training_step")
        result = original_call(*args, **kwargs)
        receipt["native_forward_completed"] += 1
        write(receipt_path, receipt)
        task(output, f"learning-backward-or-bookkeeping-{count:06d}", "training_step")
        return result

    owner.learning_logprobs = observed
    try:
        yield
    finally:
        if had_override:
            owner.learning_logprobs = old_override
        else:
            del owner.learning_logprobs


def _update(owner, plan, root, worker, output):
    from proworksim.software_learning_v050 import prepare_training_admission, update_software_window, bind_composition
    from proworksim.software_allocation_v050 import build_support_report, select_direction
    branch = worker.removeprefix("update-")
    _restored_state(owner, root, "S_star", output)
    declaration = read_json(root / "declaration.json")
    entries = load_materialized_entries(plan, root)
    owner.begin_window(declaration["window_id"])
    admission = prepare_training_admission(entries, declaration, owner.recipe)
    if admission != read_json(root / "pretraining-admission.json"):
        raise ValueError("Matched branches cannot alter the pretraining admission")
    base = read_json(root / "support-before-training.json")
    weights = {row["slot_id"]: dict.fromkeys(row["active_members"], 1.0) for row in entries}
    direction = None
    if branch != "B":
        direction = check_seal(read_json(root / "direction.json"), "seal_sha256")
        core = check_seal(direction["direction"], "seal_sha256")
        if (direction["selected"] is not True or core.get("source_support_artifact_sha256") != reference(root / "support.json")["sha256"]
                or core.get("declaration_sha256") != digest(json_bytes(declaration))
                or core.get("design_sha256") != plan["design"]["sha256"]):
            raise ValueError("Q requires the unique predevelopment sealed supported direction")
        key = "plus" if branch == "Q_plus" else "minus"
        weights = direction[key + "_weights"]
        if weights != core[key + "_weights_by_slot"]:
            raise ValueError("Q branch changed the sealed composition")
    binding = {"declaration_sha256": digest(json_bytes(declaration)), "design_sha256": plan["design"]["sha256"],
        "mapper_spec_sha256": declaration["gamma_identity"]["mapper_spec_sha256"],
        "support_artifact_sha256": reference(root / "support.json")["sha256"] if direction else digest(json_bytes(base)),
        "selected_direction_artifact_sha256": reference(root / "direction.json")["sha256"] if direction else None}
    composition = bind_composition(entries, declaration, weights, binding=binding)
    write(output / "composition-before-update.json", composition)
    write(output / "training-compute.json", training_compute_receipt(admission))
    task(output, "actual-input-admission", "boundary")
    with training_progress(owner, output):
        report = update_software_window(owner, entries, output / "update", declaration=declaration,
            request_evidence_root=root, composition=composition, observe_support_gradients=branch == "B")
    task(output, "save-updated-complete-state-and-support", "boundary")
    if report["status"] not in {"updated", "zero_step_zero_actor_advantage_or_gradient", "zero_step_no_admitted_own_actions"}:
        raise ValueError("H1 update did not reach its declared boundary")
    if (report.get("backward_decisions_completed", 0) > len(admission["decisions"])
            or any(report.get(k, 0) > 1 for k in ("actor_optimizer_steps", "critic_optimizer_steps"))
            or report.get("post_update_additional_actor_forwards", 0) > 6):
        raise ValueError("Original H1 compute counts exceeded the frozen per-branch budget")
    if branch != "B":
        baseline = read_json(checked(direction["B_update"]))
        if any(report.get(k) != baseline.get(k) for k in ("advantages", "old_critic_values", "rewards")):
            raise ValueError("Matched branch changed the frozen advantage, critic or reward")
    checkpoint = owner.save_checkpoint(output / "checkpoint")
    compute = read_json(output / "training-compute.json")
    compute.update(ended_at=time.time())
    compute["elapsed_seconds"] = compute["ended_at"] - compute["started_at"]
    write(output / "training-compute.json", compute)
    if compute["elapsed_seconds"] > compute["maximum_seconds"]:
        raise ValueError("Update exceeded its frozen compute wall-clock budget")
    if branch == "B":
        support = build_support_report(entries, declaration, admission=admission, design=plan["inventory"], learner_report=report)
        write(root / "support.json", support)
        grad_path = output / "update/support-gradients.pt"
        if not grad_path.exists():
            raise ValueError("Support-qualified B lacks the required original gradient observation")
        gradients = owner.torch.load(grad_path, map_location="cpu", weights_only=True)
        core = select_direction(support, gradients, gradient_receipt=read_json(output / "update/support-gradients.json"), torch=owner.torch)
        direction = seal({"version": VERSION, "selected": core["selected"] is not None,
            "reliable_base_material": bool(admission["decisions"]), "direction": core, "epsilon": core["epsilon"],
            "plus_weights": core["plus_weights_by_slot"], "minus_weights": core["minus_weights_by_slot"],
            "baseline_weights": core["baseline_weights_by_slot"], "B_update": reference(output / "update/report.json"),
            "support": reference(root / "support.json"), "frozen_before_any_development": True,
            "created_at": time.time()}, "seal_sha256")
        if any((root / name).exists() for name in DEVELOPMENT):
            raise ValueError("Direction must be sealed before any development worker starts")
        write(root / "direction.json", direction)
    return {"branch": branch, "update_report": reference(output / "update/report.json"),
        "checkpoint": checkpoint, "new_actor_steps": report["actor_optimizer_steps"],
        "new_critic_steps": report["critic_optimizer_steps"], "new_backward_decisions": report["backward_decisions_completed"]}


def received_signal(signum, frame):
    raise KeyboardInterrupt(f"signal {signum}")


def run_worker(root, worker, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    plan = frozen(root)
    original.inherited.validate_worker_interpreter(plan)
    if (worker not in WORKERS or output != root / worker / "actual"
            or os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, GPU_ORDER))):
        raise ValueError("Require the original v050 worker/output and one authorized GPU")
    own = (read(root / "supervisor.json") or {}).get("states", {}).get(worker, {})
    if own.get("status") not in {"not_started", "running"} or own.get("attempted") is not True:
        raise ValueError("Require a fresh supervisor-owned worker launch")
    output.mkdir(parents=True, exist_ok=False)
    owner = None
    report = {"version": VERSION, "worker": worker, "status": "loading", "started_at": time.time(),
        "source_before": code_identity(), "success_boundary": False, "new_actor_steps": 0, "new_critic_steps": 0}
    write(output / "report.json", report)
    try:
        owner = _load_owner(plan, output)
        result = (_init_s_star(owner, plan, root, output) if worker == "s_star" else
                  _update(owner, plan, root, worker, output) if worker in UPDATES else
                  _collect(owner, plan, root, worker, output))
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
    parser.add_argument("command", choices=("prepare", "supervise", "worker", "support"))
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--worker", choices=WORKERS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, received_signal)
    if args.command == "prepare":
        prepare(args.run_root)
    elif args.command == "supervise":
        from scripts.software_learning_supervisor_v050 import supervise
        supervise(args.run_root)
    elif args.command == "support":
        run_support_gate(args.run_root)
    else:
        run_worker(args.run_root, args.worker, args.output)


if __name__ == "__main__":
    main()
