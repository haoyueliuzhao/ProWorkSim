"""Independent Requests1724 environment controls; no generation or task changes.

This deployment uses two new control identities and an explicit grading-only
httpbin transport. It never alters the running v157 communication experiment.
"""
from __future__ import annotations
from functools import lru_cache
import inspect
from types import FunctionType
from pathlib import Path

from . import software_benchmark_scope_v162 as scope
from . import software_benchmark_grading_v105 as base
from . import software_benchmark_scorer_v066 as original
from . import software_benchmark_grading_v131 as cleanup_binding
from . import software_benchmark_requests1724_v162 as provider
from .software_benchmark_candidates_v054 import reference,checked,write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function

VERSION='v162-requests1724-grading-only-real-httpbin-r1'
REUSE_VERSION='v162-no-inherited-task-qualification'
MODULE=__name__
_namespace=clone_namespace(base,scope=scope,VERSION=VERSION,REUSE_VERSION=REUSE_VERSION,MODULE=MODULE,__file__=__file__)
_parent_scorer=_namespace['scorer'];_parent_host=_namespace['host']


def scorer(policy,*,manifest_provider=None):
    value=_parent_scorer(policy,manifest_provider=manifest_provider)
    ns=value.score_request.__globals__
    env=provider.cold_environment(policy,scope_ref=reference(scope.__file__),
        directory=scope.COORDINATOR_ROOT/'environment',resolution_ref=reference(scope.RESOLUTION_FILE))
    ns['environment']=env
    source=inspect.getsource(original.validate_qualification)
    begin=source.index('        if task in environment.TASKS:')
    end=source.index('        report = receipt["official_result"]',begin)
    old=source[begin:end]
    if 'timeout_route' not in old or 'validate_transport_evidence' not in old:
        raise ValueError('Original official qualification environment block changed')
    source=source[:begin]+'''        environment.validate_control_environment(observed, identity)
        environment.validate_transport_evidence(receipt, quiet, observed, identity, folder)
'''+source[end:]
    compiled={};exec(compile(source,__file__+':exact-1724-controls','exec'),ns,compiled)
    ns['validate_qualification']=compiled['validate_qualification']
    # The original validation allows four lanes. This independent environment
    # owns exactly lane0 on four CPUs outside the v157 generation/scoring set.
    source=inspect.getsource(original.validate_capacity_claim)
    if source.count('range(4)')!=1:raise ValueError('Original grading lane guard changed')
    compiled={};exec(compile(source.replace('range(4)','range(1)'),__file__+':one-grader-lane','exec'),ns,compiled)
    ns['validate_capacity_claim']=compiled['validate_capacity_claim']
    source=inspect.getsource(original.validate_request)
    if source.count('range(4)')!=1:raise ValueError('Original request CPU-lane guard changed')
    compiled={};exec(compile(source.replace('range(4)','range(1)'),__file__+':one-request-lane','exec'),ns,compiled)
    ns['validate_request']=compiled['validate_request']
    inherited=ns['installation_manifest']
    def manifest():
        current=inherited()
        if manifest_provider is not None:return current
        return {**current,'independent_1724_provider':reference(provider.__file__),
            'independent_1724_scope':reference(scope.__file__),'independent_1724_grading':reference(__file__),
            'only_task':provider.TASK,'controls_only':True,'new_model_calls':0,
            'actual_test_interpreter':'original pinned Python2','relay_interpreter':'existing base Python3',
            'original_CA_unchanged':True,'effective_scoring_CA_augmented':True,'TLS_verification_preserved':True,
            'host_listeners_or_mounts_or_network_configuration':False,
            'maximum_control_containers':2,'maximum_concurrent_graders':1,
            'official_test_patch_and_test_commands_changed':False}
    ns['installation_manifest']=manifest
    ns['cleanup']=clone_function(cleanup_binding.bind_physical_cleanup,
        {**cleanup_binding.bind_physical_cleanup.__globals__,'VERSION':VERSION})(ns)
    for name in ('environment','validate_qualification','validate_capacity_claim','validate_request','installation_manifest','cleanup'):
        setattr(value,name,ns[name])
    return value


def prepare_environment_qualifications_local():
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    scoring=scorer(scope.dispatch_view(scope.require_grading_allowed))
    scoring.environment.prepare()
    manifest=scope.retain(scope.COORDINATOR_ROOT/'scorer-manifest.json',scoring.installation_manifest())
    requests=[]
    for kind in ('gold','empty'):
        key='control-'+provider.TASK+'-'+kind
        request={'version':VERSION,'resource_key':key,'instance_id':provider.TASK,'slot_id':None,
            'plan':reference(scope.PLAN_FILE),'configuration':plan['environments'][provider.TASK]['configuration'],
            'patch_kind':kind,'limits':scoring.LIMITS,'scorer_manifest':manifest,
            'cpuset_cpus':None,'directory':str(scope.GRADING_ROOT/key),'candidate_lock':None,
            **scoring.environment.request_fields(provider.TASK)}
        requests.append(scope.retain(scope.GRADING_ROOT/key/'request.json',request))
    result={'version':VERSION,'controls':requests,'qualifications':{},'instance_id':provider.TASK,
        'source_communication_task_unchanged':True,'model_calls':0,'Docker_operations':0,
        'containers_required':2,'maximum_parallel_graders':1}
    scope.retain(scope.COORDINATOR_ROOT/'qualification-preparation.json',result)
    return result


def host(policy,scoring):
    value=_parent_host(policy,scoring)
    # v105 routes qualification through its legacy reuse inventory. Here the
    # original host's native two-control qualifier is the complete requirement.
    from importlib.util import spec_from_file_location,module_from_spec
    spec=spec_from_file_location('v162_exact_control_host',scope.ROOT/'tools/run_capability_grading_v066.py')
    original_host=module_from_spec(spec);spec.loader.exec_module(original_host)
    ns={**original_host.qualify.__globals__,'policy':policy,'scorer':scoring,'RUN_ROOT':scope.COORDINATOR_ROOT,'VERSION':VERSION}
    value.qualify=clone_function(original_host.qualify,ns)
    return value


_namespace.update(scorer=scorer,host=host,prepare_environment_qualifications_local=prepare_environment_qualifications_local)
_namespace['cold_manifest']=lru_cache(maxsize=1)(clone_function(base.cold_manifest.__wrapped__,_namespace))
_namespace['Grading']=type('Grading',(base.Grading,),{name:clone_function(value,_namespace)
    for name,value in vars(base.Grading).items() if isinstance(value,FunctionType)})
globals().update({key:value for key,value in _namespace.items() if not key.startswith('__')})
if __name__=='__main__':main()
