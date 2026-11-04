"""Offline packaging of the explicit v117 controller/actor implementation.

Only the existing pinned local Python and SDK distributions are copied. No
experiment, container, model request or run authorization is created here.
"""
from __future__ import annotations

import ast
import inspect
import json
from pathlib import PurePosixPath

from . import software_benchmark_sdk_bundle_v066 as packaging
from . import software_benchmark_sdk_bundle_v108 as previous
from . import software_benchmark_sdk_bundle_v110 as aligned_base
from .software_benchmark_runtime_inputs_v130 import (
    controller_inputs as controller_inputs, actor_inputs as actor_inputs,
)

VERSION = 'v130-verified-public-tests-and-tools-offline-bundle-r1'
OUTPUT = packaging.ROOT/'runs/software-benchmark-v130/sdk-bundle-r2'
NEW_MODULES = (
    'software_benchmark_alignment_contract_v130.py',
    'software_benchmark_tooling_v130.py',
    'software_benchmark_managed_v130.py',
    'software_benchmark_project_closure_v130.py',
    'software_benchmark_runtime_inputs_v130.py',
    'software_benchmark_managed_actor_v130.py',
    'software_benchmark_public_dependency_runtime_v130.py',
    'software_benchmark_public_test_evidence_v130.py',
    'software_benchmark_alignment_contract_v117.py',
    'software_benchmark_execution_guidance_v117.py',
    'software_benchmark_tooling_v117.py',
    'software_benchmark_tooling_v120.py',
    'software_benchmark_managed_v120.py',
    'software_benchmark_rejected_history_v114.py',
    'software_benchmark_rejected_history_v117.py',
    'software_benchmark_public_dependency_runtime_v117.py',
    'software_benchmark_managed_actor_v117.py',
    'software_benchmark_managed_actor_v119.py',
    'software_benchmark_public_dependency_runtime_v118.py',
    'software_benchmark_generation_admission_v119.py',
    'software_benchmark_finish_review_v117.py', 'software_benchmark_review_runtime_v117.py',
    'software_benchmark_native_control_v117.py', 'software_benchmark_history_budget_v110.py',
    'software_benchmark_history_v117.py', 'software_benchmark_public_tests_v110.py',
    'software_benchmark_public_test_world_v110.py', 'software_benchmark_managed_actor_v110.py',
    'software_benchmark_managed_v117.py', 'software_benchmark_project_closure_v117.py',
    'software_benchmark_runtime_inputs_v119.py',
)
NEW_TOOLS = (
    'run_ref_controller_v130.py',
    'run_project_controller_v130.py',
    'run_native_worker_docker_v130.py',
    'run_managed_worker_docker_v130.py',
    'public_test_dependencies_v130.py',
    'public_test_library_v130.py',
    'run_public_tests_v130.py',
    'public_test_execution_v130.py',
    'public_test_evidence_v130.py',
    'run_ref_controller_v117.py', 'run_project_controller_v120.py',
    'run_native_worker_docker_v118.py', 'run_managed_worker_docker_v119.py',
    'public_fixture_diagnostic_v119.py',
    'public_test_dependencies_v118.py', 'public_test_library_v118.py', 'run_public_tests_v118.py',
)
ALIASES = {**aligned_base.ALIASES,
    'controller.py': 'run_ref_controller_v130.py',
    'project-controller.py': 'run_project_controller_v130.py',
    'worker.py': 'run_native_worker_docker_v130.py',
    'managed-worker.py': 'run_managed_worker_docker_v130.py',
    'public-test.py': 'run_public_tests_v130.py',
    'public-test-library.py': 'public_test_library_v130.py',
    'public-test-dependencies.py': 'public_test_dependencies_v130.py',
    'public-test-execution.py': 'public_test_execution_v130.py',
    'public-test-evidence.py': 'public_test_evidence_v130.py'}


def probe_source():
    return '''import os
os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP="True", OPENHANDS_SUPPRESS_BANNER="1",
                  HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
import sys, socket, json, importlib.util, importlib.metadata
from pathlib import Path
runtime = Path(sys.argv[1]).resolve()
counts = {"network": 0, "process": 0}
def deny(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
        if event == "socket.getaddrinfo" or getattr(args[0], "family", None) in (socket.AF_INET, socket.AF_INET6):
            counts["network"] += 1
            raise RuntimeError("Offline bundle control refuses external networking")
    if event in {"subprocess.Popen", "os.system", "os.fork", "os.posix_spawn"}:
        counts["process"] += 1
        raise RuntimeError("Import/preload cannot create another process")
sys.addaudithook(deny)
from proworksim.software_benchmark_native_worker_v054 import preload
classes, _definitions, _sources, _schemas = preload()
from proworksim.software_benchmark_alignment_contract_v130 import condition, validate_condition
from proworksim.software_benchmark_managed_v130 import worker_type
from proworksim.software_benchmark_history_v110 import condenser_type
from proworksim.software_benchmark_public_tests_v110 import normalize_selection
for arm in ("REF", "PROJECT"):
    validate_condition(condition(arm))
assert condition("REF")["execution_strategy"] == condition("PROJECT")["execution_strategy"]
assert normalize_selection()["kind"] == "full"
worker = worker_type()
from proworksim import software_benchmark_managed_actor_v130 as managed_actor
from proworksim.software_benchmark_public_test_evidence_v130 import run_public_entry
assert managed_actor.ManagedOperationSession.execute.__globals__["run_public_entry"] is run_public_entry
from proworksim.software_benchmark_tooling_v130 import tool_definitions, schema_inventory_case
read = next(item for item in tool_definitions(schema_inventory_case()) if item["name"] == "read_file")
assert read["parameters"]["properties"]["path"] is not read["parameters"]["properties"]["patch_id"]
condenser = condenser_type()
entrypoints = []
for name in ("worker.py", "managed-worker.py", "controller.py", "project-controller.py", "public-test.py"):
    spec = importlib.util.spec_from_file_location("aligned_bundle_"+name.replace(".", "_").replace("-", "_"), runtime/name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    entrypoints.append(name)
loaded = []
for name, module in sys.modules.items():
    if name == "proworksim" or name.startswith("proworksim."):
        source = Path(module.__file__).resolve()
        loaded.append(str(source.relative_to(runtime/"project/src/proworksim")))
assert not any("software_benchmark_scorer" in item or "software_benchmark_deepseek_api" in item for item in loaded)
assert not any(counts.values())
print(json.dumps({"sdk_version": importlib.metadata.version("openhands-sdk"),
    "tools": sorted(classes), "model_calls": 0, "tool_calls": 0, "Docker_operations": 0,
    "forbidden_operation_counts": counts, "actual_worker_preload": True,
    "all_controller_and_worker_entrypoints_imported": True, "entrypoints": entrypoints,
    "managed_worker_class": worker.__name__, "shared_condenser_class": condenser.__name__,
    "loaded_project_modules": sorted(loaded), "factory_runtime_exercised_in_this_probe": False,
    "real_SDK_scripted_factory_controls_are_separate": True}))
'''


def install_public_payload(runtime):
    """Copy only individually frozen public wheel files, never the host site."""
    from .software_benchmark_candidates_v054 import reference
    from .software_benchmark_public_dependency_runtime_v130 import validate_descriptor
    payload = packaging.ROOT/'artifacts/software-benchmark-v130/public-dependencies-r1'
    manifest_path = payload/'manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    descriptor = {'version': manifest['version'], 'instance_id': manifest['instance_id'],
        'actor_root': manifest['actor_root'], 'manifest': reference(manifest_path)}
    validate_descriptor(descriptor, instance_id=manifest['instance_id'], root=payload)
    relative = PurePosixPath(manifest['actor_root']).relative_to('/opt/pws-runtime')
    destination = runtime/str(relative)
    packaging._copy_file(manifest_path, destination/'manifest.json', allowed_root=payload)
    for name in manifest['files']:
        packaging._copy_file(payload/'site'/name, destination/'site'/name, allowed_root=payload/'site')
    return descriptor


# Explicitly insert the public payload before the unchanged offline probe and
# archive. No running module, container, installed dependency or host setting is patched.
_namespace = {**vars(packaging), '__file__': __file__, 'VERSION': VERSION, 'OUTPUT': OUTPUT,
    'PROJECT_MODULES': tuple(sorted(set(packaging.PROJECT_MODULES) | set(previous.NEW_MODULES)
        | set(aligned_base.NEW_MODULES) | set(NEW_MODULES))),
    'TOOLS': tuple(dict.fromkeys((*packaging.TOOLS, *previous.NEW_TOOLS, *aligned_base.NEW_TOOLS, *NEW_TOOLS))),
    'ENTRYPOINT_ALIASES': ALIASES, 'probe_source': probe_source,
    'install_public_payload': install_public_payload}
_source = ast.parse(inspect.getsource(packaging.prepare_bundle))
_inserted = 0
for _index, _statement in enumerate(list(_source.body[0].body)):
    if isinstance(_statement, ast.Assign) and any(isinstance(target, ast.Name)
            and target.id == 'original_sources' for target in _statement.targets):
        _source.body[0].body[_index:_index] = ast.parse('public_dependency_descriptor = install_public_payload(runtime)').body
        _inserted += 1
    if isinstance(_statement, ast.Assign) and any(isinstance(target, ast.Name)
            and target.id == 'manifest' for target in _statement.targets):
        if not isinstance(_statement.value, ast.Dict):
            raise ValueError('The bundle manifest changed shape')
        _statement.value.keys.append(ast.Constant('public_test_dependencies'))
        _statement.value.values.append(ast.Name(id='public_dependency_descriptor', ctx=ast.Load()))
        _inserted += 1
if _inserted != 2:
    raise ValueError('The two declared public payload insertion points changed')
exec(compile(ast.fix_missing_locations(_source), __file__, 'exec'), _namespace)
prepare_bundle = _namespace['prepare_bundle']
runtime_environment = packaging.runtime_environment
python_argv = packaging.python_argv
