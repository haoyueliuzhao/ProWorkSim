"""Explicit +CNY200 amendment of the same ledger; never refund old attempts.

The old modules remain frozen. Only this private reader/client uses the new
policy, and recovery identities must be present in the caller's sealed registry.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from . import software_benchmark_deepseek_api_v064 as original_api
from . import software_benchmark_deepseek_runtime_v064 as original_reader
from . import software_benchmark_deepseek_runtime_v067 as wire
from . import software_benchmark_deepseek_budget_v072 as original_budget
from . import software_benchmark_fd_v085 as fd_policy
from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_deepseek_runtime_v069 import private_function

VERSION = 'v089-explicit-same-ledger-cny1700-r1'
LEDGER = original_reader.LEDGER
MAX_CONCURRENCY = original_reader.MAX_CONCURRENCY
CAP_NANOYUAN = 1700 * original_api.NANOYUAN
POLICY = {**original_api.POLICY, 'version': VERSION, 'cap_nanoyuan': CAP_NANOYUAN}
RECOVERY_SUFFIX = ':recovery-v089-r1'
AMENDMENT_ROOT = original_reader.ROOT/'artifacts/software-benchmark-v089/budget-amendment-r1'
AMENDMENT_COMPLETED = AMENDMENT_ROOT/'completed.json'
AMENDMENT_METADATA_KEY = 'budget_amendment_v089'


class BudgetLedger(original_api.BudgetLedger):
    __init__ = private_function(original_api.BudgetLedger.__init__, POLICY=POLICY,
        sqlite3=fd_policy._sqlite_view)
    snapshot = private_function(original_api.BudgetLedger.snapshot, POLICY=POLICY,
        CAP_NANOYUAN=CAP_NANOYUAN)
    reserve = private_function(original_api.BudgetLedger.reserve, CAP_NANOYUAN=CAP_NANOYUAN)


class DeepSeekClient(original_api.DeepSeekClient):
    __init__ = private_function(original_api.DeepSeekClient.__init__, BudgetLedger=BudgetLedger)


API_VIEW = SimpleNamespace(**{**vars(original_api), 'VERSION': VERSION,
    'CAP_NANOYUAN': CAP_NANOYUAN, 'POLICY': POLICY,
    'BudgetLedger': BudgetLedger, 'DeepSeekClient': DeepSeekClient,
    'DirectDeepSeekClient': DeepSeekClient})


@contextmanager
def ledger_read(path=LEDGER):
    path = Path(path).resolve()
    if not path.is_file():
        raise original_reader.APIQualificationPending('The shared ledger does not exist')
    db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        policy = db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()
        if policy is None or json.loads(policy[0]) != {**POLICY, 'max_concurrency': MAX_CONCURRENCY}:
            raise ValueError('Require the exact explicit CNY1700 amended policy')
        raw = db.execute('SELECT value FROM metadata WHERE name=?', (AMENDMENT_METADATA_KEY,)).fetchone()
        marker = json.loads(raw[0]) if raw is not None else {}
        old_policy = {**original_api.POLICY, 'max_concurrency': MAX_CONCURRENCY}
        new_policy = {**POLICY, 'max_concurrency': MAX_CONCURRENCY}
        if (marker.get('version') != VERSION or marker.get('old_cap_nanoyuan') != original_api.CAP_NANOYUAN
                or marker.get('new_cap_nanoyuan') != CAP_NANOYUAN
                or marker.get('increase_nanoyuan') != 200*original_api.NANOYUAN
                or marker.get('old_policy_sha256') != hashlib.sha256(original_api.transport._json(old_policy).encode()).hexdigest()
                or marker.get('new_policy_sha256') != hashlib.sha256(original_api.transport._json(new_policy).encode()).hexdigest()):
            raise ValueError('The same-ledger amendment marker is absent or changed')
        yield db
    finally:
        db.close()


def validate_retry_registry(retry_rows, *, originals=None):
    originals = original_budget.original_rows() if originals is None else originals
    retry_rows = list(retry_rows.values()) if isinstance(retry_rows, dict) else list(retry_rows)
    if len(retry_rows) > 44:
        raise ValueError('Only the 44 budget-interrupted recovery identities are in this amendment')
    result, indices = {}, set()
    fields = ('model_key', 'condition_id', 'instance_id', 'arm', 'input_plus_output_tokens', 'seed')
    for row in retry_rows:
        old_id = row.get('original_slot_id')
        old = originals.get(old_id)
        new_id, index = row.get('slot_id'), row.get('slot_index')
        if (old is None or old.get('model_key') != 'DEEPSEEK'
                or old.get('input_plus_output_tokens') != 5_000_000
                or new_id != old_id+RECOVERY_SUFFIX or new_id in result
                or row.get('original_slot_index') != old['slot_index']
                or row.get('recovery_attempt') != 1
                or type(index) is not int or index not in range(6000, 6044) or index in indices
                or any(row.get(field) != old.get(field) for field in fields)):
            raise ValueError('Recovery registry changed an original task or invented an attempt')
        result[new_id] = dict(row)
        indices.add(index)
    return result


_validate_uncertainty = private_function(original_budget.validate_bounded_uncertainty, api=API_VIEW)


def budget_status(*, retry_rows=(), path=LEDGER, qualification=original_reader.QUALIFICATION,
                  originals=None):
    rows = original_budget.original_rows() if originals is None else originals
    registry = {**rows, **validate_retry_registry(retry_rows, originals=rows)}
    value = {}
    try:
        with ledger_read(path) as db:
            @contextmanager
            def same_snapshot():
                yield db
            status = private_function(original_reader.budget_status, api=API_VIEW,
                _ledger_read=same_snapshot, QUALIFICATION=Path(qualification), LEDGER=Path(path))
            value = status()
            if value.get('state') != 'shared_halted':
                value.update(_validate_uncertainty(db, rows=registry))
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error,
            original_reader.APIQualificationPending) as error:
        value = {**value, 'state': 'shared_halted', 'can_start_generation': False,
                 'temporary_wait': False, 'reason': 'amended_budget_validation_failed:'+str(error)}
    return {**value, 'version': VERSION, 'failure_scope': 'API', 'qwen_stop_required': False,
        'cap_CNY': '1700.00', 'original_cap_CNY': '1500.00', 'explicit_increase_CNY': '200.00',
        'ledger_path': str(path), 'new_cash_budget': False, 'existing_ledger_amended': True,
        'new_neutral_calls': 0, 'ledger_records_modified': False,
        'unknown_reservations_released': False}


_usage = private_function(original_reader._usage, _ledger_read=ledger_read, api=API_VIEW)
preparation_usage = private_function(original_reader.preparation_usage, _usage=_usage)


def usage_for_slot(row, *, retry_rows=()):
    originals = original_budget.original_rows()
    registry = {**originals, **validate_retry_registry(retry_rows, originals=originals)}
    bound = registry.get(row.get('slot_id'))
    if (bound is None or bound.get('model_key') != 'DEEPSEEK'
            or any(row.get(key) != bound.get(key) for key in ('slot_id', 'condition_id', 'instance_id'))):
        raise ValueError('Usage reads require a registered original or recovery identity')
    return _usage(row['slot_id'], expected_condition=row['condition_id'])


def require_amendment():
    completed = json.loads(checked(reference(AMENDMENT_COMPLETED)).read_bytes())
    if (completed.get('version') != VERSION or completed.get('committed') is not True
            or completed.get('ledger') != str(LEDGER)
            or completed.get('new_cap_nanoyuan') != CAP_NANOYUAN
            or completed.get('all_existing_financial_rows_preserved') is not True):
        raise ValueError('The explicit same-ledger amendment has no trusted completion receipt')
    with ledger_read() as db:
        marker = db.execute('SELECT value FROM metadata WHERE name=?', (AMENDMENT_METADATA_KEY,)).fetchone()
        if marker is None or json.loads(marker[0]) != completed['amendment_metadata']:
            raise ValueError('The live ledger and amendment completion receipt disagree')
    return reference(AMENDMENT_COMPLETED)


def build_runtime(*, scope_guard, retry_rows, inventory_ref, identity_file):
    """Build the private broker for the sealed 44-recovery phase, not a retry API."""
    registry = validate_retry_registry(retry_rows)
    identity_file = Path(identity_file)

    class Runtime(wire.DeepSeekRuntime):
        def _require_allowed(self, *, slot_id=None, instance_id=None):
            return scope_guard('v089.api.request', slot_id=slot_id, instance_id=instance_id)

        def read_only_preflight(self):
            require_amendment()
            if self.budget_status()['state'] != 'ready':
                raise wire.APIUnavailable(self.budget_status())
            inventory = wire.policy.load(inventory_ref)
            declared = validate_retry_registry(inventory['rows'])
            if declared != registry:
                raise ValueError('Runtime recovery rows differ from the sealed inventory')
            self.qualified = wire.policy.load(reference(wire.QUALIFICATION))
            if (self.qualified.get('passed') is not True or self.qualified.get('model_calls') != 2
                    or self.qualified.get('unknown_usage_calls') != 0):
                raise wire.APIQualificationPending('Original neutral qualification is not intact')
            preparation = wire.policy.load(self.qualified['plan'])
            if (Path(self.qualified['plan']['path']).resolve() != wire.QUALIFICATION.parent/'plan.json'
                    or preparation.get('ledger') != str(LEDGER)
                    or self.qualified.get('cash_snapshot', {}).get('ledger_path') != str(LEDGER)):
                raise ValueError('The old neutral calls and amended runtime must share one ledger')
            for source in preparation['sources']:
                checked(source)
            self.preparation_usage_validation = wire.validate_existing_preparation_usage(
                preparation_usage(), self.qualified)
            self.schemas = wire.policy.load(wire.prepare_schema_inventory())
            with ledger_read() as db:
                used = {slot for (slot,) in db.execute('SELECT DISTINCT slot_id FROM requests')}
            if used & registry.keys():
                raise ValueError('A recovery attempt with prior API evidence cannot be replayed')
            self.rows, self.inventory = dict(registry), inventory
            names = set(self.schemas['tool_names']['REF']) | set(self.schemas['tool_names']['PROJECT'])
            return {'preparation': preparation, 'allowed_tool_names': names,
                    'eligible_API_slots': len(registry), 'neutral_usage': self.preparation_usage_validation}

        initialize_for_run = private_function(wire.DeepSeekRuntime.initialize_for_run, api=API_VIEW)

        def logical_resident(self):
            if self.client is None or self.counter is None or self.qualified is None:
                raise wire.APIQualificationPending('Initialize the amended host client explicitly')
            identity = {'version': VERSION, 'model_key': 'DEEPSEEK', 'model': API_VIEW.MODEL,
                'model_revision': API_VIEW.DOCUMENTED_MODEL_VERSION,
                'documented_model_version': API_VIEW.DOCUMENTED_MODEL_VERSION,
                'provider_weight_revision_pinnable': False, 'project_training_adapter_loaded': False,
                'context_limit': API_VIEW.CONTEXT_TOKENS, 'max_output_tokens': API_VIEW.MAX_OUTPUT_TOKENS,
                'thinking': True, 'service_admission_complete': True, 'port': 18219,
                'endpoint': wire.ENDPOINT, 'host_listener': False, 'deployment_version': VERSION,
                'qualification': reference(wire.QUALIFICATION),
                'tool_schema_inventory': reference(wire.SCHEMA_FILE), 'continuation_inventory': inventory_ref,
                'ledger_path': str(LEDGER), 'cash_cap_CNY': '1700.00', 'new_neutral_calls': 0,
                'explicit_budget_amendment': reference(AMENDMENT_COMPLETED),
                'recovery_is_new_attempt_not_exact_interrupted_state_resume': True}
            ref = wire.policy.retain(identity_file, identity)
            return {'model_key': 'DEEPSEEK', 'endpoint': wire.ENDPOINT, 'api_key_file': None,
                'identity': ref, 'identity_value': identity, 'directory': str(identity_file.parent),
                'logical_only_no_listener': True}

        def transport_factory(self, row, output):
            return private_function(wire.DeepSeekRuntime.transport_factory,
                _ledger_read=ledger_read, budget_status=self.budget_status, api=API_VIEW)(self, row, output)

        def budget_status(self):
            return budget_status(retry_rows=registry)

        def usage_for_slot(self, row):
            return usage_for_slot(row, retry_rows=registry)

        def preparation_usage(self):
            return preparation_usage()

    return Runtime(scope_guard=scope_guard)


class RuntimeView(fd_policy.RuntimeView):
    """Keep the existing FD wait semantics without reinstalling the old cap."""
    def initialize_for_run(self):
        initializer = self.runtime.initialize_for_run.__func__
        api = initializer.__globals__.get('api')
        if api is not API_VIEW or api.DeepSeekClient is not DeepSeekClient:
            raise ValueError('Only the explicitly amended closing client may initialize')
        return initializer(self.runtime)
