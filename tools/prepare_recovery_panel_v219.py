"""Fixed recovery set from technical preparation failures, never successor scores."""
import json,time
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_organization_generator_v219 import validated_candidates
R=Path(__file__).resolve().parents[1];OLD=R/'runs/software-benchmark-v218/pilot8-r1';P=R/'artifacts/software-benchmark-v219/protocol-r1'
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
plan=json.loads((R/'artifacts/software-benchmark-v218/protocol-r1/candidate-tasks.json').read_text());rows=[]
for row in plan['rows']:
 i=row['index']
 if i not in (1,2,4,5,6,7):continue
 row=dict(row);row['recovery_kind']='new_independent_prefix_once' if i==2 else 'reuse_unmodified_checkpoint_and_recompile_original_proposals';rows.append(row)
 if i==2:continue
 gen=OLD/f'task-{i:02d}/GENERATOR';prior=json.loads((gen/'candidate-bank.json').read_text());state=json.loads(checked(prior['source_state']).read_text());valid={};proofs=[]
 for a in (0,1):
  path=gen/f'generated-{a}.json';body=json.loads(path.read_text());calls=body['choices'][0]['message'].get('tool_calls',[])
  if len(calls)!=1 or calls[0]['function']['name']!='propose_organization':raise ValueError('Unexpected original generator tool identity')
  try:
   candidates,errors,proof=validated_candidates(calls[0]['function']['arguments'],state);valid.update(candidates);proofs.append({'source':reference(path),'proof':proof,'errors':errors})
  except ValueError as e:proofs.append({'source':reference(path),'rejected':str(e)})
 assert valid,'No automatic new proposal API on reused states'
 bank={**prior,'version':'v219-original-output-recompiled','candidates':{'KEEP':prior['candidates']['KEEP'],**{'C'+str(j+1):v for j,v in enumerate(sorted(valid.values(),key=lambda c:c['candidate_id'])[:2])}},'offline_recovery':True,'new_generator_tokens':0,'new_generator_cost':0,'original_generator_bank':reference(gen/'candidate-bank.json'),'recovery_proofs':proofs}
 bank['coverage_limited']=len(bank['candidates'])<3
 save(P/f'recovered-bank-{i:02d}.json',bank)
plan.update(version='v219-six-state-recovery',main_states=6,max_main_continuations=15,rows=rows,phase_sizes={'dev1':1,'dev2':1,'confirm':4},initial_policy=reference(OLD/'policy-3.json'),remaining_at_start=463.88658312,planning_admission_CNY=270,new_budget=0,recovery={'unchanged_checkpoint_states':[1,4,5,6,7],'fresh_prefix_once':[2],'no_retry_budget_unqualified':[0],'completed_pair_not_replayed':[3],'same_solver_settings':True,'original_costs_preserved':True})
save(P/'candidate-tasks.json',plan)
print({'states':len(rows),'offline_recovered':5,'new_generator_calls_for_reused':0,'max_continuations':15})
