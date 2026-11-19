"""Targeted KEEP isolation and actionable, deduplicated delivery observations.

No owner writes, automatic acceptance, testing, completion or submission.
Full current state remains available through existing explicit read-only tools.
"""
import copy
from . import software_organization_world_v216 as old
PROJECT=old.PROJECT
VERSION='v216.2-kept-structure-actionable-observation-r1'
tool_definitions=old.tool_definitions
STRUCTURAL={'split_work','assign_work','offer_transfer','accept_transfer','offer_joint_arrangement','accept_joint_arrangement','change_dependency'}

def compact_observation(value):
    """Only the default presentation changes; explicit tools keep full receipts."""
    v=copy.deepcopy(value)
    graph=v.get('dynamic_organization',{})
    lifecycle=graph.get('lifecycle',{})
    proposal=lifecycle.pop('proposal',None)
    # The same proposal/target previously appeared twice in every observation.
    choice=v.get('organization_choice')
    if proposal:
        v['organization_decision']={k:proposal.get(k) for k in ('candidate_id','keep','reason')}
        if not choice:v['organization_decision']['operations']=proposal.get('operations',[])
        v['organization_decision']['full_record_tool']='dynamic_status'
    # These are byte-identical duplicates of the final-integrator readiness.
    status=v.get('delivery_status',{})
    status.pop('delivery_readiness',None)
    # Keep actor-relative checklist: for member002 it may differ from final001.
    actor_check=graph.pop('delivery_gaps',None)
    if actor_check is not None:
        v['actor_delivery_checklist']=actor_check
        if status.get('delivery_checklist')==actor_check:status.pop('delivery_checklist')
    final=v.get('delivery_readiness',{}).get('package_chain')
    if final is not None and final==actor_check:
        v['actor_delivery_checklist']={'same_as':'delivery_readiness.package_chain'}
    v['observation_revision']=VERSION
    return v

class World(old.World):
    def keep_locked(self):
        p=self.protocol();choice=p.get('choice') or {}
        return bool(p.get('proposal') and (p['proposal'].get('keep') or choice.get('decision') in ('keep','defer')))
    def _tool_project_action(self,actor,project_id,tool,arguments,interface_profile=None):
        if self.keep_locked():
            if tool in STRUCTURAL:
                self.org_reject('This branch keeps the checkpoint scope, owners and dependencies. Continue repair, review and delivery with current owners; responsibility changes are disabled.', 'kept_arrangement_frozen',tool=tool)
            if tool=='assign_verification':
                w=self.dynamic()['work'].get(arguments.get('task_id'),{})
                if w.get('reviewer') not in (None,arguments.get('reviewer')):
                    self.org_reject('KEEP permits filling a missing reviewer, not changing an existing one','kept_arrangement_frozen')
        return super()._tool_project_action(actor,project_id,tool,arguments,interface_profile)
    def _action_work_readiness(self,actor,project_id,task_id):
        v=super()._action_work_readiness(actor,project_id,task_id)
        for gap in v['gaps']:
            if gap['kind']=='upstream_patch_not_adopted':
                gap['next_explicit_action']={'tool':'integrate_patch','arguments':{'patch_id':gap['patch_id']},'note':'Reviewing a published tree does not adopt it into your working tree.'}
        return v
    def _action_delivery_readiness(self,actor,project_id):
        v=super()._action_delivery_readiness(actor,project_id)
        next_actions=[]
        for row in v['package_chain']['packages']:
            tid=row['task_id'];owner=row['owner'];reviewer=row['reviewer'];c=row['completion'];missing=row['missing']
            if not missing:continue
            if c is None:
                readiness=self._action_work_readiness(owner,PROJECT,tid)
                next_actions.append({'actor':owner,'task_id':tid,'tool':'work_readiness','arguments':{'task_id':tid},'current_gaps':readiness['gaps']})
                if readiness['ready']:
                    current=self.org_current_identity(owner)
                    patches=[p for p in self._software()['patches'].values() if tid in p['task_snapshots'] and p['author']==owner and self.org_patch_identity(p['patch_id'])==current and self._artifact_current(p)]
                    if patches:next_actions.append({'actor':owner,'tool':'complete_work','arguments':{'task_id':tid,'patch_id':patches[-1]['patch_id']},'note':'Requires successful actual test of this version.'})
                    else:next_actions.append({'actor':owner,'task_id':tid,'tools':['begin_work','run_tests','fix_patch','complete_work'],'alternative_if_no_code_contribution':'run_tests then complete_evidence with actual requirement IDs and test sequence; do not invent unnecessary edits'})
            elif 'reopen_stale_completion' in missing or 'evidence_version_differs_from_final_tree_revalidate' in missing:
                next_actions.append({'actor':owner,'task_id':tid,'tool':'reopen_work','arguments':{'task_id':tid,'reason':'Refresh stale completion against the final version'},'then':'Explicitly align final tree, test, complete and obtain fresh independent review.'})
            elif 'independent_current_review' in missing and reviewer:
                if c.get('kind')=='evidence':
                    next_actions.append({'actor':reviewer,'task_id':tid,'evidence_id':c['evidence_id'],'tools':['adopt_evidence','run_tests(evidence_id)','review_evidence'],'note':'Accept only after actual version-bound checks; request changes if needed.'})
                else:
                    next_actions.append({'actor':reviewer,'task_id':tid,'patch_id':c['patch_id'],'tools':['open_patch_review','run_patch_review_tests','org_review_patch'],'note':'Accept or request changes using actual checks, never assume acceptance.'})
            if c and 'integrate_partner_patch' in missing and 'independent_current_review' not in missing:
                next_actions.append({'actor':'member_001','task_id':tid,'tool':'integrate_patch','arguments':{'patch_id':c['patch_id']}})
        if next_actions:
            v['next_actions']=next_actions
            v['final_steps_after_package_chain']=['run_tests','fix_patch','submit_integration']
        v['presentation_revision']=VERSION
        return v

class Port(old.Port):
    def observe(self):return compact_observation(super().observe())

def attach(prepared,requirements):
    old.attach(prepared,requirements);prepared.world.__class__=World
    return prepared
register_proposal=old.register_proposal
SoftwareCollaborationPort=Port
SoftwareCollaborationWorld=World
