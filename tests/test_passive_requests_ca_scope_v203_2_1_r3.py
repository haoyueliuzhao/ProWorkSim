"""Independent CA control resource admission; temporary claims, no Docker."""
from pathlib import Path
import pytest
from proworksim import software_benchmark_scope_passive_requests_v203_2_1_r3 as scope
from proworksim.software_benchmark_candidates_v054 import reference,write_new


def test_disjoint_lanes_two_control_plan_and_joint_full_reservation():
 plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
 assert len(plan['resources'])==2 and plan['rows']==[]
 parent=set(scope.parent.host_cpu_pool()[:64])
 lanes=[{int(x) for x in scope.cpu_set('grader',i).split(',')} for i in (0,1)]
 assert len(lanes[0])==len(lanes[1])==4 and not lanes[0]&lanes[1]
 assert not (lanes[0]|lanes[1])&parent
 assert scope.COMBINED_CPU==72 and scope.COMBINED_MEMORY==496*scope.GIB
 assert scope.COMBINED_DISK_FLOOR==168*scope.GIB
 with pytest.raises(PermissionError):scope.require_allowed('v203.2.1.api.request')
 with pytest.raises(ValueError):scope.cpu_set('actor',0)


def test_native_allocator_claims_and_cleanup_never_touch_parent(tmp_path,monkeypatch):
 real=scope.load(reference(scope.PLAN_FILE));plan=write_new(tmp_path/'plan.json',real)
 auth=write_new(tmp_path/'auth.json',{'CPU_fixture':True})
 policy=scope.dispatch_view(lambda *a,**k:{'plan':plan})
 ns=policy.claim_resource.__globals__;ns.update(BATCH_ROOT=tmp_path,AUTHORIZATION_FILE=Path(auth['path']),
  require_v066_allowed=lambda *a,**k:{'plan':plan})
 monkeypatch.setattr(scope,'physical_capacity',lambda:{'passed':True,'CPU_fixture':True})
 keys=sorted(real['resources']);claims=[policy.claim_resource(key,lane=i) for i,key in enumerate(keys)]
 for i,ref in enumerate(claims):
  c=scope.load(ref);assert c['reserved_cpu']==4 and c['reserved_memory_bytes']==16*scope.GIB
  assert Path(c['lease']).parent==tmp_path/'resource-claims'
  assert c['admission']['reserved_memory_bytes_after']==(i+1)*20*scope.GIB
  assert c['docker_name'].startswith('pws-v066-')
 with pytest.raises(scope.ResourceBusy):scope._budget([scope.load(r) for r in claims],4,16*scope.GIB)
 for ref in claims:assert policy.release_resource(ref,quiescent=True)
 assert not list((tmp_path/'resource-claims').glob('active-*.json'))
 # The parent can legitimately change while live, so no equality assertion on
 # its active rows; this code never writes there. All actual leases were above.
 assert not any(str(scope.parent.BATCH_ROOT) in str(scope.load(r)['lease']) for r in claims)
