"""Critical candidate/oracle boundaries without a daemon or model."""
import io
from pathlib import Path
import subprocess
import tarfile
from types import SimpleNamespace

import pytest

from proworksim import software_panel_docker_v053 as docker


def tar_bytes(entries):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, content in entries:
            info = tarfile.TarInfo(name)
            if isinstance(content, tuple):
                info.type, info.linkname = tarfile.SYMTYPE, content[0]
                archive.addfile(info)
            else:
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def test_snapshot_excludes_gold_history_and_cache_and_is_order_independent():
    entries = [
        ("testbed/src/main.py", b"buggy\n"),
        ("testbed/.git/objects/gold", b"correct secret source"),
        ("testbed/src/__pycache__/main.pyc", b"cached correct source"),
        ("testbed/src/link.py", ("main.py",)),
    ]
    first, records = docker.normalize_archive([tar_bytes(entries)])
    second, second_records = docker.normalize_archive([tar_bytes(list(reversed(entries)))])
    assert first == second and records == second_records
    assert [row["path"] for row in records] == ["src/link.py", "src/main.py"]


@pytest.mark.parametrize("entries", [
    [("testbed/../../host", b"bad")],
    [("testbed/symlink", ("/host/secret",))],
    [("testbed/symlink", ("../../host",))],
    [("testbed/link", ("directory",)), ("testbed/link/child", b"bad")],
    [("testbed/duplicate", b"a"), ("testbed/duplicate", b"b")],
])
def test_snapshot_rejects_path_traversal_links_and_duplicate_members(entries):
    with pytest.raises(ValueError):
        docker.normalize_archive([tar_bytes(entries)])


def test_admission_requires_observed_clean_bug_and_gold_test_transitions():
    task = {"FAIL_TO_PASS": ["test_fix"], "PASS_TO_PASS": ["test_keep"]}
    passed = {"technical_error": None,
              "test_status_map": {"test_fix": "PASSED", "test_keep": "PASSED"}}
    buggy = {"technical_error": None,
             "test_status_map": {"test_fix": "FAILED", "test_keep": "PASSED"}}
    assert docker.admission_verdict(task, passed, buggy, passed) == (True, None)
    missing = {"technical_error": None, "test_status_map": {"test_keep": "PASSED"}}
    admitted, reason = docker.admission_verdict(task, passed, missing, passed)
    assert admitted is False and "transition_mismatch" in reason
    unknown = {"technical_error": "official_test_timeout", "test_status_map": {}}
    admitted, reason = docker.admission_verdict(task, passed, buggy, unknown)
    assert admitted is False and "gold:official_test_timeout" in reason


def test_test_protection_includes_new_collection_hooks_and_explicit_oracle():
    profile = SimpleNamespace(_is_test_path=lambda root, file: "tests" in root.split("/"))
    assert docker.protected_path("new/conftest.py", profile)
    assert docker.protected_path("tests/changed.py", profile)
    assert docker.protected_path("odd_spec.py", profile, ["odd_spec.py"])
    assert not docker.protected_path("src/implementation.py", profile)


def test_lock_cannot_be_overwritten_or_read_after_tampering(tmp_path):
    path = tmp_path / "lock.json"
    reference = docker.write_new(path, {"source": "first"})
    assert docker.checked(reference) == path
    with pytest.raises(FileExistsError):
        docker.write_new(path, {"source": "second"})
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="evidence changed"):
        docker.checked(reference)


def test_default_daemon_is_never_implicitly_accepted(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "docker", SimpleNamespace())
    with pytest.raises(ValueError, match="dedicated"):
        docker.docker_client({"docker_host": "unix:///var/run/docker.sock"})


def test_strict_completion_does_not_drop_skipped_xpass_or_missing_required_tests():
    task = {"FAIL_TO_PASS": ["fix"], "PASS_TO_PASS": ["keep"]}
    assert docker.strict_completion(task, {"fix": "PASSED", "keep": "XFAIL"})["R_code"] == 1
    for status in ("SKIPPED", "XPASS", "FAILED", "ERROR", None):
        statuses = {"keep": "PASSED"}
        if status is not None:
            statuses["fix"] = status
        report = docker.strict_completion(task, statuses)
        assert report["R_code"] == 0
        assert report["required_not_passed"] == [{"test": "fix", "status": status or "MISSING"}]
    assert docker.strict_completion(task, {}, technical_error="timeout")["R_code"] is None


@pytest.mark.parametrize("error_type,expected", [
    (docker.CommonSystemFault, "unresolved_common_system_fault"),
    (docker.SourceEnvironmentError, "source_not_admitted"),
])
def test_common_fault_pauses_without_rejecting_a_source(tmp_path, monkeypatch, error_type, expected):
    repository = {
        "profile_slug": "owner__repo.12345678", "repository": "owner/repo",
        "image_name": "pinned/image",
        "candidate_task_ids": [f"task-{i}" for i in range(10)],
    }
    monkeypatch.setattr(docker, "docker_client", lambda config: SimpleNamespace(close=lambda: None))

    def fail(*args, **kwargs):
        raise error_type("registry transport unavailable" if error_type is docker.CommonSystemFault
                         else "manifest explicitly not found")

    monkeypatch.setattr(docker, "image_identity", fail)
    report = docker.qualify_repository({"environment_root": str(tmp_path)}, repository)
    assert report["status"] == expected
    final = tmp_path / "repositories/owner__repo.12345678/qualification.json"
    if error_type is docker.CommonSystemFault:
        assert report["admitted"] is None and not final.exists()
        assert docker.checked(report["fault_receipt"]).is_file()
    else:
        assert report["admitted"] is False and final.exists()


def test_actor_cleanup_preserves_init_and_trusted_processes_and_handles_pid_reuse():
    compile(docker.ACTOR_SUPERVISOR, "<actor-supervisor>", "exec")
    baseline = {"1": {"starttime": "100"}, "7": {"starttime": "110"},
                "9": {"starttime": "120"}}
    current = {
        "1": {"starttime": "100", "state": "S"},
        "7": {"starttime": "110", "state": "S"},
        "9": {"starttime": "999", "state": "S"},
        "13": {"starttime": "130", "state": "S"},
        "14": {"starttime": "140", "state": "Z"},
        "20": {"starttime": "150", "state": "R"},
    }
    assert docker.process_targets(current, baseline, own_pid=20) == {"9": "999", "13": "130"}


def test_mirror_baseline_separates_upstream_and_preserves_installation_changes(monkeypatch):
    commit, tree, upstream = "a" * 40, "b" * 40, "c" * 40
    container = SimpleNamespace(image=SimpleNamespace(id="sha256:" + "d" * 64))
    task = {"repo": "swesmith/owner__repo.12345678", "instance_id": "task"}
    contract = {"upstream_source_commit": upstream}
    answers = {
        "git symbolic-ref --quiet HEAD": "refs/heads/main\n",
        "git rev-parse HEAD HEAD^{tree} refs/heads/main refs/remotes/origin/main":
            "\n".join([commit, tree, commit, commit]) + "\n",
        "git remote get-url origin": "https://github.com/" + task["repo"],
        "git status --porcelain=v1 --untracked-files=normal": "",
        "git diff --binary " + tree + " " + tree: "",
    }
    monkeypatch.setattr(docker, "require_exec", lambda _, command: answers[command])
    monkeypatch.setattr(docker, "indexed_tree", lambda *args: tree)
    baseline = docker.identify_image_baseline(container, task, contract)
    assert baseline["image_base_commit"] == commit != upstream
    assert baseline["image_base_tree"] == tree
    assert baseline["upstream_source_commit"] == upstream
    answers["git symbolic-ref --quiet HEAD"] = "refs/heads/master"
    with pytest.raises(docker.CommonSystemFault, match="unresolved"):
        docker.identify_image_baseline(container, task, contract)
    answers["git symbolic-ref --quiet HEAD"] = "refs/heads/main"
    answers["git status --porcelain=v1 --untracked-files=normal"] = " D tests/test_focal_loss.py\n"
    installed = "e" * 40
    monkeypatch.setattr(docker, "indexed_tree", lambda *args: installed)
    answers["git diff --binary " + tree + " " + installed] = "installation deletion\n"
    baseline = docker.identify_image_baseline(container, task, contract)
    assert baseline["image_worktree_tree"] == installed
    assert baseline["tracked_and_nonignored_worktree_clean"] is False
    assert baseline["image_worktree_status"].startswith(" D ")
    monkeypatch.setattr(docker, "exec_in", lambda *args: {"returncode": 1, "exception_info": None})
    assert docker.official_task_trees(container, task, baseline)["available_in_frozen_image"] is False


def test_initialization_error_defaults_to_common_fault_and_patch_evidence_is_explicit(monkeypatch):
    result = {"returncode": 128, "exception_info": None, "output": "could not parse object"}
    monkeypatch.setattr(docker, "exec_in", lambda *args: result)
    with pytest.raises(docker.CommonSystemFault):
        docker.require_exec(None, "git init")
    with pytest.raises(docker.SourceEnvironmentError):
        docker.require_exec(None, "git apply --check patch.diff", source_failure=True)
    result["exception_info"] = "daemon disconnected"
    with pytest.raises(docker.CommonSystemFault):
        docker.require_exec(None, "git apply --check patch.diff", source_failure=True)


def test_installation_deleted_test_remains_deleted_in_projected_bug_and_actor(tmp_path, monkeypatch):
    monkeypatch.setenv("LC_ALL", "C")
    def command(_, text, *args):
        result = subprocess.run(["bash", "-c", text], cwd=tmp_path, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return result.stdout

    monkeypatch.setattr(docker, "require_exec", command)
    monkeypatch.setattr(docker, "put_bytes", lambda _, path, value: Path(path).write_bytes(value))

    def execute(_, text, timeout, *, separate_output=False):
        result = subprocess.run(["bash", "-c", text], cwd=tmp_path, capture_output=True, text=True)
        return {"returncode": result.returncode, "output": result.stdout + result.stderr,
                "exception_info": None, "stdout": result.stdout, "stderr": result.stderr}

    monkeypatch.setattr(docker, "exec_in", execute)
    command(None, "git init -q && git config user.email test@localhost && git config user.name Test")
    (tmp_path / "source.py").write_text("correct\n")
    (tmp_path / "hidden_test.py").write_text("test fix\n")
    (tmp_path / "installed_deleted_test.py").write_text("test installation dependency\n")
    command(None, "git add -A && git commit -qm Initial")
    original = command(None, "git rev-parse HEAD^{tree}").strip()
    (tmp_path / "source.py").write_text("bug\n")
    bug = docker.indexed_tree(None, original, "git add -A")
    actor = docker.indexed_tree(None, bug, "git update-index --force-remove -- hidden_test.py")
    (tmp_path / "source.py").write_text("correct\n")
    (tmp_path / "installed_deleted_test.py").unlink()
    installed = docker.indexed_tree(None, original, "git add -A")
    delta = command(None, "git diff --binary " + original + " " + installed)
    baseline = {"image_base_tree": original, "image_worktree_tree": installed,
                "installation_delta_sha256": docker.sha256(delta.encode())}
    branch = {"available_in_frozen_image": True, "bug_tree": bug, "actor_tree": actor}
    projected = docker.projected_task_trees(None, branch, baseline, ["hidden_test.py"])
    assert projected["comparison_available"] is True
    for tree in (projected["projected_bug_tree"], projected["projected_actor_tree"]):
        assert "installed_deleted_test.py" not in command(None, "git ls-tree --name-only " + tree)
        assert command(None, "git show " + tree + ":source.py") == "bug\n"
    assert "hidden_test.py" not in command(None, "git ls-tree --name-only " + projected["projected_actor_tree"])
    assert not (tmp_path / "installed_deleted_test.py").exists()
    assert (tmp_path / "source.py").read_text() == "correct\n"


def test_source_cleanup_removes_old_answers_without_deleting_dependency_cache(tmp_path):
    source = tmp_path / "testbed"
    source.mkdir()
    preserved = {
        source / "module.py": b"current buggy source\n",
        tmp_path / "root/.cache/uv/wheels-v5/pypi/hatchling/build.whl": b"official dependency\n",
        tmp_path / "root/.cache/uv/archive-v0/project/_pydantic.pth": b"/testbed\n",
    }
    removed = [
        source / ".git/objects/old-correct-source",
        source / "__pycache__/module.cpython-310.pyc",
        source / "legacy.pyo",
        source / ".pytest_cache/v/cache/nodeids",
    ]
    for path, value in preserved.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    for path in removed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old artifact")
    result = subprocess.run(
        ["bash", "-c", "set -euo pipefail\n" + docker.SOURCE_HISTORY_CACHE_CLEANUP],
        cwd=source, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert all(not path.exists() for path in removed)
    assert all(path.read_bytes() == value for path, value in preserved.items())


def test_planned_local_image_wait_loads_or_stops_without_duplicate_pull(monkeypatch):
    class APIError(Exception):
        status_code = 404

    class ImageNotFound(APIError):
        pass

    monkeypatch.setitem(__import__("sys").modules, "docker", SimpleNamespace(
        errors=SimpleNamespace(APIError=APIError, ImageNotFound=ImageNotFound)))
    image = SimpleNamespace(id="sha256:original", attrs={"Architecture": "amd64", "Os": "linux"})
    clock = [0]
    calls = {"get": 0, "pull": 0}

    class Stop:
        stopped = False
        stop_during_wait = False

        def is_set(self):
            return self.stopped

        def wait(self, seconds):
            clock[0] += seconds
            self.stopped = self.stop_during_wait
            return self.stopped

    stop = Stop()
    monkeypatch.setattr(docker.time, "monotonic", lambda: clock[0])
    available_after = [2]

    def get(name):
        calls["get"] += 1
        if calls["get"] >= available_after[0]:
            return image
        raise ImageNotFound(name)

    def pull(name):
        calls["pull"] += 1
        return image

    client = SimpleNamespace(images=SimpleNamespace(get=get, pull=pull))
    settings = {"allow_pull": True, "local_image_wait_seconds": 30,
                "local_image_wait_names": ["official/image"], "stop_event": stop}
    assert docker.image_identity(client, "official/image", **settings)["image_id"] == image.id
    assert calls == {"get": 2, "pull": 0}
    calls["get"], clock[0], available_after[0] = 0, 0, 1000
    with pytest.raises(docker.CommonSystemFault, match="Timed out waiting"):
        docker.image_identity(client, "official/image", **settings)
    assert clock[0] == 30 and calls["pull"] == 0
    calls["get"], clock[0], stop.stop_during_wait = 0, 0, True
    with pytest.raises(docker.CommonSystemFault, match="preparation stopped"):
        docker.image_identity(client, "official/image", **settings)
    assert calls["get"] == 1 and calls["pull"] == 0
    stop.stopped = False
    assert docker.image_identity(client, "another/image", **settings)["image_id"] == image.id
    assert calls["pull"] == 1


def test_projection_keeps_real_git_whitespace_warnings_out_of_tree_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("LC_ALL", "C")

    class LocalContainer:
        def exec_run(self, command, *, workdir, user, demux):
            result = subprocess.run(command, cwd=tmp_path, capture_output=True)
            return SimpleNamespace(
                exit_code=result.returncode,
                output=(result.stdout, result.stderr) if demux else result.stdout + result.stderr)

    container = LocalContainer()
    monkeypatch.setattr(docker, "put_bytes", lambda _, path, value: Path(path).write_bytes(value))

    def command(text):
        return docker.require_exec(container, text)

    command("git init -q && git config user.email test@localhost && git config user.name Test"
            " && git config apply.whitespace warn")
    (tmp_path / "source.py").write_text("correct\n")
    (tmp_path / "hidden_test.py").write_text("test fix\n")
    metadata = tmp_path / "installation_metadata.txt"
    metadata.write_text("original\n")
    command("git add -A && git commit -qm Initial")
    original = command("git rev-parse HEAD^{tree}").strip()
    (tmp_path / "source.py").write_text("bug\n")
    bug = docker.indexed_tree(container, original, "git add -A")
    actor = docker.indexed_tree(
        container, bug, "git update-index --force-remove -- hidden_test.py")
    (tmp_path / "source.py").write_text("correct\n")
    metadata.write_text("installed with trailing whitespace \n\n")
    installed = docker.indexed_tree(container, original, "git add -A")
    delta = command("git diff --binary " + original + " " + installed)
    projected = docker.projected_task_trees(
        container, {"available_in_frozen_image": True, "bug_tree": bug, "actor_tree": actor},
        {"image_base_tree": original, "image_worktree_tree": installed,
         "installation_delta_sha256": docker.sha256(delta.encode())},
        ["hidden_test.py"])
    assert "trailing whitespace" in projected["projection_stderr"]
    tree = projected["projected_bug_tree"]
    assert len(tree) == 40 and all(letter in "0123456789abcdef" for letter in tree)
    assert command("git show " + tree + ":source.py") == "bug\n"
    assert command("git show " + tree + ":installation_metadata.txt") == metadata.read_text()
    assert "hidden_test.py" not in command(
        "git ls-tree --name-only " + projected["projected_actor_tree"])
    assert (tmp_path / "source.py").read_text() == "correct\n"
