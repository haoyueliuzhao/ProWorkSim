"""Source-bound v049 r1 continuation of only the original unstarted inventory.

The original S0, declaration, model-visible implementation, slots and closed
records remain immutable. New artifacts interpret missing budget-wrapper world
identity through a separately checked reader; no input or trajectory is replayed.
"""
from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import signal
import time

from proworksim.audit import code_identity
from proworksim.storage import digest, json_bytes, read_json
from scripts import software_learning_v049 as original
from scripts.run_ne_v021 import read, reference, write
from scripts.software_development_v028 import task

VERSION = "software-learning-original-inventory-resume-v0.49-r1"
SOURCE = Path(__file__).resolve().parents[1]
ORIGINAL_VERSION = original.VERSION
DESIGN = original.DESIGN
GPU_ORDER = original.GPU_ORDER
WORKERS = original.WORKERS
LIMITS = copy.deepcopy(original.LIMITS)
checked = original.checked
COLLECTORS = ("collect-LA", "collect-LB")


def source_files():
    return original.source_files()


def _seal(value, key="sha256"):
    return {**value, key: digest(json_bytes(value))}


def _check_seal(value, key):
    if value.get(key) != digest(json_bytes({name: item for name, item in value.items() if name != key})):
        raise ValueError("Original sealed artifact changed: " + key)


def original_source_agreement(parent, source_root=SOURCE):
    """Every pre-existing frozen file remains byte-identical; new adapters are additions."""
    checked_files = {}
    for name, expected in parent["source_files"].items():
        path = Path(source_root) / name
        if not path.is_file() or digest(path.read_bytes()) != expected:
            raise ValueError("An original frozen dependency changed: " + name)
        checked_files[name] = expected
    return {"version": "v049-r1-original-source-agreement", "passed": True,
        "original_source": copy.deepcopy(parent["source"]), "files_checked": len(checked_files),
        "all_original_files_unchanged": True, "original_source_files_sha256": digest(json_bytes(checked_files)),
        "scope": "All original Python, original business assets and protocol bindings; only newly added host/reader files may differ."}


def _unit_folder(root, unit):
    return Path(root) / ("collect-" + unit["root"]) / "actual/episodes" / unit["slot_id"]


def bind_closed_slot(folder, unit, *, expected_source=None):
    """Identify one actual original closed slot; never select on R or map validity."""
    folder = Path(folder).resolve()
    row, manifest, measured = (read_json(folder / name) for name in
        ("slot-result.json", "episode/manifest.json", "mechanical-measurement.json"))
    scope = manifest.get("scenario", {}).get("variation", {}).get("organization_runtime", {})
    if (row.get("status") != "closed" or type(row.get("R")) is not int or row["R"] not in (0, 1)
            or manifest.get("status") != "closed" or measured.get("decision") != "continue"
            or row.get("slot_id") != unit["slot_id"] or row.get("sampling_seed") != unit["sampling_seed"]
            or row.get("first_member") != unit["first_member"] or row.get("purpose") != "policy_training"
            or row.get("training_eligible") is not True or row.get("condition") != "O1"
            or scope.get("slot_id") != unit["slot_id"] or scope.get("case") != original._case(unit)
            or scope.get("online_window_id") != "v049-o1-learning-window-01"
            or scope.get("actor_identity") != row.get("actor_identity")
            or row.get("episode_manifest") != str(folder / "episode/manifest.json")
            or any(row.get(key) != 0 for key in ("actor_updates", "critic_updates", "new_backward_calls"))
            or row.get("usage", {}).get("uncertain_usage_attempts") != 0
            or expected_source is not None and manifest.get("source_start") != expected_source):
        raise ValueError("A started slot lacks its exact safely closed original binding: " + unit["slot_id"])
    paths = {"source_result": "slot-result.json", "source_manifest": "episode/manifest.json",
        "source_mechanical": "mechanical-measurement.json", "source_assessment": "assessment.json",
        "source_capture": "public-capture.json", "source_guard": "evaluation-guard.json"}
    result = {"slot_id": unit["slot_id"], "original_unit": copy.deepcopy(unit),
        "episode_folder": str(folder), **{name: reference(folder / name_on_disk) for name, name_on_disk in paths.items()},
        "original_formal_R": row["R"], "actual_usage": copy.deepcopy(row["usage"]),
        "actual_member_tests": row["team_budget"]["tests"]["used"]}
    for label, filename in (("original_training_entry", "training-entry.json"), ("original_training_export", "training-export.json")):
        if (folder / filename).is_file():
            result[label] = reference(folder / filename)
    return result


def derive_inventory(original_root, *, source_root=SOURCE, check_source=True):
    root = Path(original_root).resolve()
    parent = read_json(root / "plan.json")
    _check_seal(parent, "plan_sha256")
    if parent.get("version") != ORIGINAL_VERSION or parent.get("workers") != list(WORKERS):
        raise ValueError("Continuation requires the one original v049 plan")
    states = read_json(root / "supervisor.json")
    if (states.get("status") not in {"complete", "closed_with_unknowns"}
            or not states.get("ended_at") or states.get("source") != parent["source"]
            or any(row.get("status") in {"running", "waiting", "launch_intent"} for row in states.get("states", {}).values())):
        raise ValueError("Original supervisor must first close all in-flight workers")
    for name in WORKERS:
        state = states["states"].get(name, {})
        if name not in {"s0", *COLLECTORS}:
            if state.get("attempted") is not False or (root / name / "actual").exists():
                raise ValueError("An original update/development attempt cannot be resumed or replayed")
            continue
        if state.get("exit_code") != 0 or not state.get("ended_at"):
            raise ValueError("Original S0/collection workers need known clean exits")
        report = read_json(root / name / "actual/report.json")
        allowed = {"complete"} if name == "s0" else {"complete", "paused_before_next_slot"}
        if (report.get("status") not in allowed or report.get("source_before") != report.get("source_after")
                or report.get("source_after") != parent["source"]
                or any(report.get(key) != 0 for key in ("new_actor_steps", "new_critic_steps"))):
            raise ValueError("Original preupdate frozen-worker boundary is incomplete")
    s0 = read_json(root / "s0.json")
    declaration = read_json(root / "declaration.json")
    checkpoint = read_json(checked(s0["checkpoint_ref"]))
    checked(checkpoint["state"])
    if (declaration.get("gamma_identity", {}).get("s0") != s0
            or declaration.get("actor_identity") != s0.get("actor_identity")
            or checkpoint.get("state_tensor_digest") != s0.get("state_tensor_digest")
            or checkpoint.get("actor_steps") != 3 or checkpoint.get("critic_steps") != 3):
        raise ValueError("Original complete S0/declaration cannot be changed")
    units = parent["inventory"]["training_slots"]
    if len(units) != 8 or len({u["slot_id"] for u in units}) != 8 or [u["slot_id"] for u in units] != [u["slot_id"] for u in declaration["slots"]]:
        raise ValueError("Preserve the original unique eight-slot order")
    known_paths = {_unit_folder(root, unit).resolve() for unit in units}
    actual_paths = {p.resolve() for name in COLLECTORS for p in (root / name / "actual/episodes").glob("*") if p.is_dir()}
    if not actual_paths <= known_paths:
        raise ValueError("Unexpected original training episode directory")
    retained, remaining = [], []
    for unit in units:
        folder = _unit_folder(root, unit)
        if not folder.exists():
            remaining.append(copy.deepcopy(unit))
        elif not (folder / "slot-result.json").is_file():
            raise ValueError("Started or prepared but unclosed slot cannot be treated as unstarted: " + unit["slot_id"])
        else:
            retained.append({**bind_closed_slot(folder, unit, expected_source=parent["source"]), "origin": "original_v049"})
    usage = {key: sum(item["actual_usage"][key] for item in retained)
             for key in ("decisions", "attempts", "prompt_tokens", "completion_tokens", "total_tokens")}
    usage["member_tests"] = sum(item["actual_member_tests"] for item in retained)
    usage["worker_gpu_seconds_including_original_S0"] = sum(row.get("elapsed_gpu_seconds", 0) for row in states["states"].values())
    return {"version": VERSION, "original_root": str(root), "original_plan": reference(root / "plan.json"),
        "original_supervisor": reference(root / "supervisor.json"), "original_s0": reference(root / "s0.json"),
        "original_declaration": reference(root / "declaration.json"), "original_checkpoint": s0["checkpoint_ref"],
        "original_checkpoint_state": checkpoint["state"],
        "retained_slots": retained, "remaining_training_units": remaining,
        "retained_actual_cost": usage, "old_unspent_token_budget_not_transferred": len(retained) * 500000 - usage["total_tokens"],
        "original_stops": [reference(path) for path in sorted((root / "mechanism-stops").glob("*.json"))],
        "source_agreement": original_source_agreement(parent, source_root) if check_source else None,
        "old_results_or_exports_rewritten": False, "replayed_slots": [], "new_seeds": []}


def budget_caps(derived):
    new_training = len(derived["remaining_training_units"])
    maximum_new = new_training + 12
    old = derived["retained_actual_cost"]
    return {"new_training_slots": new_training, "conditional_development_slots_max": 12,
        "new_generation_slots_max": maximum_new, "new_actual_generation_tokens_max": maximum_new * 500000,
        "new_decisions_max": maximum_new * 128, "new_attempts_max": maximum_new * 128,
        "new_member_tests_max": maximum_new * 32,
        "including_retained_actual_tokens_upper": old["total_tokens"] + maximum_new * 500000,
        "including_retained_actual_decisions_upper": old["decisions"] + maximum_new * 128,
        "including_retained_actual_attempts_upper": old["attempts"] + maximum_new * 128,
        "including_retained_actual_tests_upper": old["member_tests"] + maximum_new * 32,
        "old_actual_cost_counted_once": True,
        "old_unspent_tokens_not_transferred": derived["old_unspent_token_budget_not_transferred"],
        "new_S0_qualification_workers": 0, "new_model_qualification_calls": 0,
        "original_design_generation_slots_max": 20, "original_design_actual_generation_tokens_max": 10000000,
        "original_three_H1_branches_max": 3, "additional_samples_or_directions": 0}


def prepare(root, *, original_root, controls):
    root, old_root = Path(root).resolve(), Path(original_root).resolve()
    if root.exists() or root == old_root or root in old_root.parents or old_root in root.parents:
        raise FileExistsError("Resume needs a new independent root, never an original or nested output")
    source = code_identity()
    if source.get("code_dirty") is not False:
        raise ValueError("Commit the complete isolated r1 reader/host before any resumed model work")
    controls = Path(controls).resolve()
    proof = read_json(controls)
    _check_seal(proof, "sha256")
    if proof.get("passed") is not True or proof.get("new_model_calls") != 0 or proof.get("new_gpu_workers") != 0:
        raise ValueError("New finite CPU read-binding controls must pass before resuming")
    derived = derive_inventory(old_root)
    parent = read_json(checked(derived["original_plan"]))
    plan = {**copy.deepcopy(parent), "version": VERSION, "created_at": time.time(),
        "source": source, "source_root": str(SOURCE), "source_files": source_files(),
        "resume_of": derived["original_plan"], "original_root": str(old_root),
        "original_S0_reused_without_new_qualification": True,
        "declaration": derived["original_declaration"], "s0": derived["original_s0"],
        "resume_inventory": derived, "new_budget_caps": budget_caps(derived),
        "resume_cpu_controls": reference(controls), "workers": list(WORKERS),
        "prior_artifact_roots": original.inherited.support.dense._artifact_roots([*parent["prior_artifact_roots"], old_root]),
        "sampling_source_scope": "Every original pre-existing frozen source file is byte-identical; only new read-only record adapters and host files are added.",
        "entry_materialization": "Exactly once from all eight unique archived original slots at B admission; Q consumes that same sealed derived material.",
        "scope": "Original v049 inventory continuation: retain all closed slots, collect only original unstarted slots, interpret every original training source once for B, then execute original conditional H1/development branches. No new seed, source task, S0 qualification or extra direction.",
        "automatic_retries": False, "automatic_successors": [], "old_queues_remain_paused": True}
    plan.pop("plan_sha256", None)
    plan["plan_sha256"] = digest(json_bytes(plan))
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    plan = read_json(Path(root) / "plan.json")
    _check_seal(plan, "plan_sha256")
    if (plan.get("version") != VERSION or plan.get("source") != code_identity()
            or plan.get("source_files") != source_files() or plan.get("workers") != list(WORKERS)
            or plan.get("limits") != LIMITS or plan.get("gpu_preference") != list(GPU_ORDER)
            or plan.get("automatic_retries") is not False or plan.get("automatic_successors") != []):
        raise ValueError("Frozen r1 host, source or dependency inventory changed")
    derived = derive_inventory(plan["original_root"])
    if (derived != plan.get("resume_inventory") or budget_caps(derived) != plan.get("new_budget_caps")
            or plan.get("declaration") != derived["original_declaration"] or plan.get("s0") != derived["original_s0"]):
        raise ValueError("Original closed inventory, S0, declaration or continuation budget changed")
    parent = read_json(checked(plan["resume_of"]))
    for key in ("inventory", "design", "mapper_specification", "source_partition", "task_source_manifest", "training_reward", "development_F"):
        if plan[key] != parent[key]:
            raise ValueError("Original declaration or scientific protocol changed: " + key)
    checked(plan["resume_cpu_controls"])
    return plan


def _restored_state(owner, root, branch, output):
    plan = read_json(Path(root) / "plan.json")
    folder = (checked(plan["resume_inventory"]["original_checkpoint"]).parent if branch == "S0"
              else Path(root) / ("update-" + branch) / "actual/checkpoint")
    restored = owner.restore_checkpoint(folder)
    if branch == "S0" and restored.get("state_tensor_digest") != read_json(checked(plan["s0"]))["state_tensor_digest"]:
        raise ValueError("Restored original S0 state differs from its exact declaration")
    write(Path(output) / "loaded-state.json", {"branch": branch, "checkpoint": reference(folder / "checkpoint.json"),
        "restored": restored, "actor_identity": owner.freeze_identity(),
        "actor_steps": owner.actor_steps, "critic_steps": owner.critic_steps,
        "original_S0_reused": branch == "S0", "old_complete_state_modified": False})
    return restored


def _source_registry(plan, root):
    retained = {row["slot_id"]: copy.deepcopy(row) for row in plan["resume_inventory"]["retained_slots"]}
    rows = []
    for unit in plan["inventory"]["training_slots"]:
        if unit["slot_id"] in retained:
            row = retained[unit["slot_id"]]
            for value in row.values():
                if isinstance(value, dict) and "path" in value and "sha256" in value:
                    checked(value)
        else:
            row = {**bind_closed_slot(_unit_folder(root, unit), unit, expected_source=plan["source"]), "origin": "resume_r1"}
        rows.append(row)
    if len(rows) != 8 or len({row["episode_folder"] for row in rows}) != 8:
        raise ValueError("The eight original training episode sources must be unique")
    return _seal({"version": "v049-unique-source-registry-r1", "slots": rows,
        "declaration": plan["declaration"], "original_plan": plan["resume_of"],
        "resume_plan": reference(Path(root) / "plan.json"), "development_sources_included": False,
        "new_source_instances_created": 0, "original_files_copied": False})


def materialize_entries(plan, root):
    """One source-bound re-export of every original slot, then immutable reuse."""
    from proworksim.software_training_v049r1 import reexport_closed_slot
    root = Path(root)
    registry_path, entries_path = root / "source-registry.json", root / "entries.json"
    if registry_path.exists() or entries_path.exists() or (root / "rematerialized-entries").exists():
        raise FileExistsError("Original eight-slot materialization cannot be retried or overwritten")
    registry = _source_registry(plan, root)
    write(registry_path, registry)
    declaration = read_json(checked(plan["declaration"]))
    entries, refs = [], []
    for row in registry["slots"]:
        destination = root / "rematerialized-entries" / row["slot_id"]
        entry, details = reexport_closed_slot(row["episode_folder"], declaration, destination)
        if entry["slot_id"] != row["slot_id"]:
            raise ValueError("Re-export changed the original slot identity")
        entries.append(entry)
        refs.append({"slot_id": row["slot_id"], "episode_folder": row["episode_folder"],
            "entry_sha256": digest(json_bytes(entry)), "details_sha256": digest(json_bytes(details))})
    write(entries_path, entries)
    write(root / "materialization.json", _seal({"version": VERSION, "passed": True,
        "source_registry": reference(registry_path), "entries": reference(entries_path), "slots": refs,
        "original_slots_once_each": 8, "old_costs_counted_once": True,
        "original_record_or_feedback_rewritten": False, "new_model_calls": 0,
        "new_tokenizer_calls": 0, "new_world_or_acceptance_executions": 0}))
    return entries


def load_materialized_entries(plan, root):
    root = Path(root)
    proof = read_json(root / "materialization.json")
    _check_seal(proof, "sha256")
    if proof.get("passed") is not True or proof.get("original_slots_once_each") != 8:
        raise ValueError("Matched branches need the single completed original eight-slot materialization")
    registry = read_json(checked(proof["source_registry"]))
    _check_seal(registry, "sha256")
    if registry != _source_registry(plan, root):
        raise ValueError("Original training sources changed after materialization")
    entries = read_json(checked(proof["entries"]))
    if ([entry["slot_id"] for entry in entries] != [unit["slot_id"] for unit in plan["inventory"]["training_slots"]]
            or [digest(json_bytes(entry)) for entry in entries] != [row["entry_sha256"] for row in proof["slots"]]):
        raise ValueError("Original per-slot material or order changed")
    return entries


def _collect(owner, plan, root, worker, output, *, development=False):
    from proworksim.software_organization_runtime_v049 import collect_episode
    from proworksim.software_organization_measurement_v049 import measure_slot
    branch = worker.removeprefix("dev-") if development else "S0"
    restored = _restored_state(owner, root, branch, output)
    declaration = read_json(checked(plan["declaration"]))
    units = plan["inventory"]["development_units_shared_by_branches"] if development else [
        row for row in plan["resume_inventory"]["remaining_training_units"] if row["root"] == worker.removeprefix("collect-")]
    guard = owner.capture_evaluation_state()
    if not development:
        owner.begin_window(declaration["window_id"])
    rows, entries, terminal = [], [], "complete"
    for original_unit in units:
        if list((root / "mechanism-stops").glob("*.json")):
            terminal = "paused_before_next_slot"
            break
        unit = copy.deepcopy(original_unit)
        sid = unit.get("slot_id", unit.get("unit_id"))
        if development:
            sid += "-" + branch
        unit["slot_id"] = sid
        folder = output / "episodes" / sid
        task(output, sid + "-prepare", "boundary")
        prepared = original._new_prepared(unit, folder / "prepared")
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
            entries.append({"slot_id": sid, "active_members": list(prepared.case["active_roles"]),
                            "reward": {"value": row["R"], "eligible": False},
                            "scope": "Frozen collection close only; training materialization happens once at B admission"})
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
        write(output / "collection-close-slots.json", entries)
    return {"rows": rows, "status": terminal, "training_entries_materialization_deferred": not development, "state_loaded_for_collection": restored,
            "collection_guard": reference(output / "collection-guard.json")}


def _update(owner, plan, root, worker, output):
    from proworksim.software_learning_v049r1 import prepare_window, software_feature_function, update_software_window, bind_composition
    from proworksim.software_allocation_v049r1 import build_support_report, select_direction
    from scripts.software_allocation_v036 import training_progress

    branch = worker.removeprefix("update-")
    _restored_state(owner, root, "S0", output)
    declaration = read_json(checked(plan["declaration"]))
    entries = materialize_entries(plan, root) if branch == "B" else load_materialized_entries(plan, root)
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
            request_evidence_root=root / "source-registry.json", composition=composition, observe_support_gradients=branch == "B")
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
    original.inherited.validate_worker_interpreter(plan)
    if (worker not in WORKERS or worker == "s0" or output != root / worker / "actual"
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
        owner = original._load_owner(plan, output)
        if worker.startswith("collect-"):
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
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--original-root", type=Path)
    parser.add_argument("--controls", type=Path)
    parser.add_argument("--worker", choices=WORKERS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    if args.command == "prepare":
        if args.original_root is None or args.controls is None:
            parser.error("prepare requires --original-root and --controls")
        prepare(args.run_root, original_root=args.original_root, controls=args.controls)
    elif args.command == "supervise":
        from scripts.software_learning_resume_supervisor_v049r1 import supervise
        supervise(args.run_root)
    else:
        run_worker(args.run_root, args.worker, args.output)


if __name__ == "__main__":
    main()
