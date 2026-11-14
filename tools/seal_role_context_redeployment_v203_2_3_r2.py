"""Seal fresh physical deployment and diagnostic without adding any API allowance."""
from __future__ import annotations
import importlib.util,json,shutil,sqlite3
from pathlib import Path
from proworksim import software_benchmark_scope_v203_2_3_r2 as scope
from proworksim import software_benchmark_alignment_contract_v203_2_3 as alignment
from proworksim.software_benchmark_candidates_v054 import reference,checked

VERSION='v203.2.3-zero-provider-redeployment-seal-r2'
SNAPSHOT=scope.ARTIFACT_ROOT/'source-snapshot-r2'
REQUIRED=(
'src/proworksim/software_benchmark_scope_v203_2_3_r2.py',
'src/proworksim/software_benchmark_episode_v203_2_3_r2.py',
'src/proworksim/software_benchmark_host_api_v203_2_3_r2.py',
'src/proworksim/software_benchmark_grading_redeployment_v203_2_3_r2.py',
'src/proworksim/software_benchmark_requests_recovery_v203_2_3_r3.py',
'src/proworksim/software_benchmark_preparation_grading_v203_2_3_r3.py',
'src/proworksim/software_benchmark_grading_v203_2_3_r3.py',
 'tools/run_role_context_pilot_v203_2_3_r2.py','tools/launch_role_context_pilot_v203_2_3_r2.py',
 'tools/run_role_context_diagnostic_v203_2_3_r2.py','tools/launch_role_context_diagnostic_v203_2_3_r2.py',
 'tools/recover_role_context_cash_admissions_v203_2_3_r2.py',
 'tools/prepare_role_context_redeployment_v203_2_3_r2.py',
 'tools/seal_role_context_redeployment_v203_2_3_r2.py','tools/check_role_context_cpu_lanes_v203_2_3_r2.py')


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def seal():
    if scope.SOURCE_FILE.exists() or scope.AUTH_FILE.exists() or list((scope.BATCH_ROOT/'resource-claims').glob('*.json')):
        raise PermissionError('Cannot reseal an entered new deployment')
    gate=scope.require_common_gate()
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    proof=scope.load(plan['zero_provider_redeployment_evidence'])
    with sqlite3.connect(scope.LEDGER_FILE.resolve().as_uri()+'?mode=ro',uri=True) as db:
        if db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]:raise PermissionError('No paid attempt may be replayed')
        if [list(r) for r in db.execute('SELECT slot_id,state FROM team_admissions ORDER BY slot_id')]!=proof['team_admissions']:
            raise PermissionError('Predecessor closed admissions changed before the diagnostic')
    from proworksim import software_benchmark_sdk_bundle_v203_2_3 as bundle
    from proworksim import software_benchmark_host_api_v203_2_3_r2 as host
    from proworksim import software_benchmark_grading_redeployment_v203_2_3_r2 as grading
    manifest_ref=reference(bundle.OUTPUT/'manifest.json');manifest=scope.load(manifest_ref)
    if manifest.get('adapter')!=reference(bundle.__file__) or manifest.get('version')!=bundle.VERSION:
        raise PermissionError('Frozen model-visible bundle changed during recovery')
    for ref in (*manifest['source_tools'].values(),*manifest['project_modules'].values(),manifest['archive'],manifest['member_inventory'],manifest['probe_source']):checked(ref)
    schemas=host.prepare_schemas()
    index_ref=reference(scope.COORDINATOR_ROOT/'qualification-completion-index.json');index=scope.load(index_ref)
    scoring=grading.scorer(scope.dispatch_view())
    if len(index['qualifications'])!=3 or set(index['pending_tasks'])!={'psf__requests-1766'}:raise PermissionError('Recovery retains ready9 and pending3')
    for task,qref in index['qualifications'].items():
        scoring.validate_qualification(qref,scope.load(plan['environments'][task]['configuration']),reference(scope.PLAN_FILE))
    units=[]
    for stem in ('launch_role_context_pilot_v203_2_3_r2','launch_role_context_diagnostic_v203_2_3_r2'):
        units.append(module(scope.ROOT/'tools'/(stem+'.py'),stem).prepare()['specification'])
    old=module(scope.ROOT/'tools/seal_role_pilot_v142.py','source_reader_recovery_r2')
    roots=[scope.ROOT/name for name in REQUIRED]+[Path(r['path']) for r in (*manifest['source_tools'].values(),*manifest['project_modules'].values())]
    code=old.source_closure(scope.ROOT,roots=roots);snapshots=[]
    for ref in code:
        source=Path(ref['path']);target=SNAPSHOT/source.relative_to(scope.ROOT);target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if target.read_bytes()!=source.read_bytes():raise PermissionError('Recovery source snapshot changed')
        else:shutil.copyfile(source,target)
        snapshots.append({'source':ref,'snapshot':reference(target)})
    snapshot_ref=scope.retain(SNAPSHOT/'manifest.json',{'version':VERSION,'files':snapshots,'old_frozen_sources_changed':False})
    files=code+[reference(p) for p in (scope.PLAN_FILE,scope.PANEL_FILE,scope.CPU_POOL_FILE,scope.BUDGET_BASELINE_FILE,
        scope.PREVIOUS_BATCH_ROOT/'execution-plan.json',scope.PREVIOUS_BATCH_ROOT/'runtime-sources.json',
        scope.ARTIFACT_ROOT/'runtime-gates-r2/gate.json',scope.COORDINATOR_ROOT/'pending-qualification-plan.json',
        scope.ARTIFACT_ROOT/'cpu-lane-controls-r2/summary.json')]
    files += [manifest_ref,schemas,index_ref,snapshot_ref,plan['zero_provider_redeployment_evidence'],*units,*gate['evidence']]
    for row in plan['rows']:
        config=scope.load(row['configuration']);files += [row['configuration'],config['configuration'],config['public_tasks'],config['public_test_registry'],config['scorer_request_base']['dataset'],config['scorer_request_base']['baseline_mapping']]
    files += list(index['qualifications'].values())+[reference(scope.GRADING_ROOT/'environments/bindings.json')]
    files=list({r['path']:r for r in files}.values())
    source_ref=scope.retain(scope.SOURCE_FILE,{'version':scope.VERSION,'files':files,'source_snapshot':snapshot_ref,
        'bundle_archive':manifest['archive'],'runtime_receipts_and_same_cash_ledger_excluded':True})
    proposal=scope.retain(scope.PROPOSAL_FILE,{'version':VERSION,'plan':reference(scope.PLAN_FILE),'source_index':source_ref,
        'constraints':scope.CONSTRAINTS,'same_existing_ledger':str(scope.LEDGER_FILE),'same_cash_CNY':'130.00','additional_cash_CNY':'0.00',
        'logical_slots_and_seeds_unchanged':True,'old_failures_preserved':True,'one_actual_zero_model_diagnostic_required':True,'units':units})
    grant=scope.retain(scope.USER_GRANT_FILE,{'version':VERSION,'status':'approved','proposal':proposal,
        'authority_source':'Existing user authorization covers noninterfering diagnostic and repair. The same original CNY130 allowance and zero-provider logical attempts are preserved; no added cash or model resampling.',
        'original_grant':reference(scope.ARTIFACT_ROOT/'runtime-authorization-r1/user-authority.json')})
    authority=scope.retain(scope.AUTH_FILE,{'version':scope.VERSION,'status':'approved','execution_alignment_version':alignment.VERSION,
        'plan':reference(scope.PLAN_FILE),'source_index':source_ref,'proposal':proposal,'API_cash_cap_CNY':scope.CASH_CAP_CNY,
        'cash_budget_scope':scope.CASH_MODE,'ledger_paths':{g:str(p) for g,p in scope.LEDGER_FILES.items()},
        'constraints':scope.CONSTRAINTS,'shared_host_configuration_changes':0,'user_grant':grant,'additional_cash_CNY':'0.00'})
    return {'authorization':authority,'source_index':source_ref,'static_source_files':len(code),'API_calls':0,'Docker_operations':0}

if __name__=='__main__':print(json.dumps(seal()))
