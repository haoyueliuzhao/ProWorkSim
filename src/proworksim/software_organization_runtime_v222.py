"""Identical L/G schemas and base prompt; mode is never an extra solver hint."""
import inspect
from . import software_organization_runtime_v216_2 as base
from . import software_organization_runtime_v219 as repaired
from . import software_organization_runtime_v221 as navigation
from . import software_organization_world_v222 as world
VERSION='v222-matched-LG-sdk-r1';CONTRACT=navigation.CONTRACT
source=inspect.getsource(base).replace('software_organization_world_v216_2 as dynamic','software_organization_world_v222 as dynamic')
ns={'__name__':__name__+'_private','__package__':__package__,'__file__':__file__};exec(compile(source,__file__+':private','exec'),ns)
build_team_owner=ns['build_team_owner'];member_wire_tools=ns['member_wire_tools']
def build_runtime(owner,prepared,*args,**kwargs):
 if not isinstance(prepared.world,world.World):raise ValueError('Matched L/G world required')
 kwargs['worker_factory']=repaired.worker_type();return ns['build_runtime'](owner,prepared,*args,**kwargs)
close_runtime=repaired.close_runtime;lock_fixed_candidates=repaired.lock_fixed_candidates;set_native_limit=repaired.set_native_limit;enter_continuation=repaired.enter_continuation;run_fragment=repaired.run_fragment
