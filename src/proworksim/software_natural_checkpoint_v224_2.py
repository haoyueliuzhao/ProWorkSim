"""Measure natural work; absence of a structural alternative never stops solving."""
import copy
from .software_mapping_checkpoint_v224_1 import capture as measured_capture,test_cases
from .software_project_relations_v223_1 import allowed_event
from .software_organization_opportunity_v218 import distinct_structure,structure
from .storage import digest,json_bytes
VERSION='v224.2-observe-without-work-gating-r1'
INITIAL_WORK_INSTRUCTION='''Solve the original issue normally within the shared task budget. Members may read, investigate, implement and test in parallel using the actual managed tools. Group work only when useful; there is no required number of packages, no duty to leave a package idle, and no requirement to test before a partner starts. Do not publish or run tests merely to satisfy experimental sampling. If an organization proposal arrives, consider it using the real current state and explicit consent. If no useful change is available, retain the arrangement and finish the original task. Already-authored code and immutable evidence retain their actual provenance.'''

def assess(state,visible_events,*,terminal=False):
 evidence=[]
 for e in visible_events:
  k=e.get('kind','');reason=None
  if k=='read' and e.get('path') and e.get('source_reference') and isinstance(e.get('start_character'),int) and isinstance(e.get('end_character'),int) and e['end_character']>e['start_character']:reason='actual_repository_read'
  elif k.endswith(':work_performed') and e.get('source_reference'):reason='actual_work_edit'
  elif k=='patch_fixed' and e.get('changed_paths'):reason='visible_published_patch'
  elif k=='test' and test_cases(e)['qualifying']:reason='executed_public_cases'
  elif k=='navigation_v222:located' and e.get('result_paths'):reason='actual_repository_location'
  if reason:evidence.append({'event_sequence':e['sequence'],'actor':e['actor_id'],'kind':reason,'source_reference':copy.deepcopy(e.get('source_reference'))})
 mutable=[k for k,w in state['graph']['work'].items() if not w.get('children') and not w.get('authors') and w.get('completion') is None]
 return {'version':VERSION,'eligible':bool(evidence) and not terminal and state['team_remaining_tokens']>0,'observer':'member_001','evidence':evidence,'remaining_unstarted_work':mutable,'sampling_exhausted':False,'lack_of_alternative_stops_solving':False,'test_is_not_a_planning_prerequisite':True,'all_started_is_not_a_stop_condition':True,'terminal':terminal,'preparation_cap_means_keep_continuation_not_task_failure':True}

def capture(prepared,runtime):
 state=measured_capture(prepared,runtime);world=prepared.world
 visible=[v for e in world.state['software_events'] if (v:=allowed_event(world,e,'member_001')) is not None]
 gate=assess(state,visible,terminal=bool(world.protocol()['terminal']))
 state['mapping_decision_gate']=gate;state['eligible']=gate['eligible'];state['version']=VERSION
 state['organization_action_capabilities']={'owner_consent_required':True,'prior_edit_or_test_required':False,'unstarted_rearrangement_ids':gate['remaining_unstarted_work'],'published_patch_adoption_allowed':True,'authorship_cannot_be_erased':True,'private_evidence_automatically_shared':False}
 return state

def effect_signature(candidate):
 return digest(json_bytes({'structure':structure(candidate['target']),'explicit_adoptions':sorted(candidate.get('planned_adoptions',[]),key=lambda a:(a['actor'],a['task_id'],a['patch_id']))}))

def effective_alternative(state,candidate):
 return distinct_structure(state,candidate) or bool(candidate.get('planned_adoptions'))

def keep_bank(state,*,prefix_tokens,source_reference,checkpoint_reference,reason):
 remaining=5_000_000-prefix_tokens
 if remaining<=0:raise ValueError('No tokens remain; score the existing closed endpoint instead')
 assessment={'decision':'keep','demand_types':[],'reason':reason}
 candidate={'candidate_id':'KEEP-'+digest(json_bytes(state['graph'])),'keep':True,'target':copy.deepcopy(state['graph']),'actions':[],'decision_assessment':assessment,'reason':reason,'host_execution':False}
 return {'version':VERSION,'decision_assessment':assessment,'candidates':{'KEEP':candidate},'actual_generator_tokens':0,'shared_graph_tokens':0,'prefix_tokens':prefix_tokens,'remaining_branch_token_limit':remaining,'checkpoint':checkpoint_reference,'source_state':source_reference,'shared_graph_state':source_reference,'system_keep_fallback':True,'fallback_is_not_model_keep_endorsement':True,'selected':None,'selection_rule':'Continue original task; no new policy observation or artificial alternative'}

def next_window_context(policy_before,policy_after,records):
 from .software_mapping_checkpoint_v224_1 import window_admission
 evidence=window_admission(policy_before,policy_after,records)
 return {**evidence,'continue_planned_tasks':True,'next_window_purpose':'updated_policy_validation' if evidence['proceed'] else 'additional_observation_with_unchanged_policy','no_update_is_not_a_queue_fault':True,'no_automatic_extra_tasks':True}
