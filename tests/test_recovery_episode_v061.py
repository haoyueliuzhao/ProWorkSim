"""CPU-only recovery-boundary checks; no Docker, model or network resources."""
import io
import json
import tarfile
import threading

import pytest

from proworksim import software_benchmark_recovery_episode_v061 as episode
from proworksim.software_benchmark_candidates_v054 import reference


def archive(path, members):
    with tarfile.open(path, "w") as out:
        for name, body, kind, mode in members:
            info = tarfile.TarInfo(name)
            info.mode = mode
            if kind == "file":
                info.size = len(body)
                out.addfile(info, io.BytesIO(body))
            else:
                info.type = tarfile.SYMTYPE
                info.linkname = body
                out.addfile(info)


def test_closed_native_archive_retains_binary_modes_and_opaque_links(tmp_path):
    path = tmp_path / "tree.tar"
    archive(path, [("testbed/normal.py", b"print('ok')\n", "file", 0o755),
                   ("testbed/binary", b"\xff\0\x80", "file", 0o644),
                   ("testbed/link", "/absolute/not-followed", "link", 0o777),
                   ("testbed/.git/config", b"not part of patch", "file", 0o644)])
    bundle = episode.archive_bundle(path)
    assert set(bundle["files"]) == {"normal.py", "binary", "link"}
    assert bundle["entry_metadata"]["normal.py"]["mode"] == "100755"
    assert bundle["entry_metadata"]["binary"]["encoding"] == "base64"
    assert bundle["files"]["link"] == "/absolute/not-followed"
    assert bundle["symlink_targets_followed"] is False and bundle["truncated"] is False
    # Byte-safe exporter must preserve that complete unique terminal tree.
    empty = {"files": {}, "entry_metadata": {}, "gitlinks": []}
    result = episode.export_utf8_patch(empty, bundle, tmp_path / "candidate.patch")
    assert result["round_trip_verified"] is True
    assert result["candidate_tree_sha256"] == bundle["tree"]["tree_sha256"]


@pytest.mark.parametrize("name", ["testbed/../escape", "/testbed/file", "other/file"])
def test_worktree_tar_cannot_escape_declared_root(tmp_path, name):
    path = tmp_path / "bad.tar"
    archive(path, [(name, b"x", "file", 0o644)])
    with pytest.raises(ValueError, match="escapes"):
        episode.archive_bundle(path)


def test_controller_output_paths_are_mapped_without_rewriting_raw_json(tmp_path):
    path = tmp_path / "controller.tar"
    raw = json.dumps({"ledger": "/pws/output/ref-ledger/ledger.json"}).encode()
    archive(path, [("output/controller-result.json", raw, "file", 0o600)])
    root = tmp_path / "retained"
    relocation = episode.extract_controller_output(path, root)
    assert (root / "controller-result.json").read_bytes() == raw
    assert relocation["container_prefix"] == "/pws/output"
    assert relocation["host_prefix"] == str(root.resolve())
    assert relocation["raw_json_references_rewritten"] is False


def test_controller_output_link_does_not_create_host_alias(tmp_path):
    path = tmp_path / "controller.tar"
    archive(path, [("output/escape", "/tmp", "link", 0o777)])
    with pytest.raises(ValueError, match="link/special"):
        episode.extract_controller_output(path, tmp_path / "retained")
    assert not (tmp_path / "retained/escape").exists()


def test_cancelled_capacity_never_consumes_authorization_or_resources(monkeypatch):
    event = threading.Event()
    event.set()
    monkeypatch.setattr(episode.policy, "require_v061_allowed", lambda *a, **k: pytest.fail("No resource admission after cancellation"))
    with pytest.raises(InterruptedError, match="before resource admission"):
        episode.wait_capacity(event)


def test_preparation_failure_has_explicit_unknown_and_quiescence_without_docker(tmp_path, monkeypatch):
    row = {"slot_index": 2, "slot_id": "original", "recovery_slot_id": "original:v061-r1",
           "condition_id": "REF_B2000K", "instance_id": "task", "seed": 11,
           "original_config": {"path": "fixed"}}
    monkeypatch.setattr(episode, "BATCH", tmp_path)
    monkeypatch.setattr(episode, "_row_and_config", lambda *a: ({}, {}, {}))
    monkeypatch.setattr(episode, "wait_capacity", lambda *a: {"admit": True})
    def fail():
        raise ValueError("frozen runtime archive changed")
    monkeypatch.setattr(episode.runtime, "prepare_bundle", fail)
    result_ref = episode.run_episode(row, {})
    result = episode.load(result_ref)
    assert result["status"] == "technical_unknown" and result["candidate_lock"] is None
    assert result["error"]["message"] == "frozen runtime archive changed"
    quiet = episode.load(result["quiescence"])
    assert quiet["quiescent"] is True and quiet["removed_roles"] == []
    assert quiet["create_result_unknown"] is False
    assert reference(tmp_path / "episodes/2/result.json") == result_ref
