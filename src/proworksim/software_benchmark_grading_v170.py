"""Independent technical-attempt scoring, reusing exact qualified environments.

Only the five selected original task environments are needed. The official
tests, isolation, patch selection and delivery proof stay unchanged; no old
candidate scores are reused and this batch has no scoring network access.
"""
from __future__ import annotations
from functools import lru_cache
import inspect
from types import FunctionType

from . import software_benchmark_scope_v170 as scope
from . import software_benchmark_scope_v157 as original_scope
from . import software_benchmark_grading_v157 as prior_grading
from . import software_benchmark_grading_v105 as base
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function

VERSION='v170-completion-technical-attempt-official-scoring-r1'
REUSE_VERSION='v161-exact-original-environment-only-reuse-r1'
MODULE=__name__
FRESH_CONTROL_TASKS=frozenset()
_namespace=clone_namespace(base,scope=scope,VERSION=VERSION,REUSE_VERSION=REUSE_VERSION,MODULE=MODULE,__file__=__file__)
_parent_scorer=_namespace['scorer'];_parent_host=_namespace['host']


@lru_cache(maxsize=1)
def original_inventory():
    result=prior_grading.validate_environment_preparation()
    if result.get('inventory_valid') is not True:
        raise ValueError('Original environment evidence is not trustworthy')
    return result


@lru_cache(maxsize=1)
def original_qualified_scorer():
    manifest=scope.load(reference(original_scope.COORDINATOR_ROOT/'scorer-manifest.json'))
    return prior_grading.scorer(original_scope.dispatch_view(original_scope.require_grading_allowed),
        manifest_provider=lambda:manifest)


def reuse_value(task,manifest_ref,plan):
    entry=original_inventory()['qualifications'][task]
    if entry.get('status')!='qualified':
        raise ValueError('Technical recovery requires an exact already-qualified environment')
    source_ref=reference(original_scope.PLAN_FILE);source=scope.load(source_ref)
    before=scope.load(source['environments'][task]['configuration'])
    after=scope.load(plan['environments'][task]['configuration'])
    if base.environment_identity(before)!=base.environment_identity(after):
        raise ValueError('Technical recovery changed the official scoring environment')
    old_ref=reference(original_scope.COORDINATOR_ROOT/'scorer-manifest.json')
    old,current=scope.load(old_ref),scope.load(manifest_ref)
    keys=('parent','archive_adapter','limits','cap_drop','no_new_privileges',
        'official_tests_and_scoring_rules_changed','host_namespace_mount_or_daemon_operations',
        'pilot_environment_adapter','selective_reset_by_task','selective_reset_actual_hashes',
        'legacy_boundary_probe','fresh_baseline_normalization_tasks')
    if any(old.get(key)!=current.get(key) for key in keys):
        raise ValueError('Official test/reset/baseline mechanism differs from the actual controls')
    actual=original_qualified_scorer().validate_qualification(entry['qualification'],before,source_ref)
    if actual.get('passed') is not True:
        raise ValueError('The original actual gold/empty controls no longer qualify')
    return {'version':REUSE_VERSION,'instance_id':task,'passed':True,'plan':reference(scope.PLAN_FILE),
        'original_plan':source_ref,'original_qualification':entry['qualification'],
        'original_configuration':source['environments'][task]['configuration'],
        'original_manifest':old_ref,'current_manifest':manifest_ref,'unchanged_environment_fields':list(keys),
        'exact_environment_identity':base.environment_identity(after),'old_candidate_scores_reused':False,
        'model_calls':0,'Docker_operations':0,'new_controls':0,'scoring_network_access':False}


def validate_reused_qualification(ref,config,plan_ref):
    value=scope.load(ref)
    if (value.get('version')!=REUSE_VERSION or value.get('plan')!=plan_ref
            or value!=reuse_value(config['instance_id'],value['current_manifest'],scope.load(plan_ref))):
        raise ValueError('Technical recovery qualification lost its exact environment/plan binding')
    return value


def scorer(policy,*,manifest_provider=None):
    from . import software_benchmark_project_closure_v170 as closure
    from . import software_benchmark_project_closure_v157 as original_closure
    for name in ('validate_delivery_evidence','export_managed_closure'):
        if getattr(closure,name).__code__ is not getattr(original_closure,name).__code__:
            raise ValueError('Recovery changed the frozen candidate/delivery contract')
    source=inspect.getsource(prior_grading.scorer)
    needle='from . import software_benchmark_project_closure_v157 as closure'
    if source.count(needle)!=1:raise ValueError('Original private scorer binding changed')
    source=source.replace(needle,'from . import software_benchmark_project_closure_v170 as closure')
    namespace={**prior_grading.scorer.__globals__,'scope':scope,'VERSION':VERSION,'REUSE_VERSION':REUSE_VERSION,
        'MODULE':MODULE,'__file__':__file__,'_parent_scorer':_parent_scorer,
        'validate_reused_qualification':validate_reused_qualification}
    compiled={};exec(compile(source,__file__+':unchanged-scoring-factory','exec'),namespace,compiled)
    value=compiled['scorer'](policy,manifest_provider=manifest_provider)
    if value.environment.TASKS:
        raise ValueError('The five recovery tasks need no scoring network provider')
    return value


def host(policy,scoring):
    namespace={**prior_grading.host.__globals__,'scope':scope,'VERSION':VERSION,'_parent_host':_parent_host,
        'FRESH_CONTROL_TASKS':FRESH_CONTROL_TASKS}
    return clone_function(prior_grading.host,namespace)(policy,scoring)


def prepare_environment_qualifications_local():
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    scoring=scorer(scope.dispatch_view(scope.require_grading_allowed))
    manifest=scope.retain(scope.COORDINATOR_ROOT/'scorer-manifest.json',scoring.installation_manifest())
    qualifications={}
    for task in plan['environments']:
        proof=reuse_value(task,manifest,plan)
        ref=scope.retain(scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'),proof)
        qualifications[task]={'status':'qualified','qualification':ref,'reused_actual_controls':True}
    result={'version':VERSION,'qualifications':qualifications,'controls':[],'model_calls':0,
        'Docker_operations':0,'qualified_count':len(qualifications),'blocked_tasks':[],
        'new_scoring_identity_per_candidate':True,'old_candidate_scores_reused':False}
    scope.retain(scope.COORDINATOR_ROOT/'qualification-preparation.json',result)
    return result


def validate_environment_preparation():
    plan_ref=reference(scope.PLAN_FILE);plan=scope.validate_plan(scope.load(plan_ref))
    ref=reference(scope.COORDINATOR_ROOT/'qualification-preparation.json');value=scope.load(ref)
    if (set(value['qualifications'])!=set(plan['environments']) or value.get('controls')!=[]
            or value.get('blocked_tasks')!=[]):
        raise ValueError('All selected technical recovery environments require qualified evidence')
    for task,row in value['qualifications'].items():
        if row.get('status')!='qualified':raise ValueError('The recovery environment is not qualified')
        validate_reused_qualification(row['qualification'],scope.load(plan['environments'][task]['configuration']),plan_ref)
    return {**value,'passed':True,'inventory_valid':True,'first_wave_qualified':True,
        'full_panel_ready':True,'status':ref,'new_controls':0}


_namespace.update(scorer=scorer,host=host,validate_reused_qualification=validate_reused_qualification,
    prepare_environment_qualifications_local=prepare_environment_qualifications_local)
_namespace['cold_manifest']=lru_cache(maxsize=1)(clone_function(base.cold_manifest.__wrapped__,_namespace))
_namespace['Grading']=type('Grading',(base.Grading,),{name:clone_function(value,_namespace)
    for name,value in vars(base.Grading).items() if isinstance(value,FunctionType)})
globals().update({key:value for key,value in _namespace.items() if not key.startswith('__')})
if __name__=='__main__':main()
