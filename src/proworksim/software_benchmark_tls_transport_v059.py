"""Bounded raw TLS-byte transport over one non-TTY Docker exec connection.

No TLS context is created here. The original container client verifies the real
server. Each call serves one client, and a shared budget permits at most two
sequential calls per diagnostic container. Importing this module performs no IO.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import select
import socket
import struct
import threading
import time

from .software_benchmark_tls_policy_v059 import (
    require_tls_diagnostic_allowed,
    validate_connect_target,
    validate_ipv4_targets,
)

VERSION = "v059-bounded-exec-tls-byte-transport-r1"
READY, ACCEPT, DATA, EOF, DONE, ERROR = range(1, 7)
CHUNK = 16384
MAX_DOCKER_FRAME = 65536
MAX_BYTES = 2 * 1024**2
MAX_SESSIONS = 2
TOTAL_SECONDS = 120.0
CONNECT_SECONDS = 10.0
IDLE_SECONDS = 15.0
HEADER = struct.Struct("!BI")


class RelayError(RuntimeError):
    """The byte transport did not complete its declared protocol."""


def packet(kind, payload=b""):
    if kind not in (READY, ACCEPT, DATA, EOF, DONE, ERROR) or not isinstance(payload, bytes):
        raise RelayError("Invalid transport packet")
    limit = CHUNK if kind == DATA else 512 if kind == ERROR else 0
    if len(payload) > limit:
        raise RelayError("Transport packet exceeds its limit")
    return HEADER.pack(kind, len(payload)) + payload


class PacketDecoder:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        result = []
        while len(self.buffer) >= HEADER.size:
            kind, size = HEADER.unpack(self.buffer[:HEADER.size])
            if kind not in (READY, ACCEPT, DATA, EOF, DONE, ERROR):
                raise RelayError("Unknown transport packet kind")
            limit = CHUNK if kind == DATA else 512 if kind == ERROR else 0
            if size > limit:
                raise RelayError("Oversized transport packet")
            end = HEADER.size + size
            if len(self.buffer) < end:
                break
            result.append((kind, bytes(self.buffer[HEADER.size:end])))
            del self.buffer[:end]
        return result

    def finish(self):
        if self.buffer:
            raise RelayError("Truncated transport packet")


class DockerFrameDecoder:
    """Decode Docker's non-TTY 8-byte stdout/stderr envelope incrementally."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        result = []
        while len(self.buffer) >= 8:
            header = self.buffer[:8]
            stream, size = header[0], int.from_bytes(header[4:], "big")
            if stream not in (1, 2, 3) or header[1:4] != b"\0\0\0":
                raise RelayError("Invalid non-TTY Docker stream header")
            if size > MAX_DOCKER_FRAME:
                raise RelayError("Oversized Docker stream frame")
            if len(self.buffer) < 8 + size:
                break
            result.append((stream, bytes(self.buffer[8:8 + size])))
            del self.buffer[:8 + size]
        return result

    def finish(self):
        if self.buffer:
            raise RelayError("Truncated Docker stream frame")


@dataclass
class TransferBudget:
    """Application payload and wall time, not Ethernet/TCP wire-byte accounting."""
    bytes_used: int = field(default=0, init=False)
    sessions: int = field(default=0, init=False)
    started_at: float | None = field(default=None, init=False)
    active: bool = field(default=False, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def begin(self, now):
        with self._lock:
            if self.active or self.sessions >= MAX_SESSIONS:
                raise RelayError("Only two sequential transport sessions are allowed")
            if self.started_at is None:
                self.started_at = now
            if now >= self.started_at + TOTAL_SECONDS or self.bytes_used >= MAX_BYTES:
                raise RelayError("Shared transport budget exhausted")
            self.sessions += 1
            self.active = True
            return self.sessions

    def remaining_seconds(self, now):
        if self.started_at is None:
            return TOTAL_SECONDS
        return max(0.0, self.started_at + TOTAL_SECONDS - now)

    def remaining_bytes(self):
        return max(0, MAX_BYTES - self.bytes_used)

    def consume(self, count):
        with self._lock:
            if type(count) is not int or count < 0 or self.bytes_used + count > MAX_BYTES:
                raise RelayError("Shared application payload budget exhausted")
            self.bytes_used += count

    def end(self):
        with self._lock:
            self.active = False


def _connect_numeric(address, timeout):
    """One connection to a numeric frozen IPv4; no resolver or fallback attempt."""
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        connection.settimeout(timeout)
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, CHUNK)
        connection.connect(address)
        return connection
    except BaseException:
        connection.close()
        raise


def relay_once(exec_socket, public_ip, budget, *, instance_id, resolved_ips,
               on_ready=None, connector=None, wait=None, clock=None):
    """Bridge one owned exec to httpbin.org:443 and return an explicit outcome.

    ``on_ready`` must return promptly (e.g. set a threading.Event); the probe
    itself runs through a separate Docker exec. ``connector``/``wait``/``clock``
    are dependency seams for pure CPU fake-socket controls, not policy overrides.
    The caller owns container cleanup and must inspect the exec exit status.
    """
    clock = clock or time.monotonic
    connector = connector or _connect_numeric
    wait = wait or select.select
    channel = getattr(exec_socket, "_sock", exec_socket)
    peer = None
    began = False
    start = clock()
    result = {"version": VERSION, "ok": False, "status": "failed", "target_hostname": "httpbin.org",
              "target_ip": public_ip, "target_port": 443, "upstream_connected": False,
              "ready": False, "accepted": False, "bytes_to_upstream": 0,
              "bytes_from_upstream": 0, "stderr_bytes": 0, "error": None}
    docker_frames, packets = DockerFrameDecoder(), PacketDecoder()
    last_progress = start
    client_eof = remote_eof = done = False

    def timeout():
        remaining = min(budget.remaining_seconds(clock()), IDLE_SECONDS - (clock() - last_progress))
        if remaining <= 0:
            raise RelayError("Transport total or idle deadline exceeded")
        return remaining

    def send(destination, body, *, public_payload=False):
        nonlocal last_progress
        if public_payload and len(body) > budget.remaining_bytes():
            raise RelayError("Shared application payload budget exhausted")
        view = memoryview(body)
        while view:
            destination.settimeout(timeout())
            count = destination.send(view)
            if not isinstance(count, int) or count <= 0 or count > len(view):
                raise RelayError("Transport write made no valid progress")
            if public_payload:
                budget.consume(count)
                result["bytes_to_upstream"] += count
            last_progress = clock()
            view = view[count:]

    try:
        require_tls_diagnostic_allowed("v059.transport", instance_id)
        addresses = validate_ipv4_targets(resolved_ips)
        validate_connect_target((public_ip, 443), addresses)
        result["session_index"] = budget.begin(start)
        began = True
        while not done:
            readers = [channel] + ([peer] if peer is not None and not remote_eof else [])
            ready, _, _ = wait(readers, [], [], timeout())
            if not ready:
                raise RelayError("Transport idle timeout")
            # The channel is processed first so a queued client close reaches
            # the real server without waiting for a server-first EOF.
            if channel in ready:
                channel.settimeout(timeout())
                incoming = channel.recv(CHUNK)
                if not incoming:
                    docker_frames.finish()
                    packets.finish()
                    raise RelayError("Docker exec ended before a complete DONE record")
                last_progress = clock()
                for stream, payload in docker_frames.feed(incoming):
                    if stream == 3:
                        raise RelayError("Docker exec system error: " + payload[:512].decode("utf-8", "replace"))
                    if stream == 2:
                        result["stderr_bytes"] += len(payload)
                        raise RelayError("Container relay stderr: " + payload[:512].decode("utf-8", "replace"))
                    for kind, body in packets.feed(payload):
                        if kind == READY:
                            if result["ready"] or result["accepted"]:
                                raise RelayError("Duplicate or late READY")
                            result["ready"] = True
                            if on_ready is not None:
                                on_ready()
                        elif kind == ACCEPT:
                            if not result["ready"] or result["accepted"]:
                                raise RelayError("Unexpected ACCEPT")
                            result["accepted"] = True
                            peer = connector((public_ip, 443), min(CONNECT_SECONDS, timeout()))
                            if peer.getpeername()[:2] != (public_ip, 443):
                                raise RelayError("Connected endpoint differs from the frozen target")
                            result["upstream_connected"] = True
                            last_progress = clock()
                        elif kind == DATA:
                            if peer is None or client_eof or not body:
                                raise RelayError("Unexpected client DATA")
                            send(peer, body, public_payload=True)
                        elif kind == EOF:
                            if peer is None or client_eof:
                                raise RelayError("Unexpected client EOF")
                            client_eof = True
                            peer.shutdown(socket.SHUT_WR)
                        elif kind == ERROR:
                            raise RelayError("Container relay error: " + body.decode("utf-8", "replace"))
                        elif kind == DONE:
                            if peer is None or not client_eof or not remote_eof:
                                raise RelayError("Premature DONE")
                            done = True
            if peer in ready and not remote_eof:
                if budget.remaining_bytes() == 0:
                    raise RelayError("Shared application payload budget exhausted")
                peer.settimeout(timeout())
                payload = peer.recv(min(CHUNK, budget.remaining_bytes()))
                last_progress = clock()
                if payload:
                    budget.consume(len(payload))
                    result["bytes_from_upstream"] += len(payload)
                    send(channel, packet(DATA, payload))
                else:
                    remote_eof = True
                    send(channel, packet(EOF))
        docker_frames.finish()
        packets.finish()
        result.update(ok=True, status="completed")
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:1024]}
        if not began:
            result["status"] = "rejected"
    finally:
        cleanup_errors = []
        for obj in (peer, exec_socket, channel if channel is not exec_socket else None):
            if obj is None:
                continue
            try:
                obj.close()
            except Exception as error:
                cleanup_errors.append(type(error).__name__)
        if began:
            budget.end()
        result.update(duration_seconds=max(0.0, clock() - start),
                      aggregate_application_bytes=budget.bytes_used,
                      aggregate_sessions=budget.sessions, cleanup_errors=cleanup_errors)
        if cleanup_errors:
            result.update(ok=False, status="failed")
    return result


# Standalone Python 3.9-compatible source. It is never executed by an import or
# by CPU tests. The parent sends it only to a separately authorized owned exec.
CONTAINER_RELAY_SOURCE = r'''
import os, select, socket, struct, sys, time
READY, ACCEPT, DATA, EOF, DONE, ERROR = range(1, 7)
HEADER = struct.Struct("!BI")
CHUNK, BUFFER, LIMIT = 16384, 65536, 2 * 1024**2
started = last = time.monotonic()
listener = client = None
outgoing = bytearray()
to_client = bytearray()
incoming = bytearray()
used = 0
client_eof = host_eof = write_closed = done = False

def emit(kind, payload=b""):
    outgoing.extend(HEADER.pack(kind, len(payload)) + payload)

def remaining():
    value = min(120 - (time.monotonic() - started), 15 - (time.monotonic() - last))
    if value <= 0:
        raise RuntimeError("relay total or idle timeout")
    return value

def account(count):
    global used
    if count < 0 or used + count > LIMIT:
        raise RuntimeError("relay payload limit")
    used += count

try:
    os.set_blocking(0, False)
    os.set_blocking(1, False)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 443))
    listener.listen(1)
    listener.setblocking(False)
    emit(READY)
    accept_deadline = time.monotonic() + 10
    while not done or outgoing:
        if client is None and time.monotonic() >= accept_deadline:
            raise RuntimeError("relay accept timeout")
        if client is not None and host_eof and not to_client and not write_closed:
            client.shutdown(socket.SHUT_WR)
            write_closed = True
        if client is not None and client_eof and host_eof and not to_client and not done:
            emit(DONE)
            done = True
        readers = []
        if not done:
            if client is None:
                readers.append(listener)
            elif not client_eof and len(outgoing) < BUFFER - CHUNK - HEADER.size:
                readers.append(client)
            if len(to_client) < BUFFER - CHUNK - HEADER.size:
                readers.append(0)
        writers = ([1] if outgoing else []) + ([client] if to_client else [])
        delay = remaining()
        if client is None:
            delay = min(delay, max(0.0, accept_deadline - time.monotonic()))
        ready, writable, _ = select.select(readers, writers, [], delay)
        if not ready and not writable:
            raise RuntimeError("relay idle timeout")
        if listener is not None and listener in ready:
            client, _ = listener.accept()
            client.setblocking(False)
            listener.close()
            listener = None
            emit(ACCEPT)
            last = time.monotonic()
        if client is not None and client in ready:
            payload = client.recv(CHUNK)
            last = time.monotonic()
            if payload:
                account(len(payload))
                emit(DATA, payload)
            else:
                client_eof = True
                emit(EOF)
        if 0 in ready:
            payload = os.read(0, CHUNK)
            if not payload:
                raise RuntimeError("host transport closed before DONE")
            incoming.extend(payload)
            last = time.monotonic()
            while len(incoming) >= HEADER.size:
                kind, size = HEADER.unpack(incoming[:HEADER.size])
                if kind not in (DATA, EOF, ERROR) or size > (CHUNK if kind == DATA else 512 if kind == ERROR else 0):
                    raise RuntimeError("invalid host frame")
                if len(incoming) < HEADER.size + size:
                    break
                body = bytes(incoming[HEADER.size:HEADER.size + size])
                del incoming[:HEADER.size + size]
                if kind == DATA:
                    if host_eof or not body:
                        raise RuntimeError("late or empty host DATA")
                    account(len(body))
                    to_client.extend(body)
                elif kind == EOF:
                    if host_eof:
                        raise RuntimeError("duplicate host EOF")
                    host_eof = True
                else:
                    raise RuntimeError("host error: " + body.decode("utf-8", "replace"))
        if client is not None and client in writable:
            count = client.send(to_client)
            if count <= 0:
                raise RuntimeError("client write stalled")
            del to_client[:count]
            last = time.monotonic()
        if 1 in writable:
            count = os.write(1, outgoing)
            if count <= 0:
                raise RuntimeError("stdout write stalled")
            del outgoing[:count]
            last = time.monotonic()
    if incoming:
        raise RuntimeError("truncated host frame")
except BaseException as error:
    # Docker stderr is diagnostic only; never inserted into the TLS byte stream.
    try:
        os.set_blocking(2, False)
        os.write(2, (type(error).__name__ + ": " + str(error))[:512].encode())
    except BaseException:
        pass
    sys.exit(1)
finally:
    if client is not None:
        client.close()
    if listener is not None:
        listener.close()
'''
