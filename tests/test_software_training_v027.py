"""Real CPU software provenance; scripted witnesses are never model support."""

import copy

import pytest

from proworksim.episode import begin_episode, finish_episode
from proworksim.experience import ExperienceRecorder
from proworksim.online_training import prepare_window, recipe_config
from proworksim.software_collaboration_v027 import assess_software_collaboration
from proworksim.software_training_v027 import (
    map_software_method, software_work_evidence,
)
from proworksim.support_weights import build_support
from test_online_training_v13 import _entry, _features, _identity
from test_software_collaboration_v027 import PATCHES, apply, call, published, setup_case


def archived_witness(tmp_path, route):
    prepared, a, b = setup_case(tmp_path)
    episode = tmp_path / "episode"
    recorder = ExperienceRecorder()
    begin_episode(prepared.world, episode, experience=recorder.snapshot(), work_ids=[],
                  scenario={"variation": {"software_case": prepared.case}},
                  policies={"member_a": {"origin": "rule"}, "member_b": {"origin": "rule"}})
    call(a, "claim_task", task_id="string_api")
    call(b if route != "concentrated" else a, "claim_task", task_id="inventory_consumer")
    if route in {"independent", "no_op"}:
        apply(b, PATCHES[1])
    apply(a, PATCHES[0])
    upstream = published(a, ["string_api"])
    if route == "concentrated":
        apply(a, PATCHES[1])
        actor = a
    elif route == "no_op":
        # Both write identical complete content. A declared input/patch ID does
        # not establish a byte-changing cross-member transformation.
        apply(a, PATCHES[1])
        apply(b, PATCHES[0])
        same = published(b, ["inventory_consumer"])
        call(a, "integrate_patch", patch_id=same)
        actor = a
    else:
        call(b, "declare_dependency", task_id="inventory_consumer", depends_on="string_api")
        call(b, "integrate_patch", patch_id=upstream)
        if route == "sequential":
            apply(b, PATCHES[1])
        actor = b
    published(actor, ["string_api"] if actor is a else ["inventory_consumer"])
    call(actor, "run_tests")
    call(actor, "submit_integration", message="CPU program witness only")
    # A later private edit must not retroactively change the fixed work method.
    apply(actor, {"path": "consumer.py", "old": "strip_whitespace=True",
                  "new": "strip_whitespace=False"})
    finish_episode(prepared.world, episode, experience=recorder.snapshot(),
                   termination={"status": "CPU_witness_complete"})
    assessment = assess_software_collaboration(prepared, run_root=tmp_path / "acceptance")
    assert assessment["R"] == 1
    return episode, assessment


@pytest.mark.parametrize("route,category", [
    ("sequential", "split_sequential"),
    ("independent", "split_independent_branches"),
    ("concentrated", "concentrated_delivery"),
    ("no_op", None),
])
def test_method_uses_actual_file_transform_not_declared_ids_or_later_edits(tmp_path, route, category):
    episode, assessment = archived_witness(tmp_path, route)
    evidence = software_work_evidence(episode, assessment)
    rollout = {"rollout_id": "explicit-CPU-witness", "manifest_sha256": evidence["manifest_sha256"],
               "work_validity": {"value": True}}
    mapped = map_software_method(rollout, evidence)
    assert mapped["class_id"] == category
    if route == "no_op":
        assert not evidence["cross_member_patch_transformations"]
        assert evidence["integrations_without_current_authored_byte_change"]
    if category and category.startswith("split"):
        edge = evidence["cross_member_patch_transformations"][0]
        assert edge["author_edit_sequences"] and edge["changed_paths"]
        assert edge["sender"] != edge["recipient"]
    # A valid route is not assigned when complete work is false/unknown.
    for value in (False, None):
        rollout["work_validity"]["value"] = value
        assert map_software_method(rollout, evidence)["status"] == "unmapped"


def test_fixed_assessment_identity_and_unknown_are_not_replaceable(tmp_path):
    episode, assessment = archived_witness(tmp_path, "sequential")
    wrong = copy.deepcopy(assessment)
    wrong["delivery"]["source_reference"]["version_id"] = "v1"
    with pytest.raises(ValueError, match="fixed archived"):
        software_work_evidence(episode, wrong)
    wrong = copy.deepcopy(assessment)
    wrong.update(status="unknown", R=0)
    with pytest.raises(ValueError, match="filled with zero"):
        software_work_evidence(episode, wrong)
    wrong.update(R=None)
    assert software_work_evidence(episode, wrong)["assessment_status"] == "unknown"


def test_development_scope_cannot_enter_existing_optimizer_or_current_support():
    identity = _identity()
    entry = _entry(identity, reward=1)
    entry["rollout"]["online_scope"] = {"optimizer_update_allowed": False,
                                        "composition_reconfiguration_eligible": False}
    prepared = prepare_window([entry], identity, "window-0", recipe_config(), _features)
    assert prepared["decisions"] == []
    assert prepared["slots"][0]["exclusions"] == ["declared_scope_forbids_optimizer_update"]

    from test_experience_allocation_v027 import fixture_window
    _, _, _, supports, bindings = fixture_window()
    xi = "api-contract"
    slots = [copy.deepcopy(bindings[sid]) for sid in supports[xi]["slot_ids"]]
    for slot in slots:
        slot["rollout"]["online_scope"] = entry["rollout"]["online_scope"]
    support = build_support(slots, window=supports[xi]["window"],
                            member_ids=list(supports[xi]["blocks"]), min_class_count=2)
    for block in support["blocks"].values():
        assert block["M"] == 10 and block["n_positive"] == 0
        assert not any(block["base_actor_mask"].values())
        assert all("declared_scope_forbids_reconfiguration" in reasons
                   for reasons in block["diagnostics"].values())


@pytest.mark.parametrize("scope", [None, {"purpose": "policy_training",
    "optimizer_update_allowed": True, "source_training_admission": True,
    "composition_reconfiguration_eligible": True}])
def test_frozen_development_case_cannot_be_relabelled_as_training(scope):
    identity = _identity()
    entry = _entry(identity, reward=1)
    case = {"usage": "interface_dev", "training_eligible": False}
    entry["rollout"]["manifest"]["scenario"] = {"variation": {"software_case": case}}
    if scope is not None:
        entry["rollout"]["online_scope"] = scope
    result = prepare_window([entry], identity, "window-0", recipe_config(), _features)
    assert result["decisions"] == []
    from test_experience_allocation_v027 import fixture_window
    _, _, _, supports, bindings = fixture_window()
    xi = "api-contract"
    slots = [copy.deepcopy(bindings[sid]) for sid in supports[xi]["slot_ids"]]
    for slot in slots:
        slot["rollout"]["manifest"]["scenario"] = {"variation": {"software_case": case}}
        if scope is not None:
            slot["rollout"]["online_scope"] = scope
    support = build_support(slots, window=supports[xi]["window"],
                            member_ids=list(supports[xi]["blocks"]), min_class_count=2)
    assert all(block["n_positive"] == 0 and not any(block["base_actor_mask"].values())
               for block in support["blocks"].values())


def test_relayed_foreign_change_cannot_be_credited_to_patch_publisher(tmp_path):
    prepared, a, b = setup_case(tmp_path)
    episode = tmp_path / "episode"
    recorder = ExperienceRecorder()
    begin_episode(prepared.world, episode, experience=recorder.snapshot(), work_ids=[],
                  scenario={"variation": {"software_case": prepared.case}}, policies={})
    call(a, "claim_task", task_id="string_api")
    call(b, "claim_task", task_id="inventory_consumer")
    apply(a, PATCHES[0])
    original = published(a, ["string_api"])
    apply(b, PATCHES[1])
    call(b, "integrate_patch", patch_id=original)
    relayed = published(b, ["inventory_consumer"])
    apply(a, PATCHES[1])  # Receiver already has B's actual authored file bytes.
    apply(a, {"path": PATCHES[0]["path"], "old": PATCHES[0]["new"], "new": PATCHES[0]["old"]})
    call(a, "integrate_patch", patch_id=relayed)  # Only relayed A-authored fields.py changes.
    published(a, ["string_api"])
    call(a, "run_tests")
    call(a, "submit_integration", message="CPU relay attribution negative control")
    finish_episode(prepared.world, episode, experience=recorder.snapshot(), termination={"status": "CPU"})
    assessment = assess_software_collaboration(prepared, run_root=tmp_path / "acceptance")
    assert assessment["R"] == 1
    evidence = software_work_evidence(episode, assessment)
    assert [(e["sender"], e["recipient"]) for e in evidence["cross_member_patch_transformations"]] == [
        ("member_a", "member_b")]
    rejected = evidence["integrations_without_current_authored_byte_change"][0]
    assert rejected["changed_paths"] and not rejected["authored_changed_paths"]
