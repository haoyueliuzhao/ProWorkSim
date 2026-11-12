"""Ordinary-user pressure observation and queue-owned API cancellation requests.

This module never signals a PID, calls Docker, writes cgroups, or changes host
configuration.  The owning queue supplies an opaque per-episode ownership token
and a nonblocking callback that sets only that episode's local stop event.  The
normal episode lifecycle retains the original candidate/usage and cleans both
its actor and controller.  Cancelled episodes are never automatically replayed.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path, PurePosixPath
import re
import threading
import time

VERSION = "v076-owned-api-physical-memory-pressure-r1"
GIB = 1024**3
PAUSE_BYTES = 256 * GIB
RESUME_BYTES = 320 * GIB
EMERGENCY_BYTES = 192 * GIB
CRITICAL_BYTES = 128 * GIB
PARENT_MAX_BYTES = 224 * GIB
PARENT_PAUSE_BYTES = 64 * GIB
PARENT_RESUME_BYTES = 96 * GIB
PARENT_EMERGENCY_BYTES = 16 * GIB
PARENT_CRITICAL_BYTES = 8 * GIB
POLL_SECONDS = 1.0
MAX_AGE_SECONDS = 5.0
ABORT_INTERVAL_SECONDS = 1.0
MAX_CRITICAL_ABORTS_PER_TICK = 4
_API_SLOT = re.compile(r"v064:[^:]+:DEEPSEEK_(?:REF|PROJECT)_B5000K:[0-9]+")
_HEX = re.compile(r"[0-9a-f]{64}")


def host_available_memory(path=Path("/proc/meminfo")):
    values = [line.split() for line in Path(path).read_text().splitlines()
              if line.startswith("MemAvailable:")]
    if (len(values) != 1 or len(values[0]) != 3 or values[0][2] != "kB"
            or not values[0][1].isdigit()):
        raise ValueError("A unique nonnegative MemAvailable value is required")
    return int(values[0][1]) * 1024


def process_start_ticks(pid, proc_root=Path("/proc")):
    if type(pid) is not int or pid <= 0:
        raise ValueError("A container PID must be positive")
    raw = (Path(proc_root) / str(pid) / "stat").read_text()
    fields = raw[raw.rfind(")") + 2:].split()
    if len(fields) < 20 or not fields[19].isdigit():
        raise ValueError("Cannot bind the container process start identity")
    return int(fields[19])


@dataclass(frozen=True)
class OwnedContainer:
    slot_id: str
    role: str
    container_id: str
    claim_sha256: str
    pid: int
    start_ticks: int
    cgroup_path: str


def capture_owned_container(claim_ref, attrs, *, validate_claim, proc_root=Path("/proc")):
    """Capture telemetry identity after the caller's exact resource-scope check.

    ``attrs`` is a Docker inspect result already available to the owned provider;
    no Docker API is accessed here.  The claim validator must be the active
    revision's validator, not a permissive predicate.
    """
    claim = validate_claim(claim_ref)
    spec, labels = claim["spec"], attrs.get("Config", {}).get("Labels", {})
    slot, role, container_id = spec.get("slot_id"), spec.get("role"), attrs.get("Id")
    if (not isinstance(slot, str) or _API_SLOT.fullmatch(slot) is None
            or role not in {"actor", "controller"}
            or not isinstance(container_id, str) or _HEX.fullmatch(container_id) is None
            or not isinstance(claim_ref.get("sha256"), str) or _HEX.fullmatch(claim_ref["sha256"]) is None
            or attrs.get("Name", "").removeprefix("/") != claim.get("docker_name")
            or attrs.get("Image") != spec.get("image_id")
            or labels.get("proworksim.resource") != claim.get("key")
            or labels.get("proworksim.claim") != claim_ref["sha256"]
            or labels.get("proworksim.owner") != "v066-owned-private-docker-actor-pair-r1"
            or attrs.get("State", {}).get("Running") is not True):
        raise ValueError("Only an exact running owned API actor/controller may be observed")
    pid = attrs["State"].get("Pid")
    start = process_start_ticks(pid, proc_root)
    lines = (Path(proc_root) / str(pid) / "cgroup").read_text().splitlines()
    paths = [line[3:] for line in lines if line.startswith("0::")]
    if len(paths) != 1:
        raise ValueError("One exact unified container cgroup is required")
    group = PurePosixPath(paths[0])
    if (not group.is_absolute() or ".." in group.parts
            or group.name not in {container_id, "docker-" + container_id + ".scope"}
            or process_start_ticks(pid, proc_root) != start):
        raise ValueError("Container PID/cgroup identity changed during observation")
    return OwnedContainer(slot, role, container_id, claim_ref["sha256"], pid, start, str(group))


def owned_memory_current(container, *, proc_root=Path("/proc"), cgroup_root=Path("/sys/fs/cgroup")):
    """Read only the registered container cgroup; reject stale/reused PIDs."""
    if not isinstance(container, OwnedContainer):
        raise ValueError("An ownership-bound container observation is required")
    group = PurePosixPath(container.cgroup_path)
    if (group.name not in {container.container_id, "docker-" + container.container_id + ".scope"}
            or not group.is_absolute() or ".." in group.parts
            or _HEX.fullmatch(container.container_id) is None
            or process_start_ticks(container.pid, proc_root) != container.start_ticks):
        raise ValueError("The registered container identity is no longer current")
    raw_group = (Path(proc_root) / str(container.pid) / "cgroup").read_text().splitlines()
    if [line[3:] for line in raw_group if line.startswith("0::")] != [str(group)]:
        raise ValueError("The registered process moved to another cgroup")
    root = Path(cgroup_root).resolve()
    path = root.joinpath(*group.parts[1:], "memory.current").resolve()
    if not path.is_relative_to(root):
        raise ValueError("Container telemetry cannot escape the cgroup root")
    raw = path.read_text().strip()
    if not raw.isdigit() or process_start_ticks(container.pid, proc_root) != container.start_ticks:
        raise ValueError("Container memory value or process identity is invalid")
    return int(raw)


def _pair(value):
    """Normalize only the queue-owned registry, never arbitrary PID targets."""
    slot, model, token = value.get("slot_id"), value.get("model_key"), value.get("ownership_token")
    started = value.get("started_unix", value.get("started"))
    if (not isinstance(slot, str) or _API_SLOT.fullmatch(slot) is None or model != "DEEPSEEK"
            or not isinstance(token, str) or not 16 <= len(token) <= 128
            or not isinstance(started, (int, float)) or isinstance(started, bool)
            or not math.isfinite(started) or started < 0):
        raise ValueError("Pressure cancellation must bind an active owned 5M API episode")
    containers = tuple(value.get("containers", ()))
    if (len(containers) > 2 or any(not isinstance(item, OwnedContainer) or item.slot_id != slot
                                 or item.role not in {"actor", "controller"} for item in containers)
            or len({item.role for item in containers}) != len(containers)):
        raise ValueError("Container telemetry must belong to this exact episode pair")
    return {"slot_id": slot, "model_key": model, "ownership_token": token,
            "started_unix": float(started), "containers": containers}


class PressureWatchdog:
    """One-second physical-memory guard with queue-local emergency aborts.

    Registry rows contain slot_id, model_key, started_unix (or started), and an
    opaque ownership_token.  Optional ``containers`` are OwnedContainer records.
    The caller must recheck the ownership token before setting the local stop
    event; the callback must not block, signal arbitrary PIDs, or retry the task.
    Missing individual-container telemetry remains unknown.  API mode requires
    an independently qualified aggregate parent probe in addition to host
    MemAvailable; Qwen mode can omit it.  Qwen rows in a mixed registry are never
    cancellation candidates.  The parent probe itself must verify the dedicated
    API cgroup ownership, memory.max and swap boundary before qualified=True.
    """
    def __init__(self, snapshot_pairs, request_abort, observe=lambda value: None, *,
                 memory_probe=host_available_memory, container_probe=owned_memory_current,
                 parent_probe=None, require_parent=False,
                 clock=time.monotonic, wall_clock=time.time):
        if type(require_parent) is not bool:
            raise ValueError("Parent requirement must be explicit boolean")
        self.snapshot_pairs, self.request_abort, self.observe = snapshot_pairs, request_abort, observe
        self.memory_probe, self.container_probe = memory_probe, container_probe
        self.parent_probe = parent_probe
        self._parent_required = require_parent or parent_probe is not None
        self._parent_paused = self._parent_required
        self.clock, self.wall_clock = clock, wall_clock
        self._lock, self._stop = threading.RLock(), threading.Event()
        self._thread, self._closed = None, False
        self._paused, self._last_observed = True, None
        self._last_abort = float("-inf")
        self._aborted = set()
        self._state = {"version": VERSION, "admit": False, "reason": "not_observed",
                       "memory_available_bytes": None, "automatic_retry": False,
                       "required_observations_complete": False}

    def _parent_observation(self):
        if not self._parent_required:
            return {"required": False, "qualified": None, "admit": True,
                    "emergency": False, "critical": False, "available_bytes": None}
        try:
            if not callable(self.parent_probe):
                raise ValueError("API pressure mode requires a qualified parent probe")
            value = self.parent_probe()
            if (not isinstance(value, dict) or value.get("qualified") is not True
                    or type(value.get("current_bytes")) is not int or value["current_bytes"] < 0
                    or type(value.get("max_bytes")) is not int or value["max_bytes"] != PARENT_MAX_BYTES):
                raise ValueError("API aggregate parent is not qualified at its exact 224 GiB boundary")
            available = max(0, value["max_bytes"] - value["current_bytes"])
            if available < PARENT_PAUSE_BYTES:
                self._parent_paused = True
            elif available >= PARENT_RESUME_BYTES:
                self._parent_paused = False
            return {"required": True, "qualified": True, "admit": not self._parent_paused,
                "current_bytes": value["current_bytes"], "max_bytes": value["max_bytes"],
                "available_bytes": available, "pause_bytes": PARENT_PAUSE_BYTES,
                "resume_bytes": PARENT_RESUME_BYTES, "emergency_bytes": PARENT_EMERGENCY_BYTES,
                "critical_bytes": PARENT_CRITICAL_BYTES,
                "emergency": available <= PARENT_EMERGENCY_BYTES,
                "critical": available <= PARENT_CRITICAL_BYTES}
        except Exception as error:
            self._parent_paused = True
            return {"required": True, "qualified": False, "admit": False,
                "available_bytes": None, "emergency": False, "critical": False,
                "error": {"type": type(error).__name__, "message": str(error)}}

    def admission(self):
        with self._lock:
            age = None if self._last_observed is None else self.clock() - self._last_observed
            timely = not self._closed and age is not None and 0 <= age <= MAX_AGE_SECONDS
            fresh = timely and self._state["required_observations_complete"]
            return {**self._state, "fresh": fresh, "observation_age_seconds": age,
                    "admit": bool(fresh and self._state["admit"]),
                    "reason": self._state["reason"] if timely else "pressure_watchdog_stale_or_closed"}

    def tick(self):
        """One bounded observation; usable with CPU-only injected fixtures."""
        if self._closed:
            raise RuntimeError("A closed pressure watchdog cannot resume")
        now, emergency, candidates = self.clock(), False, []
        parent = self._parent_observation()
        telemetry, skipped_qwen, pair_error = [], 0, None
        try:
            available = self.memory_probe()
            if type(available) is not int or available < 0:
                raise ValueError("MemAvailable must be nonnegative integer bytes")
            rows, identities = [], set()
            for item in self.snapshot_pairs():
                if item.get("model_key") == "QWEN":
                    skipped_qwen += 1
                    continue
                value = _pair(item)
                if value["slot_id"] in identities:
                    raise ValueError("Duplicate episode in pressure registry")
                identities.add(value["slot_id"])
                rows.append(value)
            for value in rows:
                observed, failures = [], []
                for item in value["containers"]:
                    try:
                        used = self.container_probe(item)
                        if type(used) is not int or used < 0:
                            raise ValueError("Invalid cgroup memory.current")
                        observed.append({"role": item.role, "memory_current_bytes": used})
                    except (OSError, ValueError) as error:
                        failures.append({"role": item.role, "reason": type(error).__name__})
                telemetry.append({"slot_id": value["slot_id"], "containers_observed": observed,
                    "container_observation_failures": failures,
                    "pair_memory_current_bytes": sum(item["memory_current_bytes"] for item in observed)
                    if len(observed) == 2 else None,
                    "missing_cgroup_telemetry_is_zero": False})
            if available < PAUSE_BYTES:
                self._paused = True
            elif available >= RESUME_BYTES:
                self._paused = False
            emergency = available <= EMERGENCY_BYTES or parent["emergency"]
            if emergency and now - self._last_abort >= ABORT_INTERVAL_SECONDS:
                eligible = [row for row in rows if row["slot_id"] not in self._aborted]
                limit = MAX_CRITICAL_ABORTS_PER_TICK if available < CRITICAL_BYTES or parent["critical"] else 1
                candidates = sorted(eligible, key=lambda row: (row["started_unix"], row["slot_id"]),
                                    reverse=True)[:limit]
            reason = ("memory_emergency" if emergency else
                "api_parent_observation_unavailable" if parent["required"] and not parent["qualified"] else
                "memory_hysteresis_pause" if self._paused else
                "api_parent_hysteresis_pause" if not parent["admit"] else "ready")
        except Exception as error:
            available, reason, self._paused = None, "pressure_observation_unavailable", True
            pair_error = {"type": type(error).__name__, "message": str(error)}
        with self._lock:
            self._last_observed = now
            self._state = {"version": VERSION, "observed_unix": self.wall_clock(),
                "admit": not self._paused and parent["admit"], "reason": reason,
                "memory_available_bytes": available, "parent_pressure": parent,
                "required_observations_complete": pair_error is None and
                    (not parent["required"] or parent["qualified"] is True),
                "pause_bytes": PAUSE_BYTES, "resume_bytes": RESUME_BYTES,
                "emergency_bytes": EMERGENCY_BYTES, "critical_bytes": CRITICAL_BYTES,
                "emergency": emergency,
                "API_pair_memory_observations": telemetry, "Qwen_registry_rows_excluded": skipped_qwen,
                "observation_error": pair_error, "automatic_retry": False,
                "aborted_slot_ids": sorted(self._aborted), "shared_host_configuration_changed": False}
        for candidate in candidates:
            # Record before invoking: a callback exception has an unknown outcome,
            # never permission to replay or repeatedly cancel the same episode.
            self._aborted.add(candidate["slot_id"])
            self._last_abort = now
            event = {"reason": "host_and_api_parent_memory_emergency"
                if available <= EMERGENCY_BYTES and parent["emergency"] else
                "api_parent_memory_emergency" if parent["emergency"] else "host_memory_emergency",
                "memory_available_bytes": available, "parent_pressure": parent,
                "threshold_bytes": EMERGENCY_BYTES, "technical_unknown": True,
                "automatic_retry": False, "stop_entire_owned_pair": True}
            try:
                self.request_abort(dict(candidate), event)
                outcome = "owned_episode_stop_requested"
            except Exception as error:
                outcome = "abort_callback_outcome_unknown"
                event["callback_error"] = {"type": type(error).__name__, "message": str(error)}
            with self._lock:
                self._state["last_abort"] = {"slot_id": candidate["slot_id"], "outcome": outcome, **event}
                self._state.setdefault("abort_requests_this_observation", []).append(self._state["last_abort"])
                self._state["aborted_slot_ids"] = sorted(self._aborted)
        result = self.admission()
        try:
            self.observe(result)
        except Exception as error:
            with self._lock:
                self._state["observer_error"] = {"type": type(error).__name__, "message": str(error)}
        return result

    def start(self):
        with self._lock:
            if self._closed or self._thread is not None:
                raise RuntimeError("A pressure watchdog starts once and cannot be replayed")
            self.tick()
            self._thread = threading.Thread(target=self._run, name="v076-memory-pressure", daemon=True)
            self._thread.start()
        return self

    def _run(self):
        while not self._stop.wait(POLL_SECONDS):
            try:
                self.tick()
            except Exception as error:
                with self._lock:
                    self._last_observed = None
                    self._state.update(admit=False, reason="pressure_thread_failure",
                        thread_error={"type": type(error).__name__, "message": str(error)})

    def close(self):
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=MAX_AGE_SECONDS)
        with self._lock:
            self._closed = True
            self._state.update(admit=False, reason="pressure_watchdog_closed")
        if thread is not None and thread.is_alive():
            raise RuntimeError("Pressure callback has not returned; new admission remains disabled")
