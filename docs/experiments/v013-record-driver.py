"""Read-only same-version record correction for closed online evaluation runs."""
import argparse, copy, hashlib, json, sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);p.add_argument('--source-tree',type=Path,required=True);a=p.parse_args()
sys.path.insert(0,str(a.source_tree.resolve()/'src'))
from proworksim.audit import code_identity
from proworksim.storage import digest,json_bytes,read_json
from proworksim.online_rewards import assess_online_reward
from proworksim.online_support import assess_online_validity,diagnose_window
from proworksim.member_views import member_view
ROOT=Path('/data1/zhuxinrui/projects/ProWorkSim');source=code_identity();source_files={}
for name in ['online_support.py','team_validity.py','member_views.py','online_rewards.py']:
 q=a.source_tree/'src/proworksim'/name;source_files[name]={'path':str(q.resolve()),'sha256':digest(q.read_bytes())}
assert source['code_commit']=='87b785634ae3c001cdc62014799941e732e2ccfc' and not source['code_dirty']
assert not a.output.exists() and not a.archive.exists();a.output.mkdir(parents=True)
def ref(q):
 q=q.resolve();return {'path':str(q.relative_to(ROOT)) if q.is_relative_to(ROOT) else str(q),'sha256':digest(q.read_bytes())}
def save(q,v):q.write_bytes(json_bytes(v));return ref(q)
run=read_json(a.input/'online/report.json');assert run['mode']=='evaluate' and all(w['status']=='complete' for w in run['windows'])
checked={};windows=[];rows=[]
for window_dir in sorted((a.input/'online').glob('window-*')):
 c=window_dir/'collection';decl=read_json(c/'declaration.json');old_support=read_json(c/'support.json');records=[];slot_rows=[]
 out=a.output/window_dir.name;out.mkdir()
 for q in [c/'declaration.json',c/'support.json',c/'summary.json']:checked[str(q)]=ref(q)
 for i,slot in enumerate(decl['slots']):
  case=c/f'slot-{i}';old=read_json(case/'team-rollout.json');mapping=read_json(case/'mapping.json');ep=case/'episode';capture=read_json(case/'public-capture.json')
  inputs=['team-rollout.json','mapping.json','public-capture.json','episode/manifest.json','episode/experience.json','episode/start/control/state.json','episode/end/control/state.json']
  for name in inputs:checked[str(case/name)]=ref(case/name)
  reward=assess_online_reward(ep,old['online_scope']['reward_spec'])
  validity=assess_online_validity(ep,old['online_scope']['reward_spec'],members=old['members'],independent_capture=capture,reward_result=reward,window=old['window'])
  new=copy.deepcopy(old);new['reward_eligibility']=reward;new['work_validity']=validity;new['online_scope']['validity_spec_id']=validity['spec_id']
  new['record_remeasurement']={'measurement':'online-scoped-validity-v0.13.1','source':source,'original_rollout':ref(case/'team-rollout.json'),'sampling_or_parameter_update':False}
  assert new['window']==old['window'] and new['manifest']==old['manifest'] and new['events']==old['events']
  views={m:member_view(new,m) for m in slot['active_members']};where=out/f'slot-{i}';where.mkdir()
  refs={name:save(where/(name+'.json'),value) for name,value in {'original-reward':old['reward_eligibility'],'original-validity':old['work_validity'],'reward':reward,'validity':validity,'member-views':views,'team-rollout':new,'mapping':mapping}.items()}
  previous=next(g['support'] for g in old_support['groups'] if g['window']==old['window'])
  row={'slot_id':slot['slot_id'],'original_sampling_source':old['manifest']['source_start'],'reward_json_bytes_identical':json_bytes(reward)==json_bytes(old['reward_eligibility']),'R_old':old['reward_eligibility']['reward'],'R_new':reward['reward'],'eligible_old':old['reward_eligibility']['eligible'],'eligible_new':reward['eligible'],'V_old':old['work_validity']['value'],'V_new':validity['value'],'components_old':{k:v['value'] for k,v in old['work_validity']['components'].items()},'components_new':{k:v['value'] for k,v in validity['components'].items()},'window_unchanged':True,'policy_map_unchanged':True,'events_unchanged':True,'members':{},'derived_refs':refs}
  for m,v in views.items():
   row['members'][m]={'started_decisions':len(v['decisions']),'actual_generations':v['own_action_count'],'actual_output_tokens':v['own_action_tokens'],'complete_actor_trajectory':v['complete_actor_trajectory'],'complete_semantic_trajectory':v['complete_semantic_trajectory'],'base_mask_old':previous['blocks'][m]['base_actor_mask'][slot['slot_id']],'decisions':[{k:d.get(k) for k in ['call_id','generation_status','actor_required','actor_trainable','diagnostics']} for d in v['decisions']]}
  records.append({'slot_id':slot['slot_id'],'status':'closed','rollout':new,'mapping':mapping});slot_rows.append(row)
 support=diagnose_window(decl,records)
 for row in slot_rows:
  group=next(g for g in support['groups'] if row['slot_id'] in g['support']['slot_ids'])
  for m,values in row['members'].items():values['base_mask_new']=group['support']['blocks'][m]['base_actor_mask'][row['slot_id']]
  row['new_support']={m:{k:b[k] for k in ['M','n_positive','v','b','semantic_work_support','candidate_counts_before_support']} for m,b in group['support']['blocks'].items()}
 rows.extend(slot_rows);windows.append({'window_id':decl['window_id'],'declaration_ref':ref(c/'declaration.json'),'original_support_ref':ref(c/'support.json'),'derived_support_ref':save(out/'support.json',support),'slots':[r['slot_id'] for r in slot_rows]})
unchanged=all(ref(Path(q))==value for q,value in checked.items());assert unchanged
report={'version':'online-record-remeasurement-v0.13.1','scope':'Derived measurement only; no sampling, optimization, world transition or replacement of original R/V/support.','original_run_ref':ref(a.input/'online/report.json'),'measurement_source':source,'measurement_source_files':source_files,'driver_ref':ref(Path(__file__)),'windows':windows,'episodes':rows,'all_reward_json_bytes_identical':all(r['reward_json_bytes_identical'] for r in rows),'all_original_referenced_files_unchanged':unchanged,'checked_original_refs':list(checked.values()),'limits':['R equality is byte-for-byte equality of the repository JSON serialization of the full reward object, not just equal scalar numbers.','Only the record-checker frozen window binding is corrected; actor parameters, original observations/actions/tokens, case scope and policy maps are unchanged.','Initial and final evaluation can be compared with this same measurement version; original archived judgments remain independently readable.','A corrected record gate restores trustworthy existing actor traces; it does not convert actual work failure into success or create missing actions.']}
save(a.output/'report.json',report);save(a.archive,report)
print(json.dumps({'archive':str(a.archive),'slots':len(rows),'R_unchanged':report['all_reward_json_bytes_identical'],'original_SHA_unchanged':unchanged,'changes':[{'slot_id':r['slot_id'],'V':[r['V_old'],r['V_new']],'components':[r['components_old'],r['components_new']],'base':{m:[v['base_mask_old'],v['base_mask_new']] for m,v in r['members'].items()}} for r in rows]},ensure_ascii=False))
