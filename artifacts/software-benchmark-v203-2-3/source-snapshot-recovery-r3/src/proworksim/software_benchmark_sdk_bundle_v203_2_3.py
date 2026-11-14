"""New immutable REVIEW2 K-arm runtime bundle with v175 tests and durable journals."""
from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import tempfile
from types import FunctionType

from . import software_benchmark_sdk_bundle_v203_2_1 as previous
from .software_benchmark_runtime_inputs_v203_2_3 import actor_inputs, controller_inputs
from .software_benchmark_content_tokenizer_v141 import descriptor
from .storage import atomic_write, json_bytes

VERSION = "v203.2.3-role-context-v175-retained-bundle-r5"
OUTPUT = previous.OUTPUT.parents[1] / "software-benchmark-v203-2-3/sdk-bundle-r5"
NEW_MODULES = (
    "software_benchmark_alignment_contract_v203_2_3.py",
    "software_benchmark_runtime_inputs_v203_2_3.py",
    "software_benchmark_project_closure_v203_2_3.py",
    "software_benchmark_managed_actor_v203_2_3.py",
    "software_benchmark_public_test_evidence_v203_2_3.py",
    "software_public_test_retention_v203_2_3.py",
    "software_role_context_runtime_v203_2_3.py", "software_role_context_v203_2_3.py",
    "software_context_compression_v175.py",
)
NEW_TOOLS = ("run_role_context_controller_v203_2_3.py", "run_managed_worker_docker_v203_2_3.py",
    "run_native_worker_docker_v203_2_3.py", "run_public_tests_v175.py", "public_test_library_v175.py",
    "public_test_execution_v175.py", "public_test_evidence_v175.py")
ALIASES = {**previous.ALIASES,
    "controller.py": "run_role_context_controller_v203_2_3.py",
    "project-controller.py": "run_role_context_controller_v203_2_3.py",
    "managed-worker.py": "run_managed_worker_docker_v203_2_3.py",
    "worker.py": "run_native_worker_docker_v203_2_3.py",
    "public-test.py": "run_public_tests_v175.py", "public-test-library.py": "public_test_library_v175.py",
    "public-test-execution.py": "public_test_execution_v175.py",
    "public-test-evidence.py": "public_test_evidence_v175.py"}


def _controller_fixtures():
    """Prepare synthetic public identities for validation inside the copied SDK."""
    from . import software_benchmark_alignment_contract_v203_2_3 as alignment
    from . import software_benchmark_runtime_inputs_v203_2_3 as inputs
    from .software_benchmark_candidates_v054 import write_new
    from .software_benchmark_public_context_v062 import VERSION as CONTEXT_VERSION
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("_v203_public_fixture", root / "tests/test_public_runtime_bindings_v141.py")
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    rows = []
    with tempfile.TemporaryDirectory(prefix="pws-v203-controller-probe-") as temporary:
        folder = Path(temporary)
        for group in ("K0", "K1", "K2"):
            case = folder / group
            case.mkdir()
            row, public, entry, base, _, _, host = fixture.prepared(case, "REVIEW2")
            row.update(condition=group, condition_id=group, group_id=group,
                slot_id=f"v203.2.3:{row['instance_id']}:{group}:{row['seed']}")
            binding = inputs.actor_inputs(base, public_test_entry=entry, row=row)
            config = binding["config"]
            ready = {key: config[key] for key in ("organization_id", "fixed_members", "member_count", "role_contract_version",
                "role_catalog_sha256", "public_test_result_revision", "public_test_contract_sha256")}
            ready.update(public_test_selection_revision="v110-public-test-selection-r1",
                public_test_files_sha256={key: config[key] for key in inputs.PUBLIC_FILES},
                public_dependency_admission_checked=True, public_dependency_profile=None)
            host.update(slot_id=row["slot_id"], condition_id=group,
                configuration=write_new(case / "new-condition.json", alignment.condition(group)))
            context = {"version": CONTEXT_VERSION, "instance_id": row["instance_id"],
                "visible_text": "Synthetic public binding fixture", "visible_facts": {"cwd": "/testbed"}}
            output = inputs.controller_inputs(host, row, ready, {"thinking": False, "model": "deepseek-flash"},
                "http://127.0.0.1:1", public_context=context, public_environment=public,
                public_test_entry=entry, actor_config=config)
            rows.append({"config": json.loads(output["controller-config.json"]), "ready": ready,
                "actor_config": config, "contract": binding["files"]["public-test-contract.json"].decode()})
    return rows


def probe_source():
    source = previous.probe_source()
    for old, new in (
        ("software_benchmark_alignment_contract_v203_2_1", "software_benchmark_alignment_contract_v203_2_3"),
        ("software_benchmark_managed_actor_v143", "software_benchmark_managed_actor_v203_2_3"),
        ("software_benchmark_managed_actor_v141", "software_benchmark_managed_actor_v203_2_3"),
        ("software_benchmark_public_test_evidence_v141", "software_benchmark_public_test_evidence_v203_2_3"),
    ):
        source = source.replace(old, new)
    source = source.replace('worker = worker_type()', '''from proworksim.software_role_context_runtime_v203_2_3 import install, FIELDS
from proworksim.software_role_context_v203_2_3 import STRUCTURAL_KINDS
from proworksim.software_benchmark_runtime_inputs_v203_2_3 import PUBLIC_FILES
assert all('/observation/' + field in STRUCTURAL_KINDS for field in FIELDS)
worker = worker_type()''')
    controls = json.dumps(_controller_fixtures(), ensure_ascii=False)
    source = source.replace('    entrypoints.append(name)', '''    if name in ('controller.py', 'project-controller.py'):
        for fixture in json.loads(''' + repr(controls) + '''):
            assert module.validate_config(fixture['config']) == fixture['config']
            assert module.validate_ready(fixture['config'], fixture['ready']) == fixture['ready']
            contract = Path.cwd() / 'synthetic-public-test-contract.json'
            if contract.exists(): contract.chmod(0o644)
            contract.write_text(fixture['contract'])
            contract.chmod(0o444)
            assert managed_actor.verify_public_runtime_files(fixture['actor_config'], runtime, contract) == fixture['ready']['public_test_files_sha256']
    entrypoints.append(name)''')
    return source.replace('"real_SDK_scripted_factory_controls_are_separate": True',
        '"real_SDK_scripted_factory_controls_are_separate": True, "three_group_controller_config_and_actor_file_roundtrips": True')


_namespace = {**previous._namespace, "__file__": __file__, "VERSION": VERSION, "OUTPUT": OUTPUT,
    "PROJECT_MODULES": tuple(sorted(set(previous._namespace["PROJECT_MODULES"]) | set(NEW_MODULES))),
    "TOOLS": tuple(dict.fromkeys((*previous._namespace["TOOLS"], *NEW_TOOLS))),
    "ENTRYPOINT_ALIASES": ALIASES, "probe_source": probe_source}
_prepare = FunctionType(previous._prepare.__code__, _namespace, previous._prepare.__name__,
    previous._prepare.__defaults__, previous._prepare.__closure__)


def prepare_bundle():
    result = _prepare()
    path = OUTPUT / "manifest.json"
    saved = json.loads(path.read_bytes())
    metadata = {"content_tokenizer": descriptor(), "organization_id": "REVIEW2",
        "context_conditions": ["K0", "K1", "K2"], "public_test_bundle_shared": True,
        "public_framework_journal_retained": True, "old_runtime_bundles_modified": False}
    if "context_conditions" not in saved:
        result.update(metadata)
        atomic_write(path, json_bytes(result))
    elif any(saved.get(key) != value for key, value in metadata.items()):
        raise ValueError("The prepared role-context bundle metadata changed")
    return result


runtime_environment = previous.runtime_environment
python_argv = previous.python_argv
