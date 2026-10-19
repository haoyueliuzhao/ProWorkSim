"""Finite synthetic server controls; no historical tasks, models, or GPU use."""

import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess

import pytest

from proworksim import software_calibration_repo_tests_v051 as repository
from proworksim import software_calibration_shell_v051 as shell
from proworksim import software_holdout_repo_tests_v051 as holdout
from proworksim import software_sandbox
from proworksim import server_namespace_sandbox as namespace


ROOT = Path(__file__).resolve().parents[1]
CPU_PYTHON = ROOT / "artifacts/software-calibration-v051/cal2-sources/cal2/cpu-venv/bin/python"
HOLD_PYTHON = ROOT / "runs/v051-hold-cpu-venv/bin/python"
FILES = {
    "migration_candidate.py": "def answer():\n    return 42\n",
    "test_migration.py": (
        "from migration_candidate import answer\n\n"
        "def test_answer():\n    assert answer() == 42\n"
    ),
}
NODE = "test_migration.py::test_answer"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def test_shell_and_repository_synthetic_pytest_entries(tmp_path):
    assert CPU_PYTHON.exists(), "Run inside the prepared private CPU runtime."
    worktree = tmp_path / "shell-worktree"
    worktree.mkdir()
    for name, content in FILES.items():
        (worktree / name).write_text(content)
    (worktree / "pytest.ini").write_text("[pytest]\n")
    command = shlex.join([str(CPU_PYTHON), "-m", "pytest", "-q", "-p", "no:cacheprovider",
                          "--rootdir", str(worktree), "-c", "pytest.ini", NODE])
    observed = shell.run_bounded_shell(
        command, worktree=worktree, python_executable=CPU_PYTHON,
        python_prefix=CPU_PYTHON.parent.parent, evidence_root=tmp_path / "shell-evidence",
    )
    assert observed["returncode"] == 0, observed
    assert "1 passed" in observed["output"]
    task = {"nodeids": [NODE], "cpu_python": str(CPU_PYTHON),
            "frozen_test_hashes": {"test_migration.py": sha(FILES["test_migration.py"])},
            "initial_production_hashes": {"migration_candidate.py": sha(FILES["migration_candidate.py"])}}
    observed = repository.run_repository_tests(files=FILES, task=task, run_root=tmp_path / "repository")
    assert observed["executed"] is True and observed["passed"] is True, observed
    assert observed["source_unchanged"] is True
    assert observed["tests"] == [{"nodeid": NODE, "outcome": "passed", "longreprtext": "", "phase": "call"}]
    assert observed["isolation"]["filesystem_backend"] in {"landlock", "user_mount_namespace"}


def test_hold_native_unittest_standalone_child(tmp_path):
    """Cover the existing 3.10 child, without rehashing its frozen environment."""
    assert HOLD_PYTHON.exists(), "The migrated HOLD Python 3.10 environment is required."
    template_path = ROOT / "artifacts/software-calibration-v051/hold-python310/environment-template.json"
    environment = json.loads(template_path.read_text())
    root = tmp_path / "hold-worktree"
    root.mkdir()
    (root / ".hold-tmp").mkdir()
    files = {
        "migration_candidate.py": FILES["migration_candidate.py"],
        "test_migration.py": (
            "import unittest\nfrom migration_candidate import answer\n\n"
            "class MigrationTest(unittest.TestCase):\n"
            "    def test_answer(self):\n        self.assertEqual(answer(), 42)\n\n"
            "if __name__ == '__main__':\n    unittest.main()\n"
        ),
    }
    for name, content in files.items():
        (root / name).write_text(content)
    node = "test_answer (__main__.MigrationTest)"
    spec = {
        "worktree": str(root), "nodeids": [node], "nonce": "synthetic-server-control",
        "test_engine": "native_unittest", "engine_spec": {"script": "test_migration.py", "argv": ["--verbose"]},
        "target_modules": ["migration_candidate"], "dependency_paths": [],
        "file_sha256": {name: sha(content) for name, content in files.items()},
        "shell_helper_source": holdout.source_ref(Path(shell.__file__)),
        "filesystem_policy": shell.filesystem_policy(),
        "parent_pid": os.getpid(), "parent_start_ticks": shell.process_identity(os.getpid())["start_ticks"],
        "readonly_paths": ["/usr/bin", "/usr/lib/x86_64-linux-gnu", "/usr/lib64", "/lib64", "/etc/ld.so.cache",
                           *environment["runtime_paths"]],
        "env": {"PATH": str(HOLD_PYTHON.parent) + ":/usr/bin:/bin", "TMPDIR": str(root / ".hold-tmp"),
                "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "LC_ALL": "C.UTF-8"},
        "cpu_seconds": 10, "memory_bytes": 536870912, "file_bytes": 8388608,
        "uid_thread_limit": shell.uid_threads() + 16,
    }
    spec_path = tmp_path / "hold-spec.json"
    spec_path.write_text(json.dumps(spec))
    process = subprocess.Popen([str(HOLD_PYTHON), "-I", str(Path(holdout.__file__)), str(spec_path)],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               start_new_session=True, env={"PATH": "/usr/bin:/bin"})
    try:
        output, _ = process.communicate(timeout=20)
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
    text = output.decode()
    assert process.returncode == 0, text
    rows = [json.loads(line[len(holdout.RESULT_PREFIX):]) for line in text.splitlines()
            if line.startswith(holdout.RESULT_PREFIX)]
    assert len(rows) == 1, text
    observed = rows[0]
    assert observed["returncode"] == 0 and observed["original_id_bijection"] is True, observed
    assert observed["tests"] == [{"nodeid": node, "outcome": "passed"}]
    assert observed["target_imports_from_this_tree"] is True
    assert observed["isolation"]["filesystem_backend"] in {"landlock", "user_mount_namespace"}


def test_generic_readonly_worker_denies_mutation_and_subprocess(tmp_path):
    code = '''
import ctypes, errno, json, os
from pathlib import Path
from migration_candidate import answer
checks = {"candidate_read": answer() == 42}
for name, operation in (
    ("write", lambda: Path("migration_candidate.py").write_text("unexpected")),
    ("truncate", lambda: os.truncate("migration_candidate.py", 0)),
):
    try:
        operation()
    except OSError as error:
        checks[name] = error.errno in (errno.EACCES, errno.EROFS)
    else:
        checks[name] = False
libc = ctypes.CDLL(None, use_errno=True)
ctypes.set_errno(0)
child = libc.fork()
if child == 0:
    os._exit(0)
if child > 0:
    os.waitpid(child, 0)
checks["fork"] = child == -1 and ctypes.get_errno() == errno.EPERM
print(json.dumps(checks))
'''
    result = software_sandbox.run_isolated(
        {"migration_candidate.py": FILES["migration_candidate.py"]}, code, run_root=tmp_path / "readonly")
    assert result["executed"] and result["driver_completed"] and result["returncode"] == 0, result
    checks = json.loads(result["output"])
    assert checks == {"candidate_read": True, "write": True, "truncate": True, "fork": True}


def test_namespace_preflight_rejects_overlap_privileged_paths_and_inherited_directory(tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    for readonly in ([str(tmp_path)], ["/proc"], ["/"]):
        with pytest.raises((ValueError, RuntimeError)):
            namespace.validate_spec({"worktree": str(worktree), "readonly_paths": readonly})
    with pytest.raises(ValueError, match="nested mount"):
        namespace._validate_mounts([{"path": str(worktree / "nested"), "options": ["rw"]}],
                                   [str(worktree)])
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        code = '''
import importlib.util, json, sys
source = importlib.util.spec_from_file_location("namespace_control", sys.argv[1])
module = importlib.util.module_from_spec(source)
source.loader.exec_module(module)
try:
    module.validate_spec({"worktree": sys.argv[2], "readonly_paths": []})
except (ValueError, RuntimeError) as error:
    print(json.dumps({"blocked": True, "message": str(error)}))
else:
    print(json.dumps({"blocked": False}))
'''
        result = subprocess.run([str(CPU_PYTHON), "-I", "-S", "-c", code,
                                 str(Path(namespace.__file__)), str(worktree)],
                                capture_output=True, text=True, pass_fds=(fd,), timeout=10)
        assert result.returncode == 0, result.stderr
        observed = json.loads(result.stdout)
        assert observed["blocked"] is True
        assert f"descriptor: {fd} " in observed["message"]
    finally:
        os.close(fd)


def test_changed_filesystem_policy_is_rejected_before_install(tmp_path):
    policy = shell.filesystem_policy()
    altered = {**policy, "filesystem_backend": "unconfined"}
    with pytest.raises(RuntimeError, match="Filesystem backend/capability/source changed"):
        shell.install({"filesystem_policy": altered, "worktree": str(tmp_path), "readonly_paths": []})
    assert not any(tmp_path.iterdir())


def test_only_readonly_urandom_runtime_descriptor_is_admitted(tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    ordinary_file = tmp_path / "ordinary-canary.txt"
    ordinary_file.write_text("private-controller-canary")
    code = '''
import importlib.util, json, sys
source = importlib.util.spec_from_file_location("namespace_fd_control", sys.argv[1])
module = importlib.util.module_from_spec(source)
source.loader.exec_module(module)
try:
    plan = module.validate_spec({"worktree": sys.argv[2], "readonly_paths": []})
except (ValueError, RuntimeError) as error:
    print(json.dumps({"blocked": True, "message": str(error)}))
else:
    print(json.dumps({"blocked": False,
                      "fixture_fds": plan["fixture_fds"],
                      "runtime_readonly_device_fds": plan["runtime_readonly_device_fds"]}))
'''
    cases = (
        ("readonly_urandom", "/dev/urandom", os.O_RDONLY, False),
        ("writeonly_urandom", "/dev/urandom", os.O_WRONLY, True),
        ("readwrite_urandom", "/dev/urandom", os.O_RDWR, True),
        ("pathonly_urandom", "/dev/urandom", os.O_PATH, True),
        ("readonly_ordinary_file", ordinary_file, os.O_RDONLY, True),
    )
    for name, path, flags, blocked in cases:
        descriptor = os.open(path, flags)
        try:
            result = subprocess.run([str(CPU_PYTHON), "-I", "-S", "-c", code,
                                     str(Path(namespace.__file__)), str(worktree)],
                                    capture_output=True, text=True, pass_fds=(descriptor,), timeout=10)
            assert result.returncode == 0, (name, result.stderr)
            observed = json.loads(result.stdout)
            assert observed["blocked"] is blocked, (name, observed)
            if blocked:
                assert f"Unauthorized inherited descriptor: {descriptor} " in observed["message"]
            else:
                assert descriptor in observed["runtime_readonly_device_fds"]
                assert observed["fixture_fds"] == []
        finally:
            os.close(descriptor)
