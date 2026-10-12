"""Frozen candidate 1: finite mechanical controls, no model or native tokenizer."""
import copy
import json
from pathlib import Path

import pytest

from proworksim import software_context_v044 as gamma0
from proworksim import software_context_v048 as gamma1
from proworksim.software_context_v041 import MEMBER_SCOPE_FIELDS, deduplicate_static_snapshots
from proworksim.software_feedback_v044 import OrdinaryFeedbackLedger, feedback_message, project_format_feedback
from proworksim.storage import digest, json_bytes
from test_software_context_v034 import owner, render, tokenizer
from test_software_context_v041 import request as base_request
from test_software_feedback_v044 import present, register, request as feedback_request

MEMBER = "member_001"


def request():
    value = base_request()
    for index in (1, 5):
        payload = json.loads(value["messages"][index]["content"])
        observation = payload["observation"]
        observation["architecture"] = {
            "stage_plan": [{"stage_id": "implement", "members": [MEMBER],
                "limits": {"max_total_tokens": 175000, "max_decisions": 44, "max_attempts": 44, "max_test_runs": 8},
                "submit_allowed": False}],
            "allowed_tools": ["read_file", "run_tests", "fix_patch"],
            "stage_model_budget": {"available_tokens": 100 - index}}
        observation["execution_condition"] = {"initial_members": [MEMBER, "member_002"], "active_executors": [MEMBER]}
        observation["member_registry"] = {MEMBER: {"status": "live", "source": {"object_id": "base", "version_id": "v1"}}}
        observation["patches"] = [{"patch_id": "p1", "version_id": "v1", "author": "member_002"}]
        value["messages"][index]["content"] = json.dumps(payload, ensure_ascii=False)
    return value


def mutate(value, index, path, replacement):
    payload = json.loads(value["messages"][index]["content"])
    keys = path.split("/")[1:]
    current = payload
    for key in keys[:-1]:
        current = current[key]
    current[keys[-1]] = copy.deepcopy(replacement)
    value["messages"][index]["content"] = json.dumps(payload, ensure_ascii=False)


def reference(value, member=MEMBER):
    static, _ = deduplicate_static_snapshots(value)
    projected, audit = gamma1.reference_equal_fields(static, source_request=value, member_id=member)
    return static, projected, audit


def test_frozen_candidate_exact_paths_format_and_byte_roundtrip():
    candidate_path = Path(__file__).resolve().parents[1] / "docs/experiments/software-organization-v048-candidate.json"
    data = candidate_path.read_bytes()
    candidate = json.loads(data)
    assert digest(data) == gamma1.CANDIDATE_SHA256
    assert tuple(candidate["allowlist"]) == gamma1.ALLOWLIST
    assert candidate["reference_format"] == {gamma1.REFERENCE_KEY: gamma1.REFERENCE_ANCHOR + "<exact allowlisted JSON pointer>"}
    original = request()
    before = copy.deepcopy(original)
    static, projected, audit = reference(original)
    assert original == before and audit["eligible"] is True
    assert len(audit["generated_references"]) == 5
    assert projected["messages"][1] == static["messages"][1]
    assert gamma1.validate_reference_projection(projected, static, list(range(6)), audit)["passed"]
    assert json.loads(projected["messages"][-1]["content"])["observation"]["architecture"]["stage_plan"] == {
        "$same_input_ref": "first_observation#/observation/architecture/stage_plan"}


@pytest.mark.parametrize(("path", "changed"), [
    ("/observation/architecture/stage_plan", [{"stage_id": "implement", "limits": {"max_total_tokens": 175001}, "submit_allowed": True}]),
    ("/observation/architecture/allowed_tools", ["read_file", "run_tests", "submit_integration"]),
    ("/observation/execution_condition/initial_members", ["member_002", MEMBER]),
    ("/observation/member_registry", {MEMBER: {"status": "retired", "source": {"object_id": "base", "version_id": "v2"}}}),
    ("/observation/patches", [{"patch_id": "p1", "version_id": "v2", "author": "member_002"}]),
])
def test_changed_complete_field_remains_complete_without_partial_matching(path, changed):
    original = request()
    mutate(original, 5, path, changed)
    _, projected, audit = reference(original)
    assert path not in {row["path"] for row in audit["generated_references"]}
    assert gamma1._get(json.loads(projected["messages"][-1]["content"]), path) == changed


@pytest.mark.parametrize(("left", "right"), [
    (True, 1), (1, 1.0), ({"a": 1, "b": 2}, {"b": 2, "a": 1}),
    (["a", "b"], ["b", "a"]), ("é", "e\u0301"),
])
def test_strict_json_value_comparison_does_not_coerce_or_normalize(left, right):
    original = request()
    path = gamma1.ALLOWLIST[0]
    mutate(original, 1, path, left)
    mutate(original, 5, path, right)
    _, projected, audit = reference(original)
    assert path not in {row["path"] for row in audit["generated_references"]}
    assert json_bytes(gamma1._get(json.loads(projected["messages"][-1]["content"]), path)) == json_bytes(right)


def test_missing_path_single_observation_and_ambiguous_envelope_are_conservative():
    original = request()
    payload = json.loads(original["messages"][1]["content"])
    del payload["observation"]["patches"]
    original["messages"][1]["content"] = json.dumps(payload)
    _, _, audit = reference(original)
    assert {"path": "/observation/patches", "reason": "missing_path"} in audit["retained_fields"]
    original["messages"].pop(1)
    static, projected, audit = reference(original)
    assert not audit["eligible"] and projected == static
    original = request()
    original["messages"][1]["content"] = original["messages"][1]["content"].replace('"world_id": "world"', '"world_id": "world", "world_id": "world"')
    static, projected, audit = reference(original)
    assert audit["ineligible_reason"] == "ambiguous_observation_json" and projected == static


@pytest.mark.parametrize("key", [*MEMBER_SCOPE_FIELDS, "root_goal", "contract", "bound_member", "missing_actor"])
def test_no_cross_identity_or_root_reference(key):
    original = request()
    member = MEMBER
    if key == "bound_member":
        member = "member_002"
    elif key == "missing_actor":
        payload = json.loads(original["messages"][1]["content"])
        del payload["observation"]["actor_id"]
        original["messages"][1]["content"] = json.dumps(payload)
    else:
        mutate(original, 1, "/observation/" + key, {"task_id": "other_root"} if key == "root_goal" else "different")
    static, projected, audit = reference(original, member=member)
    assert not audit["eligible"] and projected == static and audit["generated_references"] == []


def test_original_v041_latest_static_values_and_nonallowlisted_payloads_remain():
    original = request()
    static, projected, audit = reference(original)
    first = json.loads(projected["messages"][1]["content"])
    latest = json.loads(projected["messages"][-1]["content"])
    assert "role_task" not in first and "contract" not in first["observation"]
    assert "initial_diagnostics" not in first["observation"]
    raw_latest = json.loads(original["messages"][-1]["content"])
    for field in ("contract", "initial_diagnostics", "team_model_budget", "workspace_reference", "tasks", "logical_time"):
        assert latest["observation"][field] == raw_latest["observation"][field]
    assert latest["role_task"] == raw_latest["role_task"]
    assert projected["messages"][:1] + projected["messages"][2:5] == original["messages"][:1] + original["messages"][2:5]
    assert projected["tools"] == original["tools"]
    assert audit["root_identity"]["root_goal_id"] == "root_goal"
    assert gamma1.validate_reference_projection(projected, static, list(range(6)), audit)["passed"]


def test_old_round_deletion_preserves_reference_targets_latest_page_and_hard_failure():
    original = request()
    original["messages"][3]["content"] = "原始完整页" * 614 + "末尾"  # 3072 Unicode characters
    assert len(original["messages"][3]["content"]) == 3072
    original["messages"][2:2] = [
        {"role": "assistant", "content": "old", "tool_calls": [{"id": "old", "function": {"name": "read"}}]},
        {"role": "tool", "tool_call_id": "old", "content": "old complete feedback" * 1000}]
    protected, evidence = gamma1.protected_software_request(original, member_id=MEMBER)
    limit = len(tokenizer(render(protected)[0])["input_ids"]) + original["max_tokens"]
    selected, audit = gamma1.project_software_request(original, render=render, tokenizer=tokenizer,
        context_limit=limit, member_id=MEMBER)
    assert selected == protected and audit["fits"]
    assert audit["removed_indices"] == [2, 3] and evidence["selected_indices"] == audit["protected_selected_indices"]
    assert audit["selected_reference_validation"]["passed"] and audit["protected_reference_validation"]["passed"]
    assert selected["messages"][2:5] == original["messages"][4:7]
    assert audit["protected_headroom_tokens"] == 0 and audit["protected_headroom_after_margin"] == -1024
    blocked, failure = gamma1.project_software_request(original, render=render, tokenizer=tokenizer,
        context_limit=limit - 1, member_id=MEMBER)
    assert blocked == selected and not failure["fits"]


def test_existing_structural_markers_are_retained_without_new_nested_reference():
    original = request()
    path = "/observation/patches"
    existing = [{"untrusted": {"$same_input_ref": "not-a-generated-marker"}}]
    for index in (1, 5):
        mutate(original, index, path, existing)
    static, projected, audit = reference(original)
    assert {"path": path, "reason": "existing_structural_reference_marker"} in audit["retained_fields"]
    assert gamma1._get(json.loads(projected["messages"][-1]["content"]), path) == existing
    assert gamma1.validate_reference_projection(projected, static, list(range(6)), audit)["passed"]


@pytest.mark.parametrize("corruption", ["dangling", "nested", "wrong_pointer", "target_altered", "outside_allowlist", "message_envelope"])
def test_generated_reference_corruption_is_rejected(corruption):
    static, projected, audit = reference(request())
    path = gamma1.ALLOWLIST[0]
    indices = list(range(6))
    if corruption == "dangling":
        del projected["messages"][1]
        indices.remove(1)
    elif corruption == "nested":
        mutate(projected, 1, path, {"$same_input_ref": "first_observation#" + path})
    elif corruption == "wrong_pointer":
        mutate(projected, 5, path, {"$same_input_ref": "first_observation#/observation/contract"})
    elif corruption == "target_altered":
        mutate(projected, 1, path, ["not the original"])
    elif corruption == "outside_allowlist":
        mutate(projected, 5, "/observation/team_model_budget", {"decisions": 99})
    else:
        projected["messages"][-1]["name"] = "changed-envelope"
    with pytest.raises(ValueError):
        gamma1.validate_reference_projection(projected, static, indices, audit)


def test_v044_history_removal_and_latest_unpresented_feedback_precede_references():
    ledger = OrdinaryFeedbackLedger(evidence_kind="cpu_programmed_fixture")
    old = register(ledger, 1)
    visible, _ = project_format_feedback(feedback_request(feedback_message(old)), ledger=ledger, member_id=MEMBER)
    present(ledger, 2, visible)
    new = register(ledger, 2)
    original = request()
    original["messages"][4:5] = [feedback_message(old), feedback_message(new)]
    snapshot = ledger.snapshot()
    selected, audit = gamma1.project_software_request(original, render=render, tokenizer=tokenizer,
        context_limit=100000, ledger=ledger, member_id=MEMBER)
    assert ledger.snapshot() == snapshot
    assert audit["format_feedback_projection"]["removed_indices"] == [4]
    assert audit["same_input_references"]["latest_observation_index"] == 5
    assert audit["selected_indices"] == [0, 1, 2, 3, 5, 6]
    assert audit["selected_reference_validation"]["passed"]
    assert feedback_message(old) not in selected["messages"]
    actual = json.loads(selected["messages"][4]["content"])["public_format_feedback"]
    assert actual["model_call_id"] == new["model_call_id"]
    assert ledger.snapshot()["records"][1]["presentations"] == []


def test_gamma0_direct_alias_and_v048_transport_budget_binding(tmp_path):
    assert gamma1.Gamma0Transport is gamma0.SoftwareContextTransport
    assert gamma1.project_gamma0_request is gamma0.project_software_request
    assert gamma1.presentation_identity("G0")["projection_version"] == gamma0.VERSION
    native = owner(capacity=100000)
    transport = gamma1.SoftwareContextTransport(native, tmp_path)
    original = request()
    with pytest.raises(ValueError, match="bound runner"):
        transport.prepare_for_budget(original)
    association = {"worker_id": MEMBER, "call_id": "cpu-only", "decision_index": 1}
    transport.bind_turn(MEMBER, association)
    prepared = transport.prepare_for_budget(original)
    projected = transport._prepared["projection"]
    assert projected["version"] == gamma1.VERSION
    assert projected["actual_presentation"]["world_runtime_library"] == "v047"
    assert prepared["selected_request_sha256"] == digest(json_bytes(transport._prepared["selected"]))
    response = transport.complete(original)
    assert response["http_status"] == 200 and len(native.calls) == 1
    assert json.loads((tmp_path / "request-00001/projection.json").read_text())["version"] == gamma1.VERSION
    transport.unbind_turn(MEMBER, association)
