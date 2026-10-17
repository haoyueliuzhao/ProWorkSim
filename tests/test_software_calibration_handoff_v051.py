"""Only new host handoff invariants; no model, old tokenizer or scorer replay."""
from pathlib import Path

import pytest

from scripts import software_calibration_v051 as host


def handoff_fixture(tmp_path):
    rows = [{"slot_id": f"slot-{i}", "worker": f"shard-{i // 12}",
             "maximum_tokens": 99, "seed": i} for i in range(48)]
    host.write(tmp_path / "slots/slot-0/started.json", {"pid": 10})
    host.write(tmp_path / "slots/slot-0/generation.json", {"usage": {"total_tokens": 7}})
    host.write(tmp_path / "slots/slot-0/grade/result.json", {"pass_at_1": 0})
    host.write(tmp_path / "slots/slot-12/started.json", {"pid": 11})
    states = {}
    for i in range(4):
        attempt = {"pid": 10 + i, "gpu": {"index": 5 if i == 1 else i},
                   "exit_code": -15 if i == 1 else 0, "output": str(tmp_path / f"worker-{i}"),
                   "report": {"status": "paused_before_next_slot", "guard": {"passed": True}}}
        states[f"shard-{i}"] = {"attempts": [attempt]}
    host.write(tmp_path / "worker-1/host-stop.json", {"reason": "explicit_user_gpu5_relinquishment"})
    supervisor = {"status": "paused", "ended_at": 1, "observer_pid": 123, "states": states}
    receipt = {"kind": "explicit_user_gpu_relinquishment", "requested_gpu": 5, "pid": 11,
               "restart_or_resample_authorized": False,
               "release_observation": {"worker_process_exists": False}}
    return {"rows": rows}, supervisor, receipt


def test_handoff_selects_exact_unstarted_and_preserves_failed_and_unknown(tmp_path):
    plan, supervisor, receipt = handoff_fixture(tmp_path)
    rows, excluded = host.remaining_inventory(tmp_path, plan, supervisor, receipt)
    assert excluded == ["slot-0", "slot-12"]
    assert rows == [r for r in plan["rows"] if r["slot_id"] not in excluded]
    ledger = host.ledger(tmp_path, plan["rows"])
    assert ledger["known_actual_tokens"] == 7
    assert ledger["uncertain_reservation_tokens"] == 99
    assert ledger["complete_actual_tokens"] is None
    assert host.GPU_PREFERENCE == [0, 1, 3, 4, 6, 7]


def test_handoff_requires_terminal_original_host_and_independent_guards(tmp_path):
    plan, supervisor, receipt = handoff_fixture(tmp_path)
    supervisor["status"] = "running"
    with pytest.raises(ValueError, match="finish closing"):
        host.remaining_inventory(tmp_path, plan, supervisor, receipt)
    supervisor["status"] = "paused"
    supervisor["states"]["shard-2"]["attempts"][0]["report"]["guard"]["passed"] = False
    with pytest.raises(ValueError, match="original guard"):
        host.remaining_inventory(tmp_path, plan, supervisor, receipt)


def test_handoff_does_not_bypass_other_unknowns_or_pre_request_faults(tmp_path):
    plan, supervisor, receipt = handoff_fixture(tmp_path)
    grade = tmp_path / "slots/slot-0/grade/result.json"
    host.write(grade, {"pass_at_1": None})
    with pytest.raises(ValueError, match="unresolved scoring"):
        host.remaining_inventory(tmp_path, plan, supervisor, receipt)
    host.write(grade, {"pass_at_1": 0})
    pre = tmp_path / "slots/slot-1"
    pre.mkdir()
    with pytest.raises(ValueError, match="pre-generation"):
        host.remaining_inventory(tmp_path, plan, supervisor, receipt)
    host.write(pre / "started.json", {"pid": 10})
    with pytest.raises(ValueError, match="Unexplained interruption"):
        host.remaining_inventory(tmp_path, plan, supervisor, receipt)


def test_prepare_copies_original_runtime_and_changes_only_host(monkeypatch, tmp_path):
    old = tmp_path / "old"
    old.mkdir()
    plan, supervisor, receipt = handoff_fixture(old)
    snapshot = old / "source"
    (snapshot / "src/proworksim").mkdir(parents=True)
    (snapshot / "scripts").mkdir()
    for name, text in {"src/proworksim/runtime.py": "old runtime\n",
                       "scripts/software_calibration_v051.py": "old host\n"}.items():
        (snapshot / name).write_text(text)
    plan.update(source_root=str(snapshot), source_files={str(p.relative_to(snapshot)): host.sha_file(p)
                for p in snapshot.rglob("*.py")}, contract=host.CONTRACT, limits=host.LIMITS)
    host.write(old / "plan.json", host.sealed(plan))
    host.write(old / "supervisor.json", supervisor)
    host.write(old / "gpu5-relinquishment.json", receipt)
    host.write(old / "gpu-idle-reschedule.json", idle_receipt(supervisor, []))
    monkeypatch.setattr(host, "frozen", lambda root: plan)
    monkeypatch.setattr("proworksim.audit.code_identity", lambda: {"code_dirty": False, "commit": "fixture"})
    result = host.prepare_continuation(tmp_path / "new", old)
    assert result["maximum_generations"] == 46
    assert result["maximum_actual_tokens"] == 46 * 99
    assert result["source_files"]["src/proworksim/runtime.py"] == plan["source_files"]["src/proworksim/runtime.py"]
    assert (Path(result["source_root"]) / "src/proworksim/runtime.py").read_text() == "old runtime\n"
    assert result["gpu_preference"] == [0, 1, 3, 4, 6, 7]
    assert result["idle_policy"] == host.IDLE_POLICY
    assert result["continuation"]["retries"] == 0


def idle_receipt(supervisor, active):
    return {"kind": "explicit_user_cancel_active_gpu_and_reschedule_when_idle",
            "allowed_gpu_indices": [0, 1, 3, 4, 6, 7], "max_residents": 4,
            "no_started_request_replay": True, "supervisor_pid": 123,
            "active_workers_at_request": active,
            "stop_observation": {"host_status": "paused", "workers": [
                {"pid": state["attempts"][-1]["pid"], "exists": False}
                for state in supervisor["states"].values()]}}


def test_second_explicit_cancellation_preserves_both_unknown_calls(tmp_path):
    plan, supervisor, receipt = handoff_fixture(tmp_path)
    attempt = supervisor["states"]["shard-2"]["attempts"][0]
    attempt.update(exit_code=-15, report={})
    host.write(tmp_path / "worker-2/host-stop.json", {"reason": "supervisor_interrupted_or_fault"})
    host.write(tmp_path / "slots/slot-24/started.json", {"pid": 12})
    reschedule = idle_receipt(supervisor, [{"pid": 12, "gpu": 2,
        "task": {"kind": "generation", "slot_id": "slot-24"}}])
    rows, excluded = host.remaining_inventory(tmp_path, plan, supervisor, receipt, reschedule)
    assert len(rows) == 45 and excluded == ["slot-0", "slot-12", "slot-24"]
    assert host.ledger(tmp_path, plan["rows"])["uncertain_reservation_tokens"] == 198
    reschedule["active_workers_at_request"][0]["pid"] = 999
    with pytest.raises(ValueError, match="original guard"):
        host.remaining_inventory(tmp_path, plan, supervisor, receipt, reschedule)


def test_idle_scheduler_requires_empty_allowed_card_and_continuous_sixty_seconds():
    history = {}
    cards = [{"index": i, "uuid": str(i), "shared": i == 1,
              "utilization_percent": 10 if i == 3 else 0} for i in range(8)]
    assert host.idle_ready_cards(cards, history, now=100) == []
    assert set(history) == {"0", "4", "6", "7"}
    assert host.idle_ready_cards(cards, history, now=159) == []
    ready = host.idle_ready_cards(cards, history, now=160)
    assert [c["index"] for c in ready] == [0, 4, 6, 7]
    cards[0]["shared"] = True
    host.idle_ready_cards(cards, history, now=161)
    assert "0" not in history
    cards[0]["shared"] = False
    assert 0 not in [c["index"] for c in host.idle_ready_cards(cards, history, now=200)]
    assert 0 in [c["index"] for c in host.idle_ready_cards(cards, history, now=260)]
