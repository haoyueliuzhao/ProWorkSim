"""Reconcile v229 development identities, official endpoints, activation records and supplier usage."""
from collections import Counter, defaultdict
from pathlib import Path
import sqlite3

from proworksim.storage import read_json,atomic_write,json_bytes,digest
from proworksim.software_benchmark_candidates_v054 import checked

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'runs/software-benchmark-v229'
ART=ROOT/'artifacts/software-benchmark-v229'
OUT=ART/'audit-20261124'/'reconciliation.json'
BATCHES=(('dev1-r1',range(4)),('dev1-extension-r1',range(16,20)),('dev1-balance90-r1',range(20,24)))
RECOVERY=RUN/'dev1-balance90-recovery-r1'


def ref(path):
    return {'path':str(path.relative_to(ROOT)),'sha256':digest(path.read_bytes())}


def main():
    with sqlite3.connect(f'file:{RUN}/dev1-r1/ledger.sqlite?mode=ro',uri=True) as c:
        entries=c.execute("""select slot,status,count(*),sum(json_extract(body,'$.input_tokens')),
            sum(json_extract(body,'$.output_tokens')),sum(tokens),sum(cost) from requests group by slot,status order by slot""").fetchall()
        cap=int(c.execute("select value from meta where key='cap'").fetchone()[0])
        assert not c.execute("select 1 from slots where status!='closed'").fetchone()
        assert not c.execute("select 1 from block_slots where status='pending'").fetchone()
    ledger=defaultdict(list)
    for slot,status,n,inp,out,tokens,cost in entries:
        namespace,task,arm=slot.split(':')
        assert namespace=='v229' and status=='settled' and inp+out==tokens
        ledger[int(task.removeprefix('task-'))].append(dict(slot=arm,requests=n,input=inp,output=out,tokens=tokens,nanoyuan=cost))
    tasks=[];receipts=0
    for batch,indices in BATCHES:
        for i in indices:
            old=RUN/batch/f'result-{i}.json'; end=RECOVERY/f'result-{i}.json'
            result_path=end if end.is_file() else old
            result=read_json(result_path);folder=result_path.parent/f'task-{i:02d}'
            item={'instance_id':result['instance_id'],'index':i,'batch':batch,'status':result['status'],
                  'original_record':ref(old),'final_record':ref(result_path),'ledger':ledger.pop(i,[]),'arms':{}}
            if 'bank' in result:
                b=result['bank']
                item['decision']={k:b[k] for k in ('kind','checkpoint','remaining','osa_tokens','osa_calls','choice','valid_nomination','decision')}
                item['decision'].update(subject=b['menu']['subject'],options=b['menu']['options'])
            candidates=result.get('arms') or ({'PREFIX':result['natural_episode']} if 'natural_episode' in result else {})
            for name,arm in candidates.items():
                assert arm['status']=='closed' and arm['instance_id']==item['instance_id']
                a={k:arm[k] for k in ('logical_tokens','termination','public_test_cost','mechanism','metrics','changed','checkpoint') if k in arm}
                a['endpoints']={}
                for kind in ('code','delivery'):
                    saved=arm['official'][kind];file=checked(saved['receipt']);raw=read_json(file)
                    assert raw['instance_id']==item['instance_id'] and raw['kind']==kind and not raw.get('cleanup_errors')
                    assert raw['resolved'] is saved['resolved'] and type(raw['resolved']) is bool and raw['status']==saved['status']
                    a['endpoints'][kind]={**ref(file),'status':raw['status'],'passed':raw['resolved'],'tree':raw.get('candidate_tree_sha256')}
                    receipts+=1
                if name!='PREFIX':
                    assert arm['checkpoint']==result['bank']['checkpoint']
                    assigned=folder/name/'assigned-graph.json';decision=read_json(assigned)
                    assert decision['changed']==arm['changed']
                    a['activation']=ref(assigned)
                if name=='CHANGE':
                    final=folder/name/'final-organization.json'
                    a['duties']=read_json(final)['graph']['duties']
                    a['final_organization']=ref(final)
                if result['status']=='paired':
                    boundary=folder/name/'boundary.json';ops=defaultdict(Counter)
                    for o in read_json(boundary)['outcomes']:
                        action=(o.get('decision') or {}).get('action') or o.get('status','unknown')
                        ops[o['worker_id']][action]+=1
                    a['successor_actions']=ops;a['boundary']=ref(boundary)
                item['arms'][name]=a
            if not candidates:assert result['status']=='cash_not_admitted' and not item['ledger']
            tasks.append(item)
    assert not ledger
    latest=RECOVERY/'window-result.json'
    summary={k:sum(row[k] for t in tasks for row in t['ledger']) for k in ('requests','input','output','tokens','nanoyuan')}
    payload={'scope':'v229 dev1 and two recruitment supplements; restored outcomes take precedence; earlier experiments excluded',
             'tasks':tasks,'counts':Counter(t['status'] for t in tasks),'official_endpoint_receipts':receipts,
             'settled_totals':summary,'account_cap_nanoyuan':cap,'remaining_nanoyuan':cap-summary['nanoyuan'],
             'latest_update':read_json(latest)['update'],'update_source':ref(latest)}
    atomic_write(OUT,json_bytes(payload))
    print(payload['counts'],receipts,summary,payload['remaining_nanoyuan'])


if __name__=='__main__':main()
