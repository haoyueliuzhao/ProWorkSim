import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_candidates_v054 import write_new

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tested_primary_v068", ROOT / "tools/run_full_benchmark_v068.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class NoModels:
    def start_residents(self):
        return []
    def ready_residents(self):
        return []
    def stop_residents(self):
        return []


def run_queue(rows, *, controls, initial, grading):
    original_globals = dict(runner.base.execute_queue.__globals__)
    execute, proof = runner.recovery_function()
    assert len(proof["only_changes"]) == 2
    assert runner.base.execute_queue.__globals__ == original_globals
    return execute(rows, controls=controls, qualifications={}, grading=grading, runtime=NoModels(),
        run_episode=lambda *_args, **_kwargs: pytest.fail("Historical generation cannot replay"),
        progress_sink=lambda *_: None, event_sink=lambda *_args, **_kwargs: None,
        cursor_sink=lambda *_: None, entered_probe=lambda _: False,
        model_exhausted=lambda _: False, generation_limit=lambda: 0, initial_state=initial)


def test_completed_gold_is_seeded_so_only_unused_empty_runs(tmp_path):
    request = write_new(tmp_path / "empty.json", {"instance_id": "task", "patch_kind": "empty"})
    observed = []
    class Grading:
        def run_request(self, ref, stop_event=None):
            observed.append(ref)
            return {"status": "process_exited", "returncode": 0}
        def trustworthy_cleanup(self, _):
            return True
        def qualify(self, task):
            assert task == "task"
            return {"proof": "same original gold and new empty receipts"}
    state = {"completed_controls": {"task": {"gold": {"status": "technical_unknown", "returncode": 0}}}}
    result = run_queue([], controls=[request], initial=state, grading=Grading())
    assert result["failure"] is None and observed == [request]
    assert result["qualifications"]["task"]["status"] == "qualified"
    assert set(state["completed_controls"]["task"]) == {"gold"}


def test_pending_score_is_seeded_without_a_new_generation(tmp_path):
    row = {"slot_id": "old-Q", "slot_index": 4, "model_key": "QWEN", "arm": "REF", "group_id": "Q"}
    result_ref = write_new(tmp_path / "generation.json", {"slot_id": "old-Q"})
    request = write_new(tmp_path / "score.json", {"instance_id": "task", "patch_kind": "candidate"})
    class Grading:
        def prepare_score(self, value, endpoint):
            assert value == result_ref and endpoint == "code"
            return request
        def run_request(self, ref, stop_event=None):
            assert ref == request
            return {"status": "process_exited"}
        def trustworthy_cleanup(self, _):
            return True
    state = {"generation": {"old-Q": {"entered": True, "status": "closed", "result": result_ref}},
             "pending_score_jobs": [("code", row, result_ref, False)]}
    result = run_queue([row], controls=[], initial=state, grading=Grading())
    assert result["failure"] is None and result["scores"]["old-Q"]["request"] == request
    assert len(result["generation"]) == 1


def test_unused_resident_id_can_reuse_released_uuid_and_caps_live_count(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.policy, "BATCH_ROOT", tmp_path)
    claims = tmp_path / "resource-claims"
    claims.mkdir()
    (claims / "model-0.released.json").write_text("{}")
    runs = tmp_path / "residents"
    old = runs / "model-0"
    old.mkdir(parents=True)
    (old / "spec.json").write_text(json.dumps({"index": 0, "gpu_uuid": "released-original-UUID"}))
    (old / "closed.json").write_text(json.dumps({"child_exited": True}))
    old_bytes = (old / "spec.json").read_bytes()
    made, launched = [], []
    class Delegate:
        RUNS = runs
        def gpu_capacity(self):
            return [{"gpu_uuid": "released-original-UUID", "gpu_index": 2},
                    {"gpu_uuid": "other-free-UUID", "gpu_index": 4},
                    {"gpu_uuid": "third-free-UUID", "gpu_index": 5}]
        def shared_capacity_for(self, number):
            assert number == 2
            return True
        def make_spec(self, index, card):
            made.append((index, card["gpu_uuid"]))
            path = self.RUNS / f"model-{index}"
            path.mkdir()
            value = {"index": index, "gpu_uuid": card["gpu_uuid"], "root": str(path)}
            write_new(path / "spec.json", value)
            return value
        def unit_command(self, spec):
            return ["scripted-unit", str(spec["index"])]
        def user_manager_environment(self):
            return {}
        def ready_residents(self):
            return []
    runtime = runner.UnusedResidentRuntime(Delegate(), guard=lambda *_: None,
        launch=lambda argv, **_: (launched.append(argv) or SimpleNamespace(returncode=0, stdout="", stderr="")))
    runtime.start_residents()
    runtime.start_residents()
    assert made == [(1, "released-original-UUID"), (2, "other-free-UUID")]
    assert len(launched) == 2 and (old / "spec.json").read_bytes() == old_bytes


def test_existing_qualification_cursor_precedes_resident_start(tmp_path, monkeypatch):
    new_root, primary = tmp_path / "new-primary", tmp_path / "old-primary"
    primary.mkdir()
    rows = [{"slot_id": f"Q{i}", "slot_index": i, "model_key": "QWEN"} for i in range(3000)]
    plan = write_new(tmp_path / "plan.json", {"rows": rows})
    inventory = {"generation": {}, "scores": {}, "deliveries": {}, "retry_zero_generation": {},
        "allowed_generation_slot_ids": [row["slot_id"] for row in rows], "usage_record_files": {},
        "unused_control_requests": [], "unused_score_jobs": [],
        "qualifications": {"task": {"status": "qualified", "qualification": {"proof": "retained"}}}}
    inventory_ref = write_new(tmp_path / "inventory.json", inventory)
    write_new(primary / "coordinator-plan.json", {"disk_boundary": {}})
    matrix = write_new(tmp_path / "matrix.json", {})
    monkeypatch.setattr(runner, "RUN_ROOT", new_root)
    monkeypatch.setattr(runner.scope, "PRIMARY_CURSOR", new_root / "cursor.json")
    monkeypatch.setattr(runner.scope, "INVENTORY_FILE", Path(inventory_ref["path"]))
    monkeypatch.setattr(runner.scope, "require_allowed", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(runner.policy, "BATCH_ROOT", tmp_path / "old-batch")
    monkeypatch.setattr(runner.policy, "PLAN_FILE", Path(plan["path"]))
    monkeypatch.setattr(runner.policy, "MATRIX_FILE", Path(matrix["path"]))
    monkeypatch.setattr(runner.policy, "COORDINATOR_RUN_ROOT", primary)
    monkeypatch.setattr(runner.base, "coordinator_limits", lambda: {})
    monkeypatch.setattr(runner.base, "diagnostic_qualifications", lambda: {})
    observed = []
    class Runtime(NoModels):
        def start_residents(self):
            cursor = json.loads((new_root / "cursor.json").read_bytes())
            assert cursor["qualifications"] == inventory["qualifications"] and cursor["active_generation"] == []
            observed.append("models_after_cursor")
        def exhausted(self, _):
            return False
    class Recorder:
        def __init__(self, *_):
            pass
        def import_original(self, *_args, **_kwargs):
            pass
        def flush(self, **_):
            pass
    def queue(_rows, **kwargs):
        assert kwargs["api_runtime"] is None
        kwargs["runtime"].start_residents()
        return {"generation": {}, "scores": {}, "deliveries": {}, "exceptions": [],
                "qualifications": inventory["qualifications"], "failure": None}
    monkeypatch.setattr(runner, "UnusedResidentRuntime", Runtime)
    monkeypatch.setattr(runner, "QwenUsageRecorder", Recorder)
    monkeypatch.setattr(runner, "recovery_function", lambda: (queue, {"fixture": True}))
    assert runner.run()["failure"] is None
    assert observed == ["models_after_cursor"]
    assert not (primary / "progress.json").exists()
