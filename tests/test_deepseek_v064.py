import copy
import json

import pytest

from proworksim import software_benchmark_deepseek_api_v064 as api
from proworksim import software_benchmark_deepseek_adapter_v064 as bridge
from proworksim.storage import digest, json_bytes


def wire():
    return {"model": "deepseek-flash", "messages": [{"role": "user", "content": "local task"}],
            "stream": False, "thinking": {"type": "enabled"}, "reasoning_effort": "high",
            "top_p": 0.95, "max_tokens": 32768,
            "tools": [{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}}],
            "tool_choice": "auto"}


def body(identity="response-1", *, prompt=100, output=10, hit=80):
    return {"id": identity, "model": "deepseek-flash", "system_fingerprint": "pinned-observation",
            "choices": [{"finish_reason": "stop", "message": {
                "role": "assistant", "content": "done", "reasoning_content": "original reasoning"}}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": output,
                      "total_tokens": prompt+output, "prompt_cache_hit_tokens": hit,
                      "prompt_cache_miss_tokens": prompt-hit,
                      "completion_tokens_details": {"reasoning_tokens": 8}}}


def reserve(ledger, identity="one", *, bound=100, output=32768):
    return ledger.reserve(request_id=identity, slot_id="slot", condition="condition", usage_id="agent",
                          request_sha256="a"*64, max_output_tokens=output, prompt_upper_bound=bound)


def test_frozen_thinking_no_search_or_lost_reasoning():
    api.validate_payload(wire(), {"read_file"})
    for edit in ({"temperature": 0.6}, {"top_p": 1.0}, {"thinking": {"type": "disabled"}},
                 {"tools": [{"type": "web_search"}]}, {"max_tokens": 32769}):
        with pytest.raises(ValueError):
            api.validate_payload({**wire(), **edit}, {"read_file"})
    missing = wire()
    missing["messages"].append({"role": "assistant", "content": "a no-tool turn"})
    with pytest.raises(ValueError, match="reasoning_content"):
        api.validate_payload(missing, {"read_file"})


def test_usage_counts_reasoning_once_and_preserves_unknown_reasoning():
    normalized = api.normalize_usage(body())
    assert normalized["total_tokens"] == 110
    assert normalized["reasoning_tokens"] == 8 and normalized["output_tokens"] == 10
    value = body()
    value["usage"].pop("completion_tokens_details")
    assert api.normalize_usage(value)["reasoning_tokens"] is None
    value["usage"]["total_tokens"] += 1
    with pytest.raises(ValueError, match="partitions"):
        api.normalize_usage(value)


def test_new_ledger_rejects_foreign_policy_without_mutating_it(tmp_path):
    ledger = api.BudgetLedger(tmp_path / "new.sqlite")
    assert ledger.snapshot()["cap_nanoyuan"] == 1500*api.NANOYUAN
    with ledger._transaction() as db:
        db.execute("UPDATE metadata SET value='old-v055-policy' WHERE name='policy'")
    with pytest.raises(ValueError, match="another immutable"):
        api.BudgetLedger(ledger.path)
    with ledger._connect() as db:
        assert db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0] == "old-v055-policy"


def test_unknown_reservation_remains_and_cannot_be_replayed(tmp_path):
    ledger = api.BudgetLedger(tmp_path / "cash.sqlite", max_concurrency=1)
    reserve(ledger)
    with pytest.raises(api.ConcurrencyBusy):
        reserve(ledger, "two")
    ledger.uncertain("one", {"reason": "socket dropped"})
    assert ledger.snapshot()["uncertain_reserved_cny"] == 5.24288
    assert ledger.snapshot()["inflight_count"] == 0
    with pytest.raises(api.BudgetStopped, match="no_replay"):
        reserve(ledger)


def test_cash_integer_gate_counts_unknowns_and_does_not_raise_cap(tmp_path, monkeypatch):
    ledger = api.BudgetLedger(tmp_path / "cash.sqlite", max_concurrency=2)
    # Exercise the same integer boundary with two full reservations, without
    # hundreds of redundant fsyncs. The frozen production policy stays CNY1500.
    monkeypatch.setattr(api, "CAP_NANOYUAN", 2*api.ABSOLUTE_RESERVATION_NANOYUAN)
    for name in ("one", "two"):
        reserve(ledger, name)
        ledger.uncertain(name, {"reason": "no receipt"})
    with pytest.raises(api.BudgetStopped, match="reservation_insufficient"):
        reserve(ledger, "three")
    assert ledger.snapshot()["remaining_cny"] == 0
    assert api.POLICY["cap_nanoyuan"] == 1500*api.NANOYUAN


def test_known_output_violation_is_billed_and_task_local(tmp_path):
    ledger = api.BudgetLedger(tmp_path / "cash.sqlite")
    reserve(ledger)
    result = body(output=32769)
    with pytest.raises(api.ProviderOutputBoundViolation) as error:
        ledger.settle("one", result)
    assert error.value.authoritative_response == result
    assert ledger.request_status("one")["status"] == "settled"
    assert ledger.snapshot()["settled_upper_cny"] > 0
    assert ledger.snapshot()["halted"] is None


def test_duplicate_response_or_invalid_usage_halts_shared_accounting(tmp_path):
    ledger = api.BudgetLedger(tmp_path / "cash.sqlite")
    reserve(ledger)
    ledger.settle("one", body())
    reserve(ledger, "two")
    with pytest.raises(api.BudgetStopped, match="duplicate"):
        ledger.settle("two", body())
    assert ledger.request_status("two")["status"] == "uncertain"
    assert ledger.snapshot()["halted"] == "duplicate_provider_response_identity"


class FakeTransport:
    def __init__(self, response):
        self.response, self.calls = response, []

    def request(self, method, path, payload=None):
        self.calls.append((method, path, copy.deepcopy(payload)))
        return self.response


def test_client_distinguishes_unsent_admission_from_sent_accounting_failure(tmp_path):
    fake = FakeTransport({"id": "bad", "model": "deepseek-flash"})
    client = api.DeepSeekClient(ledger_path=tmp_path / "cash.sqlite", api_key="test-only",
                               allowed_tool_names={"read_file"}, transport=fake, max_concurrency=1)
    reserve(client.ledger)
    with pytest.raises(api.PreDispatchConcurrencyBusy):
        client.complete(wire(), request_id="two", slot_id="slot", condition="condition", prompt_upper_bound=100)
    assert not fake.calls
    client.ledger.uncertain("one", {"reason": "prior unknown"})
    with pytest.raises(api.BudgetStopped) as error:
        client.complete(wire(), request_id="two", slot_id="slot", condition="condition", prompt_upper_bound=100)
    assert not isinstance(error.value, api.PreDispatchBudgetStopped)
    assert len(fake.calls) == 1 and fake.calls[0][:2] == ("POST", "/chat/completions")
    assert client.ledger.request_status("two")["status"] == "uncertain"


def counter(request):
    return {"prompt_tokens": 100, "method": "test_bound_counter", "request_sha256": digest(json_bytes(request))}


def adapter(tmp_path, result):
    calls = []

    def post(path, payload):
        if path == "/tokenize":
            return counter(payload["wire"])
        calls.append(path)
        if isinstance(result, BaseException):
            raise result
        return copy.deepcopy(result)

    value = bridge.DeepSeekEpisodeAdapter(post=post, arm="PROJECT", slot_id="slot", condition_id="condition",
        token_budget=5_000_000, folder=tmp_path / "episode", allowed_tool_names={"read_file"})
    return value, calls


@pytest.mark.parametrize("unsent", [False, True])
def test_episode_cancels_only_proven_unsent_requests(tmp_path, unsent):
    error = api.PreDispatchBudgetStopped("cash_stop") if unsent else api.BudgetStopped("bad_after_http")
    value, calls = adapter(tmp_path, error)
    request = value.request(wire()["messages"], wire()["tools"])
    expected = bridge.RemoteEpisodeBoundary if unsent else api.BudgetStopped
    with pytest.raises(expected):
        value.complete(request)
    assert calls == ["/chat/completions"]
    snapshot = value.ledger.snapshot()
    assert snapshot["attempts"] == (0 if unsent else 1)
    assert (snapshot["inflight"] is None) is unsent


def test_episode_keeps_actual_usage_of_withheld_response(tmp_path):
    response = body(output=32769)
    value, _ = adapter(tmp_path, api.ProviderOutputBoundViolation("output_bound", body=response))
    with pytest.raises(api.ProviderOutputBoundViolation):
        value.complete(value.request(wire()["messages"], wire()["tools"]))
    snapshot = value.ledger.snapshot()
    assert snapshot["known_actual_tokens"] == 32869
    assert snapshot["complete_actual_tokens"] == 32869
    assert (value.folder / "response-0001.json").exists()
    assert not value.history.messages


def test_host_broker_checks_scope_and_cash_before_any_api_request(tmp_path):
    fake = FakeTransport(body())
    client = api.DeepSeekClient(ledger_path=tmp_path / "cash.sqlite", api_key="test-only",
                               allowed_tool_names={"read_file"}, transport=fake)
    host = bridge.HostDeepSeekTransport(client=client, counter=counter, metadata_dir=tmp_path / "meta",
        authorize=lambda payload: {"condition_id": "condition", "token_budget": 5_000_000})
    with pytest.raises(ValueError, match="No search"):
        host.post("/v1/tools/search", {"wire": wire()})
    request = {"wire": wire(), "request_id": "one", "slot_id": "slot", "condition": "condition",
               "usage_id": "agent", "prompt_upper_bound": 100}
    with pytest.raises(ValueError, match="reservation differs"):
        host.post("/chat/completions", {**request, "prompt_upper_bound": 101})
    assert not fake.calls
    assert host.post("/chat/completions", request)["usage"]["total_tokens"] == 110
    assert len(fake.calls) == 1
    saved = client.ledger.request_status("one")
    assert json.loads(saved["usage_json"])["total_tokens"] == 110
