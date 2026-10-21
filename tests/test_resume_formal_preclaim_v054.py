"""One necessary CPU control for explicit zero-execution queue migration."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

tool = Path(__file__).resolve().parents[1] / "tools/resume_formal_preclaim_v054.py"
if not tool.exists():
    tool = Path(__file__).with_name("resume_formal_preclaim_v054.py")
spec = importlib.util.spec_from_file_location("recovery", tool)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def test_recovery_preserves_entered_results_and_rejects_any_claim(tmp_path):
    def put(name, value):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return recovery.reference(path)

    old_binding = {"path": "old", "sha256": "old", "bytes": 1}
    new_binding = {"path": "new", "sha256": "new", "bytes": 2}
    transition = {"path": "transition", "sha256": "transition", "bytes": 3}
    rows = [{"slot": {"slot_id": "slot-" + str(i)}, "generation": {"status": "pending", "attempts": []},
             "scores": {}, "delivery": {"status": "not_applicable"}} for i in range(1500)]
    original_closed = rows[0]
    original_closed.update(generation={"status": "closed", "config": {"path": "unchanged-old-condition"}},
                           scores={"code": {"status": "official_report", "resolved": False}})
    claim = recovery.claim_directory(tmp_path, "slot-0")
    claim.mkdir(parents=True)
    (claim / "claim.json").write_text("{}")
    failed = rows[4]
    job = {"path": "same-job", "sha256": "same", "bytes": 0}
    result = {"slot_id": "slot-4", "status": "preparation_not_ready", "slot_claimed": False,
              "entered": False, "model_calls": 0, "GPU_loads": 0}
    result_ref = put("result.json", result)
    completion = put("completion.json", {"returncode": 75, "job": job})
    config = put("config.json", {"model_ready": str(tmp_path / "absent-ready"),
                                 "model_identity": str(tmp_path / "absent-identity")})
    failed["generation"] = {"status": "technical_unknown", "claimed": False, "result": result_ref,
                            "job": job, "unit": "synthetic", "config": config,
                            "attempts": [{"result": result_ref, "completion": completion}]}
    state = {"status": "paused_technical_unknown", "planned_slots": 1500, "rows": rows,
             "faults": [{"kind": "original_preparation_fault"}], "bindings": old_binding}
    assert len(recovery.verify_state(state, repository=tmp_path, slot_ids=["slot-4"],
                                     unit_check=lambda unit: {"stopped": True})) == 1
    migrated = recovery.resumed_state(state, new_binding, {"slot-4"}, transition)
    assert migrated["rows"][0]["generation"] == state["rows"][0]["generation"]
    assert migrated["rows"][0]["scores"] == state["rows"][0]["scores"]
    assert migrated["rows"][0]["original_execution_bindings"] == old_binding
    assert migrated["rows"][4]["generation"]["attempts"] == state["rows"][4]["generation"]["attempts"]
    assert len(migrated["rows"][4]["generation"]["attempts"]) + 1 == 2
    assert migrated["faults"] == state["faults"] and state["status"] == "paused_technical_unknown"
    assert migrated["status"] == "running" and len(migrated["rows"]) == 1500
    untouched = copy.deepcopy(state)
    unexpected_claim = recovery.claim_directory(tmp_path, "slot-4")
    unexpected_claim.mkdir(parents=True)
    with pytest.raises(ValueError, match="global claim"):
        recovery.verify_state(state, repository=tmp_path, slot_ids=["slot-4"], unit_check=lambda unit: {})
    assert state == untouched
    unexpected_claim.rmdir()
    result["entered"] = True
    failed["generation"]["result"] = put("result.json", result)
    with pytest.raises(ValueError, match="zero-execution"):
        recovery.verify_state(state, repository=tmp_path, slot_ids=["slot-4"], unit_check=lambda unit: {})
