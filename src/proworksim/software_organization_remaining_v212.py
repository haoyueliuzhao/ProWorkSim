"""Enumerate state-conditioned legal remaining-work proposals; never execute them.

Current authors/finished work are held fixed. Targets are state descriptions, not
consent receipts. Candidate schemas are grounded in the v212 managed tools.
"""
import copy,hashlib,itertools,json
from .software_organization_selector_v212 import feature_vector
VERSION='v212-remaining-state-generator-r1'
MEMBERS=('member_001','member_002')
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def signature(state):
 work=state['work'];leaves=[(tuple(sorted(w['scope'])),w['owner'],w['reviewer'],w.get('mode','implementation'),tuple(sorted(w.get('depends_on',[])))) for w in work.values() if not w.get('children')]
 return hashlib.sha256(canonical(sorted(leaves)).encode()).hexdigest()
def step(actor,tool,**arguments):return {'actor':actor,'tool':tool,'arguments':arguments}
def joint_steps(tid,w,new_owner):
 other=next(m for m in MEMBERS if m!=new_owner)
 return [step(w['owner'],'offer_joint_arrangement',task_id=tid,to_member=new_owner,reviewer=other,mode=w.get('mode','implementation'),expected_revision=w['task_revision'],reason='Frozen remaining-work target after actual progress'),{'actor':new_owner,'tool':'accept_joint_arrangement','arguments_from_real_receipt':{'offer_id':{'preceding_tool':'offer_joint_arrangement','task_id':tid}},'on_decline':'retain_partial_execution_no_forced_change'}]

def enumerate_bank(state,remaining_tokens):
 if not any(w.get('authors') for w in state['work'].values()):raise ValueError('Actual work progress required, no zero-work prefix')
 mutable={k:w for k,w in state['work'].items() if not w.get('children') and not w.get('authors') and w.get('completion') is None}
 if not mutable:raise ValueError('No unmodified remaining package')
 proposals=[]
 def add(target,actions):
  key=signature(target)
  if key in {p['candidate_id'] for p in proposals}:return
  proposals.append({'candidate_id':key,'target':target,'actions':actions,'features':feature_vector(state,target,len(actions),remaining_tokens),'automatic_execution':False})
 add(copy.deepcopy(state),[])
 ids=sorted(mutable)
 # At most two packages per joint adaptation; enumerate combinations, not three named templates.
 for count in range(1,min(2,len(ids))+1):
  for subset in itertools.combinations(ids,count):
   target=copy.deepcopy(state);actions=[]
   for tid in subset:
    w=target['work'][tid];new=next(m for m in MEMBERS if m!=w['owner']);actions+=joint_steps(tid,w,new);w['owner']=new;w['reviewer']=next(m for m in MEMBERS if m!=new)
   add(target,actions)
 # Split one untouched multi-anchor leaf, with one child moving to the peer.
 # No dependency migration ambiguity: restrict this proposal to isolated leaves.
 for tid,w in mutable.items():
  scopes=sorted(w['scope'])
  if len(scopes)<2 or w.get('depends_on') or any(tid in x.get('depends_on',[]) for x in state['work'].values()):continue
  for cut in range(1,len(scopes)):
   target=copy.deepcopy(state);parts=[scopes[:cut],scopes[cut:]];childids=[tid+'_'+hashlib.sha256(canonical(v).encode()).hexdigest()[:7] for v in parts]
   if any(x in target['work'] for x in childids):continue
   target['work'][tid]['children']=childids
   actions=[step(w['owner'],'split_work',task_id=tid,children=[{'task_id':k,'description':'Remaining public requirements: '+', '.join(v),'scope':v} for k,v in zip(childids,parts)],reason='Refine unfinished public scopes after observed progress')]
   for k,v in zip(childids,parts):
    peer=next(m for m in MEMBERS if m!=w['owner']);child={'scope':v,'owner':w['owner'],'reviewer':peer,'children':[],'authors':[],'completion':None,'task_revision':1,'depends_on':[],'mode':'implementation'};target['work'][k]=child
    actions+=[step(w['owner'],'assign_verification',task_id=k,reviewer=peer,reason='Explicit independent verification'),step(w['owner'],'add_collaboration',task_id=k,peer=peer,reason='Explicit work exchange')]
   child=target['work'][childids[-1]];new=next(m for m in MEMBERS if m!=child['owner']);actions+=joint_steps(childids[-1],child,new);child['reviewer']=child['owner'];child['owner']=new
   add(target,actions)
 if len(proposals)<3:raise ValueError('Fewer than KEEP plus two distinct legal alternatives; retain excluded prefix and cost')
 # Predefined deterministic target sampling plus a structurally different alternative.
 keep=proposals[0];others=sorted(proposals[1:],key=lambda x:x['candidate_id']);one=others[0]
 two=max(others[1:],key=lambda x:(sum(abs(a-b) for a,b in zip(x['features'],one['features'])),x['candidate_id']))
 bank={'KEEP':keep,'Z1':one,'Z2':two};r={k:1/3 for k in bank}
 return {'version':VERSION,'source_state_sha256':hashlib.sha256(canonical(state).encode()).hexdigest(),'remaining_tokens':remaining_tokens,'legal_candidates_enumerated':len(proposals),'selected':bank,'reference':r,'source_outcomes_used':False,'source_authors_retained':True,'unexecuted_target_not_actual_state':True}
