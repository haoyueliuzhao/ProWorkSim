"""Official scoring for never-called original teams under the repaired deployment.

Original23 qualified environments are independently revalidated and rebound to
new plan/scoring identities. No old candidate result/cache is imported. The
blocked Requests1724 identity remains explicit until a separate scoring repair.
"""
from __future__ import annotations
from functools import lru_cache
import inspect
from types import FunctionType

from . import software_benchmark_scope_v168 as scope
from . import software_benchmark_scope_v157 as original_scope
from . import software_benchmark_grading_v157 as prior_grading
from . import software_benchmark_grading_v105 as base
from .software_benchmark_candidates_v054 import checked,reference
from . import software_benchmark_requests1724_binding_v165 as network_binding
from . import software_benchmark_requests1724_qualification_v164 as network_qualification
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function

VERSION='v168-second-wave-official-scoring-r1'
REUSE_VERSION='v168-verified-v157-environment-only-reuse-r1'
MODULE=__name__
FRESH_CONTROL_TASKS=frozenset()
_namespace=clone_namespace(base,scope=scope,VERSION=VERSION,REUSE_VERSION=REUSE_VERSION,MODULE=MODULE,__file__=__file__)
_parent_scorer=_namespace['scorer'];_parent_host=_namespace['host']


@lru_cache(maxsize=1)
def original_inventory():
    value=prior_grading.validate_environment_preparation()
    if value.get('inventory_valid') is not True:
        raise ValueError('The original environment inventory must be trustworthy')
    return value


@lru_cache(maxsize=1)
def original_qualified_scorer():
    frozen=scope.load(reference(original_scope.COORDINATOR_ROOT/'scorer-manifest.json'))
    return prior_grading.scorer(original_scope.dispatch_view(original_scope.require_grading_allowed),
        manifest_provider=lambda:frozen)


def reuse_value(task,manifest_ref,plan):
    inventory=original_inventory();entry=inventory['qualifications'][task]
    if task==network_binding.TASK:
        config=scope.load(plan['environments'][task]['configuration'])
        overlay=reference(network_qualification.OVERLAY_FILE)
        qualified=network_qualification.validate_qualification(overlay,config,reference(scope.PLAN_FILE))
        current=scope.load(manifest_ref)
        equivalence=network_binding.verify_qualified_reuse(current['qualified1724_environment_manifest'],config)
        return {'version':REUSE_VERSION,'instance_id':task,'passed':True,'plan':reference(scope.PLAN_FILE),
            'current_manifest':manifest_ref,'original_environment_record':inventory['status'],
            'original_qualification_status':'not_qualified','qualified_environment_overlay':overlay,
            'official_score_rule_changed':False,'test_groups_changed':False,
            'verified_environment_equivalence':equivalence,'new_model_calls':0,'Docker_operations':0,
            'original_failed_environment_record_preserved':True,'new_controls':0}
    if entry.get('status')!='qualified':
        raise ValueError('Original blocked environment remains blocked: '+task)
    source_plan_ref=reference(original_scope.PLAN_FILE);source_plan=scope.load(source_plan_ref)
    before=scope.load(source_plan['environments'][task]['configuration'])
    after=scope.load(plan['environments'][task]['configuration'])
    if base.environment_identity(before)!=base.environment_identity(after):
        raise ValueError('Recovery changed the pinned official evaluation environment')
    old_manifest_ref=reference(original_scope.COORDINATOR_ROOT/'scorer-manifest.json')
    old_manifest=scope.load(old_manifest_ref);current=scope.load(manifest_ref)
    keys=('parent','archive_adapter','limits','cap_drop','no_new_privileges',
        'official_tests_and_scoring_rules_changed','host_namespace_mount_or_daemon_operations',
        'pilot_environment_adapter','selective_reset_by_task','selective_reset_actual_hashes',
        'legacy_boundary_probe','fresh_baseline_normalization_tasks')
    if any(old_manifest.get(k)!=current.get(k) for k in keys):
        raise ValueError('Recovery changed an official test, reset, baseline or scoring mechanism')
    prior=original_qualified_scorer()
    result=prior.validate_qualification(entry['qualification'],before,source_plan_ref)
    if result.get('passed') is not True:raise ValueError('Prior actual gold/empty environment does not qualify')
    return {'version':REUSE_VERSION,'instance_id':task,'passed':True,'plan':reference(scope.PLAN_FILE),
        'original_plan':source_plan_ref,'original_qualification':entry['qualification'],
        'original_configuration':source_plan['environments'][task]['configuration'],
        'original_manifest':old_manifest_ref,'current_manifest':manifest_ref,
        'unchanged_environment_fields':list(keys),'exact_environment_identity':base.environment_identity(after),
        'old_scores_or_model_candidates_reused':False,'model_calls':0,'Docker_operations':0,'new_controls':0}


def validate_reused_qualification(ref,config,plan_ref):
    value=scope.load(ref)
    if (value.get('version')!=REUSE_VERSION or value.get('plan')!=plan_ref
        or value!=reuse_value(config['instance_id'],value['current_manifest'],scope.load(plan_ref))):
        raise ValueError('Recovery environment qualification lost its exact plan/control binding')
    return value


def scorer(policy,*,manifest_provider=None):
    from . import software_benchmark_project_closure_v168 as closure
    from . import software_benchmark_project_closure_v157 as old_closure
    if closure.validate_delivery_evidence is not old_closure.validate_delivery_evidence:
        raise ValueError('The original delivery evidence contract must remain the same function')
    # Execute the exact original scoring factory with an isolated namespace and
    # the new closure-module import. No live original module globals are edited.
    source=inspect.getsource(prior_grading.scorer)
    needle='from . import software_benchmark_project_closure_v157 as closure'
    if source.count(needle)!=1:raise ValueError('Original scorer closure binding changed')
    source=source.replace(needle,'from . import software_benchmark_project_closure_v168 as closure')
    ns={**prior_grading.scorer.__globals__,'scope':scope,'VERSION':VERSION,'REUSE_VERSION':REUSE_VERSION,
        'MODULE':MODULE,'__file__':__file__,'_parent_scorer':_parent_scorer,
        'validate_reused_qualification':validate_reused_qualification}
    compiled={};exec(compile(source,__file__+':original-scoring-factory','exec'),ns,compiled)
    value=compiled['scorer'](policy,manifest_provider=manifest_provider)
    actual_ns=value.score_request.__globals__
    old_router=value.environment
    for function in (value.Containers.create,value.validate_attrs,value._score):
        if function.__globals__.get('environment') is not old_router:
            raise ValueError('Actual private scorer dispatch/environment aliases differ')
    scope_ref=reference(scope.__file__)
    router=network_binding.environment_for(policy,scope_ref=scope_ref,
        directory=scope.COORDINATOR_ROOT/'qualified-1724-candidates'/scope_ref['sha256'][:16])
    # Change this newly constructed private router in place: create/attrs/score
    # all hold this exact object, while historical module globals stay intact.
    vars(old_router).update(vars(router))
    inherited=value.installation_manifest
    def installation_manifest():
        fields=old_router.request_fields(network_binding.TASK)
        return {**inherited(),'environment_router':reference(network_binding.__file__),
            'offline_requests_adapter':reference(network_binding.original.__file__),
            'real_tls_requests_adapter':reference(network_binding.original.__file__),
            'requests_capabilities_by_task':{network_binding.TASK:old_router.capabilities(network_binding.TASK)},
            'public_network':'Only qualified1724 scoring uses frozen bounded HTTP/TLS; actors/models remain offline',
            'maximum_real_tls_sessions':6,'qualified1724_environment_manifest':fields['environment_revision'],
            'qualified1724_network_resolution':fields['network_resolution'],
            'qualified1724_source_overlay':reference(network_qualification.OVERLAY_FILE),
            'qualified1724_scope_binding':reference(network_binding.__file__),
            'qualified1724_actual_cleanup_binding':'pass original non-reset evaluator into existing v068 hook'}
    actual_ns['installation_manifest']=value.installation_manifest=installation_manifest
    raw_score=value._score
    score_source=inspect.getsource(raw_score)
    needle='    run_instance = evaluation\n'
    if score_source.count(needle)!=1:raise ValueError('The original evaluator selection point changed')
    score_source=score_source.replace(needle,'    run_instance = evaluator_for_qualified_1724(evaluation, config["instance_id"])\n')
    actual_ns['evaluator_for_qualified_1724']=evaluator_for_qualified_1724
    compiled_score={};exec(compile(score_source,__file__+':qualified1724-cleanup-evaluator','exec'),actual_ns,compiled_score)
    actual_ns['_score']=value._score=compiled_score['_score']
    return value


def evaluator_for_qualified_1724(evaluation,task):
    if task!=network_binding.TASK:return evaluation
    if callable(evaluation.__globals__.get('cleanup_container')):return evaluation
    closed=dict(zip(evaluation.__code__.co_freevars,(cell.cell_contents for cell in (evaluation.__closure__ or ()))))
    if (set(closed)!={'adapters','original'} or set(closed['adapters'])!={'astropy__astropy-7336','pylint-dev__pylint-6528'}
        or task in closed['adapters'] or not callable(closed['original'].__globals__.get('cleanup_container'))):
        raise ValueError('1724 must expose its actual unchanged evaluator cleanup namespace')
    return closed['original']


def host(policy,scoring):
    ns={**prior_grading.host.__globals__,'scope':scope,'VERSION':VERSION,'_parent_host':_parent_host,
        'FRESH_CONTROL_TASKS':FRESH_CONTROL_TASKS}
    return clone_function(prior_grading.host,ns)(policy,scoring)


def prepare_environment_qualifications_local():
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    scoring=scorer(scope.dispatch_view(scope.require_grading_allowed))
    manifest=scope.retain(scope.COORDINATOR_ROOT/'scorer-manifest.json',scoring.installation_manifest())
    inventory=original_inventory();quals={}
    for task in plan['environments']:
        prior=inventory['qualifications'][task]
        if prior.get('status')!='qualified' and task!=network_binding.TASK:
            quals[task]={**prior,'original_environment_record':inventory['status']}
            continue
        proof=reuse_value(task,manifest,plan)
        ref=scope.retain(scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'),proof)
        quals[task]={'status':'qualified','qualification':ref,'reused_actual_controls':True,
            'qualified1724_overlay':task==network_binding.TASK}
    result={'version':VERSION,'qualifications':quals,'controls':[],'model_calls':0,'Docker_operations':0,
        'qualified_count':sum(q['status']=='qualified' for q in quals.values()),
        'blocked_tasks':[t for t,q in quals.items() if q['status']!='qualified'],
        'new_scoring_identity_per_candidate':True,'old_model_scores_reused':False}
    scope.retain(scope.COORDINATOR_ROOT/'qualification-preparation.json',result)
    return result


def validate_environment_preparation():
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    ref=reference(scope.COORDINATOR_ROOT/'qualification-preparation.json');value=scope.load(ref)
    if set(value['qualifications'])!=set(plan['environments']) or value.get('controls')!=[]:
        raise ValueError('Only the complete revalidated environment inventory may be resumed')
    for task,row in value['qualifications'].items():
        if row['status']=='qualified':
            validate_reused_qualification(row['qualification'],scope.load(plan['environments'][task]['configuration']),reference(scope.PLAN_FILE))
        elif task not in original_inventory()['blocked_tasks']:
            raise ValueError('Unexpected new blocked environment')
    first={r['instance_id'] for r in plan['rows']}
    ready=all(value['qualifications'][t]['status']=='qualified' for t in first)
    return {**value,'passed':ready,'inventory_valid':True,'selected_wave_qualified':ready,
        'full_panel_ready':not value['blocked_tasks'],'status':ref,'new_controls':0}


_namespace.update(scorer=scorer,host=host,validate_reused_qualification=validate_reused_qualification,
    prepare_environment_qualifications_local=prepare_environment_qualifications_local)
_namespace['cold_manifest']=lru_cache(maxsize=1)(clone_function(base.cold_manifest.__wrapped__,_namespace))
_namespace['Grading']=type('Grading',(base.Grading,),{name:clone_function(value,_namespace)
    for name,value in vars(base.Grading).items() if isinstance(value,FunctionType)})
globals().update({key:value for key,value in _namespace.items() if not key.startswith('__')})
if __name__=='__main__':main()
