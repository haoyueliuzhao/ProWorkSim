"""Separate, zero-API authority for only the two new Requests scorer controls."""
from __future__ import annotations
import os
from types import SimpleNamespace
from . import software_benchmark_scope_v203_2_3 as original
from .software_benchmark_candidates_v054 import checked,reference

AUTH_FILE=original.ARTIFACT_ROOT/'grading-preparation-authorization-r1/authorization.json'
KEYS=frozenset({'control-psf__requests-1766-gold','control-psf__requests-1766-empty'})


def require_allowed(operation='v203.2.3.run', *, slot_id=None,instance_id=None,**kwargs):
    allowed={'v203.2.3.run','v066.run','v066.control','v066.grader.create','v066.grader.start',
             'v066.transport','v066.resolve'}
    if os.getuid()==0 or os.geteuid()==0 or slot_id is not None or operation not in allowed:
        raise PermissionError('Preparation grading cannot start formal tasks or call a model')
    if instance_id not in (None,'psf__requests-1766'):
        raise PermissionError('Only the selected Requests environment controls are admitted')
    value=original.load(reference(AUTH_FILE))
    if (value.get('status')!='approved' or value.get('plan')!=reference(original.PLAN_FILE)
            or value.get('API_calls_allowed')!=0 or set(value.get('resource_keys',[]))!=KEYS
            or value.get('uid')!=os.getuid()):
        raise PermissionError('The two-control preparation authority differs')
    for ref in original.load(value['source_index'])['files']:checked(ref)
    return value


def dispatch_view(guard=None):
    value=original.dispatch_view(require_allowed)
    namespace=value.claim_resource.__globals__
    namespace['AUTHORIZATION_FILE']=AUTH_FILE
    value.AUTHORIZATION_FILE=AUTH_FILE
    claim=value.claim_resource
    def claim_control(key, *, lane=None):
        if key not in KEYS:raise PermissionError('Only the two explicit new control identities may be claimed')
        return claim(key,lane=lane)
    value.claim_resource=claim_control
    return value


def preparation_scope():
    return SimpleNamespace(**{**vars(original),'require_allowed':require_allowed,
        'require_grading_allowed':require_allowed,'dispatch_view':dispatch_view,'AUTH_FILE':AUTH_FILE})
