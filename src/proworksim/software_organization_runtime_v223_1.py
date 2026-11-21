"""Private SDK binding for the revised interface, keeping solver budgets/history."""
import inspect
from . import software_organization_runtime_v216_2 as baseline
from . import software_organization_runtime_v219 as repaired
from . import software_organization_world_v223_1 as world
from .software_runtime_performance_v222_1 import VERSION as PERFORMANCE_VERSION
VERSION='v223.1-typed-feedback-and-decision-handoff-sdk-r1'
EXPLANATION=(' Initial work allocation uses assign_work (or offer_transfer), followed by the recipient accept_transfer; a message is not an assignment. These initial offers are different from offer_joint_arrangement, which requires real edit/test progress and is used for later remaining-work adaptation. Fill independent reviewer/collaboration setup after actual ownership is established. '
 ' For repository searches, complete=false means the search is unfinished even if matches is empty; use continue_search or a precise public symbol query. locate_work prioritizes exact public symbol definitions, which are not proof of cause. Test diagnostic_summary shows saved failures and exact detail-page cursors; do not guess cursor hashes or rerun merely to read output. '
 ' The latest organization_decision_explanation overrides informal earlier transfer plans: KEEP retains owners and dependencies; no member should try to transfer under KEEP. Ordinary missing reviewer/collaboration setup remains available. Character offsets in project relations are not line numbers. ')
source=inspect.getsource(baseline).replace('software_organization_world_v216_2 as dynamic','software_organization_world_v223_1 as dynamic')
source=source.replace('def member_instruction(case,member):','CONTRACT += '+repr(EXPLANATION)+'\n\ndef member_instruction(case,member):')
ns={'__name__':__name__+'_private','__package__':__package__,'__file__':__file__};exec(compile(source,__file__+':private','exec'),ns)
CONTRACT=ns['CONTRACT'];build_team_owner=ns['build_team_owner'];member_wire_tools=ns['member_wire_tools']
def build_runtime(owner,prepared,*args,**kwargs):
 if not isinstance(prepared.world,world.World) or getattr(prepared.world,'performance_revision',None)!=PERFORMANCE_VERSION:raise ValueError('New v223.1 world and cache required')
 kwargs['worker_factory']=repaired.worker_type();return ns['build_runtime'](owner,prepared,*args,**kwargs)
close_runtime=repaired.close_runtime;lock_fixed_candidates=repaired.lock_fixed_candidates;set_native_limit=repaired.set_native_limit;enter_continuation=repaired.enter_continuation;run_fragment=repaired.run_fragment
