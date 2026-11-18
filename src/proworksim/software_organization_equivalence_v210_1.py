"""Exact bounded task-ID equivalence; frozen member and public scope identities stay.

At most eight work nodes. Permute only equal-colored task nodes, not agents or
public requirement anchors. This is structural equivalence, not semantic proof.
"""
import itertools,math,collections,json,hashlib
from .software_organization_space_v210 import validate

def normalize(state,*,structural_only=False):
 validate(state);groups=collections.defaultdict(list)
 for key,w in state['work'].items():
  color={'scope':len(set(w['scope'])) if structural_only else sorted(set(w['scope'])),'owner':w['owner'],'contributors':sorted(w.get('contributors',[])),'authors':sorted(w.get('authors',[])),'status':w['status'],'verifier':state['verification'].get(key)}
  groups[json.dumps(color,sort_keys=True)].append(key)
 colors=sorted(groups);n=math.prod(math.factorial(len(groups[k])) for k in colors)
 if n>40320:raise ValueError('Exceeded predeclared exact-isomorphism bound')
 best=None;best_map=None
 for combo in itertools.product(*(itertools.permutations(groups[k]) for k in colors)):
  order=[name for group in combo for name in group];mapping={k:str(i) for i,k in enumerate(order)}
  encoded={'members':state['members'],'delivery_member':state['delivery_member'],'roles':{k:sorted(set(v)) for k,v in state['roles'].items()},'work':[json.loads(k) for k,group in zip(colors,combo) for _ in group],'dependencies':sorted([mapping[a],mapping[b]] for a,b in state['dependencies']),'collaboration':sorted(state['collaboration']),'execution_order':[mapping[k] for k in state['execution_order']],'subteams':sorted(sorted(set(v)) for v in state['subteams'].values())}
  raw=json.dumps(encoded,sort_keys=True,separators=(',',':'),ensure_ascii=False)
  if best is None or raw<best:best,best_map=raw,mapping
 return {'sha256':hashlib.sha256(best.encode()).hexdigest(),'canonical':json.loads(best),'task_id_map':best_map,'permutations_checked':n,'member_identities_preserved':True,'public_scope_preserved':not structural_only}

def deduplicate(proposals):
 kept={}
 for p in proposals:
  key=normalize(p['target'])['sha256']
  if key not in kept:kept[key]={'representative':p,'equivalent_trace_count':0,'canonical_target':key}
  kept[key]['equivalent_trace_count']+=1
 return list(kept.values())

def novelty(q,r,features,gamma=1.):
 """Both coverages concern generated support only; gamma=1 first live proposal."""
 if set(q)!=set(r) or set(features)!=set(q) or not 0<=gamma<=1:raise ValueError('Same support and fixed gamma required')
 for d in (q,r):
  if any(v<=0 or not math.isfinite(v) for v in d.values()) or abs(sum(d.values())-1)>1e-10:raise ValueError('Positive normalized density')
 totals={}
 for field in ('struct','combo'):
  a=collections.defaultdict(float);b=collections.defaultdict(float)
  for k in q:a[features[k][field]]+=q[k];b[features[k][field]]+=r[k]
  totals[field]={g:max(0.,math.log(b[g]/a[g])) for g in a}
 return {k:{'struct':totals['struct'][features[k]['struct']],'combo':totals['combo'][features[k]['combo']],'combined':gamma*totals['struct'][features[k]['struct']]+(1-gamma)*totals['combo'][features[k]['combo']]} for k in q}
