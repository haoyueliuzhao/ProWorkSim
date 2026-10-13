"""Bounded v050 metadata/measure controls; no model, GPU or tensor-file work."""
from __future__ import annotations

import ast
import copy
import inspect
from types import SimpleNamespace

import pytest

from proworksim import online_training
from proworksim import software_allocation_v049 as old_allocation
from proworksim import software_allocation_v050 as allocation
from proworksim import software_learning_v049 as old_learning
from proworksim import software_learning_v050 as learning
from proworksim import software_mapper_v049 as old_mapper
from proworksim import software_mapper_v050 as mapper
from proworksim import software_member_views_v049r1 as old_reader
from proworksim import software_member_views_v050 as reader
from proworksim import software_training_v050 as training
from proworksim.storage import digest, json_bytes
from proworksim.team_rollout import work_validity
from test_online_support_v013 import actor
from test_software_member_views_v049r1 import _write_archive, fixture as refusal_fixture


def fixture(*, categories=None, residual=False, missing=False, mask_member=False):
    members = list(learning.MEMBERS)
    design = {"training_slots": [
        {"slot_id": sid, "root": "LA" if index < 12 else "LB", "members": members,
         "sampling_seed": 202610130501 + index, "purpose": "policy_training"}
        for index, sid in enumerate(learning.SLOT_IDS)],
        "mapper": {"category_order": list(allocation.CATEGORIES)},
        "direction": {"weight_lower": .5, "weight_upper": 2., "total_variation_from_b_max": .2}}
    identity = actor("v050-cpu-S-star-4")
    recipe = {"members": list(learning.CRITIC_MEMBERS), "temperature": .7,
              "max_length": 18432, "credit_assignment": "terminal_mc"}
    policies = {member: {"implementation": training.POLICY_IMPLEMENTATION,
        "config": {"weight_identity": identity, "model_revision": identity["policy_version"],
                   "context_policy": "full_history", "format_error_policy": "format_feedback_budgeted_v033"}}
        for member in members}
    gamma = {"harness": "openhands_v16", "design_sha256": digest(json_bytes(design)),
        "mapper_spec_sha256": digest(json_bytes(mapper.mapping_spec())),
        "source_usage": "policy_training", "optimizer_update_allowed": True,
        "learning_bridge_version": learning.VERSION,
        "s_star": {"actor_identity": identity, "recipe_sha256": digest(json_bytes(recipe)),
                   "actor_steps": 4, "critic_steps": 4}}
    declaration = training.declare_window(learning.TRAINING_WINDOW_ID,
        actor_identity=identity, gamma_identity=gamma, min_class_count=2,
        slot_specs=[{"slot_id": row["slot_id"], "xi_id": row["root"],
            "xi_fingerprint": digest(row["root"].encode()), "active_members": members,
            "policies": policies, "mapping_spec_id": training.MAPPER} for row in design["training_slots"]])
    entries = []
    for index, slot in enumerate(declaration["slots"]):
        sid = slot["slot_id"]
        if missing and index == 0:
            entries.append(training.unavailable_slot_entry(declaration, sid, "explicit CPU unknown source"))
            continue
        events = []
        def event(member, kind, payload):
            events.append({"sequence": len(events), "worker_id": member, "kind": kind, "payload": payload})
        for member_index, member in enumerate(members):
            # Different T,K per member verifies trajectory normalization, not
            # uniform per-token or total-observed-token renormalization.
            for turn in range(member_index + 1):
                call = f"{sid}-{member}-{turn}"
                request = {"messages": [{"role": "user", "content": "explicit CPU metadata fixture"}]}
                outputs = [3] * (turn + 1)
                response = {"id": call, "actor_identity": identity,
                    "system_fingerprint": identity["policy_version"], "online_window_id": declaration["window_id"],
                    "usage": {"prompt_tokens": 2, "completion_tokens": len(outputs), "total_tokens": 2 + len(outputs)},
                    "token_trace": {"input_ids": [1, 2], "output_ids": outputs, "input_mask": [0, 0],
                        "output_mask": [1] * len(outputs), "behavior_logprobs": [-.5] * len(outputs),
                        "sampling_temperature": .7, "sampling_top_p": 1, "sampling_top_k": 0,
                        "source": "actual generation token IDs and sampling logits, not retokenized text"}}
                event(member, "model_call", {"stage": "started", "call_id": call,
                    "request_sha256": digest(json_bytes(request))})
                event(member, "model_attempt", {"stage": "finished", "status": "success", "call_id": call,
                    "request": request, "response": {"body": response}})
                event(member, "model_response", {"call_id": call, "response": response})
        failed, unmapped = residual and index == 22, residual and index == 23
        reward = {"eligible": True, "reward": 0 if failed else 1,
            "episode_id": "cpu-" + sid, "manifest_sha256": digest(sid.encode())}
        validity = work_validity([{"dimension": dimension, "value": not failed or dimension != "delivery",
            "evidence": {"explicit_cpu_fixture": True}} for dimension in ("record", "permission", "basis", "delivery")],
            spec_id="v050-explicit-CPU-fixture")
        rollout = {"rollout_id": reward["episode_id"], "manifest_sha256": reward["manifest_sha256"],
            "window": slot["window"], "manifest": {"policies": policies},
            "members": {member: {"actor_id": member, "origin": "target_model"} for member in members},
            "events": events, "reward_eligibility": reward, "work_validity": validity,
            "online_scope": {"purpose": "policy_training", "source_training_admission": True,
                             "optimizer_update_allowed": True}}
        label = categories[index] if categories else allocation.CATEGORIES[int(index % 12 >= 6)]
        mapping = {"rollout_id": rollout["rollout_id"], "spec_id": training.MAPPER,
            "status": "unmapped" if unmapped else "mapped", "class_id": None if unmapped else label,
            "member_projections": {member: {"class_id": None if unmapped else label,
                "support_eligible": not (failed or unmapped) and not (mask_member and member == members[0]),
                "complete_actor_trajectory": True, "actual_input_bindings_complete": True,
                "own_action_count": 1 if member == members[0] else 2,
                "own_action_tokens": 1 if member == members[0] else 3} for member in members}}
        entries.append({"slot_id": sid, "active_members": members, "rollout": rollout,
            "reward": reward, "mapping": mapping, "status": "closed"})
    admission = learning.prepare_training_admission(entries, declaration, recipe)
    support = allocation.build_support_report(entries, declaration, admission=admission, design=design)
    return entries, declaration, recipe, design, admission, support


def test_fixed_48_measure_m12_and_pretraining_gate_are_cpu_only():
    entries, _, _, _, admission, support = fixture()
    assert len(entries) == admission["slot_count"] == support["original_slot_count"] == 24
    assert support["global_member_denominator_factor"] == 48
    assert len(admission["decisions"]) == 72
    for row in admission["decisions"]:
        assert row["actor_denominator"] == (48 if row["member_id"] == learning.MEMBERS[0] else 144)
        assert row["critic_denominator"] == (48 if row["member_id"] == learning.MEMBERS[0] else 96)
    gate = allocation.pretraining_support_gate(support)
    assert gate["run_B50"] and gate["development_branches"] == ["S_star", "B"]
    assert gate["new_actor_forwards"] == gate["new_backwards"] == gate["new_optimizer_steps"] == 0
    assert all(block["M"] == 12 and block["v"] == 1 for group in support["roots"].values() for block in group["blocks"].values())


def test_single_peer_per_root_cannot_pool_members_or_roots_and_closes_without_B():
    local, peer = allocation.CATEGORIES
    _, _, _, _, admission, support = fixture(categories=([local] * 11 + [peer]) * 2)
    gate = allocation.pretraining_support_gate(support)
    assert not gate["run_B50"] and gate["development_branches"] == []
    assert len(admission["decisions"]) == 72
    assert all(row["qualified_counts"] == {local: 11} and row["v"] == 11 / 12 for row in gate["blocks"])
    assert all(weight == 1 for row in support["base_weights_by_slot"].values() for weight in row.values())


def test_trusted_R0_unmapped_and_missing_slots_retain_original_mass():
    entries, _, _, _, admission, support = fixture(residual=True, missing=True)
    assert admission["slot_count"] == 24 and len(admission["decisions"]) == 69
    assert any(row["reward"] == 0 for row in admission["decisions"])
    for root in allocation.ROOTS:
        block = support["roots"][root]["blocks"][learning.MEMBERS[0]]
        assert block["M"] == 12
    assert support["roots"]["LA"]["blocks"][learning.MEMBERS[0]]["actual_repeats"] == 11
    assert support["roots"]["LB"]["blocks"][learning.MEMBERS[0]]["base_training_trajectory_count"] == 12
    assert support["roots"]["LB"]["blocks"][learning.MEMBERS[0]]["n_positive"] == 10
    assert all(weight == 1 for row in support["base_weights_by_slot"].values() for weight in row.values())
    assert all(row["slot_id"] != entries[0]["slot_id"] for row in admission["decisions"])
    with pytest.raises(ValueError, match="fixed 24 collections"):
        allocation.pretraining_support_gate(support)


def test_member_projection_masks_only_composition_support():
    _, _, _, _, admission, support = fixture(mask_member=True)
    assert len(admission["decisions"]) == 72
    gate = allocation.pretraining_support_gate(support)
    assert gate["qualified_blocks_in_frozen_order"] == [
        {"root": root, "member_id": learning.MEMBERS[1]} for root in allocation.ROOTS]
    assert all(support["roots"][root]["blocks"][learning.MEMBERS[0]]["base_training_trajectory_count"] == 12
               for root in allocation.ROOTS)


@pytest.mark.parametrize("mutation", ["old8", "reordered", "wrongseed", "duplicaterollout", "denominator16", "denominator96", "droppeddecision", "threshold1"])
def test_inventory_admission_rejects_relabeling_and_renormalization(mutation):
    entries, declaration, _, design, admission, _ = fixture()
    if mutation == "old8":
        entries = entries[:8]
    elif mutation == "reordered":
        admission["slots"].reverse()
    elif mutation == "wrongseed":
        design["training_slots"][0]["sampling_seed"] = 202610120491
    elif mutation == "duplicaterollout":
        entries[1]["rollout"] = copy.deepcopy(entries[0]["rollout"])
    elif mutation == "denominator16":
        admission["decisions"][0]["actor_denominator"] = 16
    elif mutation == "denominator96":
        admission["decisions"][0]["actor_denominator"] = 96
    elif mutation == "droppeddecision":
        admission["decisions"].pop(2)
    else:
        declaration["min_class_count"] = 1
    with pytest.raises(ValueError):
        allocation.build_support_report(entries, declaration, admission=admission, design=design)


def test_composition_keeps_residual_unit_and_critic_original_measure():
    entries, declaration, _, _, admission, support = fixture(residual=True)
    weights = copy.deepcopy(support["base_weights_by_slot"])
    sids = support["roots"]["LA"]["slot_ids"]
    for index, sid in enumerate(sids):
        weights[sid][learning.MEMBERS[0]] = 1.1 if index < 6 else .9
    binding = {"declaration_sha256": digest(json_bytes(declaration)),
        "design_sha256": declaration["gamma_identity"]["design_sha256"],
        "mapper_spec_sha256": declaration["gamma_identity"]["mapper_spec_sha256"],
        "support_artifact_sha256": digest(json_bytes(support)),
        "selected_direction_artifact_sha256": digest(b"explicit CPU direction fixture")}
    composition = learning.bind_composition(entries, declaration, weights, binding=binding)
    actual, audit = learning.validate_composition(entries, admission, composition)
    assert len(actual) == 72 and not audit["critic_reweighted"] and audit["original_normalization_preserved"]
    assert all(actual[index] == 1 for index, row in enumerate(admission["decisions"])
               if row["slot_id"] in {entries[-1]["slot_id"], entries[-2]["slot_id"]})
    changed = copy.deepcopy(weights)
    changed[sids[0]][learning.MEMBERS[0]] += .1
    with pytest.raises(ValueError, match="block mass"):
        learning.bind_composition(entries, declaration, changed, binding=binding)


def test_pretraining_gate_rejects_post_B_report_and_changed_seal():
    _, _, _, _, _, support = fixture()
    support["learner_report_sha256"] = digest(b"post-B-not-pretraining")
    support["seal_sha256"] = digest(json_bytes({key: value for key, value in support.items() if key != "seal_sha256"}))
    with pytest.raises(ValueError, match="pre-B"):
        allocation.pretraining_support_gate(support)
    support["global_member_denominator_factor"] = 16
    with pytest.raises(ValueError, match="seal"):
        allocation.pretraining_support_gate(support)


@pytest.mark.parametrize("steps", [(3, 3), (5, 5), (4, 5)])
def test_independent_branch_starts_reject_old_or_sequential_update(steps, tmp_path):
    owner = SimpleNamespace(actor_steps=steps[0], critic_steps=steps[1])
    with pytest.raises(ValueError, match="independently starts"):
        learning.update_window(owner, [{"slot_id": sid} for sid in learning.SLOT_IDS], tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()


@pytest.mark.parametrize("kind", ["tokens", "context"])
def test_strict_new_runtime_refusal_proof_does_not_promote_old_source(tmp_path, kind):
    rollout, folder = refusal_fixture(tmp_path, kind)
    assert old_reader.member_view(rollout, learning.MEMBERS[0])["complete_actor_trajectory"]
    assert not reader.member_view(rollout, learning.MEMBERS[0])["complete_actor_trajectory"]
    rollout["manifest"]["scenario"]["variation"]["organization_runtime"]["version"] = "software-organization-runtime-v0.50"
    _write_archive(rollout, folder)
    before = {str(path): digest(path.read_bytes()) for path in folder.rglob("*") if path.is_file()}
    view = reader.member_view(rollout, learning.MEMBERS[0])
    assert view["complete_actor_trajectory"] and view["own_action_tokens"] == 1
    assert view["decisions"][-1]["actor_required"] is False
    assert before == {str(path): digest(path.read_bytes()) for path in folder.rglob("*") if path.is_file()}


def test_original_numeric_recipe_mapper_and_support_kernel_remain_unchanged():
    assert learning._numeric_update.__code__ is online_training.SharedActor.update_window.__code__
    assert reader.prepare_window.__code__ is online_training.prepare_window.__code__
    assert learning._original_update_adapter.__code__ is old_learning.update_window.__code__
    assert learning._numeric_update.__globals__["prepare_window"] is reader.prepare_window
    assert learning.validate_composition.__code__ is old_learning.validate_composition.__code__
    assert mapper.map_software_method.__code__ is old_mapper.map_software_method.__code__
    assert mapper.mapping_spec is old_mapper.mapping_spec
    assert allocation.feasible_radius is old_allocation.feasible_radius
    assert allocation.build_support_report.__globals__["build_support"] is old_allocation.build_support
    assert allocation.select_direction.__globals__["materialize_weights"] is old_allocation.materialize_weights
    assert allocation._validate_gradients.__code__ is old_allocation._validate_gradients.__code__
    assert old_learning.member_view is not reader.member_view
    assert allocation.adaptation_spec()["explicit_AST_changes"] == dict.fromkeys(
        ["import", "slot_count", "denominator", "measure_text", "docstring"], 1)
    # Only the description's base measure changed inside the direction body.
    source = ast.parse(inspect.getsource(old_allocation.select_direction))
    for node in ast.walk(source):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = node.value.replace("1/(8*2*member_output_tokens)", "1/(24*2*member_output_tokens)")
    assert allocation.select_direction.__globals__["_validate_gradients"] is allocation._validate_gradients
