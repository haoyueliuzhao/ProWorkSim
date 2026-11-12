"""Private-container FIFO to Docker-exec to authenticated host loopback transport.

No listener, model key, proxy or external network is added to the controller.
The host serves one admitted request at a time and never retries it.
"""
from __future__ import annotations

import json
import http.client
import os
from pathlib import Path
import select
import stat
import socket
import threading
import time

from .software_benchmark_exact_transport_v054 import HTTPFailure, LoopbackHTTP
from .software_benchmark_ref_deployment_v054 import AuthenticatedLoopbackHTTP
from .storage import json_bytes

VERSION = "v062-controller-model-fifo-r1"
CONTROL = Path("/pws/control")
MAX_FRAME = 32 * 1024 * 1024
MAX_REQUESTS = 1100
PATHS = frozenset(("/tokenize", "/v1/chat/completions"))
PORTS = (18171, 18172)


class CancellableLoopbackHTTP(AuthenticatedLoopbackHTTP):
    """Abort only this episode's connection when its controller is gone."""
    def __init__(self, endpoint, key_file):
        super().__init__(endpoint, key_file)
        if self.port not in PORTS:
            raise ValueError("Only the two new owned capability resident ports are accepted")
        self.lock = threading.Lock()
        self.active = None
        self.response = None
        self.cancelled = threading.Event()

    def abort(self):
        self.cancelled.set()
        with self.lock:
            connection, response = self.active, self.response
        sockets = []
        if connection is not None and connection.sock is not None:
            sockets.append(connection.sock)
        if response is not None:
            raw = getattr(getattr(response, "fp", None), "raw", None)
            value = getattr(raw, "_sock", None)
            if value is not None:
                sockets.append(value)
        for value in sockets:
            try:
                value.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if connection is not None:
            connection.close()

    def post(self, path, payload):
        if path not in PATHS:
            raise ValueError("Unapproved local model operation")
        if self.cancelled.is_set():
            raise HTTPFailure("Episode model transport was cancelled; no retry")
        # A missing local listener fails before dispatch. After connecting, the
        # original 1800-second complete-response limit remains unchanged.
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        status, raw = None, None
        with self.lock:
            if self.cancelled.is_set():
                raise HTTPFailure("Episode model transport was cancelled; no retry")
            self.active = connection
        try:
            connection.connect()
            connection.auto_open = False  # Cancellation must never reconnect and replay a POST.
            connection.sock.settimeout(self.timeout_seconds)
            if self.cancelled.is_set():
                self.abort()
                raise HTTPFailure("Episode ended before model dispatch; no retry")
            connection.request("POST", path, body=json_bytes(payload), headers={
                "Content-Type": "application/json", "Authorization": "Bearer " + self.key})
            response = connection.getresponse()
            with self.lock:
                self.response = response
            if self.cancelled.is_set():
                self.abort()
                raise HTTPFailure("Episode ended while awaiting its model response")
            status = response.status
            body = response.read(self.max_response_bytes + 1)
            if len(body) > self.max_response_bytes:
                raise HTTPFailure("Response exceeds complete-response bound", status=status)
            raw = body.decode("utf-8")
            if status != 200:
                raise HTTPFailure("Non-200; no redirect or retry", status=status, raw_body=raw)
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("Expected complete JSON object")
            return result
        except HTTPFailure:
            raise
        except Exception as error:
            raise HTTPFailure(str(error), status=status, raw_body=raw) from error
        finally:
            connection.close()
            with self.lock:
                self.active = None
                self.response = None


class LineReader:
    def __init__(self, descriptor):
        self.descriptor, self.pending = descriptor, bytearray()

    def read(self, deadline):
        while True:
            split = self.pending.find(b"\n")
            if split >= 0:
                raw = bytes(self.pending[:split])
                del self.pending[:split + 1]
                return decode_frame(raw)
            if len(self.pending) > MAX_FRAME:
                raise ValueError("Model FIFO frame exceeds the request/response bound")
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.descriptor], [], [], remaining)[0]:
                raise TimeoutError("Model FIFO response exceeded the original request deadline")
            try:
                chunk = os.read(self.descriptor, min(65536, MAX_FRAME + 1 - len(self.pending)))
            except BlockingIOError:
                continue
            if not chunk:
                raise EOFError("Model FIFO bridge closed before a complete response")
            self.pending.extend(chunk)


def decode_frame(raw):
    if len(raw) > MAX_FRAME:
        raise ValueError("Model FIFO frame exceeds its bound")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("Model bridge requires one complete JSON object")
    return result


def encoded_frame(value):
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_FRAME:
        raise ValueError("Model FIFO frame exceeds its bound")
    return raw + b"\n"


def write_frame(descriptor, value, deadline):
    pending = memoryview(encoded_frame(value))
    while pending:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([], [descriptor], [], remaining)[1]:
            raise TimeoutError("Model FIFO write deadline exceeded")
        try:
            count = os.write(descriptor, pending)
        except BlockingIOError:
            continue
        if count <= 0:
            raise EOFError("Model FIFO write made no progress")
        pending = pending[count:]


def open_fifo(path, *, create=False):
    path = Path(path)
    if create:
        try:
            os.mkfifo(path, 0o600)
        except FileExistsError:
            pass
    before = path.lstat()
    if not stat.S_ISFIFO(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o600:
        raise ValueError("Model transport requires a private mode-0600 FIFO")
    descriptor = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW)
    after = os.fstat(descriptor)
    if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
        os.close(descriptor)
        raise ValueError("Model FIFO changed while opening")
    return descriptor


class FifoModelTransport(LoopbackHTTP):
    """Adapter-compatible transport; the port remains the admitted service identity."""
    def __init__(self, endpoint, *, control=CONTROL, timeout_seconds=1800):
        super().__init__(endpoint, timeout_seconds=timeout_seconds)
        if self.port not in PORTS or timeout_seconds != 1800:
            raise ValueError("Keep the fixed model endpoint range and request timeout")
        self.request_fd = open_fifo(Path(control) / "model-request.fifo")
        self.response_fd = open_fifo(Path(control) / "model-response.fifo")
        self.reader = LineReader(self.response_fd)
        self.sequence = 0

    def post(self, path, payload):
        if path not in PATHS or not isinstance(payload, dict):
            raise ValueError("Only exact counting and generation use this model transport")
        self.sequence += 1
        if self.sequence > MAX_REQUESTS:
            raise HTTPFailure("Model FIFO request bound exceeded")
        deadline = time.monotonic() + self.timeout_seconds + 30
        try:
            write_frame(self.request_fd, {"id": self.sequence, "path": path, "payload": payload}, deadline)
            result = self.reader.read(deadline)
            if result.get("id") != self.sequence:
                raise ValueError("Model bridge response belongs to a different request")
            if result.get("ok") is True and isinstance(result.get("body"), dict):
                return result["body"]
            if result.get("ok") is False and isinstance(result.get("http_failure"), dict):
                fault = result["http_failure"]
                raise HTTPFailure(fault.get("reason", "Host model request failed"),
                    status=fault.get("http_status"), raw_body=fault.get("raw_response_body"))
            raise ValueError("Model bridge returned an invalid success/failure envelope")
        except HTTPFailure:
            raise
        except Exception as error:
            raise HTTPFailure("Model FIFO transport: " + str(error)) from error

    def close(self):
        for field in ("request_fd", "response_fd"):
            value = getattr(self, field, None)
            if value is not None:
                os.close(value)
                setattr(self, field, None)


def container_bridge(control=CONTROL):
    """Run in a separate trusted controller exec; stdin/stdout belong only here."""
    control = Path(control)
    if control.resolve() != CONTROL or not control.is_dir():
        raise ValueError("Use the private controller control directory")
    requests = open_fifo(control / "model-request.fifo", create=True)
    responses = open_fifo(control / "model-response.fifo", create=True)
    os.set_blocking(0, False)
    os.set_blocking(1, False)
    request_reader, host_reader = LineReader(requests), LineReader(0)
    pending = None
    try:
        write_frame(1, {"type": "model_bridge_ready", "version": VERSION}, time.monotonic() + 15)
        while True:
            buffered = ([0] if b"\n" in host_reader.pending else []) + ([requests] if b"\n" in request_reader.pending else [])
            readable = buffered or select.select([0, requests], [], [], 1)[0]
            if 0 in readable:
                value = host_reader.read(time.monotonic() + 15)
                if value == {"op": "stop"}:
                    break
                if pending is None or value.get("id") != pending:
                    raise ValueError("Host model response is not bound to the pending request")
                write_frame(responses, value, time.monotonic() + 30)
                pending = None
            if requests in readable:
                value = request_reader.read(time.monotonic() + 15)
                if pending is not None:
                    raise ValueError("Only one model request may be in flight")
                pending = value.get("id")
                write_frame(1, value, time.monotonic() + 30)
    finally:
        os.close(requests)
        os.close(responses)


def model_response(request, transport, expected_id):
    """Pure dispatch envelope logic; dependency seam used by CPU controls."""
    if (set(request) != {"id", "path", "payload"} or type(request["id"]) is not int
            or request["id"] != expected_id or request["path"] not in PATHS
            or not isinstance(request["payload"], dict)):
        raise ValueError("Model request differs from the fixed endpoint/sequence/schema")
    try:
        return {"id": expected_id, "ok": True, "body": transport.post(request["path"], request["payload"])}
    except HTTPFailure as error:
        return {"id": expected_id, "ok": False, "http_failure": error.evidence}


def serve_model_channel(channel, *, endpoint, key_file, deadline, stop_event, slot_id,
                        on_ready=None, transport=None):
    """Host thread: only this ordinary process sees the resident authentication key.

    channel is the DockerStdioChannel supplied by the owned actor runtime. It
    separates Docker stderr from stdout and enforces its own bounded line size.
    """
    from .software_benchmark_dispatch_v062 import require_v062_allowed
    require_v062_allowed("v062.model.bridge", slot_id=slot_id)
    client = transport or CancellableLoopbackHTTP(endpoint, key_file)
    if client.port not in PORTS or client.timeout_seconds != 1800:
        raise ValueError("The host model route must retain the original admitted port and timeout")
    result = {"version": VERSION, "ready": False, "requests": 0, "failed_requests": 0,
              "model_key_sent_to_container": False, "host_listener": False, "automatic_retries": 0}
    try:
        ready = decode_frame(channel.readline(deadline=min(deadline, time.monotonic() + 20)))
        if ready != {"type": "model_bridge_ready", "version": VERSION}:
            raise ValueError("Controller model FIFO bridge did not initialize")
        result["ready"] = True
        if on_ready is not None:
            on_ready()
        while not stop_event.is_set():
            if time.monotonic() >= deadline:
                raise TimeoutError("Model bridge exceeded episode hard deadline")
            try:
                raw = channel.readline(deadline=min(deadline, time.monotonic() + 1))
            except TimeoutError:
                continue
            except ConnectionResetError as error:
                # This branch is reached only while awaiting the next request,
                # never during the actual model POST or response write. PID1
                # exit may reset its owned exec socket; the controller result
                # must still prove normal completion before the episode counts.
                stdout = getattr(channel, "buffer", None)
                frames = getattr(getattr(channel, "decoder", None), "buffer", None)
                if (not isinstance(stdout, (bytes, bytearray)) or stdout
                        or not isinstance(frames, (bytes, bytearray)) or frames):
                    raise
                result.update(status="channel_closed", requires_controller_exit_classification=True,
                              idle_exec_reset={"type": type(error).__name__, "message": str(error),
                                               "buffered_stdout_bytes": 0, "buffered_frame_bytes": 0})
                return result
            if not raw:
                result.update(status="channel_closed", requires_controller_exit_classification=True)
                return result
            result["requests"] += 1
            if result["requests"] > MAX_REQUESTS:
                raise ValueError("Model bridge request bound exceeded")
            response = model_response(decode_frame(raw), client, result["requests"])
            result["failed_requests"] += response["ok"] is False
            channel.write(encoded_frame(response))
        channel.write(encoded_frame({"op": "stop"}))
        result["status"] = "stopped_after_controller"
    except Exception as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)})
    return result
