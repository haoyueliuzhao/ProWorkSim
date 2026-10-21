"""Only new output-link boundaries and evidence-bound clone cleanup."""
import json
import os

import pytest

from proworksim import software_benchmark_rootfs_io_v054 as io


def test_actor_output_is_complete_bounded_regular_and_never_follows_links(tmp_path):
    root = tmp_path / "rootfs"
    folder = root / "tmp"
    folder.mkdir(parents=True)
    path = folder / "stdout"
    path.write_bytes(b"complete output")
    assert io.read_actor_bytes(root, "tmp/stdout", maximum_bytes=16) == b"complete output"
    path.write_bytes(b"x" * 17)
    with pytest.raises(ValueError, match="exceeds"):
        io.read_actor_bytes(root, "tmp/stdout", maximum_bytes=16)
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "stdout"
    secret.write_text("outside-must-stay-unread")
    path.unlink()
    path.symlink_to(secret)
    with pytest.raises(OSError):
        io.read_actor_bytes(root, "tmp/stdout")
    path.unlink()
    folder.rmdir()
    folder.symlink_to(outside)
    with pytest.raises(OSError):
        io.read_actor_bytes(root, "tmp/stdout")
    folder.unlink()
    folder.mkdir()
    os.mkfifo(path)
    with pytest.raises(ValueError, match="regular"):
        io.read_actor_bytes(root, "tmp/stdout")
    assert secret.read_text() == "outside-must-stay-unread"


def test_only_quiet_clone_removed_after_evidence_retained(tmp_path, monkeypatch):
    monkeypatch.setattr(io, "ROOT", tmp_path)
    episode = tmp_path / "runs/software-benchmark-v054/synthetic-episode"
    root = episode / "clone/rootfs"
    root.mkdir(parents=True)
    outside = episode / "keep.txt"
    outside.write_text("retained")
    (root / "outside-link").symlink_to(outside)
    (root / "temporary.txt").write_text("temporary")
    manifest = episode / "clone/rootfs-manifest.json"
    manifest.write_text(json.dumps({"prepared_root": str(root), "cloned_from_manifest_sha256": "a" * 64}))
    unit = "proworksim-v054-episode-" + "b" * 32 + "-actor.service"
    stopped = {"unit": unit, "populated": False, "main_pid": 0, "active_state": "inactive",
               "cgroup": "/proworksimv054ep" + "b" * 32 + ".slice/" + unit}
    proof = episode / "quiescence.json"
    proof.write_text(json.dumps({**stopped, "outer_launcher_reaped": True}))
    request = {"rootfs": str(root), "episode_root": str(episode),
               "rootfs_manifest": io.reference(manifest), "quiescence": io.reference(proof),
               "retained_evidence": [io.reference(outside)]}
    assert io.validate_cleanup(request) == root
    changed = {**request, "retained_evidence": [io.reference(root / "temporary.txt")]}
    with pytest.raises(ValueError, match="inside"):
        io.validate_cleanup(changed)
    proof.write_text(json.dumps({**stopped, "populated": True, "outer_launcher_reaped": True}))
    with pytest.raises(ValueError, match="quiescence"):
        io.validate_cleanup({**request, "quiescence": io.reference(proof)})
    proof.write_text(json.dumps({**stopped, "outer_launcher_reaped": True}))
    request["quiescence"] = io.reference(proof)
    result = io.remove_validated_root(request)
    assert result["removed"] and not root.exists()
    assert outside.read_text() == "retained"
    assert manifest.is_file() and proof.is_file()
