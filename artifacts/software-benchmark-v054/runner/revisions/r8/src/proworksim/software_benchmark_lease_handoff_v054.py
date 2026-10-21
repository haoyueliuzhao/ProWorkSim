"""Keep the same flock descriptions alive in the independently supervised model service."""
from __future__ import annotations

import array
import ctypes
import json
import os
from pathlib import Path
import socket
import struct
import threading
import signal
import time
import re
import platform

from .software_benchmark_supervision_v054 import process_identity


def _pidfd_open(pid):
    if hasattr(os, "pidfd_open"):
        return os.pidfd_open(pid)
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("This fallback supports the admitted Linux x86_64 server only")
    libc = ctypes.CDLL(None, use_errno=True)
    descriptor = libc.syscall(434, int(pid), 0)
    if descriptor < 0:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number))
    return descriptor


def _pidfd_kill(descriptor):
    if hasattr(signal, "pidfd_send_signal"):
        signal.pidfd_send_signal(descriptor, signal.SIGKILL)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.syscall(424, descriptor, int(signal.SIGKILL), 0, 0) < 0:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number))


class LeaseHandoff:
    def __init__(self, path, leases):
        self.path = Path(path)
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(path))
        os.chmod(path, 0o600)
        self.listener.listen(1)
        self.listener.settimeout(120)
        self.descriptors = [handle.fileno() for lease in leases
                            for handle in getattr(lease, "handles", [getattr(lease, "lock", None)])
                            if handle is not None]
        self.owner = process_identity(os.getpid())
        self.error = None
        self.sent = False
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        try:
            connection, _ = self.listener.accept()
            with connection:
                _, uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != os.getuid() or connection.recv(16) != b"v054-lease-v1":
                    raise ValueError("Unexpected model lease receiver")
                payload = json.dumps({"owner": self.owner, "descriptor_count": len(self.descriptors)}).encode() + b"\n"
                sent = connection.sendmsg([payload], [(socket.SOL_SOCKET, socket.SCM_RIGHTS,
                                                       array.array("i", self.descriptors))])
                if sent != len(payload):
                    connection.sendall(payload[sent:])
                self.sent = True
        except BaseException as error:
            self.error = error

    def close(self):
        self.listener.close()
        self.path.unlink(missing_ok=True)


def receive_leases(path):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(30)
        connection.connect(str(path))
        peer, uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != os.getuid():
            raise ValueError("Lease host belongs to another user")
        connection.sendall(b"v054-lease-v1")
        raw, ancillary, flags, _ = connection.recvmsg(4096, socket.CMSG_SPACE(16 * 4))
        while not raw.endswith(b"\n") and len(raw) < 4096:
            block = connection.recv(4096 - len(raw))
            if not block:
                break
            raw += block
    descriptors = []
    for level, kind, body in ancillary:
        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
            values = array.array("i")
            values.frombytes(body[:len(body) - len(body) % values.itemsize])
            descriptors.extend(values)
    try:
        receipt = json.loads(raw)
        if (flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) or len(descriptors) < 2
                or len(descriptors) != receipt["descriptor_count"] or receipt["owner"]["pid"] != peer
                or process_identity(receipt["owner"]["pid"]) != receipt["owner"]):
            raise ValueError("Incomplete or stale physical/global deployment lease transfer")
        for descriptor in descriptors:
            os.set_inheritable(descriptor, False)
        return receipt, descriptors
    except BaseException:
        for descriptor in descriptors:
            os.close(descriptor)
        raise


def drain_own_model_cgroup():
    """Retain deployment leases until every other process in this exact model unit exits."""
    entry = next(line[3:] for line in Path("/proc/self/cgroup").read_text().splitlines()
                 if line.startswith("0::"))
    unit = entry.rsplit("/", 1)[-1]
    if (not re.fullmatch(r"proworksim-v054-episode-[a-f0-9]{32}-model\.service", unit)
            or not entry.startswith("/user.slice/") or ".." in entry.split("/")):
        raise ValueError("Refuse to drain anything except this owned model service cgroup")
    root = Path("/sys/fs/cgroup" + entry)
    stopped = set()
    while True:
        members = set()
        for path in root.rglob("cgroup.procs"):
            members.update(int(pid) for pid in path.read_text().split())
        members.discard(os.getpid())
        if not members:
            return {"model_cgroup": entry, "other_processes_remaining": 0,
                    "observed_descendant_pids": sorted(stopped), "leases_released_after_quiescence": True}
        for pid in members:
            try:
                membership = Path(f"/proc/{pid}/cgroup").read_text()
                if not any(line == "0::" + entry or line.startswith("0::" + entry + "/")
                           for line in membership.splitlines()):
                    continue
                descriptor = _pidfd_open(pid)
                try:
                    # Recheck after pidfd acquisition to avoid signalling a recycled foreign PID.
                    membership = Path(f"/proc/{pid}/cgroup").read_text()
                    if any(line == "0::" + entry or line.startswith("0::" + entry + "/")
                           for line in membership.splitlines()):
                        _pidfd_kill(descriptor)
                        stopped.add(pid)
                finally:
                    os.close(descriptor)
            except ProcessLookupError:
                pass
            except FileNotFoundError:
                pass
        time.sleep(.02)
