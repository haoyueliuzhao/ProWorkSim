"""Finite new protocol binding and phase arithmetic controls, no native model."""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim.software_context_v044 import project_software_request
from proworksim.storage import digest, json_bytes
from scripts import measure_organization_budget_v047 as budget
from scripts import measure_organization_projection_v047 as projection
from scripts import measure_organization_work_v047 as work
from tests.test_measure_organization_budget_v046 import capacity_binding, seal
from tests.test_measure_organization_projection_v046 import fixture as projection_fixture
from tests.test_stage_budget_v047 import actual, advance, budget as stage_budget


@pytest.mark.parametrize("total", [250000, 500000])
def test_effective_team_budget_is_distinct_from_unchanged_personal_500k_meter(total):
    cap = capacity_binding()
    row = {"slot_id": "fixture", "version": "software-organization-runtime-v0.47", "condition": "S1",
           "team_token_budget": total, "actor_identity": cap["capacity_actor_identity"]}
    ledger = {"limits": {"max_decisions": 128, "max_attempts": 128, "max_total_tokens": total},
              "binding": {"actor_identity": row["actor_identity"], "recipe_sha256": cap["capacity_recipe_sha256"],
                          "window_id": "organization-v047:fixture"}}
    assert budget.validate_episode_capacity(cap, result=row, budget=ledger)["context_limit"] == 18432
    assert budget.MEMBER_TOKEN_CAP == 500000
    ledger["binding"]["window_id"] = "organization-v045:fixture"
    with pytest.raises(ValueError):
        budget.validate_episode_capacity(cap, result=row, budget=ledger)


def test_new_architecture_interface_keeps_exact_lifecycle_and_old_version_is_rejected(tmp_path):
    value, cap = projection_fixture(tmp_path)
    original = json.loads((value.folder / "original-request.json").read_text())
    body = json.loads(original["messages"][1]["content"])
    body["observation"]["interface_revision"] = projection.PAGE_INTERFACE
    original["messages"][1]["content"] = json.dumps(body)
    selected, projected = project_software_request(original, ledger=value.ledger, member_id="member_001",
        render=lambda item: (json.dumps(item, ensure_ascii=False), None, None),
        tokenizer=lambda text, **kwargs: {"input_ids": list(range(len(text)))}, context_limit=18432)
    prep = value.record["reservation"]["preparation"]
    prep.update(window_id="organization-v047:fixture", prompt_tokens=projected["selected_prompt_tokens"],
                original_request_sha256=digest(json_bytes(original)), selected_request_sha256=digest(json_bytes(selected)),
                input_ids_sha256=projected["input_ids_sha256"], rendered_prompt_sha256=projected["rendered_prompt_sha256"])
    seal(prep, "preparation_sha256")
    value.record["charge"]["reported_usage"]["prompt_tokens"] = prep["prompt_tokens"]
    value.call.update(selected_request_sha256=prep["selected_request_sha256"], input_ids_sha256=prep["input_ids_sha256"])
    for name, content in (("original-request.json", original), ("selected-request.json", selected), ("projection.json", projected)):
        (value.folder / name).write_bytes(json_bytes(content))
    result = projection.audit_projection(value.call, value.record, value.initial, value.assignments, value.ledger, capacity_binding=cap)
    assert result["status"] == "verified", result["issues"]
    prep["window_id"] = "organization-v045:fixture"
    seal(prep, "preparation_sha256")
    assert projection.audit_projection(value.call, value.record, value.initial, value.assignments, value.ledger, capacity_binding=cap)["status"] == "violation"


def test_stage_views_bind_same_ledger_and_only_forward_carry():
    value, state, plan = stage_budget("I2")
    actual(value, "member_001", "a", 80000, 60000)
    view = value.stage_snapshot("member_001")
    assert budget.validate_stage_snapshot(view, value.snapshot(), condition="I2", token_budget=250000)["available_tokens"] == 27500
    changed = copy.deepcopy(view)
    changed["available_tokens"] += 1000
    seal(changed, "state_sha256")
    with pytest.raises(ValueError, match="same_team_ledger"):
        budget.validate_stage_snapshot(changed, value.snapshot(), condition="I2", token_budget=250000)
    actual(value, "member_002", "b", 10000, 9000)
    advance(state, plan, 1)
    actual(value, "member_001", "selection", 170000, 160000)
    team = {"model": value.snapshot(), "tests": {"limit": 32, "used": 0, "remaining": 32, "records": []}}
    facts = budget.validate_stage_accounting({"condition": "I2", "team_token_budget": 250000}, team)
    assert facts["unique_team_charged_tokens"] == 229000
    assert [stage["usage_in_this_stage"]["charged_tokens"] for stage in facts["stages"]] == [69000, 160000]
    wrong = copy.deepcopy(team)
    wrong["model"]["records"]["selection"]["stage_id"] = "generate"
    seal(wrong["model"], "state_sha256")
    with pytest.raises(ValueError):
        budget.validate_stage_accounting({"condition": "I2", "team_token_budget": 250000}, wrong)


def test_finish_stage_feedback_is_not_voluntary_retirement():
    row = {"member": "member_001", "experience_sequence": 9, "feedback_id": "feedback-9",
           "tool": "finish_stage", "feedback_ok": True, "actual_originating_generation_bound": True,
           "_value": {"result": {"status": "stage_complete", "member_id": "member_001",
                                  "stage_id": "generate", "permanent_retirement": False}}}
    value = projection.no_followup_reason(row, {"status": "closed", "boundary": {}}, [], {"records": {}}, "fixture.jsonl")
    assert value["reason"] == "stage_boundary"
    assert value["stage_boundary_attribution"]["permanent_retirement"] is False
    row["_value"]["result"]["permanent_retirement"] = True
    assert projection.no_followup_reason(row, {"status": "closed", "boundary": {}}, [], {"records": {}}, "fixture.jsonl")["reason"] == "unknown_no_actual_followup"


def test_whole_file_application_survives_author_retirement_and_requires_exact_after_files(tmp_path):
    old, fixed, applied = ({"object_id": name, "version_id": "v1"} for name in ("old", "fixed", "applied"))
    contents = {"old": {"event_store.py": "original"}, "fixed": {"event_store.py": "changed helper"},
                "applied": {"event_store.py": "changed helper"}}
    for name, files in contents.items():
        (tmp_path / (name + ".json")).write_bytes(json_bytes({"files": files}))
    files_hash = digest(json_bytes(contents["fixed"]))
    event = {"sequence": 10, "kind": "candidate_adopted", "actor_id": "member_001", "stage_id": "select",
             "patch_id": "p", "input_reference": fixed, "previous_reference": old, "source_reference": applied,
             "files_sha256": files_hash, "selected_candidate_files_sha256": files_hash,
             "exact_files_match": True, "native_model_action": True}
    events = [event, {"sequence": 11, "kind": "test", "actor_id": "member_001", "source_reference": applied},
              {"sequence": 12, "kind": "submit", "actor_id": "member_001", "source_reference": applied}]
    data = SimpleNamespace(events=events,
        registry={"member_001": {"status": "live"}, "member_002": {"status": "retired", "retirement_sequence": 5}},
        software={"patches": {"p": {"patch_id": "p", "author": "member_002", "source_reference": fixed, "files_sha256": files_hash}},
                  "deliveries": [{"source_reference": applied}]},
        bound=lambda row: {"call_id": "synthetic-" + str(row["sequence"])}, point=lambda row: {"sequence": row["sequence"]},
        versions=SimpleNamespace(get=lambda reference: (contents[reference["object_id"]], str(tmp_path / (reference["object_id"] + ".json")), None)))
    rows, gaps = work.exact_candidate_applications(data)
    assert not gaps and len(rows) == 1
    assert rows[0]["cross_member"] and rows[0]["nonidentity_file_application"]
    assert rows[0]["changed_paths"] == ["event_store.py"]
    assert rows[0]["tested_submission_is_final_locked_delivery"] is True
    contents["applied"]["event_store.py"] = "different candidate"
    rows, gaps = work.exact_candidate_applications(data)
    assert rows == [] and len(gaps) == 1
