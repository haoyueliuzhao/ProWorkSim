"""Software binding for the existing shared learner and finite v027 allocator.

No alternate optimizer, sampling policy or loss is implemented here. The old
three-coordinate public-history critic is explicitly transferred to two stable
software members plus an inactive coordinate at a common precollection boundary.
All of its numerical state is preserved; this is not evidence that the baseline
is calibrated for software work. Training targets are only actual sampled IDs.
"""

import copy
from pathlib import Path
import time

from .critic_features import DEFAULT_MEMBERS, past_features
from .experience_allocation_v027 import inspect_allocation_window, supports_from_entries
from .member_views import member_view
from .online_training import prepare_window, recipe_config, reference, tensor_tree_digest
from .software_context_v028 import VERSION as CONTEXT_VERSION
from .storage import atomic_write, digest, json_bytes, read_json

VERSION = "software-learning-bridge-v0.29"
MEMBERS = ("member_a", "member_b")
CRITIC_MEMBERS = (*MEMBERS, "software_inactive")
PROTECTED_STATE = (
    "actor", "critic", "actor_optimizer", "critic_optimizer", "rng_cpu", "rng_cuda",
    "policy_revision", "actor_steps", "critic_steps", "critic_has_nonzero_reward_history",
    "actor_identity", "base_identity", "inference_profile", "last_window_id", "used_window_ids",
)


def software_recipe(original):
    """Explicit coordinate binding; construct the owner with its original recipe."""
    recipe = recipe_config(original)
    recipe["members"] = list(CRITIC_MEMBERS)
    return recipe


def migrate_software_owner(owner, output=None, *, expected_steps=(3, 3)):
    """Bind software coordinates once before sampling, preserving every tensor.

    The original SharedActor constructor fixes the old recipe. New workers first
    construct that owner, call this function, then restore the new common bundle.
    Migration is explicit, idempotence is rejected, and it never rewrites the old
    checkpoint. No RNG is consumed and no critic or optimizer is reinitialized.
    """
    if owner.phase != "idle" or owner.busy or getattr(owner, "sampling_only", False):
        raise ValueError("Software binding requires an idle full learner before collection")
    if tuple(owner.recipe["members"]) != DEFAULT_MEMBERS:
        raise ValueError("Migrate exactly once from the original critic coordinate binding")
    if expected_steps is not None and (owner.actor_steps, owner.critic_steps) != tuple(expected_steps):
        raise ValueError("Restore the declared original complete checkpoint before migration")
    before = owner._state_bundle()
    original_recipe = copy.deepcopy(owner.recipe)
    new_recipe = software_recipe(original_recipe)
    if tuple(owner.critic[0].weight.shape) != (32, 30):
        raise ValueError("Software binding requires the existing 30-feature shared critic")
    owner.recipe = new_recipe
    after = owner._state_bundle()
    protected = {key: tensor_tree_digest(before[key], owner.torch) ==
                 tensor_tree_digest(after[key], owner.torch) for key in PROTECTED_STATE}
    if not all(protected.values()):
        raise ValueError("Software coordinate migration changed protected learner state")
    proof = {
        "version": VERSION, "original_recipe": original_recipe, "software_recipe": new_recipe,
        "feature_binding": dict(zip(DEFAULT_MEMBERS, CRITIC_MEMBERS)),
        "active_members": list(MEMBERS), "inactive_member": CRITIC_MEMBERS[-1],
        "before_state_sha256": tensor_tree_digest(before, owner.torch),
        "after_state_sha256": tensor_tree_digest(after, owner.torch),
        "protected_state_unchanged": protected, "new_optimizer_steps": 0,
        "scope": "Numerical transfer of all existing critic coordinates and moments; no software calibration claim. Two software identities occupy the first two observed-history coordinates, the third remains zero/inactive. This binding must be shared before any support sampling or arm fork.",
    }
    owner.software_learning_binding = copy.deepcopy(proof)
    if output is not None:
        atomic_write(Path(output), json_bytes(proof))
    return proof


def software_feature_function(events, before_sequence, member_id, member_ids=CRITIC_MEMBERS):
    if tuple(member_ids) != CRITIC_MEMBERS or member_id not in MEMBERS:
        raise ValueError("Use the frozen software member critic coordinate binding")
    if any(event.get("worker_id") == CRITIC_MEMBERS[-1] for event in events):
        raise ValueError("The inactive critic coordinate cannot acquire fabricated actions")
    features, proof = past_features(events, before_sequence, member_id, CRITIC_MEMBERS)
    proof.update(software_binding_version=VERSION,
                 numerical_transfer_only=True, inactive_coordinate=CRITIC_MEMBERS[-1])
    return features, proof


def restore_common(owner, common, window_id=None):
    """Restore actor/critic/two optimizers/RNG exactly before each trial or arm."""
    if tuple(owner.recipe["members"]) != CRITIC_MEMBERS:
        raise ValueError("Apply common software binding before restoring the software checkpoint")
    record = owner.restore_checkpoint(common)
    actual = tensor_tree_digest(owner._state_bundle(), owner.torch)
    if actual != record["state_tensor_digest"]:
        raise ValueError("Common complete learner/RNG state did not restore exactly")
    proof = {"version": VERSION, "checkpoint": reference(Path(common) / "checkpoint.json"),
             "state_sha256": actual, "complete_state_exact": True,
             "actor_steps": owner.actor_steps, "critic_steps": owner.critic_steps,
             "actor_identity": owner.freeze_identity(),
             "rng_sha256": tensor_tree_digest({key: owner._state_bundle()[key]
                                               for key in ("rng_cpu", "rng_cuda")}, owner.torch)}
    if window_id is not None:
        proof["entered_window"] = window_id
        owner.begin_window(window_id)
    return proof


def allocation_gate(entries, declaration, records):
    """Keep all eight original slots; choose only the first eligible stable member."""
    slots = declaration["slots"]
    if (declaration["min_class_count"] != 2 or len(slots) != 8
            or len({row["xi_id"] for row in slots}) != 1
            or any(row["active_members"] != list(MEMBERS) for row in slots)
            or [row["slot_id"] for row in entries] != [row["slot_id"] for row in slots]):
        raise ValueError("Freeze one exact situation, eight raw slots, two stable members and minclass2")
    byslot = {row["slot_id"]: row for row in records}
    if len(byslot) != len(records) or set(byslot) - {row["slot_id"] for row in slots}:
        raise ValueError("Support status must identify each declared raw slot at most once")
    result = {"version": VERSION, "eligible_blocks": [], "selected_block": None,
              "member_selection_order": list(MEMBERS), "original_slot_count": 8}
    if len(records) != len(slots) or any(row.get("status") != "closed" for row in records):
        return {**result, "status": "incomplete_keep_original_inventory", "supports_by_xi": None,
                "raw_slot_inventory": [{"slot_id": row["slot_id"], "xi_id": row["xi_id"],
                    "status": byslot.get(row["slot_id"], {}).get("status", "not_started")} for row in slots],
                "scope": "Technical unknowns remain in the original inventory; no support estimation or trial update is admitted."}
    result.update(inspect_allocation_window(declaration, records))
    if result["status"] != "ready":
        return result
    supports, _ = supports_from_entries(entries, declaration, records)
    if supports != result["supports_by_xi"]:
        raise ValueError("Diagnostic and original-entry support reconstruction differ")
    xi = slots[0]["xi_id"]
    for member in MEMBERS:
        if supports[xi]["blocks"][member]["composition_degrees_of_freedom"] > 0:
            result.update(eligible_blocks=[[xi, member]], selected_block=[xi, member])
            break
    result["status"] = "ready" if result["eligible_blocks"] else "no_configurable_support"
    result["scope"] = "Original current window only; first canonical member with freedom. Failed/unmapped/rare-class residuals remain baseline weight one; all eight slots keep their original denominator."
    return result


def _projection_index(root):
    index = {}
    for path in sorted(Path(root).rglob("selected-request.json")):
        folder = path.parent
        if not (folder / "projection.json").is_file() or not (folder / "response.json").is_file():
            continue
        envelope = read_json(folder / "response.json")
        response = envelope.get("body", {})
        if envelope.get("http_status") != 200 or not response.get("token_trace"):
            continue
        rid = response.get("id")
        if not isinstance(rid, str) or rid in index:
            raise ValueError("Each actual sampler response requires one unique saved context projection")
        index[rid] = folder
    return index


def validate_training_entries(owner, entries, declaration, *, request_evidence_root):
    """Verify selected input evidence without reconstructing a training target.

    The complete SDK request is audited against original-request.json. Only the
    resident response's token_trace enters prepare_window or loss. Rendering and
    tokenizing selected-request.json is an equality check, never a replacement.
    """
    if tuple(owner.recipe["members"]) != CRITIC_MEMBERS:
        raise ValueError("Training requires the common software coordinate binding")
    if (owner.window_id != declaration["window_id"]
            or owner.freeze_identity() != declaration["actor_identity"]
            or [row["slot_id"] for row in entries] != [row["slot_id"] for row in declaration["slots"]]):
        raise ValueError("Keep exact current actor, window and original slot inventory")
    prepared = prepare_window(entries, owner.freeze_identity(), owner.window_id,
                              owner.recipe, software_feature_function)
    index, proofs = _projection_index(request_evidence_root), []
    views = {(entry["slot_id"], member): member_view(entry["rollout"], member)
             for entry in entries for member in entry["active_members"]}
    for row in prepared["decisions"]:
        view = views[row["slot_id"], row["member_id"]]
        decision = next(item for item in view["decisions"] if item["call_id"] == row["call_id"])
        actual = decision["actual_response"]
        folder = index.get(actual.get("id"))
        if folder is None:
            raise ValueError("Actual sampler response lacks durable selected-request evidence")
        original = read_json(folder / "original-request.json")
        selected = read_json(folder / "selected-request.json")
        projection = read_json(folder / "projection.json")
        saved = read_json(folder / "response.json")["body"]
        if (projection.get("version") != CONTEXT_VERSION or not projection.get("fits")
                or original != decision["actual_input"] or saved != actual
                or projection["original_request_sha256"] != digest(json_bytes(original))
                or projection["selected_request_sha256"] != digest(json_bytes(selected))
                or row["tokens"] != actual["token_trace"]):
            raise ValueError("Saved original/selected request and actual sampled response differ")
        indices = projection["selected_indices"]
        expected = copy.deepcopy(original)
        expected["messages"] = [original["messages"][i] for i in indices]
        if selected != expected:
            raise ValueError("Selected context differs from its exact original message inventory")
        rendered, _, _ = owner.prepare_request(selected)
        observed_ids = owner.tokenizer(rendered, add_special_tokens=False)["input_ids"]
        if (observed_ids != row["tokens"]["input_ids"]
                or digest(rendered.encode()) != projection["rendered_prompt_sha256"]
                or len(observed_ids) != projection["selected_prompt_tokens"]):
            raise ValueError("Actual token IDs do not match the selected resident request")
        proofs.append({"slot_id": row["slot_id"], "member_id": row["member_id"],
                       "call_id": row["call_id"], "sampler_response_id": actual["id"],
                       "selected_request": reference(folder / "selected-request.json"),
                       "projection": reference(folder / "projection.json"),
                       "actual_response": reference(folder / "response.json"),
                       "training_token_trace_sha256": digest(json_bytes(row["tokens"])),
                       "input_tokens": len(observed_ids), "output_tokens": len(row["tokens"]["output_ids"]),
                       "omitted_sdk_message_count": len(projection["removed_indices"]),
                       "actor_denominator": row["actor_denominator"],
                       "critic_denominator": row["critic_denominator"]})
    return {"version": VERSION, "entries_sha256": digest(json_bytes(entries)),
            "declaration_sha256": digest(json_bytes(declaration)), "rows": proofs,
            "slot_count": len(entries), "admitted_decisions": len(proofs),
            "admission_slots": prepared["slots"],
            "scope": "Original own response token_trace only; unselected SDK history is audit evidence and never enters a reconstructed training sequence."}


def update_software_window(owner, entries, output, *, declaration,
                           request_evidence_root, composition=None):
    """Audit real targets/resources then call the existing complete-window updater."""
    output = Path(output)
    proof = validate_training_entries(owner, entries, declaration,
                                      request_evidence_root=request_evidence_root)
    atomic_write(output.parent / (output.name + "-token-evidence.json"), json_bytes(proof))
    torch = owner.torch
    if owner.device.startswith("cuda"):
        for device in range(torch.cuda.device_count()):
            torch.cuda.reset_peak_memory_stats(device)
    started = time.monotonic()
    report = owner.update_window(entries, output, feature_function=software_feature_function,
                                 composition=composition)
    consumption = {"version": VERSION, "elapsed_seconds": time.monotonic() - started,
                   "admitted_decisions": report.get("admitted_decisions"),
                   "admitted_output_tokens": report.get("admitted_output_tokens"),
                   "backward_decisions_completed": report.get("backward_decisions_completed"),
                   "status": report["status"], "resource": report.get("resource"),
                   "actor_optimizer_steps": report["actor_optimizer_steps"],
                   "critic_optimizer_steps": report["critic_optimizer_steps"],
                   "peak_gpu_allocated_bytes": ({str(device): torch.cuda.max_memory_allocated(device)
                       for device in range(torch.cuda.device_count())} if owner.device.startswith("cuda") else {}),
                   "scope": "Actual current candidate update interval, separate from collection/development evaluation; measured peak allocations are not device-wide process residency."}
    atomic_write(output / "software-consumption.json", json_bytes(consumption))
    return report
