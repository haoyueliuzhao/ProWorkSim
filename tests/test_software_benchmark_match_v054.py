import copy
import json
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_match_v054 import (
    AccountingFault, CONTRACT, DispatchStopped, EpisodeLedger, MatchBridge,
    TOOL_NAMES, prepare_native_input,
)


class FixtureTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        return json.dumps({"messages": messages, **kwargs}, sort_keys=True)

    def __call__(self, text, **kwargs):
        return {"input_ids": list(text.encode())}


class FixtureOwner:
    programmed_fixture = True
    path = "project"
    contract = CONTRACT
    tokenizer = FixtureTokenizer()

    def __init__(self):
        self.calls = 0
        self.result_change = None

    def freeze_identity(self):
        return {"raw_release": True, "checkpoint": None, "adapter_sha256": None,
                "numerical_fixture_only": True}

    def generate_native(self, native):
        self.calls += 1
        result = {
            "actor_identity": self.freeze_identity(), "input": native,
            "output_ids": [111, 248044], "raw_generated_text": "fixture<|im_end|>",
            "attempt_id": f"fixture-{self.calls}", "finish_reason": "stop",
            "usage": {"prompt_tokens": native["prompt_tokens"], "completion_tokens": 2,
                      "total_tokens": native["prompt_tokens"] + 2},
        }
        if self.result_change:
            self.result_change(result)
        return result


class FixtureCodec:
    def decode(self, *, request, result):
        return {"message": {"role": "assistant", "content": "synthetic-only"},
                "codec_identity": {"programmed_fixture": True}}


def request(*, condenser=False):
    return {
        "model": "fixture", "messages": [{"role": "user", "content": "synthetic"}],
        "tools": [] if condenser else [
            {"type": "function", "function": {
                "name": name, "parameters": {"type": "object"}}}
            for name in sorted(TOOL_NAMES)
        ],
        "temperature": 0.7, "max_tokens": 2048, "stream": False,
    }


def bridge(tmp_path, owner=None, codec=None):
    return MatchBridge(owner or FixtureOwner(), codec=codec or FixtureCodec(),
                       folder=tmp_path / "episode", slot_id="synthetic",
                       allow_programmed_fixture=True)


def test_render_retains_history_and_all_tools_without_project_hint():
    row = request()
    row["messages"] += [{
        "role": "assistant", "content": "", "reasoning_content": "retained reasoning",
        "tool_calls": [{"type": "function", "id": "a", "function": {
            "name": "file_editor", "arguments": '{"command":"view","path":"a.py"}'}}],
    }]
    before = copy.deepcopy(row)
    native = prepare_native_input(FixtureTokenizer(), row)
    assert row == before
    assert not native["single_call_hint_applied"]
    assert native["actual_prompt_messages"][1]["reasoning_content"] == "retained reasoning"
    assert native["actual_prompt_messages"][1]["tool_calls"][0]["function"]["arguments"] == {
        "command": "view", "path": "a.py"}
    assert native["prompt_tokens"] == len(native["input_ids"])
    assert set(json.loads(native["rendered_prompt"])["tools"][i]["function"]["name"]
               for i in range(5)) == TOOL_NAMES


def test_agent_and_condenser_share_cost_and_attempt_cap(tmp_path):
    value = bridge(tmp_path)
    first = value.complete_request(request(), usage_id="agent")
    second = value.complete_request(request(condenser=True), usage_id="condenser")
    snapshot = value.ledger.snapshot()
    assert (snapshot["attempts"], snapshot["decisions"]) == (2, 1)
    assert snapshot["complete_actual_tokens"] == sum(
        item["usage"]["total_tokens"] for item in (first, second))
    assert set(snapshot["per_usage_id"]) == {"agent", "condenser"}
    value.ledger.attempt_limit = 2
    with pytest.raises(DispatchStopped, match="all_model_attempt_limit"):
        value.complete_request(request(condenser=True), usage_id="condenser")
    assert value.owner.calls == 2


def test_full_reservation_rejected_before_any_provider_call(tmp_path):
    value = bridge(tmp_path)
    native = value.prepare(request())
    value.ledger.token_limit = native["prompt_tokens"] + 2048 - 1
    with pytest.raises(DispatchStopped, match="reservation_insufficient"):
        value.complete_request(request(), usage_id="agent")
    assert value.owner.calls == value.ledger.attempts == 0
    assert value.ledger.decisions == 1
    ledger = EpisodeLedger(value.identity)
    oversized = {**native, "fits": False}
    with pytest.raises(DispatchStopped, match="context"):
        ledger.admit(oversized, "condenser")
    assert ledger.attempts == ledger.decisions == 0


def test_unknown_usage_retains_reservation_and_prevents_resampling(tmp_path):
    owner = FixtureOwner()
    owner.result_change = lambda result: result["usage"].pop("completion_tokens")
    value = bridge(tmp_path, owner)
    with pytest.raises(AccountingFault):
        value.complete_request(request(), usage_id="agent")
    state = value.ledger.snapshot()
    assert state["complete_actual_tokens"] is None
    assert state["uncertain_reserved_tokens"] > 2048
    assert state["attempts"] == owner.calls == 1
    with pytest.raises(DispatchStopped, match="already_stopped"):
        value.complete_request(request(), usage_id="agent")
    assert owner.calls == 1


def test_codec_failure_preserves_real_usage_and_has_no_retry(tmp_path):
    def fail(**kwargs):
        raise ValueError("synthetic format fault")
    value = bridge(tmp_path, codec=SimpleNamespace(decode=fail))
    with pytest.raises(AccountingFault, match="format fault"):
        value.complete_request(request(), usage_id="agent")
    assert value.ledger.inflight is None
    assert value.ledger.actual > 2
    assert value.owner.calls == 1
    assert (tmp_path / "episode/native-response-0001.json").is_file()


def test_length_finish_and_changed_identity_cannot_be_hidden(tmp_path):
    owner = FixtureOwner()
    def make_length(result):
        result.update(finish_reason="length", output_ids=[111] * 2048)
        result["usage"].update(completion_tokens=2048,
                               total_tokens=result["usage"]["prompt_tokens"] + 2048)
    owner.result_change = make_length
    value = bridge(tmp_path, owner)
    result = value.complete_request(request(), usage_id="agent")
    assert result["choices"][0]["finish_reason"] == "length"
    owner.freeze_identity = lambda: {"raw_release": False}
    with pytest.raises(AccountingFault, match="identity changed"):
        value.complete_request(request(), usage_id="agent")
    assert owner.calls == 1


def test_real_owner_identity_gate_rejects_wrong_raw_source_without_loading_model(tmp_path):
    from proworksim.software_calibration_runtime_v051 import CalibrationActor
    owner = CalibrationActor.__new__(CalibrationActor)
    owner.path, owner.contract = "project", CONTRACT
    owner._identity = {
        "raw_release": True, "checkpoint": None, "adapter_sha256": None,
        "trained_adapter_loaded": False, "base_revision": "wrong-raw-source",
    }
    with pytest.raises(ValueError, match="pinned raw source"):
        MatchBridge(owner, codec=None, folder=tmp_path / "never-created", slot_id="fixture")
    assert not (tmp_path / "never-created").exists()
