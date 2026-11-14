"""Two fresh Requests controls share the batch's single grader lane, zero API."""
from __future__ import annotations
import copy
import os
import fcntl
from types import SimpleNamespace
from . import software_benchmark_scope_v203_2_3 as original
from .software_benchmark_candidates_v054 import checked,reference

VERSION='v203.2.3-requests-strict-http-boundary-preparation-r4'
GRADING_ROOT=original.BATCH_ROOT/'grading-r4'
COORDINATOR_ROOT=original.BATCH_ROOT/'grading-coordinator-r4'
CONTROL_PLAN_FILE=GRADING_ROOT/'control-plan.json'
AUTH_FILE=original.ARTIFACT_ROOT/'grading-preparation-authorization-r4/authorization.json'
KEYS=frozenset({'control-r4-psf__requests-1766-gold','control-r4-psf__requests-1766-empty'})


def prepare_control_plan():
    formal=original.load(reference(original.PLAN_FILE));task='psf__requests-1766'
    resources={key:{'role':'control','instance_id':task,'patch_kind':key.rsplit('-',1)[1],
        'image_id':formal['environments'][task]['image_id'],'endpoint':'environment_control'} for key in sorted(KEYS)}
    value={'version':VERSION,'root':str(original.BATCH_ROOT),'formal_plan':reference(original.PLAN_FILE),
        'environments':{task:copy.deepcopy(formal['environments'][task])},'rows':[], 'resources':resources,
        'host_cpu_pool':reference(original.CPU_POOL_FILE),'constraints':copy.deepcopy(original.CONSTRAINTS),
        'resource_role_counts':{'control':2},'model_calls':0,'new_API_budget':False,
        'same_single_grader_lane_and_claim_directory_as_formal_run':True}
    return original.retain(CONTROL_PLAN_FILE,value)


def require_allowed(operation='v203.2.3.run', *, slot_id=None,instance_id=None,**kwargs):
    allowed={'v203.2.3.run','v066.run','v066.control','v066.grader.create','v066.grader.start','v066.transport','v066.resolve'}
    if os.getuid()==0 or os.geteuid()==0 or slot_id is not None or operation not in allowed:
        raise PermissionError('Fresh environment controls cannot enter formal/model identities')
    if instance_id not in (None,'psf__requests-1766'):
        raise PermissionError('Only the selected Requests environment controls are admitted')
    value=original.load(reference(AUTH_FILE))
    if (value.get('status')!='approved' or value.get('plan')!=reference(CONTROL_PLAN_FILE)
            or value.get('formal_plan')!=reference(original.PLAN_FILE) or value.get('API_calls_allowed')!=0
            or set(value.get('resource_keys',[]))!=KEYS or value.get('uid')!=os.getuid()):
        raise PermissionError('The two new control identities or original formal plan changed')
    for ref in original.load(value['source_index'])['files']:checked(ref)
    return value


def dispatch_view(guard=None):
    value=original.dispatch_view(require_allowed)
    namespace=value.claim_resource.__globals__
    def allowed(operation='v066.run',**identity):
        result=require_allowed(operation,**identity)
        return {**result,'plan':reference(CONTROL_PLAN_FILE),'sources':result['source_index'],'constraints':original.CONSTRAINTS}
    bindings={'AUTHORIZATION_FILE':AUTH_FILE,'PLAN_FILE':CONTROL_PLAN_FILE,'GRADING_ROOT':GRADING_ROOT,
        'COORDINATOR_RUN_ROOT':COORDINATOR_ROOT,'require_v066_allowed':allowed}
    namespace.update(bindings)
    value.__dict__.update(bindings)
    claim=value.claim_resource
    def claim_control(key, *, lane=None):
        if key not in KEYS:raise PermissionError('Only the two newly declared control identities may be claimed')
        shared=original.BATCH_ROOT/'resource-claims/grader-allocation.lock'
        shared.parent.mkdir(parents=True,exist_ok=True)
        with shared.open('a+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            others=[original.ROOT/'runs/software-benchmark-v203-2-3'/name/'resource-claims'
                for name in ('role-context-pilot12-r2','requests-leaf-r1','role-context-recovery12-r3')]
            if any(list(other.glob('active-grader-*.json')) for other in others):
                raise original.ResourceBusy('The one shared grader lane is occupied by a formal scorer')
            return claim(key,lane=lane)
    value.claim_resource=claim_control
    return value


def preparation_scope():
    return SimpleNamespace(**{**vars(original),'PLAN_FILE':CONTROL_PLAN_FILE,
        'FORMAL_PLAN_FILE':original.PLAN_FILE,'GRADING_ROOT':GRADING_ROOT,'COORDINATOR_ROOT':COORDINATOR_ROOT,
        'require_allowed':require_allowed,'require_grading_allowed':require_allowed,'dispatch_view':dispatch_view,
        'AUTH_FILE':AUTH_FILE,'validate_plan':lambda plan:validate_control_plan(plan)})


def validate_control_plan(plan):
    if (plan!=original.load(reference(CONTROL_PLAN_FILE)) or set(plan.get('resources',{}))!=KEYS
            or plan.get('formal_plan')!=reference(original.PLAN_FILE) or plan.get('model_calls')!=0):
        raise PermissionError('Exact fresh control plan differs')
    return plan
