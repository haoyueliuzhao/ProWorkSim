"""Exact 79 still-unused original API attempts; new physical identities only."""
from __future__ import annotations

from collections import Counter
from contextlib import closing
import os
from pathlib import Path
import sqlite3

from . import software_benchmark_api_scope_v089 as infrastructure
from . import software_benchmark_api_scope_v094 as previous_owner
from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_expansion_episode_v069 import clone_namespace

_root = infrastructure.ROOT/'runs/software-benchmark-v096/zero-api-first-entry-r1'
_namespace = clone_namespace(infrastructure,
    VERSION='v096-79-original-zero-API-first-entry-r1', predecessor=previous_owner,
    BATCH_ROOT=_root, API_ROOT=_root/'api-coordinator', API_UNIT='proworksim-v096-api.service',
    OLD_API_ROOT=previous_owner.API_ROOT, OLD_API_UNIT=previous_owner.API_UNIT,
    PLAN_FILE=_root/'execution-plan.json', INVENTORY_FILE=_root/'inventory.json',
    SOURCE_FILE=_root/'runtime-sources.json',
    AUTH_FILE=infrastructure.ROOT/'config/v096-zero-api-entry-authorization.json',
    AUTHORIZATION_FILE=infrastructure.ROOT/'config/v096-zero-api-entry-authorization.json',
    CLAIM_FILE=_root/'api-coordinator/coordinator-capacity.json',
    LEASE_FILE=infrastructure.original.BATCH_ROOT/'resource-claims/active-v096-api-coordinator.json',
    COORDINATOR_ROOT=_root/'grading-coordinator', RECOVERY_COUNT=79, FIRST_PHYSICAL_INDEX=6090)
globals().update({key: value for key, value in _namespace.items() if not key.startswith('__')})
ROOT, original = (_namespace[key] for key in ('ROOT', 'original'))
VERSION, AUTH_FILE, SOURCE_FILE, PLAN_FILE, INVENTORY_FILE, LEASE_FILE, CLAIM_FILE = (
    _namespace[key] for key in ('VERSION', 'AUTH_FILE', 'SOURCE_FILE', 'PLAN_FILE', 'INVENTORY_FILE', 'LEASE_FILE', 'CLAIM_FILE'))
verify_host_limits = _namespace['verify_host_limits']


def load(ref):
    # The original dispatcher rehashes bytes on every use and invalidates its
    # parsed-object cache on any digest change. Reuse parsing, never identity.
    return original._cached_json(ref)

CANONICAL_INVENTORY_FILE = _root/'canonical-original-inventory.json'
FINANCIAL_RECOVERY_INVENTORY = infrastructure.INVENTORY_FILE
AUDIT_ROOT = ROOT/'artifacts/software-benchmark-v095/historical-exception-inventory-r1'
ZERO_API_FILE = AUDIT_ROOT/'zero-api-78.json'
AUDIT_FILE = AUDIT_ROOT/'summary.json'
ORIGINAL_SUMMARY = ROOT/'runs/software-benchmark-v088/api-select-recovery-r1/api-coordinator/run-summary.json'
MODEL_ATTEMPTS = 79
TOKEN_UPPER_BOUND = 395_000_000
FIRST_PHYSICAL_INDEX, LAST_PHYSICAL_INDEX = 6090, 6168


def parent_module():
    from . import software_benchmark_api_parent_v096
    return software_benchmark_api_parent_v096


def require_physical_audit():
    value = load(reference(ZERO_API_FILE))
    flags = ('all_zero_requests', 'all_zero_response_observations', 'all_zero_provider_protocol_events',
        'all_quiescent', 'all_cleanup_errors_empty', 'all_retained_objects_empty',
        'all_create_results_known', 'all_capacity_claims_released')
    if (value.get('version') != 'v095-78-zero-API-historical-preentry-r1'
            or value.get('count') != 78 or len(value.get('rows', [])) != 78
            or any(value.get(key) is not True for key in flags)
            or len({row['slot_id'] for row in value['rows']}) != 78):
        raise PermissionError('The exact 78 zero-API physical-consumption audit is required')
    extra = load(reference(AUDIT_FILE))['groups']['original_not_started']
    if (extra.get('count') != 29 or extra.get('zero_requests_and_generation_claims') is not True
            or extra.get('qualified_but_administratively_unstarted') != {
                'count': 1, 'slot_index': 1188, 'instance_id': 'sympy__sympy-15599',
                'original_reason': 'api_shared_halted'}):
        raise PermissionError('Only the already qualified original slot1188 may be appended')
    return reference(ZERO_API_FILE)


def selected_original_rows():
    require_physical_audit()
    evidence = load(reference(ZERO_API_FILE))['rows']
    wanted = {row['slot_id'] for row in evidence}
    source = load(reference(original.PLAN_FILE))['rows']
    extra = next(row for row in source if row['slot_index'] == 1188)
    wanted.add(extra['slot_id'])
    result = sorted((row for row in source if row['slot_id'] in wanted), key=lambda row: row['slot_index'])
    if (len(result) != 79 or Counter(row['arm'] for row in result) != {'REF': 38, 'PROJECT': 41}
            or any(row['model_key'] != 'DEEPSEEK' or row['input_plus_output_tokens'] != 5_000_000
                   or ':recovery-' in row['slot_id'] for row in result)):
        raise PermissionError('Original first-entry selection differs from the exact 79 IDs')
    history = load(reference(ORIGINAL_SUMMARY))
    for row in result:
        entry = history['generation'][row['slot_id']]
        if row['slot_index'] == 1188:
            if entry != {'status': 'not_started', 'entered': False, 'not_started_reason': 'api_shared_halted'}:
                raise PermissionError('The appended original slot is no longer the recorded unstarted task')
        elif entry.get('status') != 'technical_unknown':
            raise PermissionError('Expected an original zero-API infrastructure failure')
        qualification = history['qualifications'][row['instance_id']]
        if (qualification.get('status') != 'qualified'
                or load(qualification['qualification']).get('passed') is not True):
            raise PermissionError('No already passed original environment qualification')
    return result


def canonical_rows():
    value = load(reference(CANONICAL_INVENTORY_FILE))
    rows = selected_original_rows()
    if (value.get('version') != VERSION or value.get('rows') != rows
            or value.get('zero_API_audit') != reference(ZERO_API_FILE)
            or value.get('historical_inventory_summary') != reference(AUDIT_FILE)):
        raise PermissionError('Canonical original-ID inventory changed')
    return rows


def validate_registry(rows):
    rows = list(rows.values()) if isinstance(rows, dict) else list(rows)
    expected = canonical_rows()
    if rows != expected:
        raise PermissionError('Runtime must bind the complete exact 79 original-ID registry')
    return {row['slot_id']: row for row in rows}


def physical_fields(source, position):
    if type(position) is not int or position not in range(79):
        raise PermissionError('Unknown original-ID position')
    return {'slot_index': 6090+position, 'original_slot_id': source['slot_id'],
        'original_slot_index': source['slot_index'], 'prior_physical_slot_index': source['slot_index'],
        'physical_launch_attempt': 1 if source['slot_index'] == 1188 else 2,
        'model_attempt_kind': 'original_first_model_attempt', 'additional_model_attempts': 0}


def _validate_physical_mapping_at(row, source, config, source_config, position):
    if (position is None or row != {**source, **physical_fields(source, position),
                                   'configuration': row['configuration']}
            or config != {**source_config, 'slot_index': row['slot_index']}):
        raise PermissionError('Physical continuation changed its original task, seed, settings or identity')
    return row


def validate_physical_mapping(row, source, config, source_config):
    rows = canonical_rows()
    position = next((i for i, value in enumerate(rows) if value == source), None)
    return _validate_physical_mapping_at(row, source, config, source_config, position)


validate_mapping = validate_physical_mapping


def zero_request_snapshot(rows, *, path=None):
    path = Path(path or original.PREDECESSOR_ROOT/'api-budget/ledger.sqlite3').resolve()
    ids = [row['slot_id'] for row in rows]
    if len(ids) != 79 or len(set(ids)) != 79:
        raise PermissionError('Exactly 79 unique original IDs are required')
    counts = {}
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        counts['requests'] = db.execute('SELECT COUNT(*) FROM requests WHERE slot_id IN ('+
            ','.join('?' for _ in ids)+')', ids).fetchone()[0]
        args = [v for slot in ids for v in (len(slot)+1, slot+':')]
        for table in ('response_observations', 'provider_protocol_events'):
            counts[table] = db.execute('SELECT COUNT(*) FROM '+table+' WHERE '+
                ' OR '.join('substr(request_id,1,?)=?' for _ in ids), args).fetchone()[0]
    if any(counts.values()):
        raise PermissionError('Prior API request/response/protocol evidence forbids original-ID replay')
    return {'ledger': str(path), 'exact_original_ID_counts': counts, 'read_only': True}


def validate_complete_plan(plan, inventory):
    ancestor = load(reference(original.PLAN_FILE))
    if (set(ancestor)-set(plan) or plan.get('version') != VERSION
            or plan.get('root') != str(original.BATCH_ROOT)
            or plan.get('original_plan') != reference(original.PLAN_FILE)
            or plan.get('host_cpu_pool') != ancestor['host_cpu_pool']
            or plan.get('matrix') != ancestor['matrix'] or plan.get('configurations') != ancestor['configurations']
            or plan.get('continuation_inventory') != reference(INVENTORY_FILE)
            or plan.get('inventory') != reference(INVENTORY_FILE)
            or plan.get('rows') != inventory.get('rows') or len(plan.get('rows', [])) != 79
            or plan.get('remaining_generation_slots') != 79
            or plan.get('remaining_original_token_upper_bound') != TOKEN_UPPER_BOUND
            or plan.get('historical_results_preserved') is not True or plan.get('training') is not False
            or plan.get('model_calls_during_preparation') != 0):
        raise PermissionError('The complete inherited execution-plan contract differs')
    counts = dict(Counter(item['role'] for item in plan['resources'].values()))
    if (counts != {'actor':79, 'controller':79, 'volume':79, 'score':79, 'delivery_score':41}
            or plan.get('resource_role_counts') != counts
            or {r['slot_index'] for r in plan['rows']} != set(range(6090,6169))):
        raise PermissionError('Physical resources extend beyond the 79 original first model attempts')
    canonical = canonical_rows()
    by_id = {row['slot_id']:(index,row) for index,row in enumerate(canonical)}
    for row in plan['rows']:
        bound = by_id.get(row['slot_id'])
        if bound is None:
            raise PermissionError('Unexpected logical identity')
        position, source = bound
        _validate_physical_mapping_at(row, source, load(row['configuration']), load(source['configuration']), position)
        for prefix in ('actor','controller','volume','score','delivery-score'):
            old = ancestor['resources'].get(f'{prefix}-{source["slot_index"]}')
            expected = None if old is None else {**old,
                'prior_physical_slot_index': row['prior_physical_slot_index'],
                'physical_launch_attempt': row['physical_launch_attempt']}
            if plan['resources'].get(f'{prefix}-{row["slot_index"]}') != expected:
                raise PermissionError('Physical resource changed its original role, image or task')
    return plan


def require_allowed(operation='v096.run', *, slot_id=None, instance_id=None, grading_only=False):
    accepted = {'v096.run','v096.prepare','v096.api.run','v096.api.request','v089.run',
        'v089.api.run','v089.api.request','v076.run','v079.run','v088.run','v086.run','v072.api.request'} | (set(original.OPERATIONS)-{'v066.model.start','v066.control','v066.transport','v066.resolve'})
    if os.getuid()==0 or os.geteuid()==0 or operation not in accepted or grading_only and operation.endswith('request'):
        raise PermissionError('Operation outside the original zero-API continuation scope')
    if not AUTH_FILE.is_file():
        raise PermissionError('The v096 plan is prepared only; explicit runtime approval is absent')
    original.require_v066_allowed('v066.run', slot_id=slot_id, instance_id=instance_id)
    authority = load(reference(AUTH_FILE))
    if (authority.get('version')!=VERSION or authority.get('status')!='approved'
            or authority.get('source_index')!=reference(SOURCE_FILE) or authority.get('plan')!=reference(PLAN_FILE)
            or authority.get('inventory')!=reference(INVENTORY_FILE)
            or authority.get('zero_API_audit')!=require_physical_audit()
            or authority.get('historical_inventory_summary')!=reference(AUDIT_FILE)
            or authority.get('logical_first_model_attempts')!=79 or authority.get('additional_model_attempts')!=0
            or authority.get('API_cash_cap_CNY')!='1700.00' or authority.get('old_records_overwritten') is not False
            or authority.get('Qwen_lifecycle_operations')!=0):
        raise PermissionError('Original first-model-entry authorization differs')
    for item in load(authority['source_index'])['files']:
        checked(item)
    plan = validate_complete_plan(load(authority['plan']),load(reference(INVENTORY_FILE)))
    if slot_id is not None:
        row = next((r for r in plan['rows'] if r['slot_id']==slot_id),None)
        if row is None or instance_id not in (None,row['instance_id']):
            raise PermissionError('Logical identity is outside the exact 79 first entries')
    elif instance_id is not None and instance_id not in plan['environments']:
        raise PermissionError('Task is outside this continuation')
    if not grading_only:
        parent_module().require_qualified()
    if operation.endswith('request'):
        verify_host_limits()
        if not LEASE_FILE.exists() or LEASE_FILE.read_bytes()!=checked(reference(CLAIM_FILE)).read_bytes():
            raise PermissionError('No active exact first-entry manager reservation')
    return authority


def require_grading_allowed(operation='v076.run', **identity):
    if operation not in {'v076.run','v079.run','v089.run','v096.run','v066.run','v066.score',
                         'v066.delivery.score','v066.grader.create','v066.grader.start'}:
        raise PermissionError('Grading authority cannot create model actors')
    return require_allowed(operation,grading_only=True,**identity)


_namespace.update(require_allowed=require_allowed,require_grading_allowed=require_grading_allowed,
                  parent_module=parent_module,validate_mapping=validate_mapping)
