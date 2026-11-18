"""Private namespace binding of the real pinned SDK to new dynamic managed tools.

Original modules and existing services are never patched. FREE2 is only the
fixed-roster substrate; dynamic execution/version identity is separately pinned.
"""
from types import SimpleNamespace
import inspect,copy
from . import software_role_baseline_runtime_v141 as baseline
from . import software_role_baseline_runtime_v203_2_1 as passive
from . import software_role_baseline_world_v141 as old_world
from . import software_organization_world_v211 as dynamic
from .software_fixed_organization_clone_v131 import clone_namespace,clone_function
VERSION='v211-dynamic-sdk-r1'
CONTRACT=('SEWG dynamic work execution, two real members and private workspaces. Neither member has a fixed developer or reviewer role. '
 'The original public task and all acceptance requirements stay unchanged. Every unfinished package has one accountable owner. '
 'split_work keeps each child with its old owner; assign_work and offer_transfer only propose; the recipient must accept_transfer. '
 'Use dynamic_status to read actual owners and dependency state. begin_work on your owned leaf before code edits. '
 'Upstream work must locally complete and its exact patch be adopted before downstream edits. '
 'add_collaboration opens work-bound exchange, not private history access. assign_verification selects a non-author; '
 'publish with fix_patch(task_ids=[real_leaf_ids]), run actual same-version public tests and complete_work. '
 'The assigned other member must explicitly integrate_patch, test and org_review_patch. '
 'Review is per contribution, not a claim that either member never wrote any code in the final tree. '
 'member_001 remains the unique final integrator/export identity; it must adopt all contributions, test and explicitly submit. '
 'No graph label or lifecycle flag completes work. Frozen role-baseline hints are subordinate to this dynamic contract.')
def member_instruction(case,member):
 return CONTRACT+' You are '+member+'. Use the actual declared tools and original public task.'
proxy=SimpleNamespace(**{**vars(old_world),'SoftwareCollaborationPort':dynamic.SoftwareCollaborationPort,'tool_definitions':dynamic.tool_definitions,'member_instruction':member_instruction})
ns=clone_namespace(baseline,world=proxy)
# Preserve the already-repaired passive observer implementation and bind new schema.
ns['build_team_owner']=clone_function(passive._build_owner,ns)
base=SimpleNamespace(**ns)
pns=clone_namespace(passive,base=base)
pns['_build_owner']=ns['build_team_owner']
source=inspect.getsource(passive.build_team_owner)
assert source.count("organization_id != 'REVIEW2'")==1
source=source.replace("organization_id != 'REVIEW2'","organization_id != 'FREE2'").replace('This pilot freezes original two-member REVIEW2','Dynamic overlay requires the two-member FREE2 substrate')
exec(compile(source,__file__+':dynamic-owner','exec'),pns)
build_team_owner=pns['build_team_owner'];build_runtime=pns['build_runtime'];run_fragment=pns['run_fragment'];close_runtime=pns['close_runtime'];lock_fixed_candidates=pns['lock_fixed_candidates']
member_wire_tools=ns['member_wire_tools'];worker_type=ns['worker_type'];worker_config=ns['worker_config']
