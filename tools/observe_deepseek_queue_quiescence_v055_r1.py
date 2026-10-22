"""Read-only stopped-boundary proof for the v055 queue, excluding live Qwen work."""
import argparse
import fcntl
import json
from pathlib import Path
import re
import subprocess

from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.software_benchmark_queue_v055 import ROOT,now
from proworksim.storage import digest

QUEUE=ROOT/'runs/software-benchmark-v055/queue-r1'
PREFIXES=('proworksim-v055-generation-','proworksim-v055-score-','proworksim-v055-preparation-')
ACTIVE={'active','activating','deactivating','reloading','refreshing'}


def units(manager):
    argv=['systemctl']+(['--user'] if manager=='user' else [])
    response=subprocess.run(argv+['list-units','--all','--type=service','--output=json','--no-pager'],
        capture_output=True,text=True,check=True,timeout=30)
    return json.loads(response.stdout)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--coordinator',required=True);args=parser.parse_args()
    with (QUEUE/'coordinator.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=reference(QUEUE/'state.json');state=json.loads((QUEUE/'state.json').read_bytes())
        if state.get('status')!='budget_closed_with_pending' or state.get('dispatch_stopped') is not True:
            raise ValueError('Queue has not drained at the accounting-stop boundary')
        if any(row['generation']['status'] in ('running','intent') or
               any(x['status'] in ('running','intent','pending') for x in row['scores']) for row in state['rows']):
            raise ValueError('Generation/scoring inventory is not drained')
        if any(x.get('worker',{}).get('status') in ('running','intent') for x in state['preparation'].values()):
            raise ValueError('Preparation inventory is not drained')
        claim_ids=set();scopes=[];claim_refs=[]
        for row in state['rows']:
            claim_root=ROOT/'runs/software-benchmark-v055/episode-claims'/digest(row['slot']['slot_id'].encode())
            if row['generation']['status']=='pending':
                if claim_root.exists():raise ValueError('Pending original slot has a prior claim')
                continue
            if not (claim_root/'claim.json').exists():continue
            claim=json.loads((claim_root/'claim.json').read_bytes())
            if claim['slot']['slot_id']!=row['slot']['slot_id'] or not re.fullmatch('[a-f0-9]{32}',claim['claim_id']):
                raise ValueError('Claim identity changed')
            claim_ids.add(claim['claim_id']);claim_refs.append(reference(claim_root/'claim.json'))
            if (claim_root/'scope-registry.json').exists():
                for item in json.loads((claim_root/'scope-registry.json').read_bytes()):
                    if item['claim_id']!=claim['claim_id']:raise ValueError('Scope crossed episode identity')
                    scopes.append(item)
        active=[];loaded_observed=0
        for manager in ('user','system'):
            for item in units(manager):
                name=item['unit'];match=re.fullmatch(r'proworksim-v054-episode-([a-f0-9]{32})-[a-z]+\.service',name)
                owned=name.startswith(PREFIXES) or name==args.coordinator or (match and match.group(1) in claim_ids)
                if owned:
                    loaded_observed+=1
                    if item.get('active') in ACTIVE:active.append({'manager':manager,'unit':name,'active':item['active']})
        if active:raise ValueError('A v055-owned unit remains active: '+json.dumps(active))
        cgroups=set()
        for item in scopes:
            group=item.get('cgroup')
            if not isinstance(group,str) or not group.startswith('/') or '..' in Path(group).parts:
                raise ValueError('Invalid registered cgroup')
            cgroups.add(Path('/sys/fs/cgroup'+group))
        for claim in claim_ids:
            for parent in ('/sys/fs/cgroup','/sys/fs/cgroup/system.slice'):
                cgroups.add(Path(parent)/('proworksimv054ep'+claim+'.slice'))
        observed=0
        for group in cgroups:
            events=group/'cgroup.events'
            if events.exists():
                observed+=1;value=dict(x.split() for x in events.read_text().splitlines())
                if value.get('populated')!='0':raise ValueError('A registered v055 process tree remains populated: '+str(group))
        if reference(QUEUE/'state.json')!=before:raise ValueError('Stopped queue changed during observation')
        args.output=args.output.resolve();args.output.parent.mkdir(parents=True,exist_ok=True)
        print(write_new(args.output,{'version':'v055-drained-queue-real-quiescence-r1','observed_utc':now(),
            'queue_state':before,'coordinator':args.coordinator,'controller_lock_exclusive':True,
            'all_registered_scopes_inactive':True,'all_generation_scoring_preparation_workers_inactive':True,
            'queue_rows':len(state['rows']),'pending_original_slots':sum(x['generation']['status']=='pending' for x in state['rows']),
            'v055_claims_observed':len(claim_ids),'registered_scopes_observed':len(scopes),
            'loaded_owned_units_observed':loaded_observed,'existing_cgroups_checked':observed,
            'claim_manifest_list_sha256':digest(json.dumps(claim_refs,sort_keys=True).encode()),
            'unrelated_Qwen_units_excluded':True,'processes_signalled':0,'ledger_writes':0,
            'formal_queue_writes':0,'model_calls':0,'source':reference(__file__)}))

if __name__=='__main__':main()
