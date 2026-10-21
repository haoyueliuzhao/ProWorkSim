"""Necessary remote seam failures; no model, SDK import, GPU or network."""
import copy
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_deepseek_api_v055 import APIUncertainFailure, BudgetStopped
from proworksim.software_benchmark_deepseek_interfaces_v055 import (
    DeepSeekAdapter, ReasoningHistory, RemoteEpisodeBoundary,
)


def test_thinking_tool_continuation_restores_only_the_original_action():
    history = ReasoningHistory()
    original = {"role": "assistant", "content": "", "reasoning_content": "original reasoning",
                "tool_calls": [{"id": "same-id", "type": "function",
                                "function": {"name": "read_file", "arguments": '{"path":"x"}'}}]}
    history.remember(original)
    sdk = copy.deepcopy(original)
    sdk.pop("reasoning_content")
    sdk["tool_calls"][0]["function"]["arguments"] = '{ "path": "x" }'
    assert history.restore([sdk], thinking=True) == [original]
    sdk["tool_calls"][0]["function"]["arguments"] = '{"path":"different"}'
    with pytest.raises(ValueError, match="changed the arguments"):
        history.restore([sdk], thinking=True)
    with pytest.raises(ValueError, match="no original reasoning"):
        ReasoningHistory().restore([sdk], thinking=True)


@pytest.mark.parametrize("failure,known_zero", [(BudgetStopped("cap"), True),
                                               (APIUncertainFailure("unknown"), False)])
def test_predispatch_budget_and_unknown_network_results_have_distinct_accounting(tmp_path, failure, known_zero):
    class Fixture:
        ledger = SimpleNamespace(snapshot=lambda: {"inflight_count": 0, "halted": None})

        def complete(self, *args, **kwargs):
            raise failure

    adapter = DeepSeekAdapter(client=Fixture(), arm="PROJECT", thinking=True,
        slot_id="synthetic-seam", condition_id="PROJECT-thinking", folder=tmp_path / "ledger",
        allowed_tool_names={"read_file"})
    request = adapter.request([{"role": "user", "content": "neutral fixture"}], [])
    with pytest.raises(RemoteEpisodeBoundary if known_zero else APIUncertainFailure):
        adapter.complete(request)
    snapshot = adapter.ledger.snapshot()
    assert snapshot["attempts"] == (0 if known_zero else 1)
    assert (snapshot["inflight"] is None) is known_zero
    assert snapshot["complete_actual_tokens"] == (0 if known_zero else None)
    with pytest.raises(ValueError, match="Unknown or duplicate"):
        adapter.request([{"role": "user", "content": "fixture"}], [
            {"type": "function", "function": {"name": "web_search", "parameters": {}}}])
