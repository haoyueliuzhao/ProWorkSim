"""One additional real-SDK CPU peer route plus offline sealing controls."""
import copy
import json

import pytest

from proworksim.software_mapper_v049 import Evidence, map_software_method, mapping_spec
from proworksim.storage import digest, json_bytes
from test_software_training_v049 import collect_control


@pytest.fixture(scope="module")
def peer(tmp_path_factory):
    return collect_control(tmp_path_factory.mktemp("v049-peer-export-control") / "peer", "peer")


def test_exact_partner_adoption_receipt_test_and_delivery_are_actually_presented(peer):
    assert peer["row"]["R"] == 1
    mapped = peer["entry"]["mapping"]
    assert mapped["class_id"] == "evidenced_peer_product_delivery"
    assert mapped["composition_support_eligible"] is True
    assert all(row["support_eligible"] is True for row in mapped["member_projections"].values())
    chain = mapped["evidence"]["delivery_chain"]
    application, = chain["peer_applications"]
    assert application["qualified"] is True
    assert application["source_member"] == "member_001" and application["recipient"] == "member_002"
    assert application["nonidentity_production_paths"] == ["event_time.py"]
    assert application["complete_tree_retained_to_final"] is True
    assert application["metadata_presentations"] and application["receipt_presentations"]
    assert chain["current_test_feedback_seen_before_submit"] is True
    assert application["world_sequence"] < chain["current_test_sequence"]
    assert peer["row"]["member_lifecycle"]["live_at_end"] == 2
    assert peer["row"]["actor_updates"] == peer["row"]["critic_updates"] == 0


def test_mapper_rejects_detached_export_seal_and_even_resealed_fabricated_facts(peer):
    rollout = peer["entry"]["rollout"]
    original = peer["detail"]["original_work_evidence"]
    changed = copy.deepcopy(original)
    changed["assessment_status"] = "fabricated"
    with pytest.raises(ValueError, match="seal differs"):
        map_software_method(rollout, changed, spec=mapping_spec())
    changed = copy.deepcopy(original)
    changed["source_references"]["end_state"]["path"] = str(peer["episode"] / "start/control/state.json")
    changed["evidence_sha256"] = digest(json_bytes({k: v for k, v in changed.items() if k != "evidence_sha256"}))
    with pytest.raises(ValueError, match="source reference"):
        map_software_method(rollout, changed, spec=mapping_spec())
    changed = copy.deepcopy(original)
    changed["original_events"] = []
    changed["evidence_sha256"] = digest(json_bytes({k: v for k, v in changed.items() if k != "evidence_sha256"}))
    with pytest.raises(ValueError, match="responsibility/product facts"):
        map_software_method(rollout, changed, spec=mapping_spec())


def test_gamma1_metadata_can_use_retained_first_observation_without_expanding_native_input():
    data = object.__new__(Evidence)
    patch = {"patch_id": "patch-1", "author": "member_001", "source_reference": {"object_id": "fixed", "version_id": "v2"}}
    native = {"messages": [
        {"role": "user", "content": json.dumps({"observation": {"patches": {"patch-1": patch}}})},
        {"role": "user", "content": json.dumps({"observation": {"patches": {"$same_input_ref": "first_observation#/observation/patches"}}})},
    ]}
    record = {"member_id": "member_002", "sequence": 20, "call_id": "actual-input-cpu-shape",
        "selected_request_sha256": digest(json_bytes(native))}
    data.inputs = [(record, native)]
    data.action_by_tool_id = {}
    before = copy.deepcopy(native)
    presentation, = data.metadata_seen("member_002", patch, 21)
    assert presentation["message_index"] == 0 and presentation["selected_request_sha256"] == record["selected_request_sha256"]
    assert native == before
    assert data.metadata_seen("member_002", patch, 20) == []
    assert data.metadata_seen("member_001", patch, 21) == []
    wrong = copy.deepcopy(patch)
    wrong["source_reference"]["version_id"] = "unseen-version"
    assert data.metadata_seen("member_002", wrong, 21) == []
