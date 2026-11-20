"""Build the task-midpoint collaboration brief; preserve historical policy reports."""
import json,datetime,re
from pathlib import Path
from zoneinfo import ZoneInfo
from proworksim.software_benchmark_candidates_v054 import reference
R=Path(__file__).resolve().parents[1];OUT=R/'artifacts/research-brief-20261120';DOC=R/'docs/experiments/software-weekly-research-brief-20261119'
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 OUT.mkdir(parents=True,exist_ok=True);facts={'updated':datetime.datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),'latest':{},'sources':{},'new_model_calls':0,'new_scoring_runs':0}
 b=R/'runs/software-benchmark-v222/paired4-r1';finished=read(b/'finished.json');assert finished['status']=='completed' and len(finished['results'])==8
 facts['sources']['222']=reference(b/'finished.json');paired=[]
 for task in sorted(b.glob('task-*')):
  item={'task':task.name,'arms':{}}
  for z in ('L','G'):
   bank=read(task/f'GEN-{z}/candidate-bank.json');boundary=read(task/z/'boundary.json');candidate=bank['candidates'][bank['selected']]
   actions=[]
   for o in boundary.get('outcomes',[]):
    d=o.get('decision',{});rsp=o.get('response',{})
    if d.get('action') in ('select_arrangement','offer_joint_arrangement','accept_joint_arrangement','change_dependency'):
     actions.append({'tool':d['action'],'arguments':d.get('arguments'),'ok':rsp.get('ok'),'result':rsp.get('result'),'error':rsp.get('error')})
   assert boundary['termination_class']=='budget_boundary_without_delivery'
   item['arms'][z]={'selected':bank['selected'],'candidate_id':candidate['candidate_id'],'alternative_count':len(bank['candidates'])-1,'basis':candidate.get('basis'),'target':candidate['target'],'actual_actions':actions,'termination':boundary['termination_class'],'bank_source':reference(task/f'GEN-{z}/candidate-bank.json'),'trajectory_source':reference(task/z/'boundary.json')}
  paired.append(item)
 facts['latest']={'tasks':4,'runs':8,'groups':{},'pairs':paired,'whole_panel_budget_boundaries':8}
 for z in ('L','G'):
  rows=[v for k,v in finished['results'].items() if k.endswith(':'+z)]
  facts['latest']['groups'][z]={'code_successes':sum(r['code_correct'] for r in rows),'correct_deliveries':sum(r['legal_correct'] for r in rows),'mean_logical_tokens':sum(r['logical_tokens'] for r in rows)/len(rows)}
 cash=finished['cash']['v222_requests'];assert len(cash)==1 and cash[0]['status']=='settled';facts['latest']['physical_usage']=cash[0]
 facts['latest']['different_selected_targets']=sum(t['arms']['L']['candidate_id']!=t['arms']['G']['candidate_id'] for t in paired)
 facts['sources']['project_relations']=reference(R/'src/proworksim/software_project_information_v222.py')
 facts['sources']['proposal_timing']=reference(R/'tools/run_project_relations_episode_v222.py')
 assert facts['latest']['different_selected_targets']==2
 save(OUT/'midtask-facts.json',facts)
 text=DOC.with_suffix('.md').read_text()
 for z,v in facts['latest']['groups'].items():assert f'{v["mean_logical_tokens"]/10000:.2f}万' in text
 # User preference: update Markdown only; leave historical Word files untouched.
 result={'format':'Markdown','word_generated':False}
 # Local Markdown sources must resolve. Web requests are unnecessary for local results.
 links=re.findall(r'\[[^\]]+\]\(([^)]+)\)',text)
 for link in links:assert (DOC.parent/link).is_file(),link
 result.update({'facts':reference(OUT/'midtask-facts.json'),'markdown':reference(DOC.with_suffix('.md')),'local_source_links_checked':len(links),'result_tables_recomputed':True,'scope':'midtask_organization_adjustment_only','provider_calls':0})
 save(OUT/'markdown-publication-check.json',result);print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
