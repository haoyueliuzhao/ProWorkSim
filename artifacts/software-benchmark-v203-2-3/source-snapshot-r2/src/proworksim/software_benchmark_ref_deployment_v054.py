"""Fixed-port REF admission and authenticated direct transport; no numerical changes."""
from __future__ import annotations

import fcntl
import http.client
import json
import os
from pathlib import Path
import socket

from .software_benchmark_exact_transport_v054 import HTTPFailure, LoopbackHTTP
from .software_benchmark_supervision_v054 import process_identity
from .storage import json_bytes

ROOT = Path(__file__).resolve().parents[2]


class RefPortReservation:
    def __init__(self):
        path = ROOT / "runs/v054-gpu/locks/ref-port-18054.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = path.open("a+b")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 18054))
        except BaseException:
            self.lock.close()
            raise
        self.receipt = {"port": 18054, "endpoint": "http://127.0.0.1:18054",
                        "exclusive_REF_resident": True, "host_process": process_identity(os.getpid()),
                        "lock": str(path), "slot_claimed_at_reservation": False, "GPU_allocations": 0}

    def close(self):
        self.lock.close()


class AuthenticatedLoopbackHTTP(LoopbackHTTP):
    def __init__(self, endpoint, key_file, **kwargs):
        super().__init__(endpoint, **kwargs)
        descriptor = os.open(key_file, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor) as stream:
            self.key = stream.read(4097).strip()
        if not 32 <= len(self.key) <= 4096 or "\n" in self.key:
            raise ValueError("Invalid private REF key")

    def post(self, path, payload):
        if path not in {"/tokenize", "/v1/chat/completions"}:
            raise ValueError("Unapproved local service operation")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=self.timeout_seconds)
        status, raw = None, None
        try:
            connection.request("POST", path, body=json_bytes(payload), headers={
                "Content-Type": "application/json", "Authorization": "Bearer " + self.key})
            response = connection.getresponse()
            status = response.status
            body = response.read(self.max_response_bytes + 1)
            if len(body) > self.max_response_bytes:
                raise HTTPFailure("Response exceeds complete-response bound", status=status)
            raw = body.decode("utf-8")
            if status != 200:
                raise HTTPFailure("Non-200; no redirect or retry", status=status, raw_body=raw)
            decoded = json.loads(raw)
            if not isinstance(decoded, dict):
                raise ValueError("Expected complete JSON object")
            return decoded
        except HTTPFailure:
            raise
        except Exception as error:
            raise HTTPFailure(str(error), status=status, raw_body=raw) from error
        finally:
            connection.close()
