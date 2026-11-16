"""Frozen paired continuation queue; no prefix replays, score-aware scheduling or hot edits."""
from __future__ import annotations
import argparse,concurrent.futures,json,os,sqlite3,subprocess,time
from pathlib import Path
from proworksim.storage import atomic_write,json_bytes
ROOT=Path(__file__).resolve().parents[1]
def save(p,v):atomic_write(p,json_bytes(v))
def fits(db,limit):
 with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as c:
  spent=c.execute('SELECT COALESCE(SUM(cost),0) FROM requests WHERE slot IN (SELECT id FROM slots WHERE status="closed")').fetchone()[0]
  held=c.execute('SELECT COALESCE(SUM(hold),0) FROM slots WHERE status!="closed"').fetchone()[0]
 return spent+held+limit*8000<=80_000_000_000

def main(a):
 plan=json.loads(a.plan.read_text());out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 ledger=Path(plan['ledger']);rows=plan['rows'];results=[];active={};next_row=0;gate='pending'
 env={k:v for k,v in os.environ.items() if k not in {'PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD'}}
 def run(row):
  folder=out/row['run_name']
  argv=[str(ROOT/'.venv/bin/python'),str(ROOT/'tools/run_offline_scorer_v096.py'),str(ROOT/'tools/run_delegation_episode_v203_3_3_r2.py'),
   '--output',str(folder),'--ledger',str(ledger),'--index',str(row['candidate_index']),'--checkpoint',row['checkpoint'],'--arm',row['arm']]
  with (out/(row['run_name']+'.log')).open('xb') as log:
   proc=subprocess.run(argv,env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=25000)
  result=json.loads((folder/'result.json').read_text()) if (folder/'result.json').exists() else {'status':'technical_unknown','error':'process exited without receipt'}
  return {**row,'exit':proc.returncode,'result':str(folder/'result.json'),'status':result['status'],'error':result.get('error')}
 def snapshot(status):save(out/'queue.json',{'version':'v203.3.3-paired-continuations-r1','status':status,'at':time.time(),'plan':str(a.plan.resolve()),
  'first_pair_gate':gate,'finished':results,'active':[r for r in active.values()],'unstarted':rows[next_row:]})
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  while True:
   for f in [f for f in active if f.done()]:
    row=active.pop(f)
    try:results.append(f.result())
    except Exception as e:results.append({**row,'status':'technical_unknown','queue_error':str(e)})
   if gate=='pending' and len(results)>=2:
    passed=True
    for r in results[:2]:
     folder=out/r['run_name'];restore=folder/'restore.json'
     if not restore.exists():passed=False;continue
     v=json.loads(restore.read_text())
     if v.get('prefix_recharged') is not False or v.get('world_actions_replayed')!=0:passed=False
     with sqlite3.connect('file:'+str(ledger)+'?mode=ro',uri=True) as c:
      slot='v203.3.3:'+out.name+':'+r['run_name']
      bad=c.execute('SELECT COUNT(*) FROM requests WHERE slot=? AND status="reserved"',(slot,)).fetchone()[0]
      paid=c.execute('SELECT COUNT(*) FROM requests WHERE slot=? AND status="settled"',(slot,)).fetchone()[0]
     if bad or not paid or r.get('status')!='closed':passed=False
    gate='passed' if passed else 'needs_execution_review'
    save(out/'first-pair-gate.json',{'status':gate,'scores_consulted':False,'automatic_new_attempts':False,'rows':results[:2]})
   if gate=='needs_execution_review' and not active:snapshot('first_pair_needs_execution_review');break
   # Only the original first two slots enter before their common integrity gate.
   if next_row<len(rows) and len(active)<2 and (next_row<2 or gate=='passed'):
    row=rows[next_row]
    # One admission at a time until the child has recorded its full slot hold;
    # this avoids racing two conservative cash checks before costly environment setup.
    reserved_or_finished=True
    for r in active.values():
     f=out/r['run_name']/'result.json'
     try:v=json.loads(f.read_text())
     except (FileNotFoundError,json.JSONDecodeError):reserved_or_finished=False;break
     if v['status']=='preparing':reserved_or_finished=False;break
    if reserved_or_finished and fits(ledger,row['token_limit']):
     active[pool.submit(run,row)]=row;next_row+=1;snapshot('running');continue
    if not active and not fits(ledger,row['token_limit']):snapshot('cash_admission_stopped_unstarted_retained');break
   if next_row==len(rows) and not active:snapshot('generation_ended');break
   snapshot('running');time.sleep(10)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
