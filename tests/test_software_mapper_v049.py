"""Finite new whole-file route controls; all work is explicit synthetic evidence."""
import copy

import pytest

from proworksim.software_mapper_v049 import Evidence, CLASS_ORDER, _production
from proworksim.storage import digest, json_bytes


def route(*, peer=False):
    data = object.__new__(Evidence)
    member, partner = "member_001", "member_002"
    baseline = {"files": {"main.py": "def _helper():\n    return 0\n\ndef api():\n    return _helper()\n"}, "included_patch_ids": []}
    completed = copy.deepcopy(baseline)
    completed["files"]["main.py"] = baseline["files"]["main.py"].replace("return 0", "return 1")
    initial = {"object_id": "own", "version_id": "v0"}
    final = {"object_id": "own", "version_id": "v1"}
    incoming = {"object_id": "peer", "version_id": "p1"}
    if peer:
        completed["included_patch_ids"] = ["patch-1"]
    bundles = {("own", "v0"): baseline, ("own", "v1"): completed, ("peer", "p1"): completed}
    data.bundle = lambda ref: bundles[ref["object_id"], ref["version_id"]]
    data.start = {"artifacts": {"own": {"owner": member, "versions": {"v0": {}}}}}
    data.case = {"editable_paths": ["main.py"]}
    delivery = {"delivery_id": "d1", "actor_id": member, "source_reference": final,
        "source_sha256": digest(json_bytes(completed)), "files_sha256": digest(json_bytes(completed["files"])),
        "test_sequence": 4}
    change = {"sequence": 2, "kind": "edit", "actor_id": member, "source_reference": final,
        "previous_reference": initial, "path": "main.py", "before_sha256": digest(baseline["files"]["main.py"].encode()),
        "after_sha256": digest(completed["files"]["main.py"].encode())}
    patches, publication = {}, []
    if peer:
        patches["patch-1"] = {"patch_id": "patch-1", "author": partner, "source_reference": incoming,
            "files_sha256": digest(json_bytes(completed["files"]))}
        change = {"sequence": 2, "kind": "candidate_adopted", "actor_id": member, "source_reference": final,
            "previous_reference": initial, "input_reference": incoming, "patch_id": "patch-1",
            "files_sha256": patches["patch-1"]["files_sha256"], "exact_files_match": True, "native_model_action": True}
        publication = [{"sequence": 1, "kind": "patch_fixed", "actor_id": partner, "source_reference": incoming, "patch_id": "patch-1"}]
    data.world = [*publication, change,
        {"sequence": 3, "kind": "patch_fixed", "actor_id": member, "source_reference": final, "patch_id": "patch-final"},
        {"sequence": 4, "kind": "test", "actor_id": member, "source_reference": final, "executed": True},
        {"sequence": 5, "kind": "submit", "actor_id": member, "source_reference": final, "delivery_id": "d1"}]
    data.facts, data.assessment = {"patches": patches, "deliveries": [delivery]}, {"delivery": delivery}
    data.issues = []
    data.world_action = lambda e: {"sequence": e["sequence"] * 10, "worker_id": member,
        "payload": {"action": "write_file", "arguments": {"text": completed["files"]["main.py"]}}}
    data.visible = lambda action, before=None: [{"call_id": "actual-next-input", "input_sequence": action["sequence"] + 1}]
    data.metadata_seen = lambda *args: [{"call_id": "actual-metadata-input"}]
    return data, bundles


def test_helper_only_real_change_can_supply_local_and_exact_peer_route():
    local, _ = route()
    peer, _ = route(peer=True)
    assert local.delivery_chain()["category"] == CLASS_ORDER[0]
    evidence = peer.delivery_chain()
    assert evidence["category"] == CLASS_ORDER[1]
    assert evidence["peer_applications"][0]["nonidentity_production_paths"] == ["main.py"]
    assert evidence["peer_applications"][0]["complete_tree_retained_to_final"]


def test_unseen_test_or_adoption_receipt_cannot_create_supported_route():
    data, _ = route(peer=True)
    data.visible = lambda action, before=None: []
    assert data.delivery_chain()["category"] is None
    data.visible = lambda action, before=None: [] if action["sequence"] == 20 else [{"call_id": "test-seen"}]
    assert data.delivery_chain()["category"] is None


def test_unexplained_acquired_patch_and_changed_fixed_tree_do_not_map():
    data, bundles = route(peer=True)
    data.facts["patches"]["unrelated"] = {"author": "member_002"}
    bundles["own", "v1"]["included_patch_ids"].append("unrelated")
    data.facts["deliveries"][0]["source_sha256"] = digest(json_bytes(bundles["own", "v1"]))
    result = data.delivery_chain()
    assert result["category"] is None
    assert "unexplained_peer_acquisition_or_inclusion:unrelated" in result["issues"]
    data, bundles = route(peer=True)
    bundles["peer", "p1"] = copy.deepcopy(bundles["peer", "p1"])
    bundles["peer", "p1"]["files"]["main.py"] += "\n# changed archive\n"
    with pytest.raises(ValueError, match="not exact"):
        data.delivery_chain()


def test_dynamic_or_conflicted_production_is_unmapped():
    assert _production({"x.py": "def f():\n    return eval('1')\n"}, ["x.py"]) is None
    assert _production({"x.py": "<<<<<<<\n"}, ["x.py"]) is None
