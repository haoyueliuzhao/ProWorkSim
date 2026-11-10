"""Fresh official gold/empty controls and asynchronous scoring, no network tasks."""
from functools import lru_cache
import inspect
from types import FunctionType
from . import software_benchmark_grading_v105 as base
from . import software_benchmark_scope_v192 as scope
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function
from . import software_benchmark_project_closure_v192 as closure
from .software_benchmark_delivery_reuse_v175 import bind_host
from .software_benchmark_grading_v131 import _lane_validator

VERSION='v192-private-official-context-pilot-score-r1'
MODULE='proworksim.software_benchmark_grading_v192'
_ns=clone_namespace(base,scope=scope,VERSION=VERSION,MODULE=MODULE,__file__=__file__)
_parent_scorer=_ns['scorer'];_parent_host=_ns['host'];_parent_environment=_ns['private_environment']


def private_environment(policy):
    value=_parent_environment(policy)
    # Only the selected5414 task has an offline private fixture. No live TLS,
    # DNS, external forwarding or host configuration changes are introduced.
    ns=value.request_fields.__globals__
    ns.update(TASKS=frozenset({'psf__requests-5414'}),OFFLINE_TASKS=frozenset({'psf__requests-5414'}),TLS_TASKS=frozenset())
    def prepare():
        offline=scope.retain(scope.GRADING_ROOT/'environments/offline.json',value.offline.environment_manifest())
        return scope.retain(scope.GRADING_ROOT/'environments/bindings.json',
            {'offline':offline,'tls':None,'network_resolutions':{}})
    value.__dict__.update(prepare=prepare,TASKS=ns['TASKS'],TLS_TASKS=ns['TLS_TASKS'],OFFLINE_TASKS=ns['OFFLINE_TASKS'])
    return value


def scorer(policy,*,manifest_provider=None):
    value=_parent_scorer(policy,manifest_provider=manifest_provider)
    ns=value.validate_request.__globals__
    ns.update(validate_delivery_evidence=closure.validate_delivery_evidence,MAX_GRADERS=2)
    ns['validate_request']=_lane_validator(ns)
    from .software_namespace_witness_v183 import bind_scorer
    bind_scorer(value)
    # Fresh gold/empty for every selected environment: no inherited score cache.
    ns['validate_qualification']=clone_function(base.original.validate_qualification,ns)
    original_manifest=ns['installation_manifest']
    def manifest():
        result=original_manifest()
        if manifest_provider is not None:return result
        return {**result,'managed_delivery_validator':reference(closure.__file__),
            'context_score_adapter':reference(__file__),'public_network':'none',
            'namespace_witness_adapter':reference(scope.ROOT/'src/proworksim/software_namespace_witness_v183.py'),
            'requests_capabilities_by_task':{'psf__requests-5414':['NET_ADMIN']},'maximum_real_tls_sessions':0}
    ns['installation_manifest']=manifest
    for name in ('validate_request','validate_qualification','installation_manifest','validate_delivery_evidence'):
        setattr(value,name,ns[name])
    return value


def host(policy,scoring):
    value=_parent_host(policy,scoring)
    return bind_host(value)


def prepare_environment_qualifications_local():
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    scoring=scorer(scope.dispatch_view())
    scoring.environment.prepare()
    manifest=scope.retain(scope.COORDINATOR_ROOT/'scorer-manifest.json',scoring.installation_manifest())
    controls=[]
    for task,env in plan['environments'].items():
        for kind in ('gold','empty'):
            key='control-'+task+'-'+kind
            value={'version':VERSION,'resource_key':key,'instance_id':task,'slot_id':None,
                'plan':reference(scope.PLAN_FILE),'configuration':env['configuration'],'patch_kind':kind,
                'limits':scoring.LIMITS,'scorer_manifest':manifest,'cpuset_cpus':None,
                'directory':str(scope.GRADING_ROOT/key),'candidate_lock':None,**scoring.environment.request_fields(task)}
            controls.append(scope.retain(scope.GRADING_ROOT/key/'request.json',value))
    return {'controls':controls,'qualifications':{},'model_calls':0,'new_controls':24}


_ns.update(private_environment=private_environment,scorer=scorer,host=host,
    prepare_environment_qualifications_local=prepare_environment_qualifications_local)
for name in ('score_request','main'):
    source=inspect.getsource(getattr(base,name)).replace("'v105.run'","'v192.run'")
    exec(compile(source,__file__+':'+name,'exec'),_ns)
_ns['cold_manifest']=lru_cache(maxsize=1)(clone_function(base.cold_manifest.__wrapped__,_ns))
methods={k:clone_function(v,_ns) for k,v in vars(base.Grading).items() if isinstance(v,FunctionType)}
source=inspect.getsource(base.Grading.run_request)
import textwrap
source=textwrap.dedent(source).replace("'v105.run'","'v192.run'")
local={};exec(compile(source,__file__+':scoring-child','exec'),_ns,local)
methods['run_request']=local['run_request']
_ns['Grading']=type('Grading',(base.Grading,),methods)
globals().update({k:v for k,v in _ns.items() if not k.startswith('__')})

if __name__=='__main__':main()
