"""Finite exact-field, evidence-boundary and complete-feedback controls."""
import copy
import json

import pytest

from proworksim.software_context_v041 import POLICY_SNAPSHOT_FIELDS, deduplicate_static_snapshots, project_software_request
from test_software_context_v034 import render, tokenizer


def observation(*, actor="member_001", time=0, evidence_version="v1", task="Complete this shared root."):
    reference = {"object_id": "baseline", "version_id": evidence_version}
    report = {"diagnostic_id": "root:diagnostic_a", "origin": "environment_initial_diagnostic", "initial_report": True,
        "source_reference": reference, "initial_source_reference": reference, "files_sha256": "frozen-source",
        "tests": [{"id": "actual-initial-failure", "passed": False, "expected": "Complete original expected value"}]}
    contract = "Complete immutable public contract. " * 8
    return {"role": "user", "content": json.dumps({"role_task": task, "observation": {
        "world_id": "world", "instance_id": "instance", "branch_id": "branch", "project_id": "project",
        "actor_id": actor, "interface_revision": "v040", "contract": contract,
        "root_goal": {"task_id": "root_goal", "description": contract}, "initial_diagnostics": [report],
        "workspace_reference": {"object_id": actor, "version_id": "v" + str(time + 1)},
        "tasks": [{"id": "task", "revision": time}], "team_model_budget": {"decisions": time}, "logical_time": time}})}


def request():
    return {"model": "no-model-cpu", "max_tokens": 20, "temperature": 0.7, "tools": [{"name": "read"}],
        "messages": [{"role": "system", "content": "Original system"}, observation(),
            {"role": "assistant", "content": "original reasoning", "tool_calls": [{"id": "real", "function": {"name": "read"}}]},
            {"role": "tool", "tool_call_id": "real", "content": "Full original failed-test feedback"},
            {"role": "user", "content": json.dumps({"public_format_feedback": {"reason": "Actual schema failure"}})},
            observation(time=4)]}


def test_exact_static_deletions_have_complete_selected_witnesses_and_keep_dynamic_state():
    original = request()
    before = copy.deepcopy(original)
    selected, evidence = deduplicate_static_snapshots(original)
    assert original == before and selected["tools"] == original["tools"]
    assert selected["messages"][2:5] == original["messages"][2:5]
    first, latest = [json.loads(selected["messages"][index]["content"]) for index in (1, 5)]
    assert "role_task" not in first and "initial_diagnostics" not in first["observation"]
    source = json.loads(original["messages"][5]["content"])
    assert latest["role_task"] == source["role_task"]
    assert latest["observation"]["initial_diagnostics"] == source["observation"]["initial_diagnostics"]
    for index in (1, 5):
        after, old = [json.loads(r["messages"][index]["content"])["observation"] for r in (selected, original)]
        assert all(after[key] == old[key] for key in ("tasks", "team_model_budget", "logical_time", "workspace_reference"))
    assert len(evidence["removed_values"]) == 5
    assert all(row["member_identity"]["actor_id"] == "member_001" for row in evidence["removed_values"])
    assert deduplicate_static_snapshots(selected)[0] == selected


@pytest.mark.parametrize("change", ["member", "instance", "evidence_version", "instruction", "missing_provenance"])
def test_unique_or_differently_bound_static_values_are_not_removed(change):
    original = request()
    first = json.loads(original["messages"][1]["content"])
    if change == "member":
        first["observation"]["actor_id"] = "member_002"
    elif change == "instance":
        first["observation"]["instance_id"] = "independent-instance"
    elif change == "evidence_version":
        first = json.loads(observation(evidence_version="different-initial-version")["content"])
    elif change == "instruction":
        first["role_task"] += " Distinct earlier instruction."
    else:
        del first["observation"]["actor_id"]
    original["messages"][1]["content"] = json.dumps(first)
    selected, _ = deduplicate_static_snapshots(original)
    actual = json.loads(selected["messages"][1]["content"])
    if change != "instruction":
        assert actual["observation"]["initial_diagnostics"] == first["observation"]["initial_diagnostics"]
    if change != "evidence_version":
        assert actual["role_task"] == first["role_task"]


def test_same_test_text_in_separate_events_and_changed_initial_origin_survive():
    original = request()
    first = json.loads(original["messages"][1]["content"])
    first["observation"]["initial_diagnostics"][0]["origin"] = "member_public_test_execution"
    original["messages"][1]["content"] = json.dumps(first)
    original["messages"][3]["content"] = json.dumps(first["observation"]["initial_diagnostics"])
    selected, _ = deduplicate_static_snapshots(original)
    assert selected["messages"][2:5] == original["messages"][2:5]
    assert json.loads(selected["messages"][1]["content"])["observation"]["initial_diagnostics"] == first["observation"]["initial_diagnostics"]


def test_declared_fixed_policy_snapshots_deduplicate_but_equal_dynamic_states_do_not():
    original = request()
    for index in (1, 5):
        payload = json.loads(original["messages"][index]["content"])
        observation = payload["observation"]
        observation.update({field: {"frozen_policy": field, "version": "v040"} for field in POLICY_SNAPSHOT_FIELDS})
        observation.update(execution_condition={"cumulative_births": 2}, task_formation={"tasks_created": 0},
                           member_registry={"member_001": {"status": "live"}})
        original["messages"][index]["content"] = json.dumps(payload)
    selected, evidence = deduplicate_static_snapshots(original)
    first, latest = [json.loads(selected["messages"][index]["content"])["observation"] for index in (1, 5)]
    assert all(field not in first and field in latest for field in POLICY_SNAPSHOT_FIELDS)
    assert all(first[field] == latest[field] for field in ("execution_condition", "task_formation", "member_registry"))
    assert len(evidence["removed_values"]) == 5 + len(POLICY_SNAPSHOT_FIELDS)
    different = json.loads(original["messages"][1]["content"])
    different["observation"]["action_error_policy"]["version"] = "different-policy-version"
    original["messages"][1]["content"] = json.dumps(different)
    selected, _ = deduplicate_static_snapshots(original)
    assert json.loads(selected["messages"][1]["content"])["observation"]["action_error_policy"] == different["observation"]["action_error_policy"]


def test_capacity_deletes_only_older_complete_round_and_keeps_full_latest_feedback():
    original = request()
    original["messages"][2:2] = [
        {"role": "assistant", "content": "older", "tool_calls": [{"id": "old", "function": {"name": "read"}}]},
        {"role": "tool", "tool_call_id": "old", "content": "Older complete feedback. " * 300}]
    deduplicated, _ = deduplicate_static_snapshots(original)
    minimum = copy.deepcopy(deduplicated)
    del minimum["messages"][2:4]
    limit = len(tokenizer(render(minimum)[0])["input_ids"]) + original["max_tokens"]
    selected, audit = project_software_request(original, render=render, tokenizer=tokenizer, context_limit=limit)
    assert audit["fits"] and audit["removed_indices"] == [2, 3]
    assert selected["messages"][2:5] == original["messages"][4:7]
    blocked, failure = project_software_request(original, render=render, tokenizer=tokenizer, context_limit=limit - 1)
    assert failure["fits"] is False and blocked == selected
