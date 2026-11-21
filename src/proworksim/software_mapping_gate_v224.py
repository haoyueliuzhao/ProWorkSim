"""A decision opportunity is not proof that organization must change."""
from .software_project_relations_v223_1 import allowed_event

def assess(state,events,*,terminal=False):
 edits=[e['sequence'] for e in events if e.get('actor_id')=='member_001' and e['kind'].endswith(':work_performed')]
 tests=[]
 for e in events:
  if e.get('actor_id')!='member_001' or e['kind']!='test' or not e.get('executed') or not edits or e['sequence']<=max(edits):continue
  counts=e.get('public_execution',{}).get('execution',{}).get('counts',{})
  cases=sum(counts.get(k,0) or 0 for k in ('passed','failed','errors','xfailed','xpassed'))
  if counts.get('collected',0)>0 and cases>0:tests.append(e['sequence'])
 mutable=[k for k,w in state['graph']['work'].items() if not w.get('children') and not w.get('authors') and w.get('completion') is None]
 eligible=bool(edits and tests and mutable and state['team_remaining_tokens']>=2_000_000 and not terminal)
 return {'eligible':eligible,'observed_actor':'member_001','post_latest_edit_real_test_sequences':tests,'remaining_unstarted_work':mutable,'positive_case_count_required':True,'ordinary_setup_gap_not_a_reorganization_verdict':True,'demand_presence_not_a_checkpoint_requirement':True,'terminal':terminal}

def from_world(state,world):
 visible=[v for e in world.state['software_events'] if (v:=allowed_event(world,e,'member_001')) is not None]
 return assess(state,visible,terminal=bool(world.protocol()['terminal']))
