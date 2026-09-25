"""Actual short-world boundaries and explicit v0.13 read operations, CPU only."""

import copy

import pytest

from proworksim.episode import begin_episode, finish_episode
from proworksim.information_mapper import information_graph
from proworksim.online_rewards import assess_online_reward
from proworksim.online_support import assess_online_validity, export_online_rollout
from proworksim.storage import digest, json_bytes, read_json
from proworksim.templates.online_work import build_online_case
from scripts.online_work_experiment_v013 import Witness, run_case


def arguments(root):
    manifest = read_json(root / "episode/manifest.json")
    spec = manifest["scenario"]["variation"]["online_reward"]
    members = {role: {"actor_id": role, "origin": "rule"} for role in spec["active_roles"]}
    window = {
        "window_id": "explicit-rule-scope-test",
        "xi_id": manifest["scenario"]["scenario_id"],
        "xi_fingerprint": digest(json_bytes(manifest["scenario"])),
        "gamma_fingerprint": "CPU program witness only",
        "team_policy_fingerprint": digest(json_bytes(manifest["policies"])),
    }
    return manifest, spec, members, window, read_json(root / "capture.json")


@pytest.mark.parametrize("task", ["handoff", "implement"])
def test_scope_validity_does_not_require_unassigned_team_approval(tmp_path, task):
    root = tmp_path / task
    run_case("train-w0-" + task, root)
    manifest, spec, members, window, capture = arguments(root)
    result = export_online_rollout(
        root / "episode",
        window=window,
        members=members,
        independent_capture=capture,
        reward_spec=spec,
    )
    assert result["reward_eligibility"]["reward"] == 1
    assert result["work_validity"]["value"] is True
    assert result["online_scope"]["task"] == task
    assert len(result["members"]) == 1
    assert manifest["fixed_deliveries"]["TEAM::build"]["review"] is None
    assert all(e.get("worker_id") in {None, *members} for e in result["events"])


def test_partial_reward_is_not_complete_validity_and_missing_capture_stays_unknown(tmp_path):
    root = tmp_path / "partial"
    run_case("train-w0-handoff", root, control="read_only")
    _, spec, members, _, capture = arguments(root)
    reward = assess_online_reward(root / "episode", spec)
    assert reward["reward"] == 0.25
    partial = assess_online_validity(
        root / "episode", spec, independent_capture=capture, members=members
    )
    assert partial["components"]["basis"]["value"] is True
    assert partial["components"]["delivery"]["value"] is False
    adjusted_scalar = copy.deepcopy(reward)
    adjusted_scalar.update(reward=1, completed=True)
    assert (
        assess_online_validity(
            root / "episode",
            spec,
            independent_capture=capture,
            members=members,
            reward_result=adjusted_scalar,
        )
        == partial
    )
    good = tmp_path / "good"
    run_case("train-w0-handoff", good)
    _, spec, members, _, _ = arguments(good)
    assert (
        assess_online_validity(good / "episode", spec, independent_capture=None, members=members)[
            "value"
        ]
        is None
    )


def test_actual_read_alias_and_read_version_have_declared_graph_semantics(tmp_path):
    prepared = build_online_case("train-w0-handoff", tmp_path / "case")
    root = tmp_path / "case"
    witness = Witness(prepared)
    policies = {"provider": {"implementation": "explicit_rule_witness", "config": {}}}
    begin_episode(
        prepared.world,
        root / "episode",
        experience=witness.recorder.snapshot(),
        work_ids=["TEAM::build"],
        scenario=prepared.scenario,
        policies=policies,
    )
    first = witness.call("provider", "read_alias", alias="basis", work_id="TEAM::build")
    assert set(first["reference"]) == {"object_id", "version_id"}
    second = witness.call(
        "provider", "read_version", reference=first["reference"], work_id="TEAM::build"
    )
    assert second == first
    witness.call(
        "provider",
        "handoff_information",
        route_id="basis",
        work_id="TEAM::build",
        handoff_key="exact-read",
        reference=second["reference"],
        body="Actually read exact applicable version",
    )
    finish_episode(
        prepared.world,
        root / "episode",
        experience=witness.recorder.snapshot(),
        termination={"status": "rule_witness_boundary"},
    )
    (root / "capture.json").write_bytes(json_bytes(witness.capture))
    _, spec, members, window, capture = arguments(root)
    result = export_online_rollout(
        root / "episode",
        window=window,
        members=members,
        independent_capture=capture,
        reward_spec=spec,
    )
    assert result["work_validity"]["value"] is True
    graph = information_graph(result, read_operations=["read_alias", "read_version"])
    assert graph["version"] == "information-graph-v0.13"
    nodes = {node["node_id"]: node for node in graph["nodes"]}
    reads = [
        nodes[edge["target"]]["action"]
        for edge in graph["edges"]
        if edge["kind"] == "observes_version"
    ]
    assert reads == ["read_alias", "read_version"]
    default_graph = information_graph(result)
    assert not any(edge["kind"] == "observes_version" for edge in default_graph["edges"])
    assert [e["payload"]["action"] for e in result["events"] if e["kind"] == "tool_call"] == [
        "read_alias",
        "read_version",
        "handoff_information",
    ]


def test_renaming_a_public_read_cannot_forge_its_formal_transition(tmp_path):
    from proworksim.team_validity import _record_permission_checks

    root = tmp_path / "case"
    run_case("train-w0-handoff", root)
    manifest, _, members, _, capture = arguments(root)
    state = read_json(root / "episode/end/control/state.json")
    events = read_json(root / "episode/experience.json")["events"]
    changed = copy.deepcopy(events)
    forged_capture = copy.deepcopy(capture)
    target = next(
        e for e in changed if e["kind"] == "tool_call" and e["payload"]["action"] == "read_alias"
    )
    target["payload"]["action"] = "read_version"
    next(
        e
        for e in forged_capture["provider"]
        if e["kind"] == "tool_call" and e["payload"]["action"] == "read_alias"
    )["payload"]["action"] = "read_version"
    checks = _record_permission_checks(
        manifest,
        state,
        changed,
        members,
        forged_capture,
        {"manifest_sha256": "semantic-unit-control"},
        allow_rejected_actions=True,
        allow_repair=True,
    )
    assert next(c for c in checks if c["dimension"] == "permission")["value"] is False
    command = state["operation_commits"][target["payload"]["response"]["command_id"]]
    assert command["receipt"]["contract"] == "read_alias"
