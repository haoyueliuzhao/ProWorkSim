"""Finite controls for metadata-only binding and one complete native trace."""
import copy
from types import SimpleNamespace

import pytest

from proworksim.storage import digest, json_bytes
from scripts import software_organization_capacity_qualification_v046 as candidate
from scripts.measure_organization_budget_v046 import PROTECTED_COMPONENTS
from scripts.run_ne_v021 import reference, write


class FakeOwner:
    def __init__(self):
        self.phase, self.busy, self.actor_steps, self.critic_steps = "idle", False, 3, 3
        self.torch = SimpleNamespace(is_tensor=lambda value: False)
        self.recipe = {"max_length": 16384, "max_output_tokens": 2048, "temperature": 0.7}
        self.inference_profile = {"max_context_tokens": 16384, "dtype": "bfloat16", "backend": "unchanged"}
        self.inference_profile_sha256 = digest(json_bytes(self.inference_profile))
        self._identity = self._make_identity()
        self.window_id = "neutral-test"
        self.side_effect = False

    def _make_identity(self):
        return {"adapter_sha256": "fixed", "base_manifest_sha256": "fixed-base", "policy_version": "online-3",
            "inference_profile_sha256": self.inference_profile_sha256}

    def freeze_identity(self):
        return copy.deepcopy(self._identity)

    def _state_bundle(self):
        result = {**dict.fromkeys(PROTECTED_COMPONENTS, 0), "recipe": self.recipe,
            "inference_profile": self.inference_profile, "actor_identity": self._identity}
        if self.side_effect and self.recipe["max_length"] == 18432:
            result["rng_cpu"] = 1
        return result


def common_fixture(tmp_path, owner):
    sha = candidate.tensor_tree_digest(owner._state_bundle(), owner.torch)
    write(tmp_path / "common.json", {"state_tensor_digest": sha, "training_rng_sha256": "rng-original"})
    return {"common": reference(tmp_path / "common.json"), "expected_actor_identity": owner.freeze_identity()}, {
        "state_sha256": sha, "rng_sha256": "rng-original", "actor_identity": owner.freeze_identity()}


def test_binding_protects_original_common_and_records_distinct_metadata_state(tmp_path):
    owner = FakeOwner()
    original, restored = common_fixture(tmp_path, owner)
    old_identity = owner.freeze_identity()
    binding = candidate.apply_capacity_binding(owner, original_plan=original, common_restore=restored)
    assert binding["passed"] and all(binding["protected_components_unchanged"].values())
    assert owner.recipe["max_length"] == owner.inference_profile["max_context_tokens"] == 18432
    assert binding["before_state_sha256"] == restored["state_sha256"] != binding["after_state_sha256"]
    assert restored["actor_identity"] == old_identity
    with pytest.raises(ValueError):
        candidate.apply_capacity_binding(owner, original_plan=original, common_restore=restored)


@pytest.mark.parametrize("change", ["common", "identity", "rng", "busy", "side_effect"])
def test_binding_rejects_wrong_state_or_side_effect(tmp_path, change):
    owner = FakeOwner()
    original, restored = common_fixture(tmp_path, owner)
    if change == "common":
        restored["state_sha256"] = "wrong"
    elif change == "identity":
        original["expected_actor_identity"] = {"adapter_sha256": "other"}
    elif change == "rng":
        restored["rng_sha256"] = "wrong"
    elif change == "busy":
        owner.busy = True
    else:
        owner.side_effect = True
    with pytest.raises(ValueError):
        candidate.apply_capacity_binding(owner, original_plan=original, common_restore=restored)


def response_fixture():
    owner = FakeOwner()
    owner.inference_profile = {**owner.inference_profile, "max_context_tokens": 18432}
    owner.inference_profile_sha256 = digest(json_bytes(owner.inference_profile))
    owner._identity = owner._make_identity()
    request = candidate.neutral_request(1, temperature=0.7)
    ids = [7] * 16384
    encoding = {"input_ids": ids, "prompt_tokens": 16384, "input_ids_sha256": digest(json_bytes(ids))}
    prepared = {"original_request_sha256": digest(json_bytes(request)), "selected_request_sha256": digest(json_bytes(request)),
        "prompt_tokens": 16384, "input_ids_sha256": encoding["input_ids_sha256"]}
    response = {"http_status": 200, "body": {"token_trace": {"input_ids": ids, "output_ids": [8, 9], "raw_output_ids": [8, 9]},
        "usage": {"prompt_tokens": 16384, "completion_tokens": 2, "total_tokens": 16386}, "raw_generated_text": "ack",
        "effective_generation": {"max_new_tokens": 2048}, "generation_stop_check": {"all_generated_tokens_retained": True},
        "actor_identity": owner.freeze_identity(), "inference_profile_sha256": owner.inference_profile_sha256,
        "online_window_id": owner.window_id, "choices": [{"finish_reason": "stop"}], "protocol_parse_error": "not a tool call"}}
    return response, prepared, encoding, request, owner


def test_native_capacity_qualification_accepts_nonempty_parse_error_without_execution():
    value = candidate.validate_response(*response_fixture())
    assert value["passed"] and value["protocol_parse_error"] == "not a tool call"
    assert value["implicit_truncation"] is False and value["usage"]["total_tokens"] == 16386


@pytest.mark.parametrize("change", ["input_crop", "output_crop", "empty", "usage", "reservation", "identity", "no_stop", "error"])
def test_native_trace_integrity_cannot_be_substituted_by_length_estimate(change):
    response, prepared, encoding, request, owner = response_fixture()
    body = response["body"]
    if change == "input_crop":
        body["token_trace"]["input_ids"] = body["token_trace"]["input_ids"][:-1]
    elif change == "output_crop":
        body["token_trace"]["raw_output_ids"] = [8, 9, 10]
    elif change == "empty":
        body["raw_generated_text"] = ""
    elif change == "usage":
        body["usage"]["total_tokens"] = 16387
    elif change == "reservation":
        body["effective_generation"]["max_new_tokens"] = 2047
    elif change == "identity":
        body["actor_identity"] = {}
    elif change == "no_stop":
        body["choices"] = []
    else:
        response["http_status"] = 503
    assert candidate.validate_response(response, prepared, encoding, request, owner)["passed"] is False
