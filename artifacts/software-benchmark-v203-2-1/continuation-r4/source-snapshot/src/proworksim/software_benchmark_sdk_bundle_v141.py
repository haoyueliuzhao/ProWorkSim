"""Offline v141 role-baseline runtime bundle; no inference or execution authority."""
from __future__ import annotations

import json
from pathlib import Path
from types import FunctionType

from . import software_benchmark_sdk_bundle_v132 as previous
from .software_benchmark_runtime_inputs_v141 import controller_inputs as controller_inputs, actor_inputs as actor_inputs
from .software_benchmark_content_tokenizer_v141 import SOURCE, PREFIX, manifest_bytes, descriptor
from .software_benchmark_deepseek_tokenizer_v055 import _check_file

packaging = previous.packaging
VERSION = 'v141-observed-role-baseline-offline-bundle-r1'
OUTPUT = packaging.ROOT/'runs/software-benchmark-v141/sdk-bundle-r2'
NEW_MODULES = (
    'software_benchmark_alignment_contract_v141.py', 'software_benchmark_content_tokenizer_v141.py',
    'software_benchmark_managed_actor_v141.py', 'software_benchmark_public_test_evidence_v141.py',
    'software_benchmark_runtime_inputs_v141.py', 'software_benchmark_project_closure_v141.py',
    'software_benchmark_state_storage_v141.py', 'software_collaboration_observation_v141.py',
    'software_collaboration_runtime_observer_v141.py', 'software_role_baseline_contract_v141.py',
    'software_role_baseline_world_v141.py', 'software_role_baseline_runtime_v141.py',
    'software_benchmark_deepseek_tokenizer_v055.py',
)
NEW_TOOLS = ('run_role_baseline_controller_v141.py', 'run_managed_worker_docker_v141.py',
    'run_public_tests_v141.py', 'public_test_library_v141.py',
    'public_test_execution_v141.py', 'public_test_evidence_v141.py')
ALIASES = {**previous.ALIASES, 'controller.py':'run_role_baseline_controller_v141.py',
    'project-controller.py':'run_role_baseline_controller_v141.py',
    'managed-worker.py':'run_managed_worker_docker_v141.py',
    'public-test.py':'run_public_tests_v141.py', 'public-test-library.py':'public_test_library_v141.py',
    'public-test-execution.py':'public_test_execution_v141.py',
    'public-test-evidence.py':'public_test_evidence_v141.py'}
ALIASES.pop('public-fixture-diagnostic.py', None)


def install_public_payload(runtime):
    dependency = previous.install_public_payload(runtime)
    # These five aliases are the exact files checked by the new actor before ready.
    for name in ('public-test.py', 'public-test-library.py', 'public-test-dependencies.py',
                 'public-test-execution.py', 'public-test-evidence.py'):
        (Path(runtime)/name).chmod(0o444)
    manifest = json.loads(SOURCE.read_bytes())
    overlay = Path(manifest['overlay_path']).resolve()
    destination = Path(runtime)/'content-tokenizer'
    for row in manifest['installed_files']:
        source = _check_file(row)
        packaging._copy_file(source, destination/'overlay'/source.relative_to(overlay), allowed_root=overlay)
    for row in manifest['tokenizer_files']:
        source = _check_file(row)
        packaging._copy_file(source, destination/'tokenizer'/source.name, allowed_root=source.parent)
    raw = manifest_bytes(PREFIX)
    (destination/'manifest.json').write_bytes(raw)
    (destination/'manifest.json').chmod(0o444)
    return dependency


def probe_source():
    return '''import os
os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP="True", OPENHANDS_SUPPRESS_BANNER="1",
                  HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
import sys, socket, json, hashlib, importlib.util, importlib.metadata
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
from proworksim.software_benchmark_alignment_contract_v141 import condition, validate_condition, GROUP_IDS
from proworksim.software_role_baseline_runtime_v141 import worker_type
from proworksim.software_role_baseline_runtime_v141 import prepare_schema_inventory as current_inventory
assert set(current_inventory()["schemas"]) == {"S1", "FREE2", "REVIEW2"}
schema_sha = hashlib.sha256(json.dumps(current_inventory()["schemas"], sort_keys=True,
    separators=(",", ":")).encode()).hexdigest()
from proworksim.software_benchmark_history_v110 import condenser_type
from proworksim.software_benchmark_public_tests_v110 import normalize_selection
for group in GROUP_IDS:
    validate_condition(condition(group))
assert {condition(g)["episode_limits"]["input_plus_output_tokens"] for g in GROUP_IDS} == {5000000}
assert normalize_selection()["kind"] == "full"
worker = worker_type()
from proworksim import software_benchmark_managed_actor_v141 as managed_actor
from proworksim.software_benchmark_public_test_evidence_v141 import run_public_entry
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
    if name in ("controller.py", "project-controller.py"):
        assert "software_role_baseline_runtime_v141" in module.main.__code__.co_names
        assert "software_fixed_organization_runtime_v131" not in module.main.__code__.co_names
    entrypoints.append(name)
# Exercise the same copied recipe/vocabulary in a relocated CPU view, not a download.
from proworksim.software_collaboration_observation_v141 import load_official_content_counter
raw = (runtime/"content-tokenizer/manifest.json").read_bytes()
frozen_manifest = json.loads(raw)
local_manifest = json.loads(raw)
for key in ("installed_files", "tokenizer_files"):
    for row in local_manifest[key]:
        row["path"] = str(runtime/Path(row["path"]).relative_to("/opt/pws-runtime"))
local_manifest["overlay_path"] = str(runtime/"content-tokenizer/overlay")
local_path = Path.cwd()/"probe-content-tokenizer.json"
local_raw = json.dumps(local_manifest,sort_keys=True,separators=(",",":")).encode()
local_path.write_bytes(local_raw)
counter, metadata = load_official_content_counter(local_path,manifest_sha256=hashlib.sha256(local_raw).hexdigest())
assert counter("hello world") > 0 and counter("") == 0
loaded = []
for name, module in sys.modules.items():
    if name == "proworksim" or name.startswith("proworksim."):
        source = Path(module.__file__).resolve()
        loaded.append(str(source.relative_to(runtime/"project/src/proworksim")))
assert not any("software_benchmark_scorer" in item or "software_benchmark_deepseek_api" in item
               or "software_benchmark_dispatch" in item or "software_benchmark_expansion_episode" in item for item in loaded)
assert not any(counts.values())
print(json.dumps({"sdk_version": importlib.metadata.version("openhands-sdk"),
    "tools": sorted(classes), "model_calls": 0, "tool_calls": 0, "Docker_operations": 0,
    "forbidden_operation_counts": counts, "actual_worker_preload": True,
    "all_controller_and_worker_entrypoints_imported": True, "entrypoints": entrypoints,
    "organization_ids": list(GROUP_IDS), "managed_worker_class": worker.__name__, "shared_condenser_class": condenser.__name__,
    "loaded_project_modules": sorted(loaded), "factory_runtime_exercised_in_this_probe": False,
    "role_schemas_match_new_contract": True, "exact_local_content_counter_executed": True,
    "content_vocabulary_sha256": metadata["vocabulary_sha256"], "initial_business_state_hash_streamed": True,
    "member_schema_sha256": schema_sha,
    "real_SDK_scripted_factory_controls_are_separate": True}))
'''


_namespace = {**previous._namespace, '__file__': __file__, 'VERSION': VERSION, 'OUTPUT': OUTPUT,
    'PROJECT_MODULES': tuple(sorted(set(previous._namespace['PROJECT_MODULES'])|set(NEW_MODULES))),
    'TOOLS': tuple(dict.fromkeys((*previous._namespace['TOOLS'], *NEW_TOOLS))),
    'ENTRYPOINT_ALIASES': ALIASES, 'probe_source': probe_source,
    'install_public_payload': install_public_payload}
_prepare_bundle = FunctionType(previous.prepare_bundle.__code__, _namespace,
    previous.prepare_bundle.__name__, previous.prepare_bundle.__defaults__, previous.prepare_bundle.__closure__)


def prepare_bundle():
    result = _prepare_bundle()
    result['content_tokenizer'] = descriptor()
    # Additional descriptor is deterministic from the same installed files;
    # persist it before returning the host-visible manifest.
    manifest = OUTPUT/'manifest.json'
    saved = json.loads(manifest.read_bytes())
    if 'content_tokenizer' not in saved:
        from .storage import atomic_write, json_bytes
        atomic_write(manifest,json_bytes(result))
    elif saved['content_tokenizer'] != result['content_tokenizer']:
        raise ValueError('Prepared content tokenizer differs from the current frozen manifest')
    return result


runtime_environment = packaging.runtime_environment
python_argv = packaging.python_argv
