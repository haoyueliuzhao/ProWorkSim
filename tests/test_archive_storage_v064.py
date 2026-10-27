import hashlib
import io
import os
from pathlib import Path
import tarfile

import pytest

from proworksim.software_benchmark_archive_storage_v064 import (
    ArchiveLimitExceeded, compress_transport_archive, export_compressed_stream,
    open_verified_archive, prepare_zstd_codec, retain_baseline, stream_reference,
)


def test_transport_roundtrip_preserves_bytes_and_verifies_unread_tail(tmp_path):
    path = tmp_path / "record.tar"
    content = b"\x00\xff\xe0" * 100000 + b"last"
    path.write_bytes(content)
    result = compress_transport_archive(path, stream_reference(path), allowed_root=tmp_path)
    assert not path.exists()
    with open_verified_archive(result) as stream:
        assert stream.read(3) == content[:3]
    bad = {**result, "decompressed_sha256": hashlib.sha256(content[:-1]).hexdigest()}
    with pytest.raises(ValueError, match="differs"):
        with open_verified_archive(bad) as stream:
            stream.read(1)


def test_wrong_transfer_does_not_remove_original(tmp_path):
    path = tmp_path / "record.tar"
    path.write_bytes(b"original")
    expected = {**stream_reference(path), "sha256": "0" * 64}
    with pytest.raises(ValueError, match="changed"):
        compress_transport_archive(path, expected, allowed_root=tmp_path)
    assert path.read_bytes() == b"original"


def test_baseline_hardlinks_only_identical_complete_json(tmp_path):
    store = tmp_path / "store"
    one, two, three = [tmp_path / name for name in ("one.json", "two.json", "three.json")]
    a = retain_baseline({"files": {"a": "full"}, "mode": "100755"}, one, store)
    b = retain_baseline({"files": {"a": "full"}, "mode": "100755"}, two, store)
    c = retain_baseline({"files": {"a": "changed"}, "mode": "100755"}, three, store)
    assert a["sha256"] == b["sha256"] != c["sha256"]
    assert os.stat(one).st_ino == os.stat(two).st_ino != os.stat(three).st_ino


def test_symlink_and_outside_archive_are_never_deleted(tmp_path):
    source = tmp_path / "source.tar"
    source.write_bytes(b"safe")
    link = tmp_path / "link.tar"
    link.symlink_to(source)
    with pytest.raises(ValueError):
        compress_transport_archive(link, stream_reference(source), allowed_root=tmp_path)
    with pytest.raises(ValueError):
        compress_transport_archive(source, stream_reference(source), allowed_root=tmp_path / "other")
    assert source.read_bytes() == b"safe" and link.is_symlink()


def test_zstd_streamed_tar_preserves_raw_bytes_and_checks_unread_tail(tmp_path):
    codec = prepare_zstd_codec()
    buffer = io.BytesIO()
    ledger = b'{"complete_actual_tokens":1234,"uncertain_reserved_tokens":0}\n'
    files = {"output/model-ledger/ledger.json": ledger,
             "output/managed-world/versions/full.json": b'{"source":"entire retained version"}\n' * 90000}
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    raw = buffer.getvalue()
    chunks = (raw[index:index + 7919] for index in range(0, len(raw), 7919))
    storage = export_compressed_stream(chunks, tmp_path / "controller.tar.zst",
                                       allowed_root=tmp_path, codec_manifest=codec)
    assert storage["decompressed_bytes"] == len(raw)
    assert storage["decompressed_sha256"] == hashlib.sha256(raw).hexdigest()
    assert storage["blob"] == stream_reference(tmp_path / "controller.tar.zst")
    assert storage["round_trip_verified"] is False and not list(tmp_path.glob("*.tar"))
    with open_verified_archive(storage) as source:
        with tarfile.open(fileobj=source, mode="r|") as archive:
            member = next(iter(archive))
            assert archive.extractfile(member).read() == ledger
            # Leave the large historical-source member unread deliberately.
    assert storage["round_trip_verified"] is False  # Only caller may seal post-consumer provenance.
    bad = {**storage, "decompressed_sha256": "0" * 64}
    with pytest.raises(ValueError, match="Decompressed archive differs"):
        with open_verified_archive(bad) as source:
            source.read(7)


def test_zstd_limits_keep_only_partial_new_files_and_stop_owned_codec(tmp_path, monkeypatch):
    from proworksim import software_benchmark_archive_storage_v064 as module
    codec = prepare_zstd_codec()
    original_popen, children = module.subprocess.Popen, []
    def tracked(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        children.append(process)
        return process
    monkeypatch.setattr(module.subprocess, "Popen", tracked)
    with pytest.raises(ArchiveLimitExceeded, match="Raw archive"):
        export_compressed_stream([b"too much source"], tmp_path / "raw-limit.zst",
            allowed_root=tmp_path, codec_manifest=codec, maximum_raw_bytes=3)
    with pytest.raises(ArchiveLimitExceeded, match="Compressed archive"):
        export_compressed_stream([os.urandom(20000)], tmp_path / "packed-limit.zst",
            allowed_root=tmp_path, codec_manifest=codec, maximum_compressed_bytes=3)
    assert children and all(child.poll() is not None for child in children)
    assert (tmp_path / "packed-limit.zst").stat().st_size <= 3
    assert not list(tmp_path.glob("*.tar"))
    sentinel = tmp_path / "existing.zst"
    sentinel.write_bytes(b"existing data")
    with pytest.raises(FileExistsError):
        export_compressed_stream([b"new"], sentinel, allowed_root=tmp_path, codec_manifest=codec)
    assert sentinel.read_bytes() == b"existing data"


def test_zstd_corrupt_frame_and_changed_storage_never_return_complete_receipt(tmp_path):
    codec = prepare_zstd_codec()
    storage = export_compressed_stream([b"exact binary\0\xff\xe0" * 1000], tmp_path / "valid.zst",
                                       allowed_root=tmp_path, codec_manifest=codec)
    bad = tmp_path / "truncated.zst"
    bad.write_bytes(Path(storage["blob"]["path"]).read_bytes()[:-4])
    changed = {**storage, "blob": stream_reference(bad)}
    with pytest.raises(ValueError):
        with open_verified_archive(changed) as source:
            source.read(1)
    changed = {**storage, "blob": {**storage["blob"], "sha256": "0" * 64}}
    with pytest.raises(ValueError, match="Compressed transport archive changed"):
        with open_verified_archive(changed):
            pass
