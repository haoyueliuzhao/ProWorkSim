"""New-world deployment entry with matched L/G tools and exact identity caching."""
from . import software_organization_world_v222 as prior
from .software_runtime_performance_v222_1 import install
World=prior.World
Port=prior.Port
PROJECT=prior.PROJECT
tool_definitions=prior.tool_definitions
register_proposal=prior.register_proposal
SoftwareCollaborationPort=Port
SoftwareCollaborationWorld=World

def attach(prepared,requirements,*,condition='L'):
 prior.attach(prepared,requirements,condition=condition)
 install(prepared.world)
 return prepared
