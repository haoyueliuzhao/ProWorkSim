"""Validate each frozen context-row candidate against its shared task qualification.

Condition identity remains on the score request/candidate. Only qualification
lookup maps a completely frozen row to the representative environment config.
The original scorer, official tests, and current control manifests are retained.
"""
from __future__ import annotations
from functools import lru_cache
from types import FunctionType
from . import software_benchmark_grading_v203_2_3_r2 as original
from . import software_benchmark_scope_v203_2_3 as scope
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function

VERSION='v203.2.3-frozen-condition-qualification-views-r2'
MODULE='proworksim.software_benchmark_grading_views_v203_2_3_r2'
CONDITION_FIELDS=frozenset({'slot_id','slot_index','logical_index','group_id','condition_id','condition',
                           'configuration','role_context_condition'})


def canonical_environment_config(config,plan_ref):
    if plan_ref!=reference(scope.PLAN_FILE):raise ValueError('Qualification view requires this exact new plan')
    plan=scope.validate_plan(scope.load(plan_ref))
    task=config.get('instance_id')
    matches=[r for r in plan['rows'] if r['instance_id']==task and scope.load(r['configuration'])==config]
    if len(matches)!=1:raise ValueError('Candidate configuration is not an exact frozen condition row')
    canonical=scope.load(plan['environments'][task]['configuration'])
    if {k:v for k,v in config.items() if k not in CONDITION_FIELDS}!={k:v for k,v in canonical.items() if k not in CONDITION_FIELDS}:
        raise ValueError('A condition changed task input, official environment, model, seed, or public rules')
    if original.base.environment_identity(config)!=original.base.environment_identity(canonical):
        raise ValueError('Official task environment identity differs across context conditions')
    return canonical


def scorer(policy,*,manifest_provider=None):
    value=original.scorer(policy,manifest_provider=manifest_provider)
    previous=value.validate_qualification
    def validate_qualification(ref,config,plan_ref):
        return previous(ref,canonical_environment_config(config,plan_ref),plan_ref)
    value.validate_request.__globals__['validate_qualification']=validate_qualification
    value.validate_qualification=validate_qualification
    return value


_ns=clone_namespace(original,scope=original.scope,MODULE=MODULE,__file__=__file__)
_ns['scorer']=scorer
_ns['cold_manifest']=lru_cache(maxsize=1)(clone_function(original.cold_manifest.__wrapped__,_ns))
_methods={k:clone_function(v,_ns) for k,v in vars(original.Grading).items() if isinstance(v,FunctionType)}
_ns['Grading']=type('Grading',(original.Grading,),_methods)
for _name in ('factory','score_request','main','command'):
    _ns[_name]=clone_function(getattr(original,_name),_ns)
for _name in ('factory','score_request','main','command','Grading','cold_manifest'):
    globals()[_name]=_ns[_name]

if __name__=='__main__':main()
