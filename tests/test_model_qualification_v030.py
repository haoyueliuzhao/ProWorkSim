"""Actual tiny Torch sampling/gradients; no downloaded weights or GPU use.

The toy tokenizer emits ordinary gibberish, so these controls establish numerical
and restore behavior, not successful native tools or software model performance.
"""
import copy
import json
import re
from types import SimpleNamespace

import pytest

from proworksim import model_qualification_v030 as qualification
from proworksim.online_training import SharedActor, tensor_tree_digest


def owner_fixture(tmp_path, torch, *, early_eos=False):
    class TinyActor(torch.nn.Module):
        def __init__(self):
            super().__init__()
            logits = torch.tensor([0.1, 0.2, -0.2, 0.3, -0.1, 0.0, 0.4])
            if early_eos:
                logits[6] = 20.0
            self.lora_logits = torch.nn.Parameter(logits)
            self.config = SimpleNamespace(attention_dropout=0, use_cache=False)
            self.generation_config = SimpleNamespace(eos_token_id=6 if early_eos else 99)

        def gradient_checkpointing_enable(self, **kwargs):
            self.checkpoint_kwargs = kwargs

        def forward(self, input_ids, attention_mask, use_cache, logits_to_keep):
            return SimpleNamespace(logits=self.lora_logits[None, None, :].expand(
                input_ids.shape[0], logits_to_keep, -1))

        def generate(self, input_ids, logits_processor, max_new_tokens, **kwargs):
            ids = input_ids
            for _ in range(max_new_tokens):
                scores = logits_processor[0](ids, self.lora_logits[None, :])
                chosen = torch.multinomial(scores.softmax(-1), 1)
                ids = torch.cat([ids, chosen], dim=1)
                if int(chosen[0, 0]) == self.generation_config.eos_token_id:
                    break
            return ids

    class Tokenizer:
        pad_token_id = 0

        def apply_chat_template(self, messages, **kwargs):
            return json.dumps({"messages": messages, "tools": kwargs.get("tools", [])})

        def __call__(self, text, **kwargs):
            return {"input_ids": [len(word) % 7 for word in re.findall(r"\w+|[^\w\s]", text)]}

        def decode(self, ids, **kwargs):
            return "".join("abcdefg"[value] for value in ids)

    torch.manual_seed(74)
    owner = SharedActor(TinyActor(), Tokenizer(), output=tmp_path / "owner",
        base_identity={"manifest": {"sha256": "tiny-real-sampled-control"}},
        inference_profile={"native_tool_prompt": "single_call", "fixture": True},
        recipe={"max_length": 16384, "max_output_tokens": 2048}, device="cpu", torch_module=torch)
    owner.recipe["members"] = list(qualification.MEMBERS)
    owner.save_checkpoint(tmp_path / "common")
    return owner


def actual_one_call_return(owner, folder):
    expected = owner.freeze_identity()
    snapshot = owner.capture_evaluation_state()
    owner.begin_window("tiny-updated-return-fragment")
    response = owner.complete({"model": "tiny", "temperature": owner.recipe["temperature"],
        "max_tokens": 1, "messages": [{"role": "user", "content": "one actual technical return call"}]},
        timeout_seconds=900)
    owner.finish_evaluation([], folder)
    guard = owner.finish_evaluation_guard(snapshot)
    assert response["http_status"] == 200
    assert guard["learning_unchanged"] and guard["rng_restored_exactly"]
    return {"calls": 1, "expected_actor_identity": expected,
            "observed_actor_identities": [response["body"]["actor_identity"]],
            "window_ids": [response["body"]["online_window_id"]],
            "learning_unchanged": True, "rng_restored_exactly": True,
            "scope": "tiny CPU owner call tests callback boundary; real protocol callback owns SDK execution"}


def test_all_four_actual_traces_include_malformed_stress_in_one_update_then_exact_restore(tmp_path):
    torch = pytest.importorskip("torch")
    owner = owner_fixture(tmp_path, torch)
    before = tensor_tree_digest(owner._state_bundle(), torch)
    optimizer_ids = id(owner.actor_optimizer), id(owner.critic_optimizer)
    stages = []
    result = qualification.qualify(owner, tmp_path / "qualification", common_dir=tmp_path / "common",
        return_probe=actual_one_call_return, on_stage=lambda kind, label: stages.append((kind, label)))
    assert result["errors"] == []
    assert result["native_calls_executed"] == 4
    assert all(call["actual_trace_complete"] for call in result["calls"])
    assert result["calls"][3]["finish_reason"] == "length"
    assert result["calls"][3]["interface_passed"] is False
    assert result["calls"][3]["total_tokens"] >= 15360
    update = result["update"]
    assert update["status"] == "one_aggregate_diagnostic_update_completed"
    assert update["actor_optimizer_steps"] == update["critic_optimizer_steps"] == 1
    assert update["backward_decisions_completed"] == 4
    assert update["changed_actor_elements"] > 0 and update["changed_critic_elements"] > 0
    assert all(row["passed"] for row in update["behavior_probability_checks"])
    assert all(row["passed"] for row in update["gradient_probability_checks"])
    assert update["persistent_optimizer_objects_reused"]
    for call, loss in zip(result["calls"], update["losses"], strict=True):
        assert loss["actor_denominator"] == 4 * call["output_tokens"]
        assert loss["output_tokens"] == call["output_tokens"]
        response = json.loads((tmp_path / "qualification" / f"native-call-{call['index'] + 1}" / "response.json").read_text())
        trace = response["body"]["token_trace"]
        assert trace["output_ids"] == trace["raw_output_ids"]
        assert trace["behavior_logprobs"] == trace["raw_behavior_logprobs"]
    assert result["training_integration_ready"] and result["near_16k_capacity_demonstrated"]
    assert not result["inference_ready"] and not result["training_ready"]  # Toy gibberish is not native competence.
    assert result["return_probe"]["calls"] == 1
    assert result["checkpoint_roundtrip"]["updated_reload_exact"]
    assert result["checkpoint_roundtrip"]["common_reload_exact"]
    assert result["common_restored_exactly"] and result["diagnostic_gradients_cleared"]
    assert tensor_tree_digest(owner._state_bundle(), torch) == before
    assert (id(owner.actor_optimizer), id(owner.critic_optimizer)) == optimizer_ids
    assert owner.actor_steps == owner.critic_steps == owner.policy_revision == 0
    assert owner.phase == "idle" and not owner.busy
    assert [kind for kind, _ in stages].count("qualification_inference") == 4
    assert [kind for kind, _ in stages].count("qualification_update") == 1


@pytest.mark.parametrize("gradient_only", [False, True])
def test_real_behavior_or_gradient_probability_mismatch_has_no_optimizer_step(tmp_path, gradient_only):
    torch = pytest.importorskip("torch")
    owner = owner_fixture(tmp_path, torch, early_eos=True)
    before = tensor_tree_digest(owner._state_bundle(), torch)
    actual = owner.learning_logprobs

    def mismatched(trace):
        values = actual(trace)
        return values + 0.1 if not gradient_only or torch.is_grad_enabled() else values

    owner.learning_logprobs = mismatched
    result = qualification.qualify(owner, tmp_path / "qualification", common_dir=tmp_path / "common",
        return_probe=lambda *_: pytest.fail("probability failure must not generate a return probe"))
    assert result["native_calls_executed"] == 4
    expected = "zero_step_gradient_probability_mismatch" if gradient_only else "zero_step_behavior_probability_mismatch"
    assert result["update"]["status"] == expected
    assert result["update"]["actor_optimizer_steps"] == result["update"]["critic_optimizer_steps"] == 0
    assert result["common_restored_exactly"] and result["diagnostic_gradients_cleared"]
    assert result["capacity_status"] == "capacity_not_demonstrated"
    assert not result["training_ready"]
    assert tensor_tree_digest(owner._state_bundle(), torch) == before


def test_short_natural_eos_never_claims_near_16k_or_adds_generations(tmp_path):
    torch = pytest.importorskip("torch")
    owner = owner_fixture(tmp_path, torch, early_eos=True)
    # A non-degenerate high EOS probability retains a measurable actor gradient.
    with torch.no_grad():
        owner.model.lora_logits[6] = 5.0
    owner._identity = owner._make_identity()
    owner.save_checkpoint(tmp_path / "short-common")
    result = qualification.qualify(owner, tmp_path / "qualification", common_dir=tmp_path / "short-common",
                                   return_probe=actual_one_call_return)
    assert result["errors"] == []
    assert result["native_calls_executed"] == 4
    assert result["calls"][3]["total_tokens"] < 15360
    assert not result["near_16k_capacity_demonstrated"]
    assert result["capacity_status"] == "capacity_not_demonstrated"
    assert not result["training_ready"]
    for path in (tmp_path / "qualification").glob("native-call-*/request.json"):
        request = json.loads(path.read_text())
        assert request["max_tokens"] == 2048
        assert "min_new_tokens" not in request and "eos_token_id" not in request


def test_long_fixture_is_real_and_valid_native_history_is_preserved(tmp_path):
    torch = pytest.importorskip("torch")
    owner = owner_fixture(tmp_path, torch, early_eos=True)
    folder = tmp_path / "public"
    folder.mkdir()
    fixture = qualification._public_fixture(folder)
    prior = [{"role": "user", "content": "Read public-note.json"},
             {"role": "assistant", "content": None, "tool_calls": [{"id": "read12345", "type": "function",
                "function": {"name": "read_public_note", "arguments": '{"path":"public-note.json"}'}}]},
             {"role": "tool", "tool_call_id": "read12345", "content": json.dumps(qualification.NOTE)}]
    original = copy.deepcopy(prior)
    request, measured = qualification._request(owner, 1, fixture, qualification.NOTE, prior)
    assert request["messages"][1:4] == original
    assert prior == original
    assert 8192 - 128 <= measured["actual_rendered_prompt_tokens"] <= 8192
    assert measured["fixture_last_line"] > 0
    prefix = "".join(fixture["lines"][:measured["fixture_last_line"]])
    assert prefix in request["messages"][-1]["content"]
    assert fixture["source"].read_text().startswith(prefix)
