"""Condition-distinct official grading and exact no-network environment reuse.

The selected Requests1142/1724/6028 and pytest5631/7521 are not the historical
four network-repair or two offline-wheel tasks. No repository-wide provider is
silently applied. A missing exact gold/empty proof schedules its own new pair.
"""
from __future__ import annotations
from functools import lru_cache
import inspect
import json
from pathlib import Path
from types import FunctionType
from . import software_benchmark_scope_v157 as scope
from . import software_benchmark_grading_v105 as base
from . import software_benchmark_grading_v131 as robust
from . import software_benchmark_scorer_v066 as old
from .software_benchmark_candidates_v054 import reference, checked
from .software_benchmark_expansion_episode_v069 import clone_function, clone_namespace

VERSION='v157-communication-official-scoring-r1'
REUSE_VERSION='v157-exact-no-network-official-controls-reuse-r1'
MODULE=__name__
FRESH_CONTROL_TASKS=frozenset({'psf__requests-1142','psf__requests-1724'})
_namespace=clone_namespace(base,scope=scope,VERSION=VERSION,REUSE_VERSION=REUSE_VERSION,MODULE=MODULE,__file__=__file__)
_parent_scorer=_namespace['scorer'];_parent_host=_namespace['host']

def control_key(task,kind):
    if kind not in {'gold','empty'}: raise ValueError('Only gold/empty controls')
    return 'control-recovery-r2-'+task+'-'+kind

def reuse_value(task,manifest_ref,plan):
    from .software_benchmark_grading_repairs_v157 import RESET_TASKS
    if task in RESET_TASKS:
        from .software_communication_reset_evidence_v157 import verified_reset_controls
        config=scope.load(plan['environments'][task]['configuration'])
        proof=verified_reset_controls(task,config)
        manifest=scope.load(manifest_ref)
        actual=manifest['selective_reset_actual_hashes'][task]
        if any(any(actual[k]!=r[k] for k in actual) for r in proof['controls']):
            raise ValueError('Current selective reset differs from qualified historical gold/empty')
        if manifest['selective_reset_by_task'][task]!=proof['reset_source']:
            raise ValueError('Current selective reset implementation source changed')
        return {'version':REUSE_VERSION,'instance_id':task,'passed':True,'plan':reference(scope.PLAN_FILE),
            'current_manifest':manifest_ref,'selective_reset_proof':proof,'actual_reset_hashes':actual,
            'model_calls':0,'Docker_operations':0,'new_controls':0,'network_mode':'none'}
    source=plan['environment_sources'][task]
    if source['qualification'] is None: raise ValueError('No historical qualified controls for '+task)
    before=scope.load(source['configuration']);after=scope.load(plan['environments'][task]['configuration'])
    if base.environment_identity(before)!=base.environment_identity(after):
        raise ValueError('Exact image/dataset/official baseline/scorer inputs changed')
    actual=old.validate_qualification(source['qualification'],before,source['plan'])
    if actual.get('passed') is not True: raise ValueError('Old gold/empty not qualified')
    old_manifest_ref=reference(old.policy.COORDINATOR_RUN_ROOT/'scorer-manifest.json')
    historical,current=scope.load(old_manifest_ref),scope.load(manifest_ref)
    keys=('parent','archive_adapter','limits','cap_add','cap_drop','no_new_privileges',
          'official_tests_and_scoring_rules_changed','host_namespace_mount_or_daemon_operations')
    if any(historical.get(k)!=current.get(k) for k in keys):
        raise ValueError('Official evaluator or no-network isolation/limits changed')
    if task in old.environment.TASKS: raise ValueError('Special environment requires actual provider equivalence')
    return {'version':REUSE_VERSION,'instance_id':task,'passed':True,'plan':reference(scope.PLAN_FILE),
        'original_qualification':source['qualification'],'original_configuration':source['configuration'],
        'original_plan':source['plan'],'current_manifest':manifest_ref,'original_manifest':old_manifest_ref,
        'exact_environment_identity':base.environment_identity(after),'unchanged_manifest_fields':list(keys),
        'control_result_and_cleanup_evidence_revalidated':True,'network_mode':'none',
        'model_calls':0,'Docker_operations':0,'new_controls':0}

def validate_reused_qualification(ref,config,plan_ref):
    value=scope.load(ref)
    if value!=reuse_value(config['instance_id'],value['current_manifest'],scope.load(plan_ref)) or value['plan']!=plan_ref:
        raise ValueError('Exact environment reuse proof changed')
    return value

def scorer(policy,*,manifest_provider=None):
    from . import software_benchmark_project_closure_v157 as closure
    value=_parent_scorer(policy,manifest_provider=manifest_provider)
    ns=value.validate_request.__globals__
    # The new panel is wholly network=none without provider namespaces/capabilities.
    environment=ns['environment']
    def fields(task):
        if task not in scope.load(reference(scope.PLAN_FILE))['environments']: raise ValueError('Foreign task')
        return {'environment_revision':None,'network_resolution':None}
    def validate_environment(request,task):
        if any(request.get(k)!=v for k,v in fields(task).items()): raise ValueError('Unexpected network revision')
        return None
    environment.request_fields=fields;environment.validate_request=validate_environment
    environment.provider=lambda task:None
    environment.capabilities=lambda task:[]
    environment.prepare=lambda:{'network_mode':'none','Docker_operations':0,'network_connections':0}
    environment.TASKS=environment.OFFLINE_TASKS=environment.TLS_TASKS=frozenset()
    ns.update(validate_delivery_evidence=closure.validate_delivery_evidence,MAX_GRADERS=scope.MAX_GRADERS)
    ns['validate_request']=robust._lane_validator(ns)
    native_source=inspect.getsource(old.validate_qualification)
    needle='"control-" + task + "-" + kind'
    if native_source.count(needle)!=1: raise ValueError('Official qualification key expression changed')
    compiled={}
    exec(compile(native_source.replace(needle,'"control-recovery-r2-" + task + "-" + kind'),__file__+':r2-control-validator','exec'),ns,compiled)
    native=compiled['validate_qualification']
    def validate_qualification(ref,config,plan_ref):
        proof=scope.load(ref)
        if proof.get('version')==REUSE_VERSION:
            return validate_reused_qualification(ref,config,plan_ref)
        return native(ref,config,plan_ref)
    ns['validate_qualification']=validate_qualification
    original_planned=ns['_planned'];original_generation=ns['_generation_result'];candidate=ns['validate_candidate_request']
    def planned(request):
        plan,resource,config=original_planned(request)
        if resource['role']!='control':
            row=next(r for r in plan['rows'] if r['slot_id']==request['slot_id'])
            for key in ('organization_id','group_id'):
                if any(v.get(key)!=row[key] for v in (config,request,resource)):
                    raise ValueError('Candidate crossed communication condition or REVIEW2 organization')
        return plan,resource,config
    def generation(request,config,plan):
        row,result,folder=original_generation(request,config,plan)
        if any(result.get(k)!=row[k] for k in ('organization_id','group_id')):
            raise ValueError('Generation lost exact treatment identity')
        return row,result,folder
    def validate_candidate(request,resource,config,plan):
        locked=candidate(request,resource,config,plan)
        if resource['role']=='score':
            _,result,folder=generation(request,config,plan)
            ns['validate_project_delivery'](result,config,folder)
        return locked
    ns.update(_planned=planned,_generation_result=generation,validate_candidate_request=validate_candidate)
    inherited=ns['installation_manifest']
    def manifest():
        if manifest_provider is not None: return inherited()
        return {**inherited(),'managed_delivery_validator':reference(closure.__file__),
            'communication_identity_binding':reference(__file__),'new_resource_scope':reference(scope.__file__),
            'network_mode':'none','selected_task_specific_network_providers':[],
            'scoring_rules_changed':False,'candidate_reselection':False,'grading_lane_count':2}
    ns['installation_manifest']=manifest
    ns['cleanup']=clone_function(robust.bind_physical_cleanup,{**robust.bind_physical_cleanup.__globals__,'VERSION':VERSION})(ns)
    for key in ('_planned','_generation_result','validate_candidate_request','validate_request',
                'validate_delivery_evidence','validate_qualification','installation_manifest','cleanup'):
        setattr(value,key,ns[key])
    from . import software_benchmark_grading_repairs_v157 as repairs
    dataset=json.loads(checked(reference(scope.ROOT/'artifacts/software-benchmark-v054/source/trusted-evaluation.json')).read_bytes())
    return repairs.bind_scorer(value,[row for row in dataset if row['instance_id'] in repairs.RESET_TASKS])

def prepare_environment_qualifications_local():
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    scoring=scorer(scope.dispatch_view(scope.require_grading_allowed))
    manifest=scope.retain(scope.COORDINATOR_ROOT/'scorer-manifest.json',scoring.installation_manifest())
    qualifications,controls,failures={},{},{}
    controls=[]
    for task in plan['environments']:
        try:
            value=reuse_value(task,manifest,plan)
            ref=scope.retain(scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'),value)
            qualifications[task]={'status':'qualified','qualification':ref,'reused_controls':True}
        except (ValueError,KeyError,OSError) as error:
            failures[task]={'status':'requires_new_controls','error':type(error).__name__+': '+str(error)}
            for kind in ('gold','empty'):
                key=control_key(task,kind)
                request={'version':VERSION,'resource_key':key,'instance_id':task,'slot_id':None,
                    'plan':reference(scope.PLAN_FILE),'configuration':plan['environments'][task]['configuration'],
                    'patch_kind':kind,'limits':scoring.LIMITS,'scorer_manifest':manifest,
                    'cpuset_cpus':None,'directory':str(scope.GRADING_ROOT/key),'candidate_lock':None,
                    **scoring.environment.request_fields(task)}
                controls.append(scope.retain(scope.GRADING_ROOT/key/'request.json',request))
    result={'version':VERSION,'qualifications':qualifications,'controls':controls,'reuse_failures':failures,
        'model_calls':0,'Docker_operations':0,'new_controls_only_for_missing_or_changed_exact_evidence':True}
    scope.retain(scope.COORDINATOR_ROOT/'qualification-preparation.json',result)
    return result

def validate_environment_preparation():
    """Read/verify all24 actual qualifications without creating or rerunning work."""
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    status_ref=reference(scope.API_ROOT/'environment-only-qualification-status-r2.json')
    status=scope.load(status_ref)
    if set(status.get('qualifications',{}))!=set(plan['environments']):
        raise ValueError('The current complete24-task environment inventory is missing')
    manifest_ref=reference(scope.COORDINATOR_ROOT/'scorer-manifest.json')
    frozen=scope.load(manifest_ref)
    actual=cold_manifest()
    differences={key for key in set(actual)|set(frozen) if actual.get(key)!=frozen.get(key)}
    if differences-{'managed_delivery_validator'}:
        raise ValueError('Actual official scoring environment changed: '+','.join(sorted(differences)))
    scoring=scorer(scope.dispatch_view(scope.require_grading_allowed),manifest_provider=lambda:frozen)
    qualifications={}
    for task,row in status['qualifications'].items():
        if row.get('status')!='qualified':
            raise ValueError('Task lacks qualified gold/empty environment: '+task)
        value=scoring.validate_qualification(row['qualification'],
            scope.load(plan['environments'][task]['configuration']),reference(scope.PLAN_FILE))
        if value.get('passed') is not True:
            raise ValueError('Environment qualification is not passing: '+task)
        qualifications[task]=row
    return {'version':VERSION,'passed':True,'qualifications':qualifications,'status':status_ref,
        'scorer_manifest':manifest_ref,'model_calls':0,'Docker_operations':0,'new_controls':0,
        'existing_control_cleanup_revalidated':True,
        'delivery_only_manifest_fields_changed':sorted(differences),
        'official_environment_scoring_test_rules_unchanged':True}

def host(policy,scoring):
    helper={**robust.host.__globals__,'scope':scope,'VERSION':VERSION,'_parent_host':_parent_host,
            'control_key':control_key,'FRESH_CONTROL_TASKS':FRESH_CONTROL_TASKS}
    return clone_function(robust.host,helper)(policy,scoring)

_namespace.update(scorer=scorer,host=host,validate_reused_qualification=validate_reused_qualification,
                  prepare_environment_qualifications_local=prepare_environment_qualifications_local)
_namespace['cold_manifest']=lru_cache(maxsize=1)(clone_function(base.cold_manifest.__wrapped__,_namespace))
_namespace['Grading']=type('Grading',(base.Grading,),{name:clone_function(value,_namespace)
    for name,value in vars(base.Grading).items() if isinstance(value,FunctionType)})
globals().update({key:value for key,value in _namespace.items() if not key.startswith('__')})
if __name__=='__main__': main()
