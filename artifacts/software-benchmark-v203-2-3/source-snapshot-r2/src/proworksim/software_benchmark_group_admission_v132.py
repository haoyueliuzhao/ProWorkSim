"""Fair, drainable admission for a future coordinator; no live deployment edits.

The owner registers all pending identities before starting its group threads.
Cash/health updates are supplied by that owner; this lock never reads a ledger.
An admission is granted only when both generation and startup space exist.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import threading


VERSION = "v132-fair-group-admission-r1"


class AdmissionDeferred(RuntimeError):
    """No owned object was entered; retain this identity in the pending queue."""


@dataclass(frozen=True)
class DrainState:
    mode: str = "run"
    groups: tuple[str, ...] = ()
    maximum_generations: int = 48
    revision: int = 0

    def blocks(self, group):
        return self.mode == "drain" and (not self.groups or group in self.groups)


class DrainControl:
    """Read only the new owner's declared file; absent means its frozen default.

    Writing this file does not grant resource authority. Scope/identity guards
    still run before object creation. Already entered work and scoring do not
    consult this admission-only control.
    """

    def __init__(self, path, *, batch_root, groups, maximum=48):
        self.path = Path(path)
        self.batch_root = str(Path(batch_root).resolve())
        self.groups = tuple(groups)
        self.maximum = maximum

    def read(self):
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return DrainState(maximum_generations=self.maximum)
        if self.path.is_symlink() or len(raw) > 16384:
            raise ValueError("Invalid declared admission control file")
        value = json.loads(raw)
        if (not isinstance(value, dict)
                or set(value) != {"version", "batch_root", "mode", "groups",
                                  "maximum_generations", "revision", "reason"}
                or value["version"] != VERSION or value["batch_root"] != self.batch_root
                or value["mode"] not in {"run", "drain"}
                or not isinstance(value["groups"], list)
                or any(group not in self.groups for group in value["groups"])
                or len(set(value["groups"])) != len(value["groups"])
                or type(value["maximum_generations"]) is not int
                or not 0 <= value["maximum_generations"] <= self.maximum
                or type(value["revision"]) is not int or value["revision"] < 0
                or not isinstance(value["reason"], str)):
            raise ValueError("Admission control does not match the frozen owner")
        return DrainState(value["mode"], tuple(value["groups"]),
                          value["maximum_generations"], value["revision"])


class FairAdmission:
    def __init__(self, groups, *, control, maximum=48, maximum_startups=8,
                 pressure_probe=lambda: {"passed": True}):
        self.groups = tuple(groups)
        if (not self.groups or len(set(self.groups)) != len(self.groups)
                or type(maximum) is not int or maximum < 1
                or type(maximum_startups) is not int or not 1 <= maximum_startups <= maximum):
            raise ValueError("Invalid fixed admission dimensions")
        self.control, self.maximum, self.maximum_startups = control, maximum, maximum_startups
        self.pressure_probe = pressure_probe
        self.lock = threading.Condition(threading.RLock())
        self.pending = {group: set() for group in self.groups}
        self.identities, self.active, self.starting, self.consumed = {}, {}, set(), set()
        self.status = {group: {"healthy": False, "can_dispatch": True} for group in self.groups}
        self.rotation = 0

    def register_pending(self, group, slots):
        if group not in self.pending:
            raise ValueError("Unknown fixed group")
        slots = tuple(slots)
        if len(slots) != len(set(slots)) or any(not isinstance(slot, str) or not slot for slot in slots):
            raise ValueError("Pending identities must be unique nonempty strings")
        with self.lock:
            for slot in slots:
                if (slot in self.consumed or slot in self.active
                        or self.identities.get(slot, group) != group):
                    raise ValueError("A consumed or foreign identity cannot reenter admission")
            self.pending[group].update(slots)
            self.identities.update(dict.fromkeys(slots, group))
            self.lock.notify_all()

    def remove_pending(self, group, slots):
        """Remove known unstarted environment/cash exclusions, never an active slot."""
        with self.lock:
            for slot in slots:
                if self.identities.get(slot) != group or slot in self.active:
                    raise ValueError("Only this group's pending identity may be removed")
                self.pending[group].discard(slot)
            self.lock.notify_all()

    def set_group_status(self, group, *, healthy, can_dispatch):
        if group not in self.status or type(healthy) is not bool or type(can_dispatch) is not bool:
            raise ValueError("Explicit group health and cash admission are required")
        with self.lock:
            self.status[group] = {"healthy": healthy, "can_dispatch": can_dispatch}
            self.lock.notify_all()

    def _targets(self, state):
        counts = Counter(self.active.values())
        eligible = [g for g in self.groups if self.pending[g]
                    and self.status[g]["can_dispatch"] and not state.blocks(g)]
        targets = dict(counts)
        if not eligible:
            return targets
        capacity = max(0, min(self.maximum, state.maximum_generations)
                       - sum(n for g, n in counts.items() if g not in eligible))
        order = self.groups[self.rotation:] + self.groups[:self.rotation]
        ordered = [g for g in order if g in eligible]
        base, remainder = divmod(capacity, len(ordered))
        for i, group in enumerate(ordered):
            target = base + (i < remainder)
            # An unqualified group retains its fair future share, but enters
            # only one initial team. Its withheld share is not lent away.
            if not self.status[group]["healthy"]:
                target = min(target, 1)
            targets[group] = min(target, counts[group] + len(self.pending[group]))
        return targets

    def ceiling(self, group):
        state = self.control.read()
        pressure = self.pressure_probe()  # No file/ledger IO while holding our lock.
        with self.lock:
            if pressure.get("passed") is not True or state.blocks(group):
                return sum(g == group for g in self.active.values())
            return self._targets(state).get(group, 0)

    def try_enter(self, row):
        """Atomically reserve startup+generation before any actor is created."""
        group, slot = row["organization_id"], row["slot_id"]
        state = self.control.read()
        pressure = self.pressure_probe()
        with self.lock:
            if self.identities.get(slot) != group or slot not in self.pending[group]:
                raise ValueError("Only a registered, unconsumed pending slot may start")
            if state.blocks(group):
                raise AdmissionDeferred("operator_drain_before_owned_entry")
            if (pressure.get("passed") is not True
                    or len(self.active) >= min(self.maximum, state.maximum_generations)
                    or len(self.starting) >= self.maximum_startups):
                return False
            targets, counts = self._targets(state), Counter(self.active.values())
            candidates = [g for g in self.groups if self.pending[g]
                          and counts[g] < targets.get(g, 0)]
            if not candidates:
                return False
            minimum = min(counts[g] for g in candidates)
            order = self.groups[self.rotation:] + self.groups[:self.rotation]
            chosen = next(g for g in order if g in candidates and counts[g] == minimum)
            if chosen != group:
                return False
            self.pending[group].remove(slot)
            self.active[slot] = group
            self.starting.add(slot)
            self.rotation = (self.groups.index(group) + 1) % len(self.groups)
            return True

    def enter(self, row, stop_event):
        while not stop_event.is_set():
            if self.try_enter(row):
                return
            with self.lock:
                self.lock.wait(.2)
        raise AdmissionDeferred("cancelled_before_owned_entry")

    def require_start(self, row):
        """Second drain check immediately before actor reservation/creation.

        On deferral the caller uses leave(..., unentered=True), retains its
        pending identity, and creates no object. This is not a model retry.
        """
        state = self.control.read()
        with self.lock:
            if row["slot_id"] not in self.starting:
                raise ValueError("No startup lease for this identity")
            if state.blocks(row["organization_id"]):
                raise AdmissionDeferred("operator_drain_before_owned_start")

    def ready(self, row):
        with self.lock:
            self.starting.discard(row["slot_id"])
            self.lock.notify_all()

    def leave(self, row, *, unentered=False):
        """unentered=True requires the owning queue's no-claim/no-API proof."""
        slot, group = row["slot_id"], row["organization_id"]
        with self.lock:
            if self.active.get(slot) != group:
                raise ValueError("Only the current exact lease owner may release")
            self.active.pop(slot)
            self.starting.discard(slot)
            if unentered:
                self.pending[group].add(slot)
            else:
                self.consumed.add(slot)
            self.lock.notify_all()

    def snapshot(self):
        with self.lock:
            return {"version": VERSION, "active_generation": len(self.active),
                    "active_startups": len(self.starting),
                    "by_group": dict(Counter(self.active.values())),
                    "pending": {g: len(v) for g, v in self.pending.items()},
                    "healthy_groups": [g for g in self.groups if self.status[g]["healthy"]],
                    "maximum_generation": self.maximum, "maximum_startups": self.maximum_startups,
                    "waiting_startups_hold_generation_tickets": False,
                    "existing_generation_cancelled_by_drain": False}
