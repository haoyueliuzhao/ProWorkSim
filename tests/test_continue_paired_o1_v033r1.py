"""Finite recovery controls: reuse old records, resume only unseen slots, no real worker."""
from contextlib import nullcontext
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import continue_paired_o1_v033r1 as runner
from scripts.run_ne_v021 import reference, write


@pytest.fixture
def plan(tmp_path):
    slots = runner.inventory()
    value = {
        "version": runner.VERSION, "source": {"code_commit": "cpu-fixture", "code_dirty": False},
        "candidates": list(runner.CANDIDATES), "inventories": {c: slots for c in runner.CANDIDATES},
        "remaining_inventories": {c: slots[2:] for c in runner.CANDIDATES},
        "completed_slot_ids": {c: [row["slot_id"] for row in slots[:2]] for c in runner.CANDIDATES},
        "limits": copy.deepcopy(runner.LIMITS), "gpu_preference": list(runner.GPU_ORDER),
        "frozen_development_episodes": 16, "reused_completed_episodes": 4, "new_sampling_episodes": 12,
        "optimizer_updates_allowed": False, "fresh_technical_quiz_calls": 0, "repeat_near_16k_stress": False,
        "automatic_retries": False, "automatic_successors": [], "automatic_model_replacement": False,
        "total_gpu_seconds": None, "worker_gpu_seconds": None, "queue_deadline_at": None, "wall_deadline_at": None,
        "next_stage_rule": copy.deepcopy(runner.NEXT_STAGE_RULE), "old_selected_candidate": None,
        "old_results_reclassified": False, "historical_v030_v032_results_reclassified": False,
        "v033_record_validity_reinterpreted": True, "business_assessments_regraded": False,
        "swe_rerun": False, "new_model_downloads": False,
        "original_execution_stop_preserved": True, "resample_completed_slots": False,
        "scope": "explicit CPU fixture", "prior_artifact_roots": [],
    }
    old = tmp_path / "old"
    write(old / "plan.json", {"cpu_fixture": True})
    old_states = {c: {"status": "stopped", "attempted": True, "started_at": 0, "ended_at": 10,
                      "gpu": index, "elapsed_gpu_seconds": 10, "pid": 100 + index}
                  for index, c in enumerate(runner.CANDIDATES)}
    write(old / "supervisor.json", {"worker_gpu_seconds": 20, "states": old_states})
    value["original"] = {"plan": reference(old / "plan.json"),
                         "supervisor": reference(old / "supervisor.json"), "candidates": {}}
    recovered = {"candidates": {}}
    for c in runner.CANDIDATES:
        rows = closed_rows(slots[:2])
        write(old / c / "progress.json", rows)
        value["original"]["candidates"][c] = {"progress": reference(old / c / "progress.json")}
        recovered["candidates"][c] = {"rows": rows}
    write(tmp_path / "recovery.json", recovered)
    value["record_recovery"] = reference(tmp_path / "recovery.json")
    return value


def closed_rows(slots, successes=()):
    return [{**slot, "status": "closed", "record_validity": True, "R": int(index in successes),
             "content_correct": index in successes, "required_process_satisfied": index in successes,
             "submitted": True, "complete_delivery": index in successes,
             "team_budget": {"model": {"decisions": 4, "attempts": 3, "charged_tokens": 50,
                                        "held_tokens": 0, "records": {"do_not_publish": "x" * 10000}},
                             "tests": {"used": 1}},
             "boundary": {"outcomes": [{"large_source": "x" * 10000}]}}
            for index, slot in enumerate(slots)]


def write_results(root, plan, rows, *, states=None, overrides=None):
    states = states or {c: {"status": "complete", "attempted": True, "started_at": 20, "ended_at": 30,
                           "gpu": index, "elapsed_gpu_seconds": 10}
                       for index, c in enumerate(runner.CANDIDATES)}
    write(root / "plan.json", plan)
    write(root / "supervisor.json", {"status": "complete", "states": states, "running_gpu_seconds": 0})
    for candidate, items in rows.items():
        actual = root / candidate / "actual"
        write(actual / "diagnostics/progress.json", items)
        worker = {"status": "complete", "execution_binding_passed": True, "common_restored_exactly": True,
                  "screening_optimizer_steps": 0, "diagnostic_optimizer_steps": 0,
                  "source_before": plan["source"], "source_after": plan["source"]}
        worker.update((overrides or {}).get(candidate, {}))
        write(actual / "report.json", worker)


def test_frozen_plan_requires_four_reused_and_twelve_unstarted_slots(plan):
    assert runner.validate_plan(plan, check_files=False) is plan
    assert sum(map(len, plan["remaining_inventories"].values())) == 12
    for key, changed in (("new_sampling_episodes", 16), ("resample_completed_slots", True),
                         ("automatic_retries", True), ("fresh_technical_quiz_calls", 1),
                         ("original_execution_stop_preserved", False)):
        mutated = {**plan, key: changed}
        with pytest.raises(ValueError, match="twelve unstarted"):
            runner.validate_plan(mutated, check_files=False)
    mutated = copy.deepcopy(plan)
    mutated["remaining_inventories"][runner.CANDIDATES[0]] = runner.inventory()[:6]
    with pytest.raises(ValueError):
        runner.validate_plan(mutated, check_files=False)


def test_prepared_slot_is_not_execution_but_episode_transport_and_sdk_events_block(tmp_path):
    slot = runner.inventory()[2]
    folder = tmp_path / "diagnostics/slot-2"
    write(folder / "preparation.json", {"prepared": True})
    base = folder / "sdk-conversations/member_a/conversations/id/base_state.json"
    write(base, {"execution_status": "idle", "head_is_empty": False, "agent_state": {}, "stats": {"usage_to_metrics": {}}})
    first = runner.unstarted_slot_proof(tmp_path, [slot])
    assert first[0]["episode_started"] is False
    for name in ("episode/manifest.json", "raw-transport/call-1.json", "sdk-conversations/events/event.json"):
        path = folder / name
        write(path, {"started": True})
        with pytest.raises(ValueError, match="execution evidence"):
            runner.unstarted_slot_proof(tmp_path, [slot])
        path.unlink()
        path.parent.rmdir()
    write(base, {"execution_status": "idle", "head_is_empty": False, "agent_state": {},
                 "stats": {"usage_to_metrics": {"tokens": 1}}})
    with pytest.raises(ValueError, match="usage"):
        runner.unstarted_slot_proof(tmp_path, [slot])


def test_merge_keeps_known_side_when_peer_unknown_and_does_not_take_all_zero_branch(tmp_path, plan):
    a, b = runner.CANDIDATES
    rows = closed_rows(plan["remaining_inventories"][a])[:2]
    rows[1].update(status="execution_unknown", record_validity=None, R=None, complete_delivery=None)
    states = {c: {"status": "stopped", "attempted": False} for c in runner.CANDIDATES}
    write_results(tmp_path, plan, {a: rows}, states=states)
    value = runner.results(plan, tmp_path)
    pair = next(p for p in value["paired_outcomes"] if p["candidate_id"] == a
                and p["case_id"] == rows[0]["case_id"] and p["sampling_seed"] == rows[0]["sampling_seed"])
    assert (pair["S"], pair["T"], pair["T_minus_S"]) == (0, None, None)
    assert value["next_stage"]["status"] == "technical_unknown_no_carrier_decision"
    assert not value["next_stage"]["all_team_zero_branch_applied"]
    assert len(value["outcomes"][b]) == 8
    assert all(row["R"] is None for row in value["outcomes"][b][2:])
    assert value["sampling_summary"]["offline_recovered_original_v033"]["rows_observed"] == 4
    assert value["sampling_summary"]["new_v033r1"]["rows_observed"] == 2


def test_peer_failure_does_not_block_complete_local_carrier_and_report_stays_compact(tmp_path, plan):
    a, b = runner.CANDIDATES
    rows = closed_rows(plan["remaining_inventories"][a], successes=(1,))
    states = {a: {"status": "complete", "attempted": True, "gpu": 0, "started_at": 20,
                  "ended_at": 30, "elapsed_gpu_seconds": 10},
              b: {"status": "stopped", "attempted": False}}
    write_results(tmp_path, plan, {a: rows}, states=states)
    value = runner.report(tmp_path, tmp_path / "published")
    assert value["next_stage"]["support_collection_candidate"] == a
    assert value["selected_candidate"] is None
    assert value["original_execution_status"] == "ended_with_execution_stop"
    assert not value["next_stage"]["development_records_are_training_support"]
    assert all(row["evidence_origin"] == "offline_recovered_original_v033"
               for row in value["outcomes"][a][:2])
    text = json.dumps(value)
    assert "do_not_publish" not in text and "large_source" not in text
    assert len(text) < 60000
    assert value["cost"]["original_worker_gpu_seconds"] == 20
    assert value["cost"]["new_distinct_worker_gpu_seconds"] == 10
    assert value["cost"]["interval_unions"]["original_new_overlap"]["gpu_seconds"] == 0
    assert value["cost"]["interval_unions"]["combined_worker_union"]["gpu_seconds"] == 30


def test_all_known_zero_can_use_predeclared_research_branch_and_overlap_is_deduplicated(tmp_path, plan):
    rows = {c: closed_rows(plan["remaining_inventories"][c]) for c in runner.CANDIDATES}
    states = {c: {"status": "complete", "attempted": True, "gpu": index,
                  "started_at": 5, "ended_at": 15, "elapsed_gpu_seconds": 10}
              for index, c in enumerate(runner.CANDIDATES)}
    write_results(tmp_path, plan, rows, states=states)
    value = runner.results(plan, tmp_path)
    assert value["next_stage"]["status"] == "no_local_team_carrier"
    assert value["next_stage"]["all_team_zero_branch_applied"]
    assert value["cost"]["interval_unions"]["original_new_overlap"]["gpu_seconds"] == 10
    assert value["cost"]["interval_unions"]["combined_worker_union"]["gpu_seconds"] == 30


@pytest.mark.parametrize("candidate", runner.CANDIDATES)
def test_worker_restores_same_common_and_collects_only_six_unstarted_slots(tmp_path, monkeypatch, plan, candidate):
    from proworksim import deterministic_work_v024, online_training, software_learning_v029, software_runtime_v033

    owner_root = tmp_path / "owner"
    manifest = owner_root / "manifest.json"
    write(manifest, {"fixture": True})
    common = {"state_tensor_digest": "cpu-tensors", "actor_identity": {"identity": candidate}}
    write(owner_root / "common/checkpoint.json", common)
    steps = 3 if candidate == runner.CANDIDATES[0] else 0
    profile = {"name": candidate}
    base_identity = {"path": "/cpu-fixture-model", "manifest": reference(manifest)}
    saved = {"recipe": {"seed": 1}, "inference_profile": profile, "base_identity": base_identity}
    write(owner_root / "owner.json", saved)
    loading = {"model": "/cpu-fixture-model", "manifest": reference(manifest), "runtime_profile": profile}
    write(owner_root / "loading.json", loading)
    write(owner_root / "old-plan.json", {"prior_model_plan": reference(owner_root / "loading.json"),
                                          "candidate_profiles": {candidate: profile}})
    plan["parents"] = {candidate: {"references": {
        "owner": reference(owner_root / "owner.json"), "plan": reference(owner_root / "old-plan.json"),
        "common": reference(owner_root / "common/checkpoint.json"), "base_manifest": reference(manifest)},
        "common_steps": steps}}
    write(tmp_path / "plan.json", plan)
    owner = SimpleNamespace(
        inference_profile=profile, base_identity=base_identity, actor_steps=steps, critic_steps=steps,
        torch=None, _state_bundle=lambda: {}, freeze_identity=lambda: common["actor_identity"],
        _make_identity=lambda: common["actor_identity"], restore_checkpoint=lambda path: common,
    )
    monkeypatch.setattr(deterministic_work_v024.DeterministicCandidateActor, "from_candidate",
                        lambda *args, **kwargs: owner)
    monkeypatch.setattr(runner.dense, "load_owner", lambda *args, **kwargs: owner)
    monkeypatch.setattr(online_training, "tensor_tree_digest", lambda *args: "cpu-tensors")
    monkeypatch.setattr(software_learning_v029, "migrate_software_owner", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner, "validate_plan", lambda value: value)
    monkeypatch.setattr(runner, "code_identity", lambda: plan["source"])
    monkeypatch.setattr(runner, "resources", lambda: {})
    monkeypatch.setattr(runner, "available_cards", lambda *args: [{"index": 4}])
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "4")
    collected = []

    def fake_collect(actual_owner, spec, output, worker_output, *, common_dir, on_slot, completed_slot_ids):
        assert actual_owner is owner
        assert completed_slot_ids == tuple(plan["completed_slot_ids"][candidate])
        assert Path(common_dir) == owner_root / "common"
        assert spec["window_id"] == "v033r1-" + candidate
        rows = closed_rows(plan["remaining_inventories"][candidate])
        write(Path(output) / "progress.json", rows)
        collected.extend(row["slot_id"] for row in rows)
        return [None] * 6

    monkeypatch.setattr(software_runtime_v033, "collect", fake_collect)
    value = runner.run_worker(tmp_path / "plan.json", candidate, tmp_path / "new-actual")
    assert value["status"] == "complete"
    assert value["common_restored_exactly"] is True
    assert len(value["rows"]) == 6
    assert not set(collected) & set(plan["completed_slot_ids"][candidate])
    assert value["screening_optimizer_steps"] == value["diagnostic_optimizer_steps"] == 0
    assert value["fresh_technical_quiz_calls"] == 0
    assert value["actor_steps"] == value["critic_steps"] == steps


def test_new_supervisor_uses_new_worker_module_and_surviving_peer_continues(tmp_path, monkeypatch, plan):
    root = tmp_path / "run"
    path = tmp_path / "plan.json"
    write(path, plan)
    monkeypatch.setattr(runner, "validate_plan", lambda value: value)
    monkeypatch.setattr(runner, "results", lambda *args: {"next_stage": {"cpu_fixture": True}})
    monkeypatch.setattr(runner, "lock", lambda _: nullcontext())
    monkeypatch.setattr(runner, "artifact_bytes", lambda _: 0)
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**15))
    monkeypatch.setattr(runner, "resources", lambda: {})
    cards = [{"index": 0, "uuid": "cpu-gpu-0"}, {"index": 1, "uuid": "cpu-gpu-1"}]
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
        assert command[command.index("-m") + 1] == "scripts.continue_paired_o1_v033r1"
        candidate = command[command.index("--candidate") + 1]
        if candidate == runner.CANDIDATES[1]:
            assert len(launched) == 1 and launched[0].returncode is None
            write(Path(command[command.index("--output") + 1]) / "report.json",
                  {"status": "complete", "source_before": plan["source"], "source_after": plan["source"]})
        process = FakeProcess(candidate)
        launched.append(process)
        return process

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)

    def forbidden_stop(*args, **kwargs):
        raise AssertionError("No actual process signals are allowed in this fixture")

    monkeypatch.setattr(runner.continuation, "_stop_worker", forbidden_stop)
    value = runner.supervise(path, root)
    assert len(launched) == 2
    assert value["states"][runner.CANDIDATES[0]]["status"] == "stopped"
    assert value["states"][runner.CANDIDATES[1]]["status"] == "complete"


def test_publication_is_limited_to_new_two_report_paths(tmp_path, monkeypatch):
    root, commands = tmp_path / "run", []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0] != "git":
            assert command[command.index("-m") + 1] == "scripts.continue_paired_o1_v033r1"
            write(root / "supervisor.json", {"status": "complete"})
        return SimpleNamespace(returncode=1 if command[:2] == ["git", "diff"] else 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(runner.subprocess, "check_output",
                        lambda command, **kwargs: "main\n" if command[1] == "branch" else "fixture-commit\n")
    monkeypatch.setattr(runner, "report", lambda *args: {})
    value = runner.finish(tmp_path / "plan.json", root, tmp_path / "repo", publish=True)
    assert value["publish_status"] == "pushed"
    add = next(command for command in commands if command[:2] == ["git", "add"])
    commit = next(command for command in commands if command[:2] == ["git", "commit"])
    assert add == ["git", "add", "--", *runner.REPORT_PATHS]
    assert all("recovery" in path for path in runner.REPORT_PATHS)
    assert "--only" in commit and commit[commit.index("--") + 1:] == runner.REPORT_PATHS


def test_recovered_prefix_binds_original_assessment_guard_and_zero_generation(tmp_path):
    old_plan = {"inventories": {c: runner.inventory() for c in runner.CANDIDATES}}
    recovery = {"status": "recovered", "passed": True, "source_root": str(tmp_path),
                "model_calls": 0, "optimizer_steps": 0, "acceptance_executions": 0, "new_episodes": 0,
                "old_artifacts_unchanged": True,
                "candidates": {}}
    for candidate in runner.CANDIDATES:
        rows = []
        for index, slot in enumerate(runner.inventory()[:2]):
            folder = tmp_path / candidate / "actual/diagnostics" / f"slot-{index}"
            assessment = {"R": 0, "content_correct": False, "required_process_satisfied": False,
                          "submitted": True, "complete_delivery": False}
            write(folder / "assessment.json", assessment)
            write(folder / "evaluation-guard.json", {key: True for key in runner.GUARD_KEYS})
            write(folder / "recovered-entry.json", {"slot_id": slot["slot_id"],
                "reward": {"eligible": True, "reward": 0,
                           "source_assessment_sha256": reference(folder / "assessment.json")["sha256"]}})
            rows.append({**slot, **assessment, "status": "closed", "record_validity": True,
                         "assessment": reference(folder / "assessment.json"),
                         "evaluation_guard": reference(folder / "evaluation-guard.json"),
                         "entry": reference(folder / "recovered-entry.json")})
        recovery["candidates"][candidate] = {"status": "recovered", "rows": rows,
            "completed_slot_ids": [row["slot_id"] for row in rows]}
    assert runner.validate_recovered_rows(recovery, old_plan, tmp_path) is recovery
    mutated = copy.deepcopy(recovery)
    mutated["model_calls"] = 1
    with pytest.raises(ValueError, match="zero-generation"):
        runner.validate_recovered_rows(mutated, old_plan, tmp_path)
    mutated = copy.deepcopy(recovery)
    mutated["candidates"][runner.CANDIDATES[0]]["rows"][1]["R"] = 1
    with pytest.raises(ValueError, match="without regrading"):
        runner.validate_recovered_rows(mutated, old_plan, tmp_path)
    # Even identical contents from a new assessment file cannot replace the original source.
    mutated = copy.deepcopy(recovery)
    row = mutated["candidates"][runner.CANDIDATES[0]]["rows"][1]
    replacement = tmp_path / "new-assessment.json"
    replacement.write_bytes(Path(row["assessment"]["path"]).read_bytes())
    row["assessment"] = reference(replacement)
    with pytest.raises(ValueError, match="original immutable"):
        runner.validate_recovered_rows(mutated, old_plan, tmp_path)


def test_pending_is_normal_continuation_not_a_technical_fault(tmp_path, plan):
    states = {c: {"status": "not_started", "attempted": False} for c in runner.CANDIDATES}
    write_results(tmp_path, plan, {}, states=states)
    value = runner.results(plan, tmp_path)
    assert value["next_stage"]["status"] == "pending"
    assert value["next_stage"]["required_next_design"].startswith("Continue the fixed remaining slots")


def test_controller_failure_closes_unstarted_candidates_as_unknown_not_pending(tmp_path, monkeypatch, plan):
    path, root = tmp_path / "plan.json", tmp_path / "interrupted"
    write(path, plan)
    monkeypatch.setattr(runner, "validate_plan", lambda value: value)
    monkeypatch.setattr(runner, "lock", lambda _: nullcontext())
    monkeypatch.setattr(runner, "artifact_bytes", lambda _: 0)
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**15))

    def broken_observation():
        raise RuntimeError("explicit CPU observer failure")

    monkeypatch.setattr(runner, "resources", broken_observation)
    with pytest.raises(RuntimeError, match="observer failure"):
        runner.supervise(path, root)
    value = runner.results(plan, root)
    assert value["status"] == "interrupted"
    assert value["next_stage"]["status"] == "technical_unknown_no_carrier_decision"
    assert not value["next_stage"]["all_team_zero_branch_applied"]
    assert all(row["R"] is None for rows in value["outcomes"].values() for row in rows[2:])
