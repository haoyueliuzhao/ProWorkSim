"""Finite synthetic JSON/AST evidence controls; never execute candidate code or models."""
import copy
import json

import pytest

from scripts import measure_organization_work_v039 as measure

BASE = "def public_value(value):\n    return value + 1\n"
CHANGED = "def public_value(value):\n    return value + 2\n"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def reference(obj, version):
    return {"object_id": obj, "version_id": version}


def fixture(root, *, origin="member_request", variant="positive", receiver_actual=True, message_body=True,
            direct=False, setup_edit=False):
    world = root / "prepared/world/control"
    baseline, child1, child2 = reference("baseline", "v1"), reference("child", "v1"), reference("child", "v2")
    parent1, parent2 = reference("parent", "v1"), reference("parent", "v2")
    changed = CHANGED if variant != "unchanged" else "# comment only\n" + BASE
    if variant == "complex":
        changed = "@some_runtime_decorator\n" + CHANGED
    before_parent = CHANGED if variant == "already_present" else BASE
    final_code = "def public_value(value):\n    return value + 9\n" if variant == "discarded" else changed
    for obj, version, code in [("baseline", "v1", BASE), ("child", "v1", BASE), ("child", "v2", changed),
                               ("parent", "v1", before_parent), ("parent", "v2", final_code)]:
        save(world / "versions" / obj / version / (obj + ".json"), {"files": {"product.py": code}, "included_patch_ids": []})
    groups = {name: {"executed": True, "passed": True} for name in ("upstream_regressions", "public_normal")}
    birth = {"kind": "member_spawned", "actor_id": "operator" if origin == "external_controller" else "member_001",
        "member_id": "member_003", "recipient": "member_003", "origin": origin,
        "born_by": "operator" if origin == "external_controller" else "member_001",
        "briefing": "Inspect the public function and report your finding." if origin == "member_request" else "",
        "initial_source_reference": baseline, "workspace_reference": child1, "initial_patch_id": None}
    events = [birth,
        {"kind": "edit", "actor_id": "member_003", "path": "product.py", "previous_reference": child1, "source_reference": child2},
        {"kind": "test", "actor_id": "member_003", "source_reference": child2, "groups": groups},
        {"kind": "work_message", "actor_id": "member_003", "recipient": "member_001", "task_id": "root_goal",
         "body": "The public test passed after changing public_value; please inspect the patch."},
        {"kind": "patch_fixed", "actor_id": "member_003", "author": "member_003", "patch_id": "patch-child",
         "source_reference": child2, "base_reference": baseline, "changed_paths": ["product.py"], "task_ids": []},
        {"kind": "integrate", "actor_id": "member_001", "patch_id": "patch-child", "input_reference": child2,
         "previous_reference": parent1, "source_reference": parent2, "included_patch_ids": ["patch-child"], "conflicts": []},
        {"kind": "test", "actor_id": "member_001", "source_reference": parent2, "groups": groups},
        {"kind": "submit", "actor_id": "member_003" if direct else "member_001", "delivery_id": "delivery-1",
         "source_reference": child2 if direct else parent2, "test_sequence": 3 if direct else 7,
         "included_patch_ids": ["patch-child"]}]
    if variant == "only_id":
        events[5] = {"kind": "read", "actor_id": "member_001", "path": "contract.md", "source_reference": parent1}
    if setup_edit:
        events[1].update(origin="diagnostic_setup", model_generated=False)
    for i, event in enumerate(events, 1):
        event.update(sequence=i, action_id=f"action-{i}")
    state = {"projects": {"SOFTWARE27": {"software": {"case": {
        "active_roles": ["member_001", "member_002"], "source_contract": {"contract_symbols": {"product.py": ["public_value"]}}}}}},
        "artifacts": {obj: {"filename": obj + ".json"} for obj in ("baseline", "parent", "child")},
        "software_events": events}
    save(world / "state.json", state)
    records, originals, experience = {}, [], []
    for i, event in enumerate(events, 1):
        if event["actor_id"] == "operator":
            continue
        actual = receiver_actual or event["actor_id"] != "member_001" or i < 4
        call_id = f"call-{i}"
        record = {"member": event["actor_id"], "attempt_started": actual,
            "reservation": {"preparation": {"selected_request_sha256": f"selected-{i}", "input_ids_sha256": f"input-{i}"}},
            "charge": {"reported_usage": {"total_tokens": 3}} if actual else None}
        records[call_id] = record
        if actual:
            originals.append({"call_id": call_id, "worker_id": event["actor_id"], "status": "success",
                "original_output_present": True, "experience_sequence": i * 10, "input_ids_sha256": f"input-{i}"})
        obs = {"actor_id": event["actor_id"], "contract": "Implement the public entry point.", "team_model_budget": {},
            "workspace_reference": child1 if event["actor_id"] == "member_003" else parent1,
            "own_initial_briefing": birth["briefing"] if event["actor_id"] == "member_003" else "", "messages": []}
        if event["actor_id"] == "member_001" and i >= 6:
            shown = copy.deepcopy(events[3])
            if not message_body:
                shown.pop("body")
            obs["messages"] = [shown]
        prefix = root / "raw-transport" / f"request-{i:05d}"
        save(prefix / "selected-request.json", {"messages": [{"role": "user", "content": json.dumps({"observation": obs})}]})
        save(prefix / "projection.json", {"selected_request_sha256": f"selected-{i}", "input_ids_sha256": f"input-{i}"})
        experience.append({"kind": "tool_call", "payload": {"model_call_id": call_id,
            "response": {"ok": True, "action_id": event["action_id"]}}})
    root.joinpath("experience.jsonl").write_text("\n".join(json.dumps(e) for e in experience) + "\n")
    save(root / "organization-evidence.json", {"original_attempts": originals,
        "usage_by_member": {"member_003": {"output_bearing_calls": 4}}})
    save(root / "slot-result.json", {"slot_id": "fixture", "status": "closed", "purpose": "organization_development",
        "R": 1, "submitted": True, "complete_delivery": True,
        "member_lifecycle": {"initial_members": ["member_001", "member_002"]}, "team_budget": {"model": {"records": records}}})
    return root


@pytest.mark.parametrize("origin", ["member_request", "external_controller"])
def test_real_unit_change_explicit_import_retention_and_current_test_form_limited_chain(tmp_path, origin):
    value = measure.measure_episode(fixture(tmp_path, origin=origin))
    assert value["totals"]["members_with_evidenced_peer_code_adoption"] == 1
    child = value["births"][0]
    assert child["origin"] == ("model" if origin == "member_request" else "external_controller")
    assert child["briefing"]["status"] == ("presented_in_actual_child_input" if origin == "member_request"
                                            else "not_applicable_external_no_briefing")
    assert child["briefing"]["public_root_and_budget_input"]["matches_birth_workspace"] is True
    link = child["code_work"]["code_adoption_links"][0]
    assert link["status"] == "evidenced_code_adoption"
    assert link["unit"]["initial_fingerprint"] != link["unit"]["published_unit"]["fingerprint"]
    assert link["receiver_before"]["fingerprint"] != link["final_unit"]["fingerprint"]
    assert link["final_quality"]["public_groups_executed"] is True
    assert link["final_quality"]["recorded_R"] == 1
    assert value["training_support"] is False
    assert value["new_test_or_acceptance_executions"] == 0
    info = child["information_help_candidates"][0]
    assert info["status"] == "needs_manual_review"
    assert info["preceding_child_test"]["sequence"] == 3
    assert info["receiver_actual_input"]["full_body"] is True
    assert info["semantic_consumption"] == "needs_manual_review"


@pytest.mark.parametrize("variant", ["only_id", "unchanged", "already_present", "discarded"])
def test_patch_id_or_non_novel_or_unretained_unit_never_proves_peer_use(tmp_path, variant):
    value = measure.measure_episode(fixture(tmp_path, variant=variant))
    assert value["totals"]["members_with_evidenced_peer_code_adoption"] == 0
    assert not any(link["status"] == "evidenced_code_adoption"
                   for link in value["births"][0]["code_work"]["code_adoption_links"])


@pytest.mark.parametrize("receiver_actual,message_body", [(False, True), (True, False)])
def test_prepared_unstarted_input_or_message_id_alone_is_not_received_information(tmp_path, receiver_actual, message_body):
    value = measure.measure_episode(fixture(tmp_path, receiver_actual=receiver_actual, message_body=message_body))
    info = value["births"][0]["information_help_candidates"][0]
    assert info["status"] == "unknown_unclosed_relation"
    assert info["receiver_actual_input"] is None
    assert value["totals"]["information_candidates_needing_manual_review"] == 0


def test_diagnostic_setup_edit_is_not_model_authored_change(tmp_path):
    value = measure.measure_episode(fixture(tmp_path, setup_edit=True))
    assert value["totals"]["members_with_evidenced_peer_code_adoption"] == 0
    assert value["births"][0]["code_work"]["changed_public_units"] == []
    assert value["births"][0]["actual_work"]["production_edits"] == []


def test_new_member_direct_delivery_stays_separate_from_peer_adoption(tmp_path):
    value = measure.measure_episode(fixture(tmp_path, direct=True))
    assert value["totals"]["members_with_direct_final_delivery"] == 1
    assert value["totals"]["members_with_evidenced_peer_code_adoption"] == 0


def test_complex_ast_is_unknown_instead_of_invented_contribution(tmp_path):
    value = measure.measure_episode(fixture(tmp_path, variant="complex"))
    code = value["births"][0]["code_work"]
    assert value["totals"]["members_with_evidenced_peer_code_adoption"] == 0
    assert code["unknown_or_unsupported"][0]["reason"] == "unsupported_or_unavailable_public_unit"


def test_no_birth_keeps_skipped_slot_without_loading_unneeded_inputs(tmp_path, monkeypatch):
    save(tmp_path / "slot-result.json", {"status": "closed", "slot_id": "retained-skipped-slot", "R": 0,
        "member_lifecycle": {"initial_members": ["member_001", "member_002"]},
        "external_intervention": {"status": "skipped", "reason": "natural_terminal"}})
    save(tmp_path / "prepared/world/control/state.json", {"projects": {"SOFTWARE27": {"software": {"case": {}}}},
        "software_events": []})
    def unexpected_input_scan(*args, **kwargs):
        raise AssertionError("No born member means no input scan is needed")
    monkeypatch.setattr(measure, "Inputs", unexpected_input_scan)
    value = measure.measure_episode(tmp_path)
    assert value["slot_id"] == "retained-skipped-slot"
    assert value["status"] == "no_new_births"
    assert value["totals"]["new_members"] == 0
    assert value["external_intervention"] == {"status": "skipped", "reason": "natural_terminal"}
