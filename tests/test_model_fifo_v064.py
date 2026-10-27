import json
import threading
import time
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_model_fifo_v064 as fifo
from proworksim import software_benchmark_deepseek_api_v064 as api
from proworksim import software_benchmark_deepseek_adapter_v064 as bridge


@pytest.mark.parametrize("kind", [api.PreDispatchBudgetStopped, api.PreDispatchConcurrencyBusy,
                                  api.BudgetStopped, api.APIUncertainFailure])
def test_provider_error_round_trip_keeps_dispatch_provenance(kind):
    value = fifo.provider_failure(kind("fixed_reason"))
    with pytest.raises(kind) as error:
        fifo.raise_provider_failure(value)
    assert getattr(error.value, "before_dispatch_proven", False) is value["before_dispatch_proven"]
    value["before_dispatch_proven"] = not value["before_dispatch_proven"]
    with pytest.raises(ValueError, match="cannot invent"):
        fifo.raise_provider_failure(value)


def test_withheld_body_survives_fifo_without_becoming_agent_response():
    body = {"id": "known-bill", "usage": {"total_tokens": 10}}
    original = api.ProviderOutputBoundViolation("above_experimental_limit", body=body)
    envelope = fifo.provider_failure(original)
    with pytest.raises(api.ProviderOutputBoundViolation) as error:
        fifo.raise_provider_failure(envelope)
    assert error.value.authoritative_response == body
    assert error.value.before_dispatch_proven is False


def test_host_channel_counts_admission_wait_separately_from_actual_model_attempts(monkeypatch):
    from proworksim import software_benchmark_dispatch_v064 as policy
    monkeypatch.setattr(policy, "require_v064_allowed", lambda *args, **kwargs: None)
    class Transport:
        port, timeout_seconds = 18219, 1800
        def validate_identity(self, slot_id):
            assert slot_id == "planned-slot"
        def post(self, path, payload):
            if payload.get("wait"):
                raise api.PreDispatchConcurrencyBusy("cash_owned_by_other_inflight")
            return {"count_only": path == "/tokenize"}
    class Channel:
        def __init__(self):
            self.lines = [
                {"type": "model_bridge_ready", "version": fifo.VERSION},
                {"id": 1, "path": "/tokenize", "payload": {}},
                {"id": 2, "path": "/chat/completions", "payload": {"wait": True}},
                {"id": 3, "path": "/chat/completions", "payload": {}},
            ]
            self.writes = []
        def readline(self, deadline):
            return fifo.encoded_frame(self.lines.pop(0)) if self.lines else b""
        def write(self, raw):
            self.writes.append(json.loads(raw))
    channel = Channel()
    result = fifo.serve_model_channel(channel, endpoint="http://127.0.0.1:18219", key_file=None,
        deadline=time.monotonic()+10, stop_event=threading.Event(), slot_id="planned-slot", transport=Transport())
    assert result["status"] == "channel_closed"
    assert result["requests"] == 3 and result["count_requests"] == 1
    assert result["generation_requests"] == 1 and result["predispatch_admission_replies"] == 1
    assert channel.writes[1]["provider_failure"]["before_dispatch_proven"] is True


def test_episode_http_cancellation_does_not_cancel_another_episode(tmp_path):
    client = api.DeepSeekClient(ledger_path=tmp_path / "cash.sqlite", api_key="test-only",
                               allowed_tool_names={"read_file"})
    arguments = {"client": client, "counter": lambda _: {}, "metadata_dir": tmp_path / "meta",
                 "authorize": lambda _: {}, "condition_id": "condition"}
    one = bridge.HostDeepSeekTransport(**arguments, slot_id="one")
    two = bridge.HostDeepSeekTransport(**arguments, slot_id="two")
    assert one.client.ledger.path == two.client.ledger.path == client.ledger.path
    assert one.client.transport is not two.client.transport
    one.abort()
    assert one.client.transport.cancelled.is_set()
    assert not two.client.transport.cancelled.is_set()
    assert not client.transport.cancelled.is_set()
    with pytest.raises(ValueError, match="not bound"):
        one.validate_identity("two")


def test_direct_https_has_fixed_tls_host_and_rejects_search_without_network(monkeypatch):
    calls = []
    class Connection:
        def __init__(self, host, port, **kwargs):
            calls.append((host, port, kwargs))
            self.sock = SimpleNamespace(settimeout=lambda _: None)
            self.auto_open = True
        def connect(self):
            pass
        def request(self, method, path, **kwargs):
            assert self.auto_open is False
            calls.append((method, path, kwargs["headers"]["User-Agent"]))
        def getresponse(self):
            chunks = [b'{"data":[]}', b'']
            return SimpleNamespace(status=200, read1=lambda _: chunks.pop(0))
        def close(self):
            pass
    monkeypatch.setattr(api.http.client, "HTTPSConnection", Connection)
    monkeypatch.setenv("HTTPS_PROXY", "http://unused.invalid:8080")
    transport = api.DirectHTTPS("test-only")
    with pytest.raises(ValueError, match="fixed official"):
        transport.request("POST", "/v1/tools/search", {})
    assert not calls
    assert transport.request("GET", "/models") == {"data": []}
    assert calls[0][:2] == ("api.deepseek.com", 443)
    assert calls[1][:2] == ("GET", "/models")
