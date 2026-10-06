"""Current-Gamma input binding over the unchanged real full-window learner.

Projector replay proves which input the sampler used; it never substitutes a
rendered sequence for original token_trace targets or restores hidden feedback.
The first real probability/backward check belongs to the shared B trial.
"""
from collections import Counter, defaultdict
from pathlib import Path
import time

from .member_views import member_view
from .online_training import prepare_window, reference
from .software_context_v034 import VERSION as CONTEXT_VERSION, project_software_request
from .software_learning_v029 import (
    CRITIC_MEMBERS, MEMBERS as MEMBERS, migrate_software_owner as migrate_software_owner,
    restore_common as restore_common, software_feature_function,
    _projection_index,
)
from .storage import atomic_write, digest, json_bytes, read_json
from .team_rollout import optimizer_scope_allows_update

VERSION = "software-learning-bridge-v0.35"


def validate_selected_trace(owner, *, original, actual, folder):
    """Read exact durable input/response evidence and replay the fixed v034 projection."""
    folder = Path(folder)
    saved_original = read_json(folder / "original-request.json")
    selected = read_json(folder / "selected-request.json")
    projection = read_json(folder / "projection.json")
    saved = read_json(folder / "response.json")
    if (saved.get("http_status") != 200 or saved_original != original or saved.get("body") != actual
            or projection.get("version") != CONTEXT_VERSION or projection.get("fits") is not True):
        raise ValueError("Saved original/selected request and actual sampled response differ")
    replayed, replay_audit = project_software_request(
        original, render=owner.prepare_request, tokenizer=owner.tokenizer,
        context_limit=owner.recipe["max_length"])
    if replayed != selected or replay_audit != projection:
        raise ValueError("The actual selected request is not the exact frozen v034 Gamma projection")
    rendered, _, _ = owner.prepare_request(selected)
    observed = owner.tokenizer(rendered, add_special_tokens=False)["input_ids"]
    trace = actual["token_trace"]
    if (observed != trace["input_ids"] or digest(rendered.encode()) != projection["rendered_prompt_sha256"]
            or digest(json_bytes(observed)) != projection["input_ids_sha256"]
            or len(observed) != projection["selected_prompt_tokens"]):
        raise ValueError("Original sampler token IDs differ from the actual selected input")
    return {"sampler_response_id": actual["id"], "selected_request": reference(folder / "selected-request.json"),
            "original_request": reference(folder / "original-request.json"),
            "projection": reference(folder / "projection.json"), "actual_response": reference(folder / "response.json"),
            "training_token_trace_sha256": digest(json_bytes(trace)),
            "input_tokens": len(observed), "output_tokens": len(trace["output_ids"]),
            "omitted_sdk_message_count": len(projection["removed_indices"]),
            "duplicate_values_removed": len(projection["deduplication"]["removed_values"]),
            "training_targets_reconstructed": False}


def material_summary(prepared):
    bymember = defaultdict(lambda: {"decisions": 0, "input_tokens": 0, "own_output_tokens": 0})
    lengths = []
    for row in prepared["decisions"]:
        member = bymember[row["member_id"]]
        member["decisions"] += 1
        member["input_tokens"] += len(row["tokens"]["input_ids"])
        member["own_output_tokens"] += len(row["tokens"]["output_ids"])
        lengths.append(len(row["tokens"]["input_ids"]) + len(row["tokens"]["output_ids"]))
    exclusions = Counter(reason for slot in prepared["slots"] for reason in slot["exclusions"])
    exclusions.update(reason for slot in prepared["slots"] for member in slot["members"].values()
                      for reason in member["exclusions"])
    return {"original_slot_count": prepared["slot_count"], "admitted_decisions": len(prepared["decisions"]),
            "admitted_input_tokens": sum(row["input_tokens"] for row in bymember.values()),
            "admitted_own_output_tokens": sum(row["own_output_tokens"] for row in bymember.values()),
            "maximum_actual_sequence_tokens": max(lengths, default=0),
            "sum_actual_sequence_tokens": sum(lengths), "by_member": dict(bymember),
            "exclusion_counts": dict(exclusions), "normalization": prepared["normalization"],
            "training_time_estimate_seconds": None,
            "scope": "Actual raw target scale, not a measured update cost; every planned slot stays in the base denominator"}


def validate_training_entries(owner, entries, declaration, *, request_evidence_root, require_open_window=True):
    """Audit current-policy targets without a model forward, update or reward substitution."""
    if (tuple(owner.recipe["members"]) != CRITIC_MEMBERS
            or owner.freeze_identity() != declaration["actor_identity"]
            or require_open_window and owner.window_id != declaration["window_id"]
            or [row["slot_id"] for row in entries] != [row["slot_id"] for row in declaration["slots"]]):
        raise ValueError("Keep the exact actor, declared window, software members and original slots")
    gamma = declaration["gamma_identity"]
    if (gamma.get("source_usage") != "policy_training" or gamma.get("optimizer_update_allowed") is not True
            or gamma.get("presentation_version") != CONTEXT_VERSION
            or any(entry.get("rollout") is not None and not optimizer_scope_allows_update(entry["rollout"])
                   for entry in entries)):
        raise ValueError("Only a purpose-isolated policy-training window may bind optimizer targets")
    prepared = prepare_window(entries, owner.freeze_identity(), declaration["window_id"],
                              owner.recipe, software_feature_function)
    index, proofs = _projection_index(request_evidence_root), []
    views = {(entry["slot_id"], member): member_view(entry["rollout"], member)
             for entry in entries if entry.get("rollout") is not None for member in entry["active_members"]}
    for row in prepared["decisions"]:
        view = views[row["slot_id"], row["member_id"]]
        decision = next(item for item in view["decisions"] if item["call_id"] == row["call_id"])
        actual = decision["actual_response"]
        folder = index.get(actual.get("id"))
        if folder is None or row["tokens"] != actual["token_trace"]:
            raise ValueError("An original own-token target lacks its unique durable selected-input evidence")
        evidence = validate_selected_trace(owner, original=decision["actual_input"], actual=actual, folder=folder)
        proofs.append({"slot_id": row["slot_id"], "member_id": row["member_id"], "call_id": row["call_id"],
                       "actor_denominator": row["actor_denominator"], "critic_denominator": row["critic_denominator"],
                       **evidence})
    return {"version": VERSION, "entries_sha256": digest(json_bytes(entries)),
            "declaration_sha256": digest(json_bytes(declaration)), "rows": proofs,
            "admission_slots": prepared["slots"], **material_summary(prepared),
            "probability_recomputation_executed": False, "optimizer_steps": 0,
            "requires_shared_B_trial_probability_and_full_backward": True,
            "scope": "Frozen Gamma replay is an input-integrity check only. Original own token_trace is the sole training target; unavailable backend detail is never added to actor input history."}


def update_software_window(owner, entries, output, *, declaration, request_evidence_root, composition=None):
    """Run the inherited exact full-window updater; new composition routing is explicit."""
    output = Path(output)
    proof = validate_training_entries(owner, entries, declaration, request_evidence_root=request_evidence_root)
    atomic_write(output.parent / (output.name + "-token-evidence.json"), json_bytes(proof))
    torch = owner.torch
    if owner.device.startswith("cuda"):
        for device in range(torch.cuda.device_count()):
            torch.cuda.reset_peak_memory_stats(device)
    started = time.monotonic()
    report = owner.update_window(entries, output, feature_function=software_feature_function, composition=composition)
    consumption = {"version": VERSION, "elapsed_seconds": time.monotonic() - started,
                   "actual_material": {key: proof[key] for key in (
                       "original_slot_count", "admitted_decisions", "admitted_input_tokens", "admitted_own_output_tokens",
                       "sum_actual_sequence_tokens", "maximum_actual_sequence_tokens")},
                   "backward_decisions_completed": report.get("backward_decisions_completed"),
                   "status": report["status"], "resource": report.get("resource"),
                   "actor_optimizer_steps": report["actor_optimizer_steps"],
                   "critic_optimizer_steps": report["critic_optimizer_steps"],
                   "peak_gpu_allocated_bytes": ({str(device): torch.cuda.max_memory_allocated(device)
                       for device in range(torch.cuda.device_count())} if owner.device.startswith("cuda") else {}),
                   "scope": "Measured actual update interval, distinct from sampling/development costs; numerical checks are part of this common B/trial/formal update, never a disposable extra production diagnostic"}
    atomic_write(output / "software-consumption.json", json_bytes(consumption))
    return report
