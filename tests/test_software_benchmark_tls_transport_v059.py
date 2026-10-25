"""Pure CPU transport controls: no sockets, Docker, listeners, or real TLS."""
import ast
from collections import deque
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_tls_transport_v059 as relay


def docker_frame(body, stream=1):
    return bytes([stream, 0, 0, 0]) + len(body).to_bytes(4, "big") + body


class FakeSocket:
    def __init__(self, incoming=(), address=("8.8.8.8", 443), short_write=3):
        self.incoming = deque(incoming)
        self.address = address
        self.short_write = short_write
        self.sent = bytearray()
        self.closed = False
        self.shutdowns = []

    def recv(self, size):
        data = self.incoming.popleft()
        if len(data) > size:
            self.incoming.appendleft(data[size:])
        return data[:size]

    def send(self, data):
        size = min(len(data), self.short_write)
        self.sent.extend(data[:size])
        return size

    def settimeout(self, value):
        assert 0 < value <= relay.IDLE_SECONDS

    def getpeername(self):
        return self.address

    def shutdown(self, how):
        self.shutdowns.append(how)

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def no_real_sockets(monkeypatch):
    monkeypatch.setattr(relay.socket, "socket", lambda *a, **k: pytest.fail("Real socket forbidden in CPU controls"))
    monkeypatch.setattr(relay, "require_tls_diagnostic_allowed", lambda *a, **k: {})


def run(channel, peer, schedule, *, budget=None, **kwargs):
    calls = []
    order = deque(schedule)

    def connect(address, timeout):
        calls.append((address, timeout))
        return peer

    result = relay.relay_once(channel, "8.8.8.8", budget or relay.TransferBudget(),
        instance_id="psf__requests-1766", resolved_ips=("8.8.8.8",),
        connector=connect, wait=lambda *args: (order.popleft(), [], []), clock=lambda: 0.0, **kwargs)
    return result, calls


def test_partial_docker_and_inner_frames_keep_binary_payload():
    payload = b"\0\xff\x16\x03\x03TLS-bytes"
    encoded = docker_frame(relay.packet(relay.DATA, payload))
    outer, inner = relay.DockerFrameDecoder(), relay.PacketDecoder()
    received = []
    for byte in encoded:
        for stream, body in outer.feed(bytes([byte])):
            assert stream == 1
            received.extend(inner.feed(body))
    outer.finish()
    inner.finish()
    assert received == [(relay.DATA, payload)]
    with pytest.raises(relay.RelayError, match="Oversized"):
        relay.DockerFrameDecoder().feed(b"\x01\0\0\0" + (relay.MAX_DOCKER_FRAME + 1).to_bytes(4, "big"))
    with pytest.raises(relay.RelayError, match="Oversized"):
        relay.PacketDecoder().feed(relay.HEADER.pack(relay.DATA, relay.CHUNK + 1))


def test_full_duplex_short_writes_and_half_close_preserve_tls_bytes():
    hello, reply = b"\x16client TLS hello", b"\x17server TLS bytes\0\xff"
    raw = FakeSocket([docker_frame(relay.packet(relay.READY) + relay.packet(relay.ACCEPT)
                                  + relay.packet(relay.DATA, hello)),
                      docker_frame(relay.packet(relay.EOF)), docker_frame(relay.packet(relay.DONE))])
    wrapper = SimpleNamespace(_sock=raw, close=lambda: None)
    peer = FakeSocket([reply, b""])
    order = deque([[raw], [peer], [raw], [peer], [raw]])
    ready = []
    budget = relay.TransferBudget()
    result = relay.relay_once(wrapper, "8.8.8.8", budget, instance_id="psf__requests-1921",
        resolved_ips=("8.8.8.8",), connector=lambda address, timeout: peer,
        wait=lambda *args: (order.popleft(), [], []), clock=lambda: 0.0, on_ready=lambda: ready.append(True))
    assert result["ok"] is True and result["status"] == "completed" and ready == [True]
    assert peer.sent == hello
    assert raw.sent == relay.packet(relay.DATA, reply) + relay.packet(relay.EOF)
    assert peer.shutdowns == [relay.socket.SHUT_WR]
    assert result["bytes_to_upstream"] == len(hello) and result["bytes_from_upstream"] == len(reply)
    assert budget.bytes_used == len(hello) + len(reply) and not budget.active
    assert raw.closed and peer.closed


@pytest.mark.parametrize("stream,label", [(2, "stderr"), (3, "system error")])
def test_stderr_and_system_error_are_never_forwarded(stream, label):
    channel = FakeSocket([docker_frame(b"diagnostic bytes", stream)])
    peer = FakeSocket()
    result, calls = run(channel, peer, [[channel]])
    assert result["ok"] is False and label in result["error"]["message"]
    assert not calls and channel.closed and not peer.sent


def test_truncated_exec_stream_cannot_succeed():
    channel = FakeSocket([docker_frame(relay.packet(relay.READY))[:6], b""])
    result, calls = run(channel, FakeSocket(), [[channel], [channel]])
    assert result["ok"] is False and "Truncated Docker" in result["error"]["message"]
    assert calls == [] and channel.closed


def test_two_sequential_sessions_and_shared_time_and_byte_limits():
    budget = relay.TransferBudget()
    assert budget.begin(5) == 1
    with pytest.raises(relay.RelayError, match="sequential"):
        budget.begin(5)
    budget.end()
    assert budget.begin(6) == 2
    budget.end()
    with pytest.raises(relay.RelayError, match="sequential"):
        budget.begin(7)
    budget = relay.TransferBudget()
    budget.begin(0)
    budget.end()
    with pytest.raises(relay.RelayError, match="exhausted"):
        budget.begin(121)
    budget = relay.TransferBudget()
    budget.consume(relay.MAX_BYTES)
    with pytest.raises(relay.RelayError, match="budget"):
        budget.consume(1)
    assert budget.bytes_used == relay.MAX_BYTES


def test_payload_limit_stops_before_upstream_write():
    budget = relay.TransferBudget()
    budget.consume(relay.MAX_BYTES - 2)
    channel = FakeSocket([docker_frame(relay.packet(relay.READY) + relay.packet(relay.ACCEPT)
                                      + relay.packet(relay.DATA, b"too long"))])
    peer = FakeSocket()
    result, calls = run(channel, peer, [[channel]], budget=budget)
    assert len(calls) == 1 and result["upstream_connected"] is True
    assert result["ok"] is False and "payload budget" in result["error"]["message"]
    assert peer.sent == b"" and budget.bytes_used == relay.MAX_BYTES - 2
    assert peer.closed and channel.closed


def test_no_retry_after_connect_failure_and_no_success_on_idle_timeout():
    channel = FakeSocket([docker_frame(relay.packet(relay.READY) + relay.packet(relay.ACCEPT))])
    calls = []

    def connect(address, timeout):
        calls.append(address)
        raise TimeoutError("single connection failed")

    result = relay.relay_once(channel, "8.8.8.8", relay.TransferBudget(),
        instance_id="psf__requests-1766", resolved_ips=("8.8.8.8",), connector=connect,
        wait=lambda *args: ([channel], [], []), clock=lambda: 0.0)
    assert calls == [("8.8.8.8", 443)] and result["ok"] is False and channel.closed
    channel = FakeSocket()
    result, calls = run(channel, FakeSocket(), [[]])
    assert result["ok"] is False and "idle timeout" in result["error"]["message"]
    assert calls == []


def test_pending_or_unapproved_target_stops_before_budget_or_connect(monkeypatch):
    channel = FakeSocket()
    budget = relay.TransferBudget()
    calls = []
    monkeypatch.setattr(relay, "require_tls_diagnostic_allowed", lambda *a: (_ for _ in ()).throw(PermissionError("pending")))
    result = relay.relay_once(channel, "8.8.8.8", budget, instance_id="psf__requests-1766",
        resolved_ips=("8.8.8.8",), connector=lambda *a: calls.append(a), clock=lambda: 0.0)
    assert result["status"] == "rejected" and budget.sessions == 0 and not calls and channel.closed
    monkeypatch.setattr(relay, "require_tls_diagnostic_allowed", lambda *a: {})
    result = relay.relay_once(FakeSocket(), "127.0.0.1", budget, instance_id="psf__requests-1766",
        resolved_ips=("127.0.0.1",), connector=lambda *a: calls.append(a), clock=lambda: 0.0)
    assert result["status"] == "rejected" and budget.sessions == 0 and not calls


def test_container_source_is_python39_and_has_only_fixed_loopback_listener():
    tree = ast.parse(relay.CONTAINER_RELAY_SOURCE, feature_version=(3, 9))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    binds = [node for node in calls if isinstance(node.func, ast.Attribute) and node.func.attr == "bind"]
    assert len(binds) == 1 and ast.literal_eval(binds[0].args[0]) == ("127.0.0.1", 443)
    assert not any(isinstance(node.func, ast.Attribute) and node.func.attr in {"connect", "create_connection"}
                   for node in calls)
    assert "ssl" not in {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
