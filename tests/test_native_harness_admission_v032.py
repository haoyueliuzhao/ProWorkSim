"""CPU-only no-argument orchestration and exact common-state controls."""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim import model_qualification_v030 as original
from proworksim import native_harness_admission_v032 as admission
from proworksim.native_codecs_v031 import parse_swe_xml_generated, prepare_swe_xml_request
from test_functional_dense_v031 import fixture  # noqa: F401
from test_native_path_admission_v031r2 import CapturingTokenizer, owner_and_prior


def response(raw, request):
    message, error = parse_swe_xml_generated(raw, request)
    return {"http_status": 200, "body": {"protocol_parse_error": error,
        "choices": [{"message": message, "finish_reason": "stop"}]}}


def test_real_fixed_file_read_has_no_defaulted_or_rewritten_model_arguments(tmp_path):
    original._write(tmp_path / "public-note.json", original.NOTE)
    request = {"tools": admission.public_tools()}
    good = response("<function=read_public_note>\n</function><|im_end|>", request)
    assert admission.execute_read(good, tmp_path)["actual_result"] == original.NOTE
    bad_raw = "<function=read_public_note><parameter=></parameter></function><|im_end|>"
    bad = response(bad_raw, request)
    assert bad["body"]["protocol_parse_error"]
    assert bad["body"]["choices"][0]["message"]["content"] == bad_raw
    with pytest.raises(ValueError, match="Native output format failed"):
        admission.execute_read(bad, tmp_path)
    (tmp_path / "public-note.json").unlink()
    with pytest.raises(FileNotFoundError):
        admission.execute_read(good, tmp_path)


def test_measured_request_contains_exact_zero_argument_contract(tmp_path):
    tokenizer = CapturingTokenizer()
    owner = SimpleNamespace(inference_profile={"candidate_id": "swe-next-14b"},
                            recipe={"temperature": .7}, tokenizer=tokenizer)
    owner.prepare_request = lambda request: prepare_swe_xml_request(request, tokenizer)
    request, measure = admission._request(owner, 1, original._public_fixture(tmp_path), original.NOTE, [])
    assert request["tools"][0]["function"]["parameters"]["properties"] == {}
    assert original._render_count(owner, request)[0] == measure["actual_rendered_prompt_tokens"]
    assert 8192 - 128 <= measure["actual_rendered_prompt_tokens"] <= 8192


@pytest.mark.parametrize("rejections,calls,ready", [(0, 3, True), (1, 4, True), (2, 2, False)])
def test_bounded_native_noarg_traces_receive_full_backward_and_restore(
        fixture, tmp_path, monkeypatch, rejections, calls, ready):  # noqa: F811
    owner, common, prior, trace = owner_and_prior(fixture, tmp_path)
    requests = []

    def request(_owner, stage, fixture, observation, history):
        return {"tools": admission.public_tools(), "messages": [
            {"role": "system", "content": "Explicit scripted CPU control"}, *copy.deepcopy(history),
            {"role": "user", "content": str(stage)}]}, {"actual_rendered_prompt_tokens": len(trace["input_ids"])}

    def complete(request, **kwargs):
        requests.append(copy.deepcopy(request))
        if len(requests) <= rejections:
            raw = "<function=read_public_note><parameter=></parameter></function><|im_end|>"
        elif len(requests) == rejections + 1:
            raw = "<function=read_public_note>\n</function><|im_end|>"
        else:
            raw = ("<function=record_fact><parameter=code>" + original.NOTE["code"]
                   + "</parameter><parameter=revision>17</parameter></function><|im_end|>")
        value = response(raw, request)
        value["body"].update(actor_identity=owner.freeze_identity(), token_trace=copy.deepcopy(trace),
                             generation_stop_check={"all_generated_tokens_retained": True})
        return value

    monkeypatch.setattr(admission, "_request", request)
    monkeypatch.setattr(original, "_render_count", lambda owner, request: (len(trace["input_ids"]), "CPU", {}))
    monkeypatch.setattr(owner, "complete", complete)
    monkeypatch.setattr(owner.actor_optimizer, "step", lambda: pytest.fail("No optimizer step allowed"))
    monkeypatch.setattr(owner.critic_optimizer, "step", lambda: pytest.fail("No optimizer step allowed"))
    result = admission.qualify_harness(owner, tmp_path / "qualification", common_dir=common, prior_qualification=prior)
    assert result["training_ready"] == result["inference_ready"] == ready
    assert result["native_calls_executed"] == len(requests) == calls
    assert result["correction_calls_executed"] == int(rejections > 0)
    assert result["new_optimizer_steps"] == result["optimizer_steps"] == 0
    assert result["common_restored_exactly"] and result["diagnostic_gradients_cleared"]
    assert result["zero_step_check"]["passed"]
    assert result["zero_step_check"]["backward_decisions_completed"] == calls
    assert result["inherited_numerical_qualification"]["inherited"]
    assert not result["near_16k_stress_rerun"]
    assert json.loads(prior.read_text())["training_ready"] is False
    if rejections:
        assert result["calls"][0]["interface_error"]["read_executed"] is False
        assert requests[1]["messages"][-2]["role"] == "user"
        assert not any(row["role"] == "tool" for row in requests[1]["messages"])
