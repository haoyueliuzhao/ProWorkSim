"""Immutable r4 HTTP-framing scoring namespace and independently qualified current endpoint.

Formal requests retain the original twelve-row plan. The two new controls use
their own exact plan/identities and the same single grader capacity lane.
"""
from functools import lru_cache
import inspect
import os
from pathlib import Path
import textwrap
from types import FunctionType, SimpleNamespace

from . import software_benchmark_grading_v105 as base
from . import software_benchmark_grading_v203_2_3 as prior
from . import software_benchmark_scope_v203_2_3 as formal_scope
from . import software_benchmark_preparation_grading_v203_2_3_r4 as preparation
from . import software_benchmark_environment_v203_2_3_r4 as environment_adapter
from . import software_benchmark_project_closure_v203_2_3 as closure
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_delivery_reuse_v175 import bind_host
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function
from .software_benchmark_grading_v131 import _lane_validator

VERSION='v203.2.3-http-framing-official-scoring-r4'
REUSE_VERSION='v203.2.3-r4-ordinary-environment-reuse-r1'
QUALIFICATION_VERSION='v203.2.3-http-framing-qualification-envelope-r4'
MODULE='proworksim.software_benchmark_grading_v203_2_3_r4'
PREPARATION_FLAG='PWS_V20323_GRADING_REVISION_R4'


def formal_dispatch(guard=None):
    value=formal_scope.dispatch_view(guard)
    bindings={'GRADING_ROOT':preparation.GRADING_ROOT,'COORDINATOR_RUN_ROOT':preparation.COORDINATOR_ROOT}
    value.claim_resource.__globals__.update(bindings)
    value.__dict__.update(bindings)
    return value


scope=(preparation.preparation_scope() if os.environ.get(PREPARATION_FLAG)=='1' else
       SimpleNamespace(**{**vars(formal_scope),'GRADING_ROOT':preparation.GRADING_ROOT,
          'COORDINATOR_ROOT':preparation.COORDINATOR_ROOT,'dispatch_view':formal_dispatch}))
scope.NETWORK_RESOLUTION_FILE=environment_adapter.RESOLUTION
_ns=clone_namespace(base,scope=scope,VERSION=VERSION,MODULE=MODULE,__file__=__file__)
_parent_scorer,_parent_host,_parent_environment=_ns['scorer'],_ns['host'],_ns['private_environment']


def command(arguments):
    flag='1' if scope.PLAN_FILE==preparation.CONTROL_PLAN_FILE else '0'
    bootstrap=("import os,runpy,sys; os.environ["+repr(PREPARATION_FLAG)+"]="+repr(flag)+
        "; sys.argv=["+repr(MODULE)+",*sys.argv[1:]]; runpy.run_module("+repr(MODULE)+",run_name='__main__')")
    return [str(scope.ROOT/'.venv/bin/python'),'-B',str(scope.ROOT/'tools/run_offline_scorer_v096.py'),
            '-c',bootstrap,*map(str,arguments)]


def private_environment(policy):
    environment_scope=SimpleNamespace(**{**vars(scope),'GRADING_ROOT':policy.GRADING_ROOT,
        'COORDINATOR_ROOT':policy.COORDINATOR_RUN_ROOT,'PLAN_FILE':policy.PLAN_FILE})
    return environment_adapter.private_environment(policy,environment_scope,_parent_environment)


def canonical_config(task):
    plan=formal_scope.validate_plan(formal_scope.load(reference(formal_scope.PLAN_FILE)))
    return formal_scope.load(plan['environments'][task]['configuration'])


def ordinary_qualification(task,config,plan_ref):
    if task==environment_adapter.TASK or plan_ref!=reference(formal_scope.PLAN_FILE) or config!=canonical_config(task):
        raise ValueError('Only the exact frozen ordinary task environment can reuse its qualification')
    old_ref=reference(formal_scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'))
    old_scoring=prior.scorer(formal_scope.dispatch_view())
    old_scoring.validate_qualification(old_ref,config,plan_ref)
    old_manifest_ref=reference(formal_scope.COORDINATOR_ROOT/'scorer-manifest.json')
    new_manifest_ref=reference(scope.COORDINATOR_ROOT/'scorer-manifest.json')
    old,new=scope.load(old_manifest_ref),scope.load(new_manifest_ref)
    if any(old.get(key)!=new.get(key) for key in prior.RUNTIME_FIELDS):
        raise ValueError('The ordinary official scoring runtime changed')
    return {'version':REUSE_VERSION,'instance_id':task,'passed':True,'plan':plan_ref,
        'original_qualification':old_ref,'original_scorer_manifest':old_manifest_ref,
        'scorer_manifest':new_manifest_ref,'environment_identity':base.environment_identity(config),
        'unchanged_runtime_fields':list(prior.RUNTIME_FIELDS),'model_calls':0,'new_controls':0,
        'source':reference(__file__)}


def scorer(policy,*,manifest_provider=None):
    value=_parent_scorer(policy,manifest_provider=manifest_provider)
    namespace=value.validate_request.__globals__
    namespace.update(validate_delivery_evidence=closure.validate_delivery_evidence,MAX_GRADERS=1)
    namespace['validate_request']=_lane_validator(namespace)
    from .software_namespace_witness_v183 import bind_scorer
    bind_scorer(value)
    source=inspect.getsource(base.original.validate_qualification)
    importer='from .software_benchmark_grading_qualification_v060 import validate_transport_evidence'
    key='"control-" + task + "-" + kind'
    if source.count(importer)!=1 or source.count(key)!=1:
        raise ValueError('Original control qualification seam changed')
    source=source.replace(importer,'from .software_benchmark_environment_v203_2_3_r4 import validate_transport_evidence')
    source=source.replace(key,'"control-r4-" + task + "-" + kind')
    local={}
    exec(compile(source,__file__+':new-control-qualification','exec'),namespace,local)
    native=local['validate_qualification']
    def validate(ref,config,plan_ref):
        supplied=scope.load(ref);task=config['instance_id']
        if plan_ref!=reference(formal_scope.PLAN_FILE) or config!=canonical_config(task):
            raise ValueError('Qualification requires the exact formal environment config')
        if Path(ref['path']).resolve()!=scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'):
            raise ValueError('Qualification is outside the new r4 namespace')
        if task!=environment_adapter.TASK:
            if supplied!=ordinary_qualification(task,config,plan_ref):
                raise ValueError('Ordinary r4 qualification changed')
            return supplied
        if (supplied.get('version')!=QUALIFICATION_VERSION or supplied.get('passed') is not True
                or supplied.get('instance_id')!=task or supplied.get('plan')!=plan_ref
                or supplied.get('formal_plan')!=plan_ref
                or supplied.get('control_plan')!=reference(preparation.CONTROL_PLAN_FILE)
                or supplied.get('profile')!=reference(environment_adapter.RESOLUTION)
                or supplied.get('CA_profile')!=reference(formal_scope.CA_PROFILE_FILE)
                or supplied.get('environment_identity')!=base.environment_identity(config)):
            raise ValueError('New control pair does not bind this exact formal scoring environment')
        native(supplied['native_qualification'],config,supplied['control_plan'])
        return supplied
    parent_manifest=namespace['installation_manifest']
    def manifest():
        result=parent_manifest()
        if manifest_provider is not None:return result
        return {**result,'managed_delivery_validator':reference(closure.__file__),
            'current_endpoint_scoring_adapter':reference(__file__),
            'environment_adapter':reference(environment_adapter.__file__),
            'profile':reference(environment_adapter.RESOLUTION),'scoring_CA_profile':reference(formal_scope.CA_PROFILE_FILE),
            'scoring_CA_tasks':[environment_adapter.TASK], 'original_CA_file_and_candidate_unchanged':True,
            'public_network':'Requests1766 scorer only, frozen current numeric httpbin IP:80/443; solver none',
            'maximum_graders':1,'fresh_control_plan':reference(preparation.CONTROL_PLAN_FILE)}
    namespace.update(validate_qualification=validate,installation_manifest=manifest)
    for name in ('validate_request','validate_qualification','installation_manifest','validate_delivery_evidence'):
        setattr(value,name,namespace[name])
    value.validate_native_qualification=native
    return value


def host(policy,scoring):
    value=bind_host(_parent_host(policy,scoring))
    def qualify(task):
        if task!=environment_adapter.TASK:
            ref=reference(scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'))
            scoring.validate_qualification(ref,canonical_config(task),reference(formal_scope.PLAN_FILE))
            return ref
        controls=[]
        for kind in ('gold','empty'):
            folder=scope.GRADING_ROOT/('control-r4-'+task+'-'+kind)
            controls.append({'patch_kind':kind,**{name:reference(folder/(name+'.json'))
                for name in ('receipt','quiescence','completion')},
                'initial_container':reference(folder/'official-output/initial-container.json')})
        raw={'version':VERSION,'instance_id':task,'passed':True,
             'plan':reference(preparation.CONTROL_PLAN_FILE),'controls':controls,'model_calls':0}
        raw_ref=scope.retain(scope.COORDINATOR_ROOT/'native-qualifications'/(task+'.json'),raw)
        scoring.validate_native_qualification(raw_ref,canonical_config(task),raw['plan'])
        envelope={'version':QUALIFICATION_VERSION,'instance_id':task,'passed':True,
            'plan':reference(formal_scope.PLAN_FILE),
            'formal_plan':reference(formal_scope.PLAN_FILE),'control_plan':raw['plan'],
            'native_qualification':raw_ref,'profile':reference(environment_adapter.RESOLUTION),
            'CA_profile':reference(formal_scope.CA_PROFILE_FILE),
            'environment_identity':base.environment_identity(canonical_config(task)),
            'model_calls':0,'new_control_pair':True,'old_results_overwritten':False}
        return scope.retain(scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'),envelope)
    value.qualify=qualify
    return value


def prepare_environment_qualifications_local():
    scoring=scorer(scope.dispatch_view(scope.require_grading_allowed));scoring.environment.prepare()
    manifest=scope.retain(scope.COORDINATOR_ROOT/'scorer-manifest.json',scoring.installation_manifest())
    formal_plan_ref=reference(formal_scope.PLAN_FILE)
    formal_plan=formal_scope.load(formal_plan_ref)
    qualifications={}
    for task in formal_plan['environments']:
        if task==environment_adapter.TASK:continue
        proof=ordinary_qualification(task,canonical_config(task),formal_plan_ref)
        ref=scope.retain(scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'),proof)
        qualifications[task]={'status':'qualified','qualification':ref,'reused_controls':True}
    task=environment_adapter.TASK
    qpath=scope.COORDINATOR_ROOT/'qualifications'/(task+'.json')
    if qpath.exists():
        ref=reference(qpath);scoring.validate_qualification(ref,canonical_config(task),formal_plan_ref)
        qualifications[task]={'status':'qualified','qualification':ref,'new_controls_passed':True}
        return {'qualifications':qualifications,'controls':[],'model_calls':0}
    controls=[]
    for kind in ('gold','empty'):
        key='control-r4-'+task+'-'+kind
        request={'version':VERSION,'resource_key':key,'instance_id':task,'slot_id':None,
            'plan':reference(preparation.CONTROL_PLAN_FILE),
            'configuration':formal_plan['environments'][task]['configuration'],'patch_kind':kind,
            'limits':scoring.LIMITS,'scorer_manifest':manifest,'cpuset_cpus':None,
            'directory':str(scope.GRADING_ROOT/key),'candidate_lock':None,
            **scoring.environment.request_fields(task)}
        controls.append(scope.retain(scope.GRADING_ROOT/key/'request.json',request))
    result={'qualifications':qualifications,'controls':controls,'model_calls':0,
            'fresh_environment_only_no_model_replay':True}
    scope.retain(scope.COORDINATOR_ROOT/'preparation.json',result)
    return result


_ns.update(REUSE_VERSION=REUSE_VERSION,command=command,private_environment=private_environment,
    scorer=scorer,host=host,prepare_environment_qualifications_local=prepare_environment_qualifications_local)
for _name in ('score_request','main'):
    _source=inspect.getsource(getattr(base,_name)).replace("'v105.run'","'v203.2.3.run'")
    exec(compile(_source,__file__+':'+_name,'exec'),_ns)
_ns['cold_manifest']=lru_cache(maxsize=1)(clone_function(base.cold_manifest.__wrapped__,_ns))
_methods={key:clone_function(value,_ns) for key,value in vars(base.Grading).items() if isinstance(value,FunctionType)}
_source=textwrap.dedent(inspect.getsource(base.Grading.run_request)).replace("'v105.run'","'v203.2.3.run'")
_local={};exec(compile(_source,__file__+':grading-child','exec'),_ns,_local)
_methods['run_request']=_local['run_request'];_ns['Grading']=type('Grading',(base.Grading,),_methods)
globals().update({key:value for key,value in _ns.items() if not key.startswith('__')})

if __name__=='__main__':_ns['main']()


def validate_qualification(ref, config, plan_ref):
    return scorer(formal_dispatch()).validate_qualification(ref, config, plan_ref)
