"""New manager for the same 44 proven-unconsumed authorized attempts."""
from __future__ import annotations

import os

from . import software_benchmark_api_scope_v089 as previous
from . import software_benchmark_api_scope_v091 as failed_owner
from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_expansion_episode_v069 import clone_namespace

_root = previous.ROOT/'runs/software-benchmark-v092/unentered-pressure-recovery-r1'
_namespace = clone_namespace(previous,
    VERSION='v092-unentered-recovery-manager-r1', predecessor=failed_owner,
    BATCH_ROOT=_root, API_ROOT=_root/'api-coordinator', API_UNIT='proworksim-v092-api.service',
    OLD_API_ROOT=failed_owner.API_ROOT, OLD_API_UNIT=failed_owner.API_UNIT,
    SOURCE_FILE=_root/'runtime-sources.json',
    AUTH_FILE=previous.ROOT/'config/v092-unentered-recovery-authorization.json',
    AUTHORIZATION_FILE=previous.ROOT/'config/v092-unentered-recovery-authorization.json',
    CLAIM_FILE=_root/'api-coordinator/coordinator-capacity.json',
    LEASE_FILE=previous.original.BATCH_ROOT/'resource-claims/active-v092-api-coordinator.json',
    COORDINATOR_ROOT=_root/'grading-coordinator')
globals().update({name: value for name, value in _namespace.items() if not name.startswith('__')})
ROOT, original, predecessor = (_namespace[key] for key in ('ROOT', 'original', 'predecessor'))
load, parent_module, verify_host_limits = (
    _namespace[key] for key in ('load', 'parent_module', 'verify_host_limits'))
VERSION, AUTH_FILE, SOURCE_FILE, PLAN_FILE, INVENTORY_FILE, LEASE_FILE, CLAIM_FILE = (
    _namespace[key] for key in ('VERSION', 'AUTH_FILE', 'SOURCE_FILE', 'PLAN_FILE', 'INVENTORY_FILE',
                               'LEASE_FILE', 'CLAIM_FILE'))
HANDOFF_FILE = ROOT/'artifacts/software-benchmark-v092/unentered-handoff-r1/completed.json'


def amendment_ledger():
    return original.PREDECESSOR_ROOT/'api-budget/ledger.sqlite3'


def require_handoff():
    ref = reference(HANDOFF_FILE)
    value = load(ref)
    if (value.get('version') != 'v092-exact-zero-consumption-owner-handoff-r1'
            or value.get('old_main_pid_exited') is not True
            or value.get('all_44_model_attempts_unconsumed') is not True
            or value.get('all_44_physical_identities_unconsumed') is not True
            or value.get('original_API_parent_stopped') is not False
            or value.get('original_API_parent_preserved') != reference(parent_module().CREATED)
            or predecessor.LEASE_FILE.exists()):
        raise PermissionError('Exact old-owner retirement and all-44 zero-consumption proof required')
    proof = load(value['zero_consumption_proof'])
    if proof.get('plan') != reference(PLAN_FILE) or proof.get('inventory') != reference(INVENTORY_FILE):
        raise PermissionError('Retirement proof belongs to another recovery registry')
    released = load(value['old_manager_lease_released'])
    if released.get('quiescent') is not True or released.get('claim') != reference(predecessor.CLAIM_FILE):
        raise PermissionError('Original manager reservation release is not proven')
    return ref


def require_allowed(operation='v092.run', *, slot_id=None, instance_id=None, grading_only=False):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('The continuation manager remains an ordinary user process')
    accepted = {'v092.run', 'v092.prepare', 'v092.api.run', 'v092.api.request',
        'v089.run', 'v089.api.run', 'v089.api.request', 'v091.run', 'v088.run', 'v086.run', 'v079.run', 'v076.run', 'v072.api.request'} | set(original.OPERATIONS)
    if operation not in accepted or grading_only and operation.endswith('request'):
        raise PermissionError('Operation outside the proven-unentered manager scope')
    prior_auth = predecessor.require_allowed('v089.run', slot_id=slot_id,
        instance_id=instance_id, grading_only=True)
    handoff = require_handoff()
    auth = load(reference(AUTH_FILE))
    if (auth.get('version') != VERSION or auth.get('status') != 'approved'
            or auth.get('prior_authorization') != reference(predecessor.AUTH_FILE)
            or auth.get('source_index') != reference(SOURCE_FILE)
            or auth.get('plan') != prior_auth['plan'] or auth.get('inventory') != reference(INVENTORY_FILE)
            or auth.get('handoff') != handoff or auth.get('continued_unconsumed_attempts') != 44
            or auth.get('additional_generation_attempts') != 0
            or auth.get('API_cash_cap_CNY') != '1700.00'
            or auth.get('original_records_overwritten') is not False
            or auth.get('Qwen_lifecycle_operations') != 0):
        raise PermissionError('Unentered recovery continuation authority differs')
    for item in load(auth['source_index'])['files']:
        checked(item)
    if not grading_only:
        parent_module().require_qualified()
    if operation.endswith('request'):
        verify_host_limits()
        if not LEASE_FILE.exists() or LEASE_FILE.read_bytes() != checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('No active exact new-manager reservation')
    return auth


def require_grading_allowed(operation='v076.run', **identity):
    if operation not in {'v076.run', 'v079.run', 'v089.run', 'v092.run', 'v066.run', 'v066.score',
                         'v066.delivery.score', 'v066.grader.create', 'v066.grader.start',
                         'v066.transport', 'v066.resolve'}:
        raise PermissionError('The grading scope cannot create generation objects')
    return require_allowed(operation, grading_only=True, **identity)


_namespace.update(require_allowed=require_allowed, require_grading_allowed=require_grading_allowed)
