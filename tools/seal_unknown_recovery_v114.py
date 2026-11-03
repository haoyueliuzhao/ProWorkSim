"""Seal completed preparation for review; this never grants runtime authority."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from proworksim import software_benchmark_scope_v114 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new

PROPOSAL = scope.ROOT / 'artifacts/software-benchmark-v114/runtime-authorization-r1/proposal.json'
ENTRIES = ('tools/run_unknown_recovery_v114.py', 'tools/launch_unknown_recovery_v114.py', 'tools/summarize_unknown_recovery_v114.py', 'tools/prepare_unknown_recovery_v114.py', 'tools/seal_unknown_recovery_v114.py', 'src/proworksim/software_benchmark_grading_recovery_v114.py', 'src/proworksim/software_benchmark_environment_v114.py', 'src/proworksim/software_benchmark_grading_ca_v114.py', 'src/proworksim/software_benchmark_episode_recovery_v114.py', 'src/proworksim/software_benchmark_host_api_v114.py', 'tools/run_offline_scorer_v096.py', 'tools/run_ref_controller_v110.py', 'tools/run_project_controller_v110.py', 'tools/run_native_worker_docker_v110.py', 'tools/run_managed_worker_docker_v110.py', 'tools/run_public_tests_v110.py', 'tools/public_test_library_v110.py')


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
    from proworksim import software_benchmark_scope_v113 as prior
    from proworksim import software_benchmark_host_api_v114 as host
    from proworksim.software_benchmark_alignment_contract_v110 import VERSION as ALIGNMENT_VERSION
    from proworksim.software_benchmark_grading_ca_v114 import profile_manifest
    if scope.AUTH_FILE.exists() or scope.SOURCE_FILE.exists() or (scope.API_ROOT/'execution-started.json').exists():
        raise PermissionError('Do not re-seal approved or entered recovery work')
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    parent=prior.load(reference(prior.AUTH_FILE))
    cash=scope.load(reference(scope.BUDGET_BASELINE_FILE))
    profile_manifest()
    controls={}
    names=('scope-controls-r1','unknown-runtime-controls-r1','grading-recovery-control-r1',
           'grading-transport-control-r1','grading-ca-controls-r1','test-reset-control-r1',
           'stopped-recovery-controls-r1')
    for name in names:
        ref=reference(scope.ROOT/'artifacts/software-benchmark-v114'/name/'summary.json')
        value=scope.load(ref)
        passed=value.get('passed') is True
        if name=='grading-ca-controls-r1':
            passed=(value.get('status')=='passed'
                and {row['instance_id'] for row in value.get('tasks',[])}=={'psf__requests-1766','psf__requests-1921'}
                and all(row.get('passed') is True and row.get('verify_mode_and_hostname_checks_unchanged') is True
                        for row in value['tasks'])
                and value.get('profile')==reference(scope.CA_PROFILE_FILE))
        if not passed:
            raise ValueError('Necessary recovery preparation failed: '+name)
        controls[name]=ref
    schemas=reference(host.SCHEMAS)
    old_qualification=scope.load(plan['reused_API_qualification'])
    old_schemas=scope.load(old_qualification['schema_inventory'])
    new_schemas=scope.load(schemas)
    if old_schemas['schemas']!=new_schemas['schemas'] or old_schemas['tool_names']!=new_schemas['tool_names']:
        raise ValueError('Remaining model tasks must use the same actual wire interfaces')
    sources=write_new(scope.SOURCE_FILE,{'version':scope.VERSION,'files':source_closure(),
        'controls':controls,'model_runtime_unchanged':'v110 fixed bundle and v113 effective deadline',
        'actual_tool_schemas':schemas,'CA_profile':reference(scope.CA_PROFILE_FILE),
        'network_resolution':reference(scope.NETWORK_RESOLUTION_FILE),
        'model_calls':0,'Docker_operations':0})
    proposal={'version':scope.VERSION,'status':'prepared_pending_specific_runtime_approval',
        'user_task':'处理未定，完成后继续详细分析通过率差异的原因',
        'user_CA_reply':'允许评分侧更新CA','execution_alignment_version':ALIGNMENT_VERSION,
        'original_batch_authorization':reference(prior.AUTH_FILE),
        'original_authorization':parent['original_authorization'],
        'concurrency_authorization':parent['concurrency_authorization'],
        'preparation_recovery':parent['preparation_recovery'],'diagnostics_repeated':0,
        'explicit_concurrency_instruction':'提高并发',
        'plan':reference(scope.PLAN_FILE),'source_index':sources,'controls':controls,
        'new_generation_attempts':4,'already_called_models_resampled':0,
        'original_locked_candidate_rescores':2,'stopped_tree_supplemental_scores':2,
        'supplemental_scores_overwrite_original_primary_unknown':False,
        'constraints':scope.CONSTRAINTS,'shared_host_configuration_changes':0,
        'CA_profile':reference(scope.CA_PROFILE_FILE),'effective_CA_changed_only_in_scoring':True,
        'network_resolution':reference(scope.NETWORK_RESOLUTION_FILE),
        'API_qualification':plan['reused_API_qualification'],'new_neutral_API_calls':0,
        'API_cash_cap_CNY':scope.CASH_CAP_CNY,'cash_budget_scope':scope.CASH_MODE,
        'ledger_path':str(scope.LEDGER_FILE),'cash_before_run':reference(scope.BUDGET_BASELINE_FILE),
        'remaining_CNY_at_preparation':cash['remaining_CNY'],'additional_cash':0,
        'maximum_new_containers':26,'maximum_new_named_volumes':4,
        'generation_pair_concurrency':4,'scoring_concurrency':2,'TLS_scoring_concurrency':1,
        'combined_CPU':40,'combined_memory_GiB':192,'same_owned_user_service':scope.API_UNIT,
        'GPU_operations':0,'new_system_slice':False,'new_host_bindings_or_ports':False,
        'container_network':'none','container_drop_caps':['ALL'],
        'TLS_only_scoring_caps':['NET_ADMIN','NET_BIND_SERVICE'],
        'TLS_tasks':['psf__requests-1766','psf__requests-1921'],
        'TLS_destination':'httpbin.org','TLS_selected_IP':'16.58.42.220','TLS_ports':[80,443],
        'maximum_TLS_sessions':10,'maximum_connections':5120,'maximum_TLS_payload_bytes':640*1024**2,
        'no_host_configuration_or_other_users_objects_touched':True,
        'runtime_authorized':False,'execution_started':False}
    PROPOSAL.parent.mkdir(parents=True,exist_ok=True)
    return {'proposal':write_new(PROPOSAL,proposal),'source_index':sources,'authorized':False}


if __name__=='__main__':
    print(json.dumps(seal(),ensure_ascii=False))

