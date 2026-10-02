"""Real WorldCore, immutable extraction and parent acceptance mapper controls.

These are explicitly scripted development witnesses, never current model support.
"""

import copy

import pytest

from proworksim.episode import begin_episode, finish_episode
from proworksim.experience import ExperienceRecorder
from proworksim.software_collaboration_v027 import assess_software_collaboration
from proworksim.software_training_v027 import map_software_method as old_mapper
from proworksim.software_training_v028 import map_software_method, software_work_evidence
from proworksim.storage import atomic_write, json_bytes
from test_software_collaboration_v027 import PATCHES, apply, call, published, setup_case


def witness(tmp_path, route, *, failed=False):
    prepared, a, b = setup_case(tmp_path)
    episode = tmp_path / "episode"
    recorder = ExperienceRecorder()
    begin_episode(prepared.world, episode, experience=recorder.snapshot(), work_ids=[],
                  scenario={"variation": {"software_case": prepared.case}},
                  policies={"member_a": {"origin": "rule"}, "member_b": {"origin": "rule"}})
    call(a, "claim_task", task_id="string_api")
    call(b, "claim_task", task_id="inventory_consumer")
    if route in {"comment_reverted", "comment_retained"}:
        before = call(b, "read_file", path="test_member.py", start_line=1, max_lines=10)["text"] + "\n"
        call(b, "write_file", path="test_member.py", text=before + "# unrelated early note\n")
        if route == "comment_reverted":
            call(b, "write_file", path="test_member.py", text=before)
    if route == "implementation_reverted":
        apply(b, PATCHES[1])
        apply(b, {"path": PATCHES[1]["path"], "old": PATCHES[1]["new"], "new": PATCHES[1]["old"]})
    if route in {"test_first", "trivial_test"}:
        text = ("from marshmallow import fields\n"
                "assert fields.String(strip_whitespace=True).deserialize(' X ') == 'X'\n")
        call(b, "write_file", path="test_member.py", text=text if route == "test_first" else "assert True\n")
    if route == "implementation_first":
        apply(b, PATCHES[1])
    apply(a, PATCHES[0])
    upstream = published(a, ["string_api"])
    call(b, "integrate_patch", patch_id=upstream)
    if route != "implementation_first":
        apply(b, PATCHES[1])
    if failed:
        apply(b, {"path": "consumer.py", "old": "strip_whitespace=True", "new": "strip_whitespace=False"})
    published(b, ["inventory_consumer"])
    call(b, "run_tests")
    call(b, "submit_integration", message="Explicit CPU mapper witness")
    # This syntactically valid later edit changes the current workspace but not
    # the submitted exact version, quality, route or saved raw event inventory.
    call(b, "write_file", path="test_member.py", text="raise RuntimeError('after fixed delivery')\n")
    finish_episode(prepared.world, episode, experience=recorder.snapshot(),
                   termination={"status": "CPU_witness_complete"})
    assessment = assess_software_collaboration(prepared, run_root=tmp_path / "acceptance")
    assert assessment["R"] == int(not failed)
    assert assessment["independent_acceptance"]["executed"]
    evidence = software_work_evidence(episode, assessment)
    rollout = {"rollout_id": "explicit-CPU-witness", "manifest_sha256": evidence["manifest_sha256"],
               "work_validity": {"value": assessment["R"] == 1}}
    for name, value in (("assessment", assessment), ("evidence", evidence),
                        ("mapping", map_software_method(rollout, evidence))):
        atomic_write(tmp_path / (name + ".json"), json_bytes(value))
    return assessment, evidence, rollout


@pytest.mark.parametrize("route", ["plain", "comment_reverted", "comment_retained", "implementation_reverted"])
def test_full_world_audit_counterexample_cannot_manufacture_second_route(tmp_path, route):
    _, evidence, rollout = witness(tmp_path, route)
    mapped = map_software_method(rollout, evidence)
    assert mapped["class_id"] == "net_work_after_import"
    assert not evidence["uncertain_net_units"]
    assert evidence["relevant_cross_member_inputs"]
    assert evidence["original_event_inventory"][-1]["sequence"] > evidence["events"][-1]["sequence"]
    assert all(e["path"] != "test_member.py" for e in evidence["relevant_net_edits"])
    if route == "comment_reverted":
        # The supplied audit was function-only. Here the old failure is also
        # reproduced after real WorldCore integration and independent acceptance.
        assert old_mapper(rollout, evidence)["class_id"] == "split_independent_branches"
        assert len(evidence["excluded_edit_sequences"]) == 2
    if route == "implementation_reverted":
        assert len(evidence["excluded_edit_sequences"]) == 2


@pytest.mark.parametrize("route", ["test_first", "implementation_first"])
def test_real_retained_contract_test_is_not_blanket_excluded(tmp_path, route):
    _, evidence, rollout = witness(tmp_path, route)
    assert map_software_method(rollout, evidence)["class_id"] == "net_work_before_import"
    if route == "test_first":
        unit = next(row for row in evidence["net_delivery_units"] if row["path"] == "test_member.py")
        assert unit["verification_sequences"]
        assert unit["author_edit_sequence"] < min(row["sequence"] for row in evidence["relevant_cross_member_inputs"])
        assert any(row["path"] == "test_member.py" for row in evidence["relevant_net_edits"])


def test_uncertain_test_does_not_manufacture_method_support(tmp_path):
    _, evidence, rollout = witness(tmp_path, "trivial_test")
    assert evidence["uncertain_net_units"]
    assert map_software_method(rollout, evidence)["status"] == "unmapped"


def test_failed_parent_acceptance_and_unknown_do_not_become_positive_support(tmp_path):
    _, evidence, rollout = witness(tmp_path, "plain", failed=True)
    assert map_software_method(rollout, evidence)["status"] == "unmapped"
    rollout["work_validity"]["value"] = None
    assert map_software_method(rollout, evidence)["status"] == "unmapped"
    other = copy.deepcopy(rollout)
    other["manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="another original"):
        map_software_method(other, evidence)
