"""Finite CPU round trips for complete v054 candidate artifacts."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from proworksim import software_benchmark_world_v054 as world_api
from proworksim.repository_sources_v054 import (
    RepositorySources,
    capture_repository,
    snapshot_repository,
    tree_manifest,
)
from proworksim.software_benchmark_candidates_v054 import (
    export_git_patch,
    lock_episode_candidates,
    materialize_tree,
    read_episode_candidates,
    select_last_submission,
)


def bundle(snapshot):
    return {key: copy.deepcopy(snapshot[key]) for key in ("files", "entry_metadata")}


def test_patch_preserves_add_delete_modes_binary_links_and_config_without_filters(tmp_path, monkeypatch):
    source = tmp_path / "public"
    source.mkdir()
    (source / "src").mkdir()
    (source / "src/tool.py").write_bytes(b"#!/usr/bin/env python3\r\nprint('old')\r\n")
    (source / "src/tool.py").chmod(0o755)
    (source / "obsolete.py").write_text("remove me\n")
    (source / "pyproject.toml").write_text("[project]\nname='old'\n")
    (source / "data.bin").write_bytes(b"\0\xff\xfeabc\r\n")
    (source / "tool-link").symlink_to("src/tool.py")
    (source / ".gitattributes").write_text("* filter=hostile diff=hostile text eol=lf\n")
    for index in range(230):
        (source / f"file-{index}.txt").write_text(str(index))
    baseline = bundle(snapshot_repository(source))
    target = copy.deepcopy(baseline)
    for old, new in (("src/tool.py", "src/renamed tool.py"), ("data.bin", "renamed.bin")):
        target["files"][new] = target["files"].pop(old)
        target["entry_metadata"][new] = target["entry_metadata"].pop(old)
    target["files"]["tool-link"] = "src/renamed tool.py"
    target["files"]["pyproject.toml"] = "[project]\nname='new'\n"
    target["files"].pop("obsolete.py")
    target["entry_metadata"].pop("obsolete.py")
    for name, text in (("新文件.txt", "末行没有换行"), ("new-empty", ""), ("large.txt", "x" * 40000)):
        target["files"][name] = text
        target["entry_metadata"][name] = {"kind": "file", "encoding": "utf-8", "mode": "100644"}
    # Global filters and repo redirection must not affect raw object encoding.
    marker = tmp_path / "filter-executed"
    hostile = tmp_path / "hostile.gitconfig"
    hostile.write_text(
        '[filter "hostile"]\nclean = touch ' + str(marker)
        + '\n[diff]\nexternal = touch ' + str(marker) + '\n')
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(hostile))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "must-not-be-created"))
    patch = tmp_path / "candidate.patch"
    receipt = export_git_patch(baseline, target, patch)
    assert receipt["round_trip_verified"] is True and not marker.exists()
    assert not (tmp_path / "must-not-be-created").exists()
    assert receipt["added_paths"] == ["large.txt", "new-empty", "renamed.bin", "src/renamed tool.py", "新文件.txt"]
    assert receipt["deleted_paths"] == ["data.bin", "obsolete.py", "src/tool.py"]
    assert receipt["modified_paths"] == ["pyproject.toml", "tool-link"]
    assert b"GIT binary patch" in patch.read_bytes()
    assert b"120000" in patch.read_bytes() and b"100755" in patch.read_bytes()
    output = tmp_path / "materialized"
    materialize_tree(target["files"], target["entry_metadata"], output)
    restored = snapshot_repository(output)
    assert bundle(restored) == target
    assert restored["tree"]["tree_sha256"] == receipt["candidate_tree_sha256"]
    assert (output / "src/renamed tool.py").stat().st_mode & 0o111
    assert (output / "renamed.bin").read_bytes() == b"\0\xff\xfeabc\r\n"
    with pytest.raises(FileExistsError):
        materialize_tree(target["files"], target["entry_metadata"], output)


def test_empty_tree_and_metadata_only_mode_change_are_exact(tmp_path):
    empty = {"files": {}, "entry_metadata": {}}
    before = {"files": {"script": "exit 0\n"}, "entry_metadata": {
        "script": {"kind": "file", "encoding": "utf-8", "mode": "100644"}}}
    executable = copy.deepcopy(before)
    executable["entry_metadata"]["script"]["mode"] = "100755"
    mode = export_git_patch(before, executable, tmp_path / "mode.patch")
    assert mode["modified_paths"] == ["script"] and mode["round_trip_verified"]
    deleted = export_git_patch(executable, empty, tmp_path / "empty.patch")
    assert deleted["deleted_paths"] == ["script"] and deleted["round_trip_verified"]
    unchanged = export_git_patch(empty, empty, tmp_path / "unchanged.patch")
    assert unchanged["patch"]["bytes"] == 0 and unchanged["round_trip_verified"]


def prepare_world(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "old.py").write_text("VALUE = 1\n")
    (source / "old.py").chmod(0o755)
    (source / "obsolete.txt").write_text("delete\n")
    (source / "pyproject.toml").write_text("[project]\nname='before'\n")
    (source / "asset.bin").write_bytes(b"\xff\0fixture\n")
    (source / "alias").symlink_to("old.py")
    identity = {
        "instance_id": "cpu-complete-candidate", "repo": "cpu/fixture",
        "base_commit": "synthetic-baseline", "dataset_revision": "fixture-only",
    }
    manifest = capture_repository(
        source, tmp_path / "source-snapshot", task_id=identity["instance_id"],
        problem_statement="Synthetic file-operation/export control only.",
        source_identity=identity)
    calls = []

    def public_runner(*, files, entry_metadata, task, run_root):
        calls.append(copy.deepcopy(files))
        workspace = tmp_path / ("public-test-" + str(len(calls)))
        materialize_tree(files, entry_metadata, workspace)
        execution = subprocess.run([
            sys.executable, "-c",
            "from pathlib import Path\n"
            "assert Path('new/package.py').read_text() == 'VALUE = 7\\n'\n"
            "assert not Path('obsolete.txt').exists()\n"
            "raise AssertionError('intentional synthetic regression: passing is not required to submit')",
        ], cwd=workspace, capture_output=True, text=True, timeout=10, check=False)
        observed = {
            "executed": True, "command_executed": True, "returncode": execution.returncode,
            "input_tree_sha256": tree_manifest(files, entry_metadata)["tree_sha256"],
            "scope": "real CPU subprocess on synthetic files; no benchmark task",
        }
        group = {"status": "failed", "executed": True, "passed": False,
                 "tests": [], "execution": observed}
        return {"execution": observed, "groups": {"repository_tests": group},
                "tests": [], "passed": False}

    provider = RepositorySources(manifest, runner=public_runner)
    prepared = world_api.build_software_collaboration_case(
        identity["instance_id"], tmp_path / "prepared", provider=provider)
    member = world_api.MEMBERS[0]
    port = world_api.SoftwareCollaborationPort(
        prepared.world.session(member, world_api.PROJECT), member)
    return prepared, port, calls


def call(port, tool, **arguments):
    result = port.call(tool, **arguments)
    assert result["ok"], result
    return result["result"]


@pytest.mark.parametrize("edit_after_submission", [False, True])
def test_real_world_fixed_patch_test_submit_and_dual_candidate_closure(tmp_path, edit_after_submission):
    prepared, port, calls = prepare_world(tmp_path)
    call(port, "create_file", path="new/package.py", text="VALUE = 7\n")
    call(port, "delete_file", path="obsolete.txt")
    call(port, "rename_file", path="old.py", new_path="renamed.py")
    call(port, "rename_file", path="asset.bin", new_path="new/renamed.bin")
    call(port, "rename_file", path="alias", new_path="renamed-alias")
    call(port, "write_file", path="pyproject.toml", text="[project]\nname='after'\n")
    call(port, "run_tests")
    call(port, "fix_patch", task_ids=[], message="Freeze all file operations")
    delivery = call(port, "submit_integration", message="Same-version tested submission")
    submitted = select_last_submission(prepared)
    assert submitted["binding"]["public_test_executed"] is True
    assert len(calls) == 1  # The deliberately failed subprocess still ran.
    if edit_after_submission:
        call(port, "create_file", path="only-terminal.txt", text="Not submitted\n")
        # Corrupt stored evidence only inside this synthetic control. Each
        # refusal must occur before locking, and no test or tool is re-executed.
        world = prepared.world
        original_state = world.store.load()
        try:
            tampered = copy.deepcopy(original_state)
            software = tampered["projects"][world_api.PROJECT]["software"]
            next(iter(software["patches"].values()))["added_paths"].remove("new/package.py")
            world.store.save(tampered)
            with pytest.raises(ValueError, match="Fixed patch omitted"):
                select_last_submission(prepared)
            tampered = copy.deepcopy(original_state)
            test_event = next(event for event in tampered["software_events"] if event["kind"] == "test")
            test_event["source_sha256"] = "0" * 64
            world.store.save(tampered)
            with pytest.raises(ValueError, match="same-version executed public test"):
                select_last_submission(prepared)
        finally:
            world.store.save(original_state)
        assert len(calls) == 1
    lock_ref = lock_episode_candidates(prepared, run_root=tmp_path / "closed")
    result = read_episode_candidates(lock_ref)
    terminal, legal = result["terminal_code"], result["last_legal_delivery"]
    assert legal == submitted["candidate"]
    assert ("only-terminal.txt" in terminal["files"]) is edit_after_submission
    assert "only-terminal.txt" not in legal["files"]
    assert legal["entry_metadata"]["renamed.py"]["mode"] == "100755"
    assert legal["entry_metadata"]["new/renamed.bin"]["encoding"] == "base64"
    assert legal["entry_metadata"]["renamed-alias"]["kind"] == "symlink"
    assert "old.py" not in legal["files"] and "obsolete.txt" not in legal["files"]
    assert legal["files"]["pyproject.toml"] == "[project]\nname='after'\n"
    assert result["lock"]["same_tree"] is not edit_after_submission
    assert result["lock"]["same_candidate_artifacts"] is not edit_after_submission
    last_lock = json.loads(Path(result["lock"]["last_legal_delivery"]["path"]).read_text())
    assert last_lock["source_reference"] == delivery["source_reference"]
    assert len(calls) == 1 and result["lock"]["grading_calls"] == 0
    with pytest.raises(FileExistsError):
        lock_episode_candidates(prepared, run_root=tmp_path / "second-closure")


def test_without_submission_terminal_tree_remains_without_automatic_work(tmp_path):
    prepared, port, calls = prepare_world(tmp_path)
    call(port, "create_file", path="new/package.py", text="VALUE = 7\n")
    # No automatic tests/fix/submit just to obtain a terminal-code candidate.
    ref = lock_episode_candidates(prepared, run_root=tmp_path / "closed")
    result = read_episode_candidates(ref)
    assert result["last_legal_delivery"] is None and result["lock"]["submitted"] is False
    assert result["terminal_code"]["files"]["new/package.py"] == "VALUE = 7\n"
    assert calls == []
