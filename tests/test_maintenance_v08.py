"""Finite event policies preserve exact historical context and institutional scope."""

import copy

import pytest

from proworksim.core.maintenance import (
    apply_impact,
    impact_candidates,
    normalize_rules,
    successor_identity,
    work_stage,
)
from proworksim.core.projections import rebuild_projections
from proworksim.core.work import approve_submission, submit_work
from proworksim.core.world import new_world_state


def ledger(stage="before_read", effect="revise"):
    state = new_world_state({"world_id": "maintenance", "actors": {"worker": {}, "manager": {}}})
    state["clock"] = 5
    state["projects"] = {
        "A": {"participants": ["worker", "manager"], "status": "active", "work_ids": []},
        "B": {
            "participants": ["worker", "manager"],
            "status": "active",
            "work_ids": ["B::analysis"],
        },
    }
    state["workspaces"] = {"A": {"source": "source"}, "B": {"input": "source", "output": "output"}}
    state["organization"]["grants"] = [
        {
            "actor_id": "manager",
            "scope": "project",
            "project_id": "B",
            "power": power,
            "subject": "*",
            "work_nodes": ["B::analysis"],
            "object_ids": ["*"],
        }
        for power in ("revise_requirement", "approve")
    ]
    for oid, pid in (("source", "A"), ("output", "B")):
        state["artifacts"][oid] = {
            "artifact_id": oid,
            "project_id": pid,
            "kind": "json",
            "current_version": "v1",
            "versions": {"v1": {"sha256": "fixed", "logical_time": 0}},
        }
    item = {
        "work_item_id": "B::analysis",
        "node_id": "B::analysis",
        "root_work_id": "B::analysis",
        "project_id": "B",
        "owner_role": "worker",
        "goal": "Consume source",
        "requirement_version": 1,
        "status": "open",
        "dependencies": [],
        "deliverables": ["output"],
        "inputs": ["source"],
        "required_credentials": [],
        "submissions": [],
        "artifact_edits": [],
        "activated_at": 1,
        "requirements": {"edition": "original"},
    }
    state["work_items"][item["work_item_id"]] = item
    if stage != "before_read":
        state["knowledge"]["worker"]["read_artifacts"].append(
            {
                "artifact_id": "source",
                "project_id": "B",
                "at": 2,
                "work_item_id": "B::analysis",
                "requirement_version": 1,
            }
        )
    if stage in {"output_ready", "pending", "accepted"}:
        item["artifact_edits"].append(
            {
                "artifact_id": "output",
                "version_id": "v1",
                "actor_id": "worker",
                "at": 3,
                "work_item_id": "B::analysis",
                "requirement_version": 1,
            }
        )
    rebuild_projections(state)
    if stage in {"pending", "accepted"}:
        sub = submit_work(state, "worker", "B::analysis", {"output": "v1"})
        if stage == "accepted":
            approve_submission(state, "manager", "B::analysis", sub["submission_id"])
    rule = {
        "rule_id": "source-change",
        "source": {"alias": "input", "source_project": "A"},
        "work_nodes": ["analysis"],
        "when": [stage],
        "effect": effect,
        "actor": "manager",
    }
    if effect in {"revise", "successor"}:
        rule["updates"] = {"requirements": {"edition": "changed"}}
    state["projects"]["B"]["maintenance_rules"] = normalize_rules(state, "B", [rule])
    release = {
        "release_id": "release-next",
        "object_id": "source",
        "version_id": "v1",
        "source_project": "A",
        "scope": {"target_projects": ["A", "B"], "work_ids": []},
    }
    state["releases"].append(release)
    return state, release


@pytest.mark.parametrize(
    "stage", ["before_read", "after_read", "output_ready", "pending", "accepted"]
)
def test_progress_uses_recorded_facts_not_round_number_or_status_cache(stage):
    state, release = ledger(stage)
    state["work_items"]["B::analysis"]["status"] = "arbitrary-cache"
    assert work_stage(state, "B::analysis", "source") == stage
    candidates = impact_candidates(state, release)
    assert len(candidates) == 1
    assert candidates[0]["stage"] == stage


@pytest.mark.parametrize("effect", ["notice", "ignore", "revise", "successor"])
def test_release_consequences_preserve_bytes_approval_and_observations_and_dedup(effect):
    state, release = ledger("accepted", effect)
    state["observations"].append({"frozen_observation": {"work": "B::analysis"}})
    historical = copy.deepcopy(state["work_items"]["B::analysis"]["submissions"])
    conserved = copy.deepcopy((state["artifacts"], state["observations"], state["adoptions"]))
    payload = impact_candidates(state, release)[0]
    result = apply_impact(state, payload)
    assert result["created"]
    assert (state["artifacts"], state["observations"], state["adoptions"]) == conserved
    assert state["work_items"]["B::analysis"]["submissions"][0]["review"] == historical[0]["review"]
    if effect in {"notice", "ignore"}:
        assert list(state["work_items"]) == ["B::analysis"]
        assert state["work_items"]["B::analysis"]["submissions"] == historical
    else:
        assert state["work_items"][result["new_work_id"]]["requirements"] == {"edition": "changed"}
        assert state["work_items"][result["new_work_id"]]["submissions"] == []
        assert state["projects"]["B"]["maintenance_heads"]["B::analysis"] == result["new_work_id"]
    if effect == "successor":
        assert result["new_work_id"] == successor_identity(payload)
        assert state["work_replacements"] == {}
        assert state["work_items"]["B::analysis"]["submissions"] == historical
    snapshot = copy.deepcopy(state)
    assert not apply_impact(state, payload)["created"]
    assert state == snapshot
    assert impact_candidates(state, release) == []


def test_wrong_authority_target_or_conflicting_payload_is_rejected():
    state, release = ledger()
    rule = copy.deepcopy(state["projects"]["B"]["maintenance_rules"][0])
    rule["source"].pop("alias")
    rule["actor"] = "worker"
    with pytest.raises(ValueError, match="institutional power"):
        normalize_rules(state, "B", [rule])
    payload = impact_candidates(state, release)[0]
    bad = {**payload, "target_work_id": "A::analysis"}
    before = copy.deepcopy(state)
    with pytest.raises((ValueError, KeyError)):
        apply_impact(state, bad)
    assert state == before
    apply_impact(state, payload)
    with pytest.raises(ValueError, match="payload conflict"):
        apply_impact(state, {**payload, "effect": "ignore"})


def test_read_in_other_work_or_old_requirement_is_not_a_current_work_read():
    state, _ = ledger("after_read")
    read = state["knowledge"]["worker"]["read_artifacts"][0]
    read["work_item_id"] = "B::other"
    assert work_stage(state, "B::analysis", "source") == "before_read"
    read["work_item_id"] = "B::analysis"
    read["requirement_version"] = 0
    assert work_stage(state, "B::analysis", "source") == "before_read"


def test_external_replacement_between_release_and_delivery_is_retained_as_stale():
    from proworksim.core.work import revise_requirement

    state, release = ledger()
    payload = impact_candidates(state, release)[0]
    replacements = revise_requirement(
        state, ["B::analysis"], {"goal": "External new instruction"}, "manager", "external"
    )
    work_before = copy.deepcopy(state["work_items"])
    result = apply_impact(state, payload)
    assert result["outcome"] == "stale_target"
    assert state["work_items"] == work_before
    assert len(replacements) == 1


def test_next_release_targets_maintenance_head_and_never_reopens_accepted_predecessor():
    state, release = ledger("accepted", "successor")
    result = apply_impact(state, impact_candidates(state, release)[0])
    new = result["new_work_id"]
    rule = state["projects"]["B"]["maintenance_rules"][0]
    rule.update(effect="revise", when=["before_read"])
    second = {**release, "release_id": "second-release"}
    state["releases"].append(second)
    payload = impact_candidates(state, second)[0]
    assert payload["target_work_id"] == new
    historical = copy.deepcopy(state["work_items"]["B::analysis"])
    assert apply_impact(state, payload)["new_work_id"] != new
    assert state["work_items"]["B::analysis"] == historical


def test_successor_rule_cannot_claim_an_unaccepted_predecessor():
    state, _ = ledger("accepted", "successor")
    rule = copy.deepcopy(state["projects"]["B"]["maintenance_rules"][0])
    rule["source"].pop("alias")
    rule["when"] = ["output_ready"]
    with pytest.raises(ValueError, match="accepted predecessor"):
        normalize_rules(state, "B", [rule])
