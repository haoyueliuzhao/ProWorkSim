"""Read-only v212 accounting and blocker evidence; preserve source results."""
from pathlib import Path
import collections,json,sqlite3
from proworksim.software_benchmark_candidates_v054 import reference
R=Path(__file__).resolve().parents[1];root=R/'runs/software-benchmark-v212/stage-a6-r1';out=R/'artifacts/software-benchmark-v213/v212-blockers-r1';out.mkdir(parents=True,exist_ok=True)
def load(p):return json.loads(p.read_text())
with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:usage={s:{'tokens':t,'cost_CNY_upper':cost/1e9,'requests':n} for s,t,cost,n in c.execute("SELECT slot,sum(tokens),sum(cost),count(*) FROM requests WHERE slot LIKE 'v212:%' AND status='settled' GROUP BY slot")}
rows=[]
for task in sorted(root.glob('task-*')):
 for z in ('SINGLE','COMBO'):
  p=task/z;g=load(p/'result.json');b=load(p/'boundary.json');d=load(p/'dynamic-final.json');errors=[];calls=collections.Counter()
  for o in b['outcomes']:
   tool=o.get('decision',{}).get('action');calls[tool or 'no_tool']+=1;e=o.get('response',{}).get('error')
   if e:errors.append({'tool':tool,'code':e.get('rejection',{}).get('code'),'message':e.get('message'),'arguments':o.get('decision',{}).get('arguments')})
  receipts={k:load(task/'scores'/z/k/'receipt.json') for k in ('code','delivery')}
  row={'instance_id':g['instance_id'],'condition':z,'generation_status':g['status'],'code':receipts['code']['resolved'],'delivery':receipts['delivery']['resolved'],'formal_delivery_present':receipts['delivery']['status']=='official_report','usage':usage[g['slot']],'stops':b['role_stops'],'tools':dict(calls),'errors':errors,'packages':d['delivery_gaps']['packages'],'joint_offers':d['joint_offers'],'first_submission_file':reference(p/'first-submission-usage.json') if (p/'first-submission-usage.json').exists() else None,'sources':{k:reference(p/k) for k in ('result.json','boundary.json','dynamic-final.json')},'initial_plan_followed_without_new_split':not(z=='SINGLE' and calls['split_work']>0)}
  # Inspect only the one event chain needed to establish the premature trigger.
  if task.name=='task-00' and z=='COMBO':
   w=load(p/'final-world.json');events=w['software_events'];row['midwork_event_order']=[{'sequence':e['sequence'],'kind':e['kind'],'actor':e['actor_id']} for e in events if e['kind'] in ('organization_v212:joint_offered','organization_v212:joint_accepted','organization_v212:work_performed','test')];row['coordinator_proposal']=load(p/'midwork-proposal.json')
  rows.append(row)
groups=[]
for z in ('SINGLE','COMBO'):
 rr=[r for r in rows if r['condition']==z];groups.append({'condition':z,'n':len(rr),'code_pass':sum(r['code'] for r in rr),'legal_delivery_pass':sum(r['delivery'] for r in rr),'formal_delivery_present':sum(r['formal_delivery_present'] for r in rr),'average_tokens':sum(r['usage']['tokens'] for r in rr)/len(rr),'cost_CNY_upper':sum(r['usage']['cost_CNY_upper'] for r in rr)})
(out/'evidence.json').write_text(json.dumps({'version':'v213-readonly-v212-blockers-r1','rows':rows,'groups':groups,'new_model_calls':0,'old_generation_or_scoring_modified':False,'interpretation':{'confirmed':'Misleading failed-test diagnostic; actual baseline failures; same-file merge conflicts; early midwork plan exposure; one SINGLE branch split autonomously','structural_risk_not_measured_causal_effect':'Whole-tree review identity conflicts with retaining independent local edits; new immutable review may help but gain not yet measured','budget_censoring':'All three COMBO and one SINGLE hit token reservation boundary; no cash cutoff'}},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(groups,ensure_ascii=False))
