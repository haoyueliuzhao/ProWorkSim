"""One independently owned empty-control retry with unchanged scoring semantics."""
from functools import lru_cache
import inspect
import textwrap
from types import FunctionType
from . import software_benchmark_grading_v105 as base
from . import software_benchmark_preparation_grading_v203_2_3_r3 as preparation
from . import software_benchmark_environment_v203_2_3_r2 as environment_adapter
from . import software_benchmark_project_closure_v203_2_3 as closure
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function
from .software_benchmark_grading_v131 import _lane_validator

VERSION='v203.2.3-strict-empty-recovery-scoring-r3'
MODULE='proworksim.software_benchmark_grading_v203_2_3_r3'
scope=preparation.preparation_scope()
scope.NETWORK_RESOLUTION_FILE=environment_adapter.RESOLUTION
_ns=clone_namespace(base,scope=scope,VERSION=VERSION,MODULE=MODULE,__file__=__file__)
_parent_scorer,_parent_host,_parent_environment=_ns['scorer'],_ns['host'],_ns['private_environment']


def private_environment(policy):
    return environment_adapter.private_environment(policy,scope,_parent_environment)


def scorer(policy,*,manifest_provider=None):
    value=_parent_scorer(policy,manifest_provider=manifest_provider)
    namespace=value.validate_request.__globals__
    namespace.update(validate_delivery_evidence=closure.validate_delivery_evidence,MAX_GRADERS=1)
    namespace['validate_request']=_lane_validator(namespace)
    from .software_namespace_witness_v183 import bind_scorer
    bind_scorer(value)
    parent_manifest=namespace['installation_manifest']
    def manifest():
        result=parent_manifest()
        if manifest_provider is not None:return result
        return {**result,'managed_delivery_validator':reference(closure.__file__),
            'current_endpoint_scoring_adapter':reference(__file__),
            'environment_adapter':reference(environment_adapter.__file__),
            'profile':reference(environment_adapter.RESOLUTION),
            'scoring_CA_profile':reference(scope.CA_PROFILE_FILE),
            'scoring_CA_tasks':[environment_adapter.TASK],
            'original_CA_file_and_candidate_unchanged':True,'maximum_graders':1,
            'public_network':'Requests1766 scorer only, same frozen current numeric httpbin IP:80/443; solver none',
            'fresh_control_plan':reference(preparation.CONTROL_PLAN_FILE),
            'recovery_guard':reference(preparation.__file__),
            'transport_error_policy_changed':False,'new_control_kind':'empty only'}
    namespace['installation_manifest']=manifest
    for name in ('validate_request','installation_manifest','validate_delivery_evidence'):
        setattr(value,name,namespace[name])
    return value


def host(policy,scoring):
    return _parent_host(policy,scoring)


def prepare_environment_qualifications_local():
    scoring=scorer(scope.dispatch_view());scoring.environment.prepare()
    manifest=scope.retain(scope.COORDINATOR_ROOT/'scorer-manifest.json',scoring.installation_manifest())
    plan_ref=reference(preparation.CONTROL_PLAN_FILE)
    plan=preparation.validate_control_plan(scope.load(plan_ref))
    task=environment_adapter.TASK;key='control-r3-'+task+'-empty'
    if set(plan['resources'])!={key}:raise ValueError('Only the single new empty control is planned')
    request={'version':VERSION,'resource_key':key,'instance_id':task,'slot_id':None,
        'plan':plan_ref,'configuration':plan['environments'][task]['configuration'],'patch_kind':'empty',
        'limits':scoring.LIMITS,'scorer_manifest':manifest,'cpuset_cpus':None,
        'directory':str(scope.GRADING_ROOT/key),'candidate_lock':None,
        **scoring.environment.request_fields(task)}
    ref=scope.retain(scope.GRADING_ROOT/key/'request.json',request)
    result={'controls':[ref],'model_calls':0,'gold_will_be_strictly_reused_from':'r2',
        'profile_unchanged':reference(environment_adapter.RESOLUTION),'previous_unknown_preserved':True}
    scope.retain(scope.COORDINATOR_ROOT/'preparation.json',result)
    return result


_ns.update(private_environment=private_environment,scorer=scorer,host=host,
           prepare_environment_qualifications_local=prepare_environment_qualifications_local)
for _name in ('score_request','main'):
    source=inspect.getsource(getattr(base,_name)).replace("'v105.run'","'v203.2.3.run'")
    exec(compile(source,__file__+':'+_name,'exec'),_ns)
_ns['cold_manifest']=lru_cache(maxsize=1)(clone_function(base.cold_manifest.__wrapped__,_ns))
_methods={key:clone_function(value,_ns) for key,value in vars(base.Grading).items() if isinstance(value,FunctionType)}
source=textwrap.dedent(inspect.getsource(base.Grading.run_request)).replace("'v105.run'","'v203.2.3.run'")
local={};exec(compile(source,__file__+':grading-child','exec'),_ns,local)
_methods['run_request']=local['run_request'];_ns['Grading']=type('Grading',(base.Grading,),_methods)
globals().update({key:value for key,value in _ns.items() if not key.startswith('__')})

if __name__=='__main__':_ns['main']()
