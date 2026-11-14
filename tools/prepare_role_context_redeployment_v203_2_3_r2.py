"""Retain zero-provider failure evidence and prepare fresh physical identities."""
from __future__ import annotations
from collections import Counter
import copy,json,sqlite3
from pathlib import Path
from proworksim import software_benchmark_scope_v203_2_3_r2 as scope
from proworksim import software_benchmark_scope_v203_2_3 as previous
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import declaration


def prepare():
    old=previous.load(reference(previous.PLAN_FILE))
    if list((previous.BATCH_ROOT/'resource-claims').glob('active-*.json')):
        raise PermissionError('All predecessor resources must be released')
    final=previous.load(reference(previous.API_ROOT/'coordinator-finalization.json'))
    if final['cleanup_errors'] or not previous.load(final['coordinator_release'])['released']:
        raise PermissionError('Previous coordinator did not close')
    closed=[]
    for row in old['rows']:
        folder=previous.BATCH_ROOT/'episodes'/str(row['slot_index'])
        if not (folder/'result.json').exists():continue
        result=previous.load(reference(folder/'result.json'));quiet=previous.load(result['quiescence'])
        if (result.get('controller_result') is not None or result.get('error',{}).get('message')!='The fixed host CPU pool does not cover the reviewed runtime slices'
                or quiet.get('quiescent') is not True or quiet.get('removed_roles')!=[]
                or quiet.get('create_result_unknown') is not False or quiet.get('all_owned_objects_removed') is not True):
            raise PermissionError('Recovery requires the exact pre-Docker/pre-controller CPU guard failure')
        closed.append({'row':row,'result':reference(folder/'result.json'),'quiescence':result['quiescence']})
    with sqlite3.connect(previous.LEDGER_FILE.resolve().as_uri()+'?mode=ro',uri=True) as db:
        requests=db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]
        admissions=[list(row) for row in db.execute('SELECT slot_id,state FROM team_admissions ORDER BY slot_id')]
    if requests or len(closed)!=9 or len(admissions)!=9 or any(state!='closed' for _,state in admissions):
        raise PermissionError('Only nine proven zero-provider closed attempts may get new physical identities')
    proof=scope.retain(scope.ARTIFACT_ROOT/'zero-provider-redeployment-r2/evidence.json',{
        'version':scope.VERSION,'passed':True,'original_plan':reference(previous.PLAN_FILE),'original_source_index':reference(previous.SOURCE_FILE),
        'coordinator_finalization':reference(previous.API_ROOT/'coordinator-finalization.json'),'closed_rows':closed,
        'provider_requests':0,'controllers_started':0,'containers_created':0,'team_admissions':admissions,
        'same_existing_ledger':str(previous.LEDGER_FILE),'additional_cash_CNY':'0.00','original_twelve_logical_ids_unchanged':True})
    cpu=scope.retain(scope.CPU_POOL_FILE,scope.load(reference(previous.CPU_POOL_FILE)))
    resources={k:copy.deepcopy(v) for k,v in old['resources'].items() if v['role'] in {'actor','controller','volume','score','delivery_score'}}
    row=old['rows'][0]
    diagnostic={'index':1,'slot_id':row['slot_id'],'instance_id':row['instance_id'],'organization_id':'REVIEW2','group_id':row['group_id'],'model_calls':0}
    for role in ('actor','controller','volume'):
        resources[f'diagnostic-1-{role}']={**copy.deepcopy(resources[f'{role}-{row["slot_index"]}']),
            'diagnostic':True,'diagnostic_index':1}
    inventory=scope.retain(scope.INVENTORY_FILE,{'version':scope.VERSION,'rows':old['rows'],'generation':{},'scores':{},'deliveries':{}})
    plan={**copy.deepcopy(old),'version':scope.VERSION,'root':str(scope.BATCH_ROOT),'host_cpu_pool':cpu,'inventory':inventory,
        'constraints':scope.CONSTRAINTS,'resources':resources,'resource_role_counts':dict(Counter(v['role'] for v in resources.values())),
        'public_qualifications':[],'diagnostics':[diagnostic],'dispatch_admission':declaration(scope.BATCH_ROOT),
        'zero_provider_redeployment_evidence':proof,'previous_plan':reference(previous.PLAN_FILE),'new_ledger':str(scope.LEDGER_FILE),
        'new_API_budget_CNY':'0.00','same_original_cash_CNY':'130.00'}
    scope.validate_plan(plan)
    ref=scope.retain(scope.PLAN_FILE,plan)
    old_index=previous.load(reference(previous.COORDINATOR_ROOT/'qualification-completion-index.json'))
    scope.retain(scope.COORDINATOR_ROOT/'qualification-completion-index.json',{**old_index,'plan':ref})
    # Pending Requests now has its exact terminal failure; preserve all12 denominator.
    return {'plan':ref,'evidence':proof,'model_calls':0,'new_budget_CNY':'0.00'}


if __name__=='__main__':print(json.dumps(prepare()))
