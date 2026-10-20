"""Only the new full-rootfs transport and image environment derivation contracts."""
import hashlib
import io
import json
import tarfile

import pytest

from proworksim.software_benchmark_native_worker_v054 import validate_rootfs

from proworksim.software_benchmark_native_rootfs_v054 import extract_rootfs, image_environment


def test_rootfs_extraction_preserves_links_without_following_host_absolute_targets(tmp_path):
    archive_path = tmp_path / "safe.tar"
    with tarfile.open(archive_path, "w") as archive:
        item = tarfile.TarInfo("usr/lib/public.txt")
        item.size, item.mode, item.uid, item.gid = 7, 0o644, 42, 43
        archive.addfile(item, io.BytesIO(b"public\n"))
        item = tarfile.TarInfo("usr/lib/hard.txt")
        item.type, item.linkname = tarfile.LNKTYPE, "usr/lib/public.txt"
        archive.addfile(item)
        item = tarfile.TarInfo("lib")
        item.type, item.linkname = tarfile.SYMTYPE, "/usr/lib"
        archive.addfile(item)
    root = tmp_path / "rootfs"
    manifest = extract_rootfs(archive_path, root)
    assert (root / "lib").readlink().as_posix() == "/usr/lib"
    assert (root / "usr/lib/public.txt").read_bytes() == b"public\n"
    assert (root / "usr/lib/hard.txt").stat().st_ino == (root / "usr/lib/public.txt").stat().st_ino
    entry = next(item for item in manifest["entries"] if item["path"] == "usr/lib/public.txt")
    assert (entry["uid"], entry["gid"]) == (42, 43)
    outside = tmp_path / "outside"
    outside.mkdir()
    attack = tmp_path / "attack.tar"
    with tarfile.open(attack, "w") as archive:
        item = tarfile.TarInfo("escape")
        item.type, item.linkname = tarfile.SYMTYPE, str(outside)
        archive.addfile(item)
        item = tarfile.TarInfo("escape/modified.txt")
        item.size = 3
        archive.addfile(item, io.BytesIO(b"bad"))
    with pytest.raises(ValueError, match="conflicts"):
        extract_rootfs(attack, tmp_path / "quarantined-partial")
    assert list(outside.iterdir()) == []


def test_environment_comes_from_pinned_image_and_selects_public_conda_python():
    value = {
        "os": "linux", "architecture": "amd64",
        "config": {"User": "root", "Env": ["PATH=/usr/bin:/bin", "HOME=/root",
                                           "HTTPS_PROXY=must-not-be-used"]},
    }
    body = json.dumps(value).encode()
    image_id = "sha256:" + hashlib.sha256(body).hexdigest()
    environment = image_environment(
        body, image_id=image_id, public_python="/opt/miniconda3/envs/testbed/bin/python")
    public = environment["environment"]
    assert public["PATH"].startswith("/opt/miniconda3/envs/testbed/bin:")
    assert public["CONDA_PREFIX"] == "/opt/miniconda3/envs/testbed"
    assert public["CONDA_DEFAULT_ENV"] == "testbed"
    assert "HTTPS_PROXY" not in public
    assert "PYTHONPATH" not in public and "LD_LIBRARY_PATH" not in public
    with pytest.raises(ValueError, match="immutable image"):
        image_environment(body, image_id="sha256:" + "0" * 64, public_python="/usr/bin/python")
    value["config"]["User"] = "1000"
    body = json.dumps(value).encode()
    with pytest.raises(ValueError, match="UID mapping"):
        image_environment(body, image_id="sha256:" + hashlib.sha256(body).hexdigest(),
                          public_python="/usr/bin/python")


def test_official_rootfs_requires_identity_and_real_image_uid_qualification(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    manifest = tmp_path / "manifest.json"
    body = json.dumps({
        "version": "v054-native-rootfs-v1", "prepared_root": str(root),
        "image_id": "sha256:" + "1" * 64, "original_image_user": "root",
        "instance_id": "synthetic__repo-1", "base_commit": "2" * 40,
        "numeric_ownership_equivalence_admitted": False, "native_real_task_control_passed": False,
    }).encode()
    manifest.write_bytes(body)
    environment = {
        "kind": "official_image", "rootfs_manifest": str(manifest),
        "rootfs_manifest_sha256": hashlib.sha256(body).hexdigest(),
        "image_id": "sha256:" + "1" * 64, "original_image_user": "root",
    }
    with pytest.raises(ValueError, match="qualification"):
        validate_rootfs(root, environment, preparation_only=False)
    result = validate_rootfs(root, environment, preparation_only=True)
    assert result["official_task_admitted"] is False
    assert result["preparation_only"] is True
    with pytest.raises(ValueError, match="binding"):
        validate_rootfs(tmp_path / "other", environment, preparation_only=True)
    manifest.write_bytes(body + b"\n")
    with pytest.raises(ValueError, match="changed"):
        validate_rootfs(root, environment, preparation_only=True)
