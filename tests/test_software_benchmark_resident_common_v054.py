"""One CPU integration control for session ownership and version-stratified progress."""
import importlib.util
import json
import os
from pathlib import Path

import pytest


def load(name):
    path = Path(__file__).resolve().parents[1] / "src/proworksim" / (name + ".py")
    spec = importlib.util.spec_from_file_location("proworksim.control_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exclusive_sessions_keep_resident_and_mixed_revision_rates_unknown(tmp_path, monkeypatch):
    session = load("software_benchmark_resident_session_v054")
    queue = load("software_benchmark_queue_v054")
    calls, active = [], {"claim": None, "poisoned": False}
    identity = {"raw_release": True, "resident": True}
    declaration = {"mode": "MATCH_PROJECT", "gpu_index": 6, "gpu_uuid": "fixed-GPU",
                   "session_lock_path": str(tmp_path / "session.lock"), "admin": {}, "unit": "registered"}
    class Admin:
        def call(self, op, **arguments):
            calls.append((op, arguments))
            if op == "status":
                return {"active_claim": active["claim"], "poisoned": active["poisoned"]}
            if op == "acquire":
                if active["claim"]:
                    return {"state": "busy"}
                active["claim"] = arguments["claim_id"]
                return {"claim_id": active["claim"], "state": "acquired",
                        "session_socket": "independent-" + active["claim"],
                        "session_identity": {"claim_id": active["claim"]}}
            if op == "release":
                active["claim"] = None
                return {"claim_id": arguments["claim_id"], "state": "released", "quiescence": {
                    "owner_idle": True, "model_busy": False, "active_session": None,
                    "learning_unchanged": True, "rng_restored_exactly": True, "weights_reloaded": False}}
            active["poisoned"] = True
            return {"poisoned": True, "inflight": 0}
    admin = Admin()
    monkeypatch.setattr(session, "admin_client", lambda declaration, identity, **kwargs: admin)
    observed = {"declaration": declaration, "identity": identity,
                "ready": {"host_process": session.process_identity(os.getpid())}}
    monkeypatch.setattr(session, "admitted_resident", lambda ref: observed)
    acquired = []
    for nonce in ("a" * 32, "b" * 32):
        root = tmp_path / nonce
        root.mkdir()
        lease = session.ResidentSession({}, slot={"slot_id": nonce}, claim_id=nonce,
                                        authorization={}, directory=root)
        acquired.append(lease.config_fields()["model_socket"])
        blocked = tmp_path / (nonce + "busy")
        blocked.mkdir()
        with pytest.raises(BlockingIOError):
            session.ResidentSession({}, slot={"slot_id": "another"}, claim_id="c" * 32,
                                    authorization={}, directory=blocked)
        lease.release(controller_result={"ledger": {"complete_actual_tokens": 1, "inflight": None}},
                      finish_receipt={"original_guard": True})
        lease.close()
    assert len(set(acquired)) == 2
    assert [name for name, _ in calls] == ["acquire", "release", "acquire", "release"]
    assert not active["poisoned"] and active["claim"] is None
    bad = tmp_path / "unknown"
    bad.mkdir()
    lease = session.ResidentSession({}, slot={"slot_id": "unknown"}, claim_id="d" * 32,
                                    authorization={}, directory=bad)
    with pytest.raises(ValueError, match="Unsettled"):
        lease.release(controller_result={"ledger": {"complete_actual_tokens": None}}, finish_receipt=None)
    lease.close()
    assert active["poisoned"] and len([x for x in calls if x[0] == "release"]) == 2

    coordinator = object.__new__(queue.Coordinator)
    coordinator.root = tmp_path / "queue"
    coordinator.bindings_ref = {"sha256": "new-resident-revision"}
    rows = []
    for i in range(500):
        rows.append({"slot": {"arm": "REF"}, "generation": {"status": "closed"},
                     "scores": {"code": {"status": "official_report", "resolved": True}},
                     "delivery": {"status": "not_applicable"},
                     "original_execution_bindings" if i == 0 else "next_execution_bindings":
                         {"sha256": "old-revision" if i == 0 else "new-resident-revision"}})
    coordinator.state = {"rows": rows, "status": "running"}
    coordinator.save()
    saved = json.loads((coordinator.root / "state.json").read_text())
    assert saved["mixed_runtime_revisions"] and saved["code_progress"]["REF"]["full_panel_rate"] is None
    assert saved["code_progress"]["REF"]["success_rate_bounds"] is None
    assert saved["runtime_revision_progress"]["old-revision"]["arms"]["REF"]["determinate"] == 1
    assert saved["runtime_revision_progress"]["new-resident-revision"]["arms"]["REF"]["determinate"] == 499
