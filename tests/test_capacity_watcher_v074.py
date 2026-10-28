from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from proworksim.software_benchmark_candidates_v054 import reference, write_new

FILE = Path(__file__).resolve().parents[1] / "tools/watch_additional_qwen_v074.py"
spec = importlib.util.spec_from_file_location("capacity_watcher_v074", FILE)
watcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watcher)


class ClockAndStop:
    def __init__(self):
        self.now = 0
        self.stopped = False
        self.waits = []
    def is_set(self):
        return self.stopped
    def wait(self, seconds):
        self.waits.append(seconds)
        self.now += seconds
        return self.stopped


def test_only_model5_attempts_each_minute_then_consumption_exits():
    clock, calls, records = ClockAndStop(), [], []
    def attempt(indices):
        calls.append((clock.now, indices))
        return {"residents": {"5": {"status": "waiting_for_capacity" if len(calls) == 1 else "launch_requested"}}}
    result = watcher.monitor(consumed=lambda: len(calls) == 2,
        observe_primary=lambda: {"decision": "attempt"}, attempt=attempt,
        stopped=clock, record=records.append, clock=lambda: clock.now)
    assert result == {"reason": "model5_identity_consumed", "attempts": 2}
    assert calls == [(0, [5]), (60, [5])] and clock.waits == [60]


def test_primary_health_and_six_hour_expiry_block_dispatch():
    healthy = {"phase": "running", "failure": None, "unix": 100}
    cursor = {"phase": "running", "failure": None, "pending_generation": ["Qwen"]}
    assert watcher.primary_decision(healthy, cursor, now=101)[0] == "attempt"
    assert watcher.primary_decision(healthy, cursor, now=281)[0] == "wait"
    assert watcher.primary_decision({**healthy, "phase": "closed"}, cursor, now=101)[0] == "stop"
    clock = ClockAndStop()
    result = watcher.monitor(consumed=lambda: False, observe_primary=lambda: {"decision": "wait"},
        attempt=lambda _: pytest.fail("Unhealthy primary must not launch a model"),
        stopped=clock, record=lambda _: None, clock=lambda: clock.now)
    assert result["reason"] == "six_hour_window_expired" and result["attempts"] == 0
    assert clock.now == 21600 and len(clock.waits) == 360


def test_unexpected_launcher_failure_not_blindly_retried():
    clock = ClockAndStop()
    result = watcher.monitor(consumed=lambda: False, observe_primary=lambda: {"decision": "attempt"},
        attempt=lambda _: {"residents": {"5": {"status": "launch_blocked"}}},
        stopped=clock, record=lambda _: None, clock=lambda: clock.now)
    assert result["reason"] == "launcher_noncapacity_result_no_retry" and not clock.waits


def test_reservation_charged_to_original_pool_and_only_exact_lease_released(tmp_path, monkeypatch):
    claims = tmp_path / "shared"
    claims.mkdir()
    (claims / "allocation.lock").touch()
    mine = tmp_path / "mine"
    auth = write_new(tmp_path / "authority.json", {})
    spec = write_new(tmp_path / "spec.json", {})
    other = claims / "active-other.json"
    original_other = b'{"reserved_cpu":12,"reserved_memory_bytes":103079215104}\n'
    other.write_bytes(original_other)
    monkeypatch.setattr(watcher, "LEASE", claims / "active-v074-capacity-watcher.json")
    monkeypatch.setattr(watcher, "CLAIM", mine / "claim.json")
    monkeypatch.setattr(watcher, "RELEASE", mine / "released.json")
    monkeypatch.setattr(watcher, "RUN_ROOT", mine)
    monkeypatch.setattr(watcher, "AUTH", Path(auth["path"]))
    monkeypatch.setattr(watcher, "SPEC", Path(spec["path"]))
    monkeypatch.setattr(watcher, "require_allowed", lambda: None)
    monkeypatch.setattr(watcher, "ordinary_user", lambda: None)
    monkeypatch.setattr(watcher, "affinity", lambda: [172])
    seen = []
    def budget(active, cpu, memory):
        seen.append((active, cpu, memory))
        return {"within_original_budget": True}
    monkeypatch.setattr(watcher.policy, "_budget", budget)
    claim = watcher.reserve_capacity()
    assert seen[0][1:] == (1, 4 * 1024**3)
    assert watcher.LEASE.read_bytes() == watcher.CLAIM.read_bytes()
    with pytest.raises(ValueError):
        watcher.release_capacity(reference(other))
    watcher.release_capacity(claim)
    assert not watcher.LEASE.exists() and other.read_bytes() == original_other
    assert json.loads(watcher.RELEASE.read_bytes())["claim"] == claim


def test_exact_one_CPU_bounded_nonrestarting_user_unit(monkeypatch):
    value = {"ownership_token": "a" * 32, "cpu_affinity": [172]}
    monkeypatch.setattr(watcher, "validate_spec", lambda spec: spec)
    argv = watcher.command(value)
    for expected in ("--user", "--unit=proworksim-v074-model5-watcher.service", "--property=Restart=no",
                     "--property=CPUAffinity=172", "--property=CPUQuota=100%", "--property=MemoryMax=4G",
                     "--property=MemorySwapMax=0", "--property=TasksMax=64", "--property=RuntimeMaxSec=21600"):
        assert expected in argv
    assert argv[-1] == "--execute"
