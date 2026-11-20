"""Future-only SDK binding for opt-in graph navigation; no old module mutation."""
import inspect
from . import software_organization_runtime_v216_2 as baseline
from . import software_organization_runtime_v219 as repaired
from . import software_organization_world_v221 as world
VERSION='v221-opt-in-navigation-sdk-r1'
# Rebuild the established private namespace with this world's declared schema.
source=inspect.getsource(baseline)
assert source.count('software_organization_world_v216_2 as dynamic')==1
source=source.replace('software_organization_world_v216_2 as dynamic','software_organization_world_v221 as dynamic')
ns={'__name__':__name__+'_private','__package__':__package__,'__file__':__file__}
exec(compile(source,__file__+':private-binding','exec'),ns)
build_team_owner=ns['build_team_owner'];member_wire_tools=ns['member_wire_tools']
CONTRACT=repaired.CONTRACT+' Optional locate_work returns bounded file/symbol navigation hints, not proof of root cause. Follow its version-bound read_file range or use global search when missing. record_public_check binds an actual own test to a public requirement claim; public_check_status distinguishes no check, stale version and coverage still unverified. Passing tests or file presence alone never certify the original issue. These tools do not transfer responsibility, accept a review, or submit.'

def build_runtime(owner,prepared,*args,**kwargs):
 if not isinstance(prepared.world,world.World):raise ValueError('Use opt-in v221 managed world')
 if kwargs.get('worker_factory') is not None:raise ValueError('Preserve repaired worker identity')
 kwargs['worker_factory']=repaired.worker_type()
 return ns['build_runtime'](owner,prepared,*args,**kwargs)
close_runtime=repaired.close_runtime;lock_fixed_candidates=repaired.lock_fixed_candidates;set_native_limit=repaired.set_native_limit;enter_continuation=repaired.enter_continuation;run_fragment=repaired.run_fragment
