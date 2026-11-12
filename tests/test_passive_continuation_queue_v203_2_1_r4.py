"""The remaining queue uses recovered evidence, never resamples its gate tasks."""
from collections import deque
import importlib.util
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest


def test_only_remaining_tasks_enter_after_independent_gate(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "tools/run_passive_pilot_v203_2_1_r4.py"
    spec = importlib.util.spec_from_file_location("continuation_queue_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = [{"slot_id": f"original-unused-{i}", "slot_index": i} for i in range(2032402, 2032412)]
    owner = module.Coordinator.__new__(module.Coordinator)
    owner.cash_status = lambda group: {"can_start_generation": True, "state": "ready"}
    owner.money, owner.healthy, owner.generation, owner.rotation = {}, {"REVIEW2": True}, {}, 0
    owner.pending, owner.stop_new_generation = {"REVIEW2": deque(rows)}, threading.Event()
    owner.admission = SimpleNamespace(
        control=SimpleNamespace(read=lambda: SimpleNamespace(blocks=lambda group: False)),
        set_group_status=lambda *a, **k: None, try_enter=lambda row: True)
    submissions = []
    executor = SimpleNamespace(submit=lambda fn, row: submissions.append(row) or object())
    def reject():
        raise PermissionError("original evidence incomplete")
    monkeypatch.setattr(module.scope, "require_continuation_gate", reject)
    with pytest.raises(PermissionError, match="incomplete"):
        owner._admit(executor)
    assert submissions == [] and len(owner.pending["REVIEW2"]) == 10
    monkeypatch.setattr(module.scope, "require_continuation_gate", lambda: {"passed": True})
    owner._admit(executor)
    assert [r["slot_index"] for r in submissions] == list(range(2032402, 2032410))
    assert len(owner.pending["REVIEW2"]) == 2
    assert all(r["slot_index"] not in (2032200, 2032201) for r in submissions)
