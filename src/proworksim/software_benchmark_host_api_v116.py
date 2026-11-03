"""Direct nonthinking v110 execution under the separately authorized v111 ledger."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import threading

from . import software_benchmark_scope_v116 as scope
from . import software_benchmark_deepseek_api_v105 as api
from . import software_benchmark_sdk_bundle_v110 as bundle
from .software_benchmark_deepseek_adapter_v105 import HostDeepSeekTransport
from .software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_usage_metrics_v064 import normalize_usage_call

VERSION = 'v116-four-uncalled-requests-qualified-host-r1'
ENDPOINT = 'http://127.0.0.1:18219'
MAX_CONCURRENCY = 16
TOKENIZER = scope.ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
SCHEMAS = scope.API_ROOT/'api-runtime/tool-schemas.json'
IDENTITY = scope.API_ROOT/'api-runtime/identity.json'
QUALIFICATION_ROOT = scope.BATCH_ROOT/'api-qualification'
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


def prepare_schemas(*, native_wire=None, project_wire=None):
    """Read-only schema extraction; no SDK, provider call or container is started."""
    from .software_benchmark_finish_review_v110 import DONE_DESCRIPTION
    from .software_benchmark_public_tests_v110 import SELECTION_SCHEMA
    if SCHEMAS.exists() and native_wire is None and project_wire is None:
        existing = scope.load(reference(SCHEMAS))
        native_wire = checked(existing['native_actual_wire'])
        project_wire = checked(existing['project_actual_wire'])
    native_wire = Path(native_wire or scope.ROOT/'artifacts/software-benchmark-v105/nonthinking-sdk-control-r1/native-tool-schemas.json')
    project_wire = Path(project_wire or scope.ROOT/'runs/software-benchmark-v110/cpu-controls/combined-05/ledger/request-0001.json')
    manifest_ref = reference(bundle.OUTPUT/'manifest.json')
    manifest = scope.load(manifest_ref)
    if (manifest.get('version') != bundle.VERSION
            or manifest.get('probe', {}).get('all_controller_and_worker_entrypoints_imported') is not True):
        raise ValueError('The exact aligned runtime bundle must be prepared first')
    native, project = _wire_tools(native_wire), _wire_tools(project_wire)
    if set(_names(native)) != {'file_editor', 'finish', 'task_tracker', 'terminal', 'think'}:
        raise ValueError('The preserved native SDK schema family changed')
    mapped = {item['function']['name']: item['function'] for item in project}
    if (mapped.get('staff_done', {}).get('description') != DONE_DESCRIPTION
            or mapped.get('run_tests', {}).get('parameters') != {
                'type': 'object', 'properties': {'selection': SELECTION_SCHEMA},
                'required': [], 'additionalProperties': False}
            or any(name in mapped for name in ('send_message', 'handoff_patch', 'offer_transfer',
                                              'accept_transfer', 'decline_transfer'))):
        raise ValueError('PROJECT requires the actual v110 single-agent review/selection schemas')
    return scope.retain(SCHEMAS, {'version': VERSION, 'native_bundle': manifest_ref,
        'native_actual_wire': reference(native_wire), 'project_actual_wire': reference(project_wire),
        'native_tool_schemas_unchanged_from_pinned_SDK': True,
        'project_tool_definition_source': reference(scope.ROOT/'src/proworksim/software_benchmark_public_test_world_v110.py'),
        'schema_scope': 'actual function definitions; no provider search or tool execution in preparation',
        'schemas': {'REF': native, 'PROJECT': project},
        'tool_names': {'REF': _names(native), 'PROJECT': _names(project)},
        'server_search': False, 'host_listener': False})


@contextmanager
def ledger_read():
    if not scope.LEDGER_FILE.exists():
        raise FileNotFoundError('Authorized v111 cash ledger is not initialized')
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
            'usage_source': 'v111_authoritative_provider_ledger',
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


def qualify(client, counter, schemas):
    """Reuse the immutable passed admission only; no neutral or metadata call."""
    authority = scope.require_allowed('v116.api.request')
    expected = authority['API_qualification']
    if expected != reference(QUALIFICATION):
        raise ValueError('The previous successful API qualification reference changed')
    value = scope.load(expected)
    previous = scope.load(value['schema_inventory'])
    if (value.get('passed') is not True or value.get('thinking') is not False
            or value.get('model_calls') != 2 or value.get('unknown_usage_calls') != 0
            or previous.get('schemas') != schemas.get('schemas')
            or previous.get('tool_names') != schemas.get('tool_names')):
        raise ValueError('Only byte-equivalent original interface schemas may reuse API qualification')
    return value


class DeepSeekRuntime:
    def __init__(self):
        self.client = self.counter = self.qualified = None
        self.rows = self.schemas = None
        self._transports, self._lock = [], threading.Lock()

    def initialize_for_run(self):
        scope.require_allowed('v116.api.request')
        if self.client is not None:
            return self.logical_resident()
        prepare_schemas()
        self.schemas = scope.load(reference(SCHEMAS))
        self.rows = {r['slot_id']: r for r in scope.load(reference(scope.PLAN_FILE))['generation_rows']}
        self.qualified = qualify(None, None, self.schemas)
        names = set(self.schemas['tool_names']['REF']) | set(self.schemas['tool_names']['PROJECT'])
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
        allowed = {item['function']['name']: item for item in self.schemas['schemas'][row['arm']]}
        def authorize(payload):
            scope.require_allowed('v116.api.request', slot_id=row['slot_id'], instance_id=row['instance_id'])
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
        return usage(row['slot_id'], row['condition_id'])

    budget_status = staticmethod(budget_status)
    @staticmethod
    def preparation_usage():
        return {'calls': [], 'unresolved_calls': [], 'usage_capture_complete': True,
                'new_preparation_API_calls': 0, 'reused_qualification': reference(QUALIFICATION),
                'previous_qualification_calls_excluded': 2}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Extract frozen actual tool schemas, offline only')
    parser.add_argument('--prepare-schemas', action='store_true', required=True)
    parser.add_argument('--native-wire', type=Path)
    parser.add_argument('--project-wire', type=Path)
    arguments = parser.parse_args()
    print(json.dumps(prepare_schemas(native_wire=arguments.native_wire,
                                    project_wire=arguments.project_wire), ensure_ascii=False))
