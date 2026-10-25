"""Local-only private Python/SDK bundle for the owned v061 Docker pair.

Select installed SDK dependencies, never download packages or copy weights.
Archive extraction goes through Docker put_archive into an owned container,
with no bind mount or host namespace operation.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tarfile

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .storage import digest, json_bytes

ROOT = Path(__file__).resolve().parents[2]
SYSROOT = Path("/data0/zhuxinrui/proworksim-runtime/sysroot")
SITE = ROOT / "runs/v016-sdk/resident-venv/lib/python3.12/site-packages"
OVERLAY = ROOT / "runs/software-benchmark-v054/native-sdk-overlay"
UPSTREAM = ROOT / "runs/v016-sdk/upstream/openhands-tools"
OUTPUT = ROOT / "runs/software-benchmark-v061/sdk-bundle-r3"
CONTAINER_ROOT = "/opt/pws-runtime"
VERSION = "v061-local-native-sdk-container-bundle-r3"
SEEDS = ("openhands-sdk==1.49.6", "binaryornot", "cachetools", "libtmux", "tree-sitter",
         "tree-sitter-bash", "charset-normalizer", "requests", "setuptools", "openpyxl==3.1.5")
TOOLS = ("run_native_worker_docker_v061.py", "run_ref_budget_controller_v061.py",
         "bridge_ref_model_fifo_v061.py")
CRITICAL_MODULES = ("software_benchmark_native_worker_v054.py", "software_benchmark_native_binding_v054.py",
    "software_benchmark_native_v054.py", "software_benchmark_exact_transport_v054.py",
    "software_benchmark_ref_budget_v056.py", "software_benchmark_ref_budget_v061.py", "software_benchmark_runner_transport_v054.py",
    "software_benchmark_model_fifo_v061.py")


def distributions():
    """Resolve only installed metadata, including requested dependency extras."""
    available = {}
    for location in (OVERLAY, SITE):
        for distribution in importlib.metadata.distributions(path=[str(location)]):
            available.setdefault(canonicalize_name(distribution.metadata["Name"]), distribution)
    environment = default_environment()
    environment.update(python_version="3.12", python_full_version="3.12.3", sys_platform="linux",
                       platform_system="Linux", platform_machine="x86_64", implementation_name="cpython")
    selected, expanded, wanted = {}, {}, [Requirement(item) for item in SEEDS]
    while wanted:
        request = wanted.pop()
        name = canonicalize_name(request.name)
        if name not in available:
            raise ValueError("Missing pinned local SDK dependency: " + name)
        distribution = available[name]
        if request.specifier and distribution.version not in request.specifier:
            raise ValueError("Installed SDK dependency does not satisfy frozen metadata: " + str(request))
        extras = selected.setdefault(name, set())
        extras.update(request.extras)
        scope = frozenset(extras | {""})
        if expanded.get(name) == scope:
            continue
        expanded[name] = scope
        for text in distribution.requires or ():
            child = Requirement(text)
            if child.marker is None or any(child.marker.evaluate(environment | {"extra": extra}) for extra in scope):
                wanted.append(child)
    return {name: available[name] for name in sorted(selected)}


def wrapper_text():
    return '''#!/bin/sh
set -eu
runtime_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
export PYTHONHOME="$runtime_dir/sysroot/usr"
exec "$runtime_dir/sysroot/usr/lib64/ld-linux-x86-64.so.2" \\
  --library-path "$runtime_dir/sysroot/usr/lib/x86_64-linux-gnu:$runtime_dir/sysroot/usr/lib" \\
  --argv0 "$0" "$runtime_dir/sysroot/usr/bin/python3.12" -B -S -P "$@"
'''


def runtime_environment(prefix=CONTAINER_ROOT):
    prefix = str(prefix)
    return {"PYTHONHOME": prefix + "/sysroot/usr",
        "PYTHONPATH": ":".join(prefix + "/" + name for name in ("project/src", "overlay", "upstream-tools", "site")),
        "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONSAFEPATH": "1",
        "PATH": "/usr/bin:/bin", "HOME": "/pws/output", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "OH_PERSISTENCE_DIR": "/pws/output/empty-user-config", "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "PYTHON_DOTENV_DISABLED": "1", "HF_HUB_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1", "CUDA_VISIBLE_DEVICES": "", "NVIDIA_VISIBLE_DEVICES": "void",
        "HTTP_PROXY": "", "HTTPS_PROXY": "", "ALL_PROXY": "", "http_proxy": "", "https_proxy": "",
        "all_proxy": "", "NO_PROXY": "*", "no_proxy": "*"}


def python_argv(arguments):
    if not arguments:
        raise ValueError("Pass the fixed controller, worker or FIFO bridge script")
    return [CONTAINER_ROOT + "/bin/python", *map(str, arguments)]


def controller_inputs(original_config, new_slot_id, ready, model_identity, endpoint, *, diagnostic=False):
    """Return only public/controller files; never copy scorer or resident secrets."""
    condition_raw = checked(original_config["configuration"]).read_bytes()
    old = original_config["slot_id"]
    if not diagnostic and new_slot_id != old + ":v061-r1":
        raise ValueError("Fresh generation must retain its original slot lineage")
    public = original_config["public_task"]
    safe_identity = {key: model_identity[key] for key in (
        "model_revision", "vllm_version", "raw_release", "adapter_sha256", "model_manifest_sha256",
        "context_limit", "max_output_tokens", "service_admission_complete", "port") if key in model_identity}
    seed = original_config.get("seed")
    if seed is None:
        # Original host configs bind their seed through the frozen slot manifest.
        slots = json.loads(checked(original_config["slots"]).read_bytes())
        values = slots["slots"] if isinstance(slots, dict) else slots
        matches = [item for item in values if item.get("slot_id") == old]
        if len(matches) != 1:
            raise ValueError("Original seed cannot be recovered from one fixed slot")
        seed = matches[0]["seed"]
    config = {"version": "v061-private-native-controller-r1", "slot_id": new_slot_id,
        "original_slot_id": old, "seed": seed, "condition_id": original_config["condition_id"],
        "configuration": {"path": "/pws/control/condition.json", "sha256": digest(condition_raw), "bytes": len(condition_raw)},
        "public_task": {key: public[key] for key in ("instance_id", "repo", "base_commit", "problem_statement")},
        "ref_endpoint": endpoint, "model_identity_value": safe_identity,
        "output": "/pws/output", "start": "/pws/control/start.json", "ready": "/pws/control/actor-ready.json",
        "diagnostic": bool(diagnostic), "measurement_kind": "zero_model_diagnostic" if diagnostic else "fresh_generation_recovery"}
    return {"condition.json": condition_raw, "actor-ready.json": json_bytes(ready),
            "controller-config.json": json_bytes(config)}


def _copy_file(source, destination, *, allowed_root):
    source, destination, allowed_root = Path(source), Path(destination), Path(allowed_root).resolve()
    resolved = source.resolve(strict=True)
    if not resolved.is_relative_to(allowed_root) or not resolved.is_file():
        raise ValueError("SDK source must be an ordinary file inside its declared local package root")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != resolved.read_bytes():
            raise ValueError("Two SDK distributions provide different bytes for the same archive path")
        return
    shutil.copyfile(resolved, destination)
    destination.chmod(0o755 if resolved.stat().st_mode & 0o111 else 0o644)


def _copy_tree(source, destination, *, excluded=(), allowed_root=None):
    source = Path(source)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if any(part in {"__pycache__", ".git", *excluded} for part in relative.parts) or path.suffix == ".pyc":
            continue
        if path.is_file():
            _copy_file(path, Path(destination) / relative, allowed_root=allowed_root or source)


def _member_ok(name):
    value = PurePosixPath(name)
    return (not value.is_absolute() and ".." not in value.parts
            and (value == PurePosixPath("opt") or str(value).startswith("opt/pws-runtime/")
                 or str(value) in {"opt/pws-runtime", "pws", "pws/control", "pws/output"}))


def prepare_bundle():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("SDK packaging must be an ordinary-user file operation")
    manifest_path = OUTPUT / "manifest.json"
    if manifest_path.exists():
        result = json.loads(manifest_path.read_bytes())
        if result.get("adapter") != reference(__file__):
            raise ValueError("Prepared SDK bundle uses a different builder revision")
        checked(result["archive"])
        for source in (*result["source_tools"].values(), *result["critical_modules"].values()):
            checked(source)
        return result
    OUTPUT.mkdir(parents=True, exist_ok=False)
    stage = OUTPUT / "stage"
    runtime = stage / "opt/pws-runtime"
    runtime.mkdir(parents=True)
    (stage / "pws/control").mkdir(parents=True)
    (stage / "pws/output").mkdir(parents=True)
    for name in ("usr/bin/python3.12", "usr/lib64/ld-linux-x86-64.so.2"):
        _copy_file(SYSROOT / name, runtime / "sysroot" / name, allowed_root=SYSROOT)
    _copy_tree(SYSROOT / "usr/lib/x86_64-linux-gnu", runtime / "sysroot/usr/lib/x86_64-linux-gnu")
    _copy_tree(SYSROOT / "usr/lib/python3.12", runtime / "sysroot/usr/lib/python3.12",
               excluded=("ensurepip", "site-packages", "dist-packages"), allowed_root=SYSROOT)
    selected = distributions()
    inventory = []
    for name, dist in selected.items():
        root = Path(dist.locate_file("")).resolve()
        if root not in {SITE.resolve(), OVERLAY.resolve()}:
            raise ValueError("Unexpected installed distribution root")
        for item in dist.files or ():
            relative = PurePosixPath(str(item))
            if relative.is_absolute() or ".." in relative.parts:
                continue  # Distribution command wrappers are not needed by the SDK.
            if "__pycache__" in relative.parts or relative.suffix == ".pyc":
                continue
            source = Path(dist.locate_file(item))
            if source.is_file():
                _copy_file(source, runtime / "site" / str(relative), allowed_root=root)
        inventory.append({"name": name, "version": dist.version})
    _copy_tree(OVERLAY, runtime / "overlay")
    _copy_tree(UPSTREAM / "openhands", runtime / "upstream-tools/openhands")
    _copy_tree(ROOT / "src/proworksim", runtime / "project/src/proworksim")
    for name in TOOLS:
        _copy_file(ROOT / "tools" / name, runtime / "project/tools" / name, allowed_root=ROOT / "tools")
    original_sources = {**{"tools/" + name: reference(ROOT / "tools" / name) for name in TOOLS},
                        **{"src/proworksim/" + name: reference(ROOT / "src/proworksim" / name) for name in CRITICAL_MODULES}}
    for name, original in original_sources.items():
        copied = reference(runtime / "project" / name)
        if any(copied[k] != original[k] for k in ("bytes", "sha256")):
            raise ValueError("Controller/worker source changed while constructing the private bundle")
    wrapper = runtime / "bin/python"
    wrapper.parent.mkdir()
    wrapper.write_text(wrapper_text())
    wrapper.chmod(0o755)
    probe = """import importlib.metadata,json,sys
def no_network(event,args):
    if event in {'socket.connect','socket.bind','socket.getaddrinfo'}:
        raise RuntimeError('Network forbidden during SDK-only CPU qualification')
sys.addaudithook(no_network)
from proworksim.software_benchmark_native_worker_v054 import preload
from proworksim.software_benchmark_ref_budget_v061 import RecoveryBudgetRefAdapter
from openhands.sdk import Conversation
classes, definitions, sources, schemas = preload()
print(json.dumps({'sdk_version':importlib.metadata.version('openhands-sdk'),'python':sys.version,'tools':sorted(classes),'python_executable':sys.executable,'model_calls':0,'tool_calls':0}))
"""
    env = runtime_environment(runtime)
    env["HOME"] = str(OUTPUT / "probe-home")
    Path(env["HOME"]).mkdir()
    env["OH_PERSISTENCE_DIR"] = str(OUTPUT / "probe-home/empty-user-config")
    completed = subprocess.run([str(wrapper), "-c", probe], env=env, cwd=OUTPUT,
                               capture_output=True, timeout=120, check=False)
    write_new(OUTPUT / "probe-stdout.txt", completed.stdout)
    write_new(OUTPUT / "probe-stderr.txt", completed.stderr)
    if completed.returncode:
        raise RuntimeError("Private SDK bundle import/preload failed; retained probe stderr")
    probe_result = json.loads(completed.stdout)
    if probe_result.get("sdk_version") != "1.49.6" or probe_result.get("tools") != ["file_editor", "task_tracker", "terminal"]:
        raise ValueError("Private bundle changed the pinned SDK/tools")
    members = []
    archive_path = OUTPUT / "runtime.tar.gz"
    with tarfile.open(archive_path, "w:gz", compresslevel=1) as archive:
        for path in sorted(stage.rglob("*")):
            name = path.relative_to(stage).as_posix()
            if not _member_ok(name) or path.is_symlink():
                raise ValueError("Unsafe private SDK archive member")
            info = archive.gettarinfo(str(path), arcname=name)
            if not (info.isfile() or info.isdir()):
                raise ValueError("Only regular files and directories belong in this runtime archive")
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = stat.S_IMODE(info.mode) & 0o755
            if info.isfile():
                with path.open("rb") as handle:
                    archive.addfile(info, handle)
                members.append({"path": name, "bytes": info.size})
            else:
                archive.addfile(info)
    manifest = {"version": VERSION, "adapter": reference(__file__), "archive": reference(archive_path),
        "container_root": CONTAINER_ROOT, "archive_destination": "/", "distributions": inventory,
        "files": len(members), "uncompressed_file_bytes": sum(m["bytes"] for m in members),
        "member_inventory": write_new(OUTPUT / "members.json", members), "probe": probe_result,
        "source_tools": {name: reference(ROOT / "tools" / name) for name in TOOLS},
        "critical_modules": {name: reference(ROOT / "src/proworksim" / name) for name in CRITICAL_MODULES},
        "models_or_weights_included": False, "downloaded_packages": 0,
        "host_mount_or_namespace_operations": False, "cpu_preload_only": True}
    write_new(manifest_path, manifest)
    return manifest
