"""Synthetic CPU controls for source boundaries; no downloaded SWE instances."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from proworksim.software_sources_v027 import (
    MEMBER_CAPABILITIES, PURPOSES, freeze_source_partition, require_run_admission,
    validate_derived_tasks, validate_on_policy_record,
)


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def asset(name="a", **changes):
    return {"asset_id": name, "provider": "swe_smith", "source_cluster": name,
            "repository": f"https://github.com/fixture/{name}", "commit": sha(name)[:40],
            "issue_id": "fixture-issue", "target_patch_sha256": sha(name + "patch"),
            "environment_sha256": sha(name + "environment"),
            "test_sha256": [sha(name + "tests")], "parent_asset_ids": [],
            "derivation_roots": [name], "task_derivation_started": False,
            "previously_used": False, **changes}


def partition():
    return freeze_source_partition([asset()], {"a": "policy_training"})


def task(frozen=None):
    frozen = frozen or partition()
    return {"task_id": "fixture-task", "partition_sha256": frozen["sha256"],
            "source_asset_ids": ["a"], "purpose": "policy_training",
            "family": "interface_producer_consumer", "requirements_sha256": sha("requirements"),
            "joint_solution_witness_sha256": sha("joint"),
            "dependency_witness_sha256": sha("dependency"),
            "independent_verifier_sha256": sha("verifier"),
            "members": {name: list(MEMBER_CAPABILITIES) for name in ("member_0", "member_1")}}


def plan():
    frozen = partition()
    return {"schema": "software-source-plan-v027", "primary_training_source": "swe_smith",
            "fallback_training_source": "swe_gym", "active_training_sources": ["swe_smith"],
            "teacher_trajectories_as_current_experience": False,
            "partition": frozen, "tasks": [task(frozen)],
            "run_budget": {"protocol": "software-collaboration-v027", "frozen": True,
                           "inherited_from": None, "gpu_seconds": 60, "wall_seconds": 90,
                           "episode_count": 1, "max_decisions_per_member": 12,
                           "context_tokens": 4096, "output_tokens": 256}}


def test_all_four_purposes_are_frozen_without_mutating_sources():
    sources = [asset(name) for name in ("a", "b", "c", "d")]
    assignments = dict(zip(("a", "b", "c", "d"), PURPOSES))
    before = copy.deepcopy(sources)
    frozen = freeze_source_partition(sources, assignments)
    assert sources == before
    assert frozen == freeze_source_partition(list(reversed(sources)), assignments)
    assert frozen["frozen_before_task_derivation"] is True
    assert len(frozen["clusters"]) == 4


@pytest.mark.parametrize("overlap", [
    {"repository": "https://github.com/FIXTURE/a.git/"},
    {"commit": sha("a")[:40]},
    {"source_cluster": "a"},
    {"target_patch_sha256": sha("apatch")},
    {"test_sha256": [sha("atests")]},
    {"derivation_roots": ["a"]},
    {"parent_asset_ids": ["a"]},
])
def test_any_lineage_overlap_blocks_cross_purpose_even_with_different_benchmark(overlap):
    sources = [asset(), asset("b", provider="cooperbench", **overlap)]
    with pytest.raises(ValueError, match="cross-purpose"):
        freeze_source_partition(sources, {"a": "policy_training", "b": "independent_confirmation"})
    assert len(freeze_source_partition(sources, {"a": "policy_training", "b": "policy_training"})["clusters"]) == 1


def test_transitive_derivation_prevents_indirect_leakage():
    sources = [asset(), asset("b", parent_asset_ids=["a"]), asset("c", derivation_roots=["b"])]
    with pytest.raises(ValueError, match="cross-purpose"):
        freeze_source_partition(sources, {"a": "policy_training", "b": "policy_training",
                                          "c": "contribution_development"})


@pytest.mark.parametrize("purpose", PURPOSES[1:])
def test_marshmallow_historical_assets_cannot_be_promoted_to_new_evidence(purpose):
    legacy = asset(repository="https://github.com/marshmallow-code/marshmallow")
    with pytest.raises(ValueError, match="historical"):
        freeze_source_partition([legacy], {"a": purpose})
    assert freeze_source_partition([legacy], {"a": "interface_development"})


def test_partition_cannot_be_created_after_task_derivation_or_reassigned():
    with pytest.raises(ValueError, match="before deriving"):
        freeze_source_partition([asset(task_derivation_started=True)], {"a": "policy_training"})
    frozen = partition()
    frozen["assignments"]["a"] = "independent_confirmation"
    with pytest.raises(ValueError, match="changed"):
        validate_derived_tasks(frozen, [task()])


def test_unrecorded_parent_and_unpartitioned_derived_sources_fail_closed():
    with pytest.raises(ValueError, match="parent"):
        freeze_source_partition([asset(parent_asset_ids=["missing"])], {"a": "policy_training"})
    derived = task()
    derived["source_asset_ids"] = ["missing"]
    with pytest.raises(ValueError, match="unpartitioned"):
        validate_derived_tasks(partition(), [derived])


@pytest.mark.parametrize("mutation", [
    {"purpose": "independent_confirmation"},
    {"partition_sha256": sha("another")},
    {"family": "two_unrelated_issues"},
    {"joint_solution_witness_sha256": None},
    {"members": {"manager": ["task_board"], "coder": list(MEMBER_CAPABILITIES)}},
])
def test_task_purpose_lineage_feasibility_and_member_scope_are_required(mutation):
    with pytest.raises(ValueError):
        validate_derived_tasks(partition(), [task() | mutation])


def test_valid_declaration_does_not_execute_witness_or_model():
    result = require_run_admission(plan())
    assert result["source_admission"] is True
    assert result["execution_performed"] is False
    assert result["semantic_witness_validation"] == "external_required"


@pytest.mark.parametrize("mutation", [
    {"protocol": "reciprocal-data-v026"},
    {"inherited_from": "v026-8h-extension"},
    {"frozen": False}, {"gpu_seconds": None}, {"gpu_seconds": True},
    {"output_tokens": 4096},
])
def test_prior_budget_or_incomplete_budget_never_launches(mutation):
    candidate = plan()
    candidate["run_budget"].update(mutation)
    with pytest.raises(ValueError):
        require_run_admission(candidate)


def test_current_plan_is_honestly_pending_and_cannot_admit_a_run():
    pending = json.loads(Path("examples/software-collaboration-v027/source-plan.json").read_text())
    assert pending["tasks"] == [] and pending["partition"] is None
    assert all(pending["run_budget"][name] is None for name in (
        "gpu_seconds", "wall_seconds", "episode_count", "max_decisions_per_member",
        "context_tokens", "output_tokens"))
    with pytest.raises(ValueError, match="frozen"):
        require_run_admission(pending)


def test_no_fallback_parallel_training_pipeline_or_teacher_substitution():
    candidate = plan()
    candidate["active_training_sources"].append("swe_gym")
    with pytest.raises(ValueError, match="parallel"):
        require_run_admission(candidate)
    record = {"origin": "current_policy", "window_id": "window-1", "actor_sha256": sha("actor"),
              "task_id": "fixture-task", "member_id": "member_0",
              "raw_member_actions_sha256": sha("actions")}
    assert validate_on_policy_record(record, task(), window_id="window-1", actor_sha256=sha("actor"))
    for mutation in ({"origin": "teacher"}, {"window_id": "old"},
                     {"actor_sha256": sha("other-branch")}, {"member_id": "last_successful_member"},
                     {"raw_member_actions_sha256": None}):
        with pytest.raises(ValueError):
            validate_on_policy_record(record | mutation, task(), window_id="window-1", actor_sha256=sha("actor"))
