"""Secondary read-only accounting: pagination, actual proposal presentation and review deduplication."""
import json,collections
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import checked,reference
R=Path(__file__).resolve().parents[1];out=R/'artifacts/software-benchmark-v215/final-report-r1';rows=json.loads((out/'episodes.json').read_text());diagnostics=[]
for row in rows:
 p=checked(row['refs']['result.json']).parent;b=json.loads(checked(row['refs']['boundary.json']).read_text());pages=collections.defaultdict(lambda:{'calls':0,'cursor_calls':0,'total_characters':None});review_ids=set()
 for step in b['outcomes']:
  d=step.get('decision',{});r=step.get('response',{}).get('result') or {}
  if d.get('action')=='diff_workspace':
   x=pages[r.get('text_sha256','missing')];x['calls']+=1;x['cursor_calls']+=bool(d.get('arguments',{}).get('cursor'));x['total_characters']=r.get('total_characters')
 for e in row['review_records']:
  if e['decision']=='accept':review_ids.add((e['actor_id'],e['patch_id'],e['identity']['files_sha256'],e['identity']['entry_metadata_sha256']))
 presentations=collections.Counter();request_refs=[]
 if row['midwork_proposal']:
  for f in sorted((p/'physical-api').glob('*/request.json')):
   r=json.loads(f.read_text());payload=r['payload'];messages=payload['wire'].get('messages',[])
   if any('The frozen post-progress trigger is now reached.' in json.dumps(m.get('content'),ensure_ascii=False) for m in messages):
    assert (f.parent/'response.json').exists();presentations[payload['member_id']]+=1;request_refs.append(reference(f))
  assert presentations, 'Do not claim ignored proposal if no actual request included it'
 integrations=[{'actor':x['actor'],'patch_id':x['arguments']['patch_id'],'conflicts':x['result'].get('conflict_count')} for x in row['steps'] if x['tool']=='integrate_patch' and x['ok']]
 diagnostics.append({'instance_id':row['instance_id'],'condition':row['condition'],'diff_pages':dict(pages),'accept_records':sum(e['decision']=='accept' for e in row['review_records']),'distinct_accepted_actor_candidate_versions':len(review_ids),'accepts_with_nonpassing_actual_test':sum(e['decision']=='accept' and (e.get('test_evidence')or{}).get('passed') is False for e in row['review_records']),'explicit_integrations':integrations,'late_proposal_actual_request_presentations':dict(presentations),'late_proposal_request_refs':request_refs,'not_claiming_model_used_or_understood_presentation':True})
(out/'cost-and-mechanism.json').write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2)+'\n')
for d in diagnostics:print(d['instance_id'],d['condition'],'accept distinct',d['distinct_accepted_actor_candidate_versions'],'late proposal',d['late_proposal_actual_request_presentations'])
