"""Finite v050 real-archive CPU export/Mapper/admission controls.

The scripted completions and token IDs are explicitly synthetic. These controls
exercise SDK/WorldCore archives, not performance, model calls or real learning.
"""
from __future__ import annotations

import copy
import inspect
from pathlib import Path

import pytest

from proworksim import software_allocation_v050 as allocation
from proworksim import software_learning_v050 as learning
from proworksim import software_mapper_v049 as original_mapper
from proworksim import software_mapper_v050 as broken_mapper
from proworksim import software_mapper_v050r1 as mapper
from proworksim import software_organization_runtime_v050 as runtime
from proworksim import software_training_v050 as previous
from proworksim import software_training_v050r1 as training
from proworksim.software_context_v048 import SoftwareContextTransport
from proworksim.software_organization_tasks_v050 import TRAINING_CASE_IDS, reference_solution
from proworksim.software_organization_v050 import build_software_collaboration_case, case_spec
from proworksim.storage import digest, json_bytes, read_json
from test_software_organization_runtime_v038 import action
from test_software_training_v049 import gamma as old_gamma, owner_for


def _snapshot(root):
    return {str(path.relative_to(root)): digest(path.read_bytes()) for path in root.rglob("*") if path.is_file()}


def _collect(folder, route):
    members = list(learning.MEMBERS)
    reference = reference_solution(TRAINING_CASE_IDS[0])["event_time.py"]
    scripts = {member: [action("staff_done", reason="Explicit CPU control complete")] for member in members}
    if route == "local":
        scripts[members[0]] = [action("write_file", path="event_time.py", text=reference),
            action("run_tests"), action("fix_patch", task_ids=[], message="CPU fixed source"),
            action("submit_integration", message="CPU local structural control"),
            action("staff_done", reason="CPU complete")]
    elif route == "peer":
        scripts[members[0]] = [action("write_file", path="event_time.py", text=reference),
            action("fix_patch", task_ids=[], message="CPU fixed partner source"),
            action("staff_done", reason="CPU author sleep")]
        scripts[members[1]] = [action("staff_wait", reason="Wait for actual CPU publication"),
            action("adopt_candidate", patch_id="patch-1"), action("run_tests"),
            action("fix_patch", task_ids=[], message="CPU adopted fixed tree"),
            action("submit_integration", message="CPU peer structural control"),
            action("staff_done", reason="CPU complete")]
    owner = owner_for(scripts)
    owner.actor_steps = owner.critic_steps = owner.policy_revision = 4
    owner.begin_window(learning.TRAINING_WINDOW_ID)
    prepared = build_software_collaboration_case(case_spec(TRAINING_CASE_IDS[0]), folder / "prepared")
    other = build_software_collaboration_case(case_spec(TRAINING_CASE_IDS[1]), folder / "other-prepared")
    recipe = {**copy.deepcopy(owner.recipe), "credit_assignment": "terminal_mc"}
    design = {"training_slots": [{"slot_id": sid, "root": "LA" if index < 12 else "LB", "members": members,
        "sampling_seed": 202610130501 + index, "purpose": "policy_training"}
        for index, sid in enumerate(learning.SLOT_IDS)],
        "mapper": {"category_order": list(allocation.CATEGORIES)},
        "direction": {"weight_lower": .5, "weight_upper": 2., "total_variation_from_b_max": .2}}
    gamma = {**old_gamma(), "gamma_version": previous.GAMMA_VERSION, "runtime_version": runtime.VERSION,
        "learning_bridge_version": learning.VERSION, "design_sha256": digest(json_bytes(design)),
        "s_star": {"actor_identity": owner.freeze_identity(), "recipe_sha256": digest(json_bytes(recipe)),
                   "actor_steps": 4, "critic_steps": 4}}
    slots = []
    for index, sid in enumerate(learning.SLOT_IDS):
        item = prepared if index < 12 else other
        slots.append({"slot_id": sid, "xi_id": previous.situation_id(item.case),
            "xi_fingerprint": previous.situation_fingerprint(item), "active_members": members,
            "policies": previous.policy_spec(owner, item), "mapping_spec_id": training.MAPPER})
    declaration = training.declare_window(learning.TRAINING_WINDOW_ID,
        actor_identity=owner.freeze_identity(), gamma_identity=gamma, slot_specs=slots, min_class_count=2)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(runtime, "_capture_slot_guard", lambda current: copy.deepcopy(current.learning))
        row = runtime.collect_episode(owner, prepared, folder / "slot", sampling_seed=202610130501,
            slot_id=learning.SLOT_IDS[0], manage_owner_window=False,
            transport_factory=lambda current, directory: SoftwareContextTransport(current, directory,
                evidence_kind="cpu_programmed_fixture"))
    episode = folder / "slot/episode"
    kwargs = {"declaration": declaration, "slot_id": row["slot_id"],
        "captured": read_json(folder / "slot/public-capture.json"), "runtime_row": row}
    entry, details = training.export_software_episode(prepared, episode, row["assessment"], **kwargs)
    entries = [entry, *[training.unavailable_slot_entry(declaration, sid,
        "Synthetic CPU control: unexecuted inventory retained, not a real support decision") for sid in learning.SLOT_IDS[1:]]]
    admission = learning.prepare_training_admission(entries, declaration, recipe)
    support = allocation.build_support_report(entries, declaration, admission=admission, design=design)
    return {"folder": folder, "prepared": prepared, "episode": episode, "row": row, "kwargs": kwargs,
        "entry": entry, "details": details, "entries": entries, "admission": admission,
        "support": support, "declaration": declaration, "recipe": recipe}


@pytest.fixture(scope="module")
def controls(tmp_path_factory):
    root = tmp_path_factory.mktemp("v050r1-real-archive-cpu-controls")
    return {route: _collect(root / route, route) for route in ("failure", "local", "peer")}


def test_original_failure_reproduces_and_R0_own_targets_enter_fixed_48_measure(controls):
    control = controls["failure"]
    entry, details = control["entry"], control["details"]
    with pytest.raises(ValueError, match="Original v049 export evidence seal differs"):
        previous.export_software_episode(control["prepared"], control["episode"], control["row"]["assessment"],
                                         **control["kwargs"])
    assert entry["reward"]["eligible"] is True and entry["reward"]["reward"] == 0
    assert entry["mapping"]["status"] == "unmapped"
    assert details["work_validity"]["components"]["record"]["value"] is True
    assert details["work_validity"]["components"]["delivery"]["value"] is False
    admission = control["admission"]
    assert admission["slot_count"] == 24 and len(admission["decisions"]) == 2
    assert {row["actor_denominator"] for row in admission["decisions"]} == {48}
    assert {row["critic_denominator"] for row in admission["decisions"]} == {48}
    assert all(row["reward"] == 0 for row in admission["decisions"])
    assert all(value == 1 for row in control["support"]["base_weights_by_slot"].values() for value in row.values())
    with pytest.raises(ValueError, match="fixed 24 collections"):
        allocation.pretraining_support_gate(control["support"])


@pytest.mark.parametrize("route,category", [("local", "local_lineage_delivery"), ("peer", "evidenced_peer_product_delivery")])
def test_unchanged_routes_use_actual_cpu_archives_then_support_and_prepare_window(controls, route, category):
    control = controls[route]
    assert control["row"]["R"] == 1
    assert control["entry"]["mapping"]["class_id"] == category
    assert control["details"]["binding_matches_views"] is True
    assert len(control["admission"]["decisions"]) == sum(
        row.get("actual_response") is not None for view in control["details"]["member_views"].values()
        for row in view["decisions"])
    assert all(block["M"] == 12 for root in control["support"]["roots"].values() for block in root["blocks"].values())
    for row in control["admission"]["decisions"]:
        view = control["details"]["member_views"][row["member_id"]]
        decision = next(item for item in view["decisions"] if item["call_id"] == row["call_id"])
        assert row["tokens"] == decision["actual_response"]["token_trace"]
        assert row["actor_denominator"] == 48 * view["own_action_tokens"]


@pytest.mark.parametrize("mutation", ["old-version", "seal", "episode", "source-path", "source-sha", "assessment", "case", "runtime"])
def test_strict_v050_seal_and_source_bindings_reject_detached_payloads(controls, mutation):
    control = controls["local"]
    evidence = copy.deepcopy(control["details"]["original_work_evidence"])
    if mutation == "old-version":
        evidence["version"] = "software-training-export-v0.49"
    elif mutation == "seal":
        evidence["scope"] += " tampered"
    elif mutation == "episode":
        evidence["episode_path"] = str(control["episode"].parent)
    elif mutation == "source-path":
        evidence["source_references"]["manifest"]["path"] = evidence["source_references"]["assessment"]["path"]
    elif mutation == "source-sha":
        evidence["source_references"]["end_state"]["sha256"] = "0" * 64
    elif mutation == "assessment":
        evidence["assessment"]["R"] = 0
    elif mutation == "case":
        evidence["case"]["purpose"] = "policy_development"
    else:
        evidence["runtime_binding"]["version"] = "software-organization-runtime-v0.49"
    if mutation != "seal":
        evidence["evidence_sha256"] = digest(json_bytes({k: v for k, v in evidence.items() if k != "evidence_sha256"}))
    with pytest.raises(ValueError):
        mapper.map_software_method(control["entry"]["rollout"], evidence)


def test_actual_input_binding_cannot_be_substituted_by_export_identity_fix(controls):
    control = controls["local"]
    rollout = copy.deepcopy(control["entry"]["rollout"])
    event = next(e for e in rollout["events"] if e["kind"] == "model_attempt" and e["payload"].get("status") == "success")
    event["payload"]["request"]["messages"] = [{"role": "user", "content": "fabricated upstream input"}]
    with pytest.raises(ValueError, match="changed original episode events"):
        mapper.map_software_method(rollout, control["details"]["original_work_evidence"])


def test_reexport_writes_only_fresh_destination_and_preserves_archived_R0(controls, tmp_path):
    control = controls["failure"]
    source = control["folder"] / "slot"
    before = _snapshot(source)
    destination = tmp_path / "retained"
    entry, details = training.reexport_closed_slot(source, control["declaration"], destination)
    assert entry == control["entry"] and details == control["details"]
    assert _snapshot(source) == before
    receipt = read_json(destination / "rematerialization-receipt.json")
    assert receipt["formal_R"] == 0 and all(receipt["source_files_unchanged"].values())
    assert receipt["new_model_calls"] == receipt["new_tokenizer_calls"] == receipt["new_business_tests_or_acceptances"] == 0
    with pytest.raises(ValueError, match="fresh destination"):
        training.reexport_closed_slot(source, control["declaration"], destination)
    with pytest.raises(ValueError, match="fresh destination"):
        training.reexport_closed_slot(source, control["declaration"], source / "invalid")


def test_no_other_mapper_or_learner_code_path_changes():
    assert mapper.map_software_method.__code__ is original_mapper.map_software_method.__code__
    assert mapper.Evidence is broken_mapper.Evidence
    assert mapper.mapping_spec is original_mapper.mapping_spec
    assert mapper.Evidence.delivery_chain is original_mapper.Evidence.delivery_chain
    assert mapper.Evidence._actual_inputs is original_mapper.Evidence._actual_inputs
    assert broken_mapper.map_software_method.__globals__["_validate_export_evidence"] is original_mapper._validate_export_evidence
    assert training.bind_rollout is previous.bind_rollout
    assert learning.prepare_training_admission.__globals__["prepare_window"] is learning.prepare_window
    proof = training.adaptation_spec()
    assert proof["only_v050_consumer_import_changed"] and proof["reexport_original_code_object_identical"]
    assert "software-training-export-v0.49" in inspect.getsource(original_mapper._validate_export_evidence)
    assert Path(original_mapper.__file__).is_file()
