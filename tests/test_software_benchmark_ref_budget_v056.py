"""Budget treatment changes admission, not token settlement or inference settings."""
import copy
import json
from pathlib import Path

import pytest

from proworksim.software_benchmark_ref_budget_v056 import (
    BudgetLedger, OptionalToolsCounter, canonical_request, validate_condition,
)
from proworksim.software_benchmark_match_v054 import AccountingFault, DispatchStopped

ROOT = Path(__file__).resolve().parents[1]


def condition(name):
    return json.loads((ROOT / "config" / f"v056-condition-{name}.json").read_text())


def test_only_larger_budget_admits_the_real_rejected_request_shape():
    small, large = BudgetLedger(condition("REF_B0500K")), BudgetLedger(condition("REF_B2000K"))
    for ledger in (small, large):
        ledger.actual = 452941
    measured = {"prompt_tokens": 41636, "sha256": "fixed-exact-input-proof"}
    with pytest.raises(DispatchStopped, match="reservation_insufficient"):
        small.reserve(measured, "agent", {"path": "same-request"})
    assert small.attempts == 0 and small.inflight is None
    large.reserve(measured, "agent", {"path": "same-request"})
    assert large.inflight["reservation"] == 74404 and large.attempts == 1
    assert large.actual == small.actual == 452941


def test_unknown_usage_is_retained_and_cannot_be_retried():
    ledger = BudgetLedger(condition("REF_B10000K"))
    ledger.reserve({"prompt_tokens": 100, "sha256": "proof"}, "agent", {})
    with pytest.raises(AccountingFault, match="Unresolved"):
        ledger.reserve({"prompt_tokens": 100, "sha256": "proof"}, "agent", {})
    with pytest.raises(AccountingFault):
        ledger.settle({"usage": {"prompt_tokens": 99}}, {})
    state = ledger.snapshot()
    assert state["complete_actual_tokens"] is None and state["uncertain_reserved_tokens"] == 32868


def test_gradient_keeps_inference_and_common_limits_fixed():
    value = condition("REF_B5000K")
    validate_condition(value)
    for field, changed in (("temperature", .7), ("max_tokens", 2048), ("total_context", 262144)):
        altered = copy.deepcopy(value)
        altered["inference"][field] = changed
        with pytest.raises(ValueError):
            validate_condition(altered)
    altered = copy.deepcopy(value)
    altered["episode_limits"]["all_model_attempts"] = 128
    with pytest.raises(ValueError):
        validate_condition(altered)


def test_tool_free_request_uses_identical_canonical_counting_and_generation_shape(tmp_path):
    request = {"model": "fixed", "messages": [{"role": "user", "content": "neutral"}],
               "tools": [], "tool_choice": "none", "max_tokens": 32768,
               "chat_template_kwargs": {"enable_thinking": True}}
    wire = canonical_request(request)
    assert "tools" not in wire and "tool_choice" not in wire
    assert request["tools"] == []
    calls = []

    class Transport:
        def post(self, path, payload):
            assert path == "/tokenize" and "tools" not in payload
            calls.append(payload)
            return {"tokens": [10, 11, 12], "count": 3, "max_model_len": 131072}

    counter = OptionalToolsCounter(Transport(), tmp_path)
    original = counter.measure(request)
    actual = counter.measure(wire)
    assert original == actual and len(calls) == 1
    tools_request = dict(request, tools=[{"function": {"name": "terminal"}}], tool_choice="auto")
    assert canonical_request(tools_request) == tools_request
