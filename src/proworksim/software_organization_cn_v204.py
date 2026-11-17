"""Finite, nonparametric organization selection. No model/host actions on import."""
from __future__ import annotations
import math,hashlib,json
CANDIDATES=('KEEP','ASSIST','TRANSFER')
ROLE_CONTRACT=('member_002 may investigate and supply diagnostic evidence, including accepting a bounded diagnostic task. '
 'member_001 alone implements and delivers. member_002 validates the exact member_001 candidate in a private workspace '
 'using real same-version public tests. Prior diagnostic beliefs are not test evidence. This is implementation/verification separation, not diagnosis-blind review.')
PARAMETERS={'lambda_cost':.1,'alpha':1.,'beta':1.,'rho':.8,'eta':.5,'contribution_scale':1.,'novelty_scale':1.,'probability_floor':.05}
def normalized(q):
 if set(q)!=set(CANDIDATES) or any(not math.isfinite(v) or v<=0 for v in q.values()) or abs(sum(q.values())-1)>1e-9:raise ValueError('Positive normalized feasible support required')
 return q

def utility(row,budget=5_000_000):
 if row.get('environment_healthy') is not True:raise ValueError('Contaminated result must not enter contribution')
 if any(type(row.get(k)) is not bool for k in ('official_code_pass','legal_delivery','score_same_delivery_version')):raise ValueError('Unknown quality endpoint')
 if row['legal_delivery'] and not row['score_same_delivery_version']:raise ValueError('Legal delivery needs its exact scored version')
 t=row.get('full_team_tokens')
 if type(t)!=int or not 0<=t<=budget:raise ValueError('Full prefix+suffix team usage required')
 y=int(row['official_code_pass'] and row['legal_delivery'] and row['score_same_delivery_version'])
 return y-PARAMETERS['lambda_cost']*t/budget

def update(q,r,blocks,*,round_index,previous_state_ids=()):
 normalized(q);normalized(r)
 if round_index not in (1,2) or not blocks:raise ValueError('Two nonempty fresh development windows')
 ids=[b['state_id'] for b in blocks]
 if len(set(ids))!=len(ids) or set(ids)&set(previous_state_ids):raise ValueError('Fresh independent state evidence required')
 delta={z:[] for z in CANDIDATES}
 for block in blocks:
  if block.get('stage')!='development' or set(block['results'])!=set(CANDIDATES):raise ValueError('Complete development comparison block required')
  values={z:utility(block['results'][z]) for z in CANDIDATES}
  for z in CANDIDATES:delta[z].append(values[z]-values['KEEP'])
 means={z:sum(delta[z])/len(blocks) for z in CANDIDATES};center=sum(q[z]*means[z] for z in CANDIDATES)
 contribution={z:means[z]-center for z in CANDIDATES};novelty={z:max(0.,math.log(r[z]/q[z])) for z in CANDIDATES}
 # Fixed exponential positive transforms: no batchwise normalization of tiny gaps.
 logs={z:PARAMETERS['rho']*math.log(q[z])+(1-PARAMETERS['rho'])*math.log(r[z])+PARAMETERS['eta']*(contribution[z]+novelty[z]) for z in CANDIDATES}
 maximum=max(logs.values());w={z:math.exp(logs[z]-maximum) for z in CANDIDATES};den=sum(w.values());floor=PARAMETERS['probability_floor']
 next_q={z:floor+(1-3*floor)*w[z]/den for z in CANDIDATES}
 return {'round':round_index,'fresh_state_ids':ids,'q_before':q,'reference':r,'paired_raw_deltas':delta,'mean_delta':means,'contribution':contribution,'novelty':novelty,'q_after':next_q,
  'parameters':PARAMETERS,'novelty_active':any(v>0 for v in novelty.values()),'quality_and_cost_reported_separately':True,'not_training_gradient':True,'source_blocks_sha256':hashlib.sha256(json.dumps(blocks,sort_keys=True).encode()).hexdigest()}

def select(q,uniform_draw):
 normalized(q)
 if not 0<=uniform_draw<1:raise ValueError('Preassigned draw in [0,1) required')
 cumulative=0
 for z in CANDIDATES:
  cumulative+=q[z]
  if uniform_draw<cumulative:return z
 return CANDIDATES[-1]

def intervention(z,state):
 if z not in CANDIDATES:raise ValueError('Unregistered candidate')
 if state.get('diagnosis')!='unfinished' or state.get('environment_healthy')is not True or state.get('final_review_active')is not False or state.get('already_triggered')is not False:
  raise ValueError('No eligible single intervention point')
 if z=='KEEP':return None
 common=('One-time organization policy. '+ROLE_CONTRACT+' Only use public evidence already available to you. Limit requested diagnostic work to 4 of the recipient\'s subsequent opportunities; then return findings or unresolved uncertainty. No repeated persuasion after refusal. ')
 if z=='ASSIST':return common+'Ask member_002 once for scoped diagnostic evidence via send_message with task_id=diagnose; leave diagnostic ownership with member_001. Findings do not imply acceptance or testing.'
 return common+'Offer the existing unfinished diagnostic task once to member_002 via offer_transfer and original accept/decline. If accepted, send a scoped evidence package. Keep implementation with 001; on completion or the four-opportunity boundary, request return through original transfer protocol. No forced owner changes.'

class PolicyLifecycle:
 """Bounded one-shot policy phase; host never transfers ownership or supplies findings."""
 def __init__(self,candidate):
  self.candidate=candidate;self.started=False;self.recipient_opportunities=0;self.finished=False;self.cursor=0;self.evidence=[]
 def observe(self,events,outcome):
  was_started=self.started
  fresh=events[self.cursor:];self.cursor=len(events)
  if self.finished or self.candidate=='KEEP':return None
  for e in fresh:
   if self.candidate=='TRANSFER' and e.get('kind')=='transfer_declined':
    self.finished=True;self.evidence.append(e);return None
   if (self.candidate=='TRANSFER' and e.get('kind')=='transfer_accepted' and e.get('task_id')=='diagnose') or (
    self.candidate=='ASSIST' and e.get('kind')=='work_message' and e.get('actor_id')=='member_001' and e.get('recipient')=='member_002' and e.get('task_id')=='diagnose'):
    self.started=True;self.evidence.append(e)
  if was_started and outcome.get('worker_id')=='member_002':self.recipient_opportunities+=1
  if self.recipient_opportunities>=4:
   self.finished=True
   return 'The predeclared diagnostic assistance phase has reached four recipient opportunities. Report actual findings or unresolved uncertainty. Keep implementation with 001; use the original offer/accept procedure to return any diagnostic ownership if needed. Resume exact-version verification. No new evidence or test result is supplied by this notice.'
  return None
