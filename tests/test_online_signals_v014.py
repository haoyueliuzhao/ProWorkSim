"""Credit timing and measured diagnostics, including bounded actual Torch controls."""

import copy
import math

import pytest

from proworksim.online_signals import (
    GroupGradientCapture, decision_stage, joint_return, sampled_change, select_post_update_rows,
)
from proworksim.online_training import prepare_window, recipe_config
from proworksim.storage import read_json


def _ledger_record():
    return {"reward": 0.2, "ledger": {"version": "fixture", "terminal_sequence": 9, "events": [
        {"term_id": "delivery", "sequence": 3, "amount": 0.2, "settlement": "event"},
        {"term_id": "terminal_contract_reconciliation", "sequence": 9, "amount": 0.0, "settlement": "terminal"}]}}


def test_joint_rtg_removes_past_team_success_but_preserves_terminal_mc():
    reward, events = _ledger_record(), [{"sequence": n} for n in range(10)]
    assert joint_return(reward, 1, "joint_reward_to_go", events)[0] == 0.2
    assert joint_return(reward, 4, "joint_reward_to_go", events)[0] == 0.0
    assert joint_return(reward, 4, "terminal_mc", events)[0] == 0.2
    # A later correction is a real future consequence, even when it is negative.
    reward["reward"] = 0.0
    reward["ledger"]["events"][-1]["amount"] = -0.2
    assert joint_return(reward, 1, "joint_reward_to_go", events)[0] == 0.0
    assert joint_return(reward, 4, "joint_reward_to_go", events)[0] == -0.2


def test_rtg_refuses_missing_forged_or_nonconserving_ledger():
    events = [{"sequence": n} for n in range(10)]
    with pytest.raises(ValueError, match="explicit historical"):
        joint_return({"reward": 1}, 1, "joint_reward_to_go", events)
    for mutate in [lambda r: r.update(reward=0.8),
                   lambda r: r["ledger"]["events"][0].update(sequence=100),
                   lambda r: r["ledger"]["events"][-1].update(sequence=8),
                   lambda r: r["ledger"].update(terminal_sequence=8),
                   lambda r: r["ledger"]["events"][0].update(amount=float("nan"))]:
        record = _ledger_record()
        mutate(record)
        with pytest.raises(ValueError):
            joint_return(record, 1, "joint_reward_to_go", events)


def test_stage_uses_only_public_prefix_applied_handoff_and_own_observation():
    events = [
        {"sequence": 1, "kind": "public_observation", "worker_id": "implementer",
         "payload": {"work_items": {"P::work": {"status": "in_progress"}}}},
        {"sequence": 2, "kind": "environment_event", "payload": {"kind": "manual_handoff", "outcome": "rejected",
         "payload": {"route_id": "basis", "work_item_id": "P::work"}}},
        {"sequence": 4, "kind": "environment_event", "payload": {"kind": "manual_handoff", "outcome": "applied",
         "payload": {"route_id": "basis", "work_item_id": "P::work"}}},
        {"sequence": 5, "kind": "public_observation", "worker_id": "reviewer",
         "payload": {"work_items": {"P::work": {"status": "accepted"}}}},
    ]
    assert decision_stage(events, 3, "implementer", "P::work")["label"] == "in_progress/no_episode_basis_delivery"
    assert decision_stage(events, 6, "implementer", "P::work")["label"] == "in_progress/after_basis_delivery"
    assert decision_stage(events, 6, "reviewer", "P::work")["label"] == "accepted/after_basis_delivery"


def test_sampled_change_is_explicit_estimate_and_selection_does_not_use_reward():
    result = sampled_change([-2.0, -2.0], [-1.9, -2.1], 0.2)
    assert result["mean_new_minus_old_logprob"] == pytest.approx(0)
    assert result["sampled_k3_ratio_minus_logratio_minus_one"] > 0
    assert result["sampled_ratio_outside_clip_fraction"] == 0
    assert "not full-distribution KL" in result["scope"]
    rows = [{"task": "handoff", "member_id": "provider", "stage": {"label": "start"}},
            {"task": "handoff", "member_id": "provider", "stage": {"label": "start"}},
            {"task": "implement", "member_id": "implementer", "stage": {"label": "start"}}]
    assert select_post_update_rows(rows, 2) == [0, 2]
    assert select_post_update_rows(rows, 1) == [0]
    with pytest.raises(ValueError):
        recipe_config({"credit_assignment": "manufactured_negative_failure"})
    with pytest.raises(ValueError):
        recipe_config({"post_update_max_decisions": -1})


def test_actual_group_gradient_hooks_preserve_sum_show_cancellation_and_bound_storage():
    torch = pytest.importorskip("torch")
    p = torch.nn.Parameter(torch.tensor([2.0, 3.0]))
    capture = GroupGradientCapture({"p": p}, torch, 2)
    for member, sign in [("provider", 1), ("reviewer", -1)]:
        capture.select({"task": "chain", "member_id": member})
        (sign * p.sum()).backward()
    result = capture.finish()
    assert torch.equal(p.grad, torch.zeros_like(p))
    assert [g["gradient_l2_norm"] for g in result["groups"]] == pytest.approx([math.sqrt(2)] * 2)
    assert result["all_groups_reconstruction_l2_residual"] == 0
    assert result["additional_actor_forwards"] == 0
    bounded = GroupGradientCapture({"p": p}, torch, 1)
    for member in ("provider", "reviewer"):
        bounded.select({"task": "chain", "member_id": member})
        p.sum().backward()
    assert bounded.finish()["omitted_groups"] == [["chain", "reviewer", "unspecified"]]


def test_actual_torch_rtg_update_records_targets_groups_and_changed_sampled_policy(tmp_path):
    torch = pytest.importorskip("torch")
    from test_online_training_v13 import _features, _owner, _sample_entry

    torch.manual_seed(17)
    owner = _owner(tmp_path, torch)
    owner.recipe["credit_assignment"] = "joint_reward_to_go"
    owner.begin_window("rtg")
    entry = _sample_entry(owner, reward=1)
    later_entry = _sample_entry(owner, reward=1, slot="later")
    later = copy.deepcopy(later_entry["rollout"]["events"][1:])
    for event in later:
        event["sequence"] += 3
    entry["rollout"]["events"].extend(later)
    entry["reward"]["ledger"] = {"version": "fixture", "terminal_sequence": 6, "events": [
        {"term_id": "delivered", "sequence": 3, "amount": 1.0, "settlement": "event"}]}
    admission = prepare_window([entry], owner.freeze_identity(), "rtg", owner.recipe, _features)
    assert [row["reward"] for row in admission["decisions"]] == [1.0, 0.0]
    result = owner.update_window([entry], tmp_path / "update", feature_function=_features)
    assert result["advantages"] == [1.0, 0.0]
    assert result["actor_optimizer_steps"] == result["critic_optimizer_steps"] == 1
    signal = read_json(tmp_path / "update/signal-diagnostics.json")
    assert signal["groups"][0]["advantages"] == {"positive": 1, "negative": 0, "zero": 1}
    assert signal["gradient_capture"]["groups"][0]["gradient_l2_norm"] > 0
    assert signal["gradient_capture"]["all_groups_reconstruction_l2_residual"] < 1e-7
    assert signal["groups"][0]["clipped_objective_fraction"] == 0
    post = read_json(tmp_path / "update/post-update-sampled-policy.json")
    assert len(post["decisions"]) == 1
    assert post["decisions"][0]["mean_abs_logprob_delta"] > 0
    assert result["post_update_additional_actor_forwards"] == 1


def test_predeclared_online_probe_online_preserves_learner_rng_and_real_windows(tmp_path):
    torch = pytest.importorskip("torch")
    from test_online_training_v13 import _owner, _sample_entry
    from proworksim.online_training import run_online_windows, tensor_tree_digest

    torch.manual_seed(52)
    owner = _owner(tmp_path, torch)
    expected, seen = {}, []
    original_forward, original_critic = owner.model.forward, owner.critic.forward

    def forbid_learning_forward(*args, **kwargs):
        raise AssertionError("A frozen probe must not replay actor targets or call the critic")

    def collect(actor, spec, output):
        seen.append((spec["window_id"], actor.actor_steps, actor.freeze_identity()))
        if spec["window_id"] == "probe":
            state = actor._state_bundle()
            for field in ("actor", "critic", "actor_optimizer", "critic_optimizer", "rng_cpu", "rng_cuda"):
                expected[field] = tensor_tree_digest(state[field], torch)
            actor.model.forward = forbid_learning_forward
            actor.critic.forward = forbid_learning_forward
            actor.reseed(191, label="fixed-dev-probe")
        elif spec["window_id"] == "train-1":
            state = actor._state_bundle()
            for field, expected_digest in expected.items():
                assert tensor_tree_digest(state[field], torch) == expected_digest, field
            actor.model.forward, actor.critic.forward = original_forward, original_critic
        return [_sample_entry(actor, reward=1.0, slot=spec["slots"][0]["slot_id"])]

    protocol = {"mode": "online", "windows": [
        {"window_id": "train-0", "slots": [{"slot_id": "training-first"}]},
        {"window_id": "probe", "mode": "evaluate", "slots": [{"slot_id": "dev-probe"}]},
        {"window_id": "train-1", "slots": [{"slot_id": "training-new"}]},
    ]}
    report = run_online_windows(owner, protocol, tmp_path / "online-probe", collect)
    assert report["status"] == "complete"
    assert owner.actor_steps == owner.critic_steps == 2
    assert [item[1] for item in seen] == [0, 1, 1]
    assert seen[0][2] != seen[1][2] == seen[2][2]
    assert owner.used_window_ids == ["train-0", "probe", "train-1"]
    assert [item["mode"] for item in report["windows"]] == ["online", "evaluate", "online"]
    probe = report["windows"][1]
    assert probe["update"]["actor_optimizer_steps"] == probe["update"]["critic_optimizer_steps"] == 0
    assert probe["update"]["actor_or_critic_learning_forward_executed"] is False
    assert probe["evaluation_guard"]["learning_unchanged"] is True
    assert probe["evaluation_guard"]["rng_restored_exactly"] is True
    assert probe["evaluation_guard"]["rng_after_collection_sha256"] != probe["evaluation_guard"]["rng_before_sha256"]
    calls = [read_json(path) for path in (owner.output / "calls").glob("*.json")]
    assert {item["response"]["online_window_id"] for item in calls} == {"train-0", "probe", "train-1"}
    assert len(calls) == 3


def test_invalid_predeclared_window_mode_fails_before_any_sampling(tmp_path):
    from proworksim.online_training import run_online_windows

    with pytest.raises(ValueError, match="Each window mode"):
        run_online_windows(object(), {"windows": [{"window_id": "bad", "mode": "train", "slots": []}]},
                           tmp_path / "invalid-mode", lambda *args: pytest.fail("No sampling permitted"))
