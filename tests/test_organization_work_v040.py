"""Finite JSON/AST controls for v040; no source execution, model call or GPU use."""
import copy
import json

import pytest

from scripts import measure_organization_work_v040 as measure

BASE = "def public_value(value):\n    return value + 1\n"
CHANGED = "def public_value(value):\n    return value + 2\n"
OTHER = "def public_value(value):\n    return value + 9\n"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def ref(obj, version):
    return {"object_id": obj, "version_id": version}


def fixture(root, *, variant="positive", shared=False, delay_shared=False, message=False,
            patch_visible=True, actual_receiver=True, submit=True, passed=True, rerun_visible=False):
    control = root / "prepared/world/control"
    baseline, a1, a2 = ref("baseline", "v1"), ref("source", "v1"), ref("source", "v2")
    b1, b2, b3 = ref("receiver", "v1"), ref("receiver", "v2"), ref("receiver", "v3")
    changed = "# irrelevant comment\n" + BASE if variant == "unchanged" else CHANGED
    before = CHANGED if variant == "already_present" else BASE
    integrated = OTHER if variant == "wrong_integration" else changed
    for obj, version, code in [("baseline", "v1", BASE), ("source", "v1", BASE), ("source", "v2", changed),
                               ("receiver", "v1", before), ("receiver", "v2", integrated), ("receiver", "v3", changed)]:
        save(control / "versions" / obj / version / (obj + ".json"), {"files": {"product.py": code}})
    diagnostics = {}
    for group in ("a", "b"):
        identifier = "fixture:diagnostic_" + group
        diagnostics[identifier] = {"diagnostic_id": identifier, "group_id": "diagnostic_" + group,
            "origin": "environment_initial_diagnostic", "model_generated": False, "autonomous_discovery": False,
            "source_reference": baseline, "initial_source_reference": baseline, "files_sha256": "baseline-files",
            "source_binding": {"files_sha256": "baseline-files"}, "executed": True, "passed": False,
            "tests": [{"test_id": "failure_" + group, "request": {"value": 1}, "observed": 2, "expected": 3, "passed": False},
                      {"test_id": "pass_" + group, "passed": True}]}
    ids = list(diagnostics)
    assignments = {"member_001": ids if shared else [ids[0]], "member_002": ids if shared else [ids[1]]}
    public_reports = {key: {**copy.deepcopy(value), "origin": "member_public_test_execution", "source_reference": b1}
                      for key, value in diagnostics.items()}
    for value in public_reports.values():
        value.pop("initial_source_reference")
    groups = {name: {"executed": True, "passed": passed} for name in measure.PUBLIC_GROUPS}
    events = [
        {"kind": "read", "actor_id": "member_001", "source_reference": a1, "path": "contract.md"},
        {"kind": "test", "actor_id": "member_002", "source_reference": b1, "groups": groups,
         "public_diagnostics": public_reports},
        {"kind": "read", "actor_id": "member_002", "source_reference": b1, "path": "contract.md"},
        {"kind": "edit", "actor_id": "member_001", "source_reference": a2, "previous_reference": a1, "path": "product.py"},
        {"kind": "patch_fixed", "actor_id": "member_001", "source_reference": a2, "base_reference": baseline,
         "patch_id": "patch-a", "author": "member_001", "changed_paths": ["product.py"]},
        {"kind": "work_message", "actor_id": "member_001", "recipient": "member_002", "task_id": "root_goal",
         "body": "fixture:diagnostic_a: public_value(1) returned 2; the expected value is 3."} if message else
        {"kind": "read", "actor_id": "member_001", "source_reference": a2, "path": "contract.md"},
        {"kind": "integrate", "actor_id": "member_002", "patch_id": "patch-a", "input_reference": a2,
         "previous_reference": b1, "source_reference": b2, "included_patch_ids": ["patch-a"], "conflicts": []},
        {"kind": "test", "actor_id": "member_002", "source_reference": b3, "groups": groups},
    ]
    if submit:
        events.append({"kind": "submit", "actor_id": "member_002", "delivery_id": "delivery-1",
                       "source_reference": b3, "test_sequence": 8, "included_patch_ids": ["patch-a"]})
    for index, event in enumerate(events, 1):
        event.update(sequence=index, action_id="action-" + str(index))
    if variant == "setup_edit":
        events[3].update(origin="diagnostic_setup", model_generated=False)
    registry = {member: {"origin": "initial_configuration", "initial_source_reference": baseline}
                for member in assignments}
    state = {"projects": {"SOFTWARE27": {"software": {"registry": registry, "initial_diagnostics": diagnostics,
        "initial_diagnostic_assignments": assignments, "case": {
            "source_contract": {"contract_symbols": {"product.py": ["public_value"]}}}}}},
        "artifacts": {obj: {"filename": obj + ".json"} for obj in ("baseline", "source", "receiver")},
        "software_events": events}
    save(control / "state.json", state)
    records, originals, experience = {}, [], []
    for index, event in enumerate(events, 1):
        member, call_id = event["actor_id"], "call-" + str(index)
        actual = actual_receiver or member != "member_002"
        records[call_id] = {"member": member, "attempt_started": actual,
            "reservation": {"preparation": {"selected_request_sha256": "selected-" + str(index),
                                             "input_ids_sha256": "input-" + str(index)}},
            "charge": {"reported_usage": {"total_tokens": 3}} if actual else None}
        if actual:
            originals.append({"call_id": call_id, "worker_id": member, "status": "success", "original_output_present": True,
                              "experience_sequence": index * 10, "input_ids_sha256": "input-" + str(index)})
        visible_ids = assignments[member]
        if delay_shared and member == "member_002" and index < 7:
            visible_ids = [ids[1]]
        obs = {"actor_id": member, "initial_diagnostics": [diagnostics[i] for i in visible_ids], "messages": [], "patches": []}
        if member == "member_002" and index >= 7:
            obs["patches"] = [{"patch_id": "patch-a", "source_reference": a2}] if patch_visible else [{"patch_id": "patch-a"}]
            obs["messages"] = [events[5]] if message else []
        messages = [{"role": "user", "content": json.dumps({"observation": obs})}]
        if rerun_visible and index == (7 if rerun_visible == "same_input" else 3):
            messages.insert(0, {"role": "tool", "content": json.dumps({"ok": True, "action_id": "action-2",
                                                                      "result": {"public_diagnostics": public_reports}})})
        prefix = root / "raw-transport" / f"request-{index:05d}"
        save(prefix / "selected-request.json", {"messages": messages})
        save(prefix / "projection.json", {"selected_request_sha256": "selected-" + str(index), "input_ids_sha256": "input-" + str(index)})
        experience.append({"kind": "tool_call", "payload": {"model_call_id": call_id,
                            "response": {"ok": True, "action_id": event["action_id"]}}})
    (root / "experience.jsonl").write_text("\n".join(json.dumps(e) for e in experience) + "\n")
    save(root / "organization-evidence.json", {"original_attempts": originals})
    save(root / "slot-result.json", {"slot_id": "fixture", "status": "closed", "purpose": "organization_development",
        "R": int(submit and passed), "submitted": submit, "complete_delivery": submit and passed,
        "member_lifecycle": {"initial_members": list(registry)}, "team_budget": {"model": {"records": records}}})
    return root


def test_initial_members_form_bound_changed_code_actual_input_import_test_chain(tmp_path):
    value = measure.measure_episode(fixture(tmp_path))
    assert value["has_evidenced_cross_member_chain"] is True
    assert value["totals"]["initial_members"] == 2
    assert value["totals"]["model_requested_births"] == 0
    chain = value["program_work_chains"][0]
    assert chain["source_member"] == "member_001"
    assert chain["recipient"] == "member_002"
    assert chain["recipient_actual_input"]["call_id"] == "call-7"
    assert chain["receiver_before"]["fingerprint"] != chain["integrated_unit"]["fingerprint"]
    assert chain["final_fixed_relation"]["closed"] is True
    assert value["new_model_calls"] == value["new_test_or_acceptance_executions"] == 0
    assert value["training_support"] is False
    assert value["environment_preparation"]["initial_diagnostics_are_member_discoveries"] is False


@pytest.mark.parametrize("passed,submit", [(False, True), (True, False)])
def test_use_exists_separately_from_test_success_and_final_delivery(tmp_path, passed, submit):
    value = measure.measure_episode(fixture(tmp_path, passed=passed, submit=submit))
    assert value["has_evidenced_cross_member_chain"] is True
    chain = value["program_work_chains"][0]
    assert chain["test_result"]["public_groups_passed"] is passed
    assert chain["final_fixed_relation"]["closed"] is submit


@pytest.mark.parametrize("variant", ["unchanged", "already_present"])
def test_comments_or_already_present_unit_are_complete_negative_structural_paths(tmp_path, variant):
    value = measure.measure_episode(fixture(tmp_path, variant=variant))
    assert value["has_evidenced_cross_member_chain"] is False
    assert value["program_work_chains"] == []


@pytest.mark.parametrize("change", ["id_only", "unstarted", "wrong_integration", "setup_edit"])
def test_incomplete_or_environment_paths_remain_unknown_never_positive(tmp_path, change):
    value = measure.measure_episode(fixture(tmp_path, variant=change, patch_visible=change != "id_only",
                                            actual_receiver=change != "unstarted"))
    assert value["has_evidenced_cross_member_chain"] is None
    assert value["program_work_chains"] == []


@pytest.mark.parametrize("shared,delay,prior,same", [(False, False, False, False), (True, False, True, True), (True, True, False, True)])
def test_initial_report_origin_and_actual_recipient_knowledge_are_not_inferred_from_assignment(tmp_path, shared, delay, prior, same):
    value = measure.measure_episode(fixture(tmp_path, variant="unchanged", message=True, shared=shared, delay_shared=delay))
    assert value["has_evidenced_cross_member_chain"] is None
    candidate = value["information_work_candidates"][0]
    assert candidate["status"] == "needs_manual_review"
    relation = candidate["referenced_initial_diagnostics"][0]
    assert relation["sender_report_visible_before_share"] is True
    assert relation["initial_diagnostic_is_member_discovery"] is False
    assert relation["recipient_initially_assigned"] is shared
    assert relation["recipient_had_same_initial_fact_before_message_input"] is prior
    assert relation["recipient_independently_received_same_initial_fact_in_same_input"] is same
    assert relation["novel_information_benefit"] == "not_inferred"


@pytest.mark.parametrize("route,prior,same", [(False, False, False), (True, True, False), ("same_input", False, True)])
def test_own_reexecution_counts_as_known_only_after_real_result_reaches_selected_input(tmp_path, route, prior, same):
    value = measure.measure_episode(fixture(tmp_path, variant="unchanged", message=True, rerun_visible=route))
    member = value["member_work"]["member_002"]
    assert member["own_public_diagnostic_executions"]
    assert member["same_initial_fact_self_reacquired"] == (["fixture:diagnostic_a"] if route else [])
    relation = value["information_work_candidates"][0]["referenced_initial_diagnostics"][0]
    assert relation["recipient_had_same_initial_fact_before_message_input"] is prior
    assert relation["recipient_independently_received_same_initial_fact_in_same_input"] is same
    assert value["has_evidenced_cross_member_chain"] is None


def test_missing_actual_input_and_nonclosed_results_never_become_negative(tmp_path):
    folder = fixture(tmp_path, variant="unchanged")
    (folder / "raw-transport/request-00003/selected-request.json").unlink()
    value = measure.measure_episode(folder)
    assert value["has_evidenced_cross_member_chain"] is None
    assert value["measurement_gaps"]
    save(folder / "slot-result.json", {"status": "running"})
    assert measure.measure_episode(folder)["has_evidenced_cross_member_chain"] is None
    (folder / "slot-result.json").unlink()
    assert measure.measure_episode(folder)["has_evidenced_cross_member_chain"] is None
