"""Two bounded heavy host phases and ref-only parked snapshots for future runs.

This module never changes a cgroup, sends a signal, or creates a subprocess.
The new deployment must bind it around both initial snapshot construction and
the entire stopped-controller export/verification/candidate phase.
"""
from __future__ import annotations

from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import threading


VERSION = "v132-bounded-host-snapshot-memory-r1"
GIB = 1024**3
MANAGER_MEMORY_HIGH_BYTES = 30 * GIB
MANAGER_MEMORY_MAX_BYTES = 32 * GIB


@dataclass(frozen=True)
class FrozenSnapshot:
    path: str
    sha256: str
    bytes: int
    file_policy_json: str

    @property
    def reference(self):
        return {"path": self.path, "sha256": self.sha256, "bytes": self.bytes}

    @property
    def file_policy(self):
        return json.loads(self.file_policy_json)


def park_snapshot(bundle, reference):
    """Retain the producer's already sealed reference and small policy only.

    Call only with the exact (bundle, reference) returned by owned snapshot().
    The caller must drop its full bundle variable afterwards; this function
    does not mutate it. Full bytes and digest are checked once at later load.
    """
    if (set(reference) != {"path", "sha256", "bytes"}
            or not isinstance(reference["path"], str)
            or not isinstance(reference["sha256"], str)
            or len(reference["sha256"]) != 64
            or type(reference["bytes"]) is not int or reference["bytes"] < 0
            or not isinstance(bundle.get("file_policy"), dict)):
        raise ValueError("An exact owned snapshot reference and policy are required")
    return FrozenSnapshot(reference["path"], reference["sha256"], reference["bytes"],
                          json.dumps(bundle["file_policy"], sort_keys=True, separators=(",", ":")))


class HostMemoryGate:
    """FIFO heavy phases, including cleanup after cancellation; at most two."""

    def __init__(self, maximum=2):
        if type(maximum) is not int or not 1 <= maximum <= 2:
            raise ValueError("The bounded host permits at most two heavy phases")
        self.maximum = maximum
        self.condition = threading.Condition(threading.RLock())
        self.pending, self.active = [], {}
        self.local = threading.local()
        self.executor = None
        self.closed = False

    def run_heavy(self, owner, label, operation):
        """Use only two allocation-heavy threads, not 48 separate arenas.

        Existing owned work is never cancelled by admission drain. The caller
        waits on its result; it retains only refs/small metadata while queued.
        The callback must return receipts and not capture preloaded trees.
        """
        if getattr(self.local, "owner", None) == owner:
            return operation()
        if getattr(self.local, "owner", None) is not None:
            raise ValueError("Nested heavy work cannot change its owner")
        with self.condition:
            if self.closed:
                raise RuntimeError("The heavy host executor is already closed")
            if self.executor is None:
                self.executor = ThreadPoolExecutor(max_workers=self.maximum,
                    thread_name_prefix="v132-host-heavy")
            future = self.executor.submit(self._invoke, owner, label, operation)
        return future.result()

    def _invoke(self, owner, label, operation):
        with self.phase(owner, label):
            return operation()

    def close(self):
        """Call after generation/scoring owners finish; never cancel futures."""
        with self.condition:
            self.closed = True
            executor = self.executor
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=False)

    @contextmanager
    def phase(self, owner, label):
        if not isinstance(owner, str) or not owner or not isinstance(label, str) or not label:
            raise ValueError("A heavy phase needs an exact owner and label")
        existing = getattr(self.local, "owner", None)
        if existing is not None:
            if existing != owner:
                raise ValueError("Nested heavy work cannot change its owner")
            yield self
            return
        ticket = object()
        with self.condition:
            if owner in self.active or any(item[1] == owner for item in self.pending):
                raise ValueError("One heavy phase per owned episode")
            self.pending.append((ticket, owner, label))
            while self.pending[0][0] is not ticket or len(self.active) >= self.maximum:
                self.condition.wait(.2)
            self.pending.pop(0)
            self.active[owner] = label
            self.local.owner = owner
        try:
            yield self
        finally:
            with self.condition:
                self.active.pop(owner)
                del self.local.owner
                self.condition.notify_all()

    def load(self, snapshot):
        if getattr(self.local, "owner", None) is None:
            raise RuntimeError("Loading a complete snapshot requires the shared heavy phase")
        if not isinstance(snapshot, FrozenSnapshot):
            raise TypeError("Load only an exact parked snapshot")
        path = Path(snapshot.path)
        digest, size = hashlib.sha256(), 0
        # The same open file is hashed and parsed, avoiding a path replacement
        # between independent opens. The exact owned snapshot is immutable.
        with path.open("rb") as source:
            initial = os.fstat(source.fileno())
            for chunk in iter(lambda: source.read(1024**2), b""):
                digest.update(chunk)
                size += len(chunk)
            if size != snapshot.bytes or digest.hexdigest() != snapshot.sha256:
                raise ValueError("Parked snapshot bytes changed")
            source.seek(0)
            value = json.load(source)
            final = os.fstat(source.fileno())
        if (initial.st_size, initial.st_mtime_ns, initial.st_ctime_ns) != (
                final.st_size, final.st_mtime_ns, final.st_ctime_ns):
            raise ValueError("Owned snapshot changed while being validated")
        if value.get("file_policy") != snapshot.file_policy:
            raise ValueError("Parked snapshot policy changed")
        return value

    def capture_initial(self, owner, producer, *args, **kwargs):
        """Call the existing snapshot producer but return no full-tree object.

        New episode binding: parked, baseline_ref = gate.capture_initial(
            slot_id, snapshot, pair, output, name='baseline-snapshot', ...).
        Controller inputs read parked.file_policy. The terminal phase uses
        within_snapshots/phase+load, so a model-waiting thread holds only refs.
        """
        def capture():
            value, reference = producer(*args, **kwargs)
            try:
                return park_snapshot(value, reference), reference
            finally:
                del value
        return self.run_heavy(owner, "initial_snapshot", capture)

    def within_snapshots(self, owner, snapshots, operation):
        """Load only after admission; operation returns receipts, not full trees.

        operation must not retain its input dictionaries. The loader keeps no
        snapshot cache or references after the callback returns or raises.
        """
        def execute():
            values = [self.load(snapshot) for snapshot in snapshots]
            try:
                return operation(*values)
            finally:
                values.clear()
        return self.run_heavy(owner, "snapshot_verification_and_export", execute)

    def snapshot(self):
        with self.condition:
            return {"version": VERSION, "maximum": self.maximum,
                    "active": dict(self.active),
                    "waiting": [{"owner": item[1], "phase": item[2]} for item in self.pending]}


def manager_pressure(cgroup, *, minimum_free_bytes=2 * GIB, maximum_full_avg10=20.0):
    """Read only the new frozen manager limits; pressure pauses new admission.

    Heavy cleanup does not wait on this probe: it must complete to free memory.
    No shared-host or aggregate-parent limits are changed here.
    """
    root = Path(cgroup)
    current, high, maximum = (int((root / name).read_text())
                              for name in ("memory.current", "memory.high", "memory.max"))
    if (high, maximum) != (MANAGER_MEMORY_HIGH_BYTES, MANAGER_MEMORY_MAX_BYTES):
        raise PermissionError("Manager limits differ from the new frozen 30/32-GiB scope")
    full = next(line for line in (root / "memory.pressure").read_text().splitlines()
                if line.startswith("full "))
    fields = dict(item.split("=", 1) for item in full.split()[1:])
    avg10 = float(fields["avg10"])
    return {"passed": current + minimum_free_bytes <= high and avg10 <= maximum_full_avg10,
            "current_bytes": current, "high_bytes": high, "maximum_bytes": maximum,
            "full_avg10": avg10, "minimum_free_bytes": minimum_free_bytes,
            "maximum_full_avg10": maximum_full_avg10, "existing_work_cancelled": False}
