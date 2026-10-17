"""Finite CPU input/identity/stopping controls; never load model weights/CUDA."""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim.online_training import DirectContextLimit
from proworksim.software_calibration_runtime_v051 import (
    CalibrationActor, compare_pair_inputs, completion_kind, generation_options,
    load_actor, loading_info_record, prepare_native_input, validate_contract, validate_native_input,
)
from proworksim.storage import json_bytes


def contract(**changes):
    return {"context_limit": 131072, "max_output_tokens": 81920,
        "enable_thinking": True, "preserve_thinking": False,
        "temperature": .6, "top_p": .95, "top_k": 20,
        "repetition_penalty": 1., "eos_token_ids": [248046, 248044],
        "pad_token_id": 248046,
        "max_generation_seconds": 7200., **changes}


class Tokenizer:
    def apply_chat_template(self, messages, **kwargs):
        self.messages, self.kwargs = copy.deepcopy(messages), kwargs
        return json.dumps({"messages": messages, "thinking": kwargs["enable_thinking"]})

    def __call__(self, text, *, add_special_tokens):
        assert add_special_tokens is False
        return {"input_ids": list(text.encode())}


def request():
    return {"model": "raw-qwen", "temperature": .6, "max_tokens": 81920,
            "messages": [{"role": "user", "content": "Write code."}], "tools": []}


def test_actual_rendering_and_ids_match_across_paths_without_tool_hint():
    first, second = Tokenizer(), Tokenizer()
    a, b = (prepare_native_input(t, request(), contract()) for t in (first, second))
    assert compare_pair_inputs(a, b)["passed"]
    assert a["input_ids"] == list(a["rendered_prompt"].encode())
    assert first.kwargs["enable_thinking"] is True
    assert a["single_call_hint_applied"] is False
    assert validate_native_input(a, contract())


def test_research_mode_is_a_separate_explicit_contract():
    c = contract(context_limit=18432, max_output_tokens=2048, enable_thinking=False,
                 temperature=.7, top_p=1., top_k=0, max_generation_seconds=5400)
    tok = Tokenizer()
    row = prepare_native_input(tok, request(), c)
    assert tok.kwargs["enable_thinking"] is False
    assert row["requested_output_tokens"] == 2048


def test_native_tool_hint_only_for_declared_tool_requests():
    r = request()
    r["tools"] = [{"type": "function", "function": {"name": "read_file", "parameters": {}}}]
    tok = Tokenizer()
    row = prepare_native_input(tok, r, contract())
    assert row["single_call_hint_applied"]
    assert tok.messages[0]["role"] == "system"
    assert "exactly one native <tool_call>" in tok.messages[0]["content"]
    assert tok.kwargs["tools"] == r["tools"]
    assert r["messages"][0]["role"] == "user"


@pytest.mark.parametrize("change", [
    {"temperature": float("nan")}, {"top_p": 1.1}, {"top_k": True},
    {"context_limit": 100, "max_output_tokens": 100}, {"enable_thinking": 1},
    {"max_generation_seconds": float("inf")}, {"repetition_penalty": 1.2},
    {"eos_token_ids": [248046]}, {"max_output_tokens": 0},
])
def test_rejects_undeclared_or_nonfinite_decoder(change):
    with pytest.raises(ValueError):
        validate_contract(contract(**change))


def test_filters_and_temperature_are_not_applied_twice():
    options = generation_options(contract(), pad_token_id=248046)
    assert (options["temperature"], options["top_p"], options["top_k"]) == (1., 1., 0)
    assert options["max_new_tokens"] == 81920
    assert options["max_time"] == 7200
    assert options["eos_token_id"] == [248046, 248044]


def test_changed_actual_tokens_or_contract_are_not_reinterpreted():
    row = prepare_native_input(Tokenizer(), request(), contract())
    changed = copy.deepcopy(row)
    changed["input_ids"][0] += 1
    with pytest.raises(ValueError):
        validate_native_input(changed, contract())
    with pytest.raises(ValueError):
        validate_native_input(row, contract(temperature=.7))
    assert not compare_pair_inputs(row, changed)["passed"]


def test_capacity_rejection_precedes_any_model_verification():
    c = contract(context_limit=10, max_output_tokens=9)
    row = prepare_native_input(Tokenizer(), request(), c)
    assert not row["fits"]
    actor = CalibrationActor.__new__(CalibrationActor)
    actor.contract, actor.phase, actor.busy = c, "collecting", False
    actor._verify_execution = lambda: pytest.fail("A rejected input must not enter model execution")
    with pytest.raises(DirectContextLimit):
        actor.generate_native(row)


def test_eos_length_and_time_censoring_are_distinct():
    c = contract(max_output_tokens=3)
    assert completion_kind([12, 248046], c, 2) == "stop"
    assert completion_kind([12, 13, 14], c, 2) == "length"
    assert completion_kind([12], c, 7200.1) == "time_limit"
    with pytest.raises(ValueError, match="tail crop"):
        completion_kind([248046, 12], c, 2)
    with pytest.raises(ValueError, match="identified"):
        completion_kind([12], c, 2)


def test_frozen_native_end_first_stop_union_and_explicit_pad():
    c = contract(eos_token_ids=[248044, 248046], pad_token_id=248044)
    options = generation_options(c, pad_token_id=248044)
    assert options["eos_token_id"] == [248044, 248046]
    assert options["pad_token_id"] == 248044
    assert completion_kind([12, 248044], c, 1) == "stop"
    assert completion_kind([12, 248046], c, 1) == "stop"
    with pytest.raises(ValueError, match="pad token"):
        generation_options(c, pad_token_id=248046)


def test_one_raw_resident_switches_only_the_declared_attention(tmp_path):
    actor = CalibrationActor.__new__(CalibrationActor)
    calls = []
    actor.model = SimpleNamespace(set_attn_implementation=calls.append)
    actor.busy, actor.path, actor._path_switches = False, "reference", 0
    actor._identity = {"raw_release": True, "checkpoint": None, "policy_version": "before"}
    actor.inference_profile = {"path": "reference", "contract": contract()}
    actor.output, actor._verify_execution = tmp_path, lambda: None
    result = actor.select_path("project")
    assert calls == ["sdpa_bf16_explicit_kv_v020"]
    assert result["model_reloaded"] is False
    assert result["weights_modified"] is False
    assert actor.select_path("project")["changed"] is False
    assert len(calls) == 1
    actor._identity["checkpoint"] = {"path": "S_star"}
    with pytest.raises(ValueError, match="raw-release"):
        actor.select_path("reference")


def test_world_client_receives_known_usage_and_preserved_native_timeout(tmp_path):
    actor = CalibrationActor.__new__(CalibrationActor)
    actor.contract, actor.window_id = contract(), "CPU-window"
    actor._identity = {"policy_version": "CPU-only-fixture"}
    actor.inference_profile, actor.inference_profile_sha256 = {}, "fixture"
    actor.output = tmp_path
    (tmp_path / "calls").mkdir()

    def generate(row):
        return {"raw_generated_text": "print(1)", "output_ids": [7], "behavior_logprobs": [-1.],
            "finish_reason": "time_limit", "usage": {"prompt_tokens": row["prompt_tokens"],
                "completion_tokens": 1, "total_tokens": row["prompt_tokens"] + 1},
            "effective_generation": {}, "execution_metadata": {}, "seconds": 7200.1}

    actor.tokenizer, actor.generate_native = Tokenizer(), generate
    response = actor.complete(request(), timeout_seconds=7300)
    assert response["http_status"] == 200
    assert response["body"]["choices"][0]["finish_reason"] == "length"
    assert response["body"]["native_finish_reason"] == "time_limit"
    assert response["body"]["usage"]["completion_tokens"] == 1
    assert len(list((tmp_path / "calls").glob("*.json"))) == 1


def test_reference_path_rejects_retained_checkpoint_before_loading():
    with pytest.raises(ValueError, match="Reference is raw"):
        load_actor("nonexistent", manifest="nonexistent", contract=contract(),
                   path="reference", output="nonexistent", checkpoint="S_star.json")


def test_transformers5_loading_key_sets_serialize_without_losing_source_shape():
    info = {"missing_keys": set(), "unexpected_keys": {"model.visual.b", "model.visual.a"},
            "mismatched_keys": set(), "error_msgs": []}
    before = copy.deepcopy(info)
    serialized = json.loads(json_bytes(loading_info_record(info)))
    assert serialized["loading_info"]["unexpected_keys"] == ["model.visual.a", "model.visual.b"]
    assert serialized["loading_info"]["missing_keys"] == []
    assert serialized["loading_info_source_types"]["unexpected_keys"] == "set"
    assert info == before


@pytest.mark.parametrize("method", ["update_window", "learning_logprobs", "export_sampling_snapshot", "save_checkpoint"])
def test_all_exposed_learning_entrypoints_fail_closed(method):
    actor = CalibrationActor.__new__(CalibrationActor)
    with pytest.raises(ValueError, match="forbids"):
        getattr(actor, method)()
