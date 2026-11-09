"""Freeze the concrete user-authorized context pilot before paid work."""
import importlib.util
import json
import shutil
import sqlite3
from pathlib import Path
from proworksim import software_benchmark_scope_v181 as scope
from proworksim import software_benchmark_sdk_bundle_v181 as bundle
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_benchmark_alignment_contract_v181 import VERSION as ALIGNMENT_VERSION


def main():
    if scope.AUTH_FILE.exists():raise ValueError('Do not reseal an admitted runtime')
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    sdk=scope.load(reference(scope.BATCH_ROOT.parent/'sdk-controls-r4/summary.json'))
    reader=scope.load(reference(scope.BATCH_ROOT.parent/'sdk-live-reader-r1/summary.json'))
    if sdk.get('passed') is not True or reader.get('passed') is not True:raise ValueError('Actual SDK controls must pass')
    packed=bundle.prepare_bundle()
    for ref in [*packed['source_tools'].values(),*packed['project_modules'].values()]:checked(ref)
    with sqlite3.connect(scope.LEDGER_FILE.as_uri()+'?mode=ro',uri=True) as db:
        if db.execute("SELECT count(*) FROM jobs WHERE status='running'").fetchone()[0]:raise ValueError('Old ledger is active')
        backup=scope.BATCH_ROOT/'ledger-before-v181.sqlite'
        with sqlite3.connect(backup) as output:db.backup(output)
    grant=scope.retain(scope.USER_GRANT_FILE,{'approved':True,'user_task':'按照审计继续实验',
        'cash_reply':'沿用旧账本，累计上限仍250元','standing_docker':'非干扰实验Docker/API无需另行请求',
        'start_only_cash_preference':'后续任务若已经开始运行则不因为金额上限做中断',
        'no_shared_host_configuration_changes':True,'plan':reference(scope.PLAN_FILE)})
    proposal=scope.retain(scope.PROPOSAL_FILE,{'version':scope.VERSION,'plan':reference(scope.PLAN_FILE),
        'constraints':scope.CONSTRAINTS,'user_grant':grant,'primary':48,'repeats':12,
        'same_ledger_cumulative_cash_CNY':250,'no_new_cash_allowance':True,
        'API_dispatch_requires_successful_zero_model_diagnostics_and_task_controls':True,
        'started_episodes_finish_above_cash_line':True,'estimated_start_hold_CNY_per_episode':5})
    spec=importlib.util.spec_from_file_location('v181_source_closure',scope.ROOT/'tools/seal_role_pilot_v143.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    roots=[p for folder in ('src/proworksim','tools','tests') for p in (scope.ROOT/folder).glob('*v181.py')]
    files=module.source_closure(roots=roots)
    gate=scope.retain(scope.ARTIFACT_ROOT/'sdk-gate-r1/summary.json',{'passed':True,
        'SDK_controls':reference(scope.BATCH_ROOT.parent/'sdk-controls-r4/summary.json'),
        'actual_private_reader_control':reference(scope.BATCH_ROOT.parent/'sdk-live-reader-r1/summary.json'),
        'cash_CPU_tests':reference(scope.BATCH_ROOT.parent/'cash-cpu-tests.json'),
        'scope':'SDK and local accounting; real Docker qualification follows before API',
        'no_provider_exact_source_token_claim':True,'actual_benchmark_model_calls':0})
    files += [reference(bundle.OUTPUT/'manifest.json'),packed['archive'],reference(scope.PLAN_FILE),
        gate,proposal,grant,reference(scope.ROOT/'docs/experiments/software-benchmark-v181-context-task-execution.md')]
    sources=scope.retain(scope.SOURCE_FILE,{'version':scope.VERSION,'files':files,'old_ledger_backup':reference(backup),
        'gate':gate,'paid_model_calls_at_freeze':0})
    auth=scope.retain(scope.AUTH_FILE,{'version':scope.VERSION,'status':'approved','plan':reference(scope.PLAN_FILE),
        'source_index':sources,'constraints':scope.CONSTRAINTS,'execution_alignment_version':ALIGNMENT_VERSION,
        'cash_cap_CNY':'250.00','proposal':proposal,'user_grant':grant,'gate':gate})
    scope.require_allowed()
    print(json.dumps({'sealed':True,'authorization':auth,'source_files':len(files),'Docker_operations':0,'API_calls':0}))


if __name__=='__main__':main()
