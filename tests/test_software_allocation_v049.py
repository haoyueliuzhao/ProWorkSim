"""Finite v049 support/direction CPU controls; no model or optimizer execution."""
import copy
import os
from pathlib import Path
import subprocess
import sys

import pytest

from proworksim.member_views import member_view
from proworksim.online_training import reference, tensor_tree_digest
from proworksim.software_allocation_v049 import (
    CATEGORIES, MAPPER, build_support_report, feasible_radius, select_direction,
)
from proworksim.software_learning_v049 import MEMBERS, VERSION as LEARNING_VERSION
from proworksim.storage import digest, json_bytes, read_json
from proworksim.team_rollout import work_validity
from test_online_support_v013 import actor


def _fixture(*, single_class=False, residual=False, missing=False, mask_member=False):
    from proworksim.software_training_v049 import declare_window
    design = read_json(Path(__file__).resolve().parents[1] / "docs/experiments/software-learning-v049-design.json")
    identity = actor("v049-cpu")
    policies = {member: {"implementation": "proworksim.software_organization_runtime_v049.worker_type.<locals>.StableO1Worker",
        "config": {"weight_identity": identity, "model_revision": identity["policy_version"],
            "context_policy": "full_history", "format_error_policy": "format_feedback_budgeted_v033"}} for member in MEMBERS}
    declaration = declare_window("v049-support-cpu", actor_identity=identity,
        gamma_identity={"harness": "openhands_v16", "design_sha256": digest(json_bytes(design)),
            "mapper_spec_sha256": digest(b"frozen-cpu-mapper")},
        slot_specs=[{"slot_id": slot["slot_id"], "xi_id": slot["root"], "xi_fingerprint": digest(slot["root"].encode()),
            "active_members": list(MEMBERS), "policies": policies, "mapping_spec_id": MAPPER}
            for slot in design["training_slots"]], min_class_count=2)
    entries, rows, summaries = [], [], []
    for index, slot in enumerate(declaration["slots"]):
        sid = slot["slot_id"]
        if missing and index == 0:
            entries.append({"slot_id": sid, "active_members": list(MEMBERS), "rollout": None, "reward": None, "status": "technical_unknown"})
            summaries.append({"slot_id": sid, "active_members": list(MEMBERS), "members": {}, "exclusions": ["episode_or_reward_record_missing"]})
            continue
        events = []
        def event(member, kind, payload):
            events.append({"sequence": len(events), "worker_id": member, "kind": kind, "payload": payload})
        for member in MEMBERS:
            request = {"messages": [{"role": "user", "content": "CPU metadata fixture"}], "model": "fixture"}
            call = sid + "-" + member
            response = {"id": call, "actor_identity": identity, "system_fingerprint": identity["policy_version"],
                "online_window_id": declaration["window_id"], "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
                "token_trace": {"input_ids": [1, 2], "output_ids": [3], "input_mask": [0, 0], "output_mask": [1],
                    "behavior_logprobs": [-.5], "source": "actual generation token IDs and sampling logits, not retokenized text"}}
            event(member, "model_call", {"stage": "started", "call_id": call, "request_sha256": digest(json_bytes(request))})
            event(member, "model_attempt", {"stage": "finished", "status": "success", "call_id": call,
                "request": request, "response": {"body": response}})
            event(member, "model_response", {"call_id": call, "response": response})
        failed, unmapped = residual and index == 6, residual and index == 7
        valid = work_validity([{"dimension": dimension, "value": not failed or dimension != "delivery",
            "evidence": {"explicit_cpu_fixture": True}} for dimension in ("record", "permission", "basis", "delivery")], spec_id="cpu-v049")
        rollout = {"rollout_id": "cpu-rollout-" + sid, "window": slot["window"], "manifest": {"policies": policies},
            "members": {member: {"actor_id": member, "origin": "target_model"} for member in MEMBERS}, "events": events,
            "reward_eligibility": {"eligible": True, "reward": 0 if failed else 1}, "work_validity": valid}
        category = CATEGORIES[0] if single_class or index % 4 < 2 else CATEGORIES[1]
        mapping = {"rollout_id": rollout["rollout_id"], "spec_id": MAPPER,
            "status": "unmapped" if unmapped else "mapped", "class_id": None if unmapped else category,
            "member_projections": {member: {"class_id": None if unmapped else category,
                "support_eligible": not (failed or unmapped) and not (mask_member and member == MEMBERS[0]),
                "complete_actor_trajectory": True, "actual_input_bindings_complete": True,
                "own_action_count": 1, "own_action_tokens": 1} for member in MEMBERS}}
        entries.append({"slot_id": sid, "active_members": list(MEMBERS), "rollout": rollout,
            "reward": rollout["reward_eligibility"], "mapping": mapping, "status": "closed"})
        summaries.append({"slot_id": sid, "active_members": list(MEMBERS), "exclusions": [],
            "members": {member: {"exclusions": []} for member in MEMBERS}})
        for member in MEMBERS:
            view = member_view(rollout, member)
            assert view["complete_actor_trajectory"] and view["own_action_tokens"] == 1
            decision = view["decisions"][0]
            rows.append({"slot_id": sid, "member_id": member, "call_id": decision["call_id"],
                "actor_denominator": 16, "critic_denominator": 16})
    admission = {"window_id": declaration["window_id"], "actor_identity": identity, "slot_count": 8,
                 "slots": summaries, "decisions": rows}
    report = {"before_actor_identity": identity, "window_id": declaration["window_id"],
        "advantages": [1. - index / 8 for index in range(len(rows))], "behavior_probability_passed": True,
        "backward_decisions_completed": len(rows)}
    support = build_support_report(entries, declaration, admission=admission, design=design, learner_report=report)
    return entries, declaration, admission, design, report, support


def test_support_keeps_failures_unmapped_member_masks_and_four_repeat_measure():
    _, _, _, _, _, support = _fixture(residual=True)
    la, lb = support["roots"]["LA"]["blocks"][MEMBERS[0]], support["roots"]["LB"]["blocks"][MEMBERS[0]]
    assert la["M"] == lb["M"] == 4 and support["global_member_denominator_factor"] == 16
    assert la["n_positive"] == 4 and la["b"] == dict.fromkeys(CATEGORIES, .5)
    assert lb["base_training_trajectory_count"] == 4 and lb["n_positive"] == 2 and lb["v"] == .5
    assert lb["b"] == {CATEGORIES[0]: 1.}
    assert all(all(value == 1 for value in weights.values()) for weights in support["base_weights_by_slot"].values())
    assert lb["G_raw_within_class_degrees_of_freedom"] == 1 and lb["composition_degrees_of_freedom"] == 0
    _, _, _, _, _, masked = _fixture(mask_member=True)
    assert masked["roots"]["LA"]["blocks"][MEMBERS[0]]["n_positive"] == 0
    assert masked["roots"]["LA"]["blocks"][MEMBERS[0]]["base_training_trajectory_count"] == 4
    assert masked["roots"]["LA"]["blocks"][MEMBERS[1]]["n_positive"] == 4


def test_unknown_original_slot_does_not_redistribute_base_mass_or_fabricate_repeats():
    _, _, _, _, _, support = _fixture(missing=True)
    block = support["roots"]["LA"]["blocks"][MEMBERS[0]]
    assert block["M"] == 4 and block["actual_repeats"] == 3 and block["base_training_trajectory_count"] == 3
    assert sum(block["base_actor_mask"].values()) == 3
    assert block["candidate_counts_before_support"] == {CATEGORIES[0]: 1, CATEGORIES[1]: 2}
    assert block["b"] == {CATEGORIES[1]: 1.}
    assert len(support["original_slots"]) == 8


def test_frozen_two_sided_radius_and_material_provenance_rejections():
    rho, direction = feasible_radius(dict.fromkeys(CATEGORIES, .5), CATEGORIES[0])
    assert rho == .4 and direction == {CATEGORIES[0]: .5, CATEGORIES[1]: -.5}
    entries, declaration, admission, design, report, _ = _fixture()
    changed = copy.deepcopy(admission)
    changed["slots"].reverse()
    with pytest.raises(ValueError, match="original admission"):
        build_support_report(entries, declaration, admission=changed, design=design, learner_report=report)
    changed = copy.deepcopy(entries)
    changed[1]["rollout"] = copy.deepcopy(changed[0]["rollout"])
    with pytest.raises(ValueError, match="multiple raw support"):
        build_support_report(changed, declaration, admission=admission, design=design, learner_report=report)
    with pytest.raises(ValueError, match="multiclass"):
        feasible_radius({CATEGORIES[0]: 1.}, CATEGORIES[0])


def test_cpu_actual_gradient_direction_order_scale_zero_and_single_class(tmp_path):
    try:
        import torch
    except ModuleNotFoundError:
        project = Path(__file__).resolve().parents[1]
        code = ("import sys; sys.path.extend(" + repr([path for path in sys.path if "site-packages" in path])
            + "); import pytest; raise SystemExit(pytest.main(" + repr([
                str(Path(__file__).resolve()) + "::test_cpu_actual_gradient_direction_order_scale_zero_and_single_class",
                "-q", "--basetemp=" + str(tmp_path / "torch-control")]) + "))")
        result = subprocess.run([str(project / ".train-venv/bin/python"), "-c", code], cwd=project,
            text=True, capture_output=True, timeout=120, env={**os.environ, "CUDA_VISIBLE_DEVICES": ""})
        assert result.returncode == 0, result.stdout + result.stderr
        return
    assert not torch.cuda.is_initialized()
    _, _, _, _, _, support = _fixture()
    def gradient_case(name, current_support, *, same=False, empty=False):
        gradients = {}
        groups = []
        for index, sid in enumerate(current_support["base_weights_by_slot"]):
            gradients[sid] = {}
            for member in MEMBERS:
                # First block is deliberately zero-mix; next stable member is
                # nonzero, proving canonical skip before later root candidates.
                value = 1. if same or member == MEMBERS[0] else 1. + (index % 4 >= 2)
                values = {} if empty else {"lora": torch.tensor([value / 16], dtype=torch.float32)}
                gradients[sid][member] = values
                groups.append({"slot_id": sid, "member_id": member, "parameters": len(values),
                    "gradient_sha256": tensor_tree_digest(values, torch)})
        path = tmp_path / (name + ".pt")
        torch.save(gradients, path)
        receipt = {"version": LEARNING_VERSION, "tensor_file": reference(path), "groups": groups,
            "original_rows": current_support["gradient_expected_rows"], "additional_actor_forwards": 0,
            "additional_actor_backwards": 0, "optimizer_steps": 0, "hook_returns": None,
            "observed_baseline_loss_before_shared_clipping": True}
        return gradients, receipt
    gradients, receipt = gradient_case("nonzero", support)
    original = tensor_tree_digest(gradients, torch)
    chosen = select_direction(support, gradients, gradient_receipt=receipt, torch=torch)
    assert tensor_tree_digest(gradients, torch) == original
    assert chosen["selected"]["root"] == "LA" and chosen["selected"]["member_id"] == MEMBERS[1]
    assert chosen["selected"]["category"] == CATEGORIES[0]
    assert chosen["selected"]["mixture_gradient_l2_norm"] == .125
    assert chosen["epsilon"] == .1
    sids = support["roots"]["LA"]["slot_ids"]
    assert [chosen["plus_weights_by_slot"][sid][MEMBERS[1]] for sid in sids] == [1.1, 1.1, .9, .9]
    assert [chosen["minus_weights_by_slot"][sid][MEMBERS[1]] for sid in sids] == [.9, .9, 1.1, 1.1]
    assert all(chosen["plus_weights_by_slot"][sid][MEMBERS[0]] == 1 for sid in chosen["baseline_weights_by_slot"])
    assert not chosen["development_results_read"] and chosen["additional_backwards"] == 0
    zero_gradients, zero_receipt = gradient_case("equal-classes", support, same=True)
    zero = select_direction(support, zero_gradients, gradient_receipt=zero_receipt, torch=torch)
    assert zero["selected"] is None and zero["status"] == "no_admissible_I_direction_B_only"
    assert all(item["reason"] == "actual_mixture_gradient_zero" for item in zero["candidate_checks_in_frozen_order"])
    empty, empty_receipt = gradient_case("actor-disabled", support, empty=True)
    assert select_direction(support, empty, gradient_receipt=empty_receipt, torch=torch)["selected"] is None
    _, _, _, _, _, single = _fixture(single_class=True)
    single_gradients, single_receipt = gradient_case("single-class", single)
    single_result = select_direction(single, single_gradients, gradient_receipt=single_receipt, torch=torch)
    assert single_result["selected"] is None
    assert all(item["reason"] == "single_qualified_category" and item["G_raw_within_class_degrees_of_freedom"] == 3
               for item in single_result["candidate_checks_in_frozen_order"])
    corrupted = copy.deepcopy(receipt)
    corrupted["original_rows"] = list(reversed(corrupted["original_rows"]))
    with pytest.raises(ValueError, match="actual B gradient observation"):
        select_direction(support, gradients, gradient_receipt=corrupted, torch=torch)
    corrupted_gradients = copy.deepcopy(gradients)
    corrupted_gradients[sids[0]][MEMBERS[0]]["lora"].add_(1)
    with pytest.raises(ValueError, match="exact group digests"):
        select_direction(support, corrupted_gradients, gradient_receipt=receipt, torch=torch)
    assert not torch.cuda.is_initialized()
