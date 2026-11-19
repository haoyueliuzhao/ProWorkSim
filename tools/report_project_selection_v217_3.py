"""Final canonical report: preserve original unknown, overlay same-tree rescore."""
import json,collections,statistics,sqlite3
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import checked,reference
from proworksim.software_organization_selector_v217 import policy_value
R=Path(__file__).resolve().parents[1];OUT=R/'artifacts/software-benchmark-v217/final-report-r4';OLD=R/'runs/software-benchmark-v217/selection28-r1';LEGACY=R/'runs/software-benchmark-v217/confirmation-resume-r1';STREAM=R/'runs/software-benchmark-v217/streaming-r2'
def read(p):return json.loads(p.read_text())
def save(name,x):(OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 overlay=read(R/'runs/software-benchmark-v217/fixture-recovery-r1/canonical-overlay.json');code=read(checked(overlay['code']));delivery=read(checked(overlay['delivery']))
 assert code['status']==delivery['status']=='official_report' and code['candidate_tree_sha256']==delivery['candidate_tree_sha256']
 records=read(OLD/'dev1-results.json')+read(R/'artifacts/software-benchmark-v217/resilience-r1/dev2-results-canonical.json')+[read(p) for p in sorted(STREAM.glob('task-*/panel-result.json'))]
 jobs={(j['index'],j['condition']):Path(j['episode']) for j in read(STREAM/'adopted-plan.json')['jobs']}
 r=next(r for r in records if r['index']==13);ep=jobs[(13,'KEEP')];g=read(ep/'progress.json');b=read(ep/'boundary.json')
 r['outcomes']['KEEP']={'status':'scored','code_correct':code['resolved'],'legal_correct':delivery['resolved'],'formal_submission':g['lifecycle']['terminal']=='DELIVERED','logical_tokens':g['logical_total_tokens'],'episode':reference(ep/'result.json'),'episode_path':str(ep),'scores':{'code':overlay['code'],'delivery':overlay['delivery']},'normal_budget_stop':any('budget_exhausted' in x for x in b['role_stops'].values()),'classification_overlay':reference(R/'runs/software-benchmark-v217/fixture-recovery-r1/canonical-overlay.json')};r['complete']=True
 assert len(records)==24 and all(r['complete'] for r in records)
 arms=[];graph_rows=[]
 selected_tools={'select_arrangement','offer_joint_arrangement','accept_joint_arrangement','change_dependency','assign_verification','add_collaboration','integrate_patch','complete_work','complete_evidence','org_review_patch','submit_integration'}
 for r in records:
  for z,o in r['outcomes'].items():
   ep=jobs[(r['index'],z)] if r['phase']=='confirm' else OLD/f'task-{r["index"]:02d}'/z
   boundary=read(ep/'boundary.json');d=read(ep/'dynamic-final.json');actions=[]
   for x in boundary.get('outcomes',[]):
    decision=x.get('decision',{});response=x.get('response',{})
    if decision.get('action') in selected_tools:actions.append({'actor':x.get('worker_id'),'tool':decision['action'],'ok':response.get('ok'),'arguments':decision.get('arguments'),'error':response.get('error')})
   stopped=[{'worker':x.get('worker_id'),'status':x.get('status'),'reason':x.get('reason')} for x in boundary.get('outcomes',[]) if not x.get('action_performed') and x.get('status') in ('worker_waiting','worker_done','team_budget_exhausted')]
   bank=read(checked(r['bank']));res=read(ep/'result.json');prefix=bank['prefix_tokens'];generator=bank['actual_generator_tokens'];logical=o['logical_tokens']
   arm={**o,'index':r['index'],'instance_id':r['instance_id'],'repo':r['repo'],'phase':r['phase'],'condition':z,'episode_path':str(ep),'prefix_tokens':prefix,'generator_tokens':generator,'continuation_tokens':logical-prefix-generator,'choice':d['lifecycle'].get('choice'),'actions':actions,'role_stops':boundary.get('role_stops'),'last_stop_events':stopped[-4:],'source':reference(ep/'boundary.json')}
   arms.append(arm)
   pg=read(ep/'project-relations.json');graph_rows.append({'index':r['index'],'condition':z,'kinds':dict(collections.Counter(x['kind'] for x in pg['relations'])),'statuses':dict(collections.Counter(x['fact_status'] for x in pg['relations'])),'source':reference(ep/'project-relations.json')})
 phases={}
 for ph in ('dev1','dev2','confirm'):
  rs=[r for r in records if r['phase']==ph];aa=[a for a in arms if a['phase']==ph]
  phases[ph]={'states':len(rs),'arms':len(aa),'code_pass':sum(a['code_correct'] for a in aa),'delivery_pass':sum(a['legal_correct'] for a in aa),'budget_stop':sum(a['normal_budget_stop'] for a in aa),'mean_logical_tokens':statistics.mean(a['logical_tokens'] for a in aa),'support_counts':dict(collections.Counter(len(r['outcomes']) for r in rs))}
 confirmation=[]
 for r in records:
  if r['phase']!='confirm':continue
  res={z:{'correct_legal':o['legal_correct'],'tokens':o['logical_tokens']} for z,o in r['outcomes'].items()};values={q:policy_value(dist,res) for q,dist in r['decision']['probabilities'].items()}
  for q,dist in r['decision']['probabilities'].items():values[q]['code_quality']=sum(dist[z]*r['outcomes'][z]['code_correct'] for z in dist)
  confirmation.append({'index':r['index'],'instance_id':r['instance_id'],'repo':r['repo'],'support_size':len(res),'values':values,'probabilities':r['decision']['probabilities'],'outcomes':r['outcomes'],'feature_ranges':{k:[max(v[j] for v in r['decision']['features'][k].values())-min(v[j] for v in r['decision']['features'][k].values()) for j in range(7)] for k in ('L','P')}})
 policies={q:{k:statistics.mean(x['values'][q][k] for x in confirmation) for k in ('code_quality','quality','tokens','utility')} for q in ('KEEP','q0','L_CN','P_C','P_CN')}
 comparisons={}
 for q in ('KEEP','q0','L_CN','P_C'):
  deltas=[x['values']['P_CN']['utility']-x['values'][q]['utility'] for x in confirmation]
  comparisons[q]={'mean_delta':statistics.mean(deltas),'by_task':dict(zip([x['index'] for x in confirmation],deltas)),'leave_one_out':{x['index']:(sum(deltas)-d)/(len(deltas)-1) for x,d in zip(confirmation,deltas)},'by_repo':{repo:statistics.mean(x['values']['P_CN']['utility']-x['values'][q]['utility'] for x in confirmation if x['repo']==repo) for repo in sorted({x['repo'] for x in confirmation})}}
 policy=read(R/'artifacts/software-benchmark-v217/resilience-r1/policy-2.json');updates=[]
 for h in policy['fit_history']:
  updates.append({'window':h['window'],'states':h['records'],'policies':{q:{'theta':d['fit']['theta'],'mean_KL':d['fit']['mean_KL'],'max_novelty':max(max(x['update']['undercoverage_novelty'].values()) for x in d['states'])} for q,d in h['details'].items()}})
 group={}
 for ph in ('dev1','dev2','confirm'):
  for kind in ('KEEP','adjustment'):
   aa=[a for a in arms if a['phase']==ph and (a['condition']=='KEEP')==(kind=='KEEP')]
   group[ph+':'+kind]={'n':len(aa),'code':sum(a['code_correct'] for a in aa),'delivery':sum(a['legal_correct'] for a in aa),'mean_tokens':statistics.mean(a['logical_tokens'] for a in aa)}
 with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as c:
  requests=[dict(zip(('status','requests','tokens','CNY_upper'),r)) for r in c.execute("SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE 'v217:%' GROUP BY status")]
  total=c.execute("SELECT sum(cost)/1e9 FROM requests WHERE status='settled'").fetchone()[0]
  usage=collections.Counter()
  for (body,) in c.execute("SELECT body FROM requests WHERE slot LIKE 'v217:%' AND status='settled'"):
   u=json.loads(body);usage.update({k:u.get(k,0) or 0 for k in ('input_tokens','output_tokens','total_tokens','cache_hit_tokens')})
  active=c.execute("SELECT count(*) FROM slots WHERE status!='closed' AND id LIKE 'v217:%'").fetchone()[0]
 summary={'version':'v217.3-final-canonical','planned_states':28,'prepared_states_including_backups':32,'qualified_states':24,'prefix_unqualified':8,'continuations':len(arms),'phases':phases,'policies':policies,'comparisons':comparisons,'descriptive_arm_groups_not_paired':group,'updates':updates,'physical_requests':requests,'usage':dict(usage),'shared_cash':total,'remaining_cash':1100-total,'active_slots':active,'unknown_scores':0,'same_tree_rescore':overlay,'scored_code':sum(a['code_correct'] for a in arms),'scored_delivery':sum(a['legal_correct'] for a in arms),'budget_stops':sum(a['normal_budget_stop'] for a in arms),'no_new_model_calls':True,'engineering_continue':True,'scientific_gain_demonstrated':False,'recommendation':'Focused design repair then pre-registered small validation; do not expand same design unchanged'}
 save('summary.json',summary);save('canonical-panels.json',records);save('arms-and-actions.json',arms);save('confirmation.json',confirmation);save('project-graph.json',graph_rows);save('policy-updates.json',updates)
 print(json.dumps({'phases':phases,'policies':policies,'comparisons':{q:x['mean_delta'] for q,x in comparisons.items()},'score':(summary['scored_code'],summary['scored_delivery']),'budget':summary['budget_stops'],'actions':dict(collections.Counter(a['tool'] for arm in arms for a in arm['actions'] if a['ok']))},ensure_ascii=False))
if __name__=='__main__':main()
