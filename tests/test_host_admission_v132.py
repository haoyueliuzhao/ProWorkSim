"""Necessary future-deployment controls; no services, containers or model calls."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import socket
import subprocess
import threading

import pytest

from proworksim.software_benchmark_group_admission_v132 import (
    VERSION, AdmissionDeferred, DrainControl, FairAdmission,
)
from proworksim.software_benchmark_host_memory_v132 import (
    GIB, HostMemoryGate, manager_pressure,
)


GROUPS = ("CHIEF", "PIPELINE", "REVIEW", "SPRINT", "MATRIX")


@pytest.fixture(autouse=True)
def no_external(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("CPU controls have no external-operation authority")
    for name in ("connect", "bind", "sendto"):
        monkeypatch.setattr(socket.socket, name, deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)


def prepared_gate(tmp_path):
    control = DrainControl(tmp_path / "admission.json", batch_root=tmp_path, groups=GROUPS)
    gate = FairAdmission(GROUPS, control=control)
    rows = {group: [{"organization_id": group, "slot_id": f"{group}:{i}"} for i in range(50)]
            for group in GROUPS}
    for group in GROUPS:
        gate.register_pending(group, [r["slot_id"] for r in rows[group]])
    return gate, control, rows


def write_control(control, *, mode="drain", groups=(), maximum=48):
    control.path.write_text(json.dumps({"version": VERSION, "batch_root": control.batch_root,
        "mode": mode, "groups": list(groups), "maximum_generations": maximum,
        "revision": 1, "reason": "CPU-only operator fixture"}))


def test_early_healthy_review_cannot_capture_39_tickets_and_full_pool_is_balanced(tmp_path):
    gate, _, rows = prepared_gate(tmp_path)
    for group in GROUPS:
        assert gate.try_enter(rows[group][0])
        gate.ready(rows[group][0])
    gate.set_group_status("REVIEW", healthy=True, can_dispatch=True)
    next_row = dict.fromkeys(GROUPS, 1)
    for _ in range(100):
        row = rows["REVIEW"][next_row["REVIEW"]]
        if gate.try_enter(row):
            gate.ready(row)
            next_row["REVIEW"] += 1
    assert gate.snapshot()["by_group"]["REVIEW"] <= 10
    for group in GROUPS:
        gate.set_group_status(group, healthy=True, can_dispatch=True)
    for _ in range(100):
        for group in GROUPS:
            row = rows[group][next_row[group]]
            if gate.try_enter(row):
                gate.ready(row)
                next_row[group] += 1
        if gate.snapshot()["active_generation"] == 48:
            break
    counts = gate.snapshot()["by_group"]
    assert sum(counts.values()) == 48 and max(counts.values()) - min(counts.values()) <= 1
    assert Counter(counts.values()) == {10: 3, 9: 2}
    # Repeated ceiling reads grant nothing and cannot ratchet the group share.
    before = dict(counts)
    for _ in range(50):
        gate.ceiling("REVIEW")
    assert gate.snapshot()["by_group"] == before


def test_drain_is_checked_at_dispatch_and_actual_start_without_cancelling_live_work(tmp_path):
    gate, control, rows = prepared_gate(tmp_path)
    live, not_entered = rows["CHIEF"][0], rows["PIPELINE"][0]
    assert gate.try_enter(live)
    gate.require_start(live)
    gate.ready(live)
    assert gate.try_enter(not_entered)
    write_control(control)
    with pytest.raises(AdmissionDeferred, match="before_owned_start"):
        gate.require_start(not_entered)
    gate.leave(not_entered, unentered=True)
    with pytest.raises(AdmissionDeferred, match="before_owned_entry"):
        gate.try_enter(rows["REVIEW"][0])
    assert gate.snapshot()["active_generation"] == 1
    assert gate.ceiling("CHIEF") == 1
    # An already entered generation/score can close without consulting drain.
    gate.leave(live)
    assert gate.snapshot()["active_generation"] == 0
    with pytest.raises(ValueError, match="consumed"):
        gate.register_pending("CHIEF", [live["slot_id"]])
    write_control(control, mode="run")
    # Resume respects the rotating turn; PIPELINE cannot jump four waiting
    # groups merely because its unentered lease was returned by drain.
    for group in ("REVIEW", "SPRINT", "MATRIX", "CHIEF"):
        row = rows[group][1 if group == "CHIEF" else 0]
        assert gate.try_enter(row)
        gate.ready(row)
    assert gate.try_enter(not_entered)
    gate.leave(not_entered, unentered=True)


def test_no_pending_group_takes_no_new_share_and_startup_waiters_hold_no_lease(tmp_path):
    gate, _, rows = prepared_gate(tmp_path)
    for group in GROUPS:
        gate.set_group_status(group, healthy=True, can_dispatch=True)
    for group in ("SPRINT", "MATRIX"):
        gate.remove_pending(group, [r["slot_id"] for r in rows[group]])
    assert gate.ceiling("CHIEF") == gate.ceiling("PIPELINE") == gate.ceiling("REVIEW") == 16
    next_row = dict.fromkeys(GROUPS, 0)
    for _ in range(8):
        for group in GROUPS[:3]:
            row = rows[group][next_row[group]]
            if gate.try_enter(row):
                next_row[group] += 1
    assert gate.snapshot()["active_startups"] == gate.snapshot()["active_generation"] == 8
    assert not gate.try_enter(rows["REVIEW"][next_row["REVIEW"]])
    assert gate.snapshot()["active_generation"] == 8


def test_two_heavy_phases_bound_concurrency_and_release_after_exception():
    gate = HostMemoryGate()
    release = threading.Event()
    entered = [threading.Event() for _ in range(3)]
    errors = []
    def work(index):
        try:
            with gate.phase(str(index), "scripted_archive"):
                entered[index].set()
                if index < 2:
                    assert release.wait(3)
                if index == 1:
                    raise ValueError("scripted archive failure")
        except ValueError as error:
            errors.append(str(error))
    threads = [threading.Thread(target=work, args=(i,)) for i in range(3)]
    try:
        threads[0].start()
        threads[1].start()
        assert entered[0].wait(2) and entered[1].wait(2)
        threads[2].start()
        assert not entered[2].wait(.05)
        assert len(gate.snapshot()["active"]) == 2
        release.set()
        for thread in threads:
            thread.join(3)
        assert entered[2].is_set() and all(not t.is_alive() for t in threads)
        assert errors == ["scripted archive failure"]
        assert not gate.snapshot()["active"] and not gate.snapshot()["waiting"]
    finally:
        release.set()
        for thread in threads:
            if thread.ident:
                thread.join(3)


def test_initial_snapshot_drops_tree_and_later_callback_checks_original_bytes(tmp_path):
    gate = HostMemoryGate()
    value = {"files": {"a.py": "x = 1\n"}, "entry_metadata": {"a.py": {"mode": "100644"}},
             "file_policy": {"max_source_bytes": 1024}, "tree": {"sha256": "fixture"}}
    raw = json.dumps(value).encode()
    path = tmp_path / "snapshot.json"
    path.write_bytes(raw)
    reference = {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    parked, ref = gate.capture_initial("slot", lambda: (json.loads(raw), reference))
    assert ref == reference and parked.file_policy == value["file_policy"]
    assert "files" not in vars(parked) and "tree" not in vars(parked)
    with pytest.raises(RuntimeError, match="shared heavy phase"):
        gate.load(parked)
    actual = gate.within_snapshots("slot", [parked], lambda bundle: bundle["files"]["a.py"])
    assert actual == "x = 1\n" and not gate.snapshot()["active"]
    path.write_bytes(raw.replace(b"x = 1", b"x = 2"))
    with pytest.raises(ValueError, match="bytes changed"):
        gate.within_snapshots("slot", [parked], lambda bundle: bundle)
    assert not gate.snapshot()["active"]
    gate.close()


def test_heavy_allocations_stay_on_two_workers_and_nested_work_keeps_owner():
    gate = HostMemoryGate()
    identities = set()
    results = []
    def operation():
        identities.add(threading.get_ident())
        assert threading.current_thread().name.startswith("v132-host-heavy")
        assert gate.run_heavy("slot", "nested_exact_owner", lambda: 17) == 17
        with pytest.raises(ValueError, match="change its owner"):
            gate.run_heavy("another-slot", "nested_foreign_owner", lambda: 0)
        return {"receipt": True}
    callers = [threading.Thread(target=lambda: results.append(
        gate.run_heavy("slot", "archive", operation)))
               for _ in range(6)]
    # Different generation threads use the same bounded allocation workers.
    for caller in callers:
        caller.start()
        caller.join(2)
        assert not caller.is_alive()
    assert 1 <= len(identities) <= 2
    assert results == [{"receipt": True}] * 6
    gate.close()
    with pytest.raises(RuntimeError, match="already closed"):
        gate.run_heavy("slot", "late", operation)


def test_new_manager_pressure_is_readonly_and_stops_only_new_admission(tmp_path):
    for name, value in {"memory.current": 27 * GIB, "memory.high": 30 * GIB,
                        "memory.max": 32 * GIB}.items():
        (tmp_path / name).write_text(str(value))
    pressure = tmp_path / "memory.pressure"
    pressure.write_text("some avg10=1.0\nfull avg10=0.5 avg60=0.1 avg300=0.1 total=123\n")
    assert manager_pressure(tmp_path)["passed"]
    pressure.write_text("some avg10=99.0\nfull avg10=98.0 avg60=97.0 avg300=92.0 total=123\n")
    assert not manager_pressure(tmp_path)["passed"]
    assert (tmp_path / "memory.max").read_text() == str(32 * GIB)
    (tmp_path / "memory.high").write_text(str(24 * GIB))
    with pytest.raises(PermissionError, match="new frozen"):
        manager_pressure(tmp_path)
