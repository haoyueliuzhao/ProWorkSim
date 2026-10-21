import subprocess
import json
import shutil
import sys

from proworksim.repository_sources_v054 import snapshot_repository
from proworksim.software_benchmark_candidates_v054 import export_git_patch
from proworksim.software_benchmark_candidates_v054 import materialize_tree
from proworksim.software_benchmark_gitlinks_v054 import NESTED_GIT_CONTROL


def test_complete_submodule_worktree_patch_applies_without_changing_gitlink(tmp_path):
    root = tmp_path / "parent"
    child = root / "helpers"
    child.mkdir(parents=True)
    (root / "main.py").write_text("answer = 1\n")
    (root / ".gitmodules").write_text('[submodule "helpers"]\n\tpath = helpers\n\turl = https://example.invalid/helpers\n')
    (child / "helper.py").write_text("value = 2\n")
    (child / "old.txt").write_text("remove this\n")

    def git(path, *args):
        result = subprocess.run(
            ["git", "-c", "user.name=Control", "-c", "user.email=control@example.invalid",
             "-C", str(path), *args], check=True, capture_output=True)
        return result.stdout.decode().strip()

    git(child, "init", "--quiet")
    git(child, "add", ".")
    git(child, "commit", "--quiet", "-m", "public submodule baseline")
    oid = git(child, "rev-parse", "HEAD")
    git(root, "init", "--quiet")
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "parent baseline")
    initial_index = git(root, "ls-files", "--stage", "helpers")
    baseline = snapshot_repository(root)
    assert baseline["gitlinks"] == [{"path": "helpers", "oid": oid}]
    assert "helpers/helper.py" in baseline["files"]
    assert not any(".git" in path.split("/") for path in baseline["files"])
    (root / "main.py").write_text("answer = 3\n")
    (child / "helper.py").write_text("value = 7\n")
    (child / "helper.py").chmod(0o755)
    (child / "old.txt").unlink()
    (child / "payload.bin").write_bytes(b"\0\xffpublic-control\0")
    candidate = snapshot_repository(root, gitlinks=baseline["gitlinks"])
    patch = tmp_path / "candidate.patch"
    receipt = export_git_patch(baseline, candidate, patch)
    assert receipt["gitlink_oids_preserved"] is True
    assert receipt["parent_git_tree_claimed"] is False
    assert "base_git_tree" not in receipt
    assert receipt["submodule_changed_paths"] == [
        "helpers/helper.py", "helpers/old.txt", "helpers/payload.bin"]
    git(root, "reset", "--hard", "HEAD")
    git(child, "reset", "--hard", "HEAD")
    git(child, "clean", "-fd")
    # The official scorer uses working-tree git apply, without --index.
    git(root, "apply", "--binary", str(patch))
    applied = snapshot_repository(root, gitlinks=baseline["gitlinks"])
    assert applied["tree"] == candidate["tree"]
    assert git(root, "ls-files", "--stage", "helpers") == initial_index
    # PROJECT replaces the complete public payload, preserving only admitted
    # control metadata so Git-derived setup behavior is not lost in its tests.
    staging = subprocess.run(
        [sys.executable, "-I", "-c", NESTED_GIT_CONTROL, "stage", str(root),
         json.dumps(["helpers"])], check=True, capture_output=True, text=True).stdout.strip()
    for item in root.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    payload = tmp_path / "public-payload"
    materialize_tree(candidate["files"], candidate["entry_metadata"], payload)
    shutil.copytree(payload, root, dirs_exist_ok=True)
    subprocess.run([sys.executable, "-I", "-c", NESTED_GIT_CONTROL, "restore", str(root), staging],
                   check=True, capture_output=True)
    assert git(child, "rev-parse", "HEAD") == oid
    assert snapshot_repository(root, gitlinks=baseline["gitlinks"])["tree"] == candidate["tree"]
