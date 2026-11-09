"""Two extra private Pylint controls share the existing grader resource lanes."""
from types import ModuleType
from . import software_benchmark_scope_v181 as previous
from .software_benchmark_expansion_episode_v069 import clone_namespace
from .software_benchmark_candidates_v054 import reference
ROOT=previous.ROOT
STATE=ROOT/'runs/software-benchmark-v183/pylint-controls-r1'
VERSION='v183-separated-stdout-startup-witness-controls-r1'
CONSTRAINTS={**previous.CONSTRAINTS,'fresh_generation_slots':0,'generation_token_upper_bound':0,
 'maximum_control_containers':2,'maximum_code_score_containers':0,'maximum_delivery_score_containers':0,
 'maximum_actor_containers':0,'maximum_controller_containers':0,'maximum_containers':2,'maximum_named_volumes':0,
 'zero_model_diagnostic_pairs':0,'new_owned_user_units':[]}
_ns=clone_namespace(previous,VERSION=VERSION,STATE_ROOT=STATE,
 PLAN_FILE=STATE/'plan.json',INVENTORY_FILE=STATE/'inventory.json',SOURCE_FILE=STATE/'sources.json',
 AUTH_FILE=ROOT/'config/v183-pylint-controls-authority.json',GRADING_ROOT=STATE/'grading',
 COORDINATOR_ROOT=STATE/'coordinator',API_ROOT=STATE/'no-api',CONSTRAINTS=CONSTRAINTS,__file__=__file__)

def validate_plan(plan):
 if plan.get('version')!=VERSION or plan['rows'] or plan['constraints']!=CONSTRAINTS or set(plan['environments'])!={'pylint-dev__pylint-8898'}:
  raise ValueError('Only the same Pylint environment control pair is permitted')
 if set(plan['resources'])!={f'control-v183-pylint-dev__pylint-8898-{k}' for k in ('gold','empty')}:raise ValueError('Control identities changed')
 return plan
_ns['validate_plan']=validate_plan
globals().update({k:v for k,v in _ns.items() if not k.startswith('__')})
