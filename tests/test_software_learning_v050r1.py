"""Finite CPU registry boundaries; synthetic metadata, no model/tensor load."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from proworksim import software_learning_v050 as original
from proworksim import software_learning_v050r1 as learning
from proworksim.software_training_v050 import unavailable_slot_entry
from proworksim.storage import atomic_write, digest, json_bytes
from test_software_learning_v050 import fixture


def _write(path, value):
    atomic_write(path, json_bytes(value))
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def _registry(tmp_path):
    entries, declaration, _, _, _, _ = fixture()
    resumed = tmp_path / "resume"
    sources = []
    for index, entry in enumerate(entries):
        folder = (tmp_path / "original" if index == 0 else resumed) / entry["slot_id"]
        manifest = entry["rollout"]["manifest"]
        runtime = {"version": "software-organization-runtime-v0.50", "slot_id": entry["slot_id"],
            "sampling_seed": 202610130501 + index, "purpose": "policy_training",
            "online_window_id": declaration["window_id"], "actor_identity": declaration["actor_identity"]}
        manifest.update(status="closed", scenario={"variation": {"organization_runtime": runtime}})
        manifest_ref = _write(folder / "episode/manifest.json", manifest)
        entry["rollout"].update(episode_path=str(folder / "episode"), manifest_sha256=manifest_ref["sha256"])
        result = {**runtime, "episode_manifest": manifest_ref["path"]}
        entry_path = (resumed / "retained" if index == 0 else folder) / "training-entry.json"
        sources.append({"slot_id": entry["slot_id"], "entry": _write(entry_path, entry),
            "source_manifest": manifest_ref, "source_result": _write(folder / "slot-result.json", result)})
    registry = {"version": learning.REGISTRY_VERSION, "slot_count": 24, "old_material_included": False,
        "sources": sources, "declaration": _write(resumed / "declaration.json", declaration)}
    _seal(resumed / "source-registry.json", registry)
    return entries, declaration, resumed, registry


def _seal(path, value):
    value["sha256"] = digest(json_bytes({key: item for key, item in value.items() if key != "sha256"}))
    _write(path, value)


def test_registry_resolves_one_original_and_23_resume_sources_without_numeric_changes(tmp_path):
    entries, declaration, resumed, _ = _registry(tmp_path)
    folders, proof = learning._source_folders(entries, declaration, resumed)
    assert len(folders) == 24
    assert folders[learning.SLOT_IDS[0]].parent == tmp_path / "original"
    assert all(folder.parent == resumed for sid, folder in folders.items() if sid != learning.SLOT_IDS[0])
    assert proof["original_slot_count"] == 24 and proof["original_declaration_changed"] is False
    assert learning.validate_training_entries.__code__ is original.validate_training_entries.__code__
    assert learning.update_software_window.__code__ is original.update_software_window.__code__
    assert learning.update_window is original.update_window
    assert learning.prepare_training_admission is original.prepare_training_admission
    assert original.validate_training_entries.__globals__["_source_folders"] is original._source_folders


def test_missing_training_record_keeps_declared_mass_without_inventing_a_source(tmp_path):
    entries, declaration, resumed, registry = _registry(tmp_path)
    entries[0] = unavailable_slot_entry(declaration, learning.SLOT_IDS[0],
        "Explicit CPU missing-record control: original raw source retained, target material unavailable")
    registry["sources"][0]["entry"] = _write(Path(registry["sources"][0]["entry"]["path"]), entries[0])
    _seal(resumed / "source-registry.json", registry)
    folders, proof = learning._source_folders(entries, declaration, resumed)
    assert len(folders) == 23 and learning.SLOT_IDS[0] not in folders
    assert proof["original_slot_count"] == 24 and len(entries) == 24


@pytest.mark.parametrize("mutation", ["old-registry", "seal", "drop", "order", "changed-entry", "wrong-manifest", "wrong-seed", "old-runtime", "other-actor", "other-window"])
def test_registry_rejects_missing_replaced_reordered_or_relabelled_material(tmp_path, mutation):
    entries, declaration, resumed, registry = _registry(tmp_path)
    if mutation == "old-registry":
        registry["version"] = "v049-unique-source-registry-r1"
    elif mutation == "seal":
        registry["slot_count"] = 8
    elif mutation == "drop":
        registry["sources"].pop()
    elif mutation == "order":
        registry["sources"].reverse()
    elif mutation == "changed-entry":
        entries[0]["reward"]["reward"] = 0
    elif mutation == "wrong-manifest":
        registry["sources"][0]["source_manifest"] = copy.deepcopy(registry["sources"][1]["source_manifest"])
    else:
        manifest = entries[0]["rollout"]["manifest"]
        runtime = manifest["scenario"]["variation"]["organization_runtime"]
        key, value = {"wrong-seed": ("sampling_seed", 202610120491),
            "old-runtime": ("version", "software-organization-runtime-v0.49"),
            "other-actor": ("actor_identity", {"policy_version": "another-state"}),
            "other-window": ("online_window_id", "other-window")}[mutation]
        runtime[key] = value
        source = registry["sources"][0]
        source["source_manifest"] = _write(Path(source["source_manifest"]["path"]), manifest)
        entries[0]["rollout"]["manifest_sha256"] = source["source_manifest"]["sha256"]
        source["entry"] = _write(Path(source["entry"]["path"]), entries[0])
        source["source_result"] = _write(Path(source["source_result"]["path"]), {
            **runtime, "episode_manifest": source["source_manifest"]["path"]})
    if mutation == "seal":
        _write(resumed / "source-registry.json", registry)
    else:
        _seal(resumed / "source-registry.json", registry)
    with pytest.raises(ValueError):
        learning._source_folders(entries, declaration, resumed)
