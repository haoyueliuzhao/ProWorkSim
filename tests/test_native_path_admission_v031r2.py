"""Path/history controls plus tiny real Torch zero-step restore controls.

Scripted responses below test bounded orchestration, never model capability.
No dense checkpoint, real qualification result or screening case is modified.
"""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim import model_qualification_v030 as old
from proworksim import native_path_admission_v031r2 as admission
from proworksim.native_codecs_v031 import parse_swe_xml_generated, prepare_swe_xml_request
from proworksim.storage import read_json
from test_functional_dense_v031 import fixture  # noqa: F401 -- real tiny CPU model control


def response(path):
    return {"http_status": 200, "body": {"choices": [{"finish_reason": "stop", "message": {
        "role": "assistant", "tool_calls": [{"id": "explicit-fixture-call", "type": "function", "function": {
            "name": "read_public_note", "arguments": json.dumps({"path": path})}}]}}]}}


def test_unchanged_argument_reads_real_file_and_rejects_path_aliases(tmp_path):
    old._write(tmp_path / admission.PATH, old.NOTE)
    assert admission.execute_read(response("public-note.json"), tmp_path)["actual_result"] == old.NOTE
    for bad in ("/public-note.json", "../public-note.json", "./public-note.json", "sub/../public-note.json",
                "C:\\public-note.json", "public-note.json/", " public-note.json", None):
        with pytest.raises(ValueError, match="workspace-relative path"):
            admission.execute_read(response(bad), tmp_path)
    (tmp_path / admission.PATH).unlink()
    with pytest.raises(FileNotFoundError):
        admission.execute_read(response("public-note.json"), tmp_path)


class CapturingTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        self.messages = copy.deepcopy(messages)
        assert kwargs["tools"] is None
        return json.dumps(messages, ensure_ascii=False)

    def __call__(self, rendered, **kwargs):
        return {"input_ids": list(rendered.encode())}


def test_schema_rejection_keeps_original_assistant_and_user_validation_feedback():
    original_tools = copy.deepcopy(old.TOOLS)
    request = {"messages": [{"role": "system", "content": "Actual path contract control"},
                             {"role": "user", "content": "Read the public note"}], "tools": admission.path_tools()}
    raw = '<function=read_public_note><parameter=path>/public-note.json</parameter></function><|im_end|>'
    message, error = parse_swe_xml_generated(raw, request)
    assert error and message == {"role": "assistant", "content": raw}
    actual_response = {"http_status": 200, "body": {"protocol_parse_error": error,
        "choices": [{"message": message, "finish_reason": "stop"}]}}
    feedback = {"validation_feedback": error, "read_executed": False}
    history = admission._append_history(request, actual_response, feedback)
    retry = copy.deepcopy(request)
    retry["messages"] = [request["messages"][0], *history]
    tokenizer = CapturingTokenizer()
    rendered, messages, projection = prepare_swe_xml_request(retry, tokenizer)
    assert raw in rendered and messages[-2] == {"role": "assistant", "content": raw}
    assert messages[-1]["role"] == "user" and "read_executed=false" in messages[-1]["content"]
    assert not any(row["role"] == "tool" or row.get("tool_calls") for row in messages)
    assert projection["history_projection"] == []
    bad_history = copy.deepcopy(retry)
    bad_history["messages"][-2]["tool_calls"] = response("/public-note.json")["body"]["choices"][0]["message"]["tool_calls"]
    with pytest.raises(ValueError, match="schema violation"):
        prepare_swe_xml_request(bad_history, tokenizer)
    assert old.TOOLS == original_tools


def test_request_measurement_uses_upgraded_tools_without_global_mutation(tmp_path):
    tokenizer = CapturingTokenizer()
    owner = SimpleNamespace(inference_profile={"candidate_id": "swe-next-14b"}, recipe={"temperature": .7}, tokenizer=tokenizer)
    owner.prepare_request = lambda request: prepare_swe_xml_request(request, tokenizer)
    original_tools = copy.deepcopy(old.TOOLS)
    request, measurement = admission._request(owner, 1, old._public_fixture(tmp_path), old.NOTE, [])
    assert request["tools"][0]["function"]["parameters"]["properties"]["path"]["const"] == admission.PATH
    assert old._render_count(owner, request)[0] == measurement["actual_rendered_prompt_tokens"]
    assert 8192 - 128 <= measurement["actual_rendered_prompt_tokens"] <= 8192
    assert old.TOOLS == original_tools


def owner_and_prior(fixture, tmp_path):  # noqa: F811
    from proworksim.functional_dense_v031 import learning_logprobs, native_cache_logprobs
    from proworksim.online_training import SharedActor
    from proworksim.software_learning_v029 import migrate_software_owner
    from proworksim.storage import digest

    torch, model, trace = fixture
    owner = SharedActor(model, SimpleNamespace(), output=tmp_path / "resident",
        base_identity={"manifest": {"sha256": digest(b"explicit-tiny-path-control")}},
        inference_profile={"candidate_id": "swe-next-14b", "scope": "scripted CPU control only"},
        recipe={"max_length": 16384, "max_output_tokens": 2048}, device="cpu", torch_module=torch)
    owner.learning_logprobs = lambda value: learning_logprobs(owner.model, value)
    migrate_software_owner(owner, expected_steps=None)
    common_dir = tmp_path / "common"
    owner.save_checkpoint(common_dir)
    state = old._state_fingerprints(owner)
    prior = {"version": old.VERSION, "inference_ready": False, "training_ready": False,
        "common_before": state, "common_after": state, "errors": [],
        "training_integration_ready": True, "near_16k_capacity_demonstrated": True,
        "common_restored_exactly": True, "diagnostic_gradients_cleared": True,
        "updated_identity_return_passed": True,
        "calls": [{"actual_trace_complete": True, "total_tokens": 16000} for _ in range(4)],
        "checkpoint_roundtrip": dict.fromkeys(("common_reload_exact", "updated_reload_exact", "updated_identity_changed",
                                               "updated_optimizer_states_changed"), True),
        "update": {"status": "one_aggregate_diagnostic_update_completed", "actor_optimizer_steps": 1,
                   "critic_optimizer_steps": 1, "backward_decisions_completed": 4, "persistent_optimizer_objects_reused": True,
                   "behavior_probability_checks": [{"passed": True} for _ in range(4)],
                   "gradient_probability_checks": [{"passed": True} for _ in range(4)]},
        "scope": "SYNTHETIC prior-report orchestration fixture; no real numerical proof claimed"}
    prior_path = tmp_path / "synthetic-prior-report.json"
    old._write(prior_path, prior)
    values = native_cache_logprobs(model, trace).cpu().tolist()
    trace.update(behavior_logprobs=values, raw_behavior_logprobs=list(values), input_mask=[0] * len(trace["input_ids"]))
    return owner, common_dir, prior_path, trace


@pytest.mark.parametrize("paths,expected_calls,ready", [(["public-note.json"], 3, True),
    (["/public-note.json", "public-note.json"], 4, True), (["/public-note.json", "/public-note.json"], 2, False)])
def test_bounded_read_control_retains_failed_traces_zero_steps_and_restores(fixture, tmp_path, monkeypatch, paths, expected_calls, ready):  # noqa: F811
    owner, common_dir, prior, trace = owner_and_prior(fixture, tmp_path)
    initial_trace, requests = copy.deepcopy(trace), []
    paths = iter(paths)

    def request(_owner, stage, fixture, observation, history):
        return {"tools": admission.path_tools(), "messages": [{"role": "system", "content": "Explicit scripted CPU control"},
            *copy.deepcopy(history), {"role": "user", "content": str(stage)}]}, {"actual_rendered_prompt_tokens": len(trace["input_ids"])}

    def complete(request, **kwargs):
        requests.append(copy.deepcopy(request))
        is_read = len(requests) == 1 or (len(requests) == 2 and expected_calls != 3)
        if is_read:
            raw = '<function=read_public_note><parameter=path>' + next(paths) + '</parameter></function><|im_end|>'
        else:
            raw = '<function=record_fact><parameter=code>' + old.NOTE["code"] + '</parameter><parameter=revision>17</parameter></function><|im_end|>'
        message, error = parse_swe_xml_generated(raw, request)
        return {"http_status": 200, "body": {"actor_identity": owner.freeze_identity(), "token_trace": copy.deepcopy(trace),
            "generation_stop_check": {"all_generated_tokens_retained": True}, "protocol_parse_error": error,
            "choices": [{"message": message, "finish_reason": "stop"}]}}

    monkeypatch.setattr(admission, "_request", request)
    monkeypatch.setattr(old, "_render_count", lambda owner, request: (len(trace["input_ids"]), "explicit-control", {}))
    monkeypatch.setattr(owner, "complete", complete)
    monkeypatch.setattr(owner.actor_optimizer, "step", lambda: pytest.fail("No actor step allowed"))
    monkeypatch.setattr(owner.critic_optimizer, "step", lambda: pytest.fail("No critic step allowed"))
    result = admission.qualify_path(owner, tmp_path / "admission", common_dir=common_dir, prior_qualification=prior)
    assert result["training_ready"] == result["inference_ready"] == ready
    assert result["native_calls_executed"] == len(requests) == expected_calls
    assert result["new_optimizer_steps"] == result["optimizer_steps"] == 0
    assert result["common_restored_exactly"] and result["diagnostic_gradients_cleared"]
    assert result["zero_step_check"]["passed"]
    assert result["zero_step_check"]["trajectory_count"] == expected_calls
    assert result["zero_step_check"]["backward_decisions_completed"] == expected_calls
    assert trace == initial_trace and trace["output_ids"][-1] == owner.model.config.eos_token_id
    assert not result["near_16k_stress_rerun"] and result["inherited_numerical_qualification"]["inherited"]
    assert read_json(prior)["inference_ready"] is False
    assert result["errors"] == []
    if expected_calls != 3:
        assert result["calls"][0]["interface_error"]["read_executed"] is False
        assert any(row["role"] == "assistant" and "/public-note.json" in row["content"] for row in requests[1]["messages"])
        assert not any(row["role"] == "tool" for row in requests[1]["messages"])
    if not ready:
        assert result["stopped_after_read_failure"] and not (tmp_path / "admission/actual-missing-file-feedback.json").exists()


def test_inherited_proof_refuses_changed_common_or_missing_numerical_gate(fixture, tmp_path):  # noqa: F811
    owner, common_dir, path, _ = owner_and_prior(fixture, tmp_path)
    report = read_json(path)
    assert admission.validate_prior_qualification(owner, common_dir, path)["prior_training_ready"] is False
    for section, key, value in ((None, "near_16k_capacity_demonstrated", False),
                                ("update", "backward_decisions_completed", 3),
                                ("common_before", "state_tensor_digest", "wrong-common")):
        bad = copy.deepcopy(report)
        (bad if section is None else bad[section])[key] = value
        old._write(path, bad)
        with pytest.raises(ValueError):
            admission.validate_prior_qualification(owner, common_dir, path)
    old._write(path, report)
    with pytest.raises(ValueError, match="checksum"):
        admission.validate_prior_qualification(owner, common_dir, {"path": str(path), "sha256": "wrong"})
