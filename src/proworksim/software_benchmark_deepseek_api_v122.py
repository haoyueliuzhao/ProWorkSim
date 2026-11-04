"""Explicit new runtime binding to the one-use remaining-CNY45 grant.

Importing this module never opens a client or changes the ledger. Call bind_api()
after the amendment completion receipt exists. Frozen v105 globals stay intact.
"""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

from . import software_benchmark_cash_amendment_v122 as amendment
from . import software_benchmark_deepseek_api_v105 as prior
from .software_benchmark_candidates_v054 import checked, reference

VERSION = 'v122-explicit-cash-grant-api-binding-r1'


def _private(function, **bindings):
    result = FunctionType(function.__code__, {**function.__globals__, **bindings},
                          function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = dict(function.__kwdefaults__ or {})
    return result


def _api_view(policy, ledger_path):
    cap = policy['cap_nanoyuan']
    # Compare all non-cap fields, including the unchanged policy version.
    if ({key: value for key, value in policy.items() if key != 'cap_nanoyuan'} !=
            {key: value for key, value in amendment.OLD_POLICY.items() if key != 'cap_nanoyuan'}):
        raise ValueError('Only the cash cap can differ from the frozen API policy')
    concurrency = policy['max_concurrency']
    runtime_policy = {key: value for key, value in policy.items() if key != 'max_concurrency'}
    original_init = _private(prior.BudgetLedger.__init__, POLICY=runtime_policy)

    class BudgetLedger(prior.BudgetLedger):
        def __init__(self, path, *, max_concurrency=concurrency):
            if Path(path).resolve() != Path(ledger_path).resolve() or max_concurrency != concurrency:
                raise ValueError('The grant only permits the same ledger and request concurrency')
            original_init(self, path, max_concurrency=max_concurrency)

        snapshot = _private(prior.BudgetLedger.snapshot, POLICY=runtime_policy, CAP_NANOYUAN=cap)
        reserve = _private(prior.BudgetLedger.reserve, CAP_NANOYUAN=cap)

    client_init = _private(prior.DeepSeekClient.__init__, BudgetLedger=BudgetLedger)
    client_init.__kwdefaults__['max_concurrency'] = concurrency

    class DeepSeekClient(prior.DeepSeekClient):
        __init__ = client_init

    return SimpleNamespace(**{**vars(prior), 'VERSION': VERSION, 'POLICY': runtime_policy,
        'CAP_NANOYUAN': cap, 'CASH_CAP_CNY': amendment.cny(cap),
        'BudgetLedger': BudgetLedger, 'DeepSeekClient': DeepSeekClient,
        'DirectDeepSeekClient': DeepSeekClient, 'new_neutral_calls': 0})


def bind_api(grant_path=amendment.GRANT_FILE):
    """Return a private, explicitly granted API view; perform no network calls."""
    if Path(grant_path).resolve() != amendment.GRANT_FILE:
        raise ValueError('Use the sealed v122 cash grant')
    grant_ref, grant = amendment.verified_grant()
    receipt_ref = reference(amendment.COMPLETED)
    receipt = json.loads(checked(receipt_ref).read_bytes())
    if (receipt.get('committed') is not True or receipt.get('version') != amendment.VERSION
            or receipt.get('grant') != grant_ref or receipt.get('new_cap_nanoyuan') != grant['new_cap_nanoyuan']
            or receipt.get('all_existing_rows_preserved') is not True):
        raise ValueError('The remaining-CNY45 grant has no intact completion receipt')
    with closing(amendment.open_read()) as db:
        policy = db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()
        marker = db.execute('SELECT value FROM metadata WHERE name=?', (amendment.MARKER,)).fetchone()
        if (policy is None or policy[0] != prior.transport._json(grant['new_policy'])
                or marker is None or json.loads(marker[0]) != receipt['amendment_metadata']):
            raise ValueError('The live policy or amendment marker differs from the sealed grant')
    api = _api_view(grant['new_policy'], amendment.LEDGER)
    api.cash_grant, api.cash_receipt = grant_ref, receipt_ref
    return api
