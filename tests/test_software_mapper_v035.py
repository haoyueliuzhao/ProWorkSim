"""Targeted CPU controls; synthetic records are not current-policy support."""
import copy
import json

import pytest

from proworksim.software_mapper_v035 import CLASS_ORDER, map_software_method, mapping_spec
from proworksim.software_method_evidence_v035 import _Evidence, _contract_definition_fingerprints
from proworksim.storage import digest, json_bytes


def sha(value):
    return digest(json_bytes(value))


def sealed(value):
    value = copy.deepcopy(value)
    value.pop("evidence_sha256", None)
    value["evidence_sha256"] = sha(value)
    return value


def mapping_pair(training=True):
    window = {key: "cpu-" + key for key in ["window_id", "xi_id", "xi_fingerprint", "gamma_fingerprint", "team_policy_fingerprint"]}
    case = {"training_eligible": training, "usage": "policy_training" if training else "model_interface_development"}
    rollout = {"rollout_id": "cpu-rollout", "manifest_sha256": "cpu-manifest", "window": window,
               "manifest": {"scenario": {"variation": {"software_case": case}}},
               "online_scope": {"purpose": case["usage"], "source_training_admission": training,
                                "optimizer_update_allowed": training},
               "members": {member: {"actor_id": member, "origin": "target_model"} for member in ["member_a", "member_b"]},
               "work_validity": {"value": True}}
    evidence = {"rollout_id": rollout["rollout_id"], "rollout_sha256": sha(rollout),
                "manifest_sha256": rollout["manifest_sha256"], "window": window,
                "actual_visibility_complete": True,
                "members": {member: {"member_id": member, "origin": "target_model", "own_action_count": 3,
                                     "own_action_tokens": 15, "complete_actor_trajectory": True,
                                     "own_targets_sha256": sha([member, "actual-own-targets"]),
                                     "actual_input_bindings_complete": True} for member in rollout["members"]},
                "delivery_chain": {"verified": True, "current_test_feedback_seen_before_submit": True,
                                   "retained_own_production_edit_paths": ["reader.py"],
                                   "peer_integrations": [], "peer_fixed_content_acquisitions": [],
                                   "unresolved_peer_dependencies": []}}
    return rollout, sealed(evidence)


def test_two_classes_are_frozen_and_own_method_keeps_peer_own_targets():
    rollout, evidence = mapping_pair()
    before = copy.deepcopy(rollout)
    mapped = map_software_method(rollout, evidence)
    assert mapped["class_id"] == CLASS_ORDER[0] and len(mapping_spec()["class_order"]) == 2
    assert all(row["support_eligible"] and row["base_actor_targets_unchanged"] for row in mapped["member_projections"].values())
    assert rollout == before


def test_peer_product_route_does_not_require_recipient_to_edit_code():
    rollout, evidence = mapping_pair()
    evidence["delivery_chain"].update(retained_own_production_edit_paths=[], peer_integrations=[{
        "qualifying_fixed_product_consumption": True, "file_materialized": True,
        "import_receipt_presented": True, "source_text_presented": False}])
    mapped = map_software_method(rollout, sealed(evidence))
    assert mapped["class_id"] == CLASS_ORDER[1]


@pytest.mark.parametrize("failure", ["invalid", "unknown", "missing_input", "unseen_test", "manual_copy", "missing_ancestor", "peer_overwritten"])
def test_failure_uncertainty_and_overwritten_payload_stay_unmapped_without_removing_base(failure):
    rollout, evidence = mapping_pair()
    if failure in {"invalid", "unknown"}:
        rollout["work_validity"]["value"] = False if failure == "invalid" else None
        evidence["rollout_sha256"] = sha(rollout)
    elif failure == "missing_input":
        evidence["actual_visibility_complete"] = False
    elif failure == "unseen_test":
        evidence["delivery_chain"]["current_test_feedback_seen_before_submit"] = False
    elif failure == "manual_copy":
        evidence["delivery_chain"]["peer_fixed_content_acquisitions"] = [{"patch_id": "peer"}]
    elif failure == "missing_ancestor":
        evidence["delivery_chain"]["unresolved_peer_dependencies"] = ["peer"]
    else:
        evidence["delivery_chain"]["peer_integrations"] = [{"qualifying_fixed_product_consumption": False}]
    result = map_software_method(rollout, sealed(evidence))
    assert result["status"] == "unmapped" and result["class_id"] is None
    assert all(row["own_action_tokens"] == 15 and row["base_actor_targets_unchanged"] for row in result["member_projections"].values())


def test_development_mapping_cannot_be_promoted_to_training_or_support():
    rollout, evidence = mapping_pair(training=False)
    result = map_software_method(rollout, evidence)
    assert result["status"] == "mapped" and not result["composition_support_eligible"]
    assert not any(p["support_eligible"] for p in result["member_projections"].values())
    rollout["manifest"]["scenario"]["variation"]["software_case"].update(training_eligible=True, usage="policy_training")
    with pytest.raises(ValueError, match="another exact"):
        map_software_method(rollout, evidence)


def test_different_xi_gamma_first_member_window_or_tokens_cannot_reuse_evidence():
    rollout, evidence = mapping_pair()
    for key in rollout["window"]:
        changed = copy.deepcopy(rollout)
        changed["window"][key] += "-different"
        with pytest.raises(ValueError, match="another exact"):
            map_software_method(changed, evidence)
    changed = copy.deepcopy(evidence)
    changed["members"]["member_a"]["own_action_tokens"] += 1
    with pytest.raises(ValueError, match="seal"):
        map_software_method(rollout, changed)
    with pytest.raises(ValueError, match="specification"):
        map_software_method(rollout, evidence, spec={"class_order": ["invented"]})


def visible_fixture(tmp_path):
    result = {"ok": True, "result": {"passed": True, "executed": True,
              "groups": {"public_normal": {"tests": [{"test_id": "public", "status": "passed"}]}}}}
    selected = {"model": "explicit-cpu-fixture", "max_tokens": 4, "messages": [
        {"role": "system", "content": "Fixture"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "testcall", "function": {"name": "run_tests", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "testcall", "content": json.dumps(result)},
        {"role": "user", "content": json.dumps({"observation": {"contract": "Full contract"}})}]}
    original = copy.deepcopy(selected)
    original["messages"][1:1] = [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "older", "function": {"name": "read", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "older", "content": "older selected-out observation"}]
    trace = {"input_ids": [7, 8, 9], "output_ids": [10, 11]}
    projection = {"original_request_sha256": sha(original), "selected_request_sha256": sha(selected),
                  "input_ids_sha256": sha(trace["input_ids"]), "selected_prompt_tokens": 3,
                  "rendered_prompt_sha256": sha("explicit-fixture-rendering"), "removed_indices": [1, 2]}
    body = {"token_trace": trace, "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            "prompt_projection": {"request_sha256": sha(selected), "rendered_prompt_sha256": projection["rendered_prompt_sha256"]},
            "online_window_id": "fixture-window", "actor_identity": {"fixture": True}}
    response = {"http_status": 200, "body": body}
    payload = {"call_id": "c1", "attempt_id": "a1", "decision_index": 2, "stage": "started", "request": original}
    events = [{"kind": "model_attempt", "sequence": 20, "worker_id": "member_a", "payload": payload},
              {"kind": "model_attempt", "sequence": 21, "worker_id": "member_a",
               "payload": {**payload, "stage": "finished", "status": "success", "response": response}}]
    folder = tmp_path / "raw-transport/context-projections/request-00001"
    folder.mkdir(parents=True)
    for name, value in [("original-request.json", original), ("selected-request.json", selected),
                        ("projection.json", projection), ("response.json", response)]:
        (folder / name).write_bytes(json_bytes(value))
    action = {"sequence": 10, "worker_id": "member_a", "payload": {"action": "run_tests", "response": result, "model_call_id": "previous"}}
    archive = _Evidence.__new__(_Evidence)
    archive.folder, archive.events = tmp_path, events
    archive.views = {"member_a": {"decisions": [{"call_id": "c1", "tokens": trace, "actor_trainable": True}]}}
    archive.rollout = {"window": {"window_id": "fixture-window"}}
    archive.action_by_tool_id = {("member_a", "testcall"): action}
    archive.inputs, archive.calls, archive.presentations, archive.issues = [], [], [], []
    return archive, folder


def test_actual_selected_input_not_backend_or_discarded_round_defines_visible_facts(tmp_path):
    archive, _ = visible_fixture(tmp_path)
    archive._actual_inputs()
    assert not archive.issues and len(archive.calls) == 1 and len(archive.presentations) == 1
    shown = archive.presentations[0]["visible_result"]
    assert shown["groups"]["public_normal"]["tests"] == [{"test_id": "public", "status": "passed"}]
    assert "expected" not in json.dumps(shown) and "older selected-out" not in json.dumps(archive.presentations)


def test_missing_native_presentation_proof_is_unmapped_evidence_not_invented_visibility(tmp_path):
    archive, folder = visible_fixture(tmp_path)
    response = json.loads((folder / "response.json").read_text())
    response["body"].pop("prompt_projection")
    (folder / "response.json").write_bytes(json_bytes(response))
    archive.events[-1]["payload"]["response"] = response
    archive._actual_inputs()
    assert archive.issues and archive.calls == [] and archive.presentations == []


def test_mismatching_archived_token_ids_are_blocking_not_a_visible_information_edge(tmp_path):
    archive, folder = visible_fixture(tmp_path)
    projection = json.loads((folder / "projection.json").read_text())
    projection["input_ids_sha256"] = sha([999])
    (folder / "projection.json").write_bytes(json_bytes(projection))
    with pytest.raises(ValueError, match="native selected"):
        archive._actual_inputs()


def chain_fixture(*, rewrite_peer=False, conflict=False, import_seen=True, test_seen=True):
    """Synthetic immutable file chain; no AST author inference or world rerun."""
    archive = _Evidence.__new__(_Evidence)
    a1, a2, a3, b2, base = ({"object_id": obj, "version_id": ver} for obj, ver in
                           [("a", "v1"), ("a", "v2"), ("a", "v3"), ("b", "v2"), ("base", "v1")])
    initial = {"files": {"reader.py": "def read():\n    return 0\n", "report.py": "def report():\n    return 0\n", "test_member.py": ""}, "included_patch_ids": []}
    peer = copy.deepcopy(initial)
    peer["files"]["reader.py"] = "def read():\n    return 1\n"
    imported = copy.deepcopy(peer)
    imported["included_patch_ids"] = ["patch-1"]
    final = copy.deepcopy(imported)
    changed_path = "reader.py" if rewrite_peer else "report.py"
    final["files"][changed_path] = "def read():\n    return 99\n" if rewrite_peer else "def report():\n    return 2\n"
    bundles = {("a", "v1"): initial, ("a", "v2"): imported, ("a", "v3"): final,
               ("b", "v2"): peer, ("base", "v1"): initial}
    archive.bundle = lambda ref: bundles[(ref["object_id"], ref["version_id"])]
    patch = {"patch_id": "patch-1", "author": "member_b", "source_reference": b2,
             "base_reference": base, "source_sha256": sha(peer), "files_sha256": sha(peer["files"]),
             "changed_paths": ["reader.py"], "included_patch_ids": []}
    delivery = {"delivery_id": "d1", "actor_id": "member_a", "source_reference": a3,
                "source_sha256": sha(final), "files_sha256": sha(final["files"]),
                "included_patch_ids": ["patch-1"], "test_sequence": 4}
    def event(sequence, kind, **extra):
        return {"sequence": sequence, "kind": kind, "actor_id": "member_a",
                "operation_id": f"op-{sequence}", "action_id": f"action-{sequence}", **extra}
    archive.world = [event(1, "patch_fixed", **patch),
                     event(2, "integrate", patch_id="patch-1", previous_reference=a1, source_reference=a2,
                           input_reference=b2, conflicts=["reader.py"] if conflict else [],
                           status="conflict_markers_written" if conflict else "merged"),
                     event(3, "edit", path=changed_path, previous_reference=a2, source_reference=a3,
                           before_sha256=digest(imported["files"][changed_path].encode()),
                           after_sha256=digest(final["files"][changed_path].encode())),
                     event(4, "test", source_reference=a3, executed=True),
                     event(5, "patch_fixed", patch_id="patch-2", source_reference=a3),
                     event(6, "submit", delivery_id="d1", source_reference=a3)]
    archive.world[0]["actor_id"] = "member_b"
    archive.world_actions = {e["sequence"]: {"sequence": e["sequence"] * 10, "worker_id": e["actor_id"],
        "payload": {"model_call_id": f"c{e['sequence']}", "action": "write_file" if e["kind"] == "edit" else e["kind"],
                    "arguments": {"path": changed_path, "text": final["files"][changed_path]}}} for e in archive.world}
    archive.calls = [{"call_id": f"c{i}"} for i in range(1, 7)]
    archive.start = {"artifacts": {"a": {"owner": "member_a", "versions": {"v1": {}}}}}
    archive.facts = {"deliveries": [delivery], "patches": {"patch-1": patch}}
    archive.assessment = {"delivery": delivery, "source_reference": a3, "files_sha256": sha(final["files"])}
    archive.case = {"editable_paths": ["reader.py", "report.py", "test_member.py"],
                    "contract_symbols": {"reader.py": ["read"], "report.py": ["report"]}}
    archive.presentations = []
    if import_seen:
        archive.presentations.append({"action_sequence": 20, "member_id": "member_a", "input_sequence": 25,
            "call_id": "after-import", "action": "integrate_patch", "message_sha256": "visible-import",
            "visible_result": {"source_reference": a2, "included_patch_ids": ["patch-1"]}})
    if test_seen:
        archive.presentations.append({"action_sequence": 40, "member_id": "member_a", "input_sequence": 45,
            "call_id": "after-test", "action": "run_tests", "message_sha256": "visible-test",
            "visible_result": {"source_reference": a3, "files_sha256": sha(final["files"]), "executed": True}})
    archive.inputs = [({"member_id": "member_a", "sequence": 15, "call_id": "before-import", "selected_request_sha256": "actual-input"},
                       {"messages": [{"role": "user", "content": json.dumps({"observation": {"patches": [patch]}})}]})]
    archive.action_by_tool_id = {}
    return archive


def test_whole_production_file_consumption_and_metadata_do_not_invent_source_text_visibility():
    chain = chain_fixture().delivery_chain()
    peer = chain["peer_integrations"][0]
    assert peer["qualifying_fixed_product_consumption"] and peer["file_materialized"]
    assert peer["import_receipt_presented"] and not peer["source_text_presented"]
    assert [item["path"] for item in peer["retained_production_files"]] == ["reader.py"]


@pytest.mark.parametrize("change", ["rewrite_peer", "conflict", "import_seen", "test_seen"])
def test_import_count_or_backend_execution_alone_cannot_prove_partner_method(change):
    value = False if change.endswith("seen") else True
    chain = chain_fixture(**{change: value}).delivery_chain()
    assert not chain["peer_integrations"][0]["qualifying_fixed_product_consumption"]


def test_model_authored_claim_is_not_an_actual_patch_metadata_observation():
    archive = chain_fixture()
    archive.inputs[0][1]["messages"][0]["role"] = "assistant"
    chain = archive.delivery_chain()
    assert not chain["peer_integrations"][0]["fixed_patch_metadata_presented"]
    assert not chain["peer_integrations"][0]["qualifying_fixed_product_consumption"]


def test_contract_definition_rule_rejects_comments_format_docstrings_and_irrelevant_helpers():
    base = "def read():\n    return 0\n"
    same = "# only documentation\ndef read():\n    \"a new docstring\"\n    return (0)\n\ndef unused_helper():\n    return 999\n"
    assert _contract_definition_fingerprints(base, ["read"]) == _contract_definition_fingerprints(same, ["read"])
    assert _contract_definition_fingerprints(base, ["read"]) != _contract_definition_fingerprints("def read():\n    return 1\n", ["read"])
    assert _contract_definition_fingerprints("read = lambda: 0\n", ["read"]) is None
