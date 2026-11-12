"""Read actual historical request schemas; do not confuse exposure with eligibility."""
import collections,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from inventory_multimember_v203 import ROOT,read,ref,save,sha
ART=ROOT/'artifacts/software-benchmark-v203-2'
TOOLS=('declare_dependency','offer_transfer','accept_transfer')
def obj(text):
    try:return json.loads(text) if isinstance(text,str) else {}
    except (ValueError,TypeError):return {}
def one(row):
    folder=Path(row['controller']).parent;ledger=read(folder/'model-ledger/ledger.json');records=[];errors=[]
    for call in ledger['calls']:
        r=call.get('request')
        if not r:continue
        p=Path(r['path']);p=folder/'model-ledger'/p.parts[-2]/p.name;rr=ref(p)
        if rr['sha256']!=r['sha256'] or rr['bytes']!=r['bytes']:errors.append(str(p));continue
        wire=read(p)['request'];definitions={t['function']['name']:t['function'] for t in wire.get('tools',[]) if t.get('type')=='function'}
        member=call.get('member_id') or p.parent.name;system='\n'.join(str(m.get('content','')) for m in wire['messages'] if m.get('role')=='system')
        observation={};message_index=None
        for i,m in reversed(list(enumerate(wire['messages']))):
            if m.get('role')=='user':
                candidate=obj(m.get('content')).get('observation')
                if isinstance(candidate,dict):observation=candidate;message_index=i;break
        tasks=observation.get('tasks',[]);tasks=tasks if isinstance(tasks,list) else list(tasks.values())
        owned=[t for t in tasks if isinstance(t,dict) and t.get('owner')==member];offers=observation.get('transfer_offers',{})
        offers=list(offers.values()) if isinstance(offers,dict) else offers
        pending=[o for o in offers if o.get('status')=='pending' and o.get('recipient')==member]
        available=observation.get('member_availability',{});direct=observation.get('fixed_organization',{}).get('direct_recipients',[])
        possible_receivers=[m for m in direct if m!=member and available.get(m,{}).get('can_receive_work') is True]
        basic={'declare_dependency':bool(owned and len(tasks)>1),'offer_transfer':bool(owned and possible_receivers),'accept_transfer':bool(pending)}
        records.append({'request_id':call.get('request_id'),'usage_id':call.get('usage_id'),'member':member,'request':rr,'tool_count':len(definitions),
            'tools':{t:{'schema_present':t in definitions,'description_present':bool(definitions.get(t,{}).get('description')),'schema_sha256':sha(json.dumps(definitions[t],sort_keys=True).encode()) if t in definitions else None,
                'system_exact_name_mention':t in system,'latest_observation_exact_name_mention':t in json.dumps(observation),
                'checked_basic_conditions_satisfied':basic[t] if observation and observation.get('actor_id')==member else None} for t in TOOLS},
            'observation_message_index':message_index,'observation_logical_time':observation.get('logical_time'),'task_count_reported':observation.get('task_count'),
            'task_records_visible':len(tasks),'owned_task_count':len(owned),'direct_available_recipient_count':len(possible_receivers),
            'complete_runtime_authorization_not_replayed':True})
    save(ART/f'tool-exposure-r1/task-{row["slot_index"]}.json',{'instance_id':row['instance_id'],'mode':row['organization_id'],'records':records,'errors':errors})
    return row,records,errors
def main():
    panel=read(ROOT/'artifacts/software-benchmark-v203-1/panel-r1/plan.json')['rows']
    save(ART/'tool-exposure-r1/protocol.json',{'source':ref(Path(__file__)),'panel':ref(ROOT/'artifacts/software-benchmark-v203-1/panel-r1/plan.json'),
        'agent_and_condenser_separate':True,'eligibility_scope':'visible ownership/other task or allowed reachable recipient or pending addressed offer only; no proof of all governance, cycle and stage gates',
        'no_API_or_mutation':True})
    with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,panel))
    records=[r for _,rs,_ in rows for r in rs];agent=[r for r in records if r['usage_id']=='agent'];summary={'tasks':len(rows),'all_requests':len(records),'agent_requests':len(agent),
        'condenser_or_other_requests':len(records)-len(agent),'errors':[e for _,_,es in rows for e in es],'tools':{}}
    for t in TOOLS:
        summary['tools'][t]={k:sum(r['tools'][t][k] is True for r in agent) for k in ['schema_present','description_present','system_exact_name_mention','latest_observation_exact_name_mention','checked_basic_conditions_satisfied']}
        summary['tools'][t]['tasks_with_schema']=sum(any(r['usage_id']=='agent' and r['tools'][t]['schema_present'] for r in rs) for _,rs,_ in rows)
        summary['tools'][t]['tasks_with_checked_basic_conditions']=sum(any(r['usage_id']=='agent' and r['tools'][t]['checked_basic_conditions_satisfied'] for r in rs) for _,rs,_ in rows)
        summary['tools'][t]['unknown_basic_condition_requests']=sum(r['tools'][t]['checked_basic_conditions_satisfied'] is None for r in agent)
    summary['equivalent_paths']=['fixed publication then direct read/integrate without directed handoff','claim_task/return_task with original constraints; not equivalent to atomic accepted transfer','organization assignment approvals; not ownership by themselves']
    summary['source_guards']=[ref(ROOT/p) for p in ['src/proworksim/software_fixed_organization_world_v065.py','src/proworksim/software_organization_v038.py','src/proworksim/software_organization_governance_v104.py','src/proworksim/software_organization_flow_v104.py']]
    save(ART/'tool-exposure-r1/summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
