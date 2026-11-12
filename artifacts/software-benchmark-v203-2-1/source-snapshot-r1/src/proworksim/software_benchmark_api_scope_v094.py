"""Complete execution plan for new physical launches of the same 44 attempts."""
from __future__ import annotations

from collections import Counter
import os

from . import software_benchmark_api_scope_v089 as canonical
from . import software_benchmark_api_scope_v093 as previous_owner
from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_expansion_episode_v069 import clone_namespace

_root = canonical.ROOT/'runs/software-benchmark-v094/physical-startup-recovery-r1'
_namespace = clone_namespace(canonical,
    VERSION='v094-complete-physical-recovery-scope-r1', predecessor=previous_owner,
    BATCH_ROOT=_root, API_ROOT=_root/'api-coordinator', API_UNIT='proworksim-v094-api.service',
    OLD_API_ROOT=previous_owner.API_ROOT, OLD_API_UNIT=previous_owner.API_UNIT,
    PLAN_FILE=_root/'execution-plan.json', INVENTORY_FILE=_root/'recovery-inventory.json',
    SOURCE_FILE=_root/'runtime-sources.json',
    AUTH_FILE=canonical.ROOT/'config/v094-physical-recovery-authorization.json',
    AUTHORIZATION_FILE=canonical.ROOT/'config/v094-physical-recovery-authorization.json',
    CLAIM_FILE=_root/'api-coordinator/coordinator-capacity.json',
    LEASE_FILE=canonical.original.BATCH_ROOT/'resource-claims/active-v094-api-coordinator.json',
    COORDINATOR_ROOT=_root/'grading-coordinator')
globals().update({key: value for key, value in _namespace.items() if not key.startswith('__')})
ROOT, original, load = (_namespace[key] for key in ('ROOT', 'original', 'load'))
VERSION, AUTH_FILE, SOURCE_FILE, PLAN_FILE, INVENTORY_FILE, LEASE_FILE, CLAIM_FILE = (
    _namespace[key] for key in ('VERSION', 'AUTH_FILE', 'SOURCE_FILE', 'PLAN_FILE', 'INVENTORY_FILE', 'LEASE_FILE', 'CLAIM_FILE'))
verify_host_limits = _namespace['verify_host_limits']
CANONICAL_INVENTORY_FILE = canonical.INVENTORY_FILE
AUDIT_FILE = ROOT/'artifacts/software-benchmark-v094/zero-model-environment-handoff-r1/summary.json'
FIRST_PHYSICAL_INDEX = 6046


def parent_module():
    from . import software_benchmark_api_parent_v094
    return software_benchmark_api_parent_v094


def require_physical_audit():
    ref = reference(AUDIT_FILE)
    audit = load(ref)
    flags = ('all_44_logical_model_attempts_unconsumed', 'all_42_remaining_physical_identities_unconsumed',
        'all_2_created_environments_quiescent', 'all_2_created_environments_fully_removed',
        'all_2_create_result_unknown_false', 'all_2_model_calls_zero', 'all_2_model_dispatch_started_false')
    if (audit.get('version') != 'v094-zero-model-two-environment-handoff-proof-r1'
            or any(audit.get(key) is not True for key in flags)
            or audit.get('zero_Docker_creation_claim_for_this_deployment') is not False
            or audit.get('created_containers_this_deployment') != 4
            or audit.get('created_named_volumes_this_deployment') != 2
            or audit.get('canonical_inventory') != reference(CANONICAL_INVENTORY_FILE)
            or len(audit.get('new_mapping', [])) != 44
            or {r['new_physical_index'] for r in audit['new_mapping']} != set(range(6046, 6090))):
        raise PermissionError('Require the full retained zero-model, consumed-physical audit')
    return ref


def canonical_rows():
    return load(reference(CANONICAL_INVENTORY_FILE))['rows']


def validate_physical_mapping(row, source, config, source_config):
    expected = {**source, **physical_fields(source), 'configuration': row['configuration']}
    if (row != expected or row['slot_index'] not in range(6046, 6090)
            or config != {**source_config, 'slot_index': row['slot_index']}):
        raise PermissionError('New physical launch differs from the exact unconsumed model attempt')
    return row


def physical_fields(source):
    prior = source['slot_index']
    rebuilt = prior in (6000, 6001)
    return {'slot_index': prior+(88 if rebuilt else 44),
        'prior_physical_slot_index': prior+44 if rebuilt else prior,
        'physical_launch_attempt': 3 if rebuilt else 2}


def validate_mapping(row, source, config, original_config):
    old = next((r for r in canonical_rows() if r['slot_id'] == row.get('slot_id')), None)
    if old is None:
        raise PermissionError('No authorized canonical model-attempt identity')
    old_config = load(old['configuration'])
    canonical.validate_mapping(old, source, old_config, original_config)
    return validate_physical_mapping(row, old, config, old_config)


def validate_complete_plan(plan, inventory):
    ancestor = load(reference(original.PLAN_FILE))
    if (set(ancestor)-set(plan) or plan.get('version') != VERSION
            or plan.get('root') != str(original.BATCH_ROOT)
            or plan.get('original_plan') != reference(original.PLAN_FILE)
            or plan.get('host_cpu_pool') != ancestor['host_cpu_pool']
            or plan.get('matrix') != ancestor['matrix'] or plan.get('configurations') != ancestor['configurations']
            or plan.get('continuation_inventory') != reference(INVENTORY_FILE)
            or plan.get('inventory') != reference(INVENTORY_FILE)
            or plan.get('rows') != inventory.get('rows') or len(plan.get('rows', [])) != 44
            or plan.get('remaining_generation_slots') != 44
            or plan.get('remaining_original_token_upper_bound') != 220_000_000
            or plan.get('historical_results_preserved') is not True or plan.get('training') is not False
            or plan.get('model_calls_during_preparation') != 0):
        raise PermissionError('The complete inherited execution-plan contract differs')
    counts = dict(Counter(item['role'] for item in plan['resources'].values()))
    if (counts != {'actor': 44, 'controller': 44, 'volume': 44, 'score': 44, 'delivery_score': 23}
            or plan.get('resource_role_counts') != counts
            or {r['slot_index'] for r in plan['rows']} != set(range(6046, 6090))
            or plan.get('previous_created_containers') != 4 or plan.get('previous_created_named_volumes') != 2
            or plan.get('cumulative_container_upper_bound') != 159
            or plan.get('cumulative_named_volume_upper_bound') != 46):
        raise PermissionError('Physical resources extend beyond the exact new 44-launch plan')
    originals = {row['slot_id']: row for row in canonical_rows()}
    audit = load(require_physical_audit())
    approved = {row['logical_slot_id']: row for row in audit['new_mapping']}
    prior_rows = {r['slot_id']: r for r in load(audit['prior_physical_inventory'])['rows']}
    canonical_plan = load(reference(canonical.PLAN_FILE))
    for row in plan['rows']:
        old = originals.get(row['slot_id'])
        if old is None or approved[row['slot_id']]['new_physical_index'] != row['slot_index']:
            raise PermissionError('Physical row lacks zero-model mapping evidence')
        validate_physical_mapping(row, old, load(row['configuration']), load(old['configuration']))
        if old['slot_index'] not in (6000, 6001) and row != prior_rows[row['slot_id']]:
            raise PermissionError('The 42 unconsumed physical rows/configurations must remain exact')
        for prefix in ('actor', 'controller', 'volume', 'score', 'delivery-score'):
            previous = canonical_plan['resources'].get(f'{prefix}-{old["slot_index"]}')
            if previous is not None and plan['resources'].get(f'{prefix}-{row["slot_index"]}') != {
                    **previous, 'prior_physical_slot_index': row['prior_physical_slot_index'],
                    'physical_launch_attempt': row['physical_launch_attempt']}:
                raise PermissionError('Physical resource image, role or task identity changed')
    return plan


def require_allowed(operation='v094.run', *, slot_id=None, instance_id=None, grading_only=False):
    accepted = {'v094.run', 'v094.prepare', 'v094.api.run', 'v094.api.request', 'v089.run',
        'v089.api.run', 'v089.api.request', 'v076.run', 'v079.run', 'v088.run', 'v086.run', 'v072.api.request'} | set(original.OPERATIONS)
    if os.getuid() == 0 or os.geteuid() == 0 or operation not in accepted or grading_only and operation.endswith('request'):
        raise PermissionError('Operation outside the exact physical-recovery scope')
    canonical.require_allowed('v089.run', slot_id=slot_id, instance_id=instance_id, grading_only=True)
    auth = load(reference(AUTH_FILE))
    if (auth.get('version') != VERSION or auth.get('status') != 'approved'
            or auth.get('prior_authorization') != reference(previous_owner.AUTH_FILE)
            or auth.get('source_index') != reference(SOURCE_FILE) or auth.get('plan') != reference(PLAN_FILE)
            or auth.get('inventory') != reference(INVENTORY_FILE)
            or auth.get('physical_zero_model_audit') != require_physical_audit()
            or auth.get('logical_model_attempts') != 44 or auth.get('additional_model_attempts') != 0
            or auth.get('API_cash_cap_CNY') != '1700.00'
            or auth.get('old_records_overwritten') is not False or auth.get('Qwen_lifecycle_operations') != 0):
        raise PermissionError('Physical relaunch authority differs from the original 44 model attempts')
    for item in load(auth['source_index'])['files']:
        checked(item)
    plan = validate_complete_plan(load(auth['plan']), load(reference(INVENTORY_FILE)))
    if slot_id is not None:
        row = next((r for r in plan['rows'] if r['slot_id'] == slot_id), None)
        if row is None or instance_id not in (None, row['instance_id']):
            raise PermissionError('No new physical mapping for this model attempt')
    if not grading_only:
        parent_module().require_qualified()
    if operation.endswith('request'):
        verify_host_limits()
        if not LEASE_FILE.exists() or LEASE_FILE.read_bytes() != checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('No active exact physical-recovery manager lease')
    return auth


def require_grading_allowed(operation='v076.run', **identity):
    if operation not in {'v076.run', 'v079.run', 'v089.run', 'v094.run', 'v066.run', 'v066.score',
        'v066.delivery.score', 'v066.grader.create', 'v066.grader.start', 'v066.transport', 'v066.resolve'}:
        raise PermissionError('Grading authority cannot create model actors')
    return require_allowed(operation, grading_only=True, **identity)


_namespace.update(require_allowed=require_allowed, require_grading_allowed=require_grading_allowed,
                  parent_module=parent_module, validate_mapping=validate_mapping)
