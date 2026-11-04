"""Freeze a concrete PROJECT rerun proposal; grant is recorded separately."""
from __future__ import annotations
import ast
import json
from pathlib import Path
from proworksim import software_benchmark_scope_v118 as scope
from proworksim.software_benchmark_candidates_v054 import reference,write_new,checked

PROPOSAL=scope.ROOT/'artifacts/software-benchmark-v118/runtime-authorization-r1/proposal.json'
ENTRIES=('tools/run_project_rerun_v118.py','tools/launch_project_rerun_v118.py',
 'tools/summarize_project_rerun_v118.py','tools/prepare_project_panel_v118.py',
 'tools/prepare_project_runtime_v118.py','tools/seal_project_rerun_v118.py',
 'tools/run_project_controller_v118.py','tools/run_managed_worker_docker_v118.py',
 'tools/run_native_worker_docker_v118.py','tools/run_public_tests_v118.py',
 'tools/public_test_library_v118.py','tools/public_test_dependencies_v118.py',
 'tools/public_fixture_diagnostic_v118.py','tools/run_offline_scorer_v096.py',
 'src/proworksim/software_benchmark_grading_v118.py',
 'src/proworksim/software_benchmark_host_api_v118.py',
 'src/proworksim/software_benchmark_sdk_bundle_v118.py',
 'src/proworksim/software_benchmark_episode_v118.py')

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
    from proworksim import software_benchmark_sdk_bundle_v118 as bundle
    from proworksim import software_benchmark_host_api_v118 as host
    from proworksim.software_benchmark_alignment_contract_v117 import VERSION as ALIGNMENT
    from proworksim.software_benchmark_generation_admission_v118 import diagnostic_descriptor
    if scope.AUTH_FILE.exists() or scope.SOURCE_FILE.exists() or PROPOSAL.exists():
        raise PermissionError('Do not reseal an entered/authorized preparation')
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    cash=scope.load(reference(scope.BUDGET_BASELINE_FILE))
    if (cash['ledger_path']!=str(scope.LEDGER_FILE) or cash['cash_budget_scope']!=scope.CASH_MODE
            or cash['budget_increased'] is not False or cash['totals_nanoyuan']['inflight']!=0):
        raise ValueError('Preserve the existing idle cumulative cash ledger')
    bundle_ref=reference(bundle.OUTPUT/'manifest.json')
    b=scope.load(bundle_ref)
    for ref in (*b['source_tools'].values(),*b['project_modules'].values()):
        checked(ref)
    schemas_ref=reference(host.SCHEMAS)
    schemas=scope.load(schemas_ref)
    if schemas['runtime_bundle']!=bundle_ref or set(schemas['schemas'])!={'PROJECT'}:
        raise ValueError('Only the actual new PROJECT tool route is admitted')
    controls={}
    for name,path in (
        ('scope','scope-controls-r1/summary.json'),
        ('public_certificates','public-fixture-certificate-controls-r1/summary.json'),
        ('selected_entry','generation-admission-r1/selected-entry-control.json'),
        ('runtime','runtime-controls-r1/summary.json'),
        ('zero_model_factory','diagnostic-factory-controls-r1/summary.json'),
        ('grading_evaluator','concrete-evaluator-control-r1/summary.json'),
        ('grading_preparation','grading-transport-control-r1/preparation.json'),
        ('generation_preparation','generation-admission-r1/preparation-summary.json')):
        ref=reference(scope.ROOT/'artifacts/software-benchmark-v118'/path)
        value=scope.load(ref)
        if name != 'generation_preparation' and value.get('passed') is not True:
            raise ValueError('Necessary preparation control did not pass: '+name)
        if name == 'generation_preparation' and not all(value.get(key) is True for key in (
                'v117_archive_hash_valid','original_2931_public_baseline_matches_profile',
                'changed_baseline_rejected','diagnostic_gate_positive_and_negative_CPU_controls',
                'public_helpers_parse_as_python39')):
            raise ValueError('Generation public environment preparation did not qualify')
        controls[name]=ref
    actual=scope.load(controls['grading_preparation'])
    if (len(actual.get('reused_unchanged_environments', [])) != 48
            or len(actual.get('prepared_fresh_control_requests', [])) != 4
            or actual.get('fresh_controls_executed') != 0):
        raise ValueError('Grading preparation count changed')
    # Complete candidate inventories remain fixed even when qualification is unknown.
    if len(plan['rows'])!=50 or len(plan['diagnostics'])!=1:
        raise ValueError('Incomplete original panel')
    preparation_refs=[reference(path) for path in (
        scope.PLAN_FILE,scope.PANEL_FILE,scope.CPU_POOL_FILE,scope.BUDGET_BASELINE_FILE,
        scope.NETWORK_RESOLUTION_FILE,scope.CA_PROFILE_FILE,host.SCHEMAS,
        bundle.OUTPUT/'manifest.json',scope.API_ROOT/'coordinator-unit.json',
        scope.ROOT/'artifacts/software-benchmark-v118/public-dependencies-r1/manifest.json')]
    files=source_closure()+preparation_refs
    source_index=write_new(scope.SOURCE_FILE,{'version':scope.VERSION,'files':files,
        'controls':controls,'execution_started':False,'model_calls':0,'Docker_operations':0})
    value={'version':scope.VERSION,'status':'prepared','user_instruction':'对project组重新进行实验',
        'execution_alignment_version':ALIGNMENT,'plan':reference(scope.PLAN_FILE),
        'source_index':source_index,'constraints':scope.CONSTRAINTS,'controls':controls,
        'API_cash_cap_CNY':scope.CASH_CAP_CNY,'cash_budget_scope':scope.CASH_MODE,
        'ledger_path':str(scope.LEDGER_FILE),'cash_before_run':reference(scope.BUDGET_BASELINE_FILE),
        'cash_remaining_before_run_CNY':cash['remaining_CNY'],'additional_cash':0,
        'new_generation_attempts':50,'new_groups':['PROJECT'],'new_aggregate_task_tokens_upper_bound':250000000,
        'maximum_containers':302,'maximum_named_volumes':51,'maximum_actor_pairs':16,
        'maximum_graders':2,'combined_CPU':112,'combined_memory_GiB':576,
        'maximum_official_control_containers':100,'expected_reused_official_qualifications':48,
        'initial_new_TLS_controls':4,'automatic_score_retries':False,
        'generation_diagnostic_pairs':1,'public_fixture_diagnostic':diagnostic_descriptor(),
        'neutral_API_calls':1,'neutral_total_tokens_upper_bound':4096,'metadata_API_requests':0,
        'network_resolution':reference(scope.NETWORK_RESOLUTION_FILE),'CA_profile':reference(scope.CA_PROFILE_FILE),
        'maximum_TLS_sessions':8,'maximum_external_grading_connections':4096,
        'maximum_external_grading_payload_bytes':512*1024**2,
        'external_grading_destination':'httpbin.org','external_grading_ports':[80,443],
        'TLS_grading_serial':True,'container_network':'none','container_cap_drop':['ALL'],
        'scoring_only_private_caps':['NET_ADMIN','NET_BIND_SERVICE'],
        'host_binds':0,'host_listeners':0,'GPUs':0,'system_slice_created':False,
        'ordinary_user_unit':scope.API_UNIT,'shared_host_configuration_changes':0,
        'new_ref_model_attempts':0,'existing_generations_or_scores_overwritten':False,
        'old_v116_recovery_started':False,'server_search_or_fetch_enabled':False,
        'API_direct_TLS_no_proxy':True,'source_bundle':bundle_ref,'actual_PROJECT_schemas':schemas_ref,
        'execution_started':False,'runtime_authorized':False,
        'grading_preparation_summary_keys':sorted(actual)}
    PROPOSAL.parent.mkdir(parents=True,exist_ok=True)
    return {'proposal':write_new(PROPOSAL,value),'source_index':source_index,'runtime_authorized':False}

if __name__=='__main__':
    print(json.dumps(seal(),ensure_ascii=False))
