"""Critical candidate/oracle boundaries without a daemon or model."""
import io
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
