"""Temporary-data-only cold archive controls; no experiment is archived."""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile

import pytest

from proworksim import software_cold_archive_v036 as cold


def sample(tmp_path, kind="development"):
    actual = tmp_path / "worker" / "actual"
    actual.mkdir(parents=True)
    (actual / "report.json").write_text('{"status":"complete"}\n')
    source = actual / kind
    source.mkdir()
    (source / "nested").mkdir()
    (source / "nested" / "empty").mkdir()
    (source / "empty").mkdir()
    data = {"trace.jsonl": b'{"original":true}\n', "nested/bytes.bin": bytes(range(256)),
            "nested/中文.txt": "保留原始字节\n".encode(), "zero": b""}
    for name, value in data.items():
        (source / name).write_bytes(value)
    os.chmod(source / "trace.jsonl", 0o640)
    support = actual / "collection"
    support.mkdir()
    (support / "learning-targets").write_bytes(b"must stay live")
    return source, actual / (kind + "-original.tar.gz"), data


@pytest.mark.parametrize("kind", ["development", "confirmation"])
def test_closed_round_trip_all_bytes_paths_and_empty_directories(tmp_path, kind):
    source, archive, expected = sample(tmp_path, kind)
    result = cold.archive_closed_directory(source, archive)
    assert result["state"] == "archived" and result["source_removed"] is True
    assert result["archive_verified"] is True and result["file_count"] == len(expected)
    assert result["original_file_bytes"] == sum(map(len, expected.values()))
    assert not source.exists() and not Path(result["quarantine_path"]).exists()
    assert (archive.parent / "collection/learning-targets").read_bytes() == b"must stay live"
    before = archive.read_bytes(), cold.manifest_path(archive).read_bytes()
    assert cold.verify_archive(archive) == result
    assert before == (archive.read_bytes(), cold.manifest_path(archive).read_bytes())
    destination = tmp_path / "restored"
    restored = cold.restore_archive(archive, destination)
    assert restored["restored"] is restored["archive_preserved"] is True
    actual = {path.relative_to(destination).as_posix(): path.read_bytes()
              for path in destination.rglob("*") if path.is_file()}
    assert actual == expected
    assert (destination / "empty").is_dir() and (destination / "nested/empty").is_dir()
    assert stat.S_IMODE((destination / "trace.jsonl").stat().st_mode) == 0o640
    for entry in result["entries"]:
        assert (destination / entry["path"]).stat().st_mtime_ns == entry["mtime_ns"]
    with pytest.raises(FileExistsError, match="must not exist"):
        cold.restore_archive(archive, destination)
    assert actual == {path.relative_to(destination).as_posix(): path.read_bytes()
                      for path in destination.rglob("*") if path.is_file()}


@pytest.mark.parametrize("case", ["support", "outside_actual", "inside_source", "not_complete", "existing_archive", "existing_manifest"])
def test_archive_scope_completion_and_no_overwrite_guards(tmp_path, case):
    source, archive, expected = sample(tmp_path)
    if case == "support":
        source = source.parent / "collection"
    elif case == "outside_actual":
        archive = tmp_path / "not-in-actual.tar.gz"
    elif case == "inside_source":
        archive = source / "inside.tar.gz"
    elif case == "not_complete":
        (source.parent / "report.json").write_text('{"status":"running"}\n')
    elif case == "existing_archive":
        archive.write_bytes(b"existing archive must not be overwritten")
    elif case == "existing_manifest":
        cold.manifest_path(archive).write_bytes(b"existing manifest must not be overwritten")
    with pytest.raises((ValueError, FileExistsError)):
        cold.archive_closed_directory(source, archive)
    assert source.is_dir()
    if case != "support":
        assert all((source / name).read_bytes() == content for name, content in expected.items())
    if case == "existing_archive":
        assert archive.read_bytes() == b"existing archive must not be overwritten"
    if case == "existing_manifest":
        assert cold.manifest_path(archive).read_bytes() == b"existing manifest must not be overwritten"


@pytest.mark.parametrize("kind", ["symlink_file", "symlink_directory", "hardlink", "fifo"])
def test_source_links_and_special_nodes_preserve_originals(tmp_path, kind):
    source, archive, expected = sample(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"external bytes")
    if kind == "symlink_file":
        (source / "unsafe").symlink_to(sentinel)
    elif kind == "symlink_directory":
        (source / "unsafe").symlink_to(outside, target_is_directory=True)
    elif kind == "hardlink":
        os.link(sentinel, source / "unsafe")
    else:
        os.mkfifo(source / "unsafe")
    with pytest.raises(ValueError, match="Only ordinary"):
        cold.archive_closed_directory(source, archive)
    assert source.exists() and not archive.exists()
    assert sentinel.read_bytes() == b"external bytes"
    assert all((source / name).read_bytes() == content for name, content in expected.items())


def test_verify_failure_occurs_before_any_source_removal(tmp_path, monkeypatch):
    source, archive, expected = sample(tmp_path)
    def fail(*args, **kwargs):
        raise ValueError("injected read-back checksum failure")
    monkeypatch.setattr(cold, "_verify", fail)
    with pytest.raises(ValueError, match="read-back"):
        cold.archive_closed_directory(source, archive)
    assert source.is_dir() and not archive.exists() and not cold.manifest_path(archive).exists()
    assert all((source / name).read_bytes() == content for name, content in expected.items())


def test_manifest_failure_preserves_source_even_after_archive_is_durable(tmp_path, monkeypatch):
    source, archive, expected = sample(tmp_path)
    def fail(*args, **kwargs):
        raise OSError("injected manifest persistence failure")
    monkeypatch.setattr(cold, "_json_write", fail)
    with pytest.raises(OSError, match="manifest persistence"):
        cold.archive_closed_directory(source, archive)
    assert source.is_dir() and archive.is_file() and not cold.manifest_path(archive).exists()
    assert all((source / name).read_bytes() == content for name, content in expected.items())


def test_changed_closed_source_is_retained_in_named_quarantine(tmp_path, monkeypatch):
    source, archive, expected = sample(tmp_path)
    write = cold._json_write
    def modify_after_durable_manifest(path, value, *, replace=False):
        write(path, value, replace=replace)
        if not replace:
            (source / "trace.jsonl").write_bytes(b"late writer must not be lost")
    monkeypatch.setattr(cold, "_json_write", modify_after_durable_manifest)
    with pytest.raises(ValueError, match="changed before duplicate removal"):
        cold.archive_closed_directory(source, archive)
    manifest = cold.verify_archive(archive)
    assert manifest["state"] == "source_retained_archive_verified" and manifest["source_removed"] is False
    quarantine = Path(manifest["retained_source_path"])
    assert quarantine == Path(manifest["quarantine_path"])
    assert (quarantine / "trace.jsonl").read_bytes() == b"late writer must not be lost"
    for name, content in expected.items():
        if name != "trace.jsonl":
            assert (quarantine / name).read_bytes() == content
    restored = tmp_path / "restored-original-snapshot"
    cold.restore_archive(archive, restored)
    assert (restored / "trace.jsonl").read_bytes() == expected["trace.jsonl"]


def test_failed_quarantine_cleanup_retains_verified_archive(tmp_path, monkeypatch):
    source, archive, expected = sample(tmp_path)
    def fail(path):
        raise OSError("injected cleanup interruption")
    fail.avoids_symlink_attacks = True
    monkeypatch.setattr(cold.shutil, "rmtree", fail)
    with pytest.raises(OSError, match="cleanup interruption"):
        cold.archive_closed_directory(source, archive)
    manifest = cold.verify_archive(archive)
    assert manifest["state"] == "cleanup_error_archive_verified"
    assert manifest["source_removed"] is False
    quarantine = Path(manifest["retained_source_path"])
    assert all((quarantine / name).read_bytes() == content for name, content in expected.items())


def crafted_archive(tmp_path, variant):
    archive = tmp_path / "untrusted.tar.gz"
    payload = b"x"
    entry = {"path": "data.bin", "type": "file", "size": 1,
             "sha256": hashlib.sha256(payload).hexdigest(), "mode": 0o600, "mtime_ns": 0}
    with tarfile.open(archive, "w:gz") as stream:
        info = tarfile.TarInfo("data.bin")
        info.size = 1
        if variant == "traversal":
            info.name = "../escaped"
        elif variant == "absolute":
            info.name = str(tmp_path / "escaped")
        elif variant in {"symlink", "hardlink"}:
            info.type = tarfile.SYMTYPE if variant == "symlink" else tarfile.LNKTYPE
            info.linkname, info.size = "../outside", 0
        elif variant == "wrong_bytes":
            payload = b"z"
        stream.addfile(info, io.BytesIO(payload) if info.isreg() else None)
        if variant == "duplicate":
            stream.addfile(info, io.BytesIO(payload))
    manifest = {"version": cold.VERSION, "source_kind": "development", "entries": [entry],
        "root_metadata": {"mode": 0o700, "mtime_ns": 0}, "file_count": 1, "original_file_bytes": 1,
        "archive": {"size": archive.stat().st_size, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}}
    cold.manifest_path(archive).write_text(json.dumps(manifest))
    return archive


@pytest.mark.parametrize("variant", ["traversal", "absolute", "symlink", "hardlink", "duplicate", "wrong_bytes"])
def test_unsafe_or_unfaithful_tar_never_restores(tmp_path, variant):
    archive = crafted_archive(tmp_path, variant)
    outside = tmp_path / "outside"
    outside.write_bytes(b"preserve outside")
    destination = tmp_path / "new-restore"
    with pytest.raises(ValueError):
        cold.verify_archive(archive)
    with pytest.raises(ValueError):
        cold.restore_archive(archive, destination)
    assert not destination.exists() and not (tmp_path / "escaped").exists()
    assert outside.read_bytes() == b"preserve outside"


def test_compressed_corruption_and_restore_link_are_rejected(tmp_path):
    source, archive, _ = sample(tmp_path)
    cold.archive_closed_directory(source, archive)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(archive.parent, target_is_directory=True)
    with pytest.raises(ValueError, match="Symbolic"):
        cold.restore_archive(archive, linked_parent / "new")
    with pytest.raises(ValueError, match="traversal"):
        cold.restore_archive(archive, tmp_path / ".." / "new")
    raw = bytearray(archive.read_bytes())
    raw[-1] ^= 1
    archive.write_bytes(raw)
    with pytest.raises(ValueError, match="checksum"):
        cold.verify_archive(archive)
