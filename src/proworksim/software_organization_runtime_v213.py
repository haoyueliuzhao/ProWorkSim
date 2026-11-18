"""Private namespace binding of the real pinned SDK to new dynamic managed tools.

Original modules and existing services are never patched. FREE2 is only the
fixed-roster substrate; dynamic execution/version identity is separately pinned.
"""
from types import SimpleNamespace
import inspect,copy
from . import software_role_baseline_runtime_v141 as baseline
from . import software_role_baseline_runtime_v203_2_1 as passive
from . import software_role_baseline_world_v141 as old_world
from . import software_organization_world_v213 as dynamic
from .software_fixed_organization_clone_v131 import clone_namespace,clone_function
VERSION='v213-published-review-sdk-r1'
CONTRACT=('Two actual members, private workspaces, original public task, shared 5M budget. Neither member has a fixed developer/reviewer role. '
 'Every leaf has one accountable owner. Before code work, assign_verification to the other non-author and add_collaboration, '
 'resolve dependencies, inspect work_readiness, then begin_work. Splitting preserves the original requirements. '
 'For an unmodified remaining package, offer_joint_arrangement plus the addressed member accept_joint_arrangement '
 'atomically changes owner, reviewer and implementation/evidence mode. Consent is never automatic. Joint changes require actual code progress followed by an executed public test; do not act on a future adjustment before the live proposal arrives. '
 'Code work: run actual public tests, fix_patch with real leaf IDs, complete_work; the assigned partner uses open_patch_review, run_patch_review_tests and org_review_patch on the immutable published version. This preserves their own different edits. Final member_001 integration is a separate explicit obligation. '
 'After local completion use reopen_work to revise: old authors/evidence remain but a new revision requires new publication/checks/review. '
 'No-code verification work: run actual same-version checks and complete_evidence using real requirement IDs and test sequence; '
 'the other checker explicitly adopt_evidence, tests and review_evidence. It does not require a new code patch. '
 'Use delivery_checklist to inspect missing steps. member_001 must explicitly integrate partner code and finally fix, test and submit_integration. '
 'This checklist neither repairs nor submits. If tests fail, inspect the saved report and distinguish relevant failures from unrelated baseline failures. Select justified public tests with the actual supported selector syntax; do not repeatedly run unchanged failing tests or claim full-suite success. For SymPy, keyword is a simple name substring, not a pytest expression. Diagnose and repair applicable failures; do not claim they passed. '
 'A contribution-level review does not claim the reviewer never authored any other code in the tree. '
 'All old FREE2/v211 hints are subordinate to this repairable contract.')

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
