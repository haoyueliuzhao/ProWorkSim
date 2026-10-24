"""Necessary CPU proofs for the non-UTF8 official prediction repair."""
import json
import os
from pathlib import Path

import pytest

from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_native_artifact_v054 import (
    export_native_git_patch, snapshot_native_candidate,
)
from proworksim.software_benchmark_patch_transport_v056 import prepare_transport, validate_transport


def make_lock(tmp_path, *, opaque_link=False):
    work = tmp_path / "work"
    work.mkdir()
    (work / "code.py").write_bytes(b"answer = 1\r\n")
    (work / "obsolete").write_bytes(b"delete me\n")
    (work / "mode.sh").write_bytes(b"exit 0\n")
    (work / "compressed.inv").write_bytes(b"old payload\n")
    (work / "link").symlink_to("code.py")
    # Candidate attributes must not override the exact transport rule.
    (work / ".gitattributes").write_text("* diff text eol=lf\n")
    before = snapshot_native_candidate(work)
    (work / "code.py").write_bytes(b"answer = 2\r\n")
    (work / "obsolete").unlink()
    (work / "mode.sh").chmod(0o755)
    (work / "new[1] file.pdf").write_bytes(b"%PDF-1.0\n\xff\xfe no NUL payload\n")
    (work / "compressed.inv").write_bytes(b"\xfe no NUL compressed payload\n")
    (work / "新文件").write_bytes(b"valid bytes\n")
    (work / "link").unlink()
    os.symlink(b"\xffopaque-target" if opaque_link else "新文件".encode(), os.fsencode(work / "link"))
    after = snapshot_native_candidate(work)
    original = export_native_git_patch(before, after, tmp_path / "original.patch")
    return write_new(tmp_path / "lock.json", {
        "version": "software-benchmark-native-closure-v054", "lock_before_grading": True,
        "endpoint": "terminal_code", "slot": {"arm": "REF", "slot_id": "cpu:fixed",
            "condition_id": "REF_B5000K", "instance_id": "cpu:task"},
        "baseline": write_new(tmp_path / "baseline.json", before),
        "candidate": write_new(tmp_path / "terminal.json", after),
        "patch_receipt": original, "tree_sha256": original["candidate_tree_sha256"],
    })


def test_binary_transport_preserves_locked_tree_links_and_modes(tmp_path):
    locked = make_lock(tmp_path)
    original = (tmp_path / "original.patch").read_bytes()
    with pytest.raises(UnicodeDecodeError):
        original.decode("utf-8")
    transport = prepare_transport(locked, tmp_path / "transport")
    receipt = validate_transport(locked, transport)
    raw = Path(receipt["transport_patch"]["path"]).read_bytes()
    raw.decode("utf-8", "strict")
    assert raw.count(b"GIT binary patch") == 2
    assert b"answer = 2" in raw  # Normal source hunks retain their existing representation.
    assert receipt["forced_binary_paths"] == ["compressed.inv", "new[1] file.pdf"]
    assert receipt["original_patch_round_trip_verified"]
    assert receipt["transport_patch_round_trip_verified"]
    assert (tmp_path / "original.patch").read_bytes() == original
    assert receipt["candidate_content_changed"] is False
    assert receipt["candidate_files_filtered"] is False
    with pytest.raises(FileExistsError):
        prepare_transport(locked, tmp_path / "transport")


def test_binding_rejects_other_candidate_and_mutated_transport(tmp_path):
    locked = make_lock(tmp_path)
    transport = prepare_transport(locked, tmp_path / "transport")
    body = json.loads((tmp_path / "lock.json").read_text())
    body["slot"]["slot_id"] = "cpu:another"
    alternate = write_new(tmp_path / "another-lock.json", body)
    with pytest.raises(ValueError, match="not bound"):
        validate_transport(alternate, transport)
    patch = tmp_path / "transport/candidate-utf8.patch"
    patch.write_bytes(patch.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="Immutable"):
        validate_transport(locked, transport)


def test_original_patch_must_reproduce_target_even_with_updated_file_hash(tmp_path):
    locked = make_lock(tmp_path)
    original = tmp_path / "original.patch"
    original.write_bytes(original.read_bytes().replace(b"+answer = 2", b"+answer = 7"))
    lock = json.loads((tmp_path / "lock.json").read_text())
    lock["patch_receipt"]["patch"] = reference(original)
    locked = write_new(tmp_path / "bad-original-lock.json", lock)
    with pytest.raises(ValueError, match="exact locked candidate"):
        prepare_transport(locked, tmp_path / "transport")


def test_unsupported_opaque_link_never_gets_lossy_replacement(tmp_path):
    locked = make_lock(tmp_path, opaque_link=True)
    with pytest.raises(ValueError, match="UTF-8-safe"):
        prepare_transport(locked, tmp_path / "transport")
    assert not (tmp_path / "transport/receipt.json").exists()
