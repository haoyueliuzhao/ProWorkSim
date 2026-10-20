"""Pinned SWE-smith environments and candidate-only, independent grading.

The official profile chooses commands, parsers and F2P/P2P resolution. Docker
transport, immutable export and admission are ours. No official helper is allowed
to select the default daemon, fetch branches, or expose a correct git ancestor.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
from functools import lru_cache
import hashlib
import importlib.metadata
import inspect
import io
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import shlex
import sys
import tarfile
from threading import RLock
import time
import uuid

from .software_panel_v053 import CODE_REVISION, canonical_bytes, source_record

VERSION = "software-panel-docker-v053-v1"
WORKDIR = "/testbed"
SNAPSHOT_LIMIT = 512 * 1024 * 1024
ARCHIVE_TRANSPORT_LIMIT = 16 * 1024 * 1024 * 1024
EXCLUDED_PARTS = frozenset({
    ".git", ".pytest_cache", "__pycache__", ".mypy_cache", ".ruff_cache",
    ".tox", ".venv", "node_modules",
})
DEFAULT_RESOURCES = {"mem_limit": "10g", "cpus": 4, "pids_limit": 512}


class CommonSystemFault(RuntimeError):
    """Shared transport/dependency/identity fault: pause, never replace a repo."""


class SourceEnvironmentError(RuntimeError):
    """Evidence that this pinned source cannot run under the declared contract."""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def source_ref(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {"path": str(path), "sha256": sha256(data), "bytes": len(data)}


def checked(reference):
    path = Path(reference["path"])
    if not path.is_absolute() or source_ref(path) != reference:
        raise ValueError("Frozen Docker evidence changed")
    return path


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not isinstance(data, bytes):
        data = canonical_bytes(data)
    with path.open("xb") as stream:
        stream.write(data)
    return source_ref(path)


def safe_relative(value):
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or ".." in path.parts
            or ".git" in path.parts or str(path) in ("", ".")):
        raise ValueError(f"Unsafe source path: {value!r}")
    return str(path)


def protected_path(path, profile, explicit_files=()):
    """Protect tests, test collection hooks and runner configuration."""
    path = PurePosixPath(path)
    return (
        str(path) in explicit_files
        or profile._is_test_path(str(path.parent), path.name)
        or path.name in {"conftest.py", "pytest.ini", ".coveragerc", "tox.ini",
                         "pyproject.toml", "setup.cfg"}
    )


@lru_cache(maxsize=1)
def official_modules(code_root):
    root = Path(code_root).resolve()
    if CODE_REVISION not in root.name:
        raise ValueError("Use the extracted pinned official source revision")
    if not (root / "swesmith/harness/grading.py").is_file():
        raise ValueError("Missing pinned official grading source")
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    try:
        import dotenv.main
        if not getattr(dotenv.main, "_load_dotenv_disabled", lambda: False)():
            raise ImportError("Require python-dotenv with PYTHON_DOTENV_DISABLED support")
        sys.path.insert(0, str(root))
        from swesmith import constants
        from swesmith.harness import grading
        from swesmith.profiles import registry
    except ImportError as error:
        raise CommonSystemFault(f"Official harness import failed: {error}") from error
    if not Path(grading.__file__).resolve().is_relative_to(root):
        raise ValueError("Another SWE-smith installation was imported")
    return registry, grading, constants


def load_task(config, task):
    if "instance_id" in task and "patch" in task:
        raw = copy.deepcopy(task)
    elif task.get("source_row"):
        raw = json.loads(checked(task["source_row"]).read_bytes())
    else:
        task_id = task.get("task_id", task.get("instance_id"))
        raw = json.loads((Path(config["task_rows_root"]) / (task_id + ".json")).read_bytes())
    description = source_record(raw)
    if task.get("source_row_sha256") not in (None, description["source_row_sha256"]):
        raise ValueError("Task differs from the frozen panel source row")
    return raw, description


def profile_contract(config, task):
    if config.get("disable_dotenv", True) is not True:
        raise ValueError("The v053 harness requires dotenv auto-loading disabled")
    registry, _, _ = official_modules(config["official_code_root"])
    profile = registry.get_from_inst(task)
    if profile.image_name != task["image_name"]:
        raise ValueError("Official task image does not match its pinned profile")
    command, _ = profile.get_test_cmd(task, f2p_only=False)
    f2p, p2p = profile.get_test_files(task)
    files = sorted({safe_relative(str(path)) for path in f2p + p2p})
    module_path = Path(sys.modules[type(profile).__module__].__file__).resolve()
    oracle_sources = {
        name: source_ref(Path(sys.modules[name].__file__))
        for name in ("swesmith.profiles.base", "swesmith.harness.grading",
                     "swesmith.constants", "swebench.harness.grading",
                     "swebench.harness.constants")
    }
    return profile, {
        "official_code_revision": CODE_REVISION,
        "dotenv_auto_loading_disabled": True,
        "profile_class": type(profile).__name__,
        "profile_source": source_ref(module_path),
        "oracle_sources": oracle_sources,
        "harness_dependency_versions": {
            package: importlib.metadata.version(package)
            for package in ("docker", "swebench", "ghapi", "python-dotenv", "unidiff")
        },
        "base_commit": profile.commit, "image_name": profile.image_name,
        "test_command": command, "public_test_command": profile.test_cmd,
        "test_timeout_seconds": int(profile.timeout),
        "reference_timeout_seconds": int(profile.timeout_ref),
        "official_test_files": files,
        "hidden_f2p_files": sorted({safe_relative(str(path)) for path in f2p}),
        "actor_f2p_files_hidden": True,
        "docker_init_enabled": True,
        "actor_background_processes_persist": False,
        "candidate_source_byte_limit": SNAPSHOT_LIMIT,
        "candidate_archive_transport_byte_limit": ARCHIVE_TRANSPORT_LIMIT,
        "grading": (
            "official parser and auxiliary official get_eval_report; primary R requires "
            "every original F2P/P2P status PASSED or XFAIL, not f2p_only"
        ),
        "test_protection": (
            "official F2P/P2P files, profile test paths, collection hooks, "
            "pytest.ini, tox.ini, setup.cfg and pyproject.toml"
        ),
    }


def docker_client(config):
    import docker

    host = config["docker_host"]
    if (not host.startswith("unix:///") or host == "unix:///var/run/docker.sock"
            or not Path(host.removeprefix("unix://")).is_absolute()):
        raise ValueError("An explicit dedicated local Docker socket is required")
    try:
        return docker.DockerClient(base_url=host, timeout=1200)
    except Exception as error:
        raise CommonSystemFault(f"Dedicated Docker daemon unavailable: {error}") from error


def resources(config):
    value = {key: config.get(key, default) for key, default in DEFAULT_RESOURCES.items()}
    if type(value["cpus"]) not in (int, float) or not 0 < value["cpus"] <= 32:
        raise ValueError("Invalid explicit container CPU limit")
    if type(value["pids_limit"]) is not int or not 16 <= value["pids_limit"] <= 4096:
        raise ValueError("Invalid explicit container PID limit")
    return value


def image_identity(client, image_name, *, allow_pull=False):
    import docker

    try:
        try:
            image = client.images.get(image_name)
        except docker.errors.ImageNotFound:
            if not allow_pull:
                raise CommonSystemFault("Admitted image is missing from the dedicated daemon")
            image = client.images.pull(image_name)
    except docker.errors.APIError as error:
        if error.status_code == 404:
            raise SourceEnvironmentError(f"Pinned source image unavailable: {error}") from error
        raise CommonSystemFault(f"Image registry/daemon failure: {error}") from error
    except CommonSystemFault:
        raise
    except Exception as error:
        raise CommonSystemFault(f"Image transport failed: {error}") from error
    return {"requested_image": image_name, "image_id": image.id,
            "repo_digests": sorted(image.attrs.get("RepoDigests") or []),
            "architecture": image.attrs.get("Architecture"),
            "os": image.attrs.get("Os")}


def put_bytes(container, path, content, *, mode=0o600):
    """Copy one harness-owned file without a shell or host bind mount."""
    target = PurePosixPath(path)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        info = tarfile.TarInfo(target.name)
        info.size, info.mode = len(content), mode
        archive.addfile(info, io.BytesIO(content))
    if not container.put_archive(str(target.parent), buffer.getvalue()):
        raise RuntimeError(f"Docker did not copy harness file {path}")


def exec_in(container, command, timeout_seconds, *, output_limit=None):
    if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 7200:
        raise ValueError("A bounded positive execution timeout is required")
    started = time.monotonic()
    # GNU timeout terminates the command's process group, not just the client wait.
    wrapped = ["timeout", "--signal=TERM", "--kill-after=5",
               str(timeout_seconds), "/bin/bash", "-lc", command]
    try:
        result = container.exec_run(wrapped, workdir=WORKDIR, user="root", demux=False)
        text = result.output.decode("utf-8", errors="replace")
        truncated = output_limit is not None and len(text) > output_limit
        if truncated:
            text = text[:output_limit] + "\n[terminal output truncated]"
        return {
            "output": text, "returncode": result.exit_code, "exception_info": None,
            "extra": {"timed_out": result.exit_code in (124, 137),
                      "seconds": time.monotonic() - started, "truncated": truncated},
        }
    except Exception as error:
        return {"output": "", "returncode": None,
                "exception_info": f"{type(error).__name__}: {error}",
                "extra": {"seconds": time.monotonic() - started, "transport_fault": True}}


def process_targets(current, baseline, own_pid):
    """Select only new live process identities inside one actor PID namespace."""
    return {
        pid: row["starttime"] for pid, row in current.items()
        if pid not in ("1", str(own_pid)) and row["state"] not in ("Z", "X")
        and baseline.get(pid, {}).get("starttime") != row["starttime"]
    }


ACTOR_SUPERVISOR = inspect.getsource(process_targets) + """
import json, os, signal, subprocess, sys, time
def inventory():
    result = {}
    for name in os.listdir('/proc'):
        if not name.isdigit():
            continue
        try:
            with open('/proc/' + name + '/stat') as stream:
                fields = stream.read().rsplit(')', 1)[1].split()
            result[name] = {'state': fields[0], 'starttime': fields[19]}
        except (FileNotFoundError, ProcessLookupError):
            continue
    return result
def cleanup(baseline):
    if '1' not in baseline:
        raise RuntimeError('Missing protected container init identity')
    signals = []
    for attempt in range(6):
        targets = process_targets(inventory(), baseline, os.getpid())
        if not targets:
            break
        selected_signal = signal.SIGTERM if attempt == 0 else signal.SIGKILL
        for pid, birth in targets.items():
            if inventory().get(pid, {}).get('starttime') != birth:
                continue
            try:
                os.kill(int(pid), selected_signal)
                signals.append({'pid': int(pid), 'starttime': birth, 'signal': int(selected_signal)})
            except ProcessLookupError:
                pass
        time.sleep(.05)
    remaining = process_targets(inventory(), baseline, os.getpid())
    return {'signalled': signals, 'remaining_live_processes': remaining}
baseline = inventory()
receipt = {'returncode': None, 'exception_info': None}
try:
    child = subprocess.Popen(
        ['timeout', '--signal=TERM', '--kill-after=5', sys.argv[2], '/bin/bash', '-lc', sys.argv[1]],
        cwd='/testbed', stdin=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    receipt['returncode'] = child.wait()
except Exception as error:
    receipt['exception_info'] = type(error).__name__ + ': ' + str(error)
try:
    receipt['cleanup'] = cleanup(baseline)
    if receipt['cleanup']['remaining_live_processes']:
        receipt['exception_info'] = 'Background processes survived terminal cleanup'
except Exception as error:
    receipt['exception_info'] = 'Cleanup failed: ' + type(error).__name__ + ': ' + str(error)
descriptor = os.open(sys.argv[3], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
with os.fdopen(descriptor, 'w') as stream:
    json.dump(receipt, stream)
"""


def execute_actor_command(container, command, timeout_seconds):
    """Cleanup happens inside the exec supervisor before inherited stdout closes."""
    started = time.monotonic()
    receipt_path = "/tmp/proworksim-command-" + uuid.uuid4().hex + ".json"
    output = ""
    try:
        execution = container.exec_run(
            ["/opt/miniconda3/bin/python", "-I", "-S", "-c", ACTOR_SUPERVISOR,
             command, str(timeout_seconds), receipt_path],
            workdir=WORKDIR, user="root", demux=False)
        output = execution.output.decode("utf-8", errors="replace")
        if execution.exit_code != 0:
            raise CommonSystemFault(f"Trusted actor supervisor exited {execution.exit_code}")
        chunks, _ = container.get_archive(receipt_path)
        stream = io.BufferedReader(_ChunkReader(chunks, 1024 * 1024))
        with tarfile.open(fileobj=stream, mode="r|*") as archive:
            member = next(iter(archive))
            if not member.isfile() or member.name != PurePosixPath(receipt_path).name:
                raise CommonSystemFault("Actor supervisor receipt identity mismatch")
            receipt = json.loads(archive.extractfile(member).read())
        removal = container.exec_run(["rm", "-f", "--", receipt_path], user="root")
        if removal.exit_code != 0:
            raise CommonSystemFault("Could not remove actor supervisor receipt")
        return {
            "output": output[:24000] + ("\n[terminal output truncated]" if len(output) > 24000 else ""),
            "returncode": receipt["returncode"], "exception_info": receipt["exception_info"],
            "extra": {
                "seconds": time.monotonic() - started, "truncated": len(output) > 24000,
                "timed_out": receipt["returncode"] in (124, 137),
                "background_process_cleanup": receipt.get("cleanup"),
            },
        }
    except Exception as error:
        return {"output": output[:24000], "returncode": None,
                "exception_info": f"{type(error).__name__}: {error}",
                "extra": {"seconds": time.monotonic() - started, "transport_fault": True}}


def require_exec(container, command, timeout=120):
    result = exec_in(container, command, timeout)
    if result["exception_info"]:
        raise CommonSystemFault(f"Docker execution transport failed: {result}")
    if result["returncode"] != 0:
        raise SourceEnvironmentError(f"Environment command failed: {command}\n{result}")
    return result["output"]


@contextmanager
def container_context(config, image, *, role):
    client = docker_client(config)
    limits = resources(config)
    labels = {"proworksim.version": VERSION, "proworksim.role": role}
    labels.update({key: str(value) for key, value in config.get("episode_labels", {}).items()
                   if key in ("proworksim.slot_id", "proworksim.worker_root")})
    container = None
    try:
        container = client.containers.create(
            image=image["image_id"], name="proworksim-v053-" + role + "-" + uuid.uuid4().hex,
            command=["/bin/bash", "-lc", "exec tail -f /dev/null"],
            entrypoint=[], user="root", detach=True, network_mode="none", init=True,
            mem_limit=limits["mem_limit"], memswap_limit=limits["mem_limit"],
            nano_cpus=int(limits["cpus"] * 1_000_000_000),
            pids_limit=limits["pids_limit"], cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            labels=labels,
            environment={"PYTHONDONTWRITEBYTECODE": "1", "GIT_TERMINAL_PROMPT": "0",
                         "PIP_NO_INDEX": "1", "HF_HUB_OFFLINE": "1",
                         "TOKENIZERS_PARALLELISM": "false"},
            working_dir=WORKDIR,
        )
        container.start()
        yield container
    finally:
        if container is not None:
            container.remove(force=True, v=True)
        client.close()


def prepare_checkout(container, task, contract, *, state, actor=False):
    """Base + exact mutation; no network fetch or guessed task branch."""
    commit = shlex.quote(contract["base_commit"])
    require_exec(container, f"git -c safe.directory=/testbed reset --hard {commit}")
    actual = require_exec(container, "git rev-parse HEAD").strip()
    if actual != contract["base_commit"]:
        raise ValueError("Image does not contain the pinned base commit")
    if state in ("bug", "gold"):
        put_bytes(container, "/tmp/proworksim-mutation.diff", task["patch"].encode())
        require_exec(container, "git apply --check /tmp/proworksim-mutation.diff")
        require_exec(container, "git apply /tmp/proworksim-mutation.diff")
        if state == "gold":
            require_exec(container, "git apply --reverse --check /tmp/proworksim-mutation.diff")
            require_exec(container, "git apply --reverse /tmp/proworksim-mutation.diff")
            require_exec(container, "git diff --exit-code")
        require_exec(container, "rm -f /tmp/proworksim-mutation.diff")
    elif state != "clean":
        raise ValueError("Unknown checkout state")
    tracked = require_exec(container, "git ls-files -z").split("\0")
    tracked = [safe_relative(path) for path in tracked if path]
    hidden_files = []
    if actor:
        if state != "bug":
            raise ValueError("Actors must start from an independent buggy tree")
        # Official task branches hide F2P test files. Do it before the sole new
        # git commit so reset/reflog can never recover tests or correct source.
        hidden_files = contract["hidden_f2p_files"]
        hidden = " ".join(shlex.quote(path) for path in hidden_files)
        if hidden:
            require_exec(container, f"rm -f -- {hidden}")
    # The judge also executes candidate code. It must not expose correct source
    # through git show, reflogs or cached bytecode. Admission uses this same
    # sanitization, so repository-version dependencies are checked in advance.
    visible = [path for path in tracked if path not in hidden_files]
    put_bytes(container, "/tmp/proworksim-visible-source.list",
              ("\0".join(visible) + "\0").encode())
    require_exec(container, """
set -euo pipefail
find /testbed -type d -name .git -prune -exec rm -rf {} +
find /testbed -type d \\( -name __pycache__ -o -name .pytest_cache \\) -prune -exec rm -rf {} +
find /testbed -type f \\( -name '*.pyc' -o -name '*.pyo' \\) -delete
rm -rf /root/.cache /tmp/patch.diff /patch.diff /eval.sh
git init -q
git config user.name ProWorkSim
git config user.email evaluation@localhost
git add -A
xargs -0 -r git add -f -- < /tmp/proworksim-visible-source.list
rm -f /tmp/proworksim-visible-source.list
git -c core.hooksPath=/dev/null commit -qm 'Independent task initial state'
test "$(git rev-list --count HEAD)" = 1
test -z "$(git remote)"
""")
    return tracked


class _ChunkReader(io.RawIOBase):
    """Bounded Docker archive stream for Python's streaming tar reader."""

    def __init__(self, chunks, limit):
        self.chunks, self.buffer, self.total, self.limit = iter(chunks), b"", 0, limit

    def readable(self):
        return True

    def readinto(self, target):
        while not self.buffer:
            try:
                self.buffer = next(self.chunks)
            except StopIteration:
                return 0
            self.total += len(self.buffer)
            if self.total > self.limit:
                raise ValueError("Candidate archive exceeds its frozen byte limit")
        count = min(len(target), len(self.buffer))
        target[:count], self.buffer = self.buffer[:count], self.buffer[count:]
        return count


def normalize_archive(chunks, *, root="testbed", limit=SNAPSHOT_LIMIT,
                      transport_limit=ARCHIVE_TRANSPORT_LIMIT):
    """Canonical safe source archive; never follow model-controlled symlinks."""
    entries, contents, names = [], {}, set()
    # Installed .venv trees can be large, but are streamed and discarded. The
    # actual exported candidate has a separate, much smaller source byte limit.
    stream = io.BufferedReader(_ChunkReader(chunks, transport_limit))
    total = 0
    with tarfile.open(fileobj=stream, mode="r|*") as archive:
        for info in archive:
            raw = PurePosixPath(info.name)
            if not raw.parts or raw.parts[0] != root:
                raise ValueError("Docker archive root differs from the requested workspace")
            if len(raw.parts) == 1:
                continue
            relative = str(PurePosixPath(*raw.parts[1:]))
            if EXCLUDED_PARTS.intersection(raw.parts[1:]) or relative.endswith((".pyc", ".pyo")):
                continue
            path = safe_relative(relative)
            if info.isdir():
                continue
            if path in names:
                raise ValueError("Duplicate candidate archive path")
            names.add(path)
            if info.isfile():
                total += info.size
                if total > limit:
                    raise ValueError("Candidate source exceeds its frozen byte limit")
                data = archive.extractfile(info).read()
                mode = 0o755 if info.mode & 0o111 else 0o644
                entries.append({"path": path, "kind": "file", "mode": mode,
                                "sha256": sha256(data), "bytes": len(data)})
                contents[path] = data
            elif info.issym():
                target = info.linkname
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
                if (target.startswith("/") or resolved == ".." or resolved.startswith("../")
                        or ".git" in PurePosixPath(resolved).parts):
                    raise ValueError("Candidate symlink escapes the source tree")
                entries.append({"path": path, "kind": "symlink", "target": target})
            else:
                raise ValueError("Candidate archive contains a special file or hardlink")
    links = {row["path"] for row in entries if row["kind"] == "symlink"}
    for path in names:
        if any(str(parent) in links for parent in PurePosixPath(path).parents):
            raise ValueError("Candidate source has a symlink ancestor")
    output = io.BytesIO()
    entries.sort(key=lambda row: row["path"])
    with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for row in entries:
            info = tarfile.TarInfo(row["path"])
            if row["kind"] == "symlink":
                info.type, info.linkname, info.mode = tarfile.SYMTYPE, row["target"], 0o777
                archive.addfile(info)
            else:
                info.size, info.mode = row["bytes"], row["mode"]
                archive.addfile(info, io.BytesIO(contents[row["path"]]))
    return output.getvalue(), entries


def capture_workspace(container):
    chunks, _ = container.get_archive(WORKDIR)
    return normalize_archive(chunks)


def clear_exported_source(container):
    """Remove stale source, including untracked build outputs and old symlinks.

    Fixed environment directories omitted by export remain in the fresh judge
    image. This runs before any candidate code or file enters the judge.
    """
    script = (
        "import os\n"
        f"excluded = {sorted(EXCLUDED_PARTS)!r}\n"
        "directories = []\n"
        "for root, dirs, files in os.walk('/testbed', topdown=True, followlinks=False):\n"
        "    dirs[:] = [name for name in dirs if name not in excluded]\n"
        "    for name in list(dirs):\n"
        "        path = os.path.join(root, name)\n"
        "        if os.path.islink(path):\n"
        "            os.unlink(path)\n"
        "            dirs.remove(name)\n"
        "    directories.extend(os.path.join(root, name) for name in dirs)\n"
        "    for name in files:\n"
        "        if name not in excluded:\n"
        "            os.unlink(os.path.join(root, name))\n"
        "for path in reversed(directories):\n"
        "    if not os.listdir(path):\n"
        "        os.rmdir(path)\n"
    )
    put_bytes(container, "/tmp/proworksim-clear-source.py", script.encode())
    require_exec(container, "/opt/miniconda3/bin/python /tmp/proworksim-clear-source.py")


def strict_completion(task, status_map, *, technical_error=None):
    required = task["FAIL_TO_PASS"] + task["PASS_TO_PASS"]
    not_passed = [{"test": case, "status": status_map.get(case, "MISSING")}
                  for case in required if status_map.get(case) not in ("PASSED", "XFAIL")]
    return {
        "R_code": int(not not_passed) if technical_error is None else None,
        "required_not_passed": not_passed,
        "required_test_coverage": {
            "total": len(required),
            "observed": sum(case in status_map for case in required),
            "passed_or_xfail": len(required) - len(not_passed),
        },
    }


def execute_official_test(config, container, task, contract, folder, *, timeout=None):
    _, grading, constants = official_modules(config["official_code_root"])
    folder = Path(folder)
    script = "\n".join([
        "#!/bin/bash", "set -uxo pipefail", "cd /testbed",
        f": '{constants.TEST_OUTPUT_START}'", contract["test_command"],
        "proworksim_test_exit=$?",
        f": '{constants.TEST_OUTPUT_END}'", 'exit "$proworksim_test_exit"', "",
    ])
    put_bytes(container, "/tmp/proworksim-eval.sh", script.encode())
    result = exec_in(container, "/bin/bash /tmp/proworksim-eval.sh",
                     timeout or contract["test_timeout_seconds"])
    log_ref = write_new(folder / "test-output.txt", result["output"].encode())
    run_ref = write_new(folder / "execution.json", result)
    container.reload()
    technical = None
    if result["exception_info"]:
        technical = "docker_transport_failure"
    elif container.attrs.get("State", {}).get("OOMKilled"):
        technical = "container_oom"
    elif result["extra"].get("timed_out"):
        technical = "official_test_timeout"
    elif result["returncode"] in (126, 127):
        technical = "official_test_command_unavailable"
    output, complete = grading.read_test_output(log_ref["path"])
    if not complete and technical is None:
        technical = "official_test_output_incomplete"
    profile, _ = profile_contract(config, task)
    status_map = profile.log_parser(output) if complete else {}
    # A candidate may break imports/collection. With a complete, normally
    # terminated test run the official missing-test failures remain model R=0.
    # Admission separately requires observed clean/bug/gold transitions.
    report = grading.get_eval_report(
        {"model_patch": "candidate snapshot"}, copy.deepcopy(task), log_ref["path"],
        f2p_only=False) if technical is None else None
    strict = strict_completion(task, status_map, technical_error=technical)
    official_result = int(report["resolved"]) if report is not None else None
    receipt = {
        "version": VERSION, "task_id": task["instance_id"], "contract": contract,
        "test_output": log_ref, "execution": run_ref, "technical_error": technical,
        "official_report": report, "test_status_map": status_map,
        **strict, "official_R": official_result,
        "primary_R_matches_official_R": (
            strict["R_code"] == official_result if technical is None else None),
    }
    write_new(folder / "receipt.json", receipt)
    return receipt


def admission_verdict(task, clean, bug, gold):
    """Admission is determined without any model trajectory or outcome."""
    technical = [f"{name}:{receipt['technical_error']}" for name, receipt in
                 (("clean", clean), ("bug", bug), ("gold", gold))
                 if receipt.get("technical_error")]
    if technical:
        return False, ";".join(technical)
    for phase, record in (("clean", clean), ("gold", gold)):
        statuses = record["test_status_map"]
        missing = [case for case in task["FAIL_TO_PASS"] + task["PASS_TO_PASS"]
                   if statuses.get(case) not in ("PASSED", "XFAIL")]
        if missing:
            return False, f"{phase}_required_tests_not_passing:{len(missing)}"
    statuses = bug["test_status_map"]
    bad_f2p = [case for case in task["FAIL_TO_PASS"]
               if statuses.get(case) not in ("FAILED", "ERROR")]
    bad_p2p = [case for case in task["PASS_TO_PASS"]
               if statuses.get(case) not in ("PASSED", "XFAIL")]
    if bad_f2p or bad_p2p:
        return False, f"bug_expected_transition_mismatch:f2p={len(bad_f2p)},p2p={len(bad_p2p)}"
    return True, None


def run_admission_phase(config, image, task, contract, root, state, *, timeout=None):
    """Reuse completed evidence and retain interrupted attempts separately."""
    root = Path(root)
    completed = root / "completed.json"
    if completed.exists():
        reference = json.loads(completed.read_bytes())["receipt"]
        return json.loads(checked(reference).read_bytes()), reference
    attempt = root / ("attempt-" + uuid.uuid4().hex)
    write_new(attempt / "entered.json", {
        "task_id": task["instance_id"], "state": state, "image": image,
        "contract": contract, "model_calls": 0,
    })
    try:
        with container_context(config, image, role="admission-" + state) as container:
            prepare_checkout(container, task, contract, state=state)
            receipt = execute_official_test(
                config, container, task, contract, attempt, timeout=timeout)
        if receipt["technical_error"] == "docker_transport_failure":
            raise CommonSystemFault(f"Docker transport failed during {state} testing")
        reference = source_ref(attempt / "receipt.json")
        write_new(completed, {"receipt": reference})
        return receipt, reference
    except Exception as error:
        write_new(attempt / "exception.json", {
            "exception_type": type(error).__name__, "detail": str(error),
            "completed": False, "model_calls": 0,
        })
        raise


def qualify_repository(config, repository, *, allow_pull=False, stop_event=None):
    """Check every preselected task; never substitute an easier task within a repo."""
    folder = Path(config["environment_root"]) / "repositories" / repository["profile_slug"]
    folder.mkdir(parents=True, exist_ok=True)
    summary_path = folder / "qualification.json"
    if len(set(repository["candidate_task_ids"])) != 10:
        raise ValueError("A repository admission requires its ten frozen distinct tasks")
    if summary_path.exists():
        previous = json.loads(summary_path.read_bytes())
        if (previous.get("resources") != resources(config)
                or previous["candidate_task_ids"] != repository["candidate_task_ids"]):
            raise ValueError("Existing repository admission has another configuration")
        for reference in previous["task_receipts"]:
            checked(reference)
        return previous
    client, started = None, time.monotonic()
    summary = {
        "version": VERSION, "repository": repository["repository"],
        "candidate_task_ids": repository["candidate_task_ids"],
        "admitted": False, "qualified_task_ids": [], "model_runs_started": 0,
        "resources": resources(config), "network": "none", "task_receipts": [],
        "status": "running",
    }
    try:
        if stop_event is not None and stop_event.is_set():
            raise CommonSystemFault("Admission paused by another repository's shared fault")
        client = docker_client(config)
        image = image_identity(client, repository["image_name"], allow_pull=allow_pull)
        summary["image"] = image
        if (folder / "image.json").exists():
            if json.loads((folder / "image.json").read_bytes()) != image:
                raise ValueError("Repository image identity changed after admission began")
        else:
            write_new(folder / "image.json", image)
        clean_cache = {}
        for task_id in repository["candidate_task_ids"]:
            if stop_event is not None and stop_event.is_set():
                raise CommonSystemFault("Admission paused by another repository's shared fault")
            declared = next(row for row in repository["candidate_tasks"]
                            if row["task_id"] == task_id)
            task, description = load_task(config, declared)
            profile, contract = profile_contract(config, task)
            task_folder = Path(config["environment_root"]) / "tasks" / task_id
            qualification_path = task_folder / "qualification.json"
            if qualification_path.exists():
                record = json.loads(qualification_path.read_bytes())
                if (record["source_row_sha256"] != description["source_row_sha256"]
                        or record["contract"] != contract or record["image"] != image
                        or record["resources"] != resources(config)):
                    raise ValueError("Previous admission belongs to another source or environment")
            else:
                clean_key = sha256(canonical_bytes({
                    "image": image, "base_commit": profile.commit,
                    "command": contract["test_command"], "resources": resources(config),
                    "profile": contract["profile_source"],
                    "oracle_sources": contract["oracle_sources"],
                    "harness_dependency_versions": contract["harness_dependency_versions"],
                }))
                clean_folder = folder / "clean" / clean_key
                if clean_key not in clean_cache:
                    clean_cache[clean_key] = run_admission_phase(
                        config, image, task, contract, clean_folder, "clean",
                        timeout=contract["reference_timeout_seconds"])
                phases = {"clean": clean_cache[clean_key][0]}
                phase_references = {"clean": clean_cache[clean_key][1]}
                for state in ("bug", "gold"):
                    phase_folder = task_folder / state
                    phases[state], phase_references[state] = run_admission_phase(
                        config, image, task, contract, phase_folder, state)
                admitted, reason = admission_verdict(task, **phases)
                record = {
                    "version": VERSION, "task_id": task_id, "admitted": admitted,
                    "reason": reason, "source_row_sha256": description["source_row_sha256"],
                    "contract": contract, "image": image, "resources": resources(config),
                    "clean_reused_identity": clean_key,
                    "clean_receipt": phase_references["clean"],
                    "bug_receipt": phase_references["bug"],
                    "gold_receipt": phase_references["gold"],
                    "model_runs_started": 0,
                }
                write_new(qualification_path, record)
            summary["task_receipts"].append(source_ref(qualification_path))
            if record["admitted"]:
                summary["qualified_task_ids"].append(task_id)
        summary["admitted"] = set(summary["qualified_task_ids"]) == set(repository["candidate_task_ids"])
        summary["reason"] = None if summary["admitted"] else "one_or_more_preselected_tasks_failed_environment_admission"
        if summary["admitted"]:
            # Source archive size, link types and installed environments differ
            # across repositories. Check the transport once per repository,
            # using its first preselected task; no model and no extra test run.
            first_task = repository["candidate_tasks"][0]
            control_row = {"task_id": first_task["task_id"],
                           "slot_id": "admission-" + repository["profile_slug"]}
            control_root = folder / "actor-export-control"
            completed = control_root / "completed.json"
            if completed.exists():
                control = json.loads(completed.read_bytes())
                checked(control["candidate_lock"])
            else:
                control_started = time.monotonic()
                attempt_root = control_root / ("attempt-" + uuid.uuid4().hex)
                with DockerBackend(config, first_task, control_row, attempt_root) as backend:
                    control = {
                        "candidate_lock": backend.export_candidate(attempt_root),
                        "model_calls": 0, "additional_test_runs": 0,
                    }
                control["wall_seconds"] = time.monotonic() - control_started
                write_new(completed, control)
            summary["actor_export_control"] = control
        summary["status"] = "admitted" if summary["admitted"] else "source_not_admitted"
    except SourceEnvironmentError as error:
        summary["admitted"] = False
        summary["status"] = "source_not_admitted"
        summary["reason"] = f"{type(error).__name__}: {error}"
    except Exception as error:
        if stop_event is not None:
            stop_event.set()
        summary["admitted"] = None
        summary["status"] = "unresolved_common_system_fault"
        summary["reason"] = f"{type(error).__name__}: {error}"
    finally:
        if client is not None:
            client.close()
    summary["wall_seconds"] = time.monotonic() - started
    summary["generation_tokens"] = 0
    if summary["status"] == "unresolved_common_system_fault":
        summary["fault_receipt"] = write_new(
            folder / ("common-system-fault-" + uuid.uuid4().hex + ".json"), summary)
    else:
        write_new(summary_path, summary)
    return summary


class DockerBackend:
    """One independent actor container and one immutable final candidate."""

    working_dir = WORKDIR

    def __init__(self, config, task, row, run_root):
        self.config, self.row, self.run_root = copy.deepcopy(config), copy.deepcopy(row), Path(run_root)
        self._command_lock = RLock()
        self.config["episode_labels"] = {
            "proworksim.slot_id": row["slot_id"],
            "proworksim.worker_root": str(Path(run_root)),
        }
        self.task, description = load_task(config, task)
        self.profile, self.contract = profile_contract(config, self.task)
        self.container, self._context, self._export = None, None, None
        if row["task_id"] != self.task["instance_id"]:
            raise ValueError("Episode row differs from the task source")
        qualification_path = Path(config["environment_root"]) / "tasks" / row["task_id"] / "qualification.json"
        qualification = json.loads(qualification_path.read_bytes())
        if (qualification.get("admitted") is not True
                or qualification["source_row_sha256"] != description["source_row_sha256"]
                or qualification["contract"] != self.contract
                or qualification["resources"] != resources(config)):
            raise ValueError("Formal environment differs from admitted identity")
        self.image = qualification["image"]
        self._context = container_context(self.config, self.image, role="actor")
        self.container = self._context.__enter__()
        try:
            self.tracked = prepare_checkout(
                self.container, self.task, self.contract, state="bug", actor=True)
            self.initial_tree = require_exec(self.container, "git rev-parse HEAD^{tree}").strip()
            self.identity = {
                "version": VERSION, "task_id": row["task_id"], "slot_id": row["slot_id"],
                "fresh_initial_state": True, "image": self.image,
                "source_row_sha256": description["source_row_sha256"],
                "qualification": source_ref(qualification_path), "contract": self.contract,
                "initial_git_tree": self.initial_tree, "git_history_commits": 1,
                "network": "none", "host_mounts": [], "resources": resources(config),
                "actor_background_processes_persist": False,
                "container_id": self.container.id,
            }
            write_new(self.run_root / "docker-initial-state.json", self.identity)
        except BaseException:
            self.close()
            raise

    def execute(self, command, timeout_seconds=120):
        with self._command_lock:
            if self._export is not None:
                raise ValueError("Actor commands are forbidden after candidate locking")
            if not isinstance(command, str):
                raise TypeError("Terminal command must be text")
            if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 600:
                raise ValueError("Actor command timeout must be positive and at most 600 seconds")
            return execute_actor_command(self.container, command, timeout_seconds)

    def run_public_tests(self):
        return self.execute(self.contract["public_test_command"],
                            self.contract["test_timeout_seconds"])

    def export_candidate(self, run_root=None):
        with self._command_lock:
            return self._export_candidate_locked(run_root)

    def _export_candidate_locked(self, run_root):
        if self._export is not None:
            raise FileExistsError("A final candidate has already been locked")
        folder = Path(run_root) if run_root is not None else self.run_root
        self.container.pause()
        try:
            archive, entries = capture_workspace(self.container)
            archive_ref = write_new(folder / "candidate" / "source.tar", archive)
            entry_ref = write_new(folder / "candidate" / "entries.json", entries)
            lock = {
                "version": VERSION, "task_id": self.row["task_id"],
                "slot_id": self.row["slot_id"], "backend_identity": self.identity,
                "source_archive": archive_ref, "entries": entry_ref,
                "candidate_export_rule": "final workspace snapshot; git metadata and caches excluded",
                "locked_before_grading": True, "evaluation_attempts_allowed": 1,
            }
            self._export = write_new(folder / "candidate" / "lock.json", lock)
            return copy.deepcopy(self._export)
        finally:
            # No further actor commands are accepted. Keeping it stopped also
            # prevents background processes mutating the exported candidate.
            self.container.unpause()
            self.container.stop(timeout=5)

    def grade_candidate(self, lock_ref):
        folder = self.run_root / "grade"
        try:
            if self._export != lock_ref:
                raise ValueError("Only this episode's once-locked candidate may be graded")
            lock = json.loads(checked(lock_ref).read_bytes())
            if lock["backend_identity"] != self.identity or not lock["locked_before_grading"]:
                raise ValueError("Candidate identity or export order changed")
            archive = checked(lock["source_archive"]).read_bytes()
            entries = json.loads(checked(lock["entries"]).read_bytes())
            # One receipt per candidate; no score-dependent re-evaluation.
            write_new(folder / "entered.json", {"candidate_lock": lock_ref})
            with container_context(self.config, self.image, role="judge") as container:
                tracked = prepare_checkout(container, self.task, self.contract, state="bug")
                explicit = self.contract["official_test_files"]
                protected = [path for path in tracked
                             if protected_path(path, self.profile, explicit)]
                # Capture original tests outside the actor-visible filesystem.
                if protected:
                    paths = " ".join(shlex.quote(path) for path in protected)
                    require_exec(container, f"tar -cf /tmp/proworksim-tests.tar -- {paths}")
                clear_exported_source(container)
                if not container.put_archive(WORKDIR, archive):
                    raise RuntimeError("Candidate source snapshot copy failed")
                # Newly introduced tests/hooks cannot replace the scoring oracle.
                new_tests = [row["path"] for row in entries
                             if protected_path(row["path"], self.profile, explicit)]
                if new_tests:
                    put_bytes(container, "/tmp/proworksim-candidate-tests.list",
                              ("\0".join(new_tests) + "\0").encode())
                    require_exec(container, "xargs -0 -r rm -f -- < /tmp/proworksim-candidate-tests.list")
                if protected:
                    require_exec(container, "tar -xf /tmp/proworksim-tests.tar -C /testbed")
                receipt = execute_official_test(
                    self.config, container, self.task, self.contract, folder / "official")
                receipt["candidate_lock"] = lock_ref
                receipt["restored_test_files"] = protected
                receipt["removed_candidate_test_files"] = new_tests
            receipt_ref = write_new(folder / "receipt.json", receipt)
            return {"R_code": receipt["R_code"], "Q": receipt["R_code"],
                    "technical_error": receipt["technical_error"], "receipt": receipt_ref}
        except Exception as error:
            unknown = {"version": VERSION, "R_code": None, "Q": None,
                       "technical_error": f"{type(error).__name__}: {error}",
                       "candidate_lock": lock_ref}
            if not (folder / "technical-error.json").exists():
                unknown["receipt"] = write_new(folder / "technical-error.json", unknown)
            else:
                unknown["receipt"] = source_ref(folder / "technical-error.json")
            return unknown

    def close(self):
        if self._context is not None:
            context, self._context = self._context, None
            context.__exit__(None, None, None)
            self.container = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def validate_backend_baseline(config, task, run_root):
    """Once-only CPU seam control: background cleanup, export and original bug R=0."""
    raw, description = load_task(config, task)
    run_root = Path(run_root)
    write_new(run_root / "entered.json", {
        "task_id": raw["instance_id"], "kind": "cpu_original_bug_backend_control",
        "model_calls": 0, "generation_tokens": 0,
    })
    row = {"task_id": raw["instance_id"], "slot_id": "cpu-original-bug-control"}
    started, controls = time.monotonic(), []
    try:
        with DockerBackend(config, description, row, run_root / "backend") as backend:
            for command in (
                'sleep 60 >/dev/null 2>&1 & printf "%s\\n" "$!"',
                'setsid sleep 60 >/dev/null 2>&1 & printf "%s\\n" "$!"',
            ):
                result = backend.execute(command, 10)
                pid = int(result["output"].strip().splitlines()[-1])
                cleanup = result["extra"].get("background_process_cleanup", {})
                passed = (
                    result["returncode"] == 0 and result["exception_info"] is None
                    and any(record["pid"] == pid for record in cleanup.get("signalled", []))
                    and cleanup.get("remaining_live_processes") == {}
                )
                controls.append({"command": command, "pid": pid, "passed": passed,
                                 "result": result})
                if not passed:
                    raise CommonSystemFault("Actor background process survived a completed command")
            final = backend.execute("true", 10)
            if (final["returncode"] != 0 or final["exception_info"]
                    or final["extra"]["background_process_cleanup"]["remaining_live_processes"]):
                raise CommonSystemFault("The trusted actor/init process was damaged by cleanup")
            candidate = backend.export_candidate(run_root / "backend")
            grade = backend.grade_candidate(candidate)
            if grade["R_code"] != 0 or grade["technical_error"]:
                raise CommonSystemFault("Original buggy candidate did not close as strict R=0")
        value = {
            "version": VERSION, "kind": "cpu_original_bug_backend_control", "passed": True,
            "task_id": raw["instance_id"], "candidate_lock": candidate, "grade": grade,
            "background_controls": controls, "model_calls": 0, "generation_tokens": 0,
            "wall_seconds": time.monotonic() - started, "additional_model_episodes": 0,
        }
    except Exception as error:
        value = {
            "version": VERSION, "kind": "cpu_original_bug_backend_control", "passed": False,
            "task_id": raw["instance_id"], "background_controls": controls,
            "technical_error": f"{type(error).__name__}: {error}",
            "model_calls": 0, "generation_tokens": 0,
            "wall_seconds": time.monotonic() - started,
        }
        write_new(run_root / "receipt.json", value)
        raise
    write_new(run_root / "receipt.json", value)
    return value
