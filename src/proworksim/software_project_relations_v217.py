"""Event-backed decision projection, not a second authoritative world.

Only actor-visible receipts enter the generator view. Dependencies declared by
members remain claims; deleting an execution edge does not erase its evidence.
"""
import copy,json,hashlib
VERSION='v217-event-project-relations-r1'
def identity(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
class Projection:
 def __init__(self,actor='member_001'):
  self.actor=actor;self.seen={};self.relations={};self.active={};self.latest={};self.edits={};self.processed=0
 def export(self):return copy.deepcopy(vars(self))
 def restore(self,value):
  if value.get('actor')!=self.actor:raise ValueError('Foreign actor projection')
  self.__dict__.update(copy.deepcopy(value))
 def put(self,kind,source,target,event,*,status='observed',version=None,revision=None,details=None):
  r={'kind':kind,'source':source,'target':target,'source_event':event['sequence'],'observed_order':event['sequence'],'version':version,'work_revision':revision,'fact_status':status,'visible_to':self.actor,'validity':'current','details':details or {}}
  key=identity({k:r[k] for k in ('kind','source','target','source_event')});r['id']=key;self.relations[key]=r
 def apply(self,e):
  n=e['sequence'];fingerprint=identity(e)
  if n in self.seen:
   if self.seen[n]!=fingerprint:raise ValueError('Event identity reused with different content')
   return
  self.seen[n]=fingerprint;self.processed+=1;k=e['kind'];actor=e['actor_id'];task=e.get('task_id');version=e.get('source_reference') or e.get('identity',{}).get('source_reference');rev=e.get('work_epoch',e.get('task_revision'))
  if k.endswith(':work_started'):self.active[actor]=task
  if k=='edit':
   self.latest[actor]=version;self.edits[e.get('operation_id')]=e
   if e.get('operation')=='integrate' and e.get('patch_id'):self.put('artifact_adopted',e['patch_id'],actor,e,version=version,details={'conflicts':e.get('conflicts',[]),'adoption_not_validation':True})
   for path in e.get('paths',[]):
    self.put('work_code_region',self.active.get(actor,'unbound:'+actor),path,e,version=version,details={'operation':e.get('operation'),'author':actor})
  elif k.endswith(':work_performed'):
   self.latest[actor]=version
   prior=self.edits.get(e.get('operation_id'))
   if prior:
    for path in prior.get('paths',[]):self.put('work_code_region',task,path,e,version=version,revision=rev,details={'author':actor,'role':'actual_edit'})
  elif k=='read':self.put('work_observed_region',self.active.get(actor,'unbound:'+actor),e.get('path'),e,version=version,details={'start':e.get('start_character'),'end':e.get('end_character')})
  elif k=='patch_fixed':
   for tid in e.get('task_ids',[]):
    self.put('work_fixed_artifact',tid,e['patch_id'],e,version=version,details={'author':e.get('author'),'paths':e.get('changed_paths',[])})
    for path in e.get('changed_paths',[]):self.put('work_code_region',tid,path,e,version=version,details={'author':e.get('author'),'role':'published_candidate'})
  elif k=='test':self.put('test_version','test:'+str(n),actor,e,version=version,details={'executed':e.get('executed'),'passed':e.get('passed'),'selection':e.get('public_test_selection')})
  elif k in ('edit_integrate','integrate') or (e.get('operation')=='integrate' and e.get('patch_id')):
   self.latest[actor]=version;self.put('artifact_adopted',e['patch_id'],actor,e,version=version,details={'conflicts':e.get('conflicts',[]),'adoption_not_validation':True})
  elif k.endswith(':candidate_reviewed') or k.endswith(':evidence_reviewed'):
   self.put('review_candidate','review:'+str(n),e.get('patch_id') or e.get('evidence_id'),e,version=version,revision=e.get('task_revisions',e.get('work_epoch')),details={'decision':e.get('decision'),'reviewer':actor,'review_is_not_test':True})
  elif k.endswith(':dependency_changed'):
   self.put('execution_dependency',task,e.get('depends_on'),e,revision=rev,details={'operation':e.get('operation')})
   if e.get('operation')=='add':self.put('work_requires_claim',task,e.get('depends_on'),e,status='member_claim',revision=rev,details={'statement':e.get('reason'),'not_proven_semantic_dependency':True})
  elif k=='work_message':self.put('member_statement',actor,e.get('recipient'),e,status='member_claim',details={'task_id':task,'text':e.get('body',e.get('message','')),'not_verified_engineering_fact':True})
  elif k.endswith(':work_reopened'):
   self.put('work_revision',task,rev,e,revision=rev)
  elif k.endswith(':work_locally_completed') or k.endswith(':evidence_completed'):
   self.put('work_completion',task,e.get('evidence_id') or e.get('completion',{}).get('patch_id'),e,version=version,revision=rev,details={'completion':copy.deepcopy(e.get('completion'))})
  elif k.endswith(':joint_accepted'):self.put('responsibility_accepted',task,actor,e,revision=rev,details={'previous_owner':e.get('previous_owner'),'not_code_adoption':True})
  elif k in ('submit','delivery') or k.endswith(':delivered'):self.put('delivery_version',actor,'final',e,version=version,details={'official_correctness_unknown':True})
 def record_outcome(self,outcome,events):
  # Current managed integration emits an edit event without patch_id. Bind the
  # actual actor-visible receipt, never infer adoption from equal file bytes.
  if outcome.get('worker_id')!=self.actor:return
  dec=outcome.get('decision',{});resp=outcome.get('response',{});tool=dec.get('action')
  if resp.get('ok') is not True or tool!='integrate_patch':return
  args=dec.get('arguments',{});result=resp.get('result',{})
  if not args.get('patch_id') or not result.get('source_reference'):raise ValueError('Successful adoption lacks exact receipt identity')
  matched=[e for e in events if e.get('operation_id')==resp.get('command_id')]
  if not matched:raise ValueError('Adoption receipt has no matching committed event')
  e=matched[-1]
  self.put('artifact_adopted',args['patch_id'],self.actor,e,version=result['source_reference'],details={'conflicts':result.get('conflicts',[]),'adoption_not_validation':True,'source_receipt':{'command_id':resp['command_id'],'tool':tool,'arguments':args,'result_hash':identity(result)}})
 def snapshot(self,work,requirements):
  rows=copy.deepcopy(list(self.relations.values()))
  for r in rows:
   if r['kind']=='test_version':
    latest=self.latest.get(r['target']);r['validity']='current' if latest and r['version']==latest else ('historical_version' if latest else 'current_version_unknown')
  for tid,w in work.items():
   for scope in w['scope']:
    rows.append({'id':identity(['requirement',tid,scope]),'kind':'requirement_work','source':scope,'target':tid,'source_event':None,'source_document':'frozen-public-requirement-anchors','observed_order':0,'version':None,'work_revision':w.get('work_epoch'),'fact_status':'member_claim','visible_to':self.actor,'validity':'current','details':{'scope_coverage_not_semantic_proof':True}})
  doc={'version':VERSION,'actor':self.actor,'relations':sorted(rows,key=lambda r:r['id']),'requirements':requirements,'processed_visible_events':self.processed,'unobserved_relations_are_unknown':True,'private_peer_history_used':False,'hidden_scoring_used':False}
  doc['graph_id']=identity(doc);return doc

def allowed_event(world,e,actor):
 if e['actor_id']==actor:return e
 try:return world._action_read_work_event(actor,'SOFTWARE27',e['sequence'])
 except (ValueError,PermissionError):return None

def synchronize(projection,world,requirements):
 for e in world.state['software_events']:
  if e['sequence'] not in projection.seen:
   visible=allowed_event(world,e,projection.actor)
   if visible is not None:projection.apply(visible)
 graph=world._action_dynamic_status(projection.actor,'SOFTWARE27')
 return projection.snapshot(graph['work'],requirements)
