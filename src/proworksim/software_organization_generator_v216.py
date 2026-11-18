"""Validate MODEL-PROPOSED remaining-work transformations; never mutate a live world."""
import copy,hashlib,json
MEMBERS=('member_001','member_002')
SUPPORTED=('SPLIT_WORK','JOINT_ASSIGN','ADD_COLLABORATION','CHANGE_DEPENDENCY','ASSIGN_VERIFICATION')
VERSION='v216-model-compositional-generator-r1'
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def target_id(g):
 work=g['work'];scope=lambda k:tuple(sorted(work[k]['scope']))
 leaves=sorted((scope(k),w['owner'],w['reviewer'] or '',w.get('mode','implementation'),tuple(sorted(scope(p) for p in w.get('depends_on',[])))) for k,w in work.items() if not w['children'])
 edges=sorted((scope(t),a,b) for t,a,b in g['collaboration'] if not work[t]['children'])
 return digest({'leaves':leaves,'collaboration':edges})
def validate(source,proposal):
 if set(proposal)!={'reason','operations'} or not isinstance(proposal['reason'],str) or not proposal['reason'].strip():raise ValueError('reason and operations required')
 ops=proposal['operations']
 if not isinstance(ops,list) or not 1<=len(ops)<=6:raise ValueError('One to six supported operations')
 g=copy.deepcopy(source);actions=[]
 def add(actor,tool,**kw):actions.append({'actor':actor,'tool':tool,'arguments':kw})
 def owned(actor,tid,unstarted=True):
  w=g['work'].get(tid)
  if not w or w['children'] or w['owner']!=actor or w['completion']:raise ValueError('Actual unfinished owned leaf required')
  if unstarted and w['authors']:raise ValueError('Cannot reassign/split/depend authored work')
  return w
 for op in ops:
  if set(op)!={'op','actor','arguments'} or op['op'] not in SUPPORTED or op['actor'] not in MEMBERS:raise ValueError('Unsupported operator/actor; no successful no-op')
  kind,actor,a=op['op'],op['actor'],op['arguments'];tid=a['task_id'];w=owned(actor,tid,unstarted=kind not in ('ASSIGN_VERIFICATION','ADD_COLLABORATION'))
  reason=proposal['reason']
  if kind=='JOINT_ASSIGN':
   if set(a)!={'task_id','to_member','reviewer','mode'}:raise ValueError('Exact JOINT_ASSIGN fields')
   peer=a['to_member']
   if peer not in MEMBERS or peer==actor or a['reviewer'] not in MEMBERS or a['reviewer']==peer or a['mode'] not in ('implementation','evidence'):raise ValueError('Distinct actual new owner/verifier required')
   add(actor,'offer_joint_arrangement',**a,expected_revision=w['task_revision'],reason=reason)
   add(actor,'send_message',recipient=peer,task_id='root_goal',body='A frozen joint arrangement has been offered for '+tid+'. Read dynamic_status and explicitly accept or decline the real pending offer.')
   actions.append({'actor':peer,'tool':'accept_joint_arrangement','arguments_from_real_receipt':{'offer_id':{'task_id':tid,'tool':'offer_joint_arrangement'}},'refusal_is_preserved':True})
   w['owner']=peer;w['reviewer']=a['reviewer'];w['mode']=a['mode']
  elif kind=='SPLIT_WORK':
   if set(a)!={'task_id','children'} or w.get('depends_on') or any(tid in x.get('depends_on',[]) for x in g['work'].values()):raise ValueError('Split only dependency-free unfinished leaf; no implicit migration')
   cc=a['children'];ids=[c['task_id'] for c in cc];scopes=[s for c in cc for s in c['scope']]
   if not 2<=len(cc)<=3 or len(set(ids))!=len(ids) or set(ids)&set(g['work']) or sorted(scopes)!=sorted(w['scope']) or len(set(scopes))!=len(scopes):raise ValueError('Disjoint complete public scope partition required')
   for c in cc:
    if set(c)!={'task_id','description','scope'} or not c['description'].strip() or not c['scope']:raise ValueError('Exact actual child schema')
   add(actor,'split_work',**a,reason=reason);w['children']=ids
   for c in cc:g['work'][c['task_id']]={'scope':c['scope'],'children':[],'owner':actor,'authors':[],'reviewer':None,'completion':None,'task_revision':1,'depends_on':[],'mode':'implementation'}
  elif kind=='ADD_COLLABORATION':
   if set(a)!={'task_id','peer'} or a['peer'] not in MEMBERS or a['peer']==actor:raise ValueError('Actual other peer required')
   add(actor,'add_collaboration',**a,reason=reason)
   for e in ([tid,actor,a['peer']],[tid,a['peer'],actor]):
    if e not in g['collaboration']:g['collaboration'].append(e)
  elif kind=='ASSIGN_VERIFICATION':
   if set(a)!={'task_id','reviewer'} or a['reviewer'] not in MEMBERS or a['reviewer']==actor or a['reviewer'] in w['authors']:raise ValueError('Independent non-author verifier required')
   add(actor,'assign_verification',**a,reason=reason);w['reviewer']=a['reviewer']
  elif kind=='CHANGE_DEPENDENCY':
   if set(a)!={'task_id','depends_on','operation'}:raise ValueError('Exact dependency fields')
   parent=a['depends_on'];other=g['work'].get(parent)
   if not other or other['children'] or parent==tid:raise ValueError('Distinct real upstream leaf required')
   if a['operation']=='add' and parent not in w['depends_on']:w['depends_on'].append(parent)
   elif a['operation']=='remove' and parent in w['depends_on']:w['depends_on'].remove(parent)
   else:raise ValueError('Dependency must actually change')
   w['task_revision']+=1;add(actor,'change_dependency',**a,reason=reason)
 # Validate whole target, not each primitive in isolation.
 for tid,w in g['work'].items():
  if w['children']:continue
  if w['reviewer'] not in MEMBERS or w['reviewer']==w['owner'] or w['reviewer'] in w['authors']:raise ValueError('Complete target must retain independent verification')
  if any(e not in g['collaboration'] for e in ([tid,w['owner'],w['reviewer']],[tid,w['reviewer'],w['owner']])):raise ValueError('Target work exchange must be explicitly enabled')
  def visit(k,seen):
   if k in seen:raise ValueError('Dependency cycle')
   for parent in g['work'][k].get('depends_on',[]):visit(parent,seen|{k})
  visit(tid,set())
 for tid,w in source['work'].items():
  if w['authors'] and (g['work'][tid]['authors']!=w['authors'] or g['work'][tid]['owner']!=w['owner']):raise ValueError('Historical author/owner cannot be washed away')
 if target_id(g)==target_id(source):raise ValueError('Duplicate KEEP/no effective structural change')
 return {'candidate_id':target_id(g),'keep':False,'reason':proposal['reason'],'operations':copy.deepcopy(ops),'actions':actions,'target':g,'host_execution':False,'version':VERSION}

GENERATOR_INSTRUCTION='''You propose organization changes for a real coding team at an actual mid-work checkpoint. You are a proposal service, not a third autonomous worker. Never solve the code issue or use hidden tests. Return exactly two different complete candidate plans via propose_organization. KEEP is added separately. Use only SPLIT_WORK, JOINT_ASSIGN, ADD_COLLABORATION, CHANGE_DEPENDENCY, ASSIGN_VERIFICATION. Unsupported changes (merging tasks, removing collaboration, scheduling priority, new agents) must not be invented. Existing code authors and their responsibility remain unchanged. Only unfinished leaves without code authors can change ownership or dependencies or split. Preserve every public requirement anchor. Each candidate should contain at least one JOINT_ASSIGN on remaining work; combine other supported changes when useful, not cosmetic renaming. Every final leaf needs the other non-author reviewer and both collaboration directions. Splitting requires assigning verifiers and collaboration for new children. JOINT_ASSIGN means a proposal + recipient consent, not a direct host owner write. No candidate may silently mark completion or passed tests. Current resource usage is shared, not separate per-member quotas. Arguments:
SPLIT_WORK {task_id, children:[{task_id,description,scope:[existing anchor IDs]}]};
JOINT_ASSIGN {task_id,to_member,reviewer,mode:"implementation"|"evidence"};
ADD_COLLABORATION {task_id,peer}; CHANGE_DEPENDENCY {task_id,depends_on,operation:"add"|"remove"}; ASSIGN_VERIFICATION {task_id,reviewer}.
Use current actual task IDs. Each operation has op, actor, arguments. Supply a concise reason for each whole plan. Owner/verifier arrangements may concentrate or distribute remaining work; extra members writing code is not itself a reward.'''
TOOL={'type':'function','function':{'name':'propose_organization','description':'Propose two complete, distinct state-conditioned organization changes; never execute them.','parameters':{'type':'object','properties':{'candidates':{'type':'array','minItems':2,'maxItems':2,'items':{'type':'object','properties':{'reason':{'type':'string'},'operations':{'type':'array','minItems':1,'maxItems':6,'items':{'type':'object','properties':{'op':{'type':'string','enum':list(SUPPORTED)},'actor':{'type':'string','enum':list(MEMBERS)},'arguments':{'type':'object'}},'required':['op','actor','arguments'],'additionalProperties':False}}},'required':['reason','operations'],'additionalProperties':False}}},'required':['candidates'],'additionalProperties':False}}}
