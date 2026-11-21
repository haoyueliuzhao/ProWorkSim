"""Permission-bounded work/test witnesses and explicit sampling diagnostics.

The observer stays member_001. A peer's private tests are not imported. A visible
published patch plus the observer's exact-version review can establish peer
progress without treating the observer as its author.
"""
import copy
from .software_project_relations_v223_1 import allowed_event
from .software_organization_state_v216_1 import capture as prior_capture
VERSION='v224.1-permission-bounded-checkpoint-r1'
INITIAL_WORK_INSTRUCTION='''Before beginning implementation, decide whether the original issue has genuinely separable work. If so, the current owner must use split_work on work_root, giving meaningful child scopes and descriptions, then establish actual ownership with assign_work/accept_transfer and independent review. Verbal plans, work_note and annotation lists do not create child work packages. Do not create one package per quote or redundant work just to qualify. If the issue is indivisible, explain that in work_note and solve it as one package; this sampling experiment will classify the state as outside the remaining-work intervention space. Once all leaves have authors, current rules do not allow structural reassignment or splitting. A peer's private tests are not visible to the coordinator: publish the actual candidate with fix_patch when ready for legitimate review; the assigned reviewer must open_patch_review and run_patch_review_tests on that exact candidate. Messages or claims are not test receipts. No extra tests solely to manufacture a checkpoint.'''

class SamplingUnavailable(Exception):pass

def test_cases(event):
 counts=event.get('public_execution',{}).get('execution',{}).get('counts',{})
 def number(k):
  v=counts.get(k,0)
  return v if isinstance(v,int) and not isinstance(v,bool) and v>=0 else 0
 executed=sum(number(k) for k in ('passed','failed','xfailed','xpassed'))
 # Collection errors alone are not an executed test case.
 if isinstance(counts.get('tests_run'),int):executed=max(executed,number('tests_run'))
 return {'collected':number('collected'),'executed_cases':executed,'qualifying':event.get('executed') is True and number('collected')>0 and executed>0}

def assess(state,visible_events,*,observer='member_001',terminal=False):
 events=sorted(visible_events,key=lambda e:e['sequence']);edits={};patches={};witnesses=[]
 for e in events:
  actor=e.get('actor_id');version=e.get('source_reference');kind=e.get('kind','')
  if kind=='edit' or kind.endswith(':work_performed'):edits[actor]=e
  if kind=='patch_fixed' and version and e.get('changed_paths') and e.get('task_ids'):patches[e['patch_id']]=e
  if kind!='test' or not test_cases(e)['qualifying'] or not version:continue
  edit=edits.get(actor)
  if edit and edit.get('kind','').endswith(':work_performed') and edit.get('source_reference')==version:
   witnesses.append({'mode':'visible_author_test','author':actor,'tester':actor,'edit_sequence':edit['sequence'],'test_sequence':e['sequence'],'source_reference':copy.deepcopy(version),'counts':test_cases(e)})
  for patch in patches.values():
   if patch['source_reference']==version and patch['sequence']<e['sequence'] and actor==observer:
    witnesses.append({'mode':'published_patch_review','author':patch.get('author',patch['actor_id']),'tester':actor,'patch_id':patch['patch_id'],'publication_sequence':patch['sequence'],'test_sequence':e['sequence'],'source_reference':copy.deepcopy(version),'counts':test_cases(e)})
 # A later visible edit invalidates own-work evidence, but never changes the
 # identity of an immutable published candidate used by a review witness.
 witnesses=[x for x in witnesses if x['mode']=='published_patch_review' or edits[x['author']]['sequence']<=x['test_sequence']]
 work=state['graph']['work'];leaves={k:w for k,w in work.items() if not w.get('children')};mutable=[k for k,w in leaves.items() if not w.get('authors') and w.get('completion') is None]
 exhausted_space=bool(leaves) and not mutable
 reasons=[]
 if terminal:reasons.append('terminal')
 if not mutable:reasons.append('no_unstarted_mutable_work')
 if not witnesses:reasons.append('no_visible_exact_version_executed_case_witness')
 if state['team_remaining_tokens']<2_000_000:reasons.append('insufficient_remaining_task_tokens')
 return {'version':VERSION,'eligible':not reasons,'observer':observer,'witnesses':witnesses,'remaining_unstarted_work':mutable,'reasons':reasons,'sampling_exhausted':exhausted_space and not terminal,'sampling_exhaustion_reason':'authored_or_completed_leaves_cannot_be_split_or_reassigned_under_current_contract' if exhausted_space else None,'private_peer_events_imported':False,'missing_setup_does_not_prove_reorganization_need':True,'terminal':terminal}

def capture(prepared,runtime):
 state=prior_capture(prepared,runtime);w=prepared.world
 visible=[v for e in w.state['software_events'] if (v:=allowed_event(w,e,'member_001')) is not None]
 gate=assess(state,visible,terminal=bool(w.protocol()['terminal']))
 state['mapping_decision_gate']=gate;state['eligible']=gate['eligible'];state['version']=VERSION
 # Replace the old cross-actor/global-timestamp flags with the SAME witness used
 # by the gate, so the compiler cannot reintroduce a private-evidence shortcut.
 state['reason_flags'].update(actual_code_progress=bool(gate['witnesses']),subsequent_executed_public_test=bool(gate['witnesses']),unmodified_remaining_work=bool(gate['remaining_unstarted_work']))
 state['progress_event_sequences']=[x.get('edit_sequence',x.get('publication_sequence')) for x in gate['witnesses']]
 state['test_event_sequences']=[x['test_sequence'] for x in gate['witnesses']]
 return state

def generator_fallback(assessment,valid,failures):
 if valid:return False
 if assessment is None:return True
 if not failures:return False
 last=failures[-1]
 return bool(last.get('errors') or 'pre_dispatch_boundary' in last)

def window_admission(policy_before,policy_after,records):
 informative=[r for r in records if r.get('complete') and len(r.get('outcomes',{}))>=2 and not r['decision'].get('feature_degenerate')]
 changed=policy_before['theta']!=policy_after['theta']
 return {'proceed':bool(informative) and policy_after['update']>policy_before['update'] and changed,'informative_states':len(informative),'weights_changed':changed,'reason':'updated_policy_available' if informative and changed else 'no_effective_update_to_validate','not_score_threshold':True}
