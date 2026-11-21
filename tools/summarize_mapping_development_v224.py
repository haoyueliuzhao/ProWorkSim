"""Read-only live summary; plans, selected actions and scored results stay separate."""
import json,sqlite3,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'runs/software-benchmark-v224/development4-r1'
def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return None
def summary():
 rows=[]
 for row in read(R/'artifacts/software-benchmark-v224/protocol-r1/candidate-tasks.json')['rows']:
  p=O/f'task-{row["index"]:02d}';d=read(p/'decision.json');panel=read(p/'panel-result.json');b=read(p/'GENERATOR/candidate-bank.json');eps={}
  for z in ('PREFIX','KEEP','C1','C2'):
   result=read(p/z/'result.json');v=read(p/z/'progress.json');scored=read(p/(z+'-result.json'))
   if result:eps[z]={'status':result['status'],'logical_tokens':(v or {}).get('logical_total_tokens'),'last_tool':(v or {}).get('last_outcome',{}).get('decision',{}).get('action'),'progress_age_seconds':round(time.time()-v['at']) if v and v.get('at') else None,'scored':scored}
  rows.append({'index':row['index'],'instance_id':row['instance_id'],'phase':row['phase'],'episodes':eps,'decision':d,'candidate_count':len(b['candidates']) if b else None,'system_keep_fallback':b.get('system_keep_fallback') if b else None,'panel_complete':panel.get('complete') if panel else False})
 with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
  req=[{'status':a,'requests':b,'actual_tokens':t,'CNY_upper':cost} for a,b,t,cost in c.execute('SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE "v224:%" GROUP BY status')];paid=c.execute('SELECT COALESCE(sum(cost),0)/1e9 FROM requests WHERE status="settled"').fetchone()[0]
 f=read(O/'finished.json');p=read(O/'progress.json');policy=read(O/'policy-latest.json') or read(O/'policy-0.json')
 return {'finished':f,'live_phase':p.get('phase') if p else None,'states':p.get('states',{}) if p else {},'rows':rows,'actual_policy_updates':policy['update'] if policy else 0,'requests':req,'cumulative_paid_CNY_upper':paid,'remaining_global_CNY':1100-paid,'at':time.time()}
if __name__=='__main__':print(json.dumps(summary(),ensure_ascii=False,indent=2))
