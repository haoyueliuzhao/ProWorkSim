import copy,hashlib,json,shutil
from pathlib import Path
import pytest
from proworksim import software_organization_performance_v214 as fast
from proworksim.storage import json_bytes,atomic_write
from proworksim.core.journal import canonical_digest
from test_organization_world_v213 import prepare,M1,M2
from test_organization_world_v213 import test_divergent_private_trees_review_then_explicit_integrated_delivery as review_case
from proworksim.software_fixed_organization_clone_v131 import clone_function

def test_exact_encoding_normalization_and_atomic_invalidation(tmp_path):
 root=tmp_path/'world';(root/'control').mkdir(parents=True);s=fast.CachedStore(root);long='引号"\\\n😀'*1000
 state={'unicode':long,'alias1':[long,1.2,None,True],'tuple':(1,2),'keys':{1:'a','1':'b'},'nested':{'a':-0.0}}
 s.save(state);assert (root/'control/state.json').read_bytes()==json_bytes(state)
 assert s.load()==json.loads(json_bytes(state))
 x=s.load();x['alias1'].append(4);assert len(s.load()['alias1'])==4
 normalized=json.loads(json_bytes(state))
 assert s.encoder.digest(normalized)==canonical_digest(normalized)
 assert s.encoder.digest(normalized)==canonical_digest(normalized) and s.encoder.hits>0
 for fn in (s.encoder.digest,canonical_digest):
  with pytest.raises(TypeError):fn(state)
 with pytest.raises(ValueError):s.save({'bad':float('nan')})
 assert s.load()==json.loads(json_bytes(state))
 atomic_write(root/'control/state.json',json_bytes({'external':True}));assert s.load()=={'external':True}
 # Decoded immutable version callers must not share mutable descendants.
 bundle=root/'bundle.json';bundle.write_bytes(json_bytes({'values':[long]}));cache=fast.BundleCache(limit=100000)
 one=cache.get(bundle);one['values'].append('bad');assert len(cache.get(bundle)['values'])==1
 atomic_write(bundle,json_bytes({'new':'value'}));assert cache.get(bundle)=={'new':'value'}
 assert cache.size<=cache.limit

def normalize(x):
 if isinstance(x,dict):return {k:normalize(v) for k,v in x.items() if k not in ('wall_seconds','state_digests')}
 if isinstance(x,list):return [normalize(v) for v in x]
 return x

def test_same_observation_tools_results_rejection_and_replay(tmp_path):
 a,pa,_,_=prepare(tmp_path/'old');b,pb,_,_=prepare(tmp_path/'new')
 shutil.copytree(a.world.store.root,b.world.store.root,dirs_exist_ok=True);fast.attach(b)
 assert pa[M1].tools()==pb[M1].tools()
 steps=[('assign_verification',{'task_id':'work_root','reviewer':M2,'reason':'Independent'}),('add_collaboration',{'task_id':'work_root','peer':M2,'reason':'Exchange'}),('begin_work',{'task_id':'work_root'}),('write_file',{'path':'sample.py','text':'value = 2\n'}),('fix_patch',{'task_ids':['work_root'],'message':'Bound candidate'}),('write_file',{'path':'.git/config','text':'forbidden'})]
 for i,(tool,args) in enumerate(steps):
  ra=pa[M1].call(tool,request_key='same-'+str(i),association={},**args);rb=pb[M1].call(tool,request_key='same-'+str(i),association={},**args)
  assert normalize(ra)==normalize(rb)
  assert normalize(pa[M1].observe())==normalize(pb[M1].observe())
  assert normalize(a.world.store.load())==normalize(b.world.store.load())
 # Exact request replay cannot generate a second artifact/effect.
 ra=pa[M1].call('fix_patch',request_key='same-4',association={},**steps[4][1]);rb=pb[M1].call('fix_patch',request_key='same-4',association={},**steps[4][1]);assert normalize(ra)==normalize(rb)
 # The other REGISTERED member cannot read a newer unpublished version,
 # even after the permitted owner's read warmed the shared decode cache.
 assert pb[M1].call('write_file',request_key='private-successor',association={},path='sample.py',text='value = 5\n')['ok']
 b.world._bundle(M1)
 with pytest.raises(ValueError):b.world._bundle(M2,reference=b.world.org_current_identity(M1)['source_reference'])
 assert b.world.store.metrics['saved_cache'] and b.world.bundle_cache.hits

def test_actual_candidate_review_merge_and_delivery_with_fast_world(tmp_path):
 def optimized(p):
  result=prepare(p);fast.attach(result[0]);return result
 clone_function(review_case,{**review_case.__globals__,'prepare':optimized})(tmp_path)

def test_failed_apply_reused_version_and_post_commit_retry(tmp_path):
 p,_,c,_=prepare(tmp_path);fast.attach(p);w=p.world
 for t,a in [('assign_verification',{'task_id':'work_root','reviewer':M2,'reason':'Independent'}),('add_collaboration',{'task_id':'work_root','peer':M2,'reason':'Exchange'}),('begin_work',{'task_id':'work_root'})]:assert c(M1,t,**a)['ok']
 initial=w.org_current_identity(M1)
 def fail_apply(phase,details):
  if phase=='after_apply':raise ValueError('Synthetic abort after new-version read populated cache')
 w.fault_hook=fail_apply
 r=c(M1,'write_file',path='sample.py',text='value = 3\n');assert not r['ok'];w.fault_hook=None
 assert w.org_current_identity(M1)==initial
 assert c(M1,'write_file',path='sample.py',text='value = 2\n')['ok']
 assert w._bundle(M1)[2]['files']['sample.py']=='value = 2\n'
 def fail_commit(phase,details):
  if phase=='after_command_commit':raise RuntimeError('Synthetic process failure after durable commit')
 w.fault_hook=fail_commit
 with pytest.raises(RuntimeError):w.session(M1,fast.semantic.PROJECT).call('write_file',request_key='commit-then-replay',path='sample.py',text='value = 4\n')
 w.fault_hook=None;committed=w.org_current_identity(M1)
 r=w.session(M1,fast.semantic.PROJECT).call('write_file',request_key='commit-then-replay',path='sample.py',text='value = 4\n')
 assert r['ok'] and w.org_current_identity(M1)==committed
 assert w._bundle(M1)[2]['files']['sample.py']=='value = 4\n'
 assert fast.CachedStore(w.store.root).load()==w.store.load()
