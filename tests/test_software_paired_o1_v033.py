"""Finite CPU controls for the fixed paired diagnostic; no real GPU, worker or git."""
from contextlib import nullcontext
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import software_paired_o1_v033 as runner
from scripts.run_ne_v021 import write


def fixed_inventory():
    return [
        {"case_id": case, "sampling_seed": seed, "condition": condition,
         "team_decisions": 128, "team_tokens": 500000, "team_run_tests": 32}
        for case in ("api-consumer", "failure-repair")
        for seed in (0, 1)
        for condition in ("S", "T")
    ]


@pytest.fixture
def plan(monkeypatch):
    monkeypatch.setattr(runner, "inventory", fixed_inventory)
    return {
        "version": runner.VERSION, "candidates": list(runner.CANDIDATES),
        "inventories": {c: fixed_inventory() for c in runner.CANDIDATES},
        "limits": copy.deepcopy(runner.LIMITS), "gpu_preference": runner.GPU_ORDER,
        "frozen_development_episodes": 16, "optimizer_updates_allowed": False,
        "fresh_technical_quiz_calls": 0, "repeat_near_16k_stress": False,
        "automatic_retries": False, "automatic_successors": [],
        "automatic_model_replacement": False, "swe_rerun": False,
        "new_model_downloads": False, "old_results_reclassified": False,
        "next_stage_rule": copy.deepcopy(runner.NEXT_STAGE_RULE), "old_selected_candidate": None,
        "total_gpu_seconds": None, "worker_gpu_seconds": None,
        "queue_deadline_at": None, "wall_deadline_at": None,
        "source": {"code_commit": "cpu-fixture", "code_dirty": False},
        "prior_artifact_roots": [], "scope": "Explicit CPU fixture",
    }


def closed_rows(successes=()):
    return [
        {**slot, "status": "closed", "record_validity": True,
         "R": int(index in successes), "complete_delivery": index in successes,
         "content_correct": index in successes, "required_process_satisfied": index in successes}
        for index, slot in enumerate(fixed_inventory())
    ]


def complete_worker(plan):
    return {
        "status": "complete", "source_before": plan["source"], "source_after": plan["source"],
        "execution_binding_passed": True, "common_restored_exactly": True,
        "screening_optimizer_steps": 0,
    }


def put_results(root, plan, rows_by_candidate, states=None, worker_overrides=None):
    states = states or {c: {"status": "complete"} for c in runner.CANDIDATES}
    write(root / "supervisor.json", {"status": "complete", "states": states})
    for c, rows in rows_by_candidate.items():
        write(root / c / "actual/diagnostics/progress.json", rows)
        worker = complete_worker(plan)
        worker.update((worker_overrides or {}).get(c, {}))
        write(root / c / "actual/report.json", worker)


def test_exact_inventory_parallel_limit_and_no_quiz_no_automatic_successor(plan):
    assert runner.validate_plan(plan, check_files=False) is plan
    assert sum(map(len, plan["inventories"].values())) == 16
    assert plan["limits"]["max_parallel_model_instances"] == 2
    assert plan["fresh_technical_quiz_calls"] == 0
    assert not plan["repeat_near_16k_stress"]
    assert plan["automatic_successors"] == []


@pytest.mark.parametrize("key,value", [
    ("frozen_development_episodes", 32), ("optimizer_updates_allowed", True),
    ("fresh_technical_quiz_calls", 3), ("repeat_near_16k_stress", True),
    ("automatic_retries", True), ("automatic_successors", ["train"]),
    ("automatic_model_replacement", True), ("old_selected_candidate", "qwen3.5-9b"),
])
def test_protocol_drift_rejected(plan, key, value):
    plan[key] = value
    with pytest.raises(ValueError, match="16-episode"):
        runner.validate_plan(plan, check_files=False)


def test_missing_and_invalid_records_remain_unknown_and_never_support_candidate(tmp_path, plan):
    a, b = runner.CANDIDATES
    one = closed_rows((1,))[:2]
    one[0].update(record_validity=False, R=None, content_correct=None,
                  required_process_satisfied=None)
    put_results(tmp_path, plan, {a: one},
                states={a: {"status": "stopped"}, b: {"status": "not_started"}})
    value = runner.results(plan, tmp_path)
    assert value["next_stage"]["status"] == "pending"
    assert value["next_stage"]["support_collection_candidate"] is None
    assert all(pair["S"] is None and pair["T"] is None and pair["T_minus_S"] is None
               for pair in value["paired_outcomes"])
    assert value["candidate_results"][b]["conditions"]["T"]["known"] == 0
    assert value["candidate_results"][a]["conditions"]["S"]["known"] == 0
    assert value["outcomes"][b] == []


def test_only_complete_trusted_eight_with_team_success_proposes_fresh_support(tmp_path, plan):
    a, b = runner.CANDIDATES
    put_results(tmp_path, plan, {a: closed_rows((1,)), b: closed_rows((0, 2, 4, 6))})
    value = runner.results(plan, tmp_path)
    next_stage = value["next_stage"]
    assert next_stage["status"] == "fresh_support_candidate_identified"
    assert next_stage["support_collection_candidate"] == a
    assert next_stage["prior_v030_selected_candidate"] is None
    assert not next_stage["old_selection_reclassified"]
    assert not next_stage["automatic_execution"]
    assert not next_stage["development_records_are_training_support"]
    assert value["selected_candidate"] is None
    assert not value["allocation_experiment_started"]


@pytest.mark.parametrize("change", [
    {"execution_binding_passed": False}, {"common_restored_exactly": False},
    {"screening_optimizer_steps": 1}, {"status": "execution_error"},
])
def test_untrusted_worker_cannot_promote_team_success(tmp_path, plan, change):
    a, b = runner.CANDIDATES
    put_results(tmp_path, plan, {a: closed_rows((1,)), b: closed_rows()},
                worker_overrides={a: change})
    assert runner.results(plan, tmp_path)["next_stage"]["support_collection_candidate"] is None


def test_rank_team_then_joint_successes_and_all_zero_has_no_winner(tmp_path, plan):
    a, b = runner.CANDIDATES
    put_results(tmp_path, plan, {a: closed_rows((1, 3)), b: closed_rows((0, 1, 3))})
    assert runner.results(plan, tmp_path)["next_stage"]["support_collection_candidate"] == b
    put_results(tmp_path, plan, {a: closed_rows((1, 3)), b: closed_rows((0, 1))})
    assert runner.results(plan, tmp_path)["next_stage"]["support_collection_candidate"] == a
    put_results(tmp_path, plan, {a: closed_rows((0, 1)), b: closed_rows((0, 1))})
    assert runner.results(plan, tmp_path)["next_stage"]["support_collection_candidate"] == a
    put_results(tmp_path, plan, {a: closed_rows(), b: closed_rows()})
    value = runner.results(plan, tmp_path)
    assert value["next_stage"]["status"] == "no_local_team_carrier"
    assert value["next_stage"]["support_collection_candidate"] is None
    assert all(pair["pattern"] == "both_failed" for pair in value["paired_outcomes"])


def test_observed_inventory_cannot_append_or_change_slot(tmp_path, plan):
    expected = plan["inventories"][runner.CANDIDATES[0]]
    rows = closed_rows()
    rows[0]["condition"] = "T"
    write(tmp_path / "diagnostics/progress.json", rows)
    with pytest.raises(ValueError, match="paired result"):
        runner.observed_rows(tmp_path, expected)
    write(tmp_path / "diagnostics/progress.json", closed_rows() + [closed_rows()[0]])
    with pytest.raises(ValueError, match="More episodes"):
        runner.observed_rows(tmp_path, expected)


def test_two_mock_workers_start_and_one_failure_does_not_stop_the_other(tmp_path, monkeypatch, plan):
    root = tmp_path / "run"
    plan_path = tmp_path / "plan.json"
    write(plan_path, plan)
    monkeypatch.setattr(runner, "validate_plan", lambda value: value)
    monkeypatch.setattr(runner, "lock", lambda _: nullcontext())
    monkeypatch.setattr(runner, "artifact_bytes", lambda _: 0)
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**15))
    monkeypatch.setattr(runner, "resources", lambda: {})
    cards = [{"index": 4, "uuid": "cpu-gpu-4"}, {"index": 6, "uuid": "cpu-gpu-6"}]
    monkeypatch.setattr(runner, "available_cards",
                        lambda p, s, occupied=(): [c for c in cards if c["index"] not in occupied])
    monkeypatch.setattr(runner, "worker_identity", lambda pid: {"start_ticks": pid + 100})
    monkeypatch.setattr(runner, "target_resources", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner, "rss", lambda _: 0)
    monkeypatch.setattr(runner.original, "worker_env", lambda *args: {})
    monkeypatch.setattr(runner, "TelemetryGuard", lambda *args, **kwargs: SimpleNamespace(
        observe=lambda *args, **kwargs: {"stop_reason": None}))
    monkeypatch.setitem(runner.LIMITS, "gpu_capacity_stability_seconds", 0)
    monkeypatch.setitem(runner.LIMITS, "poll_seconds", 0)
    launched = []

    class FakeProcess:
        def __init__(self, candidate):
            self.candidate, self.returncode, self.polls = candidate, None, 0
            self.pid = 200 + len(launched)

        def poll(self):
            self.polls += 1
            if self.candidate == runner.CANDIDATES[0]:
                self.returncode = 1
            elif self.polls >= 4:
                self.returncode = 0
            return self.returncode

        def wait(self, timeout):
            assert self.returncode is not None
            return self.returncode

    def fake_popen(command, **kwargs):
        candidate = command[command.index("--candidate") + 1]
        output = Path(command[command.index("--output") + 1])
        if candidate == runner.CANDIDATES[1]:
            # The peer has already been launched and is still active at this point.
            assert len(launched) == 1 and launched[0].returncode is None
            write(output / "report.json", complete_worker(plan))
            write(output / "diagnostics/progress.json", closed_rows((1,)))
        process = FakeProcess(candidate)
        launched.append(process)
        return process

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)

    def forbidden_stop(*args, **kwargs):
        raise AssertionError("This CPU fixture must not signal any process")

    monkeypatch.setattr(runner.continuation, "_stop_worker", forbidden_stop)
    summary = runner.supervise(plan_path, root)
    a, b = runner.CANDIDATES
    assert len(launched) == 2
    assert summary["states"][a]["status"] == "stopped"
    assert summary["states"][a]["stop_reason"] == "worker_exit_error"
    assert summary["states"][b]["status"] == "complete"
    assert [summary["states"][c]["gpu"] for c in runner.CANDIDATES] == [4, 6]
    assert runner.results(plan, root)["next_stage"]["support_collection_candidate"] == b


def test_publication_only_stages_and_commits_the_two_fixed_reports(tmp_path, monkeypatch):
    root, repo = tmp_path / "run", tmp_path / "repo"
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0] != "git":
            write(root / "supervisor.json", {"status": "complete"})
        return SimpleNamespace(returncode=1 if command[:2] == ["git", "diff"] else 0,
                               stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(runner.subprocess, "check_output",
                        lambda command, **kwargs: "main\n" if command[1] == "branch" else "fixture-commit\n")
    monkeypatch.setattr(runner, "report", lambda *args: {})
    state = runner.finish(tmp_path / "plan.json", root, repo, publish=True)
    assert state["publish_status"] == "pushed"
    add = next(cmd for cmd in commands if cmd[:2] == ["git", "add"])
    commit = next(cmd for cmd in commands if cmd[:2] == ["git", "commit"])
    expected = ["docs/experiments/software-paired-o1-v033.md",
                "docs/experiments/software-paired-o1-v033.json"]
    assert add == ["git", "add", "--", *expected]
    assert "--only" in commit and commit[commit.index("--") + 1:] == expected
    assert state["report_commit"] == "fixture-commit"


def test_plain_and_sized_tensor_references_bind_original_bytes(tmp_path):
    path = tmp_path / "state.pt"
    path.write_bytes(b"explicit non-torch fixture")
    plain = runner.reference(path)
    sized = {**plain, "bytes": path.stat().st_size}
    assert runner.checked(plain) == path
    assert runner.checked(sized) == path
    for change in ({"bytes": True}, {"bytes": 1.0}, {"bytes": 0},
                   {"sha256": "changed"}, {"unvalidated_extra": True}):
        with pytest.raises(ValueError):
            runner.checked({**sized, **change})
    path.write_bytes(b"tampered fixture bytes")
    with pytest.raises(ValueError):
        runner.checked(sized)
