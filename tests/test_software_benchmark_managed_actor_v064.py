"""Necessary CPU controls for complete-tree transfer without model shell access."""
import copy
import subprocess

import pytest

from proworksim import software_benchmark_managed_actor_v064 as actor
from proworksim.repository_sources_v054 import snapshot_repository, tree_manifest


def baseline(tmp_path):
    root = tmp_path / "actor"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / ".git/pws-fixture").write_text("original control metadata\n")
    (root / "main.py").write_text("value = 0\n")
    (root / "locked.txt").write_text("protected\n")
    (root / "old.bin").write_bytes(b"\0\xffbinary")
    return root, snapshot_repository(root, file_policy={"readonly_paths": ["locked.txt"]})


def request_for(files, metadata):
    return {"tree_sha256": tree_manifest(files, metadata)["tree_sha256"],
            "source_reference": {"object_id": "fixture", "version_id": "version-2"}}


def test_delta_recreates_complete_tree_and_cleans_test_side_effects_without_touching_git(tmp_path):
    root, old = baseline(tmp_path)
    files, metadata = copy.deepcopy(old["files"]), copy.deepcopy(old["entry_metadata"])
    files["main.py"] = "value = 1\n"
    files["assets/renamed.bin"] = files.pop("old.bin")
    metadata["assets/renamed.bin"] = metadata.pop("old.bin")
    payload = actor.make_delta(old, files, metadata, request=request_for(files, metadata))
    assert "locked.txt" not in payload["changed_files"]
    assert payload["deleted_paths"] == ["old.bin"]
    candidate = actor.reconstruct_delta(old, payload)
    (root / "__pycache__").mkdir()
    (root / "__pycache__/generated.pyc").write_bytes(b"generated test cache")
    (root / "main.py").write_text("unintended public-test side effect\n")
    actual = actor.synchronize_tree(root, candidate)
    assert actual["exact_complete_tree"] is True
    assert (root / "main.py").read_text() == "value = 1\n"
    assert (root / "assets/renamed.bin").read_bytes() == b"\0\xffbinary"
    assert not (root / "old.bin").exists() and not (root / "__pycache__").exists()
    assert (root / ".git/pws-fixture").read_text() == "original control metadata\n"


def test_forged_baseline_or_missing_whole_tree_bytes_cannot_pass_transfer(tmp_path):
    _, old = baseline(tmp_path)
    payload = actor.make_delta(old, old["files"], old["entry_metadata"],
                               request=request_for(old["files"], old["entry_metadata"]))
    wrong = copy.deepcopy(payload)
    wrong["baseline_tree_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="baseline"):
        actor.reconstruct_delta(old, wrong)
    wrong = copy.deepcopy(payload)
    wrong["deleted_paths"] = ["main.py"]
    with pytest.raises(ValueError, match="complete tree"):
        actor.reconstruct_delta(old, wrong)
    changed = dict(old["files"], **{"locked.txt": "unauthorized"})
    wrong = actor.make_delta(old, changed, old["entry_metadata"], request=request_for(changed, old["entry_metadata"]))
    with pytest.raises(ValueError, match="protected baseline"):
        actor.reconstruct_delta(old, wrong)


def test_delta_is_not_capped_by_the_internal_per_frame_size(tmp_path, monkeypatch):
    _, old = baseline(tmp_path)
    monkeypatch.setattr(actor, "MAX_RPC_BYTES", 4200)
    result = actor.make_delta(old, old["files"], old["entry_metadata"],
                             request=request_for(old["files"], old["entry_metadata"]))
    assert result["candidate_tree_sha256"] == old["tree"]["tree_sha256"]


def test_public_entry_rejects_model_command_overrides_and_host_child_cleanup():
    entry = {"version": actor.PUBLIC_ENTRY_VERSION, "instance_id": "fixture", "argv": ["/env/bin/python", "-m", "pytest"],
             "cwd": "/testbed", "timeout_seconds": 1800, "hidden_material_used": False}
    assert actor.validate_public_entry(entry, instance_id="fixture", public_python="/env/bin/python") == entry
    for wrong in ({**entry, "argv": ["/bin/bash", "-c", "anything"]},
                  {**entry, "cwd": "/"}, {**entry, "hidden_material_used": True},
                  {**entry, "command": "arbitrary"}, {**entry, "timeout_seconds": 1801}):
        with pytest.raises(ValueError):
            actor.validate_public_entry(wrong, instance_id="fixture", public_python="/env/bin/python")
    with pytest.raises(ValueError, match="private actor PID"):
        actor._reap_private_children()
