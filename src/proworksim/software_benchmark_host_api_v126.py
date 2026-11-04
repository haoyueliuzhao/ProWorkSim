"""Direct original REF execution using the explicit remaining-CNY45 cash amendment."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import threading

from . import software_benchmark_scope_v126 as scope
from .software_benchmark_deepseek_api_v122 import bind_api

from . import software_benchmark_sdk_bundle_v126 as bundle
from . import software_benchmark_sdk_bundle_v110 as original_bundle
from .software_benchmark_deepseek_adapter_v105 import HostDeepSeekTransport
from .software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_usage_metrics_v064 import normalize_usage_call

api = bind_api()

VERSION = 'v126-independent-recovery2-direct-nonthinking-host-r1'
ENDPOINT = 'http://127.0.0.1:18219'
MAX_CONCURRENCY = 16
TOKENIZER = scope.ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
SCHEMAS = scope.API_ROOT/'api-runtime/tool-schemas.json'
IDENTITY = scope.API_ROOT/'api-runtime/identity.json'
QUALIFICATION_ROOT = scope.ROOT/'runs/software-benchmark-v111/aligned-interface-r1/api-qualification'
QUALIFICATION = QUALIFICATION_ROOT/'result.json'
NEUTRAL_SLOT, NEUTRAL_CONDITION = 'v111:neutral:aligned-tools:r1', 'v111-API-PREPARATION'


def _names(tools):
    names = [tool['function']['name'] for tool in tools]
    if len(names) != len(set(names)) or any(tool.get('type') != 'function' for tool in tools):
        raise ValueError('Only distinct original local function tools are admitted')
    return sorted(names)


def _wire_tools(path):
    value = json.loads(Path(path).read_bytes())
    if isinstance(value, dict):
        value = value.get('request', value)
        value = value.get('tools', value)
    if not isinstance(value, list):
        raise ValueError('A recorded actual SDK tool list is required')
    _names(value)
    return value


def prepare_schemas(*, native_wire=None):
    """Reuse the exact original REF SDK schema, entirely offline."""
    original = scope.load(reference(QUALIFICATION))
    previous = scope.load(original['schema_inventory'])
    recorded = checked(previous['native_actual_wire'])
    native_wire = Path(native_wire or recorded)
    manifest_ref = reference(bundle.OUTPUT/'manifest.json')
    manifest = scope.load(manifest_ref)
    native = _wire_tools(native_wire)
    if (manifest.get('version') != bundle.VERSION
            or manifest.get('probe', {}).get('all_controller_and_worker_entrypoints_imported') is not True
            or previous.get('native_bundle') != reference(original_bundle.OUTPUT/'manifest.json')
            or manifest.get('probe', {}).get('native_rejected_history_revision') != 'v114-native-source-bound-rejected-tool-history-r1'
            or manifest.get('probe', {}).get('original_v110_model_visible_strategy_retained') is not True
            or native != previous.get('schemas', {}).get('REF')
            or set(_names(native)) != {'file_editor', 'finish', 'task_tracker', 'terminal', 'think'}):
        raise ValueError('The preserved REF runtime or actual SDK schema changed')
    return scope.retain(SCHEMAS, {'version': VERSION, 'native_bundle': manifest_ref,
        'original_native_bundle': previous['native_bundle'],
        'deployment_change': 'trusted rejected-call history only; original visible REF schema retained',
        'native_actual_wire': reference(native_wire), 'original_schema_inventory': original['schema_inventory'],
        'schemas': {'REF': native}, 'tool_names': {'REF': _names(native)},
        'schema_scope': 'original REF SDK functions; no PROJECT route or provider search',
        'server_search': False, 'host_listener': False})


@contextmanager
def ledger_read():
    if not scope.LEDGER_FILE.exists():
        raise FileNotFoundError('Authorized v118 cash ledger is not initialized')
    db = sqlite3.connect(scope.LEDGER_FILE.as_uri()+'?mode=ro', uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        policy = db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()
        if policy is None or json.loads(policy[0]) != {**api.POLICY, 'max_concurrency': MAX_CONCURRENCY}:
            raise ValueError('The authorized cumulative cash ledger policy changed')
        yield db
    finally:
        db.close()


def usage(slot_id, condition):
    if not scope.LEDGER_FILE.exists():
        return {'calls': [], 'unresolved_calls': [], 'usage_capture_complete': False}
    with ledger_read() as db:
        rows = [dict(row) for row in db.execute('SELECT * FROM requests WHERE slot_id=? ORDER BY request_id', (slot_id,))]
    calls, unknown = [], []
    for row in rows:
        if row['condition'] != condition:
            raise ValueError('Usage belongs to another frozen condition')
        if row['usage_json'] is not None and row['settled_nanoyuan'] is not None:
            value = json.loads(row['usage_json'])
            calls.append(normalize_usage_call(row['request_id'], row['usage_id'], value,
                accounted_cost_cny=str(row['settled_nanoyuan']/api.NANOYUAN)))
        else:
            unknown.append({'call_id': row['request_id'], 'purpose': row['usage_id'],
                'reserved_tokens': row['prompt_upper_bound']+row['max_output_tokens'],
                'reserved_cost_cny': str(row['reserved_nanoyuan']/api.NANOYUAN),
                'reservation_is_actual_usage': False, 'status': row['status']})
    return {'calls': calls, 'unresolved_calls': unknown, 'usage_capture_complete': not unknown,
            'usage_source': 'v118_authoritative_provider_ledger',
            'known_withheld_response_usage_included': True}


def budget_status():
    if not scope.LEDGER_FILE.exists():
        return {'state': 'qualification_pending', 'can_start_generation': False, 'temporary_wait': True}
    with ledger_read() as db:
        totals = api.BudgetLedger._totals(db)
        halt = db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
        cooldown = db.execute("SELECT value FROM metadata WHERE name='cooldown_until_utc'").fetchone()
    remaining = api.CAP_NANOYUAN-totals['committed']
    waits = api.transport.cooldown_state(cooldown[0] if cooldown else None)
    state = 'ready'
    if halt or remaining < 0:
        state = 'shared_halted'
    elif remaining < api.ABSOLUTE_RESERVATION_NANOYUAN:
        state = 'waiting_inflight_cash' if totals['inflight'] else 'cash_exhausted'
    elif (totals['inflight'] or 0) >= MAX_CONCURRENCY:
        state = 'waiting_concurrency'
    elif waits['admission_wait_seconds'] > 0:
        state = 'waiting_cooldown'
    elif not QUALIFICATION.exists():
        state = 'qualification_pending'
    elif scope.load(reference(QUALIFICATION)).get('passed') is not True:
        state = 'qualification_failed'
    return {'version': VERSION, 'state': state, 'can_start_generation': state == 'ready',
        'temporary_wait': state.startswith('waiting_') or state == 'qualification_pending',
        'reason': halt[0] if halt else None, 'cap_CNY': scope.CASH_CAP_CNY,
        'remaining_CNY': str(remaining/api.NANOYUAN),
        'settled_upper_CNY': str(totals['settled']/api.NANOYUAN),
        'uncertain_reserved_CNY': str(totals['uncertain']/api.NANOYUAN),
        'committed_upper_CNY': str(totals['committed']/api.NANOYUAN),
        'inflight_count': totals['inflight'] or 0, 'attempts': totals['attempts'],
        'ledger_path': str(scope.LEDGER_FILE), **waits}


def neutral_request(arm, schemas):
    if arm != 'REF':
        raise ValueError('Only the original REF qualification can be reused')
    name = 'finish'
    tool = next(item for item in schemas['schemas'][arm] if item['function']['name'] == name)
    arguments = {'message': 'pws-v111-neutral', 'security_risk': 'LOW'}
    return {'model': api.MODEL, 'stream': False, 'thinking': {'type': 'disabled'},
        'temperature': 1.0, 'top_p': 1.0, 'max_tokens': 1024,
        'user_id': api.slot_user_id(NEUTRAL_SLOT, NEUTRAL_CONDITION), 'tool_choice': 'auto',
        'messages': [{'role': 'user', 'content':
            'Neutral API schema check only; no benchmark task or actual repository exists. '
            'No requested tool will execute. Call ' + name + ' exactly once using these exact JSON arguments: '
            + json.dumps(arguments, ensure_ascii=False) + '. Do not search, run tests or invent results.'}],
        'tools': [tool]}, name, arguments


def qualify(client, counter, schemas):
    """Validate the settled original REF proof; there is no new-call path."""
    scope.require_allowed('v126.api.request')
    value = scope.load(reference(QUALIFICATION))
    original = scope.load(value['schema_inventory'])
    calls = [call for call in value.get('calls', []) if call.get('arm') == 'REF']
    if (value.get('passed') is not True or value.get('thinking') is not False
            or value.get('tools_executed') != 0 or value.get('benchmark_tasks_used') != 0
            or len(calls) != 1 or set(schemas['schemas']) != {'REF'}
            or original.get('schemas', {}).get('REF') != schemas['schemas']['REF']
            or original.get('tool_names', {}).get('REF') != schemas['tool_names']['REF']):
        raise ValueError('The original REF schema qualification cannot be reused')
    call = calls[0]
    wire, _name, _arguments = neutral_request('REF', schemas)
    response = scope.load(call['response'])
    if scope.load(call['request']).get('wire') != wire:
        raise ValueError('The original neutral REF request changed')
    with ledger_read() as db:
        record = db.execute('SELECT * FROM requests WHERE request_id=?',
                            (NEUTRAL_SLOT+':0001',)).fetchone()
    if (record is None or record['slot_id'] != NEUTRAL_SLOT
            or record['condition'] != NEUTRAL_CONDITION or record['usage_id'] != 'preparation'
            or record['status'] != 'settled' or record['settled_nanoyuan'] is None
            or record['response_id'] != response.get('id') or record['usage_json'] is None
            or json.loads(record['usage_json']).get('total_tokens') != call['usage']['total_tokens']):
        raise ValueError('The original REF neutral proof lacks its exact settled ledger record')
    proof = {'version': VERSION, 'passed': True, 'prior_qualification': reference(QUALIFICATION),
        'REF_call': call, 'current_schema_inventory': reference(SCHEMAS),
        'exact_REF_tool_schemas_equal': True, 'original_neutral_slot': NEUTRAL_SLOT,
        'original_REF_tokens': call['usage']['total_tokens'], 'new_API_calls': 0,
        'other_arm_qualification_repeated': False}
    scope.retain(scope.API_ROOT/'api-runtime/qualification-reuse.json', proof)
    return proof


class DeepSeekRuntime:
    def __init__(self):
        self.client = self.counter = self.qualified = None
        self.rows = self.schemas = None
        self._transports, self._lock = [], threading.Lock()

    def initialize_for_run(self):
        scope.require_allowed('v126.api.request')
        if self.client is not None:
            return self.logical_resident()
        prepare_schemas()
        self.schemas = scope.load(reference(SCHEMAS))
        plan = scope.load(reference(scope.PLAN_FILE))
        scope.validate_plan(plan)
        self.rows = {r['slot_id']: r for r in plan['rows']}
        if {r['arm'] for r in self.rows.values()} != {'REF'}:
            raise ValueError('Only the new REF attempts may use this runtime')
        self.qualified = qualify(None, None, self.schemas)
        names = set(self.schemas['tool_names']['REF'])
        self.client = api.DeepSeekClient(ledger_path=scope.LEDGER_FILE,
            api_key=api.load_api_key(scope.ROOT/'.env'), allowed_tool_names=names,
            max_concurrency=MAX_CONCURRENCY)
        token_ref = reference(TOKENIZER)
        self.counter = OfficialDeepSeekCounter(token_ref['path'], manifest_sha256=token_ref['sha256'],
                                               reservation_margin_tokens=128)
        return self.logical_resident()

    def logical_resident(self):
        if self.qualified is None or self.qualified.get('passed') is not True:
            raise ValueError('Trustworthy nonthinking API admission is required')
        identity = {'version': VERSION, 'model_key': 'DEEPSEEK', 'model': api.MODEL,
            'model_revision': api.DOCUMENTED_MODEL_VERSION, 'documented_model_version': api.DOCUMENTED_MODEL_VERSION,
            'provider_weight_revision_pinnable': False, 'project_training_adapter_loaded': False,
            'context_limit': api.CONTEXT_TOKENS, 'max_output_tokens': api.MAX_OUTPUT_TOKENS,
            'thinking': False, 'service_admission_complete': True, 'port': 18219,
            'endpoint': ENDPOINT, 'host_listener': False, 'deployment_version': VERSION,
            'qualification': reference(QUALIFICATION), 'tool_schema_inventory': reference(SCHEMAS),
            'ledger_path': str(scope.LEDGER_FILE), 'cash_cap_CNY': scope.CASH_CAP_CNY}
        ref = scope.retain(IDENTITY, identity)
        return {'model_key': 'DEEPSEEK', 'endpoint': ENDPOINT, 'api_key_file': None,
                'identity': ref, 'identity_value': identity, 'directory': str(IDENTITY.parent),
                'logical_only_no_listener': True}

    def transport_factory(self, row, output):
        if self.rows is None or self.rows.get(row.get('slot_id')) != row:
            raise ValueError('Unsealed generation row')
        from .software_benchmark_alignment_contract_v110 import validate_plan_identity
        validate_plan_identity(row)
        if row['arm'] != 'REF':
            raise ValueError('PROJECT is outside this REF-only deployment')
        allowed = {item['function']['name']: item for item in self.schemas['schemas'][row['arm']]}
        def authorize(payload):
            scope.require_allowed('v126.api.request', slot_id=row['slot_id'], instance_id=row['instance_id'])
            prefix = row['slot_id']+':'
            suffix = payload.get('request_id', '').removeprefix(prefix)
            if (payload.get('slot_id') != row['slot_id'] or payload.get('condition') != row['condition_id']
                    or not payload.get('request_id', '').startswith(prefix)
                    or len(suffix) != 4 or not suffix.isdigit() or not 1 <= int(suffix) <= 512
                    or type(payload['wire'].get('max_tokens')) is not int
                    or not 0 < payload['wire']['max_tokens'] <= 32768):
                raise ValueError('Broker request changed its row, sequence or actual output cap')
            tools = payload['wire'].get('tools', [])
            if ((payload['usage_id'] == 'agent' and {item['function']['name']: item for item in tools} != allowed)
                    or (payload['usage_id'] == 'condenser' and tools)):
                raise ValueError('Agent or condenser tool inventory changed')
            if payload.get('usage_id') not in {'agent', 'condenser'}:
                raise ValueError('No unplanned model use is allowed')
            return {'condition_id': row['condition_id'], 'token_budget': 5_000_000}
        value = HostDeepSeekTransport(client=self.client, counter=self.counter,
            metadata_dir=Path(output)/'host-api-counts', authorize=authorize,
            slot_id=row['slot_id'], condition_id=row['condition_id'])
        with self._lock:
            self._transports.append(value)
        return value

    def cancel_all(self):
        with self._lock:
            values = list(self._transports)
        for value in values:
            value.abort()

    def settled_route_witnesses(self):
        """Read this panel's first paid responses, without waiting for episode end."""
        if not self.rows or not scope.LEDGER_FILE.exists():
            return {}
        slots = list(self.rows)
        with ledger_read() as db:
            rows = db.execute('SELECT DISTINCT slot_id,condition FROM requests '
                "WHERE status='settled' AND usage_json IS NOT NULL AND settled_nanoyuan IS NOT NULL "
                "AND usage_id IN ('agent','condenser') AND slot_id IN ("
                + ','.join('?' for _ in slots) + ')', slots).fetchall()
        witnessed = {}
        for record in rows:
            planned = self.rows[record['slot_id']]
            if record['condition'] != planned['condition_id']:
                raise ValueError('A paid response witness belongs to another frozen condition')
            witnessed[planned['arm']] = record['slot_id']
        return witnessed

    @staticmethod
    def usage_for_slot(row):
        from .software_benchmark_alignment_contract_v110 import validate_plan_identity
        validate_plan_identity(row)
        if row['arm'] != 'REF':
            raise ValueError('PROJECT is outside this REF-only deployment')
        return usage(row['slot_id'], row['condition_id'])

    budget_status = staticmethod(budget_status)
    preparation_usage = staticmethod(lambda: {'calls': [], 'unresolved_calls': [],
        'usage_capture_complete': True, 'new_preparation_API_calls': 0,
        'reused_qualification': reference(QUALIFICATION)})


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Extract frozen actual tool schemas, offline only')
    parser.add_argument('--prepare-schemas', action='store_true', required=True)
    parser.add_argument('--native-wire', type=Path)
    arguments = parser.parse_args()
    print(json.dumps(prepare_schemas(native_wire=arguments.native_wire), ensure_ascii=False))
