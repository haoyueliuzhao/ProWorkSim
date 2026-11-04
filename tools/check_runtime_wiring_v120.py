"""Narrow v120 source equivalence and actual SDK worker-class binding, no model."""
from __future__ import annotations
import ast
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def run():
    os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                      HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    prohibited = {'network': 0, 'process': 0}
    def audit(event, args):
        if event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'):
            prohibited['network'] += 1
            raise RuntimeError('This source/SDK construction control cannot use a network')
        if event in ('subprocess.Popen', 'os.system', 'os.fork', 'os.posix_spawn'):
            prohibited['process'] += 1
            raise RuntimeError('This source/SDK construction control cannot launch processes')
    sys.addaudithook(audit)
    source = ROOT/'src/proworksim'
    old_factory = (source/'software_benchmark_managed_v117.py').read_text()
    new_factory = source/'software_benchmark_managed_v120.py'
    expected = old_factory.replace('software_benchmark_tooling_v117', 'software_benchmark_tooling_v120').replace(
        "REPAIR_REVISION = 'v117-managed-aligned-review-history-public-tests-r1'",
        "REPAIR_REVISION = 'v120-managed-tool-json-key-order-r1'")
    assert ast.dump(ast.parse(expected)) == ast.dump(ast.parse(new_factory.read_text()))
    old_controller = (ROOT/'tools/run_project_controller_v118.py').read_text()
    new_controller = ROOT/'tools/run_project_controller_v120.py'
    expected = old_controller.replace('software_benchmark_managed_v117', 'software_benchmark_managed_v120').replace(
        'software_benchmark_tooling_v117', 'software_benchmark_tooling_v120')
    assert ast.dump(ast.parse(expected)) == ast.dump(ast.parse(new_controller.read_text()))
    from proworksim import software_benchmark_managed_v120 as managed
    from proworksim import software_benchmark_tooling_v120 as tooling
    from proworksim import software_benchmark_tooling_v117 as original_tooling
    from proworksim import software_benchmark_sdk_bundle_v120 as bundle
    from proworksim import software_benchmark_sdk_bundle_v119 as old_bundle
    from proworksim import software_benchmark_runtime_inputs_v119 as inputs
    from proworksim.software_benchmark_history_v117 import history_worker_type
    from proworksim.software_benchmark_review_runtime_v117 import FinishReviewWorkerMixin
    from proworksim.software_benchmark_candidates_v054 import reference
    worker = managed.worker_type()
    assert worker.__bases__ == (tooling.ToolFeedbackWorkerMixin, FinishReviewWorkerMixin, history_worker_type())
    assert managed.world is tooling
    for name in ('prepare_case', 'validate_case', 'member_instruction', 'SoftwareCollaborationPort', 'PublicTestCallback'):
        assert getattr(tooling, name) is getattr(original_tooling, name)
    assert bundle.actor_inputs is inputs.actor_inputs and bundle.controller_inputs is inputs.controller_inputs
    expected_aliases = {**old_bundle.ALIASES, 'project-controller.py': 'run_project_controller_v120.py'}
    assert bundle.ALIASES == expected_aliases
    for name in ('software_benchmark_managed_v120.py', 'software_benchmark_tooling_v120.py'):
        assert name in bundle._namespace['PROJECT_MODULES']
    assert 'run_project_controller_v120.py' in bundle._namespace['TOOLS']
    assert 'from proworksim.software_benchmark_managed_v120 import worker_type' in bundle.probe_source()
    assert not any(prohibited.values())
    evidence = {'version': 'v120-fresh-project-wiring-equivalence-r1', 'passed': True,
        'factory_changes_only_tooling_imports_and_revision_label': True,
        'controller_changes_only_managed_and_tooling_imports': True,
        'actual_SDK_worker_bases': [cls.__module__+'.'+cls.__name__ for cls in worker.__bases__],
        'world_tools_schema_prompts_budget_history_review_unchanged': True,
        'actor_and_public_dependencies_and_certificates_unchanged': True,
        'runtime_input_functions_reused_by_identity': True, 'only_PROJECT_controller_alias_changed': True,
        'behavior_control': reference(ROOT/'artifacts/software-benchmark-v120/cursor-sdk-control-r2/summary.json'),
        'behavior_control_repeated': False,
        'sources': [reference(new_factory), reference(new_controller), reference(source/'software_benchmark_sdk_bundle_v120.py')],
        'prohibited_operation_counts': prohibited, 'model_calls': 0, 'Docker_operations': 0, 'services_started': 0}
    output = ROOT/'artifacts/software-benchmark-v120/runtime-wiring-controls-r1'
    output.mkdir(parents=True, exist_ok=True)
    (output/'summary.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    run()
