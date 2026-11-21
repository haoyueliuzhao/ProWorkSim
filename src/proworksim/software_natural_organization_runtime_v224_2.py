"""Same SDK/history/budget, matched to the relaxed experimental timing rule."""
import inspect
from . import software_organization_runtime_v216_2 as baseline
from . import software_organization_runtime_v223_1 as validated
from . import software_organization_runtime_v219 as repaired
from . import software_natural_organization_world_v224_2 as world
from .software_runtime_performance_v222_1 import VERSION as PERFORMANCE_VERSION
VERSION='v224.2-natural-coordination-sdk-r1'
source=inspect.getsource(baseline).replace('software_organization_world_v216_2 as dynamic','software_natural_organization_world_v224_2 as dynamic')
old='Joint changes require actual code progress followed by an executed public test; do not act on a future adjustment before the live proposal arrives.'
assert old in source
source=source.replace(old,'Consensual arrangements do not require a prior edit or public test. Ordinary work and initial allocation continue naturally; a proposed change never implies consent.')
explanation=validated.EXPLANATION.replace('which requires real edit/test progress and is used for later remaining-work adaptation','which is a consensual arrangement for unmodified work and does not require prior edits or tests')
source=source.replace('def member_instruction(case,member):','CONTRACT += '+repr(explanation)+'\n\ndef member_instruction(case,member):')
ns={'__name__':__name__+'_private','__package__':__package__,'__file__':__file__};exec(compile(source,__file__+':private','exec'),ns)
CONTRACT=ns['CONTRACT'];build_team_owner=ns['build_team_owner'];member_wire_tools=ns['member_wire_tools']
def build_runtime(owner,prepared,*args,**kwargs):
 if not isinstance(prepared.world,world.World) or getattr(prepared.world,'performance_revision',None)!=PERFORMANCE_VERSION:raise ValueError('Use the v224.2 world')
 kwargs['worker_factory']=repaired.worker_type();return ns['build_runtime'](owner,prepared,*args,**kwargs)
close_runtime=repaired.close_runtime;lock_fixed_candidates=repaired.lock_fixed_candidates;set_native_limit=repaired.set_native_limit;enter_continuation=repaired.enter_continuation;run_fragment=repaired.run_fragment
