"""Local-only SDK and explicit managed-runtime bundle for the v064 Docker pair.

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
OUTPUT = ROOT / "runs/software-benchmark-v064/sdk-bundle-r2"
CONTAINER_ROOT = "/opt/pws-runtime"
VERSION = "v064-local-ref-project-sdk-container-bundle-r2"
SEEDS = ("openhands-sdk==1.49.6", "binaryornot", "cachetools", "libtmux", "tree-sitter",
         "tree-sitter-bash", "charset-normalizer", "requests", "setuptools", "openpyxl==3.1.5")
TOOLS = ("run_native_worker_docker_v064.py", "run_ref_controller_v064.py",
         "bridge_ref_model_fifo_v064.py", "run_project_controller_v064.py",
         "run_managed_worker_docker_v064.py")
ENTRYPOINT_ALIASES = {
    "worker.py": "run_native_worker_docker_v064.py",
    "controller.py": "run_ref_controller_v064.py",
    "managed-worker.py": "run_managed_worker_docker_v064.py",
    "project-controller.py": "run_project_controller_v064.py",
}
CRITICAL_MODULES = ("software_benchmark_native_worker_v054.py", "software_benchmark_native_binding_v054.py",
    "software_benchmark_native_v054.py", "software_benchmark_exact_transport_v054.py",
    "software_benchmark_ref_budget_v056.py", "software_benchmark_ref_budget_v064.py", "software_benchmark_runner_transport_v054.py",
    "software_benchmark_model_fifo_v064.py", "software_benchmark_exact_transport_v057.py",
    "software_benchmark_native_execution_v057.py", "software_benchmark_native_control_v062.py",
    "software_benchmark_public_context_v062.py")
# Explicit transitive runtime modules observed under a minimal package initializer.
# Internal evaluation.py contains generic project record boundaries, not the
# SWE-bench harness or reference tests. No model updater or provider-key module.
MANAGED_MODULES = (
    "adapters/__init__.py",
    "adapters/capabilities.py",
    "adapters/locations.py",
    "audit.py",
    "basis.py",
    "contracts.py",
    "core/__init__.py",
    "core/adoption.py",
    "core/conditions.py",
    "core/issues.py",
    "core/journal.py",
    "core/maintenance.py",
    "core/projections.py",
    "core/publication.py",
    "core/references.py",
    "core/rules.py",
    "core/runner.py",
    "core/transitions.py",
    "core/types.py",
    "core/visibility.py",
    "core/work.py",
    "core/world.py",
    "domains/__init__.py",
    "domains/decision_team.py",
    "domains/executable_project.py",
    "domains/operating_toy.py",
    "domains/reconciliation.py",
    "domains/research_review.py",
    "domains/retail_projects.py",
    "domains/retail_work.py",
    "domains/work_product.py",
    "episode.py",
    "evaluation.py",
    "experience.py",
    "format_diagnostics.py",
    "formula.py",
    "harness_policy_v040.py",
    "harness_port.py",
    "harness_runtime.py",
    "harness_sdk.py",
    "information_mapper.py",
    "lifecycle.py",
    "member_views.py",
    "model_policy.py",
    "model_transport.py",
    "online_collection.py",
    "online_support.py",
    "policies/__init__.py",
    "policies/organization.py",
    "presentations.py",
    "repository_sources_v054.py",
    "scenarios.py",
    "schema.py",
    "software_acceptance.py",
    "software_benchmark_candidates_v054.py",
    "software_benchmark_deepseek_adapter_v064.py",
    "software_benchmark_deepseek_contract_v064.py",
    "software_benchmark_deepseek_interfaces_v055.py",
    "software_benchmark_deepseek_prefix_v055_r2.py",
    "software_benchmark_exact_transport_v054.py",
    "software_benchmark_exact_transport_v057.py",
    "software_benchmark_full_plan_v064.py",
    "software_benchmark_managed_v064.py",
    "software_benchmark_managed_worker_v056.py",
    "software_benchmark_match_v054.py",
    "software_benchmark_normal_boundary_v064.py",
    "software_benchmark_ref_budget_v056.py",
    "software_benchmark_ref_budget_v064.py",
    "software_benchmark_state_cache_v054.py",
    "software_benchmark_world_v054.py",
    "software_benchmark_world_v056.py",
    "software_benchmark_world_v064.py",
    "software_calibration_collector_v051.py",
    "software_calibration_world_v051.py",
    "software_collaboration_v027.py",
    "software_collaboration_v028.py",
    "software_collaboration_v029.py",
    "software_collaboration_v030.py",
    "software_collaboration_v033.py",
    "software_collaboration_v036.py",
    "software_context_v028.py",
    "software_context_v034.py",
    "software_context_v041.py",
    "software_context_v042.py",
    "software_context_v044.py",
    "software_context_v048.py",
    "software_feedback_v044.py",
    "software_member_tests_v036.py",
    "software_organization_runtime_v038.py",
    "software_organization_runtime_v039.py",
    "software_organization_runtime_v040.py",
    "software_organization_runtime_v041.py",
    "software_organization_runtime_v042.py",
    "software_organization_runtime_v044.py",
    "software_organization_runtime_v045.py",
    "software_organization_runtime_v047.py",
    "software_organization_tasks_v038.py",
    "software_organization_tasks_v039.py",
    "software_organization_tasks_v040.py",
    "software_organization_tasks_v045.py",
    "software_organization_v038.py",
    "software_organization_v039.py",
    "software_organization_v040.py",
    "software_organization_v042.py",
    "software_organization_v045.py",
    "software_runtime_v033.py",
    "software_sandbox.py",
    "software_sources_v027.py",
    "software_tasks_v028.py",
    "software_tasks_v030.py",
    "software_tasks_v034.py",
    "software_tasks_v035.py",
    "software_tasks_v036.py",
    "spreadsheet.py",
    "staff_runtime.py",
    "stage_budget_v047.py",
    "storage.py",
    "support_weights.py",
    "team_budget_v033.py",
    "team_rollout.py",
    "templates/__init__.py",
    "templates/decision_team.py",
    "templates/online_work.py",
    "templates/public_formats.py",
    "templates/reconciliation.py",
    "templates/research_review.py",
    "templates/software_maintenance.py",
    "tool_outcomes.py",
    "work_interface.py",
    "world_core.py",
    "software_benchmark_managed_actor_v064.py",
    "software_benchmark_gitlinks_v054.py",
    "software_benchmark_project_closure_v064.py",
)
PROJECT_MODULES = tuple(sorted(set(CRITICAL_MODULES) | set(MANAGED_MODULES) | {
    "storage.py", "repository_sources_v054.py", "software_benchmark_candidates_v054.py",
    "software_benchmark_match_v054.py", "software_benchmark_owner_ipc_v054.py",
    "software_benchmark_normal_boundary_v054.py", "software_benchmark_supervision_v054.py",
    "software_benchmark_ref_deployment_v054.py", "software_benchmark_normal_boundary_v064.py",
}))
PACKAGE_INITIALIZER = '''"""Private v064 REF/PROJECT runtime; no benchmark scoring or training entrypoint."""
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
controller = tool_module("run_ref_controller_v064")
tool_module("run_native_worker_docker_v064")
tool_module("bridge_ref_model_fifo_v064")
tool_module("run_project_controller_v064")
tool_module("run_managed_worker_docker_v064")
from proworksim.software_benchmark_native_worker_v054 import preload
from proworksim.software_benchmark_ref_budget_v064 import PairedQwenAdapter
from proworksim.software_benchmark_model_fifo_v064 import FifoModelTransport
from proworksim.software_benchmark_managed_v064 import worker_type
from proworksim.software_benchmark_managed_actor_v064 import validate_public_entry
from proworksim.software_benchmark_project_closure_v064 import export_managed_closure
from proworksim.software_benchmark_normal_boundary_v064 import GuardedModelAdapter
from proworksim.software_benchmark_native_v054 import initialized_interface_manifest
from proworksim.software_benchmark_deepseek_adapter_v064 import build_native_llm
from proworksim.software_benchmark_exact_transport_v057 import ResponseProjectionFault, ResponseNormalizationError
from openhands.sdk.llm import Message, TextContent
classes, definitions, sources, schemas = preload()
managed_class = worker_type()
ready = json.loads((output / "probe-native-interface.json").read_bytes())
class Adapter:
    maximum_input_tokens, maximum_output_tokens, temperature = 98304, 32768, .6
    thinking, model = True, "deepseek-flash"
    def count(self, *args, **kwargs):
        counts["model"] += 1
        raise RuntimeError("No real inference/count backend in private runtime CPU control")
    complete = count
class RPC:
    def __init__(self, name):
        self._bound, self.session_id, self.ready = False, "v064_bundle_" + name, ready
    def request(self, *args, **kwargs):
        counts["tools"] += 1
        raise RuntimeError("No tools execute in private runtime CPU control")
workspace = output / "probe-workspace"
workspace.mkdir()
manifests = {}
for model in ("QWEN", "DEEPSEEK"):
    adapter, rpc = Adapter(), RPC(model)
    conversation = controller.create_conversation({"model_key": model, "execution_arm": "REF"},
        adapter, rpc, output / ("factory-" + model), {"agent_decisions": 512}, workspace=workspace)
    try:
        conversation.send_message("Synthetic production-factory CPU control. Do not run inference.")
        manifests[model] = initialized_interface_manifest(conversation.agent)
        assert conversation.max_iteration_per_run == 512
        assert conversation.agent.llm._adapter is adapter._v057_projection_guard
    finally:
        conversation.close()
assert manifests["QWEN"]["tool_schemas"] == manifests["DEEPSEEK"]["tool_schemas"]
assert sorted(manifests["QWEN"]["tool_schemas"]) == ["file_editor", "finish", "task_tracker", "terminal", "think"]
class Ledger:
    def snapshot(self):
        return {"per_usage_id": {"agent": {"prompt_tokens": 100, "completion_tokens": 10}}}
class Scripted(Adapter):
    ledger = Ledger()
    def __init__(self):
        self.calls = 0
    def request(self, messages, tools):
        return {"model": self.model, "messages": messages, "stream": False,
                "max_tokens": 32768, "thinking": {"type": "enabled"},
                "reasoning_effort": "high", "top_p": .95}
    def complete(self, wire, usage_id):
        self.calls += 1
        message = {"role": "assistant", "content": "ok", "reasoning_content": "kept"}
        if self.calls == 2:
            message["reasoning"] = "conflicting"
        return {"id": "scripted-" + str(self.calls), "model": self.model,
                "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}}
scripted = Scripted()
llm = build_native_llm(scripted, normalization_folder=output / "scripted-projection")
messages = [Message(role="user", content=[TextContent(text="Programmed fixture only")])]
response = llm.completion(messages)
assert response.message.reasoning_content == "kept"
assert response.raw_response.usage.total_tokens == 110
try:
    llm.completion(messages)
    raise AssertionError("The ambiguous projection should fail")
except ResponseNormalizationError:
    pass
try:
    llm.get_token_count(messages)
    raise AssertionError("The sticky projection guard should reject further access")
except ResponseProjectionFault:
    pass
assert scripted.calls == 2
loaded = []
for name, module in sys.modules.items():
    if name == "proworksim" or name.startswith("proworksim."):
        source = Path(module.__file__).resolve()
        loaded.append(str(source.relative_to(runtime / "project/src/proworksim")))
assert not any("software_benchmark_scorer" in name or "software_benchmark_deepseek_api" in name
               or name.startswith(("training", "trainer")) for name in loaded)
assert not any(counts.values())
print(json.dumps({"sdk_version": importlib.metadata.version("openhands-sdk"), "python": sys.version,
    "tools": sorted(classes), "python_executable": sys.executable,
    "model_calls": 0, "tool_calls": 0, "forbidden_operation_counts": counts,
    "fixed_REF_tool_schemas_equal_across_models": True, "scripted_sdk_responses": scripted.calls,
    "DeepSeek_reasoning_projection_and_sticky_guard": True, "managed_worker_class": managed_class.__name__,
    "actual_worker_preload": True, "all_controller_and_worker_entrypoints_imported": True,
    "explicit_namespace_only": True, "loaded_project_modules": sorted(loaded), "interfaces": manifests}))
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
        "TRANSFORMERS_OFFLINE": "1", "CUDA_VISIBLE_DEVICES": "", "NVIDIA_VISIBLE_DEVICES": "void", "OPENHANDS_SUPPRESS_BANNER": "1",
        "HTTP_PROXY": "", "HTTPS_PROXY": "", "ALL_PROXY": "", "http_proxy": "", "https_proxy": "",
        "all_proxy": "", "NO_PROXY": "*", "no_proxy": "*"}


def python_argv(arguments):
    if not arguments:
        raise ValueError("Pass the fixed controller, worker or FIFO bridge script")
    return [CONTAINER_ROOT + "/bin/python", *map(str, arguments)]


def controller_inputs(host_config, row, ready, model_identity, endpoint, *, diagnostic=False,
                      public_context=None, public_environment=None, public_test_entry=None,
                      file_policy=None, gitlinks=None):
    """Project public task/runtime fields; evaluator references and keys stay host-side."""
    condition_raw = checked(host_config["configuration"]).read_bytes()
    arm = row.get("arm", row.get("execution_arm"))
    if (not row["slot_id"].startswith("v064:") or arm not in {"REF", "PROJECT"}
            or row.get("execution_arm", arm) != arm or row.get("model_key") not in {"QWEN", "DEEPSEEK"}
            or any(host_config.get(key) != row[key] for key in
                   ("slot_id", "seed", "source_slot_id", "condition_id"))):
        raise ValueError("Controller inputs require one exact v064 model/interface/budget slot")
    public = host_config["public_task"]
    safe_identity = {key: model_identity[key] for key in (
        "model", "model_key", "model_revision", "documented_model_version", "vllm_version", "raw_release",
        "adapter_sha256", "model_manifest_sha256", "context_limit", "max_output_tokens",
        "service_admission_complete", "port", "deployment_version", "thinking",
        "provider_model_alias", "provider_weight_revision_pinnable") if key in model_identity}
    config = {"version": "v064-private-native-controller-r1" if arm == "REF" else "v064-private-project-controller-r1",
        "slot_id": row["slot_id"], "source_slot_id": row["source_slot_id"], "seed": row["seed"],
        "condition_id": row["condition_id"], "execution_arm": arm, "model_key": row["model_key"],
        "configuration": {"path": "/pws/control/condition.json", "sha256": digest(condition_raw), "bytes": len(condition_raw)},
        "public_task": {key: public[key] for key in ("instance_id", "repo", "base_commit", "problem_statement")},
        "ref_endpoint": endpoint, "model_identity_value": safe_identity, "output": "/pws/output",
        "start": "/pws/control/start.json", "ready": "/pws/control/actor-ready.json",
        "diagnostic": bool(diagnostic),
        "measurement_kind": "zero_model_diagnostic" if diagnostic else "full_verified_comparison"}
    from .software_benchmark_public_context_v062 import VERSION as CONTEXT_VERSION, terminal_initialization_action
    if (not isinstance(public_context, dict) or public_context.get("version") != CONTEXT_VERSION
            or public_context.get("instance_id") != row["instance_id"]):
        raise ValueError("Both conditions require the admitted public execution context")
    terminal_initialization_action(public_environment)
    config["public_context"] = {key: public_context[key] for key in ("version", "visible_text", "visible_facts")}
    config["public_environment"] = {key: public_environment[key] for key in
                                   ("kind", "image_id", "source_config_sha256", "public_python")}
    config["public_environment"]["environment"] = {key: public_environment["environment"][key]
        for key in ("PATH", "CONDA_PREFIX", "CONDA_DEFAULT_ENV") if key in public_environment["environment"]}
    if arm == "PROJECT":
        from .repository_sources_v054 import normalize_policy
        entry = public_test_entry if public_test_entry is not None else host_config["public_test_entry"]
        if (entry.get("instance_id") != row["instance_id"] or entry.get("hidden_material_used") is not False
                or entry.get("cwd") != "/testbed" or type(entry.get("timeout_seconds")) is not int
                or not 1 <= entry["timeout_seconds"] <= 1800
                or not isinstance(entry.get("argv"), list) or not entry["argv"]
                or entry["argv"][0] != public_environment["public_python"]):
            raise ValueError("PROJECT requires an explicit public-only fixed test command and timeout")
        config["public_test_entry"] = {
            "version": "v064-repository-public-test-entry-r1", "instance_id": row["instance_id"],
            "argv": entry["argv"], "cwd": "/testbed", "timeout_seconds": entry["timeout_seconds"],
            "hidden_material_used": False}
        config["file_policy"] = normalize_policy(file_policy if file_policy is not None else host_config.get("file_policy"))
        config["dataset_revision"] = host_config["dataset_revision"]
        config["gitlinks"] = gitlinks if gitlinks is not None else host_config.get("gitlinks", [])
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
    for alias, name in ENTRYPOINT_ALIASES.items():
        _copy_file(ROOT / "tools" / name, runtime / alias, allowed_root=ROOT / "tools")
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
        "entrypoint_aliases": ENTRYPOINT_ALIASES,
        "critical_modules": {name: reference(ROOT / "src/proworksim" / name) for name in CRITICAL_MODULES},
        "project_modules": {name: reference(ROOT / "src/proworksim" / name) for name in PROJECT_MODULES},
        "private_package_initializer": {"sha256": digest(PACKAGE_INITIALIZER.encode()),
            "purpose": "explicit native and managed runtime imports only; omit public package initialization"},
        "benchmark_scorer_or_gold_modules_included": False, "host_key_files_included": False,
        "host_DeepSeek_API_or_cash_ledger_code_included": False,
        "generic_internal_evaluation_record_module_included": True,
        "parameter_update_or_training_entrypoints_included": False,
        "models_or_weights_included": False, "downloaded_packages": 0,
        "host_mount_or_namespace_operations": False, "cpu_preload_only": True}
    write_new(manifest_path, manifest)
    return manifest
