"""Immutable offline bundle for the four actual S1 context policies."""
import json
from pathlib import Path
from types import FunctionType
from . import software_benchmark_sdk_bundle_v170 as previous
from . import software_benchmark_sdk_bundle_v143 as clean_probe
from .software_benchmark_runtime_inputs_v192 import actor_inputs,controller_inputs
from .software_benchmark_content_tokenizer_v141 import descriptor
from .storage import atomic_write,json_bytes

VERSION='v192-S1-context-offline-bundle-r1'
OUTPUT=Path(__file__).resolve().parents[2]/'runs/software-benchmark-v192/sdk-bundle-r2'
NEW_MODULES=('software_benchmark_alignment_contract_v192.py','software_benchmark_runtime_inputs_v192.py',
 'software_benchmark_project_closure_v192.py','software_context_runtime_v192.py','software_role_baseline_runtime_v192.py',
 'software_context_sources_v192.py','software_context_reader_v179.py','software_context_recovery_v176.py',
 'software_context_compression_v175.py','software_collaboration_runtime_observer_v172.py',
 'software_benchmark_public_test_evidence_v175.py','software_benchmark_managed_actor_v192.py','software_context_critical_v191.py',
 'software_context_runtime_v181.py','software_context_sources_v181.py','software_benchmark_alignment_contract_v181.py',
 'software_public_test_view_v192.py','software_context_observer_v192.py')
NEW_TOOLS=('run_context_controller_v192.py','run_native_worker_docker_v192.py','run_managed_worker_docker_v192.py',
 'run_public_tests_v175.py','public_test_library_v175.py','public_test_execution_v175.py','public_test_evidence_v175.py')
ALIASES={**previous.ALIASES,'worker.py':'run_native_worker_docker_v192.py','managed-worker.py':'run_managed_worker_docker_v192.py',
 'controller.py':'run_context_controller_v192.py','project-controller.py':'run_context_controller_v192.py',
 'public-test.py':'run_public_tests_v175.py','public-test-library.py':'public_test_library_v175.py',
 'public-test-execution.py':'public_test_execution_v175.py','public-test-evidence.py':'public_test_evidence_v175.py'}

def probe_source():
    source=clean_probe.probe_source().replace('software_benchmark_alignment_contract_v141','software_benchmark_alignment_contract_v192')
    source=source.replace('software_role_baseline_runtime_v141','software_role_baseline_runtime_v192')
    source=source.replace('{"S1", "FREE2", "REVIEW2"}','{"M0","M1-5","M1-10","M1-5K"}')
    source=source.replace('software_benchmark_managed_actor_v143','software_benchmark_managed_actor_v192')
    return source.replace('software_benchmark_public_test_evidence_v141','software_benchmark_public_test_evidence_v175')

_namespace={**previous._namespace,'__file__':__file__,'VERSION':VERSION,'OUTPUT':OUTPUT,
 'PROJECT_MODULES':tuple(sorted(set(previous._namespace['PROJECT_MODULES'])|set(NEW_MODULES))),
 'TOOLS':tuple(dict.fromkeys((*previous._namespace['TOOLS'],*NEW_TOOLS))),
 'ENTRYPOINT_ALIASES':ALIASES,'probe_source':probe_source}
_prepare=FunctionType(previous._prepare.__code__,_namespace,previous._prepare.__name__,previous._prepare.__defaults__,previous._prepare.__closure__)

def prepare_bundle():
    result=_prepare();result['content_tokenizer']=descriptor()
    atomic_write(OUTPUT/'manifest.json',json_bytes(result));return result

runtime_environment=previous.runtime_environment
python_argv=previous.python_argv
