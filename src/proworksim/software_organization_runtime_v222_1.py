"""Future-only SDK entry; old experiments retain their exact frozen bindings."""
from . import software_organization_runtime_v222 as prior
from .software_runtime_performance_v222_1 import VERSION as PERFORMANCE_VERSION
VERSION='v222.1-unchanged-policy-exact-identity-cache-r1'
CONTRACT=prior.CONTRACT
build_team_owner=prior.build_team_owner
member_wire_tools=prior.member_wire_tools
close_runtime=prior.close_runtime
lock_fixed_candidates=prior.lock_fixed_candidates
set_native_limit=prior.set_native_limit
enter_continuation=prior.enter_continuation
run_fragment=prior.run_fragment

def build_runtime(owner,prepared,*args,**kwargs):
 if getattr(prepared.world,'performance_revision',None)!=PERFORMANCE_VERSION:
  raise ValueError('Prepare a new world with software_organization_world_v222_1.attach first')
 return prior.build_runtime(owner,prepared,*args,**kwargs)
