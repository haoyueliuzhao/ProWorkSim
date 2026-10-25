"""Environment rescoring preserves candidates and never promotes missing outcomes."""
import copy
import importlib.util
import os
from pathlib import Path

import pytest

from proworksim import software_benchmark_scorer_v058 as scorer
from proworksim.software_benchmark_candidates_v054 import write_new

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("requests_rescore_v058", ROOT / "tools/repair_ref_grading_environment_v058.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def fixture():
    rows, outcomes = [], []
    for index in range(16):
        slot = f"fixed-slot-{index}"
        task, condition = f"requests-{index // 4}", f"budget-{index % 4}"
        old, patch, native = {"old_request": slot}, {"patch": slot}, {"lock": slot}
        request, env, qual = {"new_request": slot}, {"environment": "one"}, {"qualification": "all-eight-passed"}
        rows.append({"slot": {"slot_id": slot, "instance_id": task, "condition_id": condition},
            "generation": {"status": "closed", "immutable_result": slot},
            "score": {"status": "official_report", "resolved": False,
                      "dispatched_request": old, "receipt": {"old_receipt": slot}}})
        receipt = {"slot_id": slot, "condition_id": condition, "scoring_recovery_of": old,
            "original_patch": patch, "native_candidate_lock": native,
            "environment_revision": env, "environment_qualification": qual,
            "status": "official_report", "resolved": index == 0,
            "model_calls": 0, "actor_feedback": False, "candidate_changed": False,
            "version": scorer.VERSION}
        outcomes.append({"slot_id": slot, "instance_id": task, "condition_id": condition,
            "known": True, "original_request": old, "request": request,
            "original_patch": patch, "native_candidate_lock": native,
            "environment_revision": env, "environment_qualification": qual,
            "receipt": receipt, "receipt_pointer": {"new_receipt": slot},
            "quiescence_reference": {"quiet": slot}, "completion": {"completed": slot},
            "quiescence": {"slot_id": slot, "condition_id": condition,
                           "quiescent": True, "cleanup_errors": [], "create_result_unknown": False,
                           "environment_revision": env, "environment_qualification": qual}})
    state = {"rows": rows, "complete": True, "binding": "unchanged", "deferred": ["historical-unknown"]}
    return state, {row["slot"]["slot_id"] for row in rows}, outcomes


def test_known_rescore_preserves_every_generation_and_old_score():
    state, allowed, outcomes = fixture()
    saved = copy.deepcopy(state)
    value, changed, pending = repair.reconciled_state(state, copy.deepcopy(state), allowed, outcomes)
    assert state == saved and len(changed) == 16 and not pending
    assert sum(row["score"]["resolved"] for row in value["rows"]) == 1
    for before, after in zip(state["rows"], value["rows"], strict=True):
        assert after["generation"] == before["generation"] and after["slot"] == before["slot"]
        assert after["prior_scoring_attempts"] == [before["score"]]
    assert value["deferred"] == state["deferred"] and value["binding"] == state["binding"]


def test_uncertain_new_scoring_keeps_old_determinate_score_and_marks_review():
    state, allowed, outcomes = fixture()
    outcomes[0]["receipt"].update(status="technical_unknown", resolved=None)
    value, changed, pending = repair.reconciled_state(state, copy.deepcopy(state), allowed, outcomes)
    assert len(changed) == 15 and pending == ["fixed-slot-0"]
    assert value["rows"][0]["score"] == state["rows"][0]["score"]
    assert value["rows"][0]["environment_review"]["old_score_not_confirmed_in_repaired_environment"] is True
    assert not any(row["score"]["resolved"] for row in value["rows"])


def test_wrong_candidate_or_condition_and_missing_panel_are_rejected():
    state, allowed, outcomes = fixture()
    for field, wrong in (("native_candidate_lock", {"another": "candidate"}), ("condition_id", "another-budget")):
        altered = copy.deepcopy(outcomes)
        altered[0]["receipt"][field] = wrong
        with pytest.raises(ValueError, match="Receipt does not bind"):
            repair.reconciled_state(state, copy.deepcopy(state), allowed, altered)
    with pytest.raises(ValueError, match="Every one"):
        repair.reconciled_state(state, copy.deepcopy(state), allowed, outcomes[:-1])


def test_scorer_preserves_original_candidate_and_requires_same_qualified_environment(tmp_path, monkeypatch):
    cpus = ",".join(map(str, sorted(os.sched_getaffinity(0))[:4]))
    old = {"instance_id": "psf__requests-2931", "patch": {"old_patch": True},
        "native_candidate_lock": {"old_lock": True}, "scorer_manifest": {},
        "trusted_output_root": "old-root", "receipt_output": "old-receipt",
        "quiescence_output": "old-quiet", "scoring_cpuset_cpus": cpus,
        "slot_id": "fixed", "condition_id": "REF_B5000K", "actor_feedback": False}
    manifest = {"new_manifest": True}
    request = old | {"scoring_recovery_of": write_new(tmp_path / "old.json", old),
        "scorer_manifest": write_new(tmp_path / "manifest.json", manifest),
        "trusted_output_root": "new-root", "receipt_output": "new-receipt",
        "quiescence_output": "new-quiet", "environment_revision": {"env": "qualified"},
        "environment_qualification": {"qual": "all-eight"}}
    seen = []
    monkeypatch.setattr(scorer.predecessor, "validate_request", lambda original: seen.append(original))
    monkeypatch.setattr(scorer, "installation_manifest", lambda: manifest)
    monkeypatch.setattr(scorer.qualification, "validate_qualification", lambda *_: {
        "environment_revision": {"env": "qualified"}})
    scorer.validate_request(request)
    assert seen == [old]
    with pytest.raises(ValueError, match="only the qualified"):
        scorer.validate_request(request | {"patch": {"different": True}})
    with pytest.raises(ValueError, match="task-specific control qualification"):
        scorer.validate_request(request | {"environment_revision": {"env": "unqualified"}})



def test_partial_admission_keeps_all_sixteen_candidates_and_unknowns():
    state, allowed, outcomes = fixture()
    before = copy.deepcopy(state)
    for outcome in outcomes[8:]:
        outcome.update(known=False, request=None, environment_revision=None,
                       environment_qualification=None,
                       error={"type": "TaskNotQualified", "message": "known TLS blocker"})
    merged, changed, pending = repair.reconciled_state(state, copy.deepcopy(state), allowed, outcomes)
    assert len(merged["rows"]) == 16 and len(changed) == 8 and len(pending) == 8
    assert state == before
    for old, new in zip(before["rows"][8:], merged["rows"][8:], strict=True):
        assert new["score"] == old["score"] and new["generation"] == old["generation"]
        assert new["environment_review"]["status"] == "unresolved"
    outcomes[0]["quiescence"]["environment_revision"] = {"wrong": "environment"}
    _, changed, pending = repair.reconciled_state(state, copy.deepcopy(state), allowed, outcomes)
    assert len(changed) == 7 and len(pending) == 9


def test_task_admission_does_not_depend_on_other_tasks(monkeypatch):
    tasks = tuple(repair.environment.PROFILES)
    summary = {"tasks": {task: {"status": "qualified", "qualification": {"task": task}} for task in tasks}}
    originals = [{"instance_id": task} for task in tasks for _ in range(4)]
    calls = []

    def validate(ref, original):
        calls.append(original["instance_id"])
        if original["instance_id"] == "psf__requests-2931":
            raise ValueError("failed gold control")
        return {"environment_revision": {"fixed": True}}

    monkeypatch.setattr(repair.qualification, "validate_qualification", validate)
    result = repair.task_qualifications(summary, originals)
    assert result["psf__requests-5414"]["status"] == "qualified"
    assert all(result[t]["status"] == "not_qualified" for t in tasks if t != "psf__requests-5414")
    assert "psf__requests-1766" not in calls and "psf__requests-1921" not in calls


def test_v058_hold_precedes_all_resource_calls(tmp_path, monkeypatch):
    import subprocess
    from proworksim import software_benchmark_shared_server_hold_v057 as hold
    from proworksim import software_benchmark_grading_environment_v058 as environment
    spec = importlib.util.spec_from_file_location("requests_admission_v058", ROOT / "tools/check_ref_grading_environment_v058.py")
    admission = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(admission)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(args)
        pytest.fail("Resource operation during hold")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    operations = [
        lambda: environment.EnvironmentContainers.create(object.__new__(environment.EnvironmentContainers)),
        lambda: environment.EnvironmentContainer.start(object.__new__(environment.EnvironmentContainer)),
        lambda: scorer.score_request({}),
        lambda: admission.prepare(tmp_path / "admission"),
        lambda: admission.worker({}, 0),
        lambda: admission.run_one(tmp_path, {}, 0),
        lambda: admission.execute(tmp_path / "admission"),
        lambda: repair.prepare(tmp_path / "rescore", None),
        lambda: repair.run_one({}, {}),
        lambda: repair.run(tmp_path / "rescore"),
        lambda: repair.reconcile(tmp_path / "rescore"),
    ]
    for operation in operations:
        with pytest.raises(hold.SharedServerHold):
            operation()
    assert calls == [] and list(tmp_path.iterdir()) == []


def test_unresolved_environment_is_unknown_in_actual_budget_analysis(tmp_path, capsys):
    import json

    state, allowed, outcomes = fixture()
    for outcome in outcomes[8:]:
        outcome.update(known=False, request=None)
    merged, _, _ = repair.reconciled_state(state, copy.deepcopy(state), allowed, outcomes)
    original = copy.deepcopy(merged)
    measured = repair.measurement_state(merged)
    budgets = ("REF_B0500K", "REF_B2000K", "REF_B5000K", "REF_B10000K")
    for index, row in enumerate(measured["rows"]):
        row["slot"].update(condition_id=budgets[index % 4], repo="synthetic/repo", seed=1,
                           input_plus_output_tokens=500000)
    source = tmp_path / "measurement.json"
    source.write_text(json.dumps(measured))
    spec = importlib.util.spec_from_file_location("budget_analysis_control", ROOT / "tools/analyze_ref_budget_results_v056.py")
    analyzer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyzer)
    analyzer.analyze(source, tmp_path / "analysis")
    summary = json.loads((tmp_path / "analysis/summary.json").read_text())
    assert all(group["planned"] == 4 and group["unknown_or_pending_code_results"] == 2
               for group in summary["groups"].values())
    assert summary["groups"][budgets[0]]["code_result_bounds"] == [0.25, 0.75]
    assert merged == original
    capsys.readouterr()


def test_admission_lane_error_and_disabled_task_do_not_stop_sibling(tmp_path, monkeypatch):
    from contextlib import nullcontext
    import json
    import subprocess
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location("admission_lane_control", ROOT / "tools/check_ref_grading_environment_v058.py")
    admission = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(admission)
    rows = [{"instance_id": task, "patch_kind": kind, "lane": i % 2,
             "directory": str(tmp_path / str(i))}
            for i, (task, kind) in enumerate((t, k) for t in admission.TASKS for k in ("gold", "empty"))]
    plan = {"rows": rows}
    calls, collected = [], []

    def run_one(root, plan, index):
        calls.append(index)
        if index == 0:
            raise OSError("synthetic lane failure")
        row = rows[index]
        if not admission.environment.PROFILES[row["instance_id"]]["admission_enabled"]:
            return {"status": "blocked_environment"}
        folder = Path(row["directory"])
        folder.mkdir()
        (folder / "quiescence.json").write_text(json.dumps({"quiescent": True, "cleanup_errors": []}))
        return {"returncode": 0}

    original_read_text = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda path, *a, **k:
                        "MemAvailable: 1000000000 kB\n" if str(path) == "/proc/meminfo"
                        else original_read_text(path, *a, **k))
    monkeypatch.setattr(admission, "require_experiment_dispatch_allowed", lambda _: None)
    monkeypatch.setattr(admission, "prepare", lambda _: plan)
    monkeypatch.setattr(admission, "run_one", run_one)
    monkeypatch.setattr(admission.queue, "lock", lambda _: nullcontext())
    monkeypatch.setattr(admission.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**15))
    monkeypatch.setattr(admission, "collect_qualifications", lambda _: collected.append(True))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Unexpected process"))
    result = admission.execute(tmp_path)
    assert 5 in calls and 3 in calls and 7 in calls and collected == [True]
    assert any(r.get("lane") == 0 and r["status"] == "technical_unknown" for r in result["results"])
