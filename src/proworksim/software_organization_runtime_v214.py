"""New-deployment runtime: same v213 model contract, optimized private persistence.

Import/select this runtime for NEW episodes. It does not migrate, stop or patch
an already running v213 episode and it does not authorize additional API runs.
"""
from . import software_organization_runtime_v213 as original
from . import software_organization_performance_v214 as performance
VERSION=original.VERSION
DEPLOYMENT_VERSION=performance.VERSION
CONTRACT=original.CONTRACT
member_instruction=original.member_instruction
member_wire_tools=original.member_wire_tools
build_team_owner=original.build_team_owner
run_fragment=original.run_fragment
close_runtime=original.close_runtime
lock_fixed_candidates=original.lock_fixed_candidates
worker_type=original.worker_type
worker_config=original.worker_config

def build_runtime(owner,prepared,*args,**kwargs):
 if not isinstance(prepared.world,performance.World):performance.attach(prepared)
 return original.build_runtime(owner,prepared,*args,**kwargs)
