"""Bounded multiplexed TCP transport through one owned Docker exec.

The host only opens numeric, preapproved public TCP endpoints. Listeners run in
the isolated grading container. TLS bytes remain opaque; neither TCP EOF nor a
client reset is evidence of TLS, HTTP, or test success. Importing performs no IO.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
import select
import socket
import struct
import time

from .software_benchmark_tls_transport_v059 import DockerFrameDecoder

VERSION = "v064-bounded-multiplexed-exec-tcp-r1"
READY, OPEN, DATA, EOF, RESET, CLOSE, STOP, DONE, ERROR = range(1, 10)
HEADER = struct.Struct("!BII")
CHUNK = 16384
BUFFER = 131072
CONTROL_LIMIT = 512


class RelayError(RuntimeError):
    """The bounded transport cannot substantiate a normal completion."""


@dataclass(frozen=True)
class Limits:
    max_connections: int = 512
    max_bytes: int = 64 * 1024**2
    max_active: int = 16
    wall_seconds: float = 1800.0
    idle_seconds: float = 60.0
    connect_seconds: float = 10.0

    def validate(self):
        for name, upper in (("max_connections", 512), ("max_bytes", 64 * 1024**2), ("max_active", 16)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= upper:
                raise RelayError("Invalid bounded transport limit: " + name)
        for name, upper in (("wall_seconds", 1800), ("idle_seconds", 60), ("connect_seconds", 10)):
            value = getattr(self, name)
            if type(value) not in (int, float) or not 0 < value <= upper:
                raise RelayError("Invalid bounded transport limit: " + name)
        return self


def _ports(values):
    values = tuple(values)
    if values not in ((443,), (80, 443)):
        raise RelayError("Only HTTPS, or HTTP and HTTPS, may be exposed")
    return values


def _addresses(values, selected):
    values = tuple(values)
    if not 1 <= len(values) <= 16 or len(set(values)) != len(values):
        raise RelayError("Invalid frozen address set")
    for value in values:
        parsed = ipaddress.IPv4Address(value)
        if str(parsed) != value or not parsed.is_global or parsed.is_multicast or parsed.is_reserved:
            raise RelayError("Only literal public IPv4 targets are allowed")
    if selected not in values:
        raise RelayError("Target is absent from the frozen address set")
    return values


def packet(kind, connection_id=0, payload=b""):
    if type(connection_id) is not int or not 0 <= connection_id <= 512 or not isinstance(payload, bytes):
        raise RelayError("Invalid connection ID or packet payload")
    if kind not in range(READY, ERROR + 1):
        raise RelayError("Unknown transport packet")
    limit = CHUNK if kind == DATA else 2 if kind == OPEN else CONTROL_LIMIT if kind in (RESET, CLOSE, ERROR) else 0
    if len(payload) > limit or (kind == OPEN and len(payload) != 2):
        raise RelayError("Invalid transport packet length")
    if (kind in (READY, STOP, DONE, ERROR)) != (connection_id == 0):
        raise RelayError("Invalid global versus connection packet")
    if kind == DATA and not payload:
        raise RelayError("Empty DATA")
    return HEADER.pack(kind, connection_id, len(payload)) + payload


class PacketDecoder:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        result = []
        while len(self.buffer) >= HEADER.size:
            kind, identity, size = HEADER.unpack(self.buffer[:HEADER.size])
            limit = CHUNK if kind == DATA else 2 if kind == OPEN else CONTROL_LIMIT if kind in (RESET, CLOSE, ERROR) else 0
            if kind not in range(READY, ERROR + 1) or size > limit:
                raise RelayError("Unknown or oversized transport packet")
            end = HEADER.size + size
            if len(self.buffer) < end:
                break
            body = bytes(self.buffer[HEADER.size:end])
            packet(kind, identity, body)
            result.append((kind, identity, body))
            del self.buffer[:end]
        return result

    def finish(self):
        if self.buffer:
            raise RelayError("Truncated transport packet")


@dataclass
class _Connection:
    identity: int
    peer: object
    record: dict
    last_progress: float
    outgoing: bytearray = field(default_factory=bytearray)
    client_eof: bool = False
    remote_eof: bool = False
    write_closed: bool = False


def _authorize(instance_id):
    from .software_benchmark_dispatch_v066 import require_v066_allowed
    return require_v066_allowed("v066.transport", instance_id=instance_id)


def _connect_numeric(address, timeout):
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        connection.settimeout(timeout)
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, CHUNK)
        connection.connect(address)
        return connection
    except BaseException:
        connection.close()
        raise


def relay_many(exec_socket, public_ip, *, instance_id, resolved_ips, stop_event,
               limits=None, listen_ports=(80, 443), on_ready=None,
               authorize=None, connector=None, wait=None, clock=None):
    """Service bounded independent TCP connections until evaluation finishes.

    Call this in a thread, run the official test through a separate exec, then
    set ``stop_event`` and join. The caller must also inspect the relay exec's
    exit code and clean up its owned container. A normal orchestration STOP
    closes unused keepalive sockets with the explicit ``evaluation_stopped``
    outcome. Client resets are recorded separately; upstream errors, bounds,
    framing errors and missing DONE make ``ok`` false. This is NOT an HTTP/TLS
    success check. Dependency seams support CPU-only fake socket controls.
    """
    limits = limits or Limits()
    clock, wait = clock or time.monotonic, wait or select.select
    connector, authorize = connector or _connect_numeric, authorize or _authorize
    channel = getattr(exec_socket, "_sock", exec_socket)
    start = clock()
    connections, closed_ids = {}, set()
    docker, decoder = DockerFrameDecoder(), PacketDecoder()
    outgoing = bytearray()
    stopped_at = None
    done = admitted = False
    highest_id = 0
    result = {"version": VERSION, "status": "rejected", "ok": False, "ready": False,
              "target_hostname": "httpbin.org", "target_ip": public_ip,
              "listen_ports": list(listen_ports), "connection_attempts": 0,
              "bytes_to_upstream": 0, "bytes_from_upstream": 0,
              "application_payload_bytes": 0, "max_active_observed": 0,
              "connections": [], "network_errors": [], "error": None,
              "late_client_bytes_discarded": 0, "stderr_bytes": 0,
              "application_success_not_inferred": True, "cleanup_errors": []}

    def emit(kind, identity=0, body=b""):
        outgoing.extend(packet(kind, identity, body))
        if len(outgoing) > BUFFER + limits.max_active * (CONTROL_LIMIT + HEADER.size):
            raise RelayError("Bounded Docker output queue exhausted")

    def finish_connection(identity, outcome, *, network_error=None, notify=True):
        item = connections.pop(identity, None)
        if item is None:
            return
        item.record.update(outcome=outcome, duration_seconds=max(0.0, clock() - item.record.pop("started_at")))
        item.record["queued_client_bytes_discarded"] = len(item.outgoing)
        if network_error is not None:
            item.record["error"] = network_error
            result["network_errors"].append({"connection_id": identity, "outcome": outcome, "error": network_error})
        try:
            item.peer.close()
        except Exception as error:
            result["cleanup_errors"].append(type(error).__name__)
        closed_ids.add(identity)
        if notify:
            emit(CLOSE, identity, outcome.encode())

    def consume(count, direction, record):
        if count < 0 or result["application_payload_bytes"] + count > limits.max_bytes:
            raise RelayError("Application payload budget exhausted")
        result["application_payload_bytes"] += count
        result[direction] += count
        record[direction] += count

    try:
        limits.validate()
        ports = _ports(listen_ports)
        _addresses(resolved_ips, public_ip)
        authorize(instance_id)
        admitted = True
        result["status"] = "failed"
        channel.setblocking(False)
        while not done:
            now = clock()
            if now - start >= limits.wall_seconds:
                raise RelayError("Transport total deadline exceeded")
            if stop_event.is_set() and stopped_at is None:
                stopped_at = now
                for identity in list(connections):
                    finish_connection(identity, "evaluation_stopped", notify=False)
                emit(STOP)
            if stopped_at is not None and now - stopped_at >= 5:
                raise RelayError("Container did not acknowledge STOP")
            for identity, item in list(connections.items()):
                if now - item.last_progress >= limits.idle_seconds:
                    finish_connection(identity, "upstream_idle_timeout", network_error="Connection idle deadline exceeded")
                    continue
                if item.client_eof and not item.outgoing and not item.write_closed:
                    try:
                        item.peer.shutdown(socket.SHUT_WR)
                        item.write_closed = True
                    except OSError as error:
                        finish_connection(identity, "upstream_shutdown_error", network_error=type(error).__name__)
                        continue
                if item.client_eof and item.remote_eof and not item.outgoing:
                    finish_connection(identity, "tcp_eof")
            readers = []
            if all(len(item.outgoing) <= BUFFER - 2 * CHUNK for item in connections.values()):
                readers.append(channel)
            if stopped_at is None and len(outgoing) <= BUFFER - 2 * CHUNK:
                readers.extend(item.peer for item in connections.values() if not item.remote_eof)
            writers = ([channel] if outgoing else []) + [item.peer for item in connections.values() if item.outgoing]
            delay = min(0.25, max(0.001, limits.wall_seconds - (now - start)))
            ready, writable, _ = wait(readers, writers, [], delay)
            if channel in writable and outgoing:
                try:
                    count = channel.send(outgoing)
                except BlockingIOError:
                    count = None
                if count is not None:
                    if not 0 < count <= len(outgoing):
                        raise RelayError("Docker write made no progress")
                    del outgoing[:count]
            if channel in ready:
                try:
                    payload = channel.recv(CHUNK)
                except BlockingIOError:
                    payload = None
                if payload == b"":
                    docker.finish()
                    decoder.finish()
                    raise RelayError("Docker exec ended without DONE")
                for stream, body in docker.feed(payload or b""):
                    if stream != 1:
                        result["stderr_bytes"] += len(body)
                        raise RelayError("Container relay stderr/system error: " + body[:512].decode("utf-8", "replace"))
                    for kind, identity, data in decoder.feed(body):
                        if kind == READY:
                            if result["ready"] or highest_id:
                                raise RelayError("Duplicate or late READY")
                            result["ready"] = True
                            if on_ready is not None:
                                on_ready()
                        elif kind == OPEN:
                            if not result["ready"] or identity != highest_id + 1:
                                raise RelayError("Unexpected connection OPEN")
                            highest_id = identity
                            port = int.from_bytes(data, "big")
                            if port not in ports:
                                raise RelayError("Unapproved destination port")
                            if identity > limits.max_connections:
                                raise RelayError("Connection budget exhausted")
                            if len(connections) >= limits.max_active:
                                raise RelayError("Concurrent connection bound exceeded")
                            record = {"connection_id": identity, "port": port, "outcome": "pending",
                                      "bytes_to_upstream": 0, "bytes_from_upstream": 0,
                                      "started_at": clock(), "upstream_connected": False}
                            result["connections"].append(record)
                            if stopped_at is not None or stop_event.is_set():
                                record.update(outcome="evaluation_stopped_before_connect", duration_seconds=0.0)
                                record.pop("started_at")
                                closed_ids.add(identity)
                                # STOP closes every container-side client. Never
                                # enqueue a per-connection frame after STOP.
                                continue
                            result["connection_attempts"] += 1
                            peer = None
                            try:
                                remaining = limits.wall_seconds - (clock() - start)
                                if remaining <= 0:
                                    raise TimeoutError("Transport total deadline exceeded before connect")
                                peer = connector((public_ip, port), min(limits.connect_seconds, remaining))
                                if peer.getpeername()[:2] != (public_ip, port):
                                    raise RelayError("Connected endpoint differs from frozen target")
                                peer.setblocking(False)
                                record["upstream_connected"] = True
                                connections[identity] = _Connection(identity, peer, record, clock())
                                result["max_active_observed"] = max(result["max_active_observed"], len(connections))
                            except Exception as error:
                                if peer is not None:
                                    peer.close()
                                detail = type(error).__name__ + ": " + str(error)[:256]
                                record.update(outcome="upstream_connect_error", error=detail,
                                              duration_seconds=max(0.0, clock() - record.pop("started_at")))
                                result["network_errors"].append({"connection_id": identity, "outcome": "upstream_connect_error", "error": detail})
                                closed_ids.add(identity)
                                emit(CLOSE, identity, b"upstream_connect_error")
                        elif kind in (DATA, EOF, RESET):
                            item = connections.get(identity)
                            if item is None:
                                if identity not in closed_ids:
                                    raise RelayError("Packet for unknown connection")
                                if kind == DATA:
                                    result["late_client_bytes_discarded"] += len(data)
                                continue
                            item.last_progress = clock()
                            if kind == RESET:
                                item.record["client_reset_detail"] = data.decode("utf-8", "replace")
                                finish_connection(identity, "client_reset")
                            elif kind == EOF:
                                if item.client_eof:
                                    raise RelayError("Duplicate client EOF")
                                item.client_eof = True
                            else:
                                if item.client_eof:
                                    raise RelayError("Client DATA after EOF")
                                if len(data) > limits.max_bytes - result["application_payload_bytes"]:
                                    raise RelayError("Application payload budget exhausted before upstream write")
                                item.outgoing.extend(data)
                                if len(item.outgoing) > BUFFER:
                                    raise RelayError("Bounded public write queue exhausted")
                        elif kind == DONE:
                            if stopped_at is None or connections:
                                raise RelayError("Premature DONE")
                            done = True
                        elif kind == ERROR:
                            raise RelayError("Container relay error: " + data.decode("utf-8", "replace"))
                        else:
                            raise RelayError("Unexpected container packet")
            # Connections can close while processing the Docker channel above.
            for identity, item in list(connections.items()):
                if item.peer in writable and item.outgoing:
                    try:
                        remaining = limits.max_bytes - result["application_payload_bytes"]
                        if remaining <= 0:
                            raise RelayError("Application payload budget exhausted")
                        count = item.peer.send(memoryview(item.outgoing)[:min(CHUNK, remaining)])
                        if not 0 < count <= min(CHUNK, remaining, len(item.outgoing)):
                            raise RelayError("Upstream write made no progress")
                        consume(count, "bytes_to_upstream", item.record)
                        del item.outgoing[:count]
                        item.last_progress = clock()
                    except BlockingIOError:
                        pass
                    except OSError as error:
                        finish_connection(identity, "upstream_write_error", network_error=type(error).__name__)
                        continue
                if (item.peer in ready and not item.remote_eof and identity in connections
                        and len(outgoing) <= BUFFER - CHUNK - HEADER.size):
                    try:
                        remaining = limits.max_bytes - result["application_payload_bytes"]
                        if remaining <= 0:
                            raise RelayError("Application payload budget exhausted")
                        data = item.peer.recv(min(CHUNK, remaining))
                        item.last_progress = clock()
                        if data:
                            consume(len(data), "bytes_from_upstream", item.record)
                            emit(DATA, identity, data)
                        else:
                            item.remote_eof = True
                            emit(EOF, identity)
                    except BlockingIOError:
                        pass
                    except OSError as error:
                        finish_connection(identity, "upstream_read_error", network_error=type(error).__name__)
            if not result["ready"] and clock() - start > 15:
                raise RelayError("Container READY deadline exceeded")
        docker.finish()
        decoder.finish()
        result.update(ok=not result["network_errors"], status="completed" if not result["network_errors"] else "network_failed")
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:1024]}
        result["status"] = "failed" if admitted else "rejected"
    finally:
        for identity in list(connections):
            finish_connection(identity, "transport_aborted", notify=False)
        for obj in (exec_socket, channel if channel is not exec_socket else None):
            if obj is not None:
                try:
                    obj.close()
                except Exception as error:
                    result["cleanup_errors"].append(type(error).__name__)
        if result["cleanup_errors"]:
            result.update(ok=False, status="failed")
        result["duration_seconds"] = max(0.0, clock() - start)
    return result


def build_container_source(limits=None, listen_ports=(80, 443)):
    limits = (limits or Limits()).validate()
    ports = _ports(listen_ports)
    parameters = {"ports": ports, "max_connections": limits.max_connections,
                  "max_active": limits.max_active, "max_bytes": limits.max_bytes,
                  "wall_seconds": limits.wall_seconds}
    return "CONFIG = " + repr(parameters) + "\n" + CONTAINER_RELAY_SOURCE


# Python 3.9-compatible, executed only inside a separately authorized container.
CONTAINER_RELAY_SOURCE = r'''
import errno, os, select, socket, struct, sys, time
READY, OPEN, DATA, EOF, RESET, CLOSE, STOP, DONE, ERROR = range(1, 10)
HEADER = struct.Struct("!BII")
CHUNK, BUFFER = 16384, 131072
started = time.monotonic()
listeners, clients = {}, {}
retired = set()
outgoing, incoming = bytearray(), bytearray()
next_id, used, stopping = 0, 0, False

def emit(kind, identity=0, body=b""):
    outgoing.extend(HEADER.pack(kind, identity, len(body)) + body)
    if len(outgoing) > BUFFER + CONFIG["max_active"] * (512 + HEADER.size):
        raise RuntimeError("bounded host queue exhausted")

def account(count):
    global used
    used += count
    if used > CONFIG["max_bytes"]:
        raise RuntimeError("container payload budget exhausted")

def retire(identity, reset=None):
    item = clients.pop(identity, None)
    if item is not None:
        item["socket"].close()
        retired.add(identity)
        if reset is not None:
            emit(RESET, identity, reset[:512].encode())

def reset_socket(sock):
    # Preserve reset/error semantics instead of manufacturing a clean TCP EOF.
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))

def client_close_error(identity, operation, error):
    if error.errno not in (errno.ECONNRESET, errno.EPIPE, errno.ENOTCONN, errno.ESHUTDOWN):
        raise error
    retire(identity, operation + ":" + type(error).__name__)

try:
    os.set_blocking(0, False)
    os.set_blocking(1, False)
    for port in CONFIG["ports"]:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listeners[listener] = port
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(CONFIG["max_active"])
        listener.setblocking(False)
    emit(READY)
    while not stopping or outgoing:
        if time.monotonic() - started >= CONFIG["wall_seconds"]:
            raise RuntimeError("container total deadline exceeded")
        for identity, item in list(clients.items()):
            if item["host_eof"] and not item["outgoing"] and not item["write_closed"]:
                try:
                    item["socket"].shutdown(socket.SHUT_WR)
                    item["write_closed"] = True
                except OSError as error:
                    client_close_error(identity, "shutdown", error)
            if identity in clients and item["close_when_drained"] and not item["outgoing"]:
                retire(identity)
        readers = []
        if not stopping:
            if all(len(item["outgoing"]) <= BUFFER - 2 * CHUNK for item in clients.values()):
                readers.append(0)
            if len(outgoing) <= BUFFER - 2 * CHUNK:
                if len(clients) < CONFIG["max_active"]:
                    readers.extend(listeners)
                readers.extend(item["socket"] for item in clients.values() if not item["client_eof"])
        writers = ([1] if outgoing else []) + [item["socket"] for item in clients.values() if item["outgoing"]]
        ready, writable, _ = select.select(readers, writers, [], 0.25)
        if 1 in writable and outgoing:
            try:
                count = os.write(1, outgoing)
                if count <= 0:
                    raise RuntimeError("stdout write stalled")
                del outgoing[:count]
            except BlockingIOError:
                pass
        # Host STOP is processed before accepting or forwarding more clients.
        if 0 in ready:
            body = os.read(0, CHUNK)
            if not body:
                raise RuntimeError("host closed without STOP")
            incoming.extend(body)
            while len(incoming) >= HEADER.size:
                kind, identity, size = HEADER.unpack(incoming[:HEADER.size])
                limit = CHUNK if kind == DATA else 512 if kind in (CLOSE, ERROR) else 0
                if kind not in (DATA, EOF, CLOSE, STOP, ERROR) or size > limit:
                    raise RuntimeError("invalid host packet")
                if len(incoming) < HEADER.size + size:
                    break
                data = bytes(incoming[HEADER.size:HEADER.size + size])
                del incoming[:HEADER.size + size]
                if kind in (STOP, ERROR):
                    if identity != 0:
                        raise RuntimeError("invalid global host packet")
                    if kind == ERROR:
                        raise RuntimeError("host error:" + data.decode("utf-8", "replace"))
                    if stopping:
                        raise RuntimeError("duplicate STOP")
                    stopping = True
                    for listener in listeners:
                        listener.close()
                    listeners.clear()
                    for active in list(clients):
                        retire(active)
                    emit(DONE)
                    continue
                if stopping:
                    raise RuntimeError("host packet after STOP")
                item = clients.get(identity)
                if item is None:
                    if identity not in retired:
                        raise RuntimeError("host packet for unknown connection")
                    continue
                if kind == CLOSE:
                    if data == b"tcp_eof":
                        # A client may half-close its request before reading
                        # the response. Preserve bytes queued before the EOF.
                        item["close_when_drained"] = True
                    else:
                        try:
                            reset_socket(item["socket"])
                        except OSError:
                            pass
                        retire(identity)
                elif kind == EOF:
                    if item["host_eof"]:
                        raise RuntimeError("duplicate host EOF")
                    item["host_eof"] = True
                else:
                    if not data or item["host_eof"]:
                        raise RuntimeError("empty or late host DATA")
                    account(len(data))
                    item["outgoing"].extend(data)
                    if len(item["outgoing"]) > BUFFER:
                        raise RuntimeError("bounded client queue exhausted")
        if stopping:
            continue
        for listener in list(listeners):
            if listener in ready and len(clients) < CONFIG["max_active"]:
                client, address = listener.accept()
                next_id += 1
                if next_id > CONFIG["max_connections"]:
                    client.close()
                    raise RuntimeError("container connection budget exhausted")
                client.setblocking(False)
                clients[next_id] = {"socket": client, "outgoing": bytearray(),
                                    "client_eof": False, "host_eof": False, "write_closed": False,
                                    "close_when_drained": False}
                emit(OPEN, next_id, struct.pack("!H", listeners[listener]))
        for identity, item in list(clients.items()):
            sock = item["socket"]
            if sock in ready and not item["client_eof"] and len(outgoing) <= BUFFER - CHUNK - HEADER.size:
                try:
                    body = sock.recv(CHUNK)
                    if body:
                        account(len(body))
                        emit(DATA, identity, body)
                    else:
                        item["client_eof"] = True
                        emit(EOF, identity)
                except BlockingIOError:
                    pass
                except OSError as error:
                    client_close_error(identity, "recv", error)
                    continue
            if sock in writable and item["outgoing"] and identity in clients:
                try:
                    count = sock.send(item["outgoing"])
                    if count <= 0:
                        raise RuntimeError("client write stalled")
                    del item["outgoing"][:count]
                except BlockingIOError:
                    pass
                except OSError as error:
                    client_close_error(identity, "send", error)
    if incoming:
        raise RuntimeError("truncated host packet")
except BaseException as error:
    try:
        os.set_blocking(2, False)
        os.write(2, (type(error).__name__ + ": " + str(error))[:512].encode())
    except BaseException:
        pass
    sys.exit(1)
finally:
    for item in clients.values():
        item["socket"].close()
    for listener in listeners:
        listener.close()
'''
