"""Actual CPU WorldCore process controls; these never supply model support."""

import copy
import os
from pathlib import Path

import pytest

from proworksim.episode import begin_episode, finish_episode
from proworksim.experience import ExperienceRecorder
from proworksim.software_collaboration_v029 import (
    CASE_IDS, MEMBERS, PROJECT, SoftwareCollaborationPort, assess_software_collaboration,
    build_software_collaboration_case, case_spec,
)
from proworksim.software_tasks_v028 import reference_solution
from proworksim.software_training_v029 import (
    _contract_units, map_software_method, software_work_evidence, source_training_admission,
)
from proworksim.storage import atomic_write, json_bytes
from proworksim.support_weights import build_support
from proworksim.team_rollout import optimizer_scope_allows_update
from test_software_collaboration_v027 import call, published


@pytest.fixture
def control_root(tmp_path, request):
    declared = os.environ.get("V029_MAPPER_CONTROLS_ROOT")
    if declared:
        path = Path(declared) / request.node.name
        path.mkdir(parents=True, exist_ok=False)
        return path
    return tmp_path


def witness(root, route, *, failed=False, task_id=CASE_IDS[0]):
    prepared = build_software_collaboration_case(case_spec(task_id), root / "case")
    a, b = [SoftwareCollaborationPort(prepared.world.session(member, PROJECT), member)
            for member in MEMBERS]
    _, _, baseline = prepared.world._bundle(MEMBERS[0], baseline=True)
    original = baseline["files"]
    reference = reference_solution(task_id)
    library = next(path for path in prepared.case["source_contract"]["contract_roots"] if path != "consumer.py")
    episode = root / "episode"
    recorder = ExperienceRecorder()
    begin_episode(prepared.world, episode, experience=recorder.snapshot(), work_ids=[],
                  scenario={"variation": {"software_case": prepared.case}},
                  policies={member: {"origin": "rule"} for member in MEMBERS})
    call(b, "claim_task", task_id="consumer_export")
    call(b if route == "concentrated" else a, "claim_task", task_id="library_repair")
    if route in {"before", "reverted"}:
        call(b, "write_file", path="consumer.py", text=reference["consumer.py"])
    if route == "reverted":
        call(b, "write_file", path="consumer.py", text=original["consumer.py"])
    if route == "comment":
        call(b, "write_file", path="test_member.py", text=original["test_member.py"] + "# early unrelated note\n")
    if route == "unrelated":
        call(b, "write_file", path="consumer.py", text=original["consumer.py"] + "\ndef unrelated_helper():\n    return 1\n")
    if route == "test_first":
        call(b, "write_file", path="test_member.py", text=(
            "from consumer import comparison_records\n"
            "assert comparison_records(['x = y']) == [{'left': 'x', 'right': 'y'}]\n"))
    if route == "conflict_rewrite":
        assert task_id == CASE_IDS[0]
        source = original[library].replace("def right(self):\n        return self.tokens[0]",
                                         "def right(self):\n        return self.tokens[1]")
        assert source != original[library]
        call(b, "write_file", path=library, text=source)
    if route == "no_op_import":
        call(b, "write_file", path=library, text=reference[library])
    if route == "concentrated":
        call(b, "write_file", path=library, text=reference[library])
    else:
        upstream = (original[library] + "\n# comment-only partner input\n"
                    if route == "comment_import" else reference[library])
        call(a, "write_file", path=library, text=upstream)
        patch = published(a, ["library_repair"])
        merged = call(b, "integrate_patch", patch_id=patch)
        if route == "conflict_rewrite":
            assert merged["conflicts"] == [library]
            call(b, "write_file", path=library, text=reference[library])
        elif route == "comment_import":
            call(b, "write_file", path=library, text=reference[library])
    if route != "before":
        call(b, "write_file", path="consumer.py", text=reference["consumer.py"])
    if route == "rewrite_after_import":
        # Reimplement the imported definition while keeping the same contract.
        text = reference[library].replace("def right(self):\n        return self.tokens[-1]",
                                          "def right(self):\n        return self.tokens[len(self.tokens) - 1]")
        assert text != reference[library]
        call(b, "write_file", path=library, text=text)
    if failed:
        call(b, "write_file", path="consumer.py", text=original["consumer.py"])
    published(b, ["consumer_export"] + (["library_repair"] if route == "concentrated" else []))
    call(b, "run_tests")
    call(b, "submit_integration", message="Explicit v0.29 CPU process control")
    call(b, "write_file", path="test_member.py", text="raise RuntimeError('after fixed submission')\n")
    finish_episode(prepared.world, episode, experience=recorder.snapshot(), termination={"status": "CPU_witness_complete"})
    assessment = assess_software_collaboration(prepared, run_root=root / "acceptance")
    assert assessment["R"] == int(not failed)
    evidence = software_work_evidence(episode, assessment)
    rollout = {"rollout_id": "CPU-control-not-model-support", "manifest_sha256": evidence["manifest_sha256"],
               "work_validity": {"value": assessment["R"] == 1}}
    mapping = map_software_method(rollout, evidence)
    for name, value in (("assessment", assessment), ("evidence", evidence), ("mapping", mapping)):
        atomic_write(root / (name + ".json"), json_bytes(value))
    return episode, assessment, evidence, rollout


@pytest.mark.parametrize("route,category", [
    ("concentrated", "concentrated_delivery"),
    ("before", "contract_work_before_import"),
    ("after", "contract_work_after_import"),
    ("test_first", "contract_work_before_import"),
    ("conflict_rewrite", "contract_work_before_import"),
    ("rewrite_after_import", "contract_work_after_import"),
])
def test_real_complete_work_process_routes(control_root, route, category):
    _, _, evidence, rollout = witness(control_root, route)
    assert map_software_method(rollout, evidence)["class_id"] == category
    assert evidence["original_event_inventory"][-1]["sequence"] > evidence["events"][-1]["sequence"]
    assert evidence["net_delivery_diagnostic"]["status"] == "not_applicable"
    if route != "concentrated":
        edge = evidence["relevant_cross_member_inputs"][0]
        assert edge["imported_contract_work"] and edge["subsequent_work_sequences"]
    if route == "conflict_rewrite":
        assert evidence["relevant_cross_member_inputs"][0]["conflicts"]
    if route == "test_first":
        early = evidence["relevant_cross_member_inputs"][0]["recipient_work_before_input"]
        assert any(row["path"] == "test_member.py" and row["test_execution_sequences"] for row in early)


@pytest.mark.parametrize("route,category", [
    ("comment", "contract_work_after_import"),
    ("unrelated", "contract_work_after_import"),
    ("reverted", "contract_work_after_import"),
    ("comment_import", "concentrated_delivery"),
    ("no_op_import", "concentrated_delivery"),
])
def test_nonwork_and_reverts_cannot_manufacture_route(control_root, route, category):
    _, _, evidence, rollout = witness(control_root, route)
    assert map_software_method(rollout, evidence)["class_id"] == category
    if route != "no_op_import":
        assert evidence["excluded_edit_sequences"]
    if route in {"comment_import", "no_op_import"}:
        assert not evidence["relevant_cross_member_inputs"]
        assert evidence["excluded_integrations"]
    else:
        assert not evidence["relevant_cross_member_inputs"][0]["recipient_work_before_input"]


def test_complete_failure_unknown_and_wrong_identity_never_become_support(control_root):
    episode, assessment, evidence, rollout = witness(control_root, "after", failed=True)
    assert map_software_method(rollout, evidence)["status"] == "unmapped"
    # A caller cannot fill in V=True to override an independently failed contract.
    rollout["work_validity"]["value"] = True
    assert map_software_method(rollout, evidence)["status"] == "unmapped"
    unknown = copy.deepcopy(assessment)
    unknown.update(status="unknown", R=None)
    uncertain = software_work_evidence(episode, unknown)
    assert map_software_method(rollout, uncertain)["status"] == "unmapped"
    rollout["manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="another original"):
        map_software_method(rollout, evidence)


@pytest.mark.parametrize("task_id", CASE_IDS[1:])
def test_new_source_roots_are_source_specific_and_cannot_supply_training(control_root, task_id):
    _, _, evidence, rollout = witness(control_root, "after", task_id=task_id)
    assert map_software_method(rollout, evidence)["class_id"] == "contract_work_after_import"
    case = case_spec(task_id)
    for mode in ("current_policy_collection", "frozen_development", "frozen_evaluation"):
        scope = source_training_admission(case, {"source_usage": case["usage"], "collection_mode": mode})
        assert scope["optimizer_update_allowed"] is False
        actual = {"manifest": {"scenario": {"variation": {"software_case": case}}}, "online_scope": scope}
        assert not optimizer_scope_allows_update(actual)
    with pytest.raises(ValueError, match="source purpose"):
        source_training_admission(case, {"source_usage": "policy_training", "collection_mode": "current_policy_collection"})


def test_member_action_ownership_failure_residual_and_exact_situations_stay_separate():
    from test_experience_allocation_v027 import fixture_window

    case = case_spec(CASE_IDS[0])
    admitted = source_training_admission(case, {"source_usage": "policy_training", "collection_mode": "current_policy_collection"})
    successor = source_training_admission(case, {"source_usage": "policy_training", "collection_mode": "successor_work"})
    assert admitted["optimizer_update_allowed"] and not successor["optimizer_update_allowed"]
    _, _, _, supports, bindings = fixture_window()
    xi = "api-contract"
    slots = [copy.deepcopy(bindings[sid]) for sid in supports[xi]["slot_ids"]]
    original = copy.deepcopy(slots)
    for slot in slots:
        slot["rollout"]["manifest"]["scenario"] = {"variation": {"software_case": case}}
        slot["rollout"]["online_scope"] = admitted
    support = build_support(slots, window=supports[xi]["window"], member_ids=list(supports[xi]["blocks"]), min_class_count=2)
    for member, block in support["blocks"].items():
        assert block["M"] == supports[xi]["blocks"][member]["M"]
        assert block["base_actor_mask"] == supports[xi]["blocks"][member]["base_actor_mask"]
    assert [slot["member_views"] for slot in slots] == [slot["member_views"] for slot in original]
    # A different fixed first opportunity cannot join the same empirical block.
    slots[0]["rollout"]["window"]["xi_id"] += "::first=member_b"
    with pytest.raises(ValueError, match="window"):
        build_support(slots, window=supports[xi]["window"], member_ids=list(supports[xi]["blocks"]), min_class_count=2)


def test_named_contract_units_ignore_comments_and_unrelated_definitions():
    names = ["C.api"]
    text = "class C:\n    def api(self):\n        return 1\n"
    same = text + "\ndef unrelated():\n    return 2\n"
    assert _contract_units(text, names) == _contract_units(same + "# comment\n", names)
    assert _contract_units(text.replace("return 1", "return 2"), names) != _contract_units(text, names)
