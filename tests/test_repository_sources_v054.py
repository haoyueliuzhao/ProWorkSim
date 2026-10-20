import copy
import json
import os

import pytest

from proworksim.repository_sources_v054 import (
    RepositorySourceError, RepositorySources, capture_repository, decode_entry,
    snapshot_repository, tree_manifest, validate_tree,
)


IDENTITY = {"instance_id": "fixture__repo-1", "repo": "fixture/repo",
            "base_commit": "1" * 40, "dataset_revision": "2" * 40}
TEXT = {"kind": "file", "encoding": "utf-8", "mode": "100644"}
LINK = {"kind": "symlink", "encoding": "symlink-target", "mode": "120000"}


def capture(tmp_path, *, policy=None, runner=None):
    root = tmp_path / "public"
    root.mkdir()
    (root / "ordinary.py").write_text("value = 1\n")
    path = capture_repository(root, tmp_path / "snapshot", task_id=IDENTITY["instance_id"],
                              problem_statement="Fix the public issue.", source_identity=IDENTITY,
                              file_policy=policy)
    return RepositorySources(path, runner=runner), path


def test_complete_tree_exceeds_old_limits_without_type_mode_or_content_loss(tmp_path):
    root = tmp_path / "public"
    root.mkdir()
    for index in range(205):
        (root / f"module_{index:03}.py").write_text(f"index = {index}\n")
    large = "# full source\n" + "x" * 3_000_000
    (root / "large.py").write_text(large)
    (root / ".hidden-public-config").write_bytes(b"public=true\r\n")
    (root / "asset.bin").write_bytes(b"\xff\0binary\r\n")
    (root / "entry.sh").write_bytes(b"#!/bin/sh\nexit 0\n")
    os.chmod(root / "entry.sh", 0o755)
    (root / "alias").symlink_to("ordinary-does-not-exist")
    (root / ".git").mkdir()
    (root / ".git" / "future-private-history").write_text("excluded Git control metadata")
    manifest = capture_repository(root, tmp_path / "snapshot", task_id=IDENTITY["instance_id"],
                                  problem_statement="Fixture problem.", source_identity=IDENTITY)
    provider = RepositorySources(manifest)
    case = provider.build_case(IDENTITY["instance_id"])
    assert len(case["files"]) == 210
    assert case["files"]["large.py"] == large
    assert decode_entry("asset.bin", case["files"]["asset.bin"],
                        case["entry_metadata"]["asset.bin"]) == b"\xff\0binary\r\n"
    assert case["files"][".hidden-public-config"] == "public=true\r\n"
    assert case["entry_metadata"]["entry.sh"]["mode"] == "100755"
    assert case["entry_metadata"]["alias"] == LINK
    assert ".git/future-private-history" not in case["files"]
    assert "large.py" not in json.dumps(case["source_contract"])
    assert large not in json.dumps(case["initial_binding"])
    assert case["file_policy"]["max_files"] is None
    assert case["initial_binding"]["initial_tree_sha256"] == tree_manifest(
        case["files"], case["entry_metadata"])["tree_sha256"]


def test_mutation_validation_allows_changes_and_preserves_readonly_bytes_and_mode(tmp_path):
    provider, _ = capture(tmp_path, policy={"readonly_prefixes": ["reserved/"]})
    case = provider.build_case(IDENTITY["instance_id"])
    files, metadata = case["files"], case["entry_metadata"]
    files["renamed.py"] = files.pop("ordinary.py")
    metadata["renamed.py"] = metadata.pop("ordinary.py")
    files["new/config.toml"], metadata["new/config.toml"] = "enabled=true\n", dict(TEXT)
    provider.validate_files(IDENTITY["instance_id"], files, entry_metadata=metadata)
    files["reserved/test.py"], metadata["reserved/test.py"] = "hidden = 0\n", dict(TEXT)
    with pytest.raises(RepositorySourceError) as error:
        provider.validate_files(IDENTITY["instance_id"], files, entry_metadata=metadata)
    assert error.value.category == "policy_error"
    del files["reserved/test.py"], metadata["reserved/test.py"]
    del files["renamed.py"], metadata["renamed.py"]
    provider.validate_files(IDENTITY["instance_id"], files, entry_metadata=metadata)
    with pytest.raises(RepositorySourceError, match="entry_metadata"):
        provider.validate_files(IDENTITY["instance_id"], files)


def test_deployment_ceiling_rejects_whole_snapshot_and_is_configurable(tmp_path):
    root = tmp_path / "public"
    root.mkdir()
    (root / "full.py").write_bytes(b"x" * 100)
    output = tmp_path / "snapshot"
    with pytest.raises(RepositorySourceError) as error:
        capture_repository(root, output, task_id=IDENTITY["instance_id"],
                           problem_statement="Fixture", source_identity=IDENTITY,
                           file_policy={"max_file_bytes": 99})
    assert error.value.category == "deployment_limit"
    assert error.value.code == "max_file_bytes_exceeded"
    assert not output.exists()
    snapshot = snapshot_repository(root, file_policy={"max_file_bytes": None, "max_source_bytes": None})
    assert snapshot["files"] == {"full.py": "x" * 100}
    assert snapshot["truncated"] is False
    with pytest.raises(RepositorySourceError) as error:
        validate_tree({"a": "a", "b": "b"}, {"a": TEXT, "b": TEXT}, {"max_files": 1})
    assert error.value.category == "deployment_limit"


def test_tampered_snapshot_and_symlink_chain_escape_are_rejected(tmp_path):
    _, manifest = capture(tmp_path)
    tree_path = manifest.parent / "initial-tree.json"
    value = json.loads(tree_path.read_bytes())
    value["files"]["ordinary.py"] = "changed"
    tree_path.write_text(json.dumps(value))
    with pytest.raises(RepositorySourceError, match="snapshot changed"):
        RepositorySources(manifest)
    for files, metadata in [
        ({"outside": "../outside"}, {"outside": LINK}),
        ({"a": ".", "x": "a/.."}, {"a": LINK, "x": LINK}),
        ({"a": "dir", "a/file": "text"}, {"a": LINK, "a/file": TEXT}),
    ]:
        with pytest.raises(RepositorySourceError):
            validate_tree(files, metadata)
    validate_tree({"dir/link": "../okay", "okay": "text"}, {"dir/link": LINK, "okay": TEXT})


def test_public_runner_receipt_binds_complete_tree_without_judge_material(tmp_path):
    calls = []

    def runner(**kwargs):
        calls.append(copy.deepcopy(kwargs))
        return {"execution": {"executed": False, "input_tree_sha256": tree_manifest(
            kwargs["files"], kwargs["entry_metadata"])["tree_sha256"]},
            "groups": {}, "tests": [], "passed": False}

    provider, _ = capture(tmp_path, runner=runner)
    case = provider.build_case(IDENTITY["instance_id"])
    result = provider.run_public_tests(IDENTITY["instance_id"], case["files"],
        entry_metadata=case["entry_metadata"], run_root=tmp_path / "public-tests")
    assert result["execution"]["executed"] is False
    assert len(calls) == 1
    assert not {"patch", "test_patch", "FAIL_TO_PASS", "PASS_TO_PASS", "eval_script"} & calls[0]["task"].keys()
    provider.runner = lambda **kwargs: {"execution": {"input_tree_sha256": "wrong"}}
    with pytest.raises(RepositorySourceError, match="complete candidate tree"):
        provider.run_public_tests(IDENTITY["instance_id"], case["files"],
            entry_metadata=case["entry_metadata"], run_root=tmp_path / "other-public-tests")


def test_manifest_ingestion_refuses_extra_hidden_fields_in_public_identity(tmp_path):
    _, manifest_path = capture(tmp_path)
    manifest = json.loads(manifest_path.read_bytes())
    manifest["tasks"][0]["source_identity"]["test_patch"] = "synthetic prohibited field"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(RepositorySourceError, match="Only public"):
        RepositorySources(manifest_path)
