"""Separate absent explicit behavior from missing/unattributed recording."""
import collections,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from inventory_multimember_v203 import ROOT,read,ref,save
ART=ROOT/'artifacts/software-benchmark-v203-1'
TARGET={'declare_dependency','offer_transfer','accept_transfer','clear_dependency','return_task'}
def inspect(row):
    folder=Path(row['controller']).parent;p=folder/'model-ledger/ledger.json';errors=[];requested=collections.Counter();witnesses=[];verified=0;missing=0
    if not p.exists():return {'instance_id':row['instance_id'],'source_gap':'member_ledger_missing'}
    ledger=read(p)
    for call in ledger.get('calls',[]):
        r=call.get('response')
        if not r:missing+=1;continue
        parts=Path(r['path']).parts;actual=folder/'model-ledger'/parts[-2]/parts[-1]
        if not actual.exists():errors.append({'kind':'response_file_missing','path':str(actual)});continue
        rr=ref(actual)
        if rr['sha256']!=r['sha256'] or rr['bytes']!=r['bytes']:errors.append({'kind':'response_hash_mismatch','path':str(actual)});continue
        verified+=1
        for choice in read(actual).get('choices',[]):
            for tc in choice.get('message',{}).get('tool_calls',[]):
                name=tc.get('function',{}).get('name');requested[name]+=1
                if name in TARGET:witnesses.append({'tool':name,'arguments':tc['function'].get('arguments'),'member':call.get('member_id'),
                    'tool_call_id':tc.get('id'),'response':rr,'request_id':call.get('request_id')})
    controller=read(row['controller']);events=controller.get('managed_boundary',{}).get('outcomes',[]);dispatched=collections.Counter();accepted=collections.Counter();rejections=[]
    for e in events:
        d=e.get('decision',{});name=d.get('action');r=e.get('response',{})
        if name not in TARGET or not e.get('action_performed'):continue
        dispatched[name]+=1
        if r.get('ok') is True:accepted[name]+=1
        else:rejections.append({'tool':name,'member':e['worker_id'],'error':r.get('error'),'command_id':r.get('command_id')})
    return {'instance_id':row['instance_id'],'slot_index':row['slot_index'],'group':row['organization_id'],'ledger':ref(p),'verified_provider_responses':verified,
        'calls_without_response_ref':missing,'response_errors':errors,'raw_model_tool_requests':{k:requested[k] for k in sorted(TARGET)},
        'managed_dispatches':dict(dispatched),'managed_successes':dict(accepted),'target_call_witnesses':witnesses,'target_rejections':rejections,
        'conclusion':'absence_of_target_calls_in_available_raw_responses_is_not_a_missing_event_in_observer; missing responses remain uncertain',
        'usage':'full-attempt recording audit only; never features or labels for the prefix comparison'}
def main():
    panel=read(ART/'panel-r1/plan.json');inventory=read(ROOT/'artifacts/software-benchmark-v203/material-admission-r1/inventory.json')
    save(ART/'observability-r1/protocol.json',{'source':ref(Path(__file__)),'panel':ref(ART/'panel-r1/plan.json'),'no_new_API':True,'reviewers_must_not_read_this_future_aware_diagnostic':True})
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(inspect,panel['rows']))
    for row in results:save(ART/f'observability-r1/task-{row.get("slot_index",row["instance_id"])}.json',row)
    recorded=[r for r in inventory if r.get('controller')];nohandoff=[r for r in recorded if not any(h['source_bound'] for h in r.get('source_bound_handoffs',[]))]
    summary={'recorded_controllers':len(recorded),'no_explicit_source_bound_handoff':len(nohandoff),
        'no_handoff_but_actual_source_bound_peer_adoption':sum(any(a['source_bound'] for a in r.get('source_bound_adoptions',[])) for r in nohandoff),
        'no_final_owned_task':sum(not r['criteria']['explicit_owned_task'] for r in recorded),
        'no_task_board_entries':sum(not r['owned_tasks'] for r in recorded),
        'no_task_board_is_not_an_observer_or_organization_failure':True,'audited_selected_tasks':len(results),
        'verified_provider_responses':sum(r.get('verified_provider_responses',0) for r in results),
        'raw_model_tool_requests':dict(sum((collections.Counter(r.get('raw_model_tool_requests',{})) for r in results),collections.Counter())),
        'managed_dispatches':dict(sum((collections.Counter(r.get('managed_dispatches',{})) for r in results),collections.Counter())),
        'managed_successes':dict(sum((collections.Counter(r.get('managed_successes',{})) for r in results),collections.Counter())),
        'response_errors':[e for r in results for e in r.get('response_errors',[])],'calls_without_response_ref':sum(r.get('calls_without_response_ref',0) for r in results),
        'source_gap_tasks':[r for r in results if r.get('source_gap')],'new_model_API':0}
    save(ART/'observability-r1/summary.json',summary);print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
