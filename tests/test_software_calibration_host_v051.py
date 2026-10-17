"""Finite controls for new CAL1 scheduling/usage seams; no GPU or real grading."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from scripts import software_calibration_v051 as host
from proworksim import software_calibration_runtime_v051 as runtime
from proworksim import software_calibration_scoring_v051 as scoring


def test_preselected_inventory_has_all_pairs_without_outcome_selection():
    cases = host.read_json(host.ASSETS / "sources/cal1-cases.json")
    rows = host.inventory(cases)
    assert len(rows) == 48
    assert sum(r["maximum_tokens"] for r in rows) == 3959768
    assert all(sum(r["worker"] == f"shard-{i}" for r in rows) == 12 for i in range(4))
    for i in range(24):
        pair = rows[2*i:2*i+2]
        assert {r["arm"] for r in pair} == {"reference", "project"}
        assert len({r["seed"] for r in pair}) == 1
    altered = [dict(c) for c in cases]
    altered[2]["seed_proposal"] += 1
    with pytest.raises(ValueError):
        host.inventory(altered)


def test_interrupted_call_preserves_uncertain_reservation(tmp_path):
    rows = [{"slot_id": str(i), "maximum_tokens": 99} for i in range(3)]
    host.write(tmp_path / "slots/0/generation.json", {"usage": {"total_tokens": 30}})
    host.write(tmp_path / "slots/1/started.json", {})
    receipt = host.ledger(tmp_path, rows)
    assert receipt["complete_generations"] == 1
    assert receipt["started_generations"] == 2
    assert receipt["known_actual_tokens"] == 30
    assert receipt["ledger_tokens"] == 129
    assert receipt["complete_actual_tokens"] is None
    assert receipt["outcomes"][2]["generation_complete"] is False


def fixture_worker(monkeypatch, tmp_path, *, corrupt_input=False, unknown=False):
    case = {"messages": [], "input_ids": [10], "rendered_prompt": "test", "evaluation_sample": {}}
    host.write(tmp_path / "cases.json", [case])
    rows = [{"worker": "shard-0", "slot_id": str(i), "ordinal": 0, "arm": arm, "seed": 51,
             "maximum_tokens": 20} for i, arm in enumerate(("reference", "project"))]
    plan = {"rows": rows, "native_python": sys.executable, "model_path": "never-loaded",
        "model_manifest": {"path": "never-loaded"}, "contract": host.CONTRACT,
        "cases": {"path": str(tmp_path / "cases.json")}, "scorer_source": "never-read"}
    host.write(tmp_path / "plan.json", {})
    monkeypatch.setattr(host, "frozen", lambda root: plan)
    res = SimpleNamespace(binding_from_env=lambda: {})
    startup = SimpleNamespace(acquire_startup_cache=lambda *a, **k: None, StartupResourceUnavailable=ValueError)
    monkeypatch.setattr(host, "resource_modules", lambda plan: (res, startup))
    observations = []

    class Owner:
        tokenizer = None
        def begin_window(self, name):
            observations.append(("begin", name))
        def select_path(self, name):
            observations.append(("arm", name))
        def reseed(self, seed, *, label):
            observations.append(("seed", seed))
        def generate_native(self, native):
            observations.append(("generate", native["input_ids"]))
            return {"usage": {"total_tokens": 10}, "raw_generated_text": "answer"}
        def verify_evaluation_guard(self):
            return {"passed": True}

    monkeypatch.setattr(runtime, "load_actor", lambda *a, **k: Owner())
    monkeypatch.setattr(runtime, "prepare_native_input", lambda *a, **k:
        {"input_ids": [11] if corrupt_input else [10], "rendered_prompt": "test"})
    def grade(raw, sample, *, run_root, **kwargs):
        reply = {"status": "technical_unknown" if unknown else "ok", "pass_at_1": None if unknown else 0}
        host.write(Path(run_root) / "result.json", reply)
        return reply
    monkeypatch.setattr(scoring, "score_cal1_candidate", grade)
    return observations


def test_worker_pairs_keep_failure_and_exactly_one_generation_per_arm(monkeypatch, tmp_path):
    seen = fixture_worker(monkeypatch, tmp_path)
    assert host.worker(tmp_path, "shard-0", tmp_path / "worker") == 0
    assert [x for x in seen if x[0] == "seed"] == [("seed", 51)] * 2
    assert len([x for x in seen if x[0] == "generate"]) == 2
    assert host.read_json(tmp_path / "worker/report.json")["status"] == "complete"
    assert host.read_json(tmp_path / "slots/0/grade/result.json")["pass_at_1"] == 0
    with pytest.raises(ValueError):
        host.worker(tmp_path, "shard-0", tmp_path / "worker")


def test_actual_input_mismatch_stops_before_generation(monkeypatch, tmp_path):
    seen = fixture_worker(monkeypatch, tmp_path, corrupt_input=True)
    with pytest.raises(ValueError, match="Actual native input"):
        host.worker(tmp_path, "shard-0", tmp_path / "worker")
    assert not any(x[0] == "generate" for x in seen)
    assert not (tmp_path / "slots/0/started.json").exists()


def test_grader_unknown_preserves_first_call_and_stops_next(monkeypatch, tmp_path):
    seen = fixture_worker(monkeypatch, tmp_path, unknown=True)
    host.worker(tmp_path, "shard-0", tmp_path / "worker")
    assert len([x for x in seen if x[0] == "generate"]) == 1
    assert (tmp_path / "pause.json").exists()
    assert (tmp_path / "slots/0/generation.json").exists()
    assert not (tmp_path / "slots/1").exists()
    assert host.read_json(tmp_path / "worker/report.json")["status"] == "paused_before_next_slot"


@pytest.mark.parametrize("first_resource_only", [True, False])
def test_supervisor_caps_pool_and_retries_only_documented_zero_model_resource(monkeypatch, tmp_path, first_resource_only):
    rows = host.inventory(host.read_json(host.ASSETS / "sources/cal1-cases.json"))
    plan = {"rows": rows, "gpu_preference": list(range(8)), "native_python": "unused",
            "runtime_dependency_path": "unused", "source_root": str(tmp_path)}
    host.write(tmp_path / "plan.json", {})
    monkeypatch.setattr(host, "frozen", lambda root: plan)
    cards = [{"index": i, "uuid": f"GPU-{i}", "free_mib": 60000} for i in range(4)]
    res = SimpleNamespace(available_cards=lambda p, s, excluded: [c for c in cards if c["index"] not in excluded],
                          launch_target=lambda c: c, worker_env=lambda env, binding: env)
    monkeypatch.setattr(host, "resource_modules", lambda plan: (res, None))
    monkeypatch.setattr(host, "target_resources", lambda *a, **k: {})
    monkeypatch.setattr(host, "worker_identity", lambda pid: {"start_ticks": 123, "alive": True})
    monkeypatch.setattr(host, "TelemetryGuard", lambda *a, **k: None)
    monkeypatch.setattr(host.signal, "signal", lambda *a: None)
    monkeypatch.setattr(host.time, "sleep", lambda t: None)
    launches, reported = [], set()

    class Process:
        def __init__(self, command, **kwargs):
            name = command[command.index("--worker") + 1]
            output = Path(command[command.index("--attempt") + 1])
            self.pid = 1000 + len(launches)
            launches.append(name)
            first = name == "shard-0" and name not in reported
            reported.add(name)
            if first:
                self.returncode = 75 if first_resource_only else 1
                reply = {"status": "pre_model_resource_unavailable", "model_loader_entered": False,
                         "generation_calls": 0} if first_resource_only else {"status": "fault"}
            else:
                self.returncode = 0
                own = [r for r in rows if r["worker"] == name]
                reply = {"status": "complete", "completed_slots": [r["slot_id"] for r in own],
                         "guard": {"passed": True}, "source_plan": host.ref(tmp_path / "plan.json")}
                for row in own:
                    host.write(tmp_path / "slots" / row["slot_id"] / "generation.json",
                               {"usage": {"total_tokens": row["prompt_tokens"] + 1}})
            host.write(output / "report.json", reply)
        def poll(self):
            return self.returncode

    monkeypatch.setattr(host.subprocess, "Popen", Process)
    result = host.supervise(tmp_path)
    assert launches[:4] == [f"shard-{i}" for i in range(4)]
    assert len(launches) == (5 if first_resource_only else 4)
    assert result["status"] == ("complete" if first_resource_only else "paused")
    assert result["ledger"]["complete_generations"] == (48 if first_resource_only else 36)
