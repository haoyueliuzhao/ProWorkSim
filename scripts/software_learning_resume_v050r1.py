"""Continue only the 23 unstarted v050 slots after a source-seal export repair.

The original closed slot, declaration, S*4/4, scientific inventory and every
pre-existing dependency remain immutable. Only export provenance and host source
selection differ; the inherited numerical update and resource guards are reused.
"""
from __future__ import annotations

import argparse
import ast
import copy
import inspect
from pathlib import Path
import signal
import time

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import worker_identity
from proworksim.storage import digest, json_bytes, read_json
from scripts import software_learning_v050 as original
from scripts.software_learning_development_resume_v049r2g import bind
from scripts.software_learning_resume_v049r1 import original_source_agreement
from scripts.run_ne_v021 import reference, write

VERSION = "software-learning-original-inventory-resume-v0.50-r1"
MODULE = "scripts.software_learning_resume_v050r1"
SOURCE, DESIGN = original.SOURCE, original.DESIGN
GPU_ORDER, WORKERS = original.GPU_ORDER, original.WORKERS
COLLECTION, UPDATES, DEVELOPMENT = original.COLLECTION, original.UPDATES, original.DEVELOPMENT
BRANCHES, LIMITS = original.BRANCHES, copy.deepcopy(original.LIMITS)
PROTOCOL = SOURCE / "docs/experiments/software-learning-v050-resume-r1-protocol.md"
CONTROLS = SOURCE / "docs/experiments/software-learning-v050-resume-r1-cpu-controls.json"
FIRST_SLOT = "org50-train-LA-r01"
checked, seal, check_seal = original.checked, original.seal, original.check_seal
validate_inventory = original.validate_inventory


def source_files():
    files = original.source_files()
    for path in (PROTOCOL, CONTROLS):
        files[str(path.relative_to(SOURCE))] = digest(path.read_bytes())
    return files


def _episode_folder(root, worker, sid):
    return Path(root) / worker / "actual/episodes" / sid


def _dead_original_processes(supervisor):
    """A reused PID belonging to another process is not the old experiment."""
    for state in supervisor["states"].values():
        if not state.get("attempted"):
            continue
        observed = worker_identity(state["pid"])
        if (observed.get("alive") is not False
                and observed.get("start_ticks") == state.get("process_identity", {}).get("start_ticks")):
            raise ValueError("An original worker is still alive")


def bind_retained_slot(folder, unit, parent, declaration):
    folder = Path(folder).resolve()
    row = read_json(folder / "slot-result.json")
    manifest = read_json(folder / "episode/manifest.json")
    measurement = read_json(folder / "mechanical-measurement.json")
    guard = read_json(folder / "evaluation-guard.json")
    runtime = manifest.get("scenario", {}).get("variation", {}).get("organization_runtime", {})
    usage, model = row.get("usage", {}), row.get("team_budget", {}).get("model", {})
    deadline = row.get("deadline_receipt", {})
    records, dispatches = model.get("records", {}), deadline.get("dispatches", {})
    if (row.get("status") != "closed" or type(row.get("R")) is not int or row["R"] not in (0, 1)
            or row.get("R_joint") != row["R"] or manifest.get("status") != "closed"
            or manifest.get("source_start") != parent["source"] or manifest.get("source_end") != parent["source"]
            or measurement.get("decision") != "continue" or row.get("version") != "software-organization-runtime-v0.50"
            or row.get("slot_id") != unit["slot_id"] or row.get("sampling_seed") != unit["sampling_seed"]
            or row.get("first_member") != unit["first_member"] or row.get("purpose") != "policy_training"
            or row.get("condition") != "O1" or row.get("training_eligible") is not True
            or row.get("online_window_id") != declaration["window_id"]
            or row.get("actor_identity") != declaration["actor_identity"]
            or runtime.get("slot_id") != unit["slot_id"] or runtime.get("actor_identity") != declaration["actor_identity"]
            or runtime.get("version") != "software-organization-runtime-v0.50"
            or row.get("episode_manifest") != str(folder / "episode/manifest.json")
            or any(row.get(key) != 0 for key in ("actor_updates", "critic_updates", "new_backward_calls"))
            or row.get("usage", {}).get("uncertain_usage_attempts") != 0
            or model.get("held_tokens") != 0 or model.get("integrity_failure") is not None
            or model.get("charged_tokens") != usage.get("total_tokens")
            or usage.get("budget_charged_tokens") != usage.get("total_tokens")
            or len(records) != usage.get("attempts") or set(records) != set(dispatches)
            or any(record.get("status") != "settled" for record in records.values())
            or any(record.get("status") != "returned" for record in dispatches.values())
            or any(deadline.get(key) is not True for key in
                   ("all_dispatched_attempts_settled", "unique_final_acceptance", "closed_before_hard_deadline"))
            or deadline.get("final_assessment_calls") != 1
            or any(guard.get(key) is not True for key in
                   ("learning_unchanged", "rng_restored_exactly", "software_binding_unchanged", "actor_identity_unchanged"))):
        raise ValueError("The original started slot must remain safely closed and source-bound")
    return {"slot_id": unit["slot_id"], "original_unit": copy.deepcopy(unit), "worker": "collect-0",
        "episode_folder": str(folder), "original_formal_R": row["R"], "original_formal_Q": row["Q_joint"],
        "actual_usage": copy.deepcopy(row["usage"]), "actual_member_tests": row["team_budget"]["tests"]["used"],
        **{key: reference(folder / name) for key, name in {
            "source_result": "slot-result.json", "source_manifest": "episode/manifest.json",
            "source_guard": "evaluation-guard.json", "source_measurement": "mechanical-measurement.json"}.items()}}


def derive_inventory(original_root, *, source_root=SOURCE, check_source=True, check_processes=True):
    root = Path(original_root).resolve()
    parent = check_seal(read_json(root / "plan.json"), "plan_sha256")
    supervisor = read_json(root / "supervisor.json")
    if (parent.get("version") != original.VERSION or parent.get("workers") != list(WORKERS)
            or parent.get("limits") != LIMITS or parent.get("gpu_preference") != list(GPU_ORDER)
            or supervisor.get("status") != "closed_with_unknowns" or not supervisor.get("ended_at")
            or supervisor.get("source") != parent["source"] or set(supervisor.get("states", {})) != set(WORKERS)):
        raise ValueError("Require the terminal original v050 inventory, with its old stopping record preserved")
    validate_inventory(parent["inventory"])
    states = supervisor["states"]
    if any(state.get("status") not in {"complete", "stopped"} for state in states.values()):
        raise ValueError("Original work must be terminal before deriving a continuation")
    if check_processes:
        _dead_original_processes(supervisor)
    for name, state in states.items():
        if name not in {"s_star", "collect-0"}:
            if state.get("attempted") is not False or (root / name).exists():
                raise ValueError("Another attempted or prepared original worker cannot be replayed")
            continue
        report = read_json(root / name / "actual/report.json")
        if (state.get("attempted") is not True or not state.get("ended_at")
                or report.get("source_before") != report.get("source_after") or report.get("source_after") != parent["source"]
                or any(report.get(key) != 0 for key in ("new_actor_steps", "new_critic_steps"))):
            raise ValueError("Original init/collector source or update boundary is unknown")
        if name == "s_star":
            if state.get("exit_code") != 0 or report.get("status") != "complete" or report.get("success_boundary") is not True:
                raise ValueError("Reuse only the completed original S* declaration")
        elif (state.get("exit_code") != 1 or report.get("status") != "execution_error"
              or report.get("error") != {"type": "ValueError", "message": "Original v049 export evidence seal differs"}):
            raise ValueError("This repair is limited to the observed post-closure export seal failure")
        if (report.get("actor_steps"), report.get("critic_steps")) != (4, 4):
            raise ValueError("Original init and collection must end at the unchanged complete 4/4 state")
    declaration, star = read_json(root / "declaration.json"), read_json(root / "s_star.json")
    checkpoint = read_json(checked(parent["s_star_checkpoint"]))
    loaded = read_json(root / "collect-0/actual/loaded-state.json")
    # State bytes are checked by the original loader; no extra tensor load or GPU init here.
    if (declaration.get("gamma_identity", {}).get("s_star") != star
            or declaration.get("actor_identity") != star.get("actor_identity")
            or star.get("checkpoint_ref", {}).get("sha256") != parent["s_star_checkpoint"]["sha256"]
            or checkpoint.get("state_tensor_digest") != star.get("state_tensor_digest")
            or loaded.get("restored") != checkpoint or loaded.get("branch") != "S_star"
            or loaded.get("actor_identity") != declaration.get("actor_identity")
            or (loaded.get("actor_steps"), loaded.get("critic_steps")) != (4, 4)
            or (checkpoint.get("actor_steps"), checkpoint.get("critic_steps")) != (4, 4)
            or [u["slot_id"] for u in declaration["slots"]] != [u["slot_id"] for u in parent["inventory"]["training_slots"]]):
        raise ValueError("Original declaration, full 24-slot measure and S*4/4 must match exactly")
    binding = check_seal(read_json(root / "precollection-binding.json"))
    if binding["declaration"] != reference(root / "declaration.json") or binding["s_star"] != reference(root / "s_star.json"):
        raise ValueError("Original precollection binding changed")
    expected = _episode_folder(root, "collect-0", FIRST_SLOT)
    observed = {p.resolve() for worker in COLLECTION for p in (root / worker / "actual/episodes").glob("*") if p.is_dir()}
    if observed != {expected.resolve()}:
        raise ValueError("Exactly one original training slot started; never replay another prepared slot")
    units = parent["inventory"]["training_slots"]
    retained = bind_retained_slot(expected, units[0], parent, declaration)
    usage = {**retained["actual_usage"], "member_tests": retained["actual_member_tests"],
        "worker_gpu_seconds_including_original_S_star": sum(s.get("elapsed_gpu_seconds", 0) for s in states.values())}
    return {"version": VERSION, "original_root": str(root), "original_plan": reference(root / "plan.json"),
        "original_supervisor": reference(root / "supervisor.json"), "original_declaration": reference(root / "declaration.json"),
        "original_s_star": reference(root / "s_star.json"), "original_precollection_binding": reference(root / "precollection-binding.json"),
        "retained_slots": [retained], "remaining_training_units": copy.deepcopy(units[1:]),
        "retained_actual_cost": usage, "old_unspent_token_budget_not_transferred": 500000 - usage["total_tokens"],
        "original_stops": [reference(p) for p in sorted((root / "mechanism-stops").glob("*.json"))],
        "source_agreement": original_source_agreement(parent, source_root) if check_source else None,
        "original_artifacts": [reference(p) for p in sorted(root.rglob("*")) if p.is_file()],
        "old_results_or_stops_rewritten": False, "replayed_slots": [], "new_seeds": []}


def budget_caps(derived):
    old = derived["retained_actual_cost"]
    return {"new_training_slots": 23, "conditional_development_slots_max": 32,
        "new_generation_slots_max": 55, "new_actual_generation_tokens_max": 27500000,
        "new_decisions_max": 7040, "new_attempts_max": 7040, "new_member_tests_max": 1760,
        "including_retained_actual_tokens_upper": old["total_tokens"] + 27500000,
        "including_retained_actual_decisions_upper": old["decisions"] + 7040,
        "including_retained_actual_attempts_upper": old["attempts"] + 7040,
        "including_retained_actual_tests_upper": old["member_tests"] + 1760,
        "old_unspent_tokens_not_transferred": derived["old_unspent_token_budget_not_transferred"],
        "old_actual_cost_counted_once": True, "new_S_star_initialization_workers": 0,
        "new_model_qualification_calls": 0, "new_seeds_or_samples": 0,
        "original_design_generation_slots_max": 56, "original_global_member_denominator_factor": 48}


def worker_units(plan, worker):
    units = original.worker_units(plan, worker)
    return [u for u in units if u["slot_id"] != FIRST_SLOT] if worker in COLLECTION else units


def validate_retained_export(refs, derived, declaration):
    retained = derived["retained_slots"][0]
    folder = Path(retained["episode_folder"])
    entry = read_json(checked(refs["training-entry.json"]))
    receipt = read_json(checked(refs["rematerialization-receipt.json"]))
    checked(refs["training-export.json"])
    unchanged = receipt.get("source_files_unchanged", {})
    invariants = receipt.get("original_observation_target_reward_invariants", {})
    if (entry.get("slot_id") != FIRST_SLOT or receipt.get("slot_id") != FIRST_SLOT
            or Path(receipt.get("source_folder", "")).resolve() != folder
            or Path((entry.get("rollout") or {}).get("episode_path", "")).resolve() != folder / "episode"
            or entry["rollout"].get("manifest_sha256") != retained["source_manifest"]["sha256"]
            or receipt.get("declaration_sha256") != digest(json_bytes(declaration))
            or receipt.get("formal_R") != retained["original_formal_R"]
            or receipt.get("reported_original_usage") != retained["actual_usage"]
            or not unchanged or not all(value is True for value in unchanged.values())
            or not all(value is True for value in invariants.values())
            or (not invariants and (receipt.get("old_entry_json_effect_equal") is not None
                                    or (folder / "training-entry.json").exists()))
            or any(receipt.get(key) != 0 for key in ("new_model_calls", "new_tokenizer_calls", "new_gpu_calls",
                "new_business_tests_or_acceptances", "new_world_actions"))):
        raise ValueError("The sole retained-slot export must bind unchanged original targets, result and cost")
    return entry


def prepare(root, *, original_root, controls=CONTROLS):
    root, old = Path(root).resolve(), Path(original_root).resolve()
    if root.exists() or root in old.parents or old in root.parents:
        raise FileExistsError("Use a new independent continuation root")
    source = code_identity()
    if source.get("code_dirty") is not False:
        raise ValueError("Commit the isolated repair, controls and protocol before any worker")
    proof = check_seal(read_json(controls))
    if (proof.get("passed") is not True or any(proof.get(k) != 0 for k in
            ("new_model_calls", "new_gpu_workers", "new_backward_calls"))):
        raise ValueError("Finite CPU repair controls must pass with no model work")
    derived = derive_inventory(old)
    parent = read_json(checked(derived["original_plan"]))
    reexport = proof["original_first_rematerialized"]
    validate_retained_export(reexport, derived, read_json(old / "declaration.json"))
    plan = copy.deepcopy(parent)
    plan.update(version=VERSION, source=source, created_at=time.time(), source_files=source_files(),
        original_root=str(old), resume_of=derived["original_plan"], resume_inventory=derived,
        resume_cpu_controls=reference(controls), resume_protocol=reference(PROTOCOL),
        new_budget_caps=budget_caps(derived), original_S_star_reused_without_new_worker=True,
        prior_artifact_roots=original.original.inherited.support.dense._artifact_roots([*parent["prior_artifact_roots"], old]))
    plan.pop("plan_sha256")
    root.mkdir(parents=True, exist_ok=False)
    # Copy the exact original declaration/state-binding bytes, never regenerate them.
    for name in ("declaration.json", "s_star.json", "precollection-binding.json"):
        (root / name).write_bytes((old / name).read_bytes())
    destination = root / "retained" / FIRST_SLOT
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("training-entry.json", "training-export.json", "rematerialization-receipt.json"):
        (destination / name).write_bytes(checked(reexport[name]).read_bytes())
    plan["retained_export_cpu_origin"] = copy.deepcopy(reexport)
    plan["retained_export"] = {name: reference(destination / name) for name in
        ("training-entry.json", "training-export.json", "rematerialization-receipt.json")}
    plan = seal(plan, "plan_sha256")
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    root = Path(root).resolve()
    plan = check_seal(read_json(root / "plan.json"), "plan_sha256")
    if (plan.get("version") != VERSION or plan.get("source") != code_identity()
            or plan.get("source_files") != source_files() or plan.get("limits") != LIMITS
            or plan.get("workers") != list(WORKERS) or plan.get("gpu_preference") != list(GPU_ORDER)):
        raise ValueError("Frozen v050r1 implementation or resources changed")
    derived = derive_inventory(plan["original_root"])
    if derived != plan["resume_inventory"] or budget_caps(derived) != plan["new_budget_caps"]:
        raise ValueError("Original evidence, unique inventory or remaining budget changed")
    parent = read_json(checked(plan["resume_of"]))
    changed = {"version", "source", "created_at", "source_files", "original_root", "resume_of", "resume_inventory",
        "resume_cpu_controls", "resume_protocol", "new_budget_caps", "original_S_star_reused_without_new_worker",
        "prior_artifact_roots", "retained_export", "retained_export_cpu_origin", "plan_sha256"}
    if {k: v for k, v in plan.items() if k not in changed} != {k: v for k, v in parent.items() if k not in changed}:
        raise ValueError("Resume cannot alter the original scientific protocol or generation/training budgets")
    for name, key in (("declaration.json", "original_declaration"), ("s_star.json", "original_s_star"),
                      ("precollection-binding.json", "original_precollection_binding")):
        if (root / name).read_bytes() != checked(derived[key]).read_bytes():
            raise ValueError("An exact reused declaration/state binding changed")
    checked(plan["resume_cpu_controls"])
    if plan["resume_protocol"] != reference(PROTOCOL):
        raise ValueError("Continuation protocol changed")
    for name, value in plan["retained_export"].items():
        if checked(value).read_bytes() != checked(plan["retained_export_cpu_origin"][name]).read_bytes():
            raise ValueError("The sole CPU rematerialization cannot be replaced or repeated")
    validate_retained_export(plan["retained_export"], derived, read_json(root / "declaration.json"))
    return plan


def materialize_entries(plan, root):
    root = Path(root).resolve()
    retained = plan["resume_inventory"]["retained_slots"][0]
    first_path = checked(plan["retained_export"]["training-entry.json"])
    first = read_json(first_path)
    if first["slot_id"] != FIRST_SLOT:
        raise ValueError("Retained entry is not the original first slot")
    by_slot = {FIRST_SLOT: first}
    sources = [{"slot_id": FIRST_SLOT, "entry": reference(first_path),
        "source_result": retained["source_result"], "source_manifest": retained["source_manifest"]}]
    for worker in COLLECTION:
        rows = read_json(root / worker / "actual/entries.json")
        if [r["slot_id"] for r in rows] != [u["slot_id"] for u in worker_units(plan, worker)]:
            raise ValueError("Each resumed collector must supply exactly its own unstarted original shard")
        for entry in rows:
            sid = entry["slot_id"]
            folder = _episode_folder(root, worker, sid)
            if sid in by_slot or entry != read_json(folder / "training-entry.json"):
                raise ValueError("Duplicate or altered resumed entry")
            by_slot[sid] = entry
            sources.append({"slot_id": sid, "entry": reference(folder / "training-entry.json"),
                "source_result": reference(folder / "slot-result.json"), "source_manifest": reference(folder / "episode/manifest.json")})
    order = [u["slot_id"] for u in plan["inventory"]["training_slots"]]
    if len(by_slot) != 24 or set(by_slot) != set(order):
        raise ValueError("Exactly one retained plus 23 new entries must fill the original 24 slots")
    sources.sort(key=lambda s: order.index(s["slot_id"]))
    for item in sources:
        folder = checked(item["source_result"]).parent
        if checked(item["source_manifest"]) != folder / "episode/manifest.json":
            raise ValueError("Each registry source must be one exact original episode")
        rollout = by_slot[item["slot_id"]].get("rollout")
        if rollout is not None and Path(rollout["episode_path"]).resolve() != folder / "episode":
            raise ValueError("A training entry may not substitute another slot's episode")
    return [by_slot[sid] for sid in order], sources


def private_adapter(function, *, import_modules=None, dependencies=None):
    """Change only explicitly counted host bindings, never original module globals."""
    namespace = {**function.__globals__, **globals(), **(dependencies or {})}
    namespace["original"] = original.original
    if not import_modules:
        return bind(function, **namespace)
    tree = ast.parse(inspect.getsource(function))
    imports = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in (import_modules or {}):
            old = node.module
            node.module = import_modules[old]
            imports[old] = imports.get(old, 0) + 1
    if imports != dict.fromkeys(import_modules or {}, 1):
        raise ValueError("Private adapter must change exactly its declared host bindings")
    exec(compile(ast.fix_missing_locations(tree), "<v050r1-private-host-binding>", "exec"), namespace)
    return namespace[function.__name__]


def _collect(*args, **kwargs):
    return private_adapter(original._collect, import_modules={
        "proworksim.software_training_v050": "proworksim.software_training_v050r1"})(*args, **kwargs)


def _update(*args, **kwargs):
    return private_adapter(original._update, import_modules={
        "proworksim.software_learning_v050": "proworksim.software_learning_v050r1"})(*args, **kwargs)


def run_support_gate(root):
    return private_adapter(original.run_support_gate, import_modules={
        "proworksim.software_learning_v050": "proworksim.software_learning_v050r1"})(root)


def load_materialized_entries(plan, root):
    return private_adapter(original.load_materialized_entries)(plan, root)


def run_worker(root, worker, output):
    if worker == "s_star":
        raise ValueError("The original S* init is reused, never dispatched again")
    return private_adapter(original.run_worker)(root, worker, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "supervise", "worker", "support"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--original-root", type=Path)
    parser.add_argument("--controls", type=Path, default=CONTROLS)
    parser.add_argument("--worker", choices=WORKERS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, original.received_signal)
    if args.command == "prepare":
        if args.original_root is None:
            parser.error("prepare requires --original-root")
        prepare(args.run_root, original_root=args.original_root, controls=args.controls)
    elif args.command == "supervise":
        from scripts.software_learning_resume_supervisor_v050r1 import supervise
        supervise(args.run_root)
    elif args.command == "support":
        run_support_gate(args.run_root)
    else:
        if args.worker is None or args.output is None:
            parser.error("worker requires --worker and --output")
        run_worker(args.run_root, args.worker, args.output)


if __name__ == "__main__":
    main()
