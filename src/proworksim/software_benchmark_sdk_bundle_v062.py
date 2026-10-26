"""Local-only private Python/SDK bundle for the owned v062 Docker pair.

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
OUTPUT = ROOT / "runs/software-benchmark-v062/sdk-bundle-r1"
CONTAINER_ROOT = "/opt/pws-runtime"
VERSION = "v062-local-native-sdk-container-bundle-r1"
SEEDS = ("openhands-sdk==1.49.6", "binaryornot", "cachetools", "libtmux", "tree-sitter",
         "tree-sitter-bash", "charset-normalizer", "requests", "setuptools", "openpyxl==3.1.5")
TOOLS = ("run_native_worker_docker_v062.py", "run_ref_controller_v062.py",
         "bridge_ref_model_fifo_v062.py")
CRITICAL_MODULES = ("software_benchmark_native_worker_v054.py", "software_benchmark_native_binding_v054.py",
    "software_benchmark_native_v054.py", "software_benchmark_exact_transport_v054.py",
    "software_benchmark_ref_budget_v056.py", "software_benchmark_ref_budget_v062.py", "software_benchmark_runner_transport_v054.py",
    "software_benchmark_model_fifo_v062.py", "software_benchmark_exact_transport_v057.py",
    "software_benchmark_native_execution_v057.py", "software_benchmark_native_control_v062.py",
    "software_benchmark_public_context_v062.py")
PROJECT_MODULES = tuple(sorted(set(CRITICAL_MODULES) | {
    "storage.py", "repository_sources_v054.py", "software_benchmark_candidates_v054.py",
    "software_benchmark_match_v054.py", "software_benchmark_owner_ipc_v054.py",
    "software_benchmark_normal_boundary_v054.py", "software_benchmark_supervision_v054.py",
    "software_benchmark_ref_deployment_v054.py",
}))
PACKAGE_INITIALIZER = '''"""Private v062 native runtime; no project worlds, training or scoring imports."""
__version__ = "0.12.0"
'''
NATIVE_SCHEMA_SOURCE = ROOT / ("runs/software-benchmark-v056/episodes/"
    "6d3849656aa3d6c683050ae41d11d5c607a7ea89713cb16bfc5f5d40d4fab15f/worker-ready.json")


def probe_source():
    return '''import importlib.metadata, importlib.util, json, os, sys
from pathlib import Path
runtime, output = Path(sys.argv[1]), Path.cwd()
counts = {"network": 0, "gpu": 0, "weights": 0, "model": 0, "tools": 0}
def audit(event, args):
    if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"}:
        counts["network"] += 1
        raise RuntimeError("No network in private runtime CPU control")
    if event == "open" and args and isinstance(args[0], (str, bytes)):
        path = os.fsdecode(args[0])
        if path.startswith(("/dev/nvidia", "/dev/dri/")):
            counts["gpu"] += 1
            raise RuntimeError("No GPU in private runtime CPU control")
        if path.endswith((".safetensors", ".gguf")) or "pytorch_model" in path:
            counts["weights"] += 1
            raise RuntimeError("No weights in private runtime CPU control")
sys.addaudithook(audit)
def tool_module(name):
    path = runtime / "project/tools" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value
controller = tool_module("run_ref_controller_v062")
worker = tool_module("run_native_worker_docker_v062")
tool_module("bridge_ref_model_fifo_v062")
from proworksim.software_benchmark_native_worker_v054 import preload
from proworksim.software_benchmark_ref_budget_v062 import CapabilityBudgetRefAdapter
from proworksim.software_benchmark_model_fifo_v062 import FifoModelTransport
from proworksim.software_benchmark_runner_transport_v054 import GuardedRefAdapter, HostDeadline
from proworksim.software_benchmark_normal_boundary_v054 import unwrap_normal_boundary
from proworksim.software_benchmark_native_binding_v054 import build_isolated_agent
from proworksim.software_benchmark_exact_transport_v054 import build_llm
from proworksim.software_benchmark_native_v054 import initialized_interface_manifest
from openhands.sdk import Conversation
classes, definitions, sources, schemas = preload()
ready = json.loads((output / "probe-native-interface.json").read_bytes())
class Adapter:
    maximum_input_tokens = 98304
    maximum_output_tokens = 32768
    temperature = .6
    def count(self, *args, **kwargs):
        counts["model"] += 1
        raise RuntimeError("No inference in private runtime CPU control")
    complete = count
class RPC:
    def __init__(self, name):
        self._bound, self.session_id, self.ready = False, "v062_bundle_" + name, ready
    def request(self, *args, **kwargs):
        counts["tools"] += 1
        raise RuntimeError("No tools execute in private runtime CPU control")
workspace = output / "probe-workspace"
workspace.mkdir()
manifests = {}
for arm in ("frozen_v054", "BASE5M", "FIX5M"):
    adapter, rpc = Adapter(), RPC(arm)
    folder = output / ("factory-" + arm)
    if arm == "frozen_v054":
        conversation = Conversation(agent=build_isolated_agent(build_llm(adapter), rpc=rpc),
            workspace=workspace, persistence_dir=folder / "native-conversation", plugins=[],
            max_iteration_per_run=512, stuck_detection=True, visualizer=None, delete_on_close=False)
    else:
        conversation = controller.create_conversation({"execution_arm": arm}, adapter, rpc,
            folder, {"agent_decisions": 512}, workspace=workspace)
    try:
        conversation.send_message("Synthetic production-factory CPU control. Do not run inference.")
        manifests[arm] = initialized_interface_manifest(conversation.agent)
        assert conversation.max_iteration_per_run == 512
        if arm != "FIX5M":
            assert conversation.agent.llm._adapter is adapter
        else:
            assert conversation.agent.llm._adapter is adapter._v057_projection_guard
    finally:
        conversation.close()
assert manifests["BASE5M"] == manifests["frozen_v054"]
assert manifests["FIX5M"]["tool_schemas"] == manifests["BASE5M"]["tool_schemas"]
assert sorted(manifests["BASE5M"]["tool_schemas"]) == ["file_editor", "finish", "task_tracker", "terminal", "think"]
loaded = []
for name, module in sys.modules.items():
    if name == "proworksim" or name.startswith("proworksim."):
        source = Path(module.__file__).resolve()
        loaded.append(str(source.relative_to(runtime / "project/src/proworksim")))
assert "evaluation.py" not in loaded and not any("scorer" in name for name in loaded)
assert not any(counts.values())
print(json.dumps({"sdk_version": importlib.metadata.version("openhands-sdk"), "python": sys.version,
    "tools": sorted(classes), "python_executable": sys.executable,
    "model_calls": 0, "tool_calls": 0, "forbidden_operation_counts": counts,
    "base_production_factory_equals_frozen_v054": True, "fixed_five_tool_schemas_equal_base": True,
    "actual_worker_preload": True, "controller_and_worker_entry_imported": True,
    "minimal_namespace_only": True, "loaded_project_modules": sorted(loaded),
    "interfaces": manifests}))
'''


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


def controller_inputs(host_config, row, ready, model_identity, endpoint, *, diagnostic=False,
                      public_context=None, public_environment=None):
    """Return only public/controller files; never copy scorer or resident secrets."""
    condition_raw = checked(host_config["configuration"]).read_bytes()
    if (not row["slot_id"].startswith("v062:")
            or any(host_config.get(key) != row[key] for key in
                   ("slot_id", "seed", "execution_arm", "source_slot_id", "condition_id"))
            or row["execution_arm"] not in {"BASE5M", "FIX5M", "FIX10M"}):
        raise ValueError("Controller inputs must bind one exact new BASE or FIX slot")
    public = host_config["public_task"]
    safe_identity = {key: model_identity[key] for key in (
        "model_revision", "vllm_version", "raw_release", "adapter_sha256", "model_manifest_sha256",
        "context_limit", "max_output_tokens", "service_admission_complete", "port", "deployment_version") if key in model_identity}
    config = {"version": "v062-private-native-controller-r1", "slot_id": row["slot_id"],
        "source_slot_id": row["source_slot_id"], "seed": row["seed"],
        "condition_id": row["condition_id"], "execution_arm": row["execution_arm"],
        "configuration": {"path": "/pws/control/condition.json", "sha256": digest(condition_raw), "bytes": len(condition_raw)},
        "public_task": {key: public[key] for key in ("instance_id", "repo", "base_commit", "problem_statement")},
        "ref_endpoint": endpoint, "model_identity_value": safe_identity,
        "output": "/pws/output", "start": "/pws/control/start.json", "ready": "/pws/control/actor-ready.json",
        "diagnostic": bool(diagnostic), "measurement_kind": "zero_model_diagnostic" if diagnostic else "capability_probe"}
    if row["execution_arm"] != "BASE5M":
        from .software_benchmark_public_context_v062 import VERSION as CONTEXT_VERSION, terminal_initialization_action
        if (not isinstance(public_context, dict) or public_context.get("version") != CONTEXT_VERSION
                or public_context.get("instance_id") != row["instance_id"]):
            raise ValueError("FIX requires separately admitted public context for this task")
        terminal_initialization_action(public_environment)
        config["public_context"] = {key: public_context[key] for key in
                                    ("version", "visible_text", "visible_facts")}
        config["public_environment"] = {key: public_environment[key] for key in
                                       ("kind", "image_id", "source_config_sha256", "public_python")}
        config["public_environment"]["environment"] = {key: public_environment["environment"][key]
            for key in ("PATH", "CONDA_PREFIX", "CONDA_DEFAULT_ENV") if key in public_environment["environment"]}
    elif public_context is not None:
        raise ValueError("BASE must retain its original public input without FIX additions")
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
        for source in (*result["source_tools"].values(), *result["project_modules"].values()):
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
    # An explicit private namespace avoids importing unrelated business-world
    # evaluation through the repository package's public __init__. Native source
    # bytes remain identical, and both controller factories are qualified below.
    package = runtime / "project/src/proworksim"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(PACKAGE_INITIALIZER)
    for name in PROJECT_MODULES:
        _copy_file(ROOT / "src/proworksim" / name, package / name, allowed_root=ROOT / "src/proworksim")
    for name in TOOLS:
        _copy_file(ROOT / "tools" / name, runtime / "project/tools" / name, allowed_root=ROOT / "tools")
    original_sources = {**{"tools/" + name: reference(ROOT / "tools" / name) for name in TOOLS},
                        **{"src/proworksim/" + name: reference(ROOT / "src/proworksim" / name) for name in PROJECT_MODULES}}
    for name, original in original_sources.items():
        copied = reference(runtime / "project" / name)
        if any(copied[k] != original[k] for k in ("bytes", "sha256")):
            raise ValueError("Controller/worker source changed while constructing the private bundle")
    wrapper = runtime / "bin/python"
    wrapper.parent.mkdir()
    wrapper.write_text(wrapper_text())
    wrapper.chmod(0o755)
    original_ready = json.loads(NATIVE_SCHEMA_SOURCE.read_bytes())
    write_new(OUTPUT / "probe-native-interface.json", {key: original_ready[key]
              for key in ("vision_enabled", "tool_definitions")})
    write_new(OUTPUT / "probe-source.py", probe_source().encode())
    env = runtime_environment(runtime)
    env["HOME"] = str(OUTPUT / "probe-home")
    Path(env["HOME"]).mkdir()
    env["OH_PERSISTENCE_DIR"] = str(OUTPUT / "probe-home/empty-user-config")
    completed = subprocess.run([str(wrapper), str(OUTPUT / "probe-source.py"), str(runtime)], env=env, cwd=OUTPUT,
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
        "probe_source": reference(OUTPUT / "probe-source.py"),
        "public_native_schema_source": reference(NATIVE_SCHEMA_SOURCE),
        "source_tools": {name: reference(ROOT / "tools" / name) for name in TOOLS},
        "critical_modules": {name: reference(ROOT / "src/proworksim" / name) for name in CRITICAL_MODULES},
        "project_modules": {name: reference(ROOT / "src/proworksim" / name) for name in PROJECT_MODULES},
        "private_package_initializer": {"sha256": digest(PACKAGE_INITIALIZER.encode()),
            "purpose": "native imports only; omit unrelated world and evaluation package initialization"},
        "benchmark_scorer_or_gold_modules_included": False, "host_key_files_included": False,
        "models_or_weights_included": False, "downloaded_packages": 0,
        "host_mount_or_namespace_operations": False, "cpu_preload_only": True}
    write_new(manifest_path, manifest)
    return manifest
