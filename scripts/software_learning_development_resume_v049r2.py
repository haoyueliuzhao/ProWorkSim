"""Continue only the two original unstarted B-development DB slots.

This host does not train, qualify, replay DA, or interpret an interrupted DA
result as zero. It restores the completed original B state for each new slot.
"""
from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import signal
import time

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import worker_identity
from proworksim.storage import digest, json_bytes, read_json
from scripts import software_learning_resume_v049r1 as previous
from scripts import software_learning_resume_supervisor_v049r1 as previous_supervisor
from scripts import software_learning_v049 as original
from scripts.run_ne_v021 import read, reference, write
from scripts.software_development_v028 import task

VERSION = "software-learning-original-B-development-resume-v0.49-r2"
SOURCE, GPU_ORDER = original.SOURCE, original.GPU_ORDER
WORKERS = ("dev-B-DB-s1", "dev-B-DB-s2")
LIMITS = copy.deepcopy(original.LIMITS)
PROTOCOL = SOURCE / "docs/experiments/software-learning-v049-development-resume-r2-protocol.md"
CONTROLS = SOURCE / "docs/experiments/software-learning-v049-development-resume-r2-cpu-controls.json"
STATE_PROOF = SOURCE / "docs/experiments/software-learning-v049-r1-evidence/S0-B-saved-state-comparison.json"
checked, _seal, _check_seal = original.checked, previous._seal, previous._check_seal


def source_files():
    files = original.source_files()
    for base in ("scripts", "tests"):
        for path in sorted((SOURCE / base).glob("*v049r2.py")):
            files[str(path.relative_to(SOURCE))] = digest(path.read_bytes())
    for path in (PROTOCOL, CONTROLS):
        files[str(path.relative_to(SOURCE))] = digest(path.read_bytes())
    return files


def _terminal_supervisor(root, plan):
    value = read_json(root / "supervisor.json")
    if (value.get("status") != "closed_with_unknowns" or not value.get("ended_at")
            or value.get("source") != plan["source"] or set(value.get("states", {})) != set(previous.WORKERS)):
        raise ValueError("The original r1 supervisor must be terminal with its original unknowns")
    for state in value["states"].values():
        if state.get("status") not in {"complete", "stopped", "not_applicable"}:
            raise ValueError("An original worker is still in flight")
        if state.get("pid"):
            live = worker_identity(state["pid"])
            saved = state.get("process_identity", {})
            if live.get("alive") and live.get("start_ticks") == saved.get("start_ticks"):
                raise ValueError("An original worker process remains alive")
    for name in ("collect-LA", "collect-LB", "update-B"):
        state = value["states"][name]
        report = read_json(root / name / "actual/report.json")
        if (state.get("status") != "complete" or state.get("exit_code") != 0 or not state.get("ended_at")
                or report.get("status") != "complete" or report.get("success_boundary") is not True
                or report.get("source_before") != report.get("source_after") or report.get("source_after") != plan["source"]):
            raise ValueError("Original collection/B requires a complete clean worker boundary")
    dev = value["states"]["dev-B"]
    if dev.get("status") != "stopped" or dev.get("attempted") is not True or not dev.get("ended_at") or dev.get("exit_code") in (None, 0):
        raise ValueError("The original interrupted B-development boundary must remain explicit")
    return value


def _bind_state_proof(path, root, plan, s0, checkpoint, direction):
    proof = read_json(path)
    branch = proof.get("branches", {}).get("B", {})
    binding = branch.get("completed_source_binding", {})
    if (proof.get("run_root") != str(root) or branch.get("status") != "complete"
            or proof.get("direction") != direction or branch.get("all_saved_state_top_level_fields_compared") is not True
            or branch.get("step_differences_match_native_report") is not True
            or binding.get("frozen_source") != plan["source"]
            or binding.get("update_report") != direction["B_update"]
            or any(binding.get(key) is not True for key in (
                "worker_checkpoint_equals_saved_checkpoint", "source_before_and_after_match_frozen_plan", "original_S0_restore_digest_matches"))
            or any(proof.get(key) != 0 for key in (
                "actor_or_critic_models_loaded", "new_forward_calls", "new_backward_calls", "new_optimizer_steps", "GPU_API_calls"))):
        raise ValueError("The independent complete-state CPU proof is not bound to original B")
    for receipt, expected, checkpoint_path in (
        (proof["S0"], read_json(checked(s0["checkpoint_ref"])), s0["checkpoint_ref"]["path"]),
        (branch["checkpoint"], checkpoint, str(root / "update-B/actual/checkpoint/checkpoint.json"))):
        if (receipt.get("checkpoint") != checkpoint_path or receipt.get("state") != expected["state"]
                or receipt.get("state_tensor_digest") != expected["state_tensor_digest"]
                or receipt.get("serialized_reload_exact") is not True or receipt.get("loaded_map_location") != "cpu"):
            raise ValueError("CPU proof checkpoint identity changed")
    for name in ("Q_plus", "Q_minus"):
        if proof["branches"].get(name, {}).get("status") != "not_applicable":
            raise ValueError("Q branches remain not applicable")
    return reference(path)


def derive_inventory(original_root, *, state_proof=STATE_PROOF, source_root=SOURCE, check_source=True):
    """Read receipts only; no model/tokenizer/world/acceptance or tensor load."""
    root = Path(original_root).resolve()
    plan = read_json(root / "plan.json")
    _check_seal(plan, "plan_sha256")
    if plan.get("version") != previous.VERSION or plan.get("workers") != list(previous.WORKERS) or plan.get("limits") != LIMITS:
        raise ValueError("Require the exact original r1 learning plan and resource policy")
    original_plan = read_json(checked(plan["resume_of"]))
    _check_seal(original_plan, "plan_sha256")
    design = read_json(checked(plan["design"]))
    if plan["inventory"] != original_plan["inventory"] or plan["inventory"] != design:
        raise ValueError("The original scientific inventory and design cannot change")
    states = _terminal_supervisor(root, plan)
    s0, declaration = (read_json(checked(plan[key])) for key in ("s0", "declaration"))
    s0_checkpoint = read_json(checked(s0["checkpoint_ref"]))
    if (declaration.get("gamma_identity", {}).get("s0") != s0
            or declaration.get("actor_identity") != s0.get("actor_identity")
            or (s0_checkpoint.get("actor_steps"), s0_checkpoint.get("critic_steps")) != (3, 3)
            or s0_checkpoint.get("state_tensor_digest") != s0.get("state_tensor_digest")):
        raise ValueError("Original complete S0/declaration binding changed")
    # Reuse the one sealed training materialization, not the original exporter.
    material = read_json(root / "materialization.json")
    _check_seal(material, "sha256")
    registry = read_json(checked(material["source_registry"]))
    _check_seal(registry, "sha256")
    checked(material["entries"])
    training_ids = [unit["slot_id"] for unit in design["training_slots"]]
    if (material.get("passed") is not True or material.get("original_slots_once_each") != 8
            or len(set(training_ids)) != 8 or [row["slot_id"] for row in registry["slots"]] != training_ids
            or [row["slot_id"] for row in material["slots"]] != training_ids
            or registry.get("declaration") != plan["declaration"]):
        raise ValueError("Exactly eight original closed training sources are required")
    for row in registry["slots"]:
        result = read_json(checked(row["source_result"]))
        if result.get("status") != "closed" or type(result.get("R")) is not int or result["R"] not in (0, 1):
            raise ValueError("An original training slot is not formally closed")
    direction = previous_supervisor.read_direction(root, states["states"], plan)
    _check_seal(direction["direction"], "seal_sha256")
    if (direction["selected"] is not False or direction["reliable_base_material"] is not True
            or direction["direction"].get("selected") is not None
            or direction["direction"].get("design_sha256") != plan["design"]["sha256"]
            or direction["direction"].get("declaration_sha256") != digest(json_bytes(declaration))):
        raise ValueError("Only original B with no admissible I direction may continue")
    for name in ("update-Q_plus", "update-Q_minus", "dev-Q_plus", "dev-Q_minus"):
        if (states["states"][name].get("status") != "not_applicable"
                or states["states"][name].get("attempted") is not False or (root / name / "actual").exists()):
            raise ValueError("Original Q inventory must remain unattempted and not applicable")
    b_report = read_json(root / "update-B/actual/report.json")
    update = read_json(checked(b_report["update_report"]))
    checkpoint_path = root / "update-B/actual/checkpoint/checkpoint.json"
    checkpoint = read_json(checkpoint_path)
    # This verifies file bytes; it does not deserialize tensors or rerun CPU state comparison.
    checked(checkpoint["state"])
    if (b_report.get("checkpoint") != checkpoint or checkpoint.get("serialized_reload_exact") is not True
            or (checkpoint.get("actor_steps"), checkpoint.get("critic_steps")) != (4, 4)
            or b_report.get("final_actor_identity") != checkpoint["actor_identity"]
            or update.get("status") != "updated" or update.get("stage") != "complete"
            or update.get("actor_optimizer_steps") != 1 or update.get("critic_optimizer_steps") != 1
            or update.get("backward_decisions_completed") != 206 or update.get("scheduled_slots") != 8
            or update.get("before_actor_identity") != s0["actor_identity"]):
        raise ValueError("Require original completed B H1 and its complete saved 4/4 state")
    proof = _bind_state_proof(Path(state_proof).resolve(), root, plan, s0, checkpoint, direction)
    units = design["development_units_shared_by_branches"]
    expected_ids = ["org49-dev-DA-s1", "org49-dev-DA-s2", "org49-dev-DB-s1", "org49-dev-DB-s2"]
    if [unit["unit_id"] for unit in units] != expected_ids:
        raise ValueError("Preserve the original four development units and order")
    episodes = root / "dev-B/actual/episodes"
    if {path.name for path in episodes.iterdir()} != {name + "-B" for name in expected_ids[:2]}:
        raise ValueError("Only the original two DA directories may already exist; DB must be truly unopened")
    retained = []
    for index, unit in enumerate(units):
        if unit.get("purpose") != "policy_development" or unit.get("generation_token_cap") != 500000:
            raise ValueError("Original per-slot development scope changed")
        if index >= 2:
            continue
        sid = unit["unit_id"] + "-B"
        folder = episodes / sid
        manifest = read_json(folder / "episode/manifest.json")
        scope = manifest.get("scenario", {}).get("variation", {}).get("organization_runtime", {})
        if manifest.get("source_start") != plan["source"] or scope.get("slot_id") != sid or scope.get("case") != original._case(unit):
            raise ValueError("Original started development slot binding changed")
        result_path = folder / "slot-result.json"
        result = read_json(result_path) if result_path.exists() else None
        if index == 0 and (result is None or result.get("status") != "closed" or type(result.get("R")) is not int
                or result["R"] not in (0, 1) or result.get("actor_identity") != checkpoint["actor_identity"]):
            raise ValueError("Original DA-s1 must remain exactly closed")
        if index == 1 and (result is not None or not (folder / "interruption.json").is_file()):
            raise ValueError("Original DA-s2 interruption/unknown must remain, without synthetic closure")
        retained.append({"slot_id": sid, "original_unit": copy.deepcopy(unit),
            "status": "closed" if result else "technical_unknown", "R": result["R"] if result else None,
            "complete_usage": result["usage"] if result else None,
            "source_receipts": {name: reference(folder / name) for name in (
                "episode/manifest.json", "slot-result.json", "mechanical-measurement.json",
                "interruption.json", "team-budget.json", "runtime-state.json") if (folder / name).is_file()},
            "replayed_or_restarted": False})
    return {"version": VERSION, "original_root": str(root), "original_plan": reference(root / "plan.json"),
        "original_supervisor": reference(root / "supervisor.json"), "s0": plan["s0"], "declaration": plan["declaration"],
        "B_checkpoint": reference(checkpoint_path), "B_state": checkpoint["state"],
        "B_worker": reference(root / "update-B/actual/report.json"), "B_update": b_report["update_report"],
        "state_proof": proof, "direction": reference(root / "direction.json"),
        "materialization": reference(root / "materialization.json"),
        "retained_development": retained, "remaining_development_units": copy.deepcopy(units[2:]),
        "original_stops": [reference(path) for path in sorted((root / "mechanism-stops").glob("*.json"))],
        "source_agreement": previous.original_source_agreement(plan, source_root) if check_source else None,
        "original_F_B": None, "unknown_DA_s2_preserved": True,
        "replayed_slots": [], "new_seeds": [], "old_unspent_budget_transferred": 0,
        "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_calls": 0}


def budget_caps():
    return {"new_generation_slots_max": 2, "new_actual_generation_tokens_max": 1000000,
        "new_decisions_max": 256, "new_attempts_max": 256, "new_member_tests_max": 64,
        "per_slot_tokens": 500000, "per_slot_decisions": 128, "per_slot_attempts": 128, "per_slot_member_tests": 32,
        "old_unspent_budget_transferred": 0, "new_actor_steps": 0, "new_critic_steps": 0,
        "new_backward_calls": 0, "new_model_qualification_calls": 0}


def prepare(root, *, original_root, controls, state_proof=STATE_PROOF):
    root, old = Path(root).resolve(), Path(original_root).resolve()
    if root.exists() or root == old or root in old.parents or old in root.parents:
        raise FileExistsError("Continuation needs a new independent root")
    source = code_identity()
    if source.get("code_dirty") is not False:
        raise ValueError("Commit isolated r2 host/protocol before model work")
    controls = Path(controls).resolve()
    proof = read_json(controls)
    _check_seal(proof, "sha256")
    if (proof.get("passed") is not True or proof.get("new_model_calls") != 0 or proof.get("new_gpu_workers") != 0
            or proof.get("original_plan") != reference(old / "plan.json")
            or proof.get("state_proof") != reference(state_proof)):
        raise ValueError("Finite CPU controls must bind the original plan and independent state proof")
    inventory = derive_inventory(old, state_proof=state_proof)
    parent = read_json(checked(inventory["original_plan"]))
    plan = {**copy.deepcopy(parent), "version": VERSION, "created_at": time.time(), "source": source,
        "source_root": str(SOURCE), "source_files": source_files(), "resume_of": inventory["original_plan"],
        "original_root": str(old), "resume_inventory": inventory, "workers": list(WORKERS),
        "new_budget_caps": budget_caps(), "resume_cpu_controls": reference(controls),
        "prior_artifact_roots": original.inherited.support.dense._artifact_roots([*parent["prior_artifact_roots"], old]),
        "scope": "Only the two original unstarted DB B-development slots, each in a new world from original complete B. No training, replay, qualification, new seed or automatic successor.",
        "automatic_retries": False, "automatic_successors": [], "old_queues_remain_paused": True}
    plan.pop("plan_sha256", None)
    plan = _seal(plan, "plan_sha256")
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    plan = read_json(Path(root) / "plan.json")
    _check_seal(plan, "plan_sha256")
    if (plan.get("version") != VERSION or plan.get("source") != code_identity()
            or plan.get("source_files") != source_files() or plan.get("workers") != list(WORKERS)
            or plan.get("limits") != LIMITS or plan.get("gpu_preference") != list(GPU_ORDER)
            or plan.get("new_budget_caps") != budget_caps() or plan.get("automatic_retries") is not False
            or plan.get("automatic_successors") != []):
        raise ValueError("Frozen r2 host/dependencies/budget changed")
    derived = derive_inventory(plan["original_root"], state_proof=checked(plan["resume_inventory"]["state_proof"]))
    if derived != plan["resume_inventory"]:
        raise ValueError("Original B, inventory, stops or unknown evidence changed")
    parent = read_json(checked(plan["resume_of"]))
    for key in ("inventory", "design", "declaration", "s0", "mapper_specification", "source_partition",
                "task_source_manifest", "training_reward", "development_F", "common", "model_references"):
        if plan[key] != parent[key]:
            raise ValueError("Original scientific or numerical contract changed: " + key)
    checked(plan["resume_cpu_controls"])
    return plan


def restore_B(owner, plan, output):
    checkpoint_path = checked(plan["resume_inventory"]["B_checkpoint"])
    expected = read_json(checkpoint_path)
    task(output, "restore-original-complete-B-before-any-evaluation", "boundary")
    restored = owner.restore_checkpoint(checkpoint_path.parent)
    if (restored != expected or owner.freeze_identity() != expected["actor_identity"]
            or (owner.actor_steps, owner.critic_steps) != (4, 4)):
        raise ValueError("Evaluation must load the original full B state, never S0/common")
    write(Path(output) / "loaded-state.json", {"branch": "B", "checkpoint": reference(checkpoint_path),
        "restored": restored, "actor_identity": owner.freeze_identity(),
        "actor_steps": owner.actor_steps, "critic_steps": owner.critic_steps,
        "original_B_reused_without_update": True})
    return restored


def collect_development(owner, plan, root, worker, output):
    from proworksim.software_organization_runtime_v049 import collect_episode
    from proworksim.software_organization_measurement_v049 import measure_slot
    if worker not in WORKERS:
        raise ValueError("No collection/update/DA/Q worker is authorized in r2")
    restored = restore_B(owner, plan, output)
    guard = owner.capture_evaluation_state()
    unit = copy.deepcopy(plan["resume_inventory"]["remaining_development_units"][WORKERS.index(worker)])
    unit["slot_id"] = unit["unit_id"] + "-B"
    sid, folder = unit["slot_id"], Path(output) / "episodes" / unit["slot_id"]
    rows, terminal = [], "paused_before_next_slot"
    if not list((Path(root) / "mechanism-stops").glob("*.json")):
        declaration = read_json(checked(plan["declaration"]))
        task(output, sid + "-prepare", "boundary")
        prepared = original._new_prepared(unit, folder / "prepared")
        task(output, sid, "episode")
        row = collect_episode(owner, prepared, folder, sampling_seed=unit["sampling_seed"], slot_id=sid,
            manage_owner_window=True, learning_binding={"branch": "B",
                "loaded_checkpoint_state_digest": restored["state_tensor_digest"],
                "declaration_sha256": digest(json_bytes(declaration)), "design_sha256": plan["design"]["sha256"]})
        task(output, sid + "-evidence", "boundary")
        measurement = measure_slot(row, folder / "mechanical-measurement.json")
        rows.append({**unit, **row, "mechanical_measurement": reference(folder / "mechanical-measurement.json")})
        write(Path(output) / "progress.json", rows)
        terminal = "complete" if measurement["decision"] == "continue" else measurement["decision"]
        if terminal != "complete":
            write(Path(root) / "mechanism-stops" / (sid + ".json"), {"kind": terminal,
                "worker": worker, "slot_id": sid, "measurement": reference(folder / "mechanical-measurement.json")})
    final_guard = owner.finish_evaluation_guard(guard)
    write(Path(output) / "collection-guard.json", final_guard)
    if (final_guard.get("learning_unchanged") is not True or final_guard.get("rng_restored_exactly") is not True
            or owner.freeze_identity() != restored["actor_identity"] or (owner.actor_steps, owner.critic_steps) != (4, 4)):
        raise ValueError("Development changed the original B learning state")
    return {"rows": rows, "status": terminal, "state_loaded_for_collection": restored,
        "collection_guard": reference(Path(output) / "collection-guard.json")}


def received_signal(signum, frame):
    # Observation only: this does not identify who sent the signal.
    raise KeyboardInterrupt(f"signal {signum}")


def run_worker(root, worker, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    plan = frozen(root)
    original.inherited.validate_worker_interpreter(plan)
    if (worker not in WORKERS or output != root / worker / "actual"
            or os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, GPU_ORDER))):
        raise ValueError("Require an original DB worker, exact output and one authorized GPU")
    own = (read(root / "supervisor.json") or {}).get("states", {}).get(worker, {})
    if own.get("status") not in {"not_started", "running"} or own.get("attempted") is not True:
        raise ValueError("Require a fresh supervisor-owned worker launch")
    output.mkdir(parents=True, exist_ok=False)
    owner = None
    report = {"version": VERSION, "worker": worker, "status": "loading", "started_at": time.time(),
        "source_before": code_identity(), "success_boundary": False, "new_actor_steps": 0,
        "new_critic_steps": 0, "new_backward_calls": 0}
    write(output / "report.json", report)
    try:
        owner = original._load_owner(plan, output)
        result = collect_development(owner, plan, root, worker, output)
        report.update(result)
        report["success_boundary"] = report["status"] == "complete"
    except BaseException as error:
        report.update(status="execution_error", error={"type": type(error).__name__, "message": str(error)})
        if isinstance(error, KeyboardInterrupt) and str(error).startswith("signal "):
            report["signal_observation"] = {"message": str(error), "observed_at": time.time(), "sender": None,
                "scope": "Worker observed a signal; inspect separate host stop-actions for any host-issued stop."}
        write(root / "mechanism-stops" / (worker + "-execution.json"), {"kind": "execution_fault",
            "worker": worker, "error": report["error"], "observed_at": time.time()})
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
    parser.add_argument("--state-proof", type=Path, default=STATE_PROOF)
    parser.add_argument("--worker", choices=WORKERS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, received_signal)
    if args.command == "prepare":
        if args.original_root is None or args.controls is None:
            parser.error("prepare requires --original-root and --controls")
        prepare(args.run_root, original_root=args.original_root, controls=args.controls, state_proof=args.state_proof)
    elif args.command == "supervise":
        from scripts.software_learning_development_resume_supervisor_v049r2 import supervise
        supervise(args.run_root)
    else:
        if args.worker is None or args.output is None:
            parser.error("worker requires --worker and --output")
        run_worker(args.run_root, args.worker, args.output)


if __name__ == "__main__":
    main()
