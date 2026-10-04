"""Measured resident budget controls; scripted CPU tokens are not model evidence."""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim.model_policy import ModelPolicy
from proworksim.software_context_v028 import SoftwareContextTransport
from proworksim.software_runtime_v030 import _terminal_detail
from proworksim.staff_runtime import PolicyBoundaryError
from proworksim.storage import digest, json_bytes, read_json


class CPUOwner:
    def __init__(self):
        self.recipe = {"max_length": 16384, "max_output_tokens": 2048, "temperature": .7}
        self.identity = {"policy_version": "explicit-cpu-control-0", "adapter_sha256": "fixture"}
        self.window_id = "explicit-cpu-budget-window"
        self.render_calls, self.requests = 0, []
        self.transport = SimpleNamespace(complete=self.complete)

    def freeze_identity(self):
        return copy.deepcopy(self.identity)

    def prepare_request(self, request):
        self.render_calls += 1
        return json.dumps(request, sort_keys=True), request["messages"], {"scope": "explicit CPU renderer"}

    def tokenizer(self, text, **kwargs):
        # Deterministic vocabulary fixture, never presented as SWE tokenization.
        return {"input_ids": [sum(map(ord, text[index:index + 4])) for index in range(0, len(text), 4)]}

    def complete(self, request, **kwargs):
        self.requests.append(copy.deepcopy(request))
        rendered, _, _ = self.prepare_request(request)
        ids = self.tokenizer(rendered)["input_ids"]
        body = {"id": "explicit-cpu-response", "object": "chat.completion", "created": 0,
            "model": "explicit-cpu-fixture", "actor_identity": self.freeze_identity(),
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
                "tool_calls": [{"id": "cpu-call-" + str(len(self.requests)), "type": "function", "function": {"name": "write_note", "arguments": '{"text":"fixture"}'}}]}}],
            "usage": {"prompt_tokens": len(ids), "completion_tokens": 3, "total_tokens": len(ids) + 3},
            "token_trace": {"input_ids": ids, "fixture_only": True}}
        return {"http_status": 200, "body": body, "raw_body": json.dumps(body)}


def request(old_length=70000):
    return {"model": "explicit-cpu-fixture", "max_tokens": 2048, "temperature": .7,
        "tools": [{"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}],
        "messages": [{"role": "system", "content": "Fixed task"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "old", "function": {"name": "read", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "old", "content": "x" * old_length},
            {"role": "user", "content": "Exact current observation"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "new", "function": {"name": "read", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "new", "content": "Exact actual newest tool result"}]}


def config(owner):
    return {"backend_id": "resident_direct", "model": "explicit-cpu-fixture", "base_url": "http://127.0.0.1",
        "api_key_env": None, "weight_identity": owner.freeze_identity(), "model_revision": owner.identity["policy_version"],
        "max_context_tokens": 16384, "max_output_tokens": 2048, "temperature": .7,
        "retry": {"max_attempts": 1, "retry_statuses": [], "backoff_seconds": []},
        "budget": {"max_decisions": 64, "max_http_attempts": 64, "max_total_tokens": 500000,
                   "max_cost_usd": 0, "max_context_bytes": 240000},
        "pricing": {"input_miss_per_million": 0, "input_hit_per_million": 0, "output_per_million": 0}}


def meter(tokens):
    return {"http_attempts": 0, "budget_accounted_tokens": tokens, "budget_accounted_cost_usd": 0,
        "reported_total_tokens": tokens, "reported_prompt_tokens": tokens, "reported_completion_tokens": 0,
        "unknown_usage_attempts": 0, "cost_upper_bound_usd": 0}


def test_old_byte_reservation_stops_early_exact_projected_reservation_keeps_original_cap(tmp_path):
    owner, original = CPUOwner(), request()
    transport = SoftwareContextTransport(owner, tmp_path / "context")
    accountant = ModelPolicy(config(owner), transport=transport)
    original_copy = copy.deepcopy(original)
    memory = {"meter": meter(449303)}  # One observed stop's actual spent count.
    old = accountant._reserve(original)
    assert memory["meter"]["budget_accounted_tokens"] + old["token_reservation"] > 500000
    with pytest.raises(PolicyBoundaryError) as stopped:
        accountant._admit(memory, old, "explicit-control-old")
    assert stopped.value.details["limits"] == ["max_total_tokens_conservative_reservation"]
    prepared = transport.prepare_for_budget(original)
    exact = accountant._reserve(original, prepared=prepared)
    assert not owner.requests and not (tmp_path / "context").exists()
    assert exact["token_reservation"] == prepared["prompt_tokens"] + 2048
    assert exact["token_reservation"] <= 16384
    assert exact["request_bytes"] == old["request_bytes"]
    assert exact["cost_reservation_usd"] == old["cost_reservation_usd"] == 0
    accountant._admit(memory, exact, "explicit-control-measured")
    renders_before = owner.render_calls
    actual = transport.complete(original, timeout_seconds=1)
    assert owner.render_calls == renders_before + 1  # Only the sampler render; no second context projection.
    assert len(owner.requests) == 1 and len(owner.requests[0]["messages"]) == 4
    assert digest(json_bytes(owner.requests[0])) == prepared["selected_request_sha256"]
    assert len(actual["body"]["token_trace"]["input_ids"]) == prepared["prompt_tokens"]
    assert original == original_copy
    charged = accountant._charge(memory, actual["body"], exact)
    assert charged["usage_status"] == "reported"
    assert memory["meter"]["budget_accounted_tokens"] == 449303 + actual["body"]["usage"]["total_tokens"]
    assert read_json(tmp_path / "context/request-00001/budget-preparation.json") == prepared
    assert read_json(tmp_path / "context/request-00001/response.json") == actual
    assert accountant.config["budget"]["max_total_tokens"] == 500000


@pytest.mark.parametrize("changed", ["request", "identity", "window", "recipe", "selected_hash"])
def test_prepared_request_and_owner_changes_fail_before_generation(tmp_path, changed):
    owner, original = CPUOwner(), request(10)
    transport = SoftwareContextTransport(owner, tmp_path)
    transport.prepare_for_budget(original)
    if changed == "request":
        original["messages"][-1]["content"] += " changed"
    elif changed == "identity":
        owner.identity["policy_version"] = "changed"
    elif changed == "window":
        owner.window_id = "changed"
    elif changed == "recipe":
        owner.recipe["temperature"] = .8
    else:
        transport._prepared["selected"]["messages"][-1]["content"] += " changed"
    with pytest.raises(ValueError, match="checksum|changed"):
        transport.complete(original)
    assert not owner.requests and transport.counter == 0


def test_preparation_metadata_checksum_and_worker_identity_cannot_be_rebound(tmp_path):
    owner, original = CPUOwner(), request(10)
    transport = SoftwareContextTransport(owner, tmp_path)
    prepared = transport.prepare_for_budget(original)
    accountant = ModelPolicy(config(owner), transport=transport)
    altered = copy.deepcopy(prepared)
    altered["prompt_tokens"] -= 1
    with pytest.raises(ValueError, match="checksum"):
        accountant._reserve(original, prepared=altered)
    accountant.config["weight_identity"] = {"policy_version": "wrong"}
    with pytest.raises(ValueError, match="frozen owner"):
        accountant._reserve(original, prepared=prepared)
    assert not owner.requests


def test_exact_reservation_denial_never_calls_sampler_and_discards_pending_preparation(tmp_path):
    pytest.importorskip("openhands.sdk")
    from proworksim.harness_sdk import HarnessWorker
    from scripts.software_development_v028 import DurableTransport
    from scripts.software_model_selection_v030 import RoutedTransport

    owner, events = CPUOwner(), []
    context = SoftwareContextTransport(owner, tmp_path / "context")
    durable = DurableTransport(context, tmp_path / "raw", owner.window_id)
    routed = RoutedTransport()
    routed.inner = durable
    worker = HarnessWorker("member_a", [], config(owner), routed,
        lambda *_: pytest.fail("No world action before admitted generation"),
        event_sink=lambda kind, payload: events.append((kind, payload)), directory=tmp_path / "sdk")
    worker.meter.update(meter(499000))
    try:
        with pytest.raises(PolicyBoundaryError) as stopped:
            worker.step({}, {"run_id": "cpu", "opportunity_id": "1"})
        assert stopped.value.status == "model_budget_exhausted"
        assert stopped.value.details["limits"] == ["max_total_tokens_exact_reservation"]
        assert not owner.requests and worker.meter["http_attempts"] == 0
        assert context._prepared is None and context.counter == durable.counter == 0
        assert not (tmp_path / "raw").exists()
        budget = next(payload for kind, payload in events if kind == "model_budget_stop")
        assert budget["reservation"]["reservation_kind"] == "exact_resident_prompt"
        assert budget["meter"]["budget_accounted_tokens"] == 499000
        # The other role may prepare after this member's terminal allowance denial.
        routed.prepare_for_budget(request(10))
        routed.discard_prepared_request(request(10))
    finally:
        worker.close()


def test_http_fallback_reservation_and_missing_usage_accounting_are_unchanged():
    owner, original = CPUOwner(), request(10)
    http_config = config(owner)
    http_config["backend_id"] = "explicit-http-control"
    accountant = ModelPolicy(http_config, transport=SimpleNamespace())
    reservation = accountant._reserve(original)
    upper = len(json_bytes(original)) + 1024 + 64 * (len(original["messages"]) + len(original["tools"]))
    assert reservation == {"request_bytes": len(json_bytes(original)), "input_token_reservation": upper,
        "output_token_reservation": 2048, "token_reservation": upper + 2048, "cost_reservation_usd": 0,
        "method": "UTF8 request bytes + 1024 + 64 per message/tool; conservative admission estimate, not measured usage or a tokenizer proof"}
    memory = {"meter": meter(0)}
    charge = accountant._charge(memory, None, reservation)
    assert charge["usage_status"] == "missing_or_invalid"
    assert memory["meter"]["budget_accounted_tokens"] == reservation["token_reservation"]


def test_actual_sdk_allowance_and_refresh_bind_the_current_actor_identity(tmp_path):
    pytest.importorskip("openhands.sdk")
    from proworksim.harness_sdk import HarnessWorker
    from scripts.software_development_v028 import DurableTransport
    from scripts.software_model_selection_v030 import RoutedTransport

    owner, executed = CPUOwner(), []
    context = SoftwareContextTransport(owner, tmp_path / "context")
    routed = RoutedTransport()
    routed.inner = DurableTransport(context, tmp_path / "raw", owner.window_id)
    tools = [{"name": "write_note", "description": "Explicit CPU action", "parameters": {"type": "object",
        "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False}}]

    def execute(name, arguments, association):
        executed.append((name, arguments, association))
        return {"ok": True, "world_effect": False, "scope": "explicit CPU control"}

    worker = HarnessWorker("member_a", tools, config(owner), routed, execute, directory=tmp_path / "sdk")
    try:
        worker.step({}, {"run_id": "cpu", "opportunity_id": "1"})
        owner.identity["policy_version"] = "explicit-cpu-control-1"
        worker.refresh_transport(routed, owner.freeze_identity())
        worker.step({}, {"run_id": "cpu", "opportunity_id": "2"})
        assert len(owner.requests) == len(executed) == 2
        assert read_json(tmp_path / "context/request-00002/budget-preparation.json")["actor_identity"] == owner.freeze_identity()
        assert worker.meter["unknown_usage_attempts"] == 0
        assert worker.meter["budget_accounted_tokens"] == worker.meter["reported_total_tokens"]
    finally:
        worker.close()


def test_terminal_details_separate_accounting_format_context_and_decision_limits():
    runtime = SimpleNamespace(roles={"member_a": {"reason": "retained actual reason", "opportunities": 41}},
                              policies={"member_a": SimpleNamespace(meter={"decisions": 41})})
    case = {"role_decision_limits": {"member_a": 64}}
    budget = {"sequence": 9, "worker_id": "member_a", "kind": "model_budget_stop", "payload": {
        "limits": ["max_total_tokens_conservative_reservation"], "meter": meter(449303), "reservation": {"token_reservation": 55698}}}
    detail = _terminal_detail("member_a", {"status": "model_budget_exhausted"}, runtime, case, [budget])
    assert detail["cause"] == "model_accounting_budget" and detail["meter"]["reported_total_tokens"] == 449303
    assert detail["reservation"]["token_reservation"] == 55698 and detail["decisions"] == 41
    assert detail["evidence"] == [{"sequence": 9, "kind": "model_budget_stop"}]
    format_error = {"sequence": 12, "worker_id": "member_a", "kind": "model_format_error", "payload": {
        "format_errors": {"total": 4, "consecutive": 1}, "format_limits": {"max_total": 4, "max_consecutive": 2},
        "reason": "original parser failure"}}
    detail = _terminal_detail("member_a", {"status": "model_format_error"}, runtime, case, [format_error])
    assert detail["cause"] == "format_error_limit" and detail["last_format_reason"] == "original parser failure"
    for kind, cause in (("decision_limit", "member_decision_limit"), ("context_capacity", "context_capacity")):
        detail = _terminal_detail("member_a", {"status": "model_budget_exhausted", "budget_kind": kind}, runtime, case)
        assert detail["cause"] == cause
