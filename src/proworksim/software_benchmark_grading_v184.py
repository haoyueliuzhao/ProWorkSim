"""Fresh official gold/empty controls and asynchronous scoring, no network tasks."""
from functools import lru_cache
import inspect
from types import FunctionType
from . import software_benchmark_grading_v105 as base
from .software_context_pylint_v184 import scope,TASK
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function
from . import software_benchmark_project_closure_v181 as closure
from .software_benchmark_delivery_reuse_v175 import bind_host
from .software_benchmark_grading_v131 import _lane_validator

VERSION='v184-original-Pylint-candidate-score-r1'
MODULE='proworksim.software_benchmark_grading_v184'
_ns=clone_namespace(base,scope=scope,VERSION=VERSION,MODULE=MODULE,__file__=__file__)
_parent_scorer=_ns['scorer'];_parent_host=_ns['host'];_parent_environment=_ns['private_environment']


def private_environment(policy):
    value=_parent_environment(policy)
    def prepare():
        return scope.retain(scope.GRADING_ROOT/'environments/bindings.json',
            {'version':VERSION,'offline':None,'tls':None,'network_resolutions':{},'all_selected_tasks_network_none':True})
    value.__dict__.update(prepare=prepare,TASKS=frozenset(),TLS_TASKS=frozenset(),OFFLINE_TASKS=frozenset())
    return value


def scorer(policy,*,manifest_provider=None):
    value=_parent_scorer(policy,manifest_provider=manifest_provider)
    ns=value.validate_request.__globals__
    ns.update(validate_delivery_evidence=closure.validate_delivery_evidence,MAX_GRADERS=2)
    ns['validate_request']=_lane_validator(ns)
    # Fresh gold/empty for every selected environment: no inherited score cache.
    ns['validate_qualification']=validate_qualification
    from .software_namespace_witness_v183 import bind_scorer
    bind_scorer(value)
    original_manifest=ns['installation_manifest']
    def manifest():
        result=original_manifest()
        if manifest_provider is not None:return result
        return {**result,'managed_delivery_validator':reference(closure.__file__),
            'context_score_adapter':reference(__file__),'public_network':'none',
            'namespace_witness_adapter':reference(scope.ROOT/'src/proworksim/software_namespace_witness_v183.py'),
            'requests_capabilities_by_task':{},'maximum_real_tls_sessions':0}
    ns['installation_manifest']=manifest
    for name in ('validate_request','validate_qualification','installation_manifest','validate_delivery_evidence'):
        setattr(value,name,ns[name])
    return value


def host(policy,scoring):
    value=_parent_host(policy,scoring)
    return bind_host(value)


def validate_qualification(ref,config,plan_ref):
    from . import software_benchmark_grading_v183 as controls
    from . import software_benchmark_scope_v183 as control_scope
    value=scope.load(ref)
    source=reference(control_scope.COORDINATOR_ROOT/'qualifications'/(TASK+'.json'))
    if (config['instance_id']!=TASK or plan_ref!=reference(scope.PLAN_FILE)
        or value!={'version':VERSION,'passed':True,'instance_id':TASK,'plan':plan_ref,'source_qualification':source}):
        raise ValueError('Repaired control provenance or task changed')
    original=controls.scorer(control_scope.dispatch_view())
    original.validate_qualification(source,config,reference(control_scope.PLAN_FILE))
    current=cold_manifest();old=scope.load(reference(control_scope.COORDINATOR_ROOT/'scorer-manifest.json'))
    for key in ('parent','limits','archive_adapter','cap_add','cap_drop','no_new_privileges',
                'diagnostic_upstream_sha256','namespace_witness_adapter','official_tests_and_scoring_rules_changed'):
        if current.get(key)!=old.get(key):raise ValueError('Repaired official evaluator differs from actual control: '+key)
    return value


def prepare_environment_qualifications_local():
    from . import software_benchmark_scope_v183 as controls
    scoring=scorer(scope.dispatch_view());scoring.environment.prepare()
    scope.retain(scope.COORDINATOR_ROOT/'scorer-manifest.json',scoring.installation_manifest())
    value={'version':VERSION,'passed':True,'instance_id':TASK,'plan':reference(scope.PLAN_FILE),
        'source_qualification':reference(controls.COORDINATOR_ROOT/'qualifications'/(TASK+'.json'))}
    ref=scope.retain(scope.COORDINATOR_ROOT/'qualifications'/(TASK+'.json'),value)
    plan=scope.load(reference(scope.PLAN_FILE))
    validate_qualification(ref,scope.load(plan['environments'][TASK]['configuration']),reference(scope.PLAN_FILE))
    return {'qualifications':{TASK:ref},'controls':[],'model_calls':0}


_ns.update(private_environment=private_environment,scorer=scorer,host=host,
    prepare_environment_qualifications_local=prepare_environment_qualifications_local)
for name in ('score_request','main'):
    source=inspect.getsource(getattr(base,name)).replace("'v105.run'","'v181.run'")
    exec(compile(source,__file__+':'+name,'exec'),_ns)
_ns['cold_manifest']=lru_cache(maxsize=1)(clone_function(base.cold_manifest.__wrapped__,_ns))
methods={k:clone_function(v,_ns) for k,v in vars(base.Grading).items() if isinstance(v,FunctionType)}
source=inspect.getsource(base.Grading.run_request)
import textwrap
source=textwrap.dedent(source).replace("'v105.run'","'v181.run'")
local={};exec(compile(source,__file__+':scoring-child','exec'),_ns,local)
methods['run_request']=local['run_request']
_ns['Grading']=type('Grading',(base.Grading,),methods)
globals().update({k:v for k,v in _ns.items() if not k.startswith('__')})

if __name__=='__main__':main()
