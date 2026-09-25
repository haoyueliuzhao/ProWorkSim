"""CPU-only shared actor mechanics; these fixtures are not model work success."""

import copy
from types import SimpleNamespace

import pytest

from proworksim.online_training import (
    SharedActor, prepare_window, recipe_config, run_online_windows, tensor_tree_digest,
)
from proworksim.storage import digest, json_bytes


def _features(events, sequence, member, members):
    assert all(e["sequence"] < sequence for e in events if e["kind"] == "public_observation")
    return [0.0] * 30, {"fixture": True, "before_event_sequence": sequence}


def _response(identity, window="window-0"):
    return {"id": "actual-completion", "model": "toy", "system_fingerprint": identity["policy_version"],
            "actor_identity": identity, "online_window_id": window,
            "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
            "token_trace": {"input_ids": [1, 2], "output_ids": [3, 4], "input_mask": [0, 0],
                "output_mask": [1, 1], "behavior_logprobs": [-1.0, -2.0],
                "sampling_temperature": 0.7, "sampling_top_p": 1, "sampling_top_k": 0,
                "source": "actual generation token IDs and sampling logits, not retokenized text"}}


def _entry(identity, response=None, *, reward=0.0, window="window-0", slot="slot-0"):
    response = response or _response(identity, window)
    request = {"messages": [], "model": "toy", "temperature": 0.7, "max_tokens": 2}
    start = {"call_id": "call-" + slot, "stage": "started", "request_sha256": digest(json_bytes(request))}
    attempt = {"call_id": start["call_id"], "stage": "finished", "status": "success", "attempt_id": "a",
               "request": request, "response": {"body": response}}
    events = [
        {"sequence": 0, "worker_id": "provider", "kind": "public_observation", "payload": {}},
        {"sequence": 1, "worker_id": "provider", "kind": "model_call", "payload": start},
        {"sequence": 2, "worker_id": "provider", "kind": "model_attempt", "payload": attempt},
        {"sequence": 3, "worker_id": "provider", "kind": "model_response", "payload": {"call_id": start["call_id"], "response": response}},
    ]
    reward_record = {"eligible": True, "reward": reward, "episode_id": "episode-" + slot, "manifest_sha256": "manifest"}
    rollout = {"rollout_id": "episode-" + slot, "manifest_sha256": "manifest",
        "window": {"window_id": window}, "members": {"provider": {"origin": "target_model"}},
        "manifest": {"policies": {"provider": {"config": {"weight_identity": identity, "model_revision": identity["policy_version"]}}}},
        "events": events, "reward_eligibility": reward_record,
        "work_validity": {"components": {"record": {"value": True}}}}
    return {"slot_id": slot, "active_members": ["provider"], "rollout": rollout, "reward": reward_record}


def _identity():
    return {"version": "shared-actor-identity-v0.13", "policy_version": "p0", "adapter_sha256": "a",
            "base_manifest_sha256": "b", "inference_profile_sha256": "i"}


def test_admission_retains_failed_actions_all_rounds_and_fixed_slot_denominators():
    identity = _identity()
    entry = _entry(identity)
    # Another failed-format sampled decision is still an actor target.
    later = copy.deepcopy(entry["rollout"]["events"][1:])
    for event in later:
        event["sequence"] += 3
        event["payload"]["call_id"] = "later-real-call"
    entry["rollout"]["events"].extend(later)
    unknown = _entry(identity, slot="unknown")
    unknown["reward"]["eligible"] = False
    unknown["reward"]["reward"] = None
    data = prepare_window([entry, unknown], identity, "window-0", recipe_config(), _features)
    assert len(data["decisions"]) == 2
    assert {row["actor_denominator"] for row in data["decisions"]} == {8}
    assert {row["critic_denominator"] for row in data["decisions"]} == {4}
    assert data["slots"][1]["exclusions"] == ["reward_unknown_or_ineligible"]
    assert all(row["reward"] == 0 for row in data["decisions"])


def test_wrong_actual_actor_or_missing_output_never_silently_admitted():
    identity = _identity()
    wrong = _entry(identity)
    wrong["rollout"]["events"][-1]["payload"]["response"]["actor_identity"] = {**identity, "adapter_sha256": "another"}
    with pytest.raises(ValueError, match="Behavior actor"):
        prepare_window([wrong], identity, "window-0", recipe_config(), _features)
    missing = _entry(identity)
    missing["rollout"]["events"].pop()
    result = prepare_window([missing], identity, "window-0", recipe_config(), _features)
    assert result["decisions"] == []
    assert result["slots"][0]["members"]["provider"]["exclusions"] == ["complete_current_target_trajectory_unavailable"]


def test_sequence_limit_excludes_entire_member_without_cropping():
    identity = _identity()
    result = prepare_window([_entry(identity)], identity, "window-0", recipe_config({"max_length": 3}), _features)
    assert result["decisions"] == []
    assert result["slots"][0]["members"]["provider"]["exclusions"] == ["full_actual_sequence_exceeds_frozen_max_length"]


def _owner(tmp_path, torch, name="owner"):
    class TinyActor(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.lora_logits = torch.nn.Parameter(torch.zeros(7))
            self.config = SimpleNamespace(attention_dropout=0, use_cache=False)
            self.generation_config = SimpleNamespace(eos_token_id=99)

        def gradient_checkpointing_enable(self, **kwargs):
            self.checkpoint_kwargs = kwargs

        def forward(self, input_ids, attention_mask, use_cache, logits_to_keep):
            return SimpleNamespace(logits=self.lora_logits[None, None, :].expand(input_ids.shape[0], logits_to_keep, -1))

        def generate(self, input_ids, logits_processor, max_new_tokens, **kwargs):
            ids = input_ids
            for _ in range(max_new_tokens):
                scores = logits_processor[0](ids, self.lora_logits[None, :])
                chosen = torch.multinomial(scores.softmax(-1), 1)
                ids = torch.cat([ids, chosen], dim=1)
            return ids

    class Tokenizer:
        pad_token_id = 0

        def apply_chat_template(self, *args, **kwargs):
            return "real fixture prompt"

        def __call__(self, text, **kwargs):
            return {"input_ids": [1, 2]}

        def decode(self, ids, **kwargs):
            return "fixture output " + str(ids)

    return SharedActor(TinyActor(), Tokenizer(), output=tmp_path / name,
                       base_identity={"manifest": {"sha256": "fixture-base"}},
                       inference_profile={"native_tool_prompt": "single_call", "fixture": True},
                       recipe={"max_length": 64, "max_output_tokens": 2}, device="cpu", torch_module=torch)


def _sample_entry(owner, *, reward, slot="slot-0"):
    response = owner.transport.complete({"messages": [{"role": "user", "content": "fixture"}],
        "model": "toy", "temperature": 0.7, "max_tokens": 2}, timeout_seconds=10)
    assert response["http_status"] == 200
    return _entry(owner.freeze_identity(), response["body"], reward=reward, window=owner.window_id, slot=slot)


def test_two_real_cpu_sampling_update_cycles_share_optimizer_and_reload(tmp_path):
    torch = pytest.importorskip("torch")
    torch.manual_seed(13)
    owner = _owner(tmp_path, torch)
    optimizer_object = id(owner.actor_optimizer)
    previous_identity = owner.freeze_identity()
    for index in range(2):
        owner.begin_window("window-" + str(index))
        stale = owner.transport
        entry = _sample_entry(owner, reward=1.0)
        result = owner.update_window([entry], tmp_path / ("update-" + str(index)), feature_function=_features)
        assert result["status"] == "updated"
        assert result["actor_optimizer_steps"] == result["critic_optimizer_steps"] == 1
        assert result["behavior_probability_passed"] is True
        assert owner.freeze_identity() != previous_identity
        assert id(owner.actor_optimizer) == optimizer_object
        with pytest.raises(ValueError, match="Stale"):
            stale.complete({}, timeout_seconds=1)
        previous_identity = owner.freeze_identity()
    checkpoint = owner.save_checkpoint(tmp_path / "checkpoint")
    restored = _owner(tmp_path, torch, "restored")
    restored.restore_checkpoint(tmp_path / "checkpoint")
    assert restored.freeze_identity() == owner.freeze_identity()
    assert restored.actor_steps == restored.critic_steps == 2
    assert tensor_tree_digest(restored.actor_optimizer.state_dict(), torch) == tensor_tree_digest(owner.actor_optimizer.state_dict(), torch)
    assert tensor_tree_digest(restored.critic_optimizer.state_dict(), torch) == tensor_tree_digest(owner.critic_optimizer.state_dict(), torch)
    assert checkpoint["serialized_reload_exact"] is True


def test_zero_signal_keeps_actor_and_optimizer_unchanged_and_next_window_runs(tmp_path):
    torch = pytest.importorskip("torch")
    owner = _owner(tmp_path, torch)
    identity = owner.freeze_identity()
    initial_optimizer = tensor_tree_digest(owner.actor_optimizer.state_dict(), torch)
    owner.begin_window("window-0")
    stale = owner.transport
    result = owner.update_window([_sample_entry(owner, reward=0.0)], tmp_path / "zero", feature_function=_features)
    assert result["zero_signal_window"] is True
    assert result["actor_optimizer_steps"] == result["critic_optimizer_steps"] == 0
    assert result["advantages"] == [0.0]
    assert owner.freeze_identity() == identity
    assert tensor_tree_digest(owner.actor_optimizer.state_dict(), torch) == initial_optimizer
    with pytest.raises(ValueError, match="Window boundary"):
        owner.begin_window("window-0")
    owner.begin_window("window-1")
    with pytest.raises(ValueError, match="Stale"):
        stale.complete({}, timeout_seconds=1)
    assert _sample_entry(owner, reward=1)["reward"]["reward"] == 1


def test_behavior_probability_mismatch_cannot_update_either_optimizer(tmp_path):
    torch = pytest.importorskip("torch")
    owner = _owner(tmp_path, torch)
    owner.begin_window("window-0")
    entry = _sample_entry(owner, reward=1)
    entry["rollout"]["events"][-1]["payload"]["response"]["token_trace"]["behavior_logprobs"] = [-5.0, -5.0]
    result = owner.update_window([entry], tmp_path / "mismatch", feature_function=_features)
    assert result["status"] == "zero_step_probability_mismatch"
    assert owner.actor_steps == owner.critic_steps == 0


def test_runner_rejects_dropped_failure_slot(tmp_path):
    class Owner:
        actor_steps = critic_steps = 0

        def save_checkpoint(self, path):
            return {}

        def begin_window(self, window_id):
            return {}

        def freeze_identity(self):
            return {}

    with pytest.raises(ValueError, match="dropped a failure"):
        run_online_windows(Owner(), {"windows": [{"window_id": "w", "slots": [{"slot_id": "a"}, {"slot_id": "b"}]}]},
                           tmp_path / "run", lambda owner, spec, output: [{"slot_id": "a"}])


def test_direct_actual_token_limit_is_budget_rejection_before_generation(tmp_path):
    torch = pytest.importorskip("torch")
    owner = _owner(tmp_path, torch)
    owner.recipe["max_length"] = 3
    owner.begin_window("window-0")
    response = owner.transport.complete({"messages": [{"role": "user", "content": "fixture"}],
        "model": "toy", "temperature": 0.7, "max_tokens": 2}, timeout_seconds=10)
    assert response["http_status"] == 400
    assert response["body"]["error"]["code"] == "context_length_exceeded"
    assert response["body"]["generation_started"] is False
    assert "token_trace" not in response["body"]
    assert owner.actor_steps == 0


def test_evaluate_mode_collects_but_never_recomputes_or_updates(tmp_path):
    torch = pytest.importorskip("torch")
    owner = _owner(tmp_path, torch)
    before = owner._state_bundle()
    identity = owner.freeze_identity()

    def forbidden(*args, **kwargs):
        raise AssertionError("Evaluation must never call actor replay or critic forward")

    owner.model.forward = forbidden
    owner.critic.forward = forbidden

    def collect(actor, spec, output):
        seed = actor.reseed(27, label="predeclared-eval-case")
        assert seed["seed"] == 27
        return [_sample_entry(actor, reward=1, slot="eval-slot")]

    report = run_online_windows(owner, {"mode": "evaluate", "windows": [
        {"window_id": "eval-window", "slots": [{"slot_id": "eval-slot"}]}]}, tmp_path / "evaluate", collect)
    assert report["status"] == "complete"
    assert owner.freeze_identity() == identity
    assert owner.actor_steps == owner.critic_steps == 0
    final = owner._state_bundle()
    for field in ["actor", "critic", "actor_optimizer", "critic_optimizer"]:
        assert tensor_tree_digest(before[field], torch) == tensor_tree_digest(final[field], torch)
    assert report["windows"][0]["update"]["probability_recomputation_executed"] is False
    assert report["windows"][0]["update"]["actor_or_critic_learning_forward_executed"] is False
    assert len(list((owner.output / "sampling-seeds").glob("*.json"))) == 1


def test_reseed_requires_idle_episode_boundary_and_does_not_change_weights(tmp_path):
    torch = pytest.importorskip("torch")
    owner = _owner(tmp_path, torch)
    with pytest.raises(ValueError, match="idle collection boundary"):
        owner.reseed(13, label="before-window")
    owner.begin_window("seed-window")
    before = owner.freeze_identity()
    first = owner.reseed(31, label="declared-case-a")
    draw = torch.rand(3)
    second = owner.reseed(31, label="declared-case-b")
    assert first["rng_after_sha256"] == second["rng_after_sha256"]
    assert torch.equal(draw, torch.rand(3))
    assert owner.freeze_identity() == before
    owner.busy = True
    with pytest.raises(ValueError, match="idle collection boundary"):
        owner.reseed(42, label="during-generation")
