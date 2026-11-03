"""Seal completed preparation for review; this never grants runtime authority."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from proworksim import software_benchmark_scope_v111 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new

PROPOSAL = scope.ROOT / 'artifacts/software-benchmark-v111/runtime-authorization-r1/proposal.json'
ENTRIES = ('tools/run_aligned_interface_v111.py', 'tools/launch_aligned_interface_v111.py', 'tools/summarize_aligned_interface_v111.py', 'tools/prepare_aligned_panel_v111.py', 'tools/prepare_aligned_runtime_v111.py', 'tools/seal_aligned_interface_v111.py', 'tools/run_ref_controller_v110.py', 'tools/run_project_controller_v110.py', 'tools/run_native_worker_docker_v110.py', 'tools/run_managed_worker_docker_v110.py', 'tools/run_public_tests_v110.py', 'tools/public_test_library_v110.py', 'tools/run_offline_scorer_v096.py', 'src/proworksim/software_benchmark_grading_v111.py', 'src/proworksim/software_benchmark_sdk_bundle_v110.py', 'src/proworksim/software_benchmark_host_api_v111.py')


def source_closure():
    pending = [scope.ROOT / name for name in ENTRIES]
    found = {}
    while pending:
        path = pending.pop().resolve()
        if str(path) in found:
            continue
        if not path.is_file():
            raise FileNotFoundError(path)
        found[str(path)] = reference(path)
        try:
            module = '.'.join(path.relative_to(scope.ROOT / 'src').with_suffix('').parts)
            package = module.rsplit('.', 1)[0]
        except ValueError:
            package = None
        for node in ast.walk(ast.parse(path.read_bytes(), filename=str(path))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith('.py'):
                literal = node.value
                target = (scope.ROOT / 'tools' / literal if Path(literal).name == literal
                          else scope.ROOT / literal if literal.startswith('tools/') else None)
                if target is not None and target.is_file():
                    pending.append(target)
            candidates = []
            if isinstance(node, ast.Import):
                candidates = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    if package is None:
                        continue
                    base = '.'.join(package.split('.')[:len(package.split('.'))-node.level+1])
                    full = base + ('.'+node.module if node.module else '')
                else:
                    full = node.module or ''
                candidates = [full, *[full+'.'+item.name for item in node.names]]
            for name in candidates:
                if not name.startswith('proworksim'):
                    continue
                target = scope.ROOT / 'src' / Path(*name.split('.'))
                for candidate in (target.with_suffix('.py'), target / '__init__.py'):
                    if candidate.is_file():
                        pending.append(candidate)
                        break
    return [found[key] for key in sorted(found)]


def seal():
    if scope.AUTH_FILE.exists() or (scope.API_ROOT/'execution-started.json').exists():
        raise PermissionError('Never change an approved or entered batch')
    if scope.SOURCE_FILE.exists() or PROPOSAL.exists():
        raise ValueError('New scope sealing is single-use')
    from proworksim.software_benchmark_alignment_contract_v110 import VERSION as ALIGNMENT_VERSION
    from proworksim import software_benchmark_sdk_bundle_v110 as bundle
    from proworksim import software_benchmark_host_api_v111 as host
    scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    budget = scope.load(reference(scope.BUDGET_BASELINE_FILE))
    if (budget['explicit_user_reply'] != '沿用旧账本，累计上限仍为350元'
            or budget['ledger_path'] != str(scope.LEDGER_FILE)
            or budget['cash_budget_scope'] != scope.CASH_MODE
            or budget['budget_increased'] is not False):
        raise ValueError('Preserve the exact original cumulative money authority')
    # Validation only; existing local archive and manifests must match sources.
    bundle.prepare_bundle()
    bundle_ref = reference(bundle.OUTPUT/'manifest.json')
    schemas_ref = reference(host.SCHEMAS)
    if scope.load(schemas_ref)['native_bundle'] != bundle_ref:
        raise ValueError('Wire schemas are not bound to this runtime')
    evidence = {}
    for name, path in (
        ('v110_implementation', 'artifacts/software-benchmark-v110/implementation-summary.json'),
        ('scope', 'artifacts/software-benchmark-v111/scope-controls-r1/summary.json'),
        ('runtime', 'artifacts/software-benchmark-v111/runtime-controls-r1/summary.json'),
        ('grading', 'artifacts/software-benchmark-v111/grading-controls-r1/summary.json'),
    ):
        ref = reference(scope.ROOT/path)
        value = scope.load(ref)
        if name != 'v110_implementation' and value.get('passed') is not True:
            raise ValueError('Necessary CPU preparation failed: '+name)
        if name == 'v110_implementation' and value.get('status') != 'implemented_and_offline_validated':
            raise ValueError('The requested strategy lacks its implementation controls')
        evidence[name] = ref
    sources = write_new(scope.SOURCE_FILE, {
        'version':scope.VERSION,'files':source_closure(),'runtime_bundle':bundle_ref,
        'actual_tool_schemas':schemas_ref,'controls':evidence,
        'execution_alignment_version':ALIGNMENT_VERSION,
        'cash_before_run':reference(scope.BUDGET_BASELINE_FILE),
        'real_model_calls':0,'Docker_operations':0,
    })
    proposal = {
        'version':scope.VERSION,'status':'prepared_pending_specific_Docker_scope_approval',
        'new_evaluation_user_request':'启用新评测',
        'budget_user_reply':budget['explicit_user_reply'],
        'execution_alignment_version':ALIGNMENT_VERSION,
        'plan':reference(scope.PLAN_FILE),'panel':reference(scope.PANEL_FILE),
        'inventory':reference(scope.INVENTORY_FILE),'source_index':sources,
        'constraints':scope.CONSTRAINTS,'runtime_bundle':bundle_ref,
        'actual_tool_schemas':schemas_ref,'preparation_evidence':evidence,
        'cash_before_run':reference(scope.BUDGET_BASELINE_FILE),
        'API_cash_cap_CNY':scope.CASH_CAP_CNY,'cash_budget_scope':scope.CASH_MODE,
        'ledger_path':str(scope.LEDGER_FILE),'available_at_preparation_CNY':budget['remaining_CNY'],
        'new_generation_attempts':100,'shared_host_configuration_changes':0,
        'resource_scope':{
            'existing_project_Docker_management_interface_only':True,
            'maximum_new_containers':454,'maximum_new_named_volumes':102,
            'maximum_simultaneous_generation_pairs':8,'maximum_simultaneous_graders':2,
            'new_ordinary_user_services':[scope.API_UNIT],
            'new_system_slice':False,'host_mounts_network_drivers_services_changed':False,
            'other_users_objects_accessed':False,'GPU_operations':0,
            'generation_network':'none','container_drop_caps':['ALL'],
            'host_bind_mounts':False,'published_ports':False,
            'grader_exceptions':{
                'tasks':scope.CONSTRAINTS['requests_private_capability_tasks'],
                'container_caps':['NET_ADMIN','NET_BIND_SERVICE'],
                'real_TLS_tasks':list(scope.original.TLS_TASKS),
                'destination':'httpbin.org','ports':[80,443],
                'maximum_sessions':10,'connections_per_session':512,
                'total_application_payload_bytes':640*1024**2,
            },
        },
        'API_preparation':{'maximum_calls':2,'total_token_bound':8192,'tools_executed':0},
        'no_new_cash_or_old_reservation_refund':True,'old_results_overwritten':False,
        'authorization_created':False,'execution_started':False,
    }
    PROPOSAL.parent.mkdir(parents=True,exist_ok=True)
    return {'proposal':write_new(PROPOSAL,proposal),'source_index':sources,
            'authorized':False,'execution_started':False}


if __name__ == '__main__':
    print(json.dumps(seal(),ensure_ascii=False))

