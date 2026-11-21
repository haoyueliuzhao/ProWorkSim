"""Consent/identity constraints, without the experimental edit-then-test gate."""
import copy
from . import software_organization_world_v223_1 as prior
from .software_organization_world_v212 import SoftwareCollaborationWorld as JointContract
PROJECT=prior.PROJECT;VERSION='v224.2-natural-coordination-r1'
def tool_definitions(case):
 tools=copy.deepcopy(prior.tool_definitions(case))
 for t in tools:
  if t['name']=='offer_joint_arrangement':t['description']+=' No prior code edit or test is required to make an owner/reviewer arrangement. Acceptance remains explicit. Already-authored work retains its authors and cannot be transferred through this unstarted-work operation.'
  if t['name']=='split_work':t['description']+=' Split only if useful for the real issue. No fixed count or one-package-per-annotation requirement.'
 return tools
class World(prior.World):
 def _tool_definitions(self,project_id):return tool_definitions(self._software()['case']) if project_id==PROJECT else super()._tool_definitions(project_id)
 def _action_offer_joint_arrangement(self,actor,project_id,**arguments):
  # Keep the original consent, authorship, revision, reviewer and mode checks.
  # Bypass only v213's experimental requirement of a previous edit and test.
  return JointContract._action_offer_joint_arrangement(self,actor,project_id,**arguments)
class Port(prior.Port):pass
def attach(prepared,requirements,*,condition='G'):
 prior.attach(prepared,requirements,condition=condition);prepared.world.__class__=World;return prepared
SoftwareCollaborationWorld=World;SoftwareCollaborationPort=Port;register_proposal=prior.register_proposal
