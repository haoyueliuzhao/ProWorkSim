from pathlib import Path
from collections import Counter
import json, hashlib, datetime
ROOT=Path('/data1/zhuxinrui/projects/ProWorkSim')
OUT=ROOT/'artifacts/software-learning-v050/final-analysis'
refs={}; checks=[]; issues=[]
def ref(p):
 p=Path(p);p=p if p.is_absolute() else ROOT/p
 b=p.read_bytes();r={'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)};refs[r['path']]=r;return r
def read(p):
 r=ref(p);return json.loads((ROOT/r['path']).read_text())
def check(name,ok,detail=None):
 x={'name':name,'passed':bool(ok)}
 if detail is not None:x['detail']=detail
 checks.append(x)
 if not ok:issues.append(x)
def link_check(r,label):
 if str(r['path']).endswith('.pt'):return
 rr=ref(r['path']);check(label,rr['sha256']==r['sha256'])
plan=read('runs/software-learning-v050/plan.json'); inv=plan['inventory']
registry=read('runs/software-learning-v050-resume-r1/source-registry.json')
train_design={x['slot_id']:x for x in inv['training_slots']}
dev_design={x['unit_id']:x for x in inv['development_units_shared_by_branches']}
check('24 original training identities',len(train_design)==24)
check('eight original development units',len(dev_design)==8)
sstar=read('runs/software-learning-v049-resume-r1/update-B/actual/checkpoint/checkpoint.json')
branches={}; final_dirs={'B':'runs/software-learning-v050-resume-r1/update-B/actual','Q_plus':'runs/software-learning-v050-resume-r4/update-Q_plus/actual','Q_minus':'runs/software-learning-v050-resume-r5/update-Q_minus/actual'}
for branch,d in final_dirs.items():
 p=ROOT/d;r=read(p/'report.json');ld=read(p/'loaded-state.json');cp=read(p/'checkpoint/checkpoint.json');u=read(p/'update/report.json');bind=read(p/'update-v050-learning-binding.json');tok=read(p/'update-token-evidence.json');orig=read(p/'update-original-updater-binding.json')
 check(branch+' final worker complete',r['status']=='complete' and r['success_boundary'])
 check(branch+' source unchanged',r['source_before']==r['source_after'] and not r['source_after']['code_dirty'])
 check(branch+' exact full Sstar4/4 restore',ld['branch']=='S_star' and ld['restored']['state_tensor_digest']==sstar['state_tensor_digest'] and ld['restored']['serialized_reload_exact'] and ld['actor_steps']==ld['critic_steps']==4)
 check(branch+' final5/5 exact serialization',cp['actor_steps']==cp['critic_steps']==5 and cp['serialized_reload_exact'] and cp==r['checkpoint'])
 check(branch+' one step each',r['new_actor_steps']==r['new_critic_steps']==u['actor_optimizer_steps']==u['critic_optimizer_steps']==1)
 check(branch+' 643 actual admitted native rows',tok['admitted_decisions']==u['admitted_decisions']==r['new_backward_decisions']==643 and tok['global_member_denominator_factor']==48 and not tok['old_material_reused'])
 check(branch+' critic not reweighted',bind['actor_composition_only'] and bind['critic_reweighted'] is False)
 check(branch+' original H1 private bound',orig['code_object_identical'] and orig['closure_identical'] and orig['defaults_identical'] and not orig['original_module_globals_mutated'] and not orig['original_owner_method_mutated'])
 link_check(r['update_report'],branch+' update report hash')
 branches[branch]={'directory':d,'worker_source':r['source_after'],'loaded_state':ld,'checkpoint':cp,'actor_identity':r['final_actor_identity'],'update_binding':bind,'original_updater_binding':orig,'actual_native_material':{k:tok[k] for k in ['entries_sha256','declaration_sha256','recipe_sha256','original_slot_count','admitted_decisions','admitted_own_output_tokens','global_member_denominator_factor','old_material_reused']},'started_at':r['started_at'],'ended_at':r['ended_at']}
# Independent same-input checks use JSON values only, never deserialize .pt.
updates={b:read(ROOT/d/'update/report.json') for b,d in final_dirs.items()}
for k in ['before_actor_identity','recipe','old_critic_values','advantages','rewards']:
 check('B/Qplus/Qminus '+k+' identical',updates['B'][k]==updates['Q_plus'][k]==updates['Q_minus'][k])
check('distinct three final actor identities',len({x['actor_identity']['adapter_sha256'] for x in branches.values()})==3)
check('same numeric updater source bytes',len({x['original_updater_binding']['original_source']['sha256'] for x in branches.values()})==1)
rows=[];outer=[]
def append_row(row,p,branch,design):
 g=read(row['evaluation_guard'])
 check(row['slot_id']+' source identity',row['sampling_seed']==design['sampling_seed'] and row['first_member']==design['first_member'])
 check(row['slot_id']+' formal outcome known',row['status']=='closed' and row['R_joint'] in [0,1] and row['Q_joint'] is not None)
 check(row['slot_id']+' per-slot guards',g['learning_unchanged'] and g['rng_restored_exactly'] and g['actor_identity_unchanged'] and g['software_binding_unchanged'])
 expected=sstar['actor_identity'] if branch in ['train','S_star'] else branches[branch]['actor_identity']
 check(row['slot_id']+' branch actor binding',row['actor_identity']==expected)
 check(row['slot_id']+' no learning during generation',row['actor_updates']==row['critic_updates']==row['new_backward_calls']==0)
 check(row['slot_id']+' protocol invariant',row['condition']=='O1' and row['context_protocol']=='software-context-v0.48-candidate-1' and row['test_feedback_protocol']=='paged-public-test-feedback-v0.42' and row['team_token_budget']==500000)
 rows.append({'slot_id':row['slot_id'],'branch':branch,'root':design['root'],'sampling_seed':row['sampling_seed'],'first_member':row['first_member'],'source':ref(p),'episode_manifest':ref(row['episode_manifest']),'evaluation_guard':ref(row['evaluation_guard']),'actor_identity':row['actor_identity'],'episode_start_steps':row['episode_start_steps'],'formal_R_known':row['R_joint'] is not None,'formal_Q_known':row['Q_joint'] is not None,'administrative_censoring':row['administrative_censoring'],'learning_guard_passed':True,'started_at':row['started_at'],'ended_at':row['ended_at']})
for s in registry['sources']:
 link_check(s['source_result'],s['slot_id']+' source result sealed hash')
 link_check(s['source_manifest'],s['slot_id']+' manifest sealed hash')
 row=read(s['source_result']['path']);append_row(row,s['source_result']['path'],'train',train_design[s['slot_id']])
check('registry 24 unique original ids',set(s['slot_id'] for s in registry['sources'])==set(train_design) and len(registry['sources'])==24 and not registry['old_material_included'])
for b in ['S_star','B','Q_plus','Q_minus']:
 root='runs/software-learning-v050-resume-r1' if b in ['S_star','B'] else 'runs/software-learning-v050-resume-r6-restored'
 for rp in sorted((ROOT/root).glob('dev-'+b+'-*/actual/report.json')):
  r=read(rp);g=read(rp.parent/'collection-guard.json');ld=r['state_loaded_for_collection']
  check(str(rp.relative_to(ROOT))+' complete source guarded',r['status']=='complete' and r['success_boundary'] and r['source_before']==r['source_after'] and not r['source_after']['code_dirty'] and g['learning_unchanged'] and g['rng_restored_exactly'])
  target=sstar if b=='S_star' else branches[b]['checkpoint']
  check(str(rp.relative_to(ROOT))+' complete exact branch state loaded',ld['state_tensor_digest']==target['state_tensor_digest'] and ld['serialized_reload_exact'])
  outer.append({'branch':b,'report':ref(rp),'source':r['source_after'],'collection_guard':ref(rp.parent/'collection-guard.json'),'learning_hashes':g['learning_before_sha256'],'state_loaded':ld})
  for row in r['rows']:
   sr=Path(row['evaluation_guard']).parent/'slot-result.json';raw=read(sr)
   check(row['slot_id']+' report bound to original slot-result',all(row[k]==raw[k] for k in ['slot_id','sampling_seed','first_member','R_joint','Q_joint','actor_identity','episode_manifest']))
   append_row(row,sr,b,dev_design[row['unit_id']])
expected_ids=set(train_design)|{u+'-'+b for u in dev_design for b in ['S_star','B','Q_plus','Q_minus']}
check('exact original56 slot set',len(rows)==56 and len({x['slot_id'] for x in rows})==56 and {x['slot_id'] for x in rows}==expected_ids)
check('no administrative censoring in56',not any(x['administrative_censoring'] for x in rows))
hashes={b:{x['learning_hashes']['critic'] for x in outer if x['branch']==b} for b in ['B','Q_plus','Q_minus']}
opt_hashes={b:{x['learning_hashes']['critic_optimizer'] for x in outer if x['branch']==b} for b in ['B','Q_plus','Q_minus']}
check('final critic equal acrossB/Qplus/Qminus',len(set.union(*hashes.values()))==1)
check('final critic Adam equal acrossB/Qplus/Qminus',len(set.union(*opt_hashes.values()))==1)
direction=read('runs/software-learning-v050-resume-r1/direction.json');support=read('runs/software-learning-v050-resume-r1/support-gate.json')
check('supported first direction one selected',direction['selected'] and direction['direction']['selected']['root']=='LA' and direction['direction']['selected']['member_id']=='member_001' and direction['direction']['selected']['category']=='local_lineage_delivery' and len(direction['direction']['candidate_checks_in_frozen_order'])==1)
check('direction sealed before any dev',direction['frozen_before_any_development'] and direction['created_at']<min(x['started_at'] for x in rows if x['branch']!='train'))
for b,weight in [('B','baseline_weights'),('Q_plus','plus_weights'),('Q_minus','minus_weights')]:
 c=read(ROOT/final_dirs[b]/'composition-before-update.json');check(b+' frozen exact composition',c['weights_by_slot']==direction[weight])
final=read('runs/software-learning-v050-resume-r6-restored/supervisor.json')
check('final r6 restored16 dev complete',len(final['states'])==16 and all(x['status']=='complete' for x in final['states'].values()))
# Original terminal attempts remain separate; no retrospective correction.
old_terminals={}
for suffix in ['', '-resume-r1','-resume-r2','-resume-r3','-resume-r4','-resume-r5','-resume-r6']:
 p=ROOT/('runs/software-learning-v050'+suffix)/'supervisor.json'
 if p.exists():
  x=read(p);old_terminals[str(p.relative_to(ROOT))]={'status':x.get('status'),'states':{k:{a:v.get(a) for a in ['status','attempted','model_started','stop_reason','exit_code']} for k,v in x.get('states',{}).items()}}
obj={'version':'v050-final-provenance-independent-json-review-v1','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Read-only JSON/protocol provenance review; no .pt loading, model calls, tokenizer, tests, acceptance, training or production edits. Science metrics/cost aggregation owned separately.','checks':checks,'blocking_findings':issues,'inventory':rows,'inventory_summary':dict(Counter(x['branch'] for x in rows)),'branches':branches,'support_gate':support['gate'],'selected_direction':direction['direction']['selected'],'direction_created_at':direction['created_at'],'first_development_started_at':min(x['started_at'] for x in rows if x['branch']!='train'),'development_outer_guards':outer,'final_critic_hashes':{k:list(v) for k,v in hashes.items()},'final_critic_optimizer_hashes':{k:list(v) for k,v in opt_hashes.items()},'historical_terminal_statuses_preserved':old_terminals,'references':list(refs.values())}
(OUT/'provenance.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'checks':len(checks),'passed':sum(x['passed'] for x in checks),'issues':issues,'inventory_summary':obj['inventory_summary'],'final_status':final['status'],'direction_timestamp':direction['created_at'],'first_dev':obj['first_development_started_at'],'critic_hashes':obj['final_critic_hashes']},ensure_ascii=False,indent=2))
