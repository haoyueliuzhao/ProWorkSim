"""Necessary controls: concurrent hard cap, unknowns, billing and network boundary."""
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

import pytest

from proworksim.software_benchmark_deepseek_api_v055 import (
    APIUncertainFailure, BudgetLedger, BudgetStopped, DeepSeekClient, DirectHTTPS,
    MAX_OUTPUT_TOKENS, MODEL, slot_user_id, validate_payload,
)


def _reserve_many(args):
    path, worker = args
    ledger = BudgetLedger(path, max_concurrency=2500)
    count = 0
    for index in range(100):
        try:
            ledger.reserve(request_id=f"{worker}-{index}", slot_id="cpu-control",
                           condition="fixture", usage_id="agent", request_sha256="cpu",
                           max_output_tokens=MAX_OUTPUT_TOKENS)
            count += 1
        except BudgetStopped:
            break
    return count


def _request(thinking=False):
    return {"model": MODEL, "messages": [{"role": "user", "content": "neutral fixture"}],
            "thinking": {"type": "enabled" if thinking else "disabled"},
            "stream": False, "max_tokens": 64}


def _response():
    return {"id": "fixture-unique", "model": MODEL, "system_fingerprint": "cpu-only",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                      "prompt_cache_hit_tokens": 80, "prompt_cache_miss_tokens": 20,
                      "prompt_tokens_details": {"cached_tokens": 80},
                      "completion_tokens_details": {"reasoning_tokens": 15}}}


def test_multiprocess_cap_and_persistent_policy(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    ledger = BudgetLedger(path, max_concurrency=2500)
    with ProcessPoolExecutor(max_workers=8, mp_context=multiprocessing.get_context("fork")) as pool:
        counts = list(pool.map(_reserve_many, [(path, i) for i in range(8)]))
    status = ledger.snapshot()
    assert sum(counts) == status["attempts"] == 381
    assert 1990 < status["committed_upper_cny"] <= 2000
    assert status["inflight_count"] == 381
    with pytest.raises(ValueError, match="policy differs"):
        BudgetLedger(path, max_concurrency=64)


def test_actual_usage_cache_reasoning_and_no_replay(tmp_path, monkeypatch):
    monkeypatch.setattr("proworksim.software_benchmark_deepseek_api_v055._now",
                        lambda: "2026-10-21T02:00:00+00:00")
    class Fixture:
        calls = 0

        def request(self, method, path, payload):
            assert (method, path) == ("POST", "/chat/completions")
            assert payload["user_id"] == slot_user_id("slot", "REF")
            self.calls += 1
            return _response()

    fixture = Fixture()
    client = DeepSeekClient(ledger_path=tmp_path / "bill.sqlite3", api_key="fixture",
                           allowed_tool_names=set(), transport=fixture)
    client.complete(_request(), request_id="first", slot_id="slot", condition="REF")
    state = client.ledger.snapshot()
    # reasoning=15 is a subset of completion=20, never another output charge.
    assert state["settled_upper_cny"] == (80 * 40 + 20 * 2000 + 20 * 8000) / 1e9
    assert state["inflight_count"] == 0 and state["uncertain_reserved_cny"] == 0
    with pytest.raises(BudgetStopped, match="already_attempted"):
        client.complete(_request(), request_id="first", slot_id="slot", condition="REF")
    assert fixture.calls == 1


def test_unknown_retains_full_reservation_and_disallows_replay(tmp_path):
    class Fixture:
        calls = 0

        def request(self, *args):
            self.calls += 1
            raise TimeoutError("potential-credential-must-not-leak")

    fixture = Fixture()
    client = DeepSeekClient(ledger_path=tmp_path / "unknown.sqlite3", api_key="fixture",
                           allowed_tool_names=set(), transport=fixture)
    with pytest.raises(APIUncertainFailure) as failure:
        client.complete(_request(), request_id="unknown", slot_id="slot", condition="PROJECT")
    assert "potential-credential" not in str(failure.value)
    state = client.ledger.snapshot()
    assert state["uncertain_reserved_cny"] == 2.097664
    assert state["inflight_count"] == 0 and state["attempts"] == 1
    with pytest.raises(BudgetStopped):
        client.complete(_request(), request_id="unknown", slot_id="slot", condition="PROJECT")
    assert fixture.calls == 1


def test_search_server_tools_remote_content_and_thinking_guard():
    request = _request(True)
    request["tools"] = [{"type": "web_search"}]
    with pytest.raises(ValueError, match="local function"):
        validate_payload(request, {"read_file"})
    request["tools"] = [{"type": "function", "function": {"name": "read_file"}}]
    request["messages"].append({"role": "assistant", "content": "", "tool_calls": []})
    with pytest.raises(ValueError, match="reasoning_content"):
        validate_payload(request, {"read_file"})
    request["messages"][-1]["reasoning_content"] = ""
    validate_payload(request, {"read_file"})
    request["messages"][0]["content"] = [{"type": "image_url", "image_url": "https://example.com"}]
    with pytest.raises(ValueError, match="Only text"):
        validate_payload(request, {"read_file"})
    request = _request()
    request["web_search"] = True
    with pytest.raises(ValueError, match="Unapproved API fields"):
        validate_payload(request, set())


def test_direct_fixed_host_ignores_proxy_and_does_not_redirect(monkeypatch):
    recorded = []

    class Response:
        status = 302

        def read1(self, amount):
            return b""

    class Connection:
        def __init__(self, host, port, **kwargs):
            recorded.append((host, port))

        def request(self, method, path, **kwargs):
            recorded.append((method, path))

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy-must-not-be-used.invalid:81")
    monkeypatch.setenv("ALL_PROXY", "socks5://proxy-must-not-be-used.invalid:82")
    monkeypatch.setattr("http.client.HTTPSConnection", Connection)
    direct = DirectHTTPS("fixture")
    with pytest.raises(APIUncertainFailure):
        direct.request("POST", "/chat/completions", _request())
    assert recorded == [("api.deepseek.com", 443), ("POST", "/chat/completions")]
    with pytest.raises(ValueError, match="Endpoint prohibited"):
        direct.request("POST", "/search", {"query": "benchmark answer"})
    assert len(recorded) == 2


def test_provider_output_over_bound_halts_budget(tmp_path):
    ledger = BudgetLedger(tmp_path / "violation.sqlite3")
    ledger.reserve(request_id="invalid", slot_id="slot", condition="MATCH", usage_id="agent",
                   request_sha256="cpu", max_output_tokens=1)
    with pytest.raises(BudgetStopped, match="exceeded"):
        ledger.settle("invalid", _response())
    assert ledger.snapshot()["halted"] == "provider_usage_exceeded_authorized_request_bound"
    with pytest.raises(BudgetStopped, match="halted"):
        ledger.reserve(request_id="next", slot_id="slot", condition="MATCH", usage_id="agent",
                       request_sha256="cpu", max_output_tokens=64)

    class Fixture:
        def request(self, *args):
            return _response()

    client = DeepSeekClient(ledger_path=tmp_path / "client-violation.sqlite3", api_key="fixture",
                           allowed_tool_names=set(), transport=Fixture())
    request = {**_request(), "max_tokens": 1}
    with pytest.raises(APIUncertainFailure):
        client.complete(request, request_id="entered", slot_id="slot", condition="MATCH")
    assert client.ledger.request_status("entered")["status"] == "uncertain"
    assert client.ledger.snapshot()["halted"]
