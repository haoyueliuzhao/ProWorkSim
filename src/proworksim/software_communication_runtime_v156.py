"""Shared communication-pilot accounting and an injected, audited request seam.

No network client, model, container, system service, or training is started here.
The same pool is used by both members, the history condenser and compressor.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import fcntl
import hashlib
import json
from pathlib import Path
import threading


VERSION = 'v156-communication-pilot-shared-runtime-r1'
PURPOSES = {'agent', 'condenser', 'compressor'}


class BudgetStopped(RuntimeError):
    pass


class AccountingConflict(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(',', ':')).encode('utf-8')


def integer(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f'{name} must be a nonnegative integer')
    return value


def normalized_usage(usage):
    if not isinstance(usage, dict):
        raise ValueError('An actual provider usage object is required')
    prompt = integer(usage.get('prompt_tokens', usage.get('input_tokens')), 'prompt_tokens')
    completion = integer(usage.get('completion_tokens', usage.get('output_tokens')), 'completion_tokens')
    total = integer(usage.get('total_tokens'), 'total_tokens')
    if total != prompt + completion:
        raise AccountingConflict('Provider total differs from input plus output')
    cached = usage.get('prompt_cache_hit_tokens')
    alternate = usage.get('prompt_tokens_details', {}).get('cached_tokens')
    if cached is None:
        cached = alternate
    if cached is not None:
        integer(cached, 'cached_tokens')
        if cached > prompt or alternate is not None and alternate != cached:
            raise AccountingConflict('Cached input must be one consistent input subset')
    missed = usage.get('prompt_cache_miss_tokens')
    if missed is not None:
        integer(missed, 'cache_miss_tokens')
        if missed > prompt or cached is not None and cached + missed != prompt:
            raise AccountingConflict('Cache hit and miss must sum to prompt usage')
    return {'input_tokens': prompt, 'output_tokens': completion,
            'total_tokens': total, 'cached_input_tokens': cached,
            'raw_usage': copy.deepcopy(usage)}


class SharedTeamPool:
    """Durable one-team token/HTTP/decision book; cash is a separate global book.

    Idempotent book operations never authorize replaying an HTTP request. An
    unknown request retains its entire reservation; a retry needs a new ID.
    """
    def __init__(self, folder, team_id, *, token_limit=5_000_000,
                 attempt_limit=512, decision_limit=512):
        if not isinstance(team_id, str) or not team_id:
            raise ValueError('A concrete team identity is required')
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder/'pool.json'
        self.lock_path = self.folder/'pool.lock'
        self.thread_lock = threading.RLock()
        self.contract = {'version': VERSION, 'team_id': team_id,
                         'token_limit': integer(token_limit, 'token_limit'),
                         'attempt_limit': integer(attempt_limit, 'attempt_limit'),
                         'decision_limit': integer(decision_limit, 'decision_limit')}
        with self._transaction() as state:
            if not state:
                state.update(contract=self.contract, requests={}, integrity_failure=None)

    @contextmanager
    def _transaction(self):
        with self.thread_lock, self.lock_path.open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                state = json.loads(self.path.read_bytes()) if self.path.exists() else {}
                if state and state.get('contract') != self.contract:
                    raise AccountingConflict('Existing shared pool has another identity or limits')
                yield state
                temporary = self.path.with_suffix('.pending')
                temporary.write_bytes(canonical(state))
                temporary.replace(self.path)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _view(self, state):
        requests = state.get('requests', {})
        known = [r for r in requests.values() if r.get('usage') is not None]
        held = [r for r in requests.values() if r.get('usage') is None]
        tokens = sum(r['usage']['total_tokens'] for r in known)
        reserved = sum(r['reservation']['input_upper'] + r['reservation']['max_output'] for r in held)
        decisions = {r['reservation']['identity']['decision_id'] for r in requests.values()
                     if r['reservation']['purpose'] == 'agent'}
        by_purpose = {}
        for purpose in sorted(PURPOSES):
            rows = [r for r in known if r['reservation']['purpose'] == purpose]
            by_purpose[purpose] = {'requests': len(rows),
                'input_tokens': sum(r['usage']['input_tokens'] for r in rows),
                'output_tokens': sum(r['usage']['output_tokens'] for r in rows),
                'total_tokens': sum(r['usage']['total_tokens'] for r in rows)}
        return {**self.contract, 'known_actual_tokens': tokens,
                'unresolved_reserved_tokens': reserved,
                'available_tokens': self.contract['token_limit'] - tokens - reserved,
                'physical_attempts': len(requests), 'agent_decisions': len(decisions),
                'actual_usage_complete': not held, 'per_purpose': by_purpose,
                'integrity_failure': state.get('integrity_failure'),
                'cash_accounting_not_implemented_by_this_team_book': True}

    def snapshot(self):
        with self._transaction() as state:
            return self._view(state)

    def reserve(self, request_id, purpose, input_upper, max_output, *, identity=None):
        if not isinstance(request_id, str) or not request_id or purpose not in PURPOSES:
            raise ValueError('A physical request ID and a declared model purpose are required')
        identity = copy.deepcopy(identity or {})
        if 'episode_id' in identity and identity['episode_id'] != self.contract['team_id']:
            raise AccountingConflict('Request episode does not own this shared pool')
        if purpose == 'agent' and (not isinstance(identity.get('decision_id'), str)
                                   or not identity['decision_id']):
            raise ValueError('Agent attempts must bind their logical decision ID')
        reservation = {'purpose': purpose, 'input_upper': integer(input_upper, 'input_upper'),
                       'max_output': integer(max_output, 'max_output'), 'identity': identity}
        if max_output <= 0:
            raise ValueError('A positive output allowance is required')
        with self._transaction() as state:
            previous = state['requests'].get(request_id)
            if previous is not None:
                if previous['reservation'] != reservation:
                    raise AccountingConflict('A physical request ID cannot be rebound')
                return copy.deepcopy(previous)
            view = self._view(state)
            if view['integrity_failure']:
                raise AccountingConflict('Shared accounting integrity has failed')
            if view['physical_attempts'] >= self.contract['attempt_limit']:
                raise BudgetStopped('Shared physical HTTP attempt limit exhausted')
            if input_upper + max_output > view['available_tokens']:
                raise BudgetStopped('Shared team token reservation exhausted')
            old_decisions = {r['reservation']['identity'].get('decision_id')
                             for r in state['requests'].values()
                             if r['reservation']['purpose'] == 'agent'}
            if (purpose == 'agent' and identity['decision_id'] not in old_decisions
                    and len(old_decisions) >= self.contract['decision_limit']):
                raise BudgetStopped('Shared agent decision limit exhausted')
            row = {'request_id': request_id, 'reservation': reservation,
                   'status': 'reserved', 'usage': None}
            state['requests'][request_id] = row
            return copy.deepcopy(row)

    def claim_dispatch(self, request_id, payload_sha256):
        """Atomic across instances/directories: one physical attempt may send once."""
        if (not isinstance(payload_sha256, str) or len(payload_sha256) != 64
                or any(c not in '0123456789abcdef' for c in payload_sha256)):
            raise ValueError('Bind a concrete canonical payload SHA256 before dispatch')
        with self._transaction() as state:
            row = state['requests'][request_id]
            if (state['integrity_failure'] or row['status'] != 'reserved'
                    or row.get('dispatch_started')):
                raise AccountingConflict('A consumed or unresolved physical identity cannot be dispatched again')
            row['dispatch_started'] = True
            row['request_payload_sha256'] = payload_sha256
            return copy.deepcopy(row)

    def settle(self, request_id, usage):
        actual = normalized_usage(usage)
        overrun = False
        with self._transaction() as state:
            row = state['requests'][request_id]
            if row.get('usage') is not None:
                if row['usage'] != actual:
                    raise AccountingConflict('A physical request has conflicting usage receipts')
                return copy.deepcopy(row)
            cap = row['reservation']
            overrun = (actual['input_tokens'] > cap['input_upper']
                       or actual['output_tokens'] > cap['max_output'])
            row.update(status='settled_overrun' if overrun else 'settled', usage=actual)
            if overrun:
                state['integrity_failure'] = 'provider_usage_exceeded_reserved_bounds'
            result = copy.deepcopy(row)
        if overrun:
            raise AccountingConflict('Actual usage retained; further dispatch halted after provider overrun')
        return result

    def uncertain(self, request_id, evidence):
        with self._transaction() as state:
            row = state['requests'][request_id]
            if row.get('usage') is not None:
                return copy.deepcopy(row)  # A later observer error cannot erase known usage.
            if row['status'] == 'uncertain' and row.get('evidence') != evidence:
                raise AccountingConflict('An uncertain attempt cannot be silently relabelled')
            row.update(status='uncertain', evidence=copy.deepcopy(evidence))
            return copy.deepcopy(row)


class RequestSourceRegistry:
    """Capture source at producer time; no text-search attribution fallback.

    The SDK adapter must carry these explicit keys through projection/summary.
    Unknown or rewritten input is intentionally left unattributed.
    """
    def __init__(self, member_id):
        self.member_id = member_id
        self.messages = {}

    def register(self, event_id, message, annotated_message):
        from .software_input_provenance_v156 import build_request
        built = build_request(annotated_message, identity={'request_id': 'registration:'+event_id,
            'episode_id': 'source-registration', 'member_id': self.member_id,
            'decision_id': event_id, 'attempt_id': 'registration',
            'model_alias': 'source-registration-only', 'request_time': 'not-dispatched'})
        if built.payload_bytes != canonical(message):
            raise AccountingConflict('Annotations must retain the exact producer message bytes')
        record = (copy.deepcopy(message), copy.deepcopy(annotated_message))
        if event_id in self.messages and self.messages[event_id] != record:
            raise AccountingConflict('An immutable source event cannot change')
        self.messages[event_id] = record

    def resolve(self, event_id, actual_message):
        record = self.messages.get(event_id)
        if record is None or canonical(record[0]) != canonical(actual_message):
            return copy.deepcopy(actual_message)
        return copy.deepcopy(record[1])


class AuditedRequestGateway:
    """Records exactly the bytes given to an injected transport, once per ID.

    CPU scripts must declare cpu_synthetic. A real transport is deliberately
    unavailable until a reviewed gate and a funded, bounded runner are bound.
    """
    def __init__(self, directory, pool, transport, *, evidence_domain='cpu_synthetic'):
        if evidence_domain != 'cpu_synthetic' or getattr(transport, 'evidence_domain', None) != evidence_domain:
            raise PermissionError('P0 gateway accepts only an explicitly injected CPU scripted transport')
        self.directory, self.pool, self.transport = Path(directory), pool, transport
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def complete(self, annotated_payload, *, identity, purpose, input_upper, max_output,
                 template_source=None):
        from .software_input_provenance_v156 import build_request, persist_request, capture_response
        built = build_request(annotated_payload, identity=identity, template_source=template_source)
        request_id = identity['request_id']
        folder = self.directory/hashlib.sha256(request_id.encode()).hexdigest()
        with self.lock:
            if (folder/'dispatch-entered.json').exists():
                raise AccountingConflict('Consumed physical identity cannot repeat an external request')
            capture_receipt = persist_request(self.directory, built)
            (folder/'capture.json').write_bytes(canonical(capture_receipt))
            try:
                self.pool.reserve(request_id, purpose, input_upper, max_output, identity=identity)
            except BudgetStopped as error:
                capture = capture_response(built, None, outcome='cancelled_before_dispatch',
                    error={'type': type(error).__name__, 'reason': str(error)})
                (folder/'response.json').write_bytes(canonical(capture))
                raise
            payload_sha = hashlib.sha256(built.payload_bytes).hexdigest()
            self.pool.claim_dispatch(request_id, payload_sha)
            with (folder/'dispatch-entered.json').open('xb') as entry:
                entry.write(canonical({'request_id': request_id, 'domain': 'cpu_synthetic',
                                       'wire_sha256': payload_sha}))
            try:
                body = self.transport(built.payload_bytes, identity=copy.deepcopy(identity))
            except Exception as error:
                self.pool.uncertain(request_id, {'stage': 'transport', 'type': type(error).__name__})
                capture = capture_response(built, None, outcome='transport_unknown', http_status=None,
                    error={'stage': 'transport', 'type': type(error).__name__})
                (folder/'response.json').write_bytes(canonical(capture))
                raise
            # Retain even a malformed/over-budget response before any validation.
            (folder/'response-original.json').write_bytes(canonical(body))
            try:
                self.pool.settle(request_id, body['usage'])
            except Exception as error:
                self.pool.uncertain(request_id, {'stage': 'usage', 'type': type(error).__name__})
                # The complete original object remains separate even if usage is malformed.
                try:
                    capture = capture_response(built, body, outcome='transport_unknown', http_status=200,
                        error={'stage': 'usage', 'type': type(error).__name__})
                except (ValueError, TypeError):
                    capture = capture_response(built, None, outcome='transport_unknown', http_status=200,
                        error={'stage': 'usage', 'type': type(error).__name__,
                               'raw_response_preserved': 'response-original.json'})
                (folder/'response.json').write_bytes(canonical(capture))
                raise
            capture = capture_response(built, body, outcome='success', http_status=200)
            (folder/'response.json').write_bytes(canonical(capture))
            return body
