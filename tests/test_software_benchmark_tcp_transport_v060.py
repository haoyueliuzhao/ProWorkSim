"""CPU-only protocol controls: no actual sockets, Docker, DNS or TLS calls."""
import ast
import builtins
from collections import deque
import errno
from types import SimpleNamespace
import threading

import pytest

from proworksim import software_benchmark_tcp_transport_v060 as relay


def docker_frame(body, stream=1):
    return bytes([stream, 0, 0, 0]) + len(body).to_bytes(4, "big") + body


def opened(identity, port):
    return relay.packet(relay.OPEN, identity, port.to_bytes(2, "big"))


class FakeSocket:
    def __init__(self, incoming=(), port=443, short_write=65536):
        self.incoming = deque(incoming)
        self.port, self.short_write = port, short_write
        self.sent = bytearray()
        self.closed = False
        self.shutdowns = []

    def recv(self, size):
        value = self.incoming.popleft()
        if isinstance(value, Exception):
            raise value
        if len(value) > size:
            self.incoming.appendleft(value[size:])
        return value[:size]

    def send(self, value):
        count = min(len(value), self.short_write)
        self.sent.extend(value[:count])
        return count

    def setblocking(self, value):
        assert value is False

    def getpeername(self):
        return ("8.8.8.8", self.port)

    def shutdown(self, how):
        self.shutdowns.append(how)

    def close(self):
        self.closed = True


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def no_real_io(monkeypatch):
    monkeypatch.setattr(relay.socket, "socket", lambda *a, **k: pytest.fail("Real socket forbidden"))


def run(channel, peers, schedule, *, stop=None, clock=None, connector=None, **kwargs):
    stop = stop or threading.Event()
    clock = clock or Clock()
    order = deque(schedule)
    peer_queue = deque(peers)
    calls = []

    def connect(address, timeout):
        calls.append(address)
        value = peer_queue.popleft()
        if isinstance(value, Exception):
            raise value
        return value

    def wait(readers, writers, exceptional, delay):
        clock.now += min(delay, 0.1)
        if not order:
            pytest.fail("Unexpected wait after scripted terminal condition")
        current = order.popleft()
        if callable(current):
            return current(readers, writers, stop)
        ready, writable = current
        assert all(item in readers for item in ready)
        assert all(item in writers for item in writable)
        return ready, writable, []

    result = relay.relay_many(channel, "8.8.8.8", instance_id="psf__requests-1766",
        resolved_ips=("8.8.8.8",), stop_event=stop, authorize=lambda task: {},
        connector=connector or connect, wait=wait, clock=clock, **kwargs)
    return result, calls


def stop_step(readers, writers, event):
    event.set()
    return [], [], []


def test_two_ports_and_concurrent_binary_streams_preserve_bytes_and_tcp_eof():
    hello1, hello2 = b"GET /get HTTP/1.1\r\n\r\n", b"\x16\x03\x03opaque\0\xff"
    reply1, reply2 = b"HTTP/1.1 200 OK\r\n", b"\x17\x03\x03encrypted\0\xff"
    channel = FakeSocket([
        docker_frame(relay.packet(relay.READY) + opened(1, 80) + opened(2, 443)
                     + relay.packet(relay.DATA, 1, hello1) + relay.packet(relay.DATA, 2, hello2)),
        docker_frame(relay.packet(relay.EOF, 1) + relay.packet(relay.EOF, 2)),
        docker_frame(relay.packet(relay.DONE)),
    ])
    first, second = FakeSocket([reply1, b""], port=80), FakeSocket([reply2, b""])
    result, calls = run(channel, [first, second], [
        ([channel], []), ([], [first, second]), ([first, second], []),
        ([channel], [channel]), ([first, second], []), ([], [channel]),
        stop_step, ([], [channel]), ([channel], []),
    ])
    assert result["ok"] and result["status"] == "completed"
    assert calls == [("8.8.8.8", 80), ("8.8.8.8", 443)]
    assert first.sent == hello1 and second.sent == hello2
    assert first.shutdowns == second.shutdowns == [relay.socket.SHUT_WR]
    assert [item["outcome"] for item in result["connections"]] == ["tcp_eof", "tcp_eof"]
    assert result["max_active_observed"] == 2
    assert result["application_payload_bytes"] == sum(map(len, (hello1, hello2, reply1, reply2)))
    assert result["application_success_not_inferred"]
    messages = relay.PacketDecoder().feed(channel.sent)
    assert (relay.DATA, 1, reply1) in messages and (relay.DATA, 2, reply2) in messages
    assert messages[-1] == (relay.STOP, 0, b"")
    assert all(item.closed for item in (channel, first, second))


def test_client_reset_is_explicit_and_does_not_abort_another_connection():
    channel = FakeSocket([
        docker_frame(relay.packet(relay.READY) + opened(1, 443) + opened(2, 443)),
        docker_frame(relay.packet(relay.RESET, 1, b"recv:ConnectionResetError") + relay.packet(relay.EOF, 2)),
        docker_frame(relay.packet(relay.DONE)),
    ])
    first, second = FakeSocket(), FakeSocket([b"opaque", b""])
    result, _ = run(channel, [first, second], [
        ([channel], []), ([channel], []), ([second], [channel]),
        ([second], [channel]), ([], [channel]), stop_step, ([], [channel]), ([channel], []),
    ])
    assert result["ok"] and result["network_errors"] == []
    assert result["connections"][0]["outcome"] == "client_reset"
    assert result["connections"][0]["client_reset_detail"] == "recv:ConnectionResetError"
    assert result["connections"][1]["outcome"] == "tcp_eof"
    assert first.shutdowns == []  # A reset is never manufactured into clean EOF.


def test_partial_writes_and_keepalive_stop_are_accounted_without_claiming_eof():
    channel = FakeSocket([docker_frame(relay.packet(relay.READY) + opened(1, 443)
        + relay.packet(relay.DATA, 1, b"abcdef")), docker_frame(relay.packet(relay.DONE))])
    peer = FakeSocket(short_write=2)
    result, _ = run(channel, [peer], [([channel], []), ([], [peer]), ([], [peer]),
        ([], [peer]), stop_step, ([], [channel]), ([channel], [])])
    assert result["ok"] and peer.sent == b"abcdef"
    assert result["connections"][0]["outcome"] == "evaluation_stopped"
    assert result["application_payload_bytes"] == 6


def test_many_ready_peers_apply_backpressure_instead_of_overflowing_shared_output():
    channel = FakeSocket([docker_frame(relay.packet(relay.READY) + b"".join(opened(i, 443) for i in range(1, 17))),
                          docker_frame(relay.packet(relay.DONE))])
    peers = [FakeSocket([b"x" * relay.CHUNK]) for _ in range(16)]

    def receive_and_stop(readers, writers, event):
        event.set()
        return list(peers), [], []

    result, _ = run(channel, peers, [([channel], []), receive_and_stop, ([], [channel]),
        ([], [channel]), ([channel], [])])
    # At most the bounded shared queue is read even when all 16 sockets are ready.
    assert result["ok"] and result["bytes_from_upstream"] == 7 * relay.CHUNK
    assert result["max_active_observed"] == 16


def test_open_already_in_flight_during_stop_never_connects_or_sends_frames_after_stop():
    channel = FakeSocket([docker_frame(relay.packet(relay.READY)), docker_frame(opened(1, 443)),
                          docker_frame(relay.packet(relay.DONE))])
    result, calls = run(channel, [], [([channel], []), stop_step,
        ([channel], [channel]), ([channel], [])])
    assert result["ok"] and calls == []
    assert relay.PacketDecoder().feed(channel.sent) == [(relay.STOP, 0, b"")]
    assert result["connections"][0]["outcome"] == "evaluation_stopped_before_connect"


def test_failed_connect_has_no_retry_but_next_connection_is_serviced_and_result_unknown():
    channel = FakeSocket([docker_frame(relay.packet(relay.READY) + opened(1, 80) + opened(2, 443)),
        docker_frame(relay.packet(relay.DONE))])
    peer = FakeSocket()
    result, calls = run(channel, [TimeoutError("unreachable"), peer], [
        ([channel], []), ([], [channel]), stop_step, ([], [channel]), ([channel], []),
    ])
    assert len(calls) == 2 and result["connection_attempts"] == 2
    assert not result["ok"] and result["status"] == "network_failed"
    assert result["connections"][0]["outcome"] == "upstream_connect_error"
    assert result["connections"][1]["outcome"] == "evaluation_stopped"
    assert peer.closed


def test_remote_reset_is_network_failure_and_not_a_successful_client_close():
    channel = FakeSocket([docker_frame(relay.packet(relay.READY) + opened(1, 443)),
        docker_frame(relay.packet(relay.DONE))])
    peer = FakeSocket([ConnectionResetError(errno.ECONNRESET, "reset")])
    result, _ = run(channel, [peer], [([channel], []), ([peer], []), ([], [channel]),
        stop_step, ([], [channel]), ([channel], [])])
    assert not result["ok"] and result["status"] == "network_failed"
    assert result["connections"][0]["outcome"] == "upstream_read_error"


@pytest.mark.parametrize("limits,packets,match,expected_attempts", [
    (relay.Limits(max_connections=1), opened(1, 443) + opened(2, 443), "Connection budget", 1),
    (relay.Limits(max_active=1), opened(1, 443) + opened(2, 443), "Concurrent connection", 1),
    (relay.Limits(max_bytes=2), opened(1, 443) + relay.packet(relay.DATA, 1, b"abc"), "payload budget", 1),
    (relay.Limits(), opened(1, 22), "Unapproved destination", 0),
])
def test_limits_reject_before_excess_connections_or_bytes(limits, packets, match, expected_attempts):
    channel, peer = FakeSocket([docker_frame(relay.packet(relay.READY) + packets)]), FakeSocket()
    result, calls = run(channel, [peer], [([channel], [])], limits=limits)
    assert not result["ok"] and match in result["error"]["message"]
    assert len(calls) == expected_attempts and peer.sent == b""
    assert result["application_payload_bytes"] == 0


def test_idle_deadline_is_per_connection_and_total_deadline_is_not_traffic_resettable():
    clock = Clock()
    channel, peer = FakeSocket([docker_frame(relay.packet(relay.READY) + opened(1, 443))]), FakeSocket()

    def lapse(readers, writers, event):
        clock.now = 2
        return [], [], []

    result, _ = run(channel, [peer], [([channel], []), lapse], clock=clock,
                    limits=relay.Limits(wall_seconds=1))
    assert not result["ok"] and "total deadline" in result["error"]["message"]
    assert peer.closed and channel.closed

    clock = Clock()
    channel = FakeSocket([docker_frame(relay.packet(relay.READY) + opened(1, 443)),
                          docker_frame(relay.packet(relay.DONE))])
    peer = FakeSocket()
    result, _ = run(channel, [peer], [([channel], []), lapse, ([], [channel]),
        stop_step, ([], [channel]), ([channel], [])], clock=clock, limits=relay.Limits(idle_seconds=1))
    assert not result["ok"] and result["connections"][0]["outcome"] == "upstream_idle_timeout"


@pytest.mark.parametrize("public_ip,addresses", [
    ("127.0.0.1", ("127.0.0.1",)), ("10.0.0.1", ("10.0.0.1",)),
    ("8.8.8.8", ("1.1.1.1",)), ("httpbin.org", ("httpbin.org",)),
])
def test_nonpublic_or_unfrozen_targets_never_connect(public_ip, addresses):
    calls, channel = [], FakeSocket()
    result = relay.relay_many(channel, public_ip, instance_id="psf__requests-1766", resolved_ips=addresses,
        stop_event=threading.Event(), authorize=lambda task: {}, connector=lambda *args: calls.append(args))
    assert not result["ok"] and result["status"] == "rejected" and calls == [] and channel.closed


def test_pending_authorization_stops_before_io():
    channel, calls = FakeSocket(), []

    def deny(task):
        raise PermissionError("pending")

    result = relay.relay_many(channel, "8.8.8.8", instance_id="psf__requests-1766", resolved_ips=("8.8.8.8",),
        stop_event=threading.Event(), authorize=deny, connector=lambda *args: calls.append(args))
    assert result["status"] == "rejected" and result["connection_attempts"] == 0 and calls == []


@pytest.mark.parametrize("body", [docker_frame(b"stderr", 2), docker_frame(relay.packet(relay.DONE)), b"\x01\0\0"])
def test_stderr_premature_done_and_truncation_cannot_be_success(body):
    channel = FakeSocket([body, b""])
    result, calls = run(channel, [], [([channel], []), ([channel], [])])
    assert not result["ok"] and result["error"] and not calls


def test_packet_decoders_preserve_arbitrary_binary_and_bound_frames():
    source = docker_frame(relay.packet(relay.DATA, 1, b"\x00\xff\x16\x03opaque"))
    outer, inner, messages = relay.DockerFrameDecoder(), relay.PacketDecoder(), []
    for byte in source:
        for stream, body in outer.feed(bytes([byte])):
            assert stream == 1
            messages.extend(inner.feed(body))
    outer.finish()
    inner.finish()
    assert messages == [(relay.DATA, 1, b"\x00\xff\x16\x03opaque")]
    with pytest.raises(relay.RelayError, match="oversized"):
        inner.feed(relay.HEADER.pack(relay.DATA, 1, relay.CHUNK + 1))
    with pytest.raises(relay.RelayError, match="global"):
        relay.packet(relay.READY, 1)


@pytest.mark.parametrize("error,expected_exit", [(ConnectionResetError(errno.ECONNRESET, "reset"), None),
                                                 (OSError(errno.EBADF, "bad descriptor"), 1)])
def test_generated_container_handles_client_reset_but_rejects_internal_socket_errors(error, expected_exit):
    """Run the actual generated source against fake imports, never real IO."""
    client = FakeSocket([error])

    class Listener(FakeSocket):
        def setsockopt(self, *args):
            pass
        def bind(self, address):
            assert address[0] == "127.0.0.1" and address[1] in (80, 443)
        def listen(self, maximum):
            assert maximum == 16
        def accept(self):
            return client, ("127.0.0.1", 12345)

    first, second = Listener(port=80), Listener(port=443)
    sockets = deque((first, second))
    writes = {1: bytearray(), 2: bytearray()}
    events = deque(([first], [client], [0], []))

    def fake_select(readers, writers, exceptional, timeout):
        ready = events.popleft()
        assert all(item in readers for item in ready)
        return ready, [1] if 1 in writers else [], []

    def write(fd, body):
        writes[fd].extend(body)
        return len(body)

    fake_modules = {
        "socket": SimpleNamespace(socket=lambda *args: sockets.popleft(), AF_INET=2, SOCK_STREAM=1,
            SOL_SOCKET=1, SO_REUSEADDR=2, SHUT_WR=1, SO_LINGER=13),
        "select": SimpleNamespace(select=fake_select),
        "os": SimpleNamespace(set_blocking=lambda *args: None, write=write,
            read=lambda fd, size: relay.packet(relay.STOP)),
        "time": SimpleNamespace(monotonic=lambda: 0),
    }
    real_import = builtins.__import__
    custom_builtins = dict(vars(builtins))
    custom_builtins["__import__"] = lambda name, *args, **kwargs: fake_modules.get(name) or real_import(name, *args, **kwargs)
    if expected_exit is not None:
        with pytest.raises(SystemExit) as caught:
            exec(relay.build_container_source(), {"__builtins__": custom_builtins})
        assert caught.value.code == expected_exit and b"bad descriptor" in writes[2]
    else:
        exec(relay.build_container_source(), {"__builtins__": custom_builtins})
        messages = relay.PacketDecoder().feed(writes[1])
        assert (relay.RESET, 1, b"recv:ConnectionResetError") in messages
        assert (relay.EOF, 1, b"") not in messages
        assert messages[-1] == (relay.DONE, 0, b"") and writes[2] == b""
    assert client.closed and first.closed and second.closed


def test_generated_source_uses_container_loopback_only_and_has_no_tls_or_public_connector():
    tree = ast.parse(relay.build_container_source(), feature_version=(3, 9))
    imports = {item.name for node in ast.walk(tree) if isinstance(node, ast.Import) for item in node.names}
    assert "ssl" not in imports
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    binds = [node for node in calls if node.func.attr == "bind"]
    assert len(binds) == 1 and ast.literal_eval(binds[0].args[0].elts[0]) == "127.0.0.1"
    assert not any(node.func.attr in ("connect", "create_connection", "getaddrinfo") for node in calls)


def test_generated_container_drains_response_before_closing_a_half_closed_client():
    client = FakeSocket([b""])

    class Listener(FakeSocket):
        def setsockopt(self, *args):
            pass
        def bind(self, address):
            assert address == ("127.0.0.1", 443)
        def listen(self, maximum):
            pass
        def accept(self):
            return client, ("127.0.0.1", 12345)

    listener = Listener()
    writes = {1: bytearray(), 2: bytearray()}
    events = deque(([listener], [client], [0], [], [0], []))
    response = b"response body that must reach a half-closed client"
    host_input = deque((relay.packet(relay.DATA, 1, response) + relay.packet(relay.EOF, 1)
                        + relay.packet(relay.CLOSE, 1, b"tcp_eof"), relay.packet(relay.STOP)))

    def fake_select(readers, writers, exceptional, timeout):
        ready = events.popleft()
        assert all(item in readers for item in ready)
        return ready, list(writers), []

    def write(fd, body):
        writes[fd].extend(body)
        return len(body)

    fake_modules = {
        "socket": SimpleNamespace(socket=lambda *args: listener, AF_INET=2, SOCK_STREAM=1,
            SOL_SOCKET=1, SO_REUSEADDR=2, SHUT_WR=1, SO_LINGER=13),
        "select": SimpleNamespace(select=fake_select),
        "os": SimpleNamespace(set_blocking=lambda *args: None, write=write,
            read=lambda fd, size: host_input.popleft()),
        "time": SimpleNamespace(monotonic=lambda: 0),
    }
    real_import = builtins.__import__
    custom_builtins = dict(vars(builtins))
    custom_builtins["__import__"] = lambda name, *args, **kwargs: fake_modules.get(name) or real_import(name, *args, **kwargs)
    exec(relay.build_container_source(listen_ports=(443,)), {"__builtins__": custom_builtins})
    assert client.sent == response and client.shutdowns == [relay.socket.SHUT_WR]
    assert client.closed and listener.closed and not writes[2]
    assert relay.PacketDecoder().feed(writes[1])[-1] == (relay.DONE, 0, b"")
