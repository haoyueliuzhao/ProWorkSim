"""Private consumer binding and unique original-source registry controls."""
import copy

import pytest

from proworksim import online_training
from proworksim import software_learning_v049 as original
from proworksim import software_learning_v049r1 as revised
from proworksim.software_member_views_v049r1 import member_view, prepare_window
from proworksim.storage import atomic_write, digest, json_bytes
from test_software_member_views_v049r1 import fixture


def test_all_native_learning_consumers_use_one_private_reader_without_changing_H1_code():
    assert revised._numeric_update.__code__ is online_training.SharedActor.update_window.__code__
    assert revised._numeric_update.__globals__["prepare_window"] is prepare_window
    assert revised._original_update_adapter.__code__ is original.update_window.__code__
    assert revised._original_update_adapter.__globals__["SharedActor"].update_window is revised._numeric_update
    assert revised.validate_composition.__code__ is original.validate_composition.__code__
    assert revised.validate_composition.__globals__["member_view"] is member_view
    assert revised.update_software_window.__code__ is original.update_software_window.__code__
    assert revised.update_software_window.__globals__["validate_training_entries"] is revised.validate_training_entries
    assert revised.update_software_window.__globals__["update_window"] is revised.update_window
    assert original.member_view is not member_view and online_training.prepare_window is not prepare_window
    assert revised.software_feature_function is original.software_feature_function
    assert revised.bind_composition is original.bind_composition


def test_source_registry_keeps_original_order_and_rejects_duplicate_or_swapped_material(tmp_path):
    left, lf = fixture(tmp_path / "left", "tokens")
    right, rf = fixture(tmp_path / "right", "context")
    entries = [{"slot_id": folder.name, "rollout": rollout} for rollout, folder in ((left, lf), (right, rf))]
    declaration = {"slots": [{"slot_id": entry["slot_id"]} for entry in entries]}
    registry = {"version": revised.REGISTRY_VERSION, "slots": [
        {"slot_id": folder.name, "episode_folder": str(folder), "origin": origin,
         "source_result": revised._reference(folder / "slot-result.json"),
         "source_manifest": revised._reference(folder / "episode/manifest.json")}
        for folder, origin in ((lf, "original_v049"), (rf, "resume_r1"))]}
    path = tmp_path / "source-registry.json"
    def write(value):
        value = copy.deepcopy(value)
        value["sha256"] = digest(json_bytes({key: row for key, row in value.items() if key != "sha256"}))
        atomic_write(path, json_bytes(value))
    write(registry)
    folders, proof = revised._source_folders(entries, declaration, path)
    assert list(folders) == [lf.name, rf.name] and proof["kind"] == "sealed_unique_source_registry"
    for folder in (lf, rf):
        raw = folder / "raw-transport/request-00001"
        atomic_write(raw / "selected-request.json", json_bytes({"explicit_cpu_fixture": True}))
        atomic_write(raw / "projection.json", json_bytes({"explicit_cpu_fixture": True}))
        atomic_write(raw / "response.json", json_bytes({"http_status": 200,
            "body": {"id": folder.name, "token_trace": {"input_ids": [1], "output_ids": [2]}}}))
    assert set(revised._source_index(folders)) == {lf.name, rf.name}
    changed = copy.deepcopy(registry)
    changed["slots"].reverse()
    write(changed)
    with pytest.raises(ValueError, match="ordered inventory"):
        revised._source_folders(entries, declaration, path)
    changed = copy.deepcopy(registry)
    changed["slots"][0]["episode_folder"] = str(rf)
    write(changed)
    with pytest.raises(ValueError, match="unique registry slot"):
        revised._source_folders(entries, declaration, path)
    write(registry)
    atomic_write(rf / "raw-transport/request-00001/response.json", json_bytes({"http_status": 200,
        "body": {"id": lf.name, "token_trace": {"input_ids": [1], "output_ids": [2]}}}))
    with pytest.raises(ValueError, match="globally unique"):
        revised._source_index(folders)
    with pytest.raises(ValueError, match="outside the declared"):
        revised._source_folders(entries, declaration, [lf])
