"""Complete the four original Pylint identities with the qualified witness repair."""
from pathlib import Path
from types import ModuleType,FunctionType
from . import software_benchmark_scope_v181 as original_scope
from . import software_context_task_api_v181 as original_api
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function

TASK='pylint-dev__pylint-8898'
ROOT=original_scope.ROOT
STATE=ROOT/'runs/software-benchmark-v184/pylint-completion-r1'
VERSION='v184-original-Pylint-four-condition-completion-r1'
_ns=clone_namespace(original_scope,STATE_ROOT=STATE,API_ROOT=STATE/'api-coordinator',
 COORDINATOR_ROOT=STATE/'grading-coordinator',GRADING_ROOT=STATE/'grading',SOURCE_FILE=STATE/'sources.json',
 AUTH_FILE=ROOT/'config/v184-pylint-completion-authority.json',
 API_UNIT='proworksim-v184-pylint-completion.service',__file__=__file__)
_allowed=_ns['require_allowed']

def allowed(operation='v181.run',*,slot_id=None,instance_id=None,**kwargs):
    if instance_id not in (None,TASK) or slot_id is not None and slot_id.split(':')[1]!=TASK:
        raise PermissionError('This companion owner may only execute the original Pylint task')
    return _allowed(operation,slot_id=slot_id,instance_id=instance_id,**kwargs)
_ns.update(require_allowed=allowed,require_grading_allowed=allowed)
scope=ModuleType(__name__+'.scope');scope.__dict__.update(_ns)
_api={**vars(original_api),'scope':scope}
_api['Route']=type('Route',(original_api.Route,),{k:clone_function(v,_api)
 for k,v in vars(original_api.Route).items() if isinstance(v,FunctionType)})
_parent=type('Runtime',(original_api.Runtime,),{k:clone_function(v,_api)
 for k,v in vars(original_api.Runtime).items() if isinstance(v,FunctionType)})

class Runtime(_parent):
    def resident(self,row):
        with self.lock:return super().resident(row)
