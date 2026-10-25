"""CPU envelopes/FIFOs only: no Docker, real model connection or listener."""
from collections import deque
import os
import threading
import time
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_model_fifo_v061 as fifo
from proworksim.software_benchmark_exact_transport_v054 import HTTPFailure


def test_host_failure_keeps_original_http_evidence_without_retry():
    calls = []
    def post(path, payload):
        calls.append((path, payload))
        raise HTTPFailure("Non-200; no redirect or retry", status=400, raw_body='{"error":"bad schema"}')
    value = fifo.model_response({"id": 1, "path": "/tokenize", "payload": {"messages": []}},
                               SimpleNamespace(post=post), 1)
    assert len(calls) == 1 and value["ok"] is False
    assert value["http_failure"]["http_status"] == 400
    assert value["http_failure"]["raw_response_body"] == '{"error":"bad schema"}'


@pytest.mark.parametrize("bad", [
    {"id": 1, "path": "https://elsewhere/", "payload": {}},
    {"id": 2, "path": "/tokenize", "payload": {}},
    {"id": 1, "path": "/tokenize", "payload": {}, "authorization": "unexpected"},
])
def test_unapproved_endpoint_or_sequence_never_dispatches(bad):
    transport = SimpleNamespace(post=lambda *_: pytest.fail("Must not dispatch"))
    with pytest.raises(ValueError):
        fifo.model_response(bad, transport, 1)


def test_real_private_fifo_roundtrip_preserves_json_and_error(tmp_path):
    request_fd = fifo.open_fifo(tmp_path / "model-request.fifo", create=True)
    response_fd = fifo.open_fifo(tmp_path / "model-response.fifo", create=True)
    client = fifo.FifoModelTransport("http://127.0.0.1:18161", control=tmp_path)
    failures = []
    def server():
        try:
            reader = fifo.LineReader(request_fd)
            first = reader.read(time.monotonic() + 5)
            assert first["payload"] == {"messages": ["line one\n第二行"]}
            fifo.write_frame(response_fd, {"id": first["id"], "ok": True, "body": {"tokens": [1, 2], "count": 2}}, time.monotonic() + 5)
            second = reader.read(time.monotonic() + 5)
            fifo.write_frame(response_fd, {"id": second["id"], "ok": False,
                "http_failure": {"reason": "shutdown", "http_status": 500, "raw_response_body": "original error"}}, time.monotonic() + 5)
        except Exception as error:
            failures.append(error)
    thread = threading.Thread(target=server)
    thread.start()
    try:
        assert client.post("/tokenize", {"messages": ["line one\n第二行"]}) == {"tokens": [1, 2], "count": 2}
        with pytest.raises(HTTPFailure) as caught:
            client.post("/v1/chat/completions", {"messages": []})
        assert caught.value.evidence["http_status"] == 500 and caught.value.evidence["raw_response_body"] == "original error"
    finally:
        client.close()
        os.close(request_fd)
        os.close(response_fd)
        thread.join(timeout=5)
    assert not thread.is_alive() and not failures


def test_fifo_does_not_follow_regular_file_or_symlink(tmp_path):
    target = tmp_path / "ordinary"
    target.write_text("not a channel")
    with pytest.raises(ValueError, match="FIFO"):
        fifo.open_fifo(target)
    link = tmp_path / "symlink"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="FIFO"):
        fifo.open_fifo(link)


def test_host_bridge_normal_stop_and_controller_eof_are_distinct(monkeypatch):
    from proworksim import software_benchmark_dispatch_v061 as policy
    monkeypatch.setattr(policy, "require_v061_allowed", lambda *a, **k: {})
    stopped = threading.Event()
    frames = deque([fifo.encoded_frame({"type": "model_bridge_ready", "version": fifo.VERSION}),
                    fifo.encoded_frame({"id": 1, "path": "/tokenize", "payload": {}})])
    sent = []
    class Channel:
        def readline(self, deadline):
            return frames.popleft()
        def write(self, raw):
            sent.append(fifo.decode_frame(raw))
    def post(*args):
        stopped.set()
        return {"count": 1, "tokens": [1]}
    transport = SimpleNamespace(port=18161, timeout_seconds=1800, post=post)
    result = fifo.serve_model_channel(Channel(), endpoint="unused", key_file="unused",
        deadline=time.monotonic() + 10, stop_event=stopped, original_slot_id="cpu", transport=transport)
    assert result["status"] == "stopped_after_controller" and result["requests"] == 1
    assert sent[-1] == {"op": "stop"}
    frames.extend([fifo.encoded_frame({"type": "model_bridge_ready", "version": fifo.VERSION}), b""])
    stopped.clear()
    result = fifo.serve_model_channel(Channel(), endpoint="unused", key_file="unused",
        deadline=time.monotonic() + 10, stop_event=stopped, original_slot_id="cpu", transport=transport)
    assert result["status"] == "channel_closed" and result["requires_controller_exit_classification"]


def test_cancellation_before_dispatch_cannot_reopen_or_send_post(tmp_path, monkeypatch):
    key = tmp_path / "key"
    key.write_text("k" * 32)
    client = fifo.CancellableLoopbackHTTP("http://127.0.0.1:18161", key)
    events = []
    class Connection:
        sock = None
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("127.0.0.1", 18161, 10)
        def connect(self):
            self.sock = SimpleNamespace(settimeout=lambda value: events.append(("timeout", value)),
                                       shutdown=lambda how: events.append(("shutdown", how)))
            client.cancelled.set()
        def request(self, *args, **kwargs):
            pytest.fail("Controller ended before dispatch; never send/retry POST")
        def close(self):
            events.append("close")
    monkeypatch.setattr(fifo.http.client, "HTTPConnection", Connection)
    with pytest.raises(HTTPFailure, match="before model dispatch"):
        client.post("/v1/chat/completions", {})
    assert ("shutdown", fifo.socket.SHUT_RDWR) in events
    assert client.active is None
    with pytest.raises(HTTPFailure, match="cancelled"):
        client.post("/tokenize", {})


def test_abort_interrupts_owned_response_socket_only(tmp_path):
    key = tmp_path / "key"
    key.write_text("k" * 32)
    client = fifo.CancellableLoopbackHTTP("http://127.0.0.1:18161", key)
    calls = []
    response_socket = SimpleNamespace(shutdown=lambda how: calls.append(("response", how)))
    client.active = SimpleNamespace(sock=None, close=lambda: calls.append("connection_close"))
    client.response = SimpleNamespace(fp=SimpleNamespace(raw=SimpleNamespace(_sock=response_socket)))
    client.abort()
    assert calls == [("response", fifo.socket.SHUT_RDWR), "connection_close"]
    assert client.cancelled.is_set()


@pytest.mark.parametrize("partial", [False, True])
def test_idle_exec_reset_is_deferred_to_controller_only_with_empty_frames(monkeypatch, partial):
    from proworksim import software_benchmark_dispatch_v061 as policy
    monkeypatch.setattr(policy, "require_v061_allowed", lambda *a, **k: {})
    class Channel:
        def __init__(self):
            self.first = True
            self.buffer = bytearray(b"{" if partial else b"")
            self.decoder = SimpleNamespace(buffer=bytearray())
        def readline(self, deadline):
            if self.first:
                self.first = False
                return fifo.encoded_frame({"type": "model_bridge_ready", "version": fifo.VERSION})
            raise ConnectionResetError("owned controller PID1 ended")
    client = SimpleNamespace(port=18161, timeout_seconds=1800,
                             post=lambda *_: pytest.fail("No model request was received"))
    result = fifo.serve_model_channel(Channel(), endpoint="unused", key_file="unused",
        deadline=time.monotonic() + 10, stop_event=threading.Event(), original_slot_id="cpu", transport=client)
    assert result["requests"] == 0
    assert result["status"] == ("technical_unknown" if partial else "channel_closed")
    if not partial:
        assert result["requires_controller_exit_classification"] is True
        assert result["idle_exec_reset"]["buffered_stdout_bytes"] == 0
