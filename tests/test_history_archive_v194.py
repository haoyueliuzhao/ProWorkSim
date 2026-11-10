import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('archive194', Path(__file__).resolve().parents[1] / 'tools/archive_completed_worlds_v194.py')
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


def sample(tmp_path):
    root = tmp_path / 'old-world'; root.mkdir()
    a = root / 'version-a.json'; b = root / 'version-b.json'
    a.write_bytes(b'{"source":"shared immutable code"}' * 4096)
    b.write_bytes(b'{"source":"revised immutable code"}' * 4096)
    rows = [{**archive.identity(p), 'relative': p.name} for p in (a, b)]
    return root, rows


def test_full_readback_precedes_release_and_preserves_exact_originals(tmp_path):
    root, rows = sample(tmp_path)
    blob, manifest = archive.encode(root, rows, tmp_path / 'retained', disk_floor=0)
    proof = archive.verify(blob, manifest)
    assert proof['files'] == 2
    assert all((root / r['relative']).is_file() for r in rows)
    assert archive.release(root, manifest) == sum(r['allocated'] for r in rows)
    assert blob.is_file() and not list(root.iterdir())
    assert archive.verify(blob, manifest)['full_decompression_and_all_file_hashes_verified']


def test_changed_source_blocks_entire_release(tmp_path):
    root, rows = sample(tmp_path)
    blob, manifest = archive.encode(root, rows, tmp_path / 'retained', disk_floor=0)
    archive.verify(blob, manifest)
    (root / rows[1]['relative']).write_bytes(b'changed after encoding')
    with pytest.raises(ValueError, match='changed'):
        archive.release(root, manifest)
    assert all((root / r['relative']).is_file() for r in rows)


def test_corrupt_archive_cannot_verify(tmp_path):
    root, rows = sample(tmp_path)
    blob, manifest = archive.encode(root, rows, tmp_path / 'retained', disk_floor=0)
    blob.write_bytes(blob.read_bytes()[:12])
    with pytest.raises((ValueError, EOFError, archive.tarfile.TarError)):
        archive.verify(blob, manifest)
    assert all((root / r['relative']).is_file() for r in rows)


def test_traversal_or_shared_hardlink_is_refused(tmp_path):
    root, rows = sample(tmp_path)
    with pytest.raises(ValueError):archive.member_path(root, '../outside')
    (root / 'shared').hardlink_to(root / rows[0]['relative'])
    with pytest.raises(ValueError):archive.identity(root / rows[0]['relative'])
