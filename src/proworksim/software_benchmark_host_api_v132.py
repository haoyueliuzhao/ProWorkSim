"""Continue only completely unused v131 teams with original schemas and cash.

All old request identities and settled/uncertain reservations are retained.
The stopped-owner/continuation scope is authoritative; no neutral call is made.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace

from . import software_benchmark_scope_v132 as scope
from .software_benchmark_alignment_contract_v131 import GROUP_IDS, condition, validate_plan_identity
from .software_benchmark_deepseek_api_v131 import group_api, PRICING, MAX_PROFILE_RESERVATION_NANOYUAN
from .software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from .software_benchmark_deepseek_prefix_v055_r2 import pending_tail_tool_ids, count_incomplete_prefix
from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_usage_metrics_v064 import normalize_usage_call
from .storage import digest, json_bytes

VERSION = 'v132-unused-team-continuation-direct-host-r1'
SCHEMAS = scope.BATCH_ROOT/'api-coordinator/api-runtime/member-tool-schemas-r2.json'
RUNTIME_BINDING = scope.API_ROOT/'api-runtime/member-schema-bundle-binding.json'
TOKENIZER = scope.ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
ENDPOINT = 'http://127.0.0.1:18219'


@lru_cache(maxsize=5)
def api_for(group):
    return group_api(group, scope.LEDGER_FILES[group], max_concurrency=scope.MAX_GENERATIONS)


def prepare_schemas(inventory_path=None):
    """Bind the streamed-hash deployment to unchanged original member tools."""
    from . import software_benchmark_sdk_bundle_v131 as original_bundle
    from . import software_benchmark_sdk_bundle_v132 as bundle
    prior = scope.load(reference(SCHEMAS))
    recorded = checked(prior['actual_member_inventory'])
    if inventory_path is not None and reference(inventory_path) != reference(recorded):
        raise ValueError('A continuation cannot replace the original actual SDK schemas')
    inventory_path = recorded
    inventory_ref = reference(inventory_path)
    inventory = scope.load(inventory_ref)
    schemas = inventory.get('schemas', {})
    if set(schemas) != set(GROUP_IDS):
        raise ValueError('The actual schema inventory must contain all five fixed groups')
    for group, members in schemas.items():
        if set(members) != set(condition(group)['fixed_members']):
            raise ValueError('Tool schemas do not match the fixed member registry')
        for member, tools in members.items():
            names = [item.get('function', {}).get('name') for item in tools]
            if (not tools or len(names) != len(set(names)) or None in names
                    or any(item.get('type') != 'function' for item in tools)
                    or any(name in names for name in ('terminal', 'web_search', 'browser', 'fetch'))):
                raise ValueError('Only the actual member managed function schemas are allowed')
    bundle_ref = reference(bundle.OUTPUT/'manifest.json')
    manifest = scope.load(bundle_ref)
    schema_sha = hashlib.sha256(json.dumps(schemas, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    probe = manifest.get('probe', {})
    if (manifest.get('version') != bundle.VERSION
            or prior.get('runtime_bundle') != reference(original_bundle.OUTPUT/'manifest.json')
            or prior.get('schemas') != schemas or prior.get('pricing_verified') != PRICING
            or prior.get('neutral_calls') != 0
            or probe.get('original_member_schemas_unchanged') is not True
            or probe.get('initial_business_state_hash_streamed') is not True
            or probe.get('member_schema_sha256') != schema_sha):
        raise ValueError('The actual fixed-organization runtime bundle changed')
    return scope.retain(RUNTIME_BINDING, {'version': VERSION, 'original_schema_inventory': reference(SCHEMAS),
        'actual_member_inventory': inventory_ref, 'original_runtime_bundle': prior['runtime_bundle'],
        'runtime_bundle': bundle_ref, 'schemas': schemas, 'member_schema_sha256': schema_sha,
        'pricing_verified': PRICING, 'neutral_calls': 0, 'model_visible_strategy_unchanged': True,
        'deployment_change': 'Same initial-state digest streamed without full hex/JSON copies',
        'provider_search_or_fetch': False, 'host_listener': False})


@contextmanager
def ledger_read(group):
    api = api_for(group)
    path = Path(scope.LEDGER_FILES[group])
    db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        policy = db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()
        if policy is None or json.loads(policy[0]) != {**api.POLICY, 'max_concurrency': scope.MAX_GENERATIONS}:
            raise ValueError('The independent organization ledger policy changed')
        yield db
    finally:
        db.close()


def budget_status(group):
    api = api_for(group)
    if not Path(scope.LEDGER_FILES[group]).exists():
        return {'group_id': group, 'state': 'qualification_pending', 'can_start_generation': False,
                'temporary_wait': True, 'cap_CNY': '100.00'}
    with ledger_read(group) as db:
        totals = api.BudgetLedger._totals(db)
        halt = db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
        cooldown = db.execute("SELECT value FROM metadata WHERE name='cooldown_until_utc'").fetchone()
    remaining = api.CAP_NANOYUAN-totals['committed']
    waiting = api.transport.cooldown_state(cooldown[0] if cooldown else None)
    state = 'ready'
    if halt or remaining < 0:
        state = 'shared_halted'  # This runtime view is one organization only.
    elif remaining < MAX_PROFILE_RESERVATION_NANOYUAN:
        state = 'waiting_inflight_cash' if totals['inflight'] else 'cash_exhausted'
    elif (totals['inflight'] or 0) >= scope.MAX_GENERATIONS:
        state = 'waiting_concurrency'
    elif waiting['admission_wait_seconds'] > 0:
        state = 'waiting_cooldown'
    return {'version': VERSION, 'group_id': group, 'state': state,
        'can_start_generation': state == 'ready', 'temporary_wait': state.startswith('waiting_'),
        'reason': halt[0] if halt else None,
        'bounded_uncertain_requests_isolated_to_their_teams': True,
        'cap_CNY': '100.00', 'remaining_CNY': str(remaining/api.NANOYUAN),
        'settled_upper_CNY': str(totals['settled']/api.NANOYUAN),
        'uncertain_reserved_CNY': str(totals['uncertain']/api.NANOYUAN),
        'committed_upper_CNY': str(totals['committed']/api.NANOYUAN),
        'inflight_count': totals['inflight'] or 0, 'attempts': totals['attempts'],
        'new_team_admission_reservation_CNY': str(MAX_PROFILE_RESERVATION_NANOYUAN/api.NANOYUAN),
        'existing_team_requests_use_actual_request_reservation': True,
        'ledger_path': str(scope.LEDGER_FILES[group]), **waiting}


def ledger_witness(group):
    """A read-only complete pre-handoff request/accounting fingerprint."""
    with ledger_read(group) as db:
        rows = [dict(row) for row in db.execute(
            'SELECT r.*,m.group_id,m.member_id FROM requests r LEFT JOIN member_requests m USING(request_id) '
            'ORDER BY r.request_id')]
        policy = json.loads(db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0])
        totals = api_for(group).BudgetLedger._totals(db)
    return {'group_id': group, 'ledger_path': str(scope.LEDGER_FILES[group]),
        'policy_sha256': digest(json_bytes(policy)), 'request_count': len(rows),
        'requests_sha256': digest(json_bytes(rows)), 'totals': totals}


def validate_fresh_rows(value, *, check_unused=True):
    original = {row['slot_id']: row for row in scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))['rows']}
    rows = value.get('eligible_first_generation', [])
    if (len({row['slot_id'] for row in rows}) != len(rows)
            or any(original.get(row['slot_id']) != row for row in rows)):
        raise ValueError('Continuation changed an original task, seed or member roster')
    for row in rows:
        validate_plan_identity(row)
        if check_unused and not scope.never_consumed(row):
            raise ValueError('A consumed request, object claim or original episode cannot be replayed')
    return rows


def usage_for_slot(row):
    validate_plan_identity(row)
    group = row['organization_id']
    with ledger_read(group) as db:
        records = [dict(record) for record in db.execute(
            'SELECT r.*,m.group_id,m.member_id FROM requests r LEFT JOIN member_requests m USING(request_id) '
            'WHERE slot_id=? ORDER BY request_id', (row['slot_id'],))]
    calls, unknown = [], []
    for record in records:
        if (record['condition'] != row['condition_id'] or record['group_id'] != group
                or record['member_id'] not in row['fixed_members']):
            raise ValueError('Provider usage lost its original team/member attribution')
        if record['status'] == 'settled' and record['usage_json'] is not None:
            value = normalize_usage_call(record['request_id'], record['usage_id'], json.loads(record['usage_json']),
                accounted_cost_cny=str(record['settled_nanoyuan']/1e9))
            calls.append({**value, 'member_id': record['member_id'], 'organization_id': group})
        else:
            unknown.append({'call_id': record['request_id'], 'member_id': record['member_id'],
                'purpose': record['usage_id'], 'reserved_tokens': record['prompt_upper_bound']+record['max_output_tokens'],
                'reserved_cost_cny': str(record['reserved_nanoyuan']/1e9),
                'reservation_is_actual_usage': False, 'status': record['status']})
    return {'calls': calls, 'unresolved_calls': unknown, 'usage_capture_complete': not unknown,
            'usage_source': 'v131_independent_group_provider_ledger', 'team_pool_not_per_member': True}


class HostTeamTransport:
    port, timeout_seconds = 18219, 1800

    def __init__(self, runtime, row, output):
        self.runtime, self.row = runtime, copy.deepcopy(row)
        self.slot_id, self.condition_id = row['slot_id'], row['condition_id']
        self.group = row['organization_id']
        self.client = runtime.clients[self.group].fork_for_episode()
        self.folder = Path(output)/'host-api-counts'
        self.folder.mkdir(parents=True, exist_ok=True)
        self._lock, self.cancelled = threading.RLock(), threading.Event()

    def validate_identity(self, slot_id):
        if slot_id != self.slot_id:
            raise ValueError('A broker cannot leave its fixed team')

    def abort(self):
        self.cancelled.set()
        self.client.transport.abort()

    def post(self, path, payload):
        api = api_for(self.group)
        if path not in {'/tokenize', '/tokenize-prefix', '/chat/completions'}:
            raise ValueError('No search, fetch, arbitrary URL or provider tool route')
        member = payload.get('member_id')
        if payload.get('team_slot_id') != self.slot_id or member not in self.row['fixed_members']:
            raise ValueError('Every count and generation request needs its original member identity')
        wire = payload['wire']
        if wire.get('user_id') != api.slot_user_id(self.slot_id+':'+member, self.condition_id):
            raise ValueError('Member cache identity changed')
        api.validate_payload(wire, self.client.allowed_tool_names)
        expected_tools = {item['function']['name']: item for item in self.runtime.schemas[self.group][member]}
        supplied = {item['function']['name']: item for item in wire.get('tools', [])}
        if supplied and supplied != expected_tools:
            raise ValueError('An agent cannot use another member tool schema')
        common = {'wire', 'member_id', 'team_slot_id'}
        with self._lock:
            if self.cancelled.is_set():
                raise api.PreDispatchBudgetStopped('owned_team_transport_stopped_before_dispatch')
            if path == '/tokenize':
                if set(payload) != common:
                    raise ValueError('Unexpected member count extension')
                return self.runtime.counter(wire)
            if path == '/tokenize-prefix':
                if set(payload) != common|{'pending_ids'}:
                    raise ValueError('Unexpected member prefix extension')
                pending = tuple(payload['pending_ids'])
                if not pending or pending_tail_tool_ids(wire['messages']) != pending:
                    raise ValueError('Only the original unfinished SDK tool tail can be counted')
                (self.folder/member).mkdir(parents=True, exist_ok=True)
                value = count_incomplete_prefix(SimpleNamespace(counter=self.runtime.counter,
                    folder=self.folder/member), wire, pending)
                return {'prompt_tokens': value, 'request_sha256': digest(json_bytes(wire)),
                    'method': 'official_original_member_incomplete_prefix', 'count_only_not_dispatchable': True,
                    'exact_provider_token_ids_available': False}
            expected = common|{'request_id', 'slot_id', 'condition', 'usage_id', 'prompt_upper_bound'}
            if (set(payload) != expected or payload['slot_id'] != self.slot_id
                    or payload['condition'] != self.condition_id
                    or payload['usage_id'] not in {'agent', 'condenser'}
                    or payload['usage_id'] == 'agent' and supplied != expected_tools
                    or payload['usage_id'] == 'condenser' and supplied):
                raise ValueError('The team/member use category or actual tool inventory changed')
            scope.require_allowed('v131.api.request', slot_id=self.slot_id, instance_id=self.row['instance_id'])
            measured = self.runtime.counter(wire)
            if (measured['request_sha256'] != digest(json_bytes(wire))
                    or measured['prompt_tokens'] != payload['prompt_upper_bound']):
                raise ValueError('Controller and host original-member token reservations differ')
            waiting_deadline = time.monotonic()+self.timeout_seconds
            while True:
                while not self.runtime.http_slots.acquire(timeout=.2):
                    if self.cancelled.is_set():
                        raise api.PreDispatchBudgetStopped('owned_team_cancelled_while_waiting_for_HTTP')
                    if time.monotonic() >= waiting_deadline:
                        raise api.PreDispatchConcurrencyBusy('HTTP_admission_wait_deadline_before_dispatch')
                try:
                    if self.cancelled.is_set():
                        raise api.PreDispatchBudgetStopped('owned_team_cancelled_before_HTTP')
                    return self.client.complete(wire, **{key: value for key, value in payload.items()
                        if key not in {'wire', 'team_slot_id'}})
                except api.PreDispatchConcurrencyBusy:
                    # This exact class can only leave the cash reservation step,
                    # before HTTP. An uncertain sent request is never retried.
                    if time.monotonic() >= waiting_deadline:
                        raise
                finally:
                    self.runtime.http_slots.release()
                if self.cancelled.wait(.2):
                    raise api.PreDispatchBudgetStopped('owned_team_cancelled_during_cash_admission_wait')


class DeepSeekRuntime:
    def __init__(self):
        self.clients, self.rows, self.schemas = {}, {}, {}
        self.counter = None
        self.http_slots = threading.BoundedSemaphore(scope.MAX_GENERATIONS)
        self.transports, self.lock = [], threading.Lock()
        self.continuation_rows, self.issued_slots = {}, set()

    def initialize_for_run(self):
        scope.require_allowed('v132.api.request')
        plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
        self.rows = {row['slot_id']: row for row in plan['rows']}
        continuation = scope.continuation()
        self.continuation_rows = {row['slot_id']: row for row in validate_fresh_rows(continuation)}
        inventory = scope.load(prepare_schemas())
        self.schemas = inventory['schemas']
        token_ref = reference(TOKENIZER)
        self.counter = OfficialDeepSeekCounter(token_ref['path'], manifest_sha256=token_ref['sha256'],
                                               reservation_margin_tokens=128)
        for group in GROUP_IDS:
            api = api_for(group)
            witness = ledger_witness(group)
            if (continuation['ledger_baseline'].get(group) != witness
                    or (witness['totals']['inflight'] or 0) != 0):
                raise ValueError('The original ledger changed or retains a live request after handoff')
            names = {item['function']['name'] for tools in self.schemas[group].values() for item in tools}
            self.clients[group] = api.DeepSeekClient(ledger_path=scope.LEDGER_FILES[group],
                api_key=api.load_api_key(scope.ROOT/'.env'), allowed_tool_names=names,
                max_concurrency=scope.MAX_GENERATIONS)
        return self

    def for_group(self, group):
        if group not in GROUP_IDS:
            raise ValueError('Unknown fixed organization')
        return GroupView(self, group)

    def transport_factory(self, row, output):
        validate_plan_identity(row)
        with self.lock:
            if self.continuation_rows.get(row['slot_id']) != row or row['slot_id'] in self.issued_slots:
                raise ValueError('Only one new host route is allowed for an originally unused team')
            with ledger_read(row['organization_id']) as db:
                if db.execute('SELECT 1 FROM requests WHERE slot_id=? LIMIT 1', (row['slot_id'],)).fetchone():
                    raise ValueError('A team with any historical provider request cannot be replayed')
            route = HostTeamTransport(self, row, output)
            self.issued_slots.add(row['slot_id'])
            self.transports.append(route)
        return route

    def cancel_group(self, group):
        with self.lock:
            routes = [route for route in self.transports if route.group == group]
        for route in routes:
            route.abort()

    def cancel_all(self):
        for group in GROUP_IDS:
            self.cancel_group(group)


class GroupView:
    def __init__(self, runtime, group):
        self.runtime, self.group = runtime, group

    def budget_status(self):
        return budget_status(self.group)

    def logical_resident(self):
        identity = {'version': VERSION, 'model_key': 'DEEPSEEK', 'model': PRICING['model'],
            'model_revision': PRICING['documented_model_version'], 'documented_model_version': PRICING['documented_model_version'],
            'provider_weight_revision_pinnable': False, 'project_training_adapter_loaded': False,
            'context_limit': 131072, 'max_output_tokens': 32768, 'thinking': False,
            'service_admission_complete': True, 'port': 18219, 'endpoint': ENDPOINT,
            'host_listener': False, 'deployment_version': VERSION, 'organization_id': self.group,
            'tool_schema_inventory': reference(SCHEMAS), 'ledger_path': str(scope.LEDGER_FILES[self.group]),
            'cash_cap_CNY': '100.00', 'new_neutral_calls': 0,
            'provider_health_qualification': 'first_formal_settled_response_not_assumed_prevalidated'}
        identity['original_formal_route_witness'] = self.settled_route_witnesses()
        identity['existing_independent_cash_ledger_preserved'] = True
        identity['runtime_schema_binding'] = reference(RUNTIME_BINDING)
        path = scope.API_ROOT/'api-runtime'/self.group/'identity.json'
        ref = scope.retain(path, identity)
        return {'model_key': 'DEEPSEEK', 'endpoint': ENDPOINT, 'api_key_file': None,
            'identity': ref, 'identity_value': identity, 'directory': str(path.parent),
            'logical_only_no_listener': True}

    def transport_factory(self, row, output):
        if row['organization_id'] != self.group:
            raise ValueError('A group view cannot dispatch another organization')
        return self.runtime.transport_factory(row, output)

    def cancel_all(self):
        self.runtime.cancel_group(self.group)

    def settled_route_witnesses(self):
        rows = {slot: row for slot, row in self.runtime.rows.items() if row['organization_id'] == self.group}
        with ledger_read(self.group) as db:
            records = db.execute("SELECT slot_id,condition FROM requests r WHERE status='settled' "
                "AND usage_json IS NOT NULL AND NOT EXISTS (SELECT 1 FROM provider_protocol_events p "
                "WHERE p.request_id=r.request_id)").fetchall()
        for record in records:
            row = rows.get(record['slot_id'])
            if row and record['condition'] == row['condition_id']:
                return {'PROJECT': row['slot_id']}
        return {}

    usage_for_slot = staticmethod(usage_for_slot)
    preparation_usage = staticmethod(lambda: {'calls': [], 'unresolved_calls': [],
        'usage_capture_complete': True, 'new_preparation_API_calls': 0})


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Freeze actual team/member schemas offline')
    parser.add_argument('--prepare-schemas', action='store_true', required=True)
    parser.add_argument('--schema-inventory', type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare_schemas(args.schema_inventory), ensure_ascii=False))
