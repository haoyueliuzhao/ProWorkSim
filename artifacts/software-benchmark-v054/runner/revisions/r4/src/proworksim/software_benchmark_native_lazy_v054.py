"""Prepare one exact task runtime before any formal slot/model is claimed.

No model is loaded. Qualified immutable templates are reused across conditions;
every episode and public test still receives its own complete rootfs clone.
"""
from __future__ import annotations

import fcntl
import json
from pathlib import Path
import selectors
import subprocess
import time
import uuid

from .software_benchmark_actor_v054 import ActorDocker, checked_public_task
from .software_benchmark_baseline_v054 import validate_mapping
from .software_benchmark_native_rootfs_v054 import canonical, clone_prepared_rootfs, prepare_rootfs
from .software_benchmark_resources_v054 import create_episode_resources, release_episode_resources
from .software_benchmark_scorer_v054 import checked_file, file_reference
from .software_benchmark_supervision_v054 import launch_owned, stop_owned

ROOT = Path(__file__).resolve().parents[2]
MECHANISM = ROOT / "artifacts/software-benchmark-v054/native-environment/real-image-control-r2.json"


def environment_from_mapping(task, mapping_reference):
    task = checked_public_task(task)
    mapping = json.loads(checked_file(mapping_reference).read_bytes())
    validate_mapping(mapping, instance=task, image={
        "image_id": mapping["official_image_id"], "manifest_digest": mapping["official_manifest_digest"]})
    if task["image"] != mapping["official_image_name"]:
        raise ValueError("Public task image differs from the final baseline mapping")
    return {
        "version": "software-benchmark-actor-v054-r3", "task": task,
        "baseline_mapping": mapping_reference,
        "image": {"image_id": mapping["actor_image_id"],
                  "config_digest": mapping["actor_config_digest"], "manifest_digest": None,
                  "platform": mapping["platform"], "source": "local_derived_actor_image",
                  "official_source_manifest_digest": mapping["official_manifest_digest"]},
        "actor_head": mapping["actor_head"], "actor_tree": mapping["actor_tree"],
        "public_python": mapping["public_python"], "runtime_version": mapping["runtime_version"],
        "limits": {"network": "none", "cpus": 4, "memory_bytes": 16 * 1024**3,
                   "pids_limit": 16384, "public_test_timeout_seconds": 1800},
        "official_grading_image_modified": False,
    }, mapping


def _frame(reader, seconds=90):
    data, deadline = bytearray(), time.monotonic() + seconds
    import os
    with selectors.DefaultSelector() as selector:
        selector.register(reader.fileno(), selectors.EVENT_READ)
        while time.monotonic() < deadline:
            if not selector.select(max(0, deadline - time.monotonic())):
                break
            block = os.read(reader.fileno(), 65536)
            if not block:
                raise RuntimeError("Instance initializer exited before a complete frame")
            data.extend(block)
            if b"\n" in data:
                return json.loads(data.split(b"\n", 1)[0])
            if len(data) > 32 * 1024**2:
                raise ValueError("Initializer frame exceeds its finite control bound")
    raise TimeoutError("Instance initialization exceeded its finite CPU deadline")


def _mechanism():
    proof = json.loads(MECHANISM.read_bytes())
    if (proof.get("passed") is not True or proof.get("model_calls") != 0
            or proof["ready"]["isolation"]["capabilities_all_zero"] is not True
            or proof["resource_slice"]["kernel_limits"] != {
                "cpu.max": "400000 100000", "memory.max": "17179869184", "pids.max": "16384"}):
        raise ValueError("Shared native UID/tool/resource mechanism has not passed")
    # Reuse only the exact mechanism whose real-image control was recorded.
    for frozen in proof["sources"]:
        checked_file(frozen)
    return file_reference(MECHANISM)


def qualify_instance(environment, root, stdlib, inherited):
    """One public initialization per task; do not repeat the full UID/tool suite."""
    directory = root / "initialization"
    directory.mkdir(exist_ok=False)
    resources = process = scope = None
    result = {"version": "v054-native-instance-initialization-v1", "passed": False,
              "instance_id": environment["task"]["instance_id"], "baseline_mapping": environment["baseline_mapping"],
              "inherited_mechanism_control": inherited, "model_calls": 0, "slot_claimed": False,
              "benchmark_tests_run": 0, "hidden_grader_called": False}
    try:
        clone = clone_prepared_rootfs(root / "public-environment.json", directory / "clone")
        resources = create_episode_resources(uuid.uuid4().hex, directory)
        process, scope = launch_owned([
            ROOT / "tools/run_native_worker_mapped_v054.sh", "--rootfs", clone["rootfs"],
            "--stdlib", str(Path(stdlib).resolve()), "--environment-manifest", clone["environment_manifest"],
            "--preparation-only"], claim_id=resources["claim_id"], role="initializer",
            resources=resources, runtime_seconds=180, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=(directory / "stderr.log").open("xb"))
        ready = _frame(process.stdout)
        if ready.get("type") != "ready":
            raise RuntimeError("Instance worker did not initialize: " + str(ready))
        version = environment["runtime_version"]
        expected = {"head": environment["actor_head"], "tree": environment["actor_tree"],
                    "python": environment["public_python"], "module": version["module"],
                    "version": version["actor"]["version"]}
        code = (
            "import importlib,json,os,subprocess,sys\n"
            "expected=" + repr(expected) + "\n"
            "assert sys.executable==expected['python']\n"
            "module=importlib.import_module(expected['module'])\n"
            "observed_version=str(getattr(module,'__version__','unknown'))\n"
            "assert observed_version==expected['version'],(observed_version,expected['version'])\n"
            "module_file=os.path.realpath(module.__file__)\n"
            "assert module_file.startswith('/testbed/'),module_file\n"
            "git=subprocess.check_output(['git','-C','/testbed','rev-parse','HEAD','HEAD^{tree}'],text=True).splitlines()\n"
            "assert git==[expected['head'],expected['tree']],git\n"
            "assert os.getuid()==0 and os.getgid()==0\n"
            "print(json.dumps({'python':sys.executable,'version':observed_version,'module_file':module_file,'git':git}))\n")
        action = {"id": 1, "tool": "terminal", "action": {
            "command": "PYTHONDONTWRITEBYTECODE=1 python - <<'PWS_PUBLIC_INITIALIZATION'\n" + code + "PWS_PUBLIC_INITIALIZATION",
            "timeout": 60}}
        process.stdin.write((json.dumps(action) + "\n").encode())
        process.stdin.flush()
        response = _frame(process.stdout)
        if (response.get("type") != "observation" or response.get("id") != 1
                or response["observation"].get("exit_code") != 0):
            raise RuntimeError("Public interpreter/tree/version initialization failed: " + str(response))
        process.stdin.write(b'{"id":2,"op":"close"}\n')
        process.stdin.flush()
        closed = _frame(process.stdout, 20)
        if closed.get("official_terminal_close_returned") is not True or process.wait(timeout=30) != 0:
            raise RuntimeError("Instance initializer did not close cleanly")
        result.update(passed=True, expected=expected, ready=ready,
                      public_initialization=response["observation"], resources=resources,
                      quiescence=stop_owned(scope))
    except BaseException as error:
        result.update(error_type=type(error).__name__, error=str(error))
    finally:
        if scope is not None:
            try:
                result["quiescence"] = stop_owned(scope)
            except Exception as error:
                result.update(passed=False, cleanup_error=str(error))
        if process is not None:
            process.wait(timeout=35)
        if resources is not None:
            result["resource_release"] = release_episode_resources(resources)
        temporary_root = directory / "clone/rootfs"
        if temporary_root.exists() and result.get("quiescence", {}).get("populated") is False:
            # All task processes and private mounts have gone. Keep metadata and
            # CPU evidence, not another multi-GB copy of the immutable template.
            if not temporary_root.resolve().is_relative_to(ROOT / "runs/software-benchmark-v054"):
                raise ValueError("Unexpected temporary initializer root")
            subprocess.run(["sudo", "-n", "/bin/rm", "-rf", "--", str(temporary_root)], check=True)
            result["temporary_rootfs_removed_after_quiescence"] = True
        (directory / "receipt.json").write_bytes(canonical(result))
    if not result["passed"]:
        raise RuntimeError("Instance preparation remains unqualified; no formal slot/model claimed")
    return file_reference(directory / "receipt.json")


def ensure_native_instance(instance_id, *, mapping_reference, cache_root, stdlib,
                           public_tasks_reference, docker_socket):
    """Return absolute paths only after this exact task's real initialization."""
    rows = json.loads(checked_file(public_tasks_reference).read_bytes())
    if len(rows) != 500 or len({row["instance_id"] for row in rows}) != 500:
        raise ValueError("The fixed full 500-task public projection is required")
    task = next(row for row in rows if row["instance_id"] == instance_id)
    environment, mapping = environment_from_mapping(task, mapping_reference)
    if mapping["instance_id"] != instance_id:
        raise ValueError("Lazy mapping belongs to another task")
    cache_root = Path(cache_root).resolve()
    if not cache_root.is_relative_to(ROOT / "runs/software-benchmark-v054"):
        raise ValueError("Native cache must remain within the dedicated project preparation directory")
    inherited = _mechanism()
    locks = cache_root / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    root = cache_root / instance_id / mapping_reference["sha256"][:16]
    with (locks / (instance_id + ".lock")).open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ready_path = root / "lazy-preparation.json"
        if ready_path.exists():
            receipt = json.loads(ready_path.read_bytes())
            if receipt["baseline_mapping"] != mapping_reference or receipt.get("status") != "qualified":
                raise ValueError("Cached native preparation differs from the frozen task")
            for key in ("rootfs_environment", "rootfs_manifest", "environment", "qualification"):
                checked_file(receipt[key])
            return {key: receipt[key]["path"] for key in (
                "rootfs_environment", "rootfs_manifest", "environment", "qualification")}
        if root.exists():
            raise RuntimeError("An incomplete preparation is retained; repair explicitly before claiming a slot")
        try:
            manifest_path = prepare_rootfs(
                environment=environment, controller=ActorDocker(docker_socket),
                config_blob=mapping["actor_config_blob"], destination=root,
                preserve_numeric_ownership=True)
            (root / "environment.json").write_bytes(canonical(environment))
            qualification = qualify_instance(environment, root, stdlib, inherited)
            manifest = json.loads(manifest_path.read_bytes())
            (root / "rootfs-manifest-before-initialization.json").write_bytes(manifest_path.read_bytes())
            manifest.update(native_real_task_control_passed=True, native_control_receipt=qualification,
                            qualification_scope="per_instance_public_runtime_plus_shared_mechanism")
            manifest_path.write_bytes(canonical(manifest))
            public_path = root / "public-environment.json"
            public = json.loads(public_path.read_bytes())
            public["rootfs_manifest_sha256"] = file_reference(manifest_path)["sha256"]
            public_path.write_bytes(canonical(public))
            receipt = {"version": "v054-lazy-native-preparation-v1", "status": "qualified",
                       "baseline_mapping": mapping_reference, "slot_claimed": False, "model_calls": 0,
                       "rootfs_environment": file_reference(public_path),
                       "rootfs_manifest": file_reference(manifest_path),
                       "environment": file_reference(root / "environment.json"), "qualification": qualification}
            ready_path.write_bytes(canonical(receipt))
        except BaseException as error:
            if root.exists():
                (root / "preparation-failure.json").write_bytes(canonical({
                    "status": "preparation_not_ready", "instance_id": instance_id,
                    "slot_claimed": False, "model_calls": 0, "error_type": type(error).__name__,
                    "error": str(error), "baseline_mapping": mapping_reference}))
            raise
        return {key: receipt[key]["path"] for key in (
            "rootfs_environment", "rootfs_manifest", "environment", "qualification")}
