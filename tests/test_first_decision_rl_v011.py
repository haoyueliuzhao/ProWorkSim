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
