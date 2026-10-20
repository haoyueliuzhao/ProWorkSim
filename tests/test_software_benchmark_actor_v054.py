"""Synthetic transport/boundary controls; no Docker or benchmark tests."""
import copy
import io
import json
from pathlib import Path
import subprocess
import tarfile

import pytest

from proworksim.repository_sources_v054 import RepositorySourceError
from proworksim.software_benchmark_actor_v054 import (
    ActorDocker, admission, bundle_from_archive, prepare_public_source, project_provider,
)


def fixture_archive():
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name, data, mode in (
            (".git/objects/not-for-provider", b"metadata", 0o644),
            ("entry.py", b"print('public')\r\n", 0o755),
            ("asset.bin", b"\xff\0\x01", 0o644),
            ("obsolete.txt", b"old", 0o644),
        ):
            entry = tarfile.TarInfo("testbed/" + name)
            entry.size, entry.mode = len(data), mode
            archive.addfile(entry, io.BytesIO(data))
        entry = tarfile.TarInfo("testbed/alias")
        entry.type, entry.linkname = tarfile.SYMTYPE, "entry.py"
        archive.addfile(entry)
    return output.getvalue()


def fixture_environment():
    task = {
        "instance_id": "synthetic__public-1", "repo": "synthetic/public",
        "base_commit": "a" * 40, "image": "fixture/public:latest",
        "problem_statement": "Synthetic public file transport only.",
    }
    image = {
        "instance_id": task["instance_id"], "base_commit": task["base_commit"],
        "image_name": "fixture/public", "tag": "latest", "status": "loaded",
        "image_id": "sha256:" + "b" * 64, "config_digest": "sha256:" + "b" * 64,
        "manifest_digest": "sha256:" + "c" * 64,
        "platform": {"os": "linux", "architecture": "amd64"},
    }
    preflight = {
        "image_id": image["image_id"], "base_commit": task["base_commit"],
        "status": "bounded_preflight_passed", "network": "none", "read_only": True,
        "details": {
            "head_matches_base": True, "working_tree_clean": True,
            "future_reachable_commit_count": 0, "future_reflog_commit_count": 0,
            "unreachable_nonancestor_commit_count": 0, "git_connectivity_fsck_returncode": 0,
            "target_package_copy_paths": [], "public_python": "/opt/testbed/bin/python",
        },
    }
    limits = {
        "cpus": 4, "memory_bytes": 16 * 1024**3, "pids_limit": 16384,
        "public_test_timeout_seconds": 1800, "network": "none",
    }
    return task, image, preflight, limits


def test_public_projection_and_known_answer_copies_are_hard_admission_gates():
    task, image, preflight, limits = fixture_environment()
    environment = admission(task, image, preflight, limits=limits)
    assert environment["host_mounts"] == []
    with pytest.raises(ValueError, match="projection"):
        admission({**task, "eval_script": "hidden"}, image, preflight, limits=limits)
    changed = copy.deepcopy(preflight)
    changed["details"]["target_package_copy_paths"] = ["/opt/conda/pkgs/future-source"]
    with pytest.raises(ValueError, match="Target-package"):
        admission(task, image, changed, limits=limits)
    changed = copy.deepcopy(preflight)
    changed["details"]["future_reflog_commit_count"] = 1
    with pytest.raises(ValueError, match="Git-history"):
        admission(task, image, changed, limits=limits)


def test_complete_tar_decode_rejects_escape_and_preserves_binary_mode_and_links():
    bundle = bundle_from_archive(io.BytesIO(fixture_archive()))
    assert set(bundle["files"]) == {"entry.py", "asset.bin", "obsolete.txt", "alias"}
    assert bundle["files"]["entry.py"].endswith("\r\n")
    assert bundle["entry_metadata"]["entry.py"]["mode"] == "100755"
    assert bundle["entry_metadata"]["asset.bin"]["encoding"] == "base64"
    assert bundle["entry_metadata"]["alias"]["kind"] == "symlink"
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        item = tarfile.TarInfo("testbed/escape")
        item.type, item.linkname = tarfile.SYMTYPE, "../../outside"
        archive.addfile(item)
    with pytest.raises(RepositorySourceError, match="escapes"):
        bundle_from_archive(io.BytesIO(output.getvalue()))
    with pytest.raises(ValueError, match="deployment limit"):
        bundle_from_archive(io.BytesIO(fixture_archive()), file_policy={"max_file_bytes": 2})


def test_public_source_provider_and_candidate_public_test_transport(tmp_path):
    task, image, preflight, limits = fixture_environment()
    environment = admission(task, image, preflight, limits=limits)

    class SyntheticDocker(ActorDocker):
        def __init__(self):
            super().__init__("unix:///synthetic/private/docker.sock")
            self.commands, self.payloads = [], []

        def run(self, *args, input=None, **kwargs):
            self.commands.append(args)
            if args[:2] == ("image", "inspect"):
                stdout = json.dumps([{"Id": image["image_id"], "Os": "linux",
                                      "Architecture": "amd64"}]).encode()
            elif args[0] == "create":
                stdout = b"synthetic-container"
            else:
                stdout = b"public synthetic result"
            if input is not None:
                self.payloads.append(input)
            return subprocess.CompletedProcess(args, 0, stdout, b"")

        def public_archive(self, container, destination):
            Path(destination).write_bytes(fixture_archive())

    controller = SyntheticDocker()
    source = prepare_public_source(environment, controller, tmp_path / "source")
    source_sha = __import__("hashlib").sha256(Path(source).read_bytes()).hexdigest()
    entry = {
        "source": "public_repository", "admitted": True, "cwd": "/testbed",
        "argv": [environment["public_python"], "-m", "pytest", "-q"],
        "source_manifest_sha256": source_sha,
    }
    provider = project_provider(source, environment, controller, entry)
    case = provider.build_case(task["instance_id"])
    files, metadata = case["files"], case["entry_metadata"]
    files.pop("obsolete.txt")
    metadata.pop("obsolete.txt")
    files["new/config.txt"] = "public new file"
    metadata["new/config.txt"] = {"kind": "file", "encoding": "utf-8", "mode": "100644"}
    result = provider.run_public_tests(
        task["instance_id"], files, entry_metadata=metadata, run_root=tmp_path / "public-test")
    assert result["execution"]["hidden_grader_called"] is False
    assert result["execution"]["executed"] is True
    assert result["output"].startswith("public synthetic result")
    with tarfile.open(fileobj=io.BytesIO(controller.payloads[0])) as archive:
        assert set(archive.getnames()) == {"entry.py", "asset.bin", "alias", "new/config.txt"}
    creates = [command for command in controller.commands if command[0] == "create"]
    for command in creates:
        assert "--pull" in command and command[command.index("--pull") + 1] == "never"
        assert "--network" in command and command[command.index("--network") + 1] == "none"
        assert "--mount" not in command and "--volume" not in command and "--gpus" not in command
        assert image["image_id"] in command
    assert any(command[-4:] == tuple(entry["argv"]) for command in controller.commands)
