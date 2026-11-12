"""New owner lifecycle for the original, still-unconsumed v105 formal pool.

The same explicitly approved user unit, containers, volumes and money are used.
Both old authority/source and the immutable deployment amendment must hold.
"""
from __future__ import annotations

from . import software_benchmark_scope_v105 as previous
from . import software_benchmark_scope_v106 as prior_deployment
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = 'v107-v105-pool-manager-wrapper-amendment-r1'
_namespace = clone_namespace(previous, VERSION=VERSION,
    API_ROOT=previous.BATCH_ROOT/'api-coordinator-v107',
    COORDINATOR_ROOT=previous.BATCH_ROOT/'grading-coordinator-v106',
    SOURCE_FILE=previous.BATCH_ROOT/'runtime-sources-v107.json',
    AUTH_FILE=previous.ROOT/'config/v107-nonthinking-manager-amendment.json',
    CLAIM_FILE=previous.BATCH_ROOT/'api-coordinator-v107/coordinator-capacity.json',
    LEASE_FILE=previous.BATCH_ROOT/'resource-claims/active-v107-coordinator.json',
    __file__=__file__)
_namespace['validate_plan'] = previous.validate_plan
_raw_require = _namespace['require_allowed']


def require_allowed(operation='v105.run', *, slot_id=None, instance_id=None, grading_only=False):
    # The old exact source index remains valid. API host limits apply to this
    # new lifecycle below, so only its non-API scope is checked here.
    prior_operation = 'v066.run' if operation.endswith('request') else operation
    prior_deployment.require_allowed(prior_operation, slot_id=slot_id,
                             instance_id=instance_id, grading_only=grading_only)
    value = _raw_require(operation, slot_id=slot_id, instance_id=instance_id, grading_only=grading_only)
    if (value.get('original_authorization') != previous.reference(previous.AUTH_FILE)
            or value.get('prior_deployment_authorization') != previous.reference(prior_deployment.AUTH_FILE)
            or value.get('same_owned_user_unit') != previous.API_UNIT
            or value.get('additional_containers') != 0
            or value.get('additional_volumes') != 0
            or value.get('diagnostics_repeated') != 0):
        raise PermissionError('The deployment amendment may not expand the original owned scope')
    if previous.LEASE_FILE.exists() or prior_deployment.LEASE_FILE.exists():
        raise PermissionError('The original coordinator has not released its exact owner lease')
    return value


_namespace['require_allowed'] = require_allowed
globals().update({key: value for key, value in _namespace.items() if not key.startswith('__')})
