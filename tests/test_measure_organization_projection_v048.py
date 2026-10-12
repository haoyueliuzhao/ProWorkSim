"""Finite independent G1 source/binding controls; mock bytes are not model tokens."""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim import software_context_v044 as gamma0
from proworksim import software_context_v048 as gamma1
from proworksim.software_feedback_v044 import OrdinaryFeedbackLedger
from proworksim.storage import digest, json_bytes
from scripts import measure_organization_projection_v047 as previous
from scripts import measure_organization_projection_v048 as measured
from tests.test_measure_organization_budget_v046 import capacity_binding, seal
from test_software_context_v034 import render, tokenizer
from test_software_context_v048 import MEMBER, request


def save(folder, name, value):
    (folder / name).write_bytes(json_bytes(value))


def fixture(tmp_path, representation="Gamma1"):
    folder = tmp_path / "raw-transport/request-00001"
    folder.mkdir(parents=True)
    original = request()
    original["max_tokens"] = 2048
    original["tools"] = [{"type": "function", "function": {"name": "read_test_result", "parameters": {"type": "object"}}}]
    for index in (1, 5):
        payload = json.loads(original["messages"][index]["content"])
        payload["observation"]["interface_revision"] = measured.PAGE_INTERFACE
        original["messages"][index]["content"] = json.dumps(payload)
    original["messages"][2:2] = [
        {"role": "assistant", "content": "old", "tool_calls": [{"id": "old", "function": {"name": "read"}}]},
        {"role": "tool", "tool_call_id": "old", "content": "old complete feedback" * 1000}]
    ledger = OrdinaryFeedbackLedger(evidence_kind="cpu_programmed_fixture").snapshot()
    projector = gamma1.project_software_request if representation == "Gamma1" else gamma0.project_software_request
    selected, projection = projector(original, render=render, tokenizer=tokenizer,
        context_limit=18432, ledger=ledger, member_id=MEMBER)
    assert projection["fits"] and projection["removed_indices"] == [2, 3]
    cap = capacity_binding()
    prep = seal({"context_limit": 18432, "reserved_output_tokens": 2048, "fits": True,
        "prompt_tokens": projection["selected_prompt_tokens"], "actor_identity": cap["capacity_actor_identity"],
        "recipe_sha256": cap["capacity_recipe_sha256"], "window_id": "organization-v047:fixture",
        "original_request_sha256": digest(json_bytes(original)), "selected_request_sha256": digest(json_bytes(selected)),
        "input_ids_sha256": projection["input_ids_sha256"], "rendered_prompt_sha256": projection["rendered_prompt_sha256"]}, "preparation_sha256")
    ids = tokenizer(render(selected)[0])["input_ids"]
    usage = {"prompt_tokens": len(ids), "completion_tokens": 1, "total_tokens": len(ids) + 1}
    body = {"id": "cpu-response", "actor_identity": prep["actor_identity"], "online_window_id": prep["window_id"],
        "token_trace": {"input_ids": ids, "output_ids": [1]}, "usage": usage}
    record = {"reservation": {"preparation": prep}, "charge": {"reported_usage": usage,
        "charged_tokens": usage["total_tokens"], "response_id": body["id"], "response_body_sha256": digest(json_bytes(body))}}
    call = {"call_id": "cpu-call", "member": MEMBER, "experience_sequence": 30,
        "path": str(folder / "selected-request.json"), "selected_request_sha256": prep["selected_request_sha256"],
        "input_ids_sha256": prep["input_ids_sha256"]}
    report = json.loads(original["messages"][-1]["content"])["observation"]["initial_diagnostics"][0]
    for name, value in (("original-request.json", original), ("selected-request.json", selected),
        ("projection.json", projection), ("response.json", {"http_status": 200, "body": body}),
        ("feedback-lifecycle-before.json", ledger)):
        save(folder, name, value)
    return SimpleNamespace(folder=folder, original=original, selected=selected, projection=projection,
        record=record, call=call, cap=cap, ledger=ledger, initial={report["diagnostic_id"]: report},
        assignments={MEMBER: [report["diagnostic_id"]]}, representation=representation)


def audit(value, **kwargs):
    return measured.audit_projection(value.call, value.record, value.initial, value.assignments,
        value.ledger, capacity_binding=value.cap, representation=value.representation, **kwargs)


@pytest.mark.parametrize("representation", ["Gamma0", "Gamma1"])
def test_correct_assigned_representation_and_actual_original_trace_are_verified(tmp_path, representation):
    value = fixture(tmp_path, representation)
    result = audit(value)
    assert result["status"] == "verified", result
    assert result["representation"] == {"representation": representation, "candidate_sha256": gamma1.CANDIDATE_SHA256}
    assert result["latest_complete_round_present"] is True
    if representation == "Gamma1":
        assert result["generated_references"] == 5
        assert result["selected_reference_validation"]["passed"]
        assert result["protected_reference_validation"]["passed"]
        assert result["protected_encoding_recomputed"] is False
    else:
        old = previous.audit_projection(value.call, value.record, value.initial, value.assignments,
            value.ledger, capacity_binding=value.cap)
        assert {k: v for k, v in result.items() if k not in {"representation", "uses_v044_feedback"}} == old


@pytest.mark.parametrize("change", ["candidate", "wrong_gamma", "first_target", "reference_path", "other_member",
    "current_budget", "initial_permission", "static_metadata", "feedback_timeline", "reference_receipt", "root_receipt",
    "selected_indices", "round_receipt", "protected_receipt", "actual_trace", "actual_charge", "capacity_seal"])
def test_reconstruction_or_original_binding_corruption_is_rejected(tmp_path, change):
    value = fixture(tmp_path)
    if change == "candidate":
        assert audit(value, candidate_sha256="0" * 64)["status"] == "violation"
        return
    if change == "wrong_gamma":
        value.representation = "Gamma0"
    elif change in {"first_target", "reference_path", "other_member", "current_budget"}:
        index = 1 if change == "first_target" else -1
        payload = json.loads(value.selected["messages"][index]["content"])
        observation = payload["observation"]
        if change == "first_target":
            observation["architecture"]["stage_plan"][0]["limits"]["max_total_tokens"] += 1
        elif change == "reference_path":
            observation["patches"] = {"$same_input_ref": "first_observation#/observation/member_registry"}
        elif change == "other_member":
            observation["actor_id"] = "member_002"
        else:
            observation["team_model_budget"]["decisions"] += 1
        value.selected["messages"][index]["content"] = json.dumps(payload)
        save(value.folder, "selected-request.json", value.selected)
    elif change == "initial_permission":
        value.assignments[MEMBER] = []
    elif change == "static_metadata":
        value.projection["deduplication"]["removed_values"] = []
        save(value.folder, "projection.json", value.projection)
    elif change == "feedback_timeline":
        wrong = copy.deepcopy(value.ledger)
        wrong["evidence_kind"] = "actual_generation_settled"
        save(value.folder, "feedback-lifecycle-before.json", wrong)
    elif change == "reference_receipt":
        value.projection["same_input_references"]["generated_references"][0]["value_sha256"] = "0" * 64
        save(value.folder, "projection.json", value.projection)
    elif change == "root_receipt":
        value.projection["same_input_references"]["root_identity"]["root_goal_id"] = "unrelated_root"
        save(value.folder, "projection.json", value.projection)
    elif change == "selected_indices":
        value.projection["selected_indices"][-1] -= 1
        save(value.folder, "projection.json", value.projection)
    elif change == "round_receipt":
        value.projection["context_stage_projection"]["measurements"][0]["prompt_tokens"] = 5
        save(value.folder, "projection.json", value.projection)
    elif change == "protected_receipt":
        value.projection["protected_request_sha256"] = "0" * 64
        save(value.folder, "projection.json", value.projection)
    elif change == "actual_trace":
        response = json.loads((value.folder / "response.json").read_text())
        response["body"]["token_trace"]["input_ids"][0] += 1
        save(value.folder, "response.json", response)
    elif change == "actual_charge":
        value.record["charge"]["charged_tokens"] += 1
    else:
        value.record["reservation"]["preparation"]["preparation_sha256"] = "0" * 64
    assert audit(value)["status"] == "violation", change


def test_missing_actual_response_stays_unresolved_and_public_api_keeps_assignment(tmp_path):
    value = fixture(tmp_path)
    (value.folder / "response.json").unlink()
    assert audit(value)["status"] == "unresolved"
    incomplete = measured.measure_episode(tmp_path, representation="Gamma1", candidate_sha256=gamma1.CANDIDATE_SHA256)
    assert incomplete["status"] == "unresolved"
    assert incomplete["representation"] == {"representation": "Gamma1", "candidate_sha256": gamma1.CANDIDATE_SHA256}
    assert incomplete["mechanism_gate_inputs"]["resolved"] is False
