"""One new CNY400 pilot ledger, attributed by group/member, with shared team limits.

The frozen HTTPS, usage normalization and conservative peak-window helpers are
reused. No old database or module global is modified; import opens no ledger.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from types import FunctionType, SimpleNamespace

from . import software_benchmark_deepseek_api_v105 as original
from .software_benchmark_alignment_contract_v141 import GROUP_IDS, TEAM_TOKEN_BUDGET, condition as frozen_condition

VERSION = 'v142-common-pilot400-actual-request-reservation-r1'
NANOYUAN = original.NANOYUAN
CAP_NANOYUAN = 400*NANOYUAN
MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS = 98304, 32768
MISS_NANOYUAN, HIT_NANOYUAN, OUTPUT_NANOYUAN = 2000, 40, 8000
MAX_PROFILE_RESERVATION_NANOYUAN = MAX_INPUT_TOKENS*MISS_NANOYUAN+MAX_OUTPUT_TOKENS*OUTPUT_NANOYUAN
PRICING = {
    'checked_date': '2026-11-06', 'currency': 'CNY',
    'model': 'deepseek-flash', 'documented_model_version': 'DeepSeek-V4.1-Flash-1017',
    'peak_per_million_tokens': {'cache_hit': '0.04', 'cache_miss': '2', 'output': '8'},
    'off_peak_divisor': 2, 'provider_context_tokens': 1048576,
    'provider_max_output_tokens': 393216, 'provider_account_concurrency': 2500,
    'peak_UTC_weekday_intervals': [[1, 4], [6, 10]],
    'unverified_public_holiday_discount_assumed': False,
    'sources': ['https://api-docs.deepseek.com/zh-cn/quick_start/pricing/',
                'https://api-docs.deepseek.com/quick_start/rate_limit/',
                'https://api-docs.deepseek.com/api/create-chat-completion/'],
}


def _private(function, **bindings):
    value = FunctionType(function.__code__, {**function.__globals__, **bindings},
                         function.__name__, function.__defaults__, function.__closure__)
    value.__kwdefaults__ = dict(function.__kwdefaults__ or {})
    return value


def request_reservation(prompt_upper_bound, max_output_tokens):
    original.transport._integer(prompt_upper_bound, 'prompt_upper_bound', maximum=MAX_INPUT_TOKENS)
    original.transport._integer(max_output_tokens, 'max_output_tokens', maximum=MAX_OUTPUT_TOKENS)
    if max_output_tokens <= 0:
        raise ValueError('An explicit positive response cap is required')
    return prompt_upper_bound*MISS_NANOYUAN+max_output_tokens*OUTPUT_NANOYUAN


def group_api(group_id, ledger_path, *, max_concurrency, panel_ref):
    """Return an isolated API view; only explicit client construction opens it."""
    if group_id not in GROUP_IDS or type(max_concurrency) is not int or not 1 <= max_concurrency <= 2500:
        raise ValueError('Unknown organization or unbounded account concurrency')
    from .software_benchmark_candidates_v054 import checked
    panel = json.loads(checked(panel_ref).read_text())
    planned = {r['slot_id']: r for r in panel['rows']}
    if len(planned) != 120 or panel.get('cash_budget_CNY') != '400.00':
        raise ValueError('The immutable120-attempt pilot with one400 budget is required')
    ledger_path = Path(ledger_path).resolve()
    concurrency_limit = max_concurrency
    if ledger_path.name != 'pilot.sqlite':
        raise ValueError('All three organizations require the same named pilot database')
    policy = {**original.POLICY, 'version': VERSION, 'group_ids': list(GROUP_IDS), 'pilot_panel': panel_ref,
        'cap_nanoyuan': CAP_NANOYUAN, 'pricing_checked_date': PRICING['checked_date'],
        'verified_pricing': PRICING, 'request_reservation_nanoyuan': None,
        'request_reservation_rule': 'peak_cache_miss_price*actual_prompt_upper_bound + peak_output_price*requested_max_tokens',
        'new_team_admission_reservation_nanoyuan': MAX_PROFILE_RESERVATION_NANOYUAN,
        'absolute_output_reservation_tokens': MAX_OUTPUT_TOKENS,
        'team_token_limit': TEAM_TOKEN_BUDGET, 'team_attempt_limit': 512,
        'member_cash_identity': 'team:member; ledger slot remains the team',
        'cash_scope': 'one_new_CNY400_pilot_shared_by_all_three_arms', 'new_neutral_calls': 0}
    init = _private(original.BudgetLedger.__init__, POLICY=policy)

    class BudgetLedger(original.BudgetLedger):
        def __init__(self, path, *, max_concurrency=max_concurrency):
            if Path(path).resolve() != ledger_path or max_concurrency != concurrency_limit:
                raise ValueError('This private cash view cannot open another database')
            init(self, path, max_concurrency=max_concurrency)
            with self._transaction() as db:
                db.execute('CREATE TABLE IF NOT EXISTS member_requests ('
                           'request_id TEXT PRIMARY KEY,group_id TEXT NOT NULL,member_id TEXT NOT NULL)')

        snapshot = _private(original.BudgetLedger.snapshot, POLICY=policy, CAP_NANOYUAN=CAP_NANOYUAN,
                            ABSOLUTE_RESERVATION_NANOYUAN=MAX_PROFILE_RESERVATION_NANOYUAN)

        def reserve(self, *, request_id, slot_id, condition, usage_id, request_sha256,
                    max_output_tokens, prompt_upper_bound, member_id):
            amount = request_reservation(prompt_upper_bound, max_output_tokens)
            expected_condition = frozen_condition(group_id)
            if (not isinstance(request_id, str) or not isinstance(slot_id, str)
                    or condition != expected_condition['condition_id']
                    or member_id not in expected_condition['fixed_members']):
                raise ValueError('Cash authority is bound to one organization and its fixed registry')
            row = planned.get(slot_id)
            if (row is None or row['organization_id'] != group_id
                    or row['condition_id'] != condition or member_id not in row['fixed_members']):
                raise ValueError('Request is outside its exact planned team and registry')
            prefix = slot_id+':'+member_id+':'
            suffix = request_id.removeprefix(prefix)
            if (not re.fullmatch(r'member_[0-9]{3}', member_id)
                    or not request_id.startswith(prefix) or not re.fullmatch(r'[0-9]{4}', suffix)
                    or not 1 <= int(suffix) <= 512 or usage_id not in {'agent', 'condenser'}
                    or not slot_id.startswith('v142:') or not isinstance(condition, str)
                    or not re.fullmatch(r'[0-9a-f]{64}', request_sha256)):
                raise ValueError('Cash reservation lacks an exact team/member/request identity')
            with self._transaction() as db:
                if db.execute('SELECT 1 FROM requests WHERE request_id=?', (request_id,)).fetchone():
                    raise original.BudgetStopped('request_id_already_attempted_no_replay')
                halt = db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
                if halt:
                    raise original.BudgetStopped('group_ledger_halted:'+halt[0])
                cooldown = db.execute("SELECT value FROM metadata WHERE name='cooldown_until_utc'").fetchone()
                if original.transport.cooldown_state(cooldown[0] if cooldown else None)['admission_wait_seconds'] > 0:
                    raise original.ConcurrencyBusy('group_provider_cooldown_before_dispatch')
                totals = self._totals(db)
                if (totals['inflight'] or 0) >= self.max_concurrency:
                    raise original.ConcurrencyBusy('group_request_concurrency_limit')
                if totals['committed']+amount > CAP_NANOYUAN:
                    if totals['inflight']:
                        raise original.ConcurrencyBusy('group_cash_reserved_by_inflight_requests')
                    raise original.BudgetStopped('group_cash_reservation_insufficient')
                rows = list(db.execute('SELECT usage_id,status,usage_json FROM requests WHERE slot_id=?', (slot_id,)))
                if any(row['status'] != 'settled' for row in rows):
                    raise original.BudgetStopped('team_has_unclosed_or_unknown_usage')
                actual = sum(json.loads(row['usage_json'])['total_tokens'] for row in rows)
                if (len(rows) >= 512 or sum(row['usage_id'] == 'agent' for row in rows) >= 512
                        or actual+prompt_upper_bound+max_output_tokens > TEAM_TOKEN_BUDGET):
                    raise original.BudgetStopped('shared_team_limit_before_dispatch')
                db.execute('INSERT INTO requests (request_id,slot_id,condition,usage_id,status,request_sha256,'
                    'reserved_nanoyuan,max_output_tokens,prompt_upper_bound,reserved_utc) VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (request_id,slot_id,condition,usage_id,'reserved',request_sha256,amount,
                     max_output_tokens,prompt_upper_bound,original.transport._now()))
                db.execute('INSERT INTO member_requests VALUES (?,?,?)', (request_id,group_id,member_id))
            return {'request_id': request_id, 'reserved_nanoyuan': amount, 'reserved_cny': amount/NANOYUAN}

    class DirectHTTPS(original.DirectHTTPS):
        request = _private(original.DirectHTTPS.request, VERSION=VERSION)

    class DeepSeekClient:
        def __init__(self, *, ledger_path=ledger_path, api_key, allowed_tool_names,
                     max_concurrency=max_concurrency, timeout_seconds=1800, transport=None):
            self.ledger = BudgetLedger(ledger_path, max_concurrency=max_concurrency)
            self.allowed_tool_names = frozenset(allowed_tool_names)
            self.transport = transport or DirectHTTPS(api_key, timeout_seconds=timeout_seconds)

        def fork_for_episode(self):
            if not isinstance(self.transport, DirectHTTPS):
                raise ValueError('Only the fixed direct transport can create an episode route')
            return type(self)(ledger_path=self.ledger.path, api_key=self.transport._api_key,
                allowed_tool_names=self.allowed_tool_names, max_concurrency=self.ledger.max_concurrency,
                timeout_seconds=self.transport.timeout_seconds)

        def complete(self, request, *, request_id, slot_id, condition, usage_id,
                     prompt_upper_bound, member_id):
            expected_user = original.slot_user_id(slot_id+':'+member_id, condition)
            if request.get('user_id') != expected_user:
                raise ValueError('The provider cache identity must belong to this team member')
            original.validate_payload(request, self.allowed_tool_names)
            try:
                self.ledger.reserve(request_id=request_id, slot_id=slot_id, condition=condition,
                    usage_id=usage_id, request_sha256=original.transport._sha(request),
                    max_output_tokens=request['max_tokens'], prompt_upper_bound=prompt_upper_bound,
                    member_id=member_id)
            except original.ConcurrencyBusy as error:
                raise original.PreDispatchConcurrencyBusy(str(error)) from None
            except original.BudgetStopped as error:
                raise original.PreDispatchBudgetStopped(str(error)) from None
            try:
                body = self.transport.request('POST', '/chat/completions', request)
                self.ledger.settle(request_id, body)
                return body
            except (original.BudgetStopped, original.ProviderOutputBoundViolation):
                raise
            except BaseException as error:
                status = getattr(error, 'http_status', None)
                self.ledger.uncertain(request_id, {'error_type': type(error).__name__, 'http_status': status,
                    'reason': 'attempt_not_proven_settled_no_automatic_retry',
                    'shared_system_failure': status in {None,400,429} or type(status) is int and 500 <= status < 600})
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    raise
                raise original.APIUncertainFailure('Group request outcome unknown; reservation retained') from None

    return SimpleNamespace(**{**vars(original), 'VERSION': VERSION, 'POLICY': policy,
        'CAP_NANOYUAN': CAP_NANOYUAN, 'CASH_CAP_CNY': '400.00', 'group_id': group_id,
        'ABSOLUTE_RESERVATION_NANOYUAN': MAX_PROFILE_RESERVATION_NANOYUAN,
        'ADMISSION_RESERVATION_NANOYUAN': MAX_PROFILE_RESERVATION_NANOYUAN,
        'BudgetLedger': BudgetLedger, 'DeepSeekClient': DeepSeekClient,
        'DirectDeepSeekClient': DeepSeekClient, 'DirectHTTPS': DirectHTTPS, 'new_neutral_calls': 0})
