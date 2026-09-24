"""Offline token/reward admission checks; these are not model or GPU experiments."""

import copy

import pytest

from scripts.first_decision_rl_v011 import (
    NODE,
    REVISION,
    compare_logprobs,
    extract_first_decision,
)


def evidence(reward_value=0):
    config = {
        "backend_id": "local-qwen-http",
        "model": "Qwen2.5-7B-Instruct",
        "model_revision": REVISION,
        "temperature": 0.3,
        "action_protocol": "single_decision_json",
        "weight_identity": {"path": "/base", "manifest": "/frozen-base.json"},
    }
    trace = {
        "input_ids": [11, 12],
        "output_ids": [13, 14, 15],
        "input_mask": [0, 0],
        "output_mask": [1, 1, 1],
        "behavior_logprobs": [-0.1, -0.2, -0.3],
        "sampling_temperature": 0.3,
        "sampling_top_p": 1.0,
        "sampling_top_k": 0,
        "source": "actual generation token IDs and sampling logits, not retokenized text",
    }
    response = {
        "id": "real-shape-simulated-data",
        "model": config["model"],
        "system_fingerprint": REVISION,
        "token_trace": trace,
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        "effective_generation": {
            "do_sample": True,
            "temperature": 1.0,
            "top_p": 1.0,
            "top_k": 0,
            "repetition_penalty": 1.0,
        },
    }
    starts = {
        "kind": "model_call",
        "worker_id": "analyst",
        "sequence": 0,
        "payload": {
            "call_id": "first-real-draw",
            "stage": "started",
            "decision_index": 1,
            "model_revision": REVISION,
        },
    }
    attempt = {
        "kind": "model_attempt",
        "worker_id": "analyst",
        "sequence": 1,
        "payload": {
            "call_id": "first-real-draw",
            "stage": "finished",
            "status": "success",
            "response": {"body": response},
        },
    }
    actual = {
        "kind": "model_response",
        "worker_id": "analyst",
        "sequence": 2,
        "payload": {"call_id": "first-real-draw", "response": response},
    }
    history = {"events": [starts, attempt, actual]}
    manifest = {
        "episode_id": "episode",
        "status": "closed",
        "policies": {
            "analyst": {"implementation": "proworksim.model_policy.ModelPolicy", "config": config}
        },
        "responsibility": {"work_nodes": [NODE]},
        "experience": {"start": 0, "end": 3},
    }
    reward = {"episode_id": "episode", "eligible": True, "reward": reward_value, "exclusions": []}
    return manifest, history, reward


def extract(manifest, history, reward, **kwargs):
    return extract_first_decision(
        manifest, history, reward, capture_matches={"analyst": True, "reviewer": True}, **kwargs
    )


def test_zero_reward_is_retained_with_actual_masks_and_constant_baseline():
    manifest, history, reward = evidence(0)
    before = copy.deepcopy([manifest, history, reward])
    result = extract(manifest, history, reward)
    assert result["eligible"] and result["reward"] == 0 and result["advantage"] == -0.5
    assert result["labels"] == [-100, -100, 13, 14, 15]
    assert result["loss_mask"] == [0, 0, 1, 1, 1]
    assert result["token_trace"]["behavior_logprobs"] == [-0.1, -0.2, -0.3]
    assert [manifest, history, reward] == before


def test_positive_reward_has_equal_episode_scope_and_no_resampling_selection():
    manifest, history, reward = evidence(1)
    first = extract(manifest, history, reward)
    assert first["eligible"] and first["advantage"] == 0.5
    # A later candidate cannot replace a first draw selected before outcomes.
    extra = copy.deepcopy(history["events"])
    for event in extra:
        event["sequence"] += 3
        event["payload"]["call_id"] = "later-draw"
        if event["kind"] == "model_call":
            event["payload"]["decision_index"] = 2
        if event["kind"] == "model_response":
            event["payload"]["response"]["token_trace"]["output_ids"] = [80, 81, 82]
    history["events"] += extra
    manifest["experience"]["end"] = 6
    assert extract(manifest, history, reward)["token_trace"]["output_ids"] == [13, 14, 15]


@pytest.mark.parametrize(
    "matches", [None, {}, {"analyst": False}, {"analyst": True, "reviewer": False}]
)
def test_missing_or_failed_raw_capture_match_is_never_training_input(matches):
    manifest, history, reward = evidence()
    result = extract_first_decision(manifest, history, reward, capture_matches=matches)
    assert not result["eligible"]
    assert result["exclusions"][0]["kind"] == "public_capture_unverified"


def test_unknown_or_service_reward_keeps_null_and_explicit_exclusion():
    manifest, history, reward = evidence()
    reward.update(eligible=False, reward=None, exclusions=[{"reason": "Observed service failure"}])
    result = extract(manifest, history, reward)
    assert not result["eligible"] and result["reward"] is None
    assert result["exclusions"][0]["reasons"] == reward["exclusions"]


def test_length_exclusion_retains_entire_original_tokens_without_cropping():
    manifest, history, reward = evidence()
    result = extract(manifest, history, reward, max_length=4)
    assert not result["eligible"]
    assert result["sequence_tokens"] == 5 and result["token_trace"]["output_ids"] == [13, 14, 15]
    assert result["exclusions"] == [
        {"kind": "length_limit", "actual": 5, "maximum": 4, "truncated": False}
    ]


@pytest.mark.parametrize(
    "change",
    ["teacher", "revision", "updated_adapter", "mask", "usage", "temperature", "extra_transform"],
)
def test_unreproducible_or_non_behavior_data_is_rejected(change):
    manifest, history, reward = evidence()
    config = manifest["policies"]["analyst"]["config"]
    response = history["events"][2]["payload"]["response"]
    if change == "teacher":
        config["backend_id"] = "deepseek-official"
    elif change == "revision":
        config["model_revision"] = "later-finetuned-weights"
    elif change == "updated_adapter":
        config["weight_identity"]["adapter_sha256"] = "new-parameters"
    elif change == "mask":
        response["token_trace"]["output_mask"] = [1, 0, 1]
    elif change == "usage":
        response["usage"]["completion_tokens"] = 4
    elif change == "temperature":
        response["token_trace"]["sampling_temperature"] = 0.7
    else:
        response["effective_generation"]["repetition_penalty"] = 1.05
    with pytest.raises(ValueError):
        extract(manifest, history, reward)


def test_no_missing_probabilities_are_reconstructed_from_generated_text():
    manifest, history, reward = evidence()
    response = history["events"][2]["payload"]["response"]
    response["token_trace"]["behavior_logprobs"] = None
    response["raw_generated_text"] = "A perfectly plausible successful response"
    result = extract(manifest, history, reward)
    assert not result["eligible"]
    assert result["exclusions"][0]["kind"] == "actual_behavior_logprobs_missing_or_invalid"


def test_first_decision_transport_retry_is_reported_not_replaced():
    manifest, history, reward = evidence()
    failed = copy.deepcopy(history["events"][1])
    failed["payload"]["status"] = "service_error"
    history["events"].insert(1, failed)
    manifest["experience"]["end"] = 4
    result = extract(manifest, history, reward)
    assert not result["eligible"]
    assert result["exclusions"][0]["kind"] == "first_decision_service_retry_or_unavailable"


def test_logprob_tolerance_preserves_all_raw_values_and_signed_errors():
    actual, behavior = [-0.12, -0.19], [-0.1, -0.2]
    result = compare_logprobs(actual, behavior, 0.2, 0.03)
    assert result["passed"] and result["recomputed_logprobs"] == actual
    assert result["actual_behavior_logprobs"] == behavior
    assert len(result["signed_delta"]) == 2
    assert result["sequence_sum_delta"] == pytest.approx(-0.01)
    assert not compare_logprobs([-0.7, -0.2], behavior, 0.2, 0.03)["passed"]
    with pytest.raises(ValueError):
        compare_logprobs([float("nan")], [-0.1], 0.2, 0.03)


def batch_evidence(tmp_path):
    import json
    from scripts.first_decision_rl_v011 import original_batch_groups

    rows = []
    for index in range(3):
        manifest, history, reward = evidence(0)
        body = history["events"][2]["payload"]["response"]
        body["id"] = "original-local-" + str(index)
        body["service_record"] = {
            "batch_index": 2 if index == 0 else 3,
            "batch_size": 1 if index == 0 else 2,
        }
        body["effective_generation"]["pad_token_id"] = 0
        row = extract(manifest, history, reward)
        row["episode_name"] = "finance-direct-qwen-" + str(index + 1)
        rows.append(row)
        (tmp_path / (body["id"] + ".json")).write_text(
            json.dumps({"request": {"model": body["model"]}, "response": body})
        )
    return rows, original_batch_groups


def test_replay_batch_membership_uses_complete_original_ledger_without_inventing_row_index(
    tmp_path,
):
    rows, group = batch_evidence(tmp_path)
    batches = group(rows, tmp_path)
    assert [item["indices"] for item in batches] == [[0], [1, 2]]
    assert [item["batch_size"] for item in batches] == [1, 2]
    assert batches[1]["original_recorded_row_indices"] == [None, None]
    assert "not backfilled" in batches[1]["replay_row_order"]
    assert all(item["original_service_files"] for item in batches)


def test_replay_rejects_silently_dropping_original_batch_peer(tmp_path):
    rows, group = batch_evidence(tmp_path)
    with pytest.raises(ValueError, match="peers"):
        group(rows[:2], tmp_path)


def test_replay_rejects_changed_original_service_response(tmp_path):
    import json

    rows, group = batch_evidence(tmp_path)
    file = tmp_path / "original-local-1.json"
    record = json.loads(file.read_text())
    record["response"]["token_trace"]["behavior_logprobs"][0] = -2
    file.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="ledger"):
        group(rows, tmp_path)


def test_replay_rejects_undeclared_extra_peer(tmp_path):
    import json

    rows, group = batch_evidence(tmp_path)
    extra = copy.deepcopy(rows[1]["first_response"])
    extra["id"] = "extra-peer"
    (tmp_path / "extra-peer.json").write_text(json.dumps({"response": extra}))
    with pytest.raises(ValueError, match="peers"):
        group(rows, tmp_path)


def test_cached_replay_keeps_prefix_gradients_and_complete_output_targets():
    from types import SimpleNamespace
    from scripts.first_decision_rl_v011 import cached_batch_logprobs

    torch = pytest.importorskip("torch")
    torch.manual_seed(11)

    class TinyCausal(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.embedding = torch.nn.Embedding(9, 4, dtype=torch.float64)
            self.projection = torch.nn.Linear(4, 9, bias=False, dtype=torch.float64)

        def prepare_inputs_for_generation(self, ids, **kwargs):
            return {
                "input_ids": ids if kwargs["past_key_values"] is None else ids[:, -1:],
                **kwargs,
            }

        def forward(self, input_ids, attention_mask, past_key_values, **kwargs):
            mask = attention_mask[:, -input_ids.shape[1] :, None]
            additions = (self.embedding(input_ids) * mask).sum(dim=1)
            hidden = additions if past_key_values is None else past_key_values + additions
            return SimpleNamespace(logits=self.projection(hidden)[:, None], past_key_values=hidden)

        def _update_model_kwargs_for_generation(self, output, kwargs, **unused):
            return {
                **kwargs,
                "past_key_values": output.past_key_values,
                "attention_mask": torch.cat(
                    (kwargs["attention_mask"], torch.ones_like(kwargs["attention_mask"][:, :1])),
                    dim=1,
                ),
                "cache_position": kwargs["cache_position"][-1:] + 1,
            }

    rows = [
        {
            "input_tokens": 2,
            "output_tokens": 3,
            "token_trace": {"input_ids": [1, 2], "output_ids": [3, 4, 5]},
            "first_response": {"effective_generation": {"pad_token_id": 0}},
        },
        {
            "input_tokens": 1,
            "output_tokens": 2,
            "token_trace": {"input_ids": [6], "output_ids": [7, 8]},
            "first_response": {"effective_generation": {"pad_token_id": 0}},
        },
    ]
    net = TinyCausal().eval()
    cached = cached_batch_logprobs(net, rows, torch=torch, device="cpu")
    prefix = []
    for row in rows:
        values = []
        for index, chosen in enumerate(row["token_trace"]["output_ids"]):
            ids = torch.tensor(
                [row["token_trace"]["input_ids"] + row["token_trace"]["output_ids"][:index]]
            )
            actual = net(ids, torch.ones_like(ids), None).logits[0, -1].float() / 0.3
            values.append(torch.log_softmax(actual, dim=-1)[chosen])
        prefix.append(torch.stack(values))
    for index, row in enumerate(rows):
        torch.testing.assert_close(
            cached[index, : row["output_tokens"]], prefix[index], rtol=1e-12, atol=1e-12
        )
    loss = 0.5 * sum(cached[i, : row["output_tokens"]].sum() for i, row in enumerate(rows)) / 2
    loss.backward()
    cached_grad = net.embedding.weight.grad.clone()
    assert cached_grad[1].abs().sum() > 0 and cached_grad[6].abs().sum() > 0
    net.zero_grad(set_to_none=True)
    (0.5 * sum(value.sum() for value in prefix) / 2).backward()
    torch.testing.assert_close(cached_grad, net.embedding.weight.grad, rtol=1e-12, atol=1e-12)


def test_resident_parameter_views_and_lossless_activation_storage_preserve_gradients():
    from types import SimpleNamespace
    from scripts.first_decision_rl_v011 import ParameterResidentSavedTensors

    torch = pytest.importorskip("torch")
    torch.manual_seed(21)

    class StorageToy(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.randn(4, 4, dtype=torch.float64))
            self.frozen = torch.nn.Parameter(
                torch.randn(4, 4, dtype=torch.float64), requires_grad=False
            )
            self.config = SimpleNamespace(num_attention_heads=4, num_key_value_heads=2)

    network = StorageToy()
    hook = ParameterResidentSavedTensors(network, torch=torch, max_rss_bytes=64 * 1024**3)
    transposed = network.weight.t()
    packed = hook.pack(transposed)
    assert packed.cpu_bytes == 0
    unpacked = hook.unpack(packed)
    assert unpacked.untyped_storage().data_ptr() == network.weight.untyped_storage().data_ptr()
    assert unpacked.stride() == transposed.stride()

    source = torch.randn(1, 2, 3, 4, dtype=torch.float64, requires_grad=True)
    independent = source.detach().clone().requires_grad_()

    def objective(value):
        repeated = value.repeat_interleave(2, dim=1)
        output = repeated.square().sum()
        # A frozen parameter transpose is saved for the input gradient; keeping
        # its original storage avoids copying the full weights per cache step.
        return (
            output
            + (value.reshape(-1, 4) @ network.frozen.t() @ network.weight.t()).t().square().sum()
        )

    with hook:
        actual = objective(source)
        actual.backward()
    actual_parameter_grad = network.weight.grad.clone()
    network.weight.grad = None
    expected = objective(independent)
    expected.backward()
    torch.testing.assert_close(actual_parameter_grad, network.weight.grad, rtol=0, atol=0)
    torch.testing.assert_close(actual, expected, rtol=0, atol=0)
    torch.testing.assert_close(source.grad, independent.grad, rtol=0, atol=0)
    assert hook.stats["retained_parameter_refs"] >= 2
    assert hook.stats["exact_repeated_head_refs"] >= 1
    assert hook.stats["offloaded_activation_bytes"] < hook.stats["raw_activation_bytes"]

    expanded = torch.tensor([[-0.0, 2.0]], dtype=torch.float64).expand(3, 2)
    returned = hook.unpack(hook.pack(expanded))
    assert returned.stride() == expanded.stride()
    assert torch.equal(
        returned.contiguous().view(torch.uint8), expanded.contiguous().view(torch.uint8)
    )
    signed = torch.zeros(1, 4, 3, 4, dtype=torch.float64)
    signed[:, 1] = -0.0
    packet = hook.pack(signed)
    assert packet.repeat_heads == 1  # Numeric equality is insufficient for a lossless byte claim.
    assert torch.equal(hook.unpack(packet).view(torch.uint8), signed.view(torch.uint8))


def test_saved_data_rss_limit_is_explicit_and_stops_before_copy():
    from scripts.first_decision_rl_v011 import ParameterResidentSavedTensors, TrainingResourceLimit

    torch = pytest.importorskip("torch")
    hook = ParameterResidentSavedTensors(torch.nn.Linear(2, 2), torch=torch, max_rss_bytes=1)
    with pytest.raises(TrainingResourceLimit) as failed:
        hook.pack(torch.ones(2))
    assert failed.value.details["observed_rss_bytes"] > 1
    assert hook.stats["offloaded_activation_bytes"] == 0
