"""Only new v034 inventory, carrier and collection controls; no controller rerun."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from scripts import software_local_feasibility_v034 as runner
from scripts.run_ne_v021 import reference, write


def slots():
    return [
        {"slot_id": f"p1-{seed}-{kind}-T", "case_id": case, "condition": "T",
         "sampling_seed": 202610060701 + seed, "first_member": "member_a" if seed == 0 else "member_b",
         "role_decision_limits": {"member_a": 128, "member_b": 128},
         "team_limits": copy.deepcopy(runner.TEAM_LIMITS)}
        for seed, kind, case in ((0, "directory", "mm-directory-rootgoal-v034"),
                                 (0, "names", "mm-name-index-rootgoal-v034"),
                                 (1, "names", "mm-name-index-rootgoal-v034"),
                                 (1, "directory", "mm-directory-rootgoal-v034"))
    ]


@pytest.fixture
def plan(monkeypatch):
    monkeypatch.setattr(runner, "inventory", slots)
    return {
        "version": runner.VERSION, "source": {"code_commit": "cpu-fixture", "code_dirty": False},
        "candidates": list(runner.CANDIDATES), "inventories": {c: slots() for c in runner.CANDIDATES},
        "limits": copy.deepcopy(runner.LIMITS), "gpu_preference": list(runner.GPU_ORDER),
        "team_limits": copy.deepcopy(runner.TEAM_LIMITS), "generation_limits": copy.deepcopy(runner.GENERATION_LIMITS),
        "frozen_development_episodes": 8, "episodes_per_model": 4, "conditions": ["T"],
        "phases": copy.deepcopy(runner.PHASES), "next_stage_rule": copy.deepcopy(runner.NEXT_STAGE_RULE),
        "optimizer_updates_allowed": False, "fresh_technical_quiz_calls": 0, "repeat_near_16k_stress": False,
        "automatic_retries": False, "automatic_successors": [], "automatic_unfrozen_successors": False,
        "automatic_model_replacement": False, "resample_v033_slots": False, "repeat_S_conditions": False,
        "historical_results_reclassified": False, "old_selected_candidate": None,
        "historical_gpu_costs_included_as_new": False, "swe_rerun": False, "new_model_downloads": False,
        "total_gpu_seconds": None, "worker_gpu_seconds": None, "queue_deadline_at": None, "wall_deadline_at": None,
        "qualification": {"path": "/cpu-fixture", "sha256": "fixture"},
        "presentation": {"version": "software-context-v0.34", "behavior_distribution_preserved": False},
        "parents": {c: {"common_steps": 3 if index == 0 else 0,
                        "common_actor_identity": {"candidate": c}} for index, c in enumerate(runner.CANDIDATES)},
        "scope": "Explicit CPU fixture",
    }


def raw_rows(successes=(), tokens=(100, 100, 100, 100)):
    return [{**slot, "status": "closed", "record_validity": True,
             "R": int(index in successes), "complete_delivery": index in successes,
             "submitted": index in successes, "content_correct": True if index in successes else None,
             "required_process_satisfied": True if index in successes else None,
             "process_observation_complete": True if index in successes else None,
             "team_budget": {"model": {"decisions": 1, "attempts": 1,
                                        "charged_tokens": tokens[index], "held_tokens": 0,
                                        "records": {"large_record_not_for_git": "x" * 10000}},
                             "tests": {"used": 1}}, "boundary": {"huge_outcome_not_for_git": "x" * 10000}}
            for index, slot in enumerate(slots())]


def compact(rows):
    return [runner.compact_row(row, slot, None, index)
            for index, (row, slot) in enumerate(zip(rows, slots()))]


def complete_worker(plan, candidate):
    parent = plan["parents"][candidate]
    return {"status": "complete", "execution_binding_passed": True, "common_restored_exactly": True,
            "source_before": plan["source"], "source_after": plan["source"],
            "common_actor_identity": parent["common_actor_identity"],
            "final_actor_identity": parent["common_actor_identity"],
            **{key: parent["common_steps"] for key in (
                "initial_actor_steps", "initial_critic_steps", "actor_steps", "critic_steps")},
            "screening_optimizer_steps": 0, "diagnostic_optimizer_steps": 0, "fresh_technical_quiz_calls": 0}


def summaries(plan, a_rows, b_rows):
    return {c: runner.candidate_summary(compact(rows), complete_worker(plan, c), {"status": "complete"}, plan, c)
            for c, rows in zip(runner.CANDIDATES, (a_rows, b_rows))}


def test_only_eight_new_T_slots_and_P2_P3_remain_unfrozen(plan):
    assert runner.validate_plan(plan, check_files=False) is plan
    assert sum(map(len, plan["inventories"].values())) == 8
    assert runner.REPORT_PATHS == ["docs/experiments/software-local-feasibility-v034.md",
                                  "docs/experiments/software-local-feasibility-v034.json"]
    for key, value in (("frozen_development_episodes", 16), ("repeat_S_conditions", True),
                       ("resample_v033_slots", True), ("fresh_technical_quiz_calls", 3),
                       ("optimizer_updates_allowed", True), ("automatic_successors", ["P2"]),
                       ("automatic_unfrozen_successors", True)):
        with pytest.raises(ValueError, match="eight-slot"):
            runner.validate_plan({**plan, key: value}, check_files=False)
    changed = copy.deepcopy(plan)
    changed["phases"]["P2"]["status"] = "executable"
    with pytest.raises(ValueError, match="P2/P3"):
        runner.validate_plan(changed, check_files=False)
    changed_slots = slots()
    changed_slots[0]["condition"] = "S"
    with pytest.raises(ValueError, match="four T slots"):
        runner.validate_inventory(changed_slots)


def test_carrier_ranks_success_count_then_root_coverage_then_all_four_cost_then_order(plan):
    a, b = runner.CANDIDATES
    results = summaries(plan, raw_rows((0, 1, 2), (900, 900, 900, 900)), raw_rows((0, 1)))
    assert runner.next_stage_decision(results, True)["local_carrier_for_p2_design"] == a
    results = summaries(plan, raw_rows((0, 3), (10, 10, 10, 10)), raw_rows((0, 1)))
    assert runner.next_stage_decision(results, True)["local_carrier_for_p2_design"] == b
    # The first model is cheaper on successful slots, but more costly over the full fixed batch.
    results = summaries(plan, raw_rows((0, 1), (10, 10, 400, 400)), raw_rows((0, 1), (20, 20, 40, 40)))
    assert results[a]["total_actual_tokens_all_four_slots"] == 820
    assert results[b]["total_actual_tokens_all_four_slots"] == 120
    assert runner.next_stage_decision(results, True)["local_carrier_for_p2_design"] == b
    results = summaries(plan, raw_rows((0, 1)), raw_rows((0, 1)))
    decision = runner.next_stage_decision(results, True)
    assert decision["local_carrier_for_p2_design"] == a
    assert not decision["one_success_is_stable_ability_or_allocation_support"]
    assert not decision["development_records_are_training_support"]
    assert not decision["P2_frozen_and_started"] and not decision["P3_frozen_and_started"]


def test_unknown_and_untrusted_are_not_all_failed_and_complete_peer_can_still_qualify(plan):
    a, b = runner.CANDIDATES
    results = summaries(plan, raw_rows(), raw_rows())
    assert runner.next_stage_decision(results, True)["status"] == "finite_p1_all_business_failed"
    unknown = compact(raw_rows((0,)))
    unknown[3].update(status="execution_unknown", record_validity=None, R=None, complete_delivery=None)
    results[a] = runner.candidate_summary(unknown, complete_worker(plan, a), {"status": "complete"}, plan, a)
    assert not results[a]["eligible_local_carrier"]
    assert runner.next_stage_decision(results, True)["status"] == "technical_unknown_no_carrier_decision"
    results[b] = runner.candidate_summary(compact(raw_rows((0,))), complete_worker(plan, b), {"status": "complete"}, plan, b)
    assert runner.next_stage_decision(results, True)["local_carrier_for_p2_design"] == b
    assert runner.next_stage_decision(results, False)["status"] == "pending"
    worker = complete_worker(plan, b)
    worker["common_restored_exactly"] = False
    untrusted = runner.candidate_summary(compact(raw_rows((0,))), worker, {"status": "complete"}, plan, b)
    assert not untrusted["eligible_local_carrier"]
    rows = compact(raw_rows((0,)))
    rows[3]["recorded_usage"]["charged_tokens"] = None
    assert not runner.candidate_summary(rows, complete_worker(plan, b), {"status": "complete"}, plan, b)["eligible_local_carrier"]


def test_compact_report_separates_process_observation_and_counts_only_current_eight(tmp_path, plan):
    write(tmp_path / "plan.json", plan)
    states = {c: {"status": "complete", "attempted": True, "gpu": index,
                  "started_at": 20, "ended_at": 30, "elapsed_gpu_seconds": 10}
              for index, c in enumerate(runner.CANDIDATES)}
    write(tmp_path / "supervisor.json", {"status": "complete", "started_at": 0,
                                        "states": states, "running_gpu_seconds": 0})
    for c in runner.CANDIDATES:
        rows = raw_rows()
        rows[0].update(submitted=True, content_correct=False, required_process_satisfied=False,
                       process_observation_complete=False)
        write(tmp_path / c / "actual/diagnostics/progress.json", rows)
        write(tmp_path / c / "actual/report.json", complete_worker(plan, c))
    value = runner.report(tmp_path, tmp_path / "report")
    assert value["logical_inventory_count"] == value["known_work_results"] == 8
    assert value["old_v033_slots_added_to_denominator"] == 0
    assert value["cost"]["new_distinct_worker_gpu_seconds"] == 20
    assert value["cost"]["worker_interval_union"]["gpu_seconds"] == 20
    assert not value["cost"]["historical_gpu_costs_included"]
    for result in value["candidate_results"].values():
        assert result["process_satisfied"] == 0
        assert result["process_observation_incomplete"] == 1
        assert result["process_observation_unknown"] == 3
    text = json.dumps(value)
    assert "large_record_not_for_git" not in text and "huge_outcome_not_for_git" not in text
    assert len(text) < 35000


@pytest.mark.parametrize("candidate", runner.CANDIDATES)
def test_worker_uses_v034_runtime_exactly_four_slots_and_original_common(tmp_path, monkeypatch, plan, candidate):
    from proworksim import deterministic_work_v024, online_training, software_learning_v029

    owner_root = tmp_path / "owner"
    manifest = owner_root / "manifest.json"
    write(manifest, {"fixture": True})
    identity = plan["parents"][candidate]["common_actor_identity"]
    common = {"state_tensor_digest": "cpu-tensors", "actor_identity": identity}
    write(owner_root / "common/checkpoint.json", common)
    steps = plan["parents"][candidate]["common_steps"]
    profile = {"name": candidate}
    base_identity = {"path": "/cpu-fixture-model", "manifest": reference(manifest)}
    saved = {"recipe": {"seed": 1}, "inference_profile": profile, "base_identity": base_identity}
    write(owner_root / "owner.json", saved)
    write(owner_root / "loading.json", {"model": "/cpu-fixture-model", "manifest": reference(manifest),
                                         "runtime_profile": profile})
    write(owner_root / "old-plan.json", {"prior_model_plan": reference(owner_root / "loading.json"),
                                          "candidate_profiles": {candidate: profile}})
    plan["parents"][candidate]["references"] = {
        "owner": reference(owner_root / "owner.json"), "plan": reference(owner_root / "old-plan.json"),
        "common": reference(owner_root / "common/checkpoint.json"), "base_manifest": reference(manifest)}
    write(tmp_path / "plan.json", plan)
    owner = SimpleNamespace(inference_profile=profile, base_identity=base_identity,
        actor_steps=steps, critic_steps=steps, torch=None, _state_bundle=lambda: {},
        freeze_identity=lambda: identity, _make_identity=lambda: identity,
        restore_checkpoint=lambda path: common)
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
    calls = []

    def fake_collect(actual_owner, spec, output, worker_output, *, common_dir, on_slot):
        assert actual_owner is owner and spec["window_id"] == "v034-" + candidate
        assert Path(common_dir) == owner_root / "common"
        rows = raw_rows()
        write(Path(output) / "progress.json", rows)
        calls.extend(row["slot_id"] for row in rows)
        return [None] * 4

    monkeypatch.setitem(sys.modules, "proworksim.software_runtime_v034", SimpleNamespace(
        collect=fake_collect, window_spec=lambda window: {"window_id": window}))
    result = runner.run_worker(tmp_path / "plan.json", candidate, tmp_path / "actual")
    assert result["status"] == "complete" and result["common_restored_exactly"] is True
    assert calls == [slot["slot_id"] for slot in slots()]
    assert len(result["rows"]) == 4
    assert result["actor_steps"] == result["critic_steps"] == steps
    assert result["fresh_technical_quiz_calls"] == result["diagnostic_optimizer_steps"] == result["screening_optimizer_steps"] == 0


def test_final_feedback_gamma_requires_passing_route_budget_and_bound_implementation(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "SOURCE", tmp_path)
    monkeypatch.setattr(runner, "inventory", slots)
    names = (
        "src/proworksim/software_tasks_v034.py", "scripts/measure_software_reference_routes_v034.py",
        "src/proworksim/software_context_v034.py", "src/proworksim/software_context_v028.py",
        "src/proworksim/candidate_runtime_v015.py", "src/proworksim/candidate_runtime_v030.py",
        "src/proworksim/native_codecs_v031.py", "src/proworksim/software_collaboration_v034.py",
    )
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Explicit CPU binding fixture: " + name + "\n")
    directory = tmp_path / "runs/v034-controls/presentation"
    write(directory / "report.json", {"explicit_cpu_fixture": True})
    write(directory / "controls.json", {"passed": True, "model_calls": 0, "gpu_used": False})
    output = {"within_2048": True, "native_parser_roundtrip_equal": True,
              "tokens_including_native_stop": 40}
    proof = {
        "version": "reference-route-native-budget-v0.34", "presentation_version": "software-context-v0.34",
        "passed": True, "model_calls": 0, "gpu_used": False, "weights_loaded": False,
        "public_feedback_projection_applied": True, "reference_routes": 4,
        "native_request_measurements": 8,
        "limits": {"context": 16384, "max_output_per_call": 2048, "episode_tokens": 500000,
                   "decisions": 128, "attempts": 128, "test_runs": 32},
        "source_refs": {name: {"path": name, "file_sha256": reference(tmp_path / name)["sha256"]}
                        for name in names[:-1]},
        "rows": [{"model": candidate, "slot_id": row["slot_id"], "case_id": row["case_id"],
                  "scripted_calls": 1, "all_steps_fit_context": True,
                  "all_constructed_outputs_fit_output_limit": True, "episode_budget_fits": True,
                  "decision_margin": 127, "attempt_margin": 127, "test_margin": 31,
                  "episode_token_margin": 496952, "episode_token_upper_bound": 3048,
                  "steps": [{"prompt_tokens": 1000, "reserved_output_tokens": 2048,
                             "context_upper_bound_tokens": 3048, "context_fits": True,
                             "canonical_reference_output": output}]}
                 for candidate in runner.CANDIDATES for row in slots()],
    }
    proof["public_feedback_projection_source"] = proof["source_refs"][names[0]]
    final = directory / "reference-route-budget-final.json"
    # The preserved initial capacity-failure report can never serve as fallback admission.
    write(directory / "reference-route-budget.json", {"passed": False})
    with pytest.raises(FileNotFoundError):
        runner.presentation_binding(tmp_path)
    write(final, {**proof, "passed": False})
    with pytest.raises(ValueError, match="passing final"):
        runner.presentation_binding(tmp_path)
    write(final, proof)
    value = runner.presentation_binding(tmp_path)
    assert value["reference_route_budget"] == reference(final)
    assert value["public_test_feedback"]["version"] == "structured-public-test-feedback-v0.34"
    assert value["public_test_feedback"]["lossless_projection"] is False
    assert value["public_test_feedback"]["member_authored_test_feedback_preserved"] is True
    assert value["latest_public_feedback_preserved_byte_for_byte"] is False
    assert "contract_current_state_schema_and_latest_feedback_preserved" not in value
    for change in ({"model_calls": 1}, {"gpu_used": True}, {"weights_loaded": True},
                   {"public_feedback_projection_applied": False}):
        write(final, {**proof, **change})
        with pytest.raises(ValueError, match="passing final"):
            runner.presentation_binding(tmp_path)
    changed = copy.deepcopy(proof)
    changed["rows"][0]["all_steps_fit_context"] = False
    write(final, changed)
    with pytest.raises(ValueError, match="budget gate"):
        runner.presentation_binding(tmp_path)
    changed = copy.deepcopy(proof)
    changed["rows"][0]["steps"][0]["prompt_tokens"] = 16384
    changed["rows"][0]["steps"][0]["context_upper_bound_tokens"] = 18432
    write(final, changed)
    with pytest.raises(ValueError, match="native limits"):
        runner.presentation_binding(tmp_path)
    write(final, proof)
    (tmp_path / names[0]).write_text("# changed feedback helper\n")
    with pytest.raises(ValueError, match="implementation changed"):
        runner.presentation_binding(tmp_path)
