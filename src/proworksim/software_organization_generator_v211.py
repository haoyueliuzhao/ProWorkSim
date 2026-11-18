"""Frozen public-anchor combinatorial generator; zero model/score inputs.

Enumerates partitions and owner allocations, not KEEP/ASSIST/TRANSFER templates.
The three selected plans are a mechanism coverage panel, not learned best plans.
"""
import itertools,hashlib,json
VERSION='v211-public-partition-generator-r1';M1='member_001';M2='member_002'
def partitions(items):
 if not items:yield [];return
 first,*rest=items
 for p in partitions(rest):
  yield [[first]]+[b[:] for b in p]
  for i in range(len(p)):
   q=[b[:] for b in p];q[i]=[first]+q[i];yield q

def generate(requirements,*,seed,dependencies=()):
 req=sorted(requirements)
 if len(set(req))!=len(req) or not 2<=len(req)<=4:raise ValueError('Two to four independently anchored public requirements')
 banks={}
 for parts in partitions(req):
  parts=sorted(tuple(sorted(b)) for b in parts)
  if len(parts)<2:continue
  for owners in itertools.product((M1,M2),repeat=len(parts)):
   tasks=[{'task_id':'work_'+hashlib.sha256('|'.join(scope).encode()).hexdigest()[:10],'scope':list(scope),'owner':owner,'reviewer':M2 if owner==M1 else M1} for scope,owner in zip(parts,owners)]
   bucket={s:t['task_id'] for t in tasks for s in t['scope']};dep=sorted({(bucket[child],bucket[parent]) for child,parent in dependencies if bucket[child]!=bucket[parent]})
   canonical={'tasks':tasks,'dependencies':dep,'delivery_member':M1,'verification':'per-contribution-exact-cross-review'}
   key=hashlib.sha256(json.dumps(canonical,sort_keys=True).encode()).hexdigest()
   actions=[{'actor':M1,'tool':'split_work','arguments':{'task_id':'work_root','children':[{'task_id':t['task_id'],'description':'Public requirement package: '+', '.join(t['scope']),'scope':t['scope']} for t in tasks],'reason':'Frozen public-anchor partition'}}]
   for t in tasks:
    tid=t['task_id'];owner=t['owner'];reviewer=t['reviewer']
    if owner!=M1:
     offer_step=len(actions)
     actions.append({'actor':M1,'tool':'assign_work','arguments':{'task_id':tid,'to_member':owner,'reason':'Frozen candidate responsibility allocation'}})
     actions.append({'actor':owner,'tool':'accept_transfer','arguments_from_real_receipt':{'offer_id':{'step':offer_step,'field':'offer_id'}},'on_decline':'record_partial_execution_no_forced_owner'})
    actions.append({'actor':owner,'tool':'add_collaboration','arguments':{'task_id':tid,'peer':reviewer,'reason':'Actual work-bound communication and handoff'}})
    actions.append({'actor':owner,'tool':'assign_verification','arguments':{'task_id':tid,'reviewer':reviewer,'reason':'Verify another member contribution; never self-review'}})
   for child,parent in dep:
    owner=next(t['owner'] for t in tasks if t['task_id']==child)
    actions.append({'actor':owner,'tool':'change_dependency','arguments':{'task_id':child,'depends_on':parent,'operation':'add','reason':'Frozen public interface dependency'}})
   banks[key]={'candidate_id':key,'target':canonical,'actions':actions,'distinct_owners':len(set(owners)),'generator_version':VERSION,'automatic_execution':False,'receipt_references_not_literal_tool_arguments':True}
 bank=[banks[k] for k in sorted(banks)]
 def order(x):return hashlib.sha256((str(seed)+x['candidate_id']).encode()).hexdigest()
 parallel=[x for x in bank if x['distinct_owners']==2]
 one=min(parallel,key=order)
 def signature(x):return {(tuple(t['scope']),t['owner'],t['reviewer']) for t in x['target']['tasks']}
 two=max((x for x in bank if x['candidate_id']!=one['candidate_id']),key=lambda x:(len(signature(x)^signature(one)),x['distinct_owners']!=one['distinct_owners'],order(x)))
 baseline={'candidate_id':'unchanged','target':{'tasks':[{'task_id':'work_root','scope':req,'owner':M1,'reviewer':M2}],'dependencies':[],'delivery_member':M1,'verification':'per-contribution-exact-cross-review'},'actions':[{'actor':M1,'tool':'add_collaboration','arguments':{'task_id':'work_root','peer':M2,'reason':'Original whole-task collaboration'}},{'actor':M1,'tool':'assign_verification','arguments':{'task_id':'work_root','reviewer':M2,'reason':'Original whole-task independent verification'}}],'automatic_execution':False}
 # O0's setup is recorded too; no hidden work or free model calls.
 return {'generator_version':VERSION,'seed':seed,'requirements':req,'candidate_bank':bank,'selected':{'O0':baseline,'O1':one,'O2':two},'selection_rule':'O1 frozen-hash choice among distinct-owner configurations; O2 maximum scope-owner-reviewer structural distance, then owner-concentration diversity, then frozen hash','quality_or_gold_used':False,'candidate_generation_API_cost':0,'all_selected_keep_original_scope':True,'not_selector_training':True}
