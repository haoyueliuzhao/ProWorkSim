"""Read-only admission inventory of actual v131 multi-member controller receipts."""
from __future__ import annotations
import collections,hashlib,json,time,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parents[1]
BATCH=ROOT/'runs/software-benchmark-v131/fixed-organization-50-r1'
OUT=ROOT/'artifacts/software-benchmark-v203/material-admission-r1'
GROUPS=('CHIEF','PIPELINE','REVIEW','SPRINT','MATRIX')
def read(p):return json.loads(Path(p).read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def ref(p):
    p=Path(p);b=p.read_bytes();return {'path':str(p.resolve()),'sha256':sha(b),'bytes':len(b)}
def save(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
def inspect(row):
    p=BATCH/f'episodes/{row["slot_index"]}/controller-output/controller-result.json'
    base={k:row[k] for k in ['slot_id','slot_index','instance_id','organization_id','fixed_members']}
    if not p.exists():return {**base,'admitted':False,'reasons':['no_controller_record'],'controller':None}
    d=read(p);registry=d.get('actual_member_registry',{});sessions=d.get('private_sessions',{});outcomes=d.get('managed_boundary',{}).get('outcomes',[])
    successful=[];rejected=collections.Counter();counts=collections.Counter();owned_objects=collections.defaultdict(set);patches={};tasks={};handoffs=[];adoptions=[];tests={};deliveries=[];errors=[]
    for index,o in enumerate(outcomes):
        decision=o.get('decision',{});action=decision.get('action');actor=o.get('worker_id');response=o.get('response',{});args=decision.get('arguments',{});r=response.get('result',{})
        if not action or not o.get('action_performed'):continue
        if response.get('ok') is not True:rejected[action]+=1;continue
        if not isinstance(r,dict):continue
        witness={'index':index,'actor':actor,'action':action,'action_id':response.get('action_id'),'command_id':response.get('command_id'),'logical_time':response.get('logical_time')}
        successful.append(witness);counts[action]+=1
        if actor not in registry:errors.append([index,'actor_missing_registry'])
        v=r.get('source_reference')
        if v and action in {'read_file','list_files','search_file','search_repository','write_file','replace_file','create_file','delete_file','rename_file','integrate_patch','run_tests','fix_patch'} and not args.get('patch_id') and not args.get('source_reference'):
            owned_objects[actor].add(v['object_id'])
        if action in {'create_task','claim_task','return_task','revise_task','accept_transfer'} and r.get('task_id'):tasks[r['task_id']]=r
        if action=='fix_patch' and r.get('patch_id'):
            patches[r['patch_id']]={'author':r.get('author',actor),'version':v,'paths':r.get('changed_paths',[]),'files_sha256':r.get('files_sha256'),'witness':witness}
        if action=='handoff_patch':
            patch=patches.get(r.get('patch_id'));recipient=r.get('recipient')
            handoffs.append({**witness,'patch_id':r.get('patch_id'),'recipient':recipient,'patch':patch,'source_bound':bool(patch and patch['version'] and recipient in registry and recipient!=actor)})
        if action=='integrate_patch':
            patch=patches.get(args.get('patch_id'))
            adoptions.append({**witness,'patch_id':args.get('patch_id'),'recipient_version':v,'source_bound':bool(patch and patch['version'] and patch['author']!=actor and v)})
        if action in {'run_tests','read_test_result'} and r.get('report_id') and r.get('executed') is True:
            key=(actor,r['report_id']);old=tests.get(key)
            if old and (old['version']!=v or old['passed']!=r.get('passed')):errors.append([index,'test_identity_conflict'])
            tests[key]={'actor':actor,'report_id':r['report_id'],'version':v,'passed':r.get('passed'),'witness':witness}
        if action=='submit_integration':deliveries.append({**witness,'version':v})
    usage=d.get('member_usage',{});active=[m for m,u in usage.items() if u.get('attempts',0)>0 and u.get('known_actual_tokens',0)>0]
    # Separate private workspace objects must be observed, not inferred from role names.
    distinct_private=len({v for m in active for v in owned_objects[m]})>=2 and sum(bool(owned_objects[m]) for m in active)>=2
    criteria={'two_executed_members':len(active)>=2,'distinct_private_sessions':len({sessions.get(m) for m in active if sessions.get(m)})==len(active),
        'observed_separate_workspace_objects':distinct_private,'actual_successful_code_edit':any(counts[x] for x in ['write_file','replace_file','create_file','delete_file','rename_file']),
        'source_bound_cross_member_handoff':any(h['source_bound'] for h in handoffs),'test_or_delivery_evidence':bool(tests or deliveries),
        'explicit_owned_task':any(t.get('owner') in active for t in tasks.values()),'no_identity_conflicts':not errors}
    reasons=[k for k,v in criteria.items() if not v]
    return {**base,'admitted':not reasons,'reasons':reasons,'criteria':criteria,'controller':ref(p),'controller_status':d.get('status'),
        'cash_censored':d.get('cash_censored'),'actual_active_members':active,'private_sessions':sessions,'observed_private_object_ids':{k:sorted(v) for k,v in owned_objects.items()},
        'successful_tools':dict(counts),'rejected_tools':dict(rejected),'outcome_records':len(outcomes),'successful_receipts':len(successful),'source_bound_handoffs':handoffs,
        'source_bound_adoptions':adoptions,'owned_tasks':[{k:t.get(k) for k in ['task_id','owner','revision','status','depends_on']} for t in tasks.values()],
        'test_runs':list(tests.values()),'deliveries':deliveries,'member_usage':usage,'errors':errors,
        'baseline_snapshot_available':(p.parent/'project-baseline-snapshot.json').exists(),'raw_member_requests_available':(p.parent/'model-ledger').exists()}

def main():
    started=time.perf_counter();plan=read(BATCH/'execution-plan.json')
    save(OUT/'preinventory-policy.json',{'source':ref(Path(__file__)),'plan':ref(BATCH/'execution-plan.json'),
        'scope':'all250 original v131 rows; actual source receipts only, no official scores or success-based selection',
        'target_unique_instances':12,'minimum_modes':3,'mode_order':list(GROUPS),'seed':'v203-20261112-inventory',
        'criteria':['two actual model members','distinct private sessions and observed objects','successful code edit','source-bound cross-member handoff','test or delivery','explicit owned task','no identity conflicts'],
        'selection':'round robin mode order; within-mode SHA256(seed,instance_id,slot_id); unique instance across all modes; no duplicate inflation',
        'new_model_API':0,'new_runtime_or_Docker_operations':0})
    with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(inspect,plan['rows']))
    available={g:sorted([r for r in rows if r['organization_id']==g and r['admitted']],key=lambda r:sha(('v203-20261112-inventory'+r['instance_id']+r['slot_id']).encode())) for g in GROUPS}
    chosen=[];used=set()
    while len(chosen)<12:
        added=False
        for group in GROUPS:
            candidate=next((r for r in available[group] if r['instance_id'] not in used),None)
            if candidate:chosen.append(candidate);used.add(candidate['instance_id']);added=True
            if len(chosen)==12:break
        if not added:break
    summary={'rows':len(rows),'controller_records':sum(r['controller'] is not None for r in rows),'eligible_attempts':sum(r['admitted'] for r in rows),
        'eligible_unique_tasks':len({r['instance_id'] for r in rows if r['admitted']}),'by_mode':{g:{'records':sum(r['controller'] is not None for r in rows if r['organization_id']==g),'eligible':len(available[g])} for g in GROUPS},
        'exclusion_reasons':dict(collections.Counter(k for r in rows for k in r['reasons'])),'selected_unique_tasks':len(chosen),'selected_modes':dict(collections.Counter(r['organization_id'] for r in chosen)),
        'G0_inventory_pass':len(chosen)==12 and len({r['organization_id'] for r in chosen})>=3,'selection_is_not_random_population_sample':True,'wall_seconds':time.perf_counter()-started}
    save(OUT/'inventory.json',rows);save(OUT/'selection.json',chosen);save(OUT/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
