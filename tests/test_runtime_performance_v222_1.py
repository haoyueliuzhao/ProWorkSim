import copy,types
import pytest
from proworksim import software_runtime_performance_v222_1 as optimized
from proworksim import software_organization_performance_v214 as old
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.storage import json_bytes,digest,atomic_write
from test_organization_world_v213 import prepare,M1,M2
import test_organization_performance_v214 as prior_tests

def attach(p):old.attach(p);optimized.install(p.world);return p

def test_exact_identity_copy_version_and_permissions(tmp_path):
 p,ports,c,_=prepare(tmp_path);attach(p);w=p.world
 original=w.org_current_identity(M1);again=w.org_current_identity(M1)
 assert original==again and optimized.metrics(w)['version_identity_cache']['hits']>=1
 again['source_reference']['version_id']='poison';assert w.org_current_identity(M1)==original
 artifact,version,bundle=w._bundle(M1)
 assert original['files_sha256']==digest(json_bytes(bundle['files']))
 assert c(M1,'assign_verification',task_id='work_root',reviewer=M2,reason='review')['ok']
 assert c(M1,'add_collaboration',task_id='work_root',peer=M2,reason='review')['ok']
 assert c(M1,'begin_work',task_id='work_root')['ok']
 assert c(M1,'write_file',path='sample.py',text='value = 3\n')['ok']
 changed=w.org_current_identity(M1);assert changed!=original
 # A warmed owner entry is never a permission bypass.
 with pytest.raises(ValueError):w._bundle(M2,reference=changed['source_reference'])
 # Same version path replaced atomically: timestamp invalidation, no stale hash.
 art,v,b=w._bundle(M1);path=w.store.version_path(art,v);b['files']['sample.py']='value = 4\n';atomic_write(path,json_bytes(b))
 assert w.org_current_identity(M1)['files_sha256']==digest(json_bytes(b['files']))
 # Permission revoked after warming must still be enforced before any hit.
 actual=w._bundle
 def denied(*args,**kwargs):raise PermissionError('test revocation')
 w._bundle=denied
 with pytest.raises(PermissionError):w.org_current_identity(M1)
 w._bundle=actual

def test_oversized_decode_cache_and_replacement_race_do_not_cache_wrong_version(tmp_path):
 p,_,_,_=prepare(tmp_path);attach(p);w=p.world
 w.bundle_cache=old.BundleCache(limit=1)
 a=w.org_current_identity(M1);assert not w._version_identity_cache
 w.bundle_cache=old.BundleCache();actual=w._bundle
 def replacing(*args,**kwargs):
  art,v,b=actual(*args,**kwargs);modified=copy.deepcopy(b);modified['files']['sample.py']='value = 99\n';atomic_write(w.store.version_path(art,v),json_bytes(modified));return art,v,b
 w._bundle=replacing
 assert w.org_current_identity(M1)==a and not w._version_identity_cache
 w._bundle=actual;assert w.org_current_identity(M1)!=a

@pytest.mark.parametrize('name',[
 'test_same_observation_tools_results_rejection_and_replay',
 'test_actual_candidate_review_merge_and_delivery_with_fast_world',
 'test_failed_apply_reused_version_and_post_commit_retry'])
def test_existing_real_semantics_with_new_private_identity_cache(tmp_path,name):
 facade=types.SimpleNamespace(**{**vars(old),'attach':attach})
 fn=getattr(prior_tests,name);clone_function(fn,{**fn.__globals__,'fast':facade})(tmp_path)
