"""Resolve an evidenced candidate failure and complete the pending second update.

No model/scorer calls, old logs and old policy-1 unchanged.
"""
import copy,json,sqlite3
from pathlib import Path
from proworksim.storage import json_bytes
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_score_recovery_v217_1 import recover
from proworksim.software_organization_selector_v217 import update
R=Path(__file__).resolve().parents[1];OLD=R/'runs/software-benchmark-v217/selection28-r1';OUT=R/'artifacts/software-benchmark-v217/resilience-r1'
def read(p):return json.loads(p.read_text())
def save(p,v):
 if p.exists():raise ValueError('Keep old recovery evidence immutable')
 p.write_bytes(json_bytes(v))
assert read(OLD/'finished.json')['status']=='paused_infrastructure'
assert not (OLD/'policy-2.json').exists() and not (OLD/'confirm-results.json').exists()
with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
 assert not c.execute('SELECT 1 FROM slots WHERE status!="closed" LIMIT 1').fetchone()
 assert not c.execute("SELECT 1 FROM requests WHERE status='reserved' LIMIT 1").fetchone()
score=OLD/'task-04/scores/KEEP/code';raw=read(score/'receipt.json');canonical=recover(raw,score)
assert canonical and canonical['resolved'] is False
qualification=read(R/'runs/software-benchmark-v217/environment-r2/task-04/qualification.json');assert qualification['qualified']
for kind,ref in qualification['proof'].items():
 v=read(checked(ref));assert v['official_image']==raw['official_image'] and v['resolved']==(kind=='gold')
canonical['original_receipt']=reference(score/'receipt.json');canonical['environment_qualification']=reference(R/'runs/software-benchmark-v217/environment-r2/task-04/qualification.json');save(OUT/'task04-code-canonical.json',canonical)
records=copy.deepcopy(read(OLD/'dev2-results.json'));record=next(r for r in records if r['index']==4)
assert list(record['outcomes'])==['KEEP'] and record['outcomes']['KEEP']['status']=='scoring_unknown'
ep=OLD/'task-04/KEEP';g=read(ep/'progress.json');boundary=read(ep/'boundary.json')
record['outcomes']['KEEP']={'status':'scored','code_correct':False,'legal_correct':False,'formal_submission':g['lifecycle']['terminal']=='DELIVERED','logical_tokens':g['logical_total_tokens'],'episode':reference(ep/'result.json'),'scores':{'code':reference(OUT/'task04-code-canonical.json'),'delivery':reference(OLD/'task-04/scores/KEEP/delivery/receipt.json')},'normal_budget_stop':any('budget_exhausted' in x for x in boundary['role_stops'].values()),'recovery':'same original locked candidate; no new model or scoring'};record['complete']=True
assert all(r['complete'] for r in records)
save(OUT/'dev2-results-canonical.json',records)
policy=update(read(OLD/'policy-1.json'),records,'dev2');assert policy['update']==2
save(OUT/'policy-2.json',policy)
save(OUT/'recovery-receipt.json',{'old_records_unchanged':True,'original_phase_records':reference(OLD/'dev2-results.json'),'canonical_phase_records':reference(OUT/'dev2-results-canonical.json'),'policy1':reference(OLD/'policy-1.json'),'policy2':reference(OUT/'policy-2.json'),'complete_development_states':[r['index'] for r in records],'new_model_calls':0,'new_scoring_calls':0,'decision_before_confirmation':True})
print('Recovered exact candidate as failure; second update completed on',len(records),'states; 0 API and 0 scoring calls')
