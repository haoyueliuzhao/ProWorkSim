"""Retain full fees for calls whose API owner died before durable settlement."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import time

from proworksim import software_benchmark_deepseek_api_v064 as api
from proworksim import software_benchmark_dispatch_v066 as policy
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

VERSION = 'v081-dead-owner-full-cash-reservation-reconciliation-r1'
ROOT = policy.ROOT
EVIDENCE = ROOT / 'artifacts/software-benchmark-v081/dead-owner-recovery-r1/exit-evidence.json'
OUT = ROOT / 'artifacts/software-benchmark-v081/dead-owner-cash-r1'
LEDGER = policy.PREDECESSOR_ROOT / 'api-budget/ledger.sqlite3'
UNIT = 'proworksim-v076-api.service'


def read_rows(db, request_ids):
    rows = [dict(db.execute('SELECT * FROM requests WHERE request_id=?', (key,)).fetchone())
            for key in request_ids]
    for row in rows:
        if (row['status'] != 'reserved' or row['reserved_nanoyuan'] != api.ABSOLUTE_RESERVATION_NANOYUAN
                or any(row.get(key) is not None for key in ('usage_json', 'response_id', 'response_sha256',
                    'settled_nanoyuan', 'settled_utc', 'settled_peak_nanoyuan', 'tariff_basis_json'))):
            raise ValueError('Only exact fully reserved and unsettled calls may be reconciled')
        for table in ('response_observations', 'provider_protocol_events'):
            if db.execute('SELECT 1 FROM '+table+' WHERE request_id=?', (row['request_id'],)).fetchone():
                raise ValueError('Authoritative response/protocol evidence requires separate reconciliation')
    return rows


def conserved(view):
    return {key: view[key] for key in ('remaining_cny', 'committed_upper_cny',
                                      'settled_upper_cny', 'attempts', 'cap_nanoyuan')}


def mark_unknown(ledger, rows):
    before = ledger.snapshot()
    before_values = conserved(before)
    for row in rows:
        # This is an administrative classification of genuinely unknown calls,
        # not a claim that the provider returned an HTTP or transport error.
        ledger.uncertain(row['request_id'], {'error_type': 'APIUncertainFailure',
            'http_status': None, 'reason': 'attempt_not_proven_settled_no_automatic_retry',
            'shared_system_failure': True})
    after = ledger.snapshot()
    if before_values != conserved(after):
        raise RuntimeError('A retained cash bound changed during administrative reconciliation')
    return before, after


def execute():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('This ledger repair requires only the existing ordinary user')
    if OUT.exists():
        raise FileExistsError('Inspect the immutable one-time cash-repair evidence before any retry')
    evidence_ref = reference(EVIDENCE)
    evidence = json.loads(checked(evidence_ref).read_bytes())
    spec = json.loads(checked(evidence['unit_specification']).read_bytes())
    if (evidence.get('unit') != UNIT or evidence.get('journal_explicit_oom_kill') is not True
            or spec.get('unit') != UNIT or spec.get('user_id') != os.getuid()
            or evidence.get('ledger') != str(LEDGER) or not LEDGER.is_file()):
        raise PermissionError('The exact OOM owner and sole original ledger are required')
    journal = checked(evidence['journal']).read_text()
    if 'oom-kill' not in journal or 'OOM killer' not in journal:
        raise ValueError('The saved own-unit journal does not establish the reported OOM')
    seen = subprocess.run(['systemctl', '--user', 'show', UNIT, '--no-pager',
        '--property=MainPID,ActiveState,SubState,LoadState'], env=user_manager_environment(),
        capture_output=True, text=True, timeout=20)
    state = dict(line.split('=', 1) for line in seen.stdout.splitlines() if '=' in line)
    if seen.returncode or state.get('MainPID') != '0' or state.get('ActiveState') not in {'inactive', 'failed'}:
        raise PermissionError('A live or ambiguous API owner cannot be reconciled')
    expected = evidence['reserved_requests']
    ids = [row['request_id'] for row in expected]
    if len(ids) != 5 or len(set(ids)) != 5:
        raise ValueError('Only these five OOM-interrupted requests are in scope')
    with sqlite3.connect(LEDGER.resolve().as_uri()+'?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        if {row[0] for row in db.execute("SELECT request_id FROM requests WHERE status='reserved'")} != set(ids):
            raise ValueError('The live-reservation set changed since the owner exit audit')
        rows = read_rows(db, ids)
        if rows != expected:
            raise ValueError('The exact original request evidence changed')
    OUT.mkdir(parents=True)
    intent = write_new(OUT/'intent.json', {'version': VERSION, 'source': reference(__file__),
        'exit_evidence': evidence_ref, 'owner_inactive': state, 'requests_before': rows,
        'classification': 'administrative_owner_OOM_with_no_durable_response_or_settlement',
        'provider_error_observed': False, 'unknown_reservations_released': False,
        'automatic_retry': False, 'unix': time.time()})
    ledger = api.BudgetLedger(LEDGER, max_concurrency=64)
    before, after = mark_unknown(ledger, rows)
    with sqlite3.connect(LEDGER.resolve().as_uri()+'?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        updated = [dict(db.execute('SELECT * FROM requests WHERE request_id=?',(key,)).fetchone()) for key in ids]
    if any(row['status'] != 'uncertain' or row['reserved_nanoyuan'] != api.ABSOLUTE_RESERVATION_NANOYUAN
           or row['usage_json'] is not None for row in updated):
        raise RuntimeError('Unknown outcomes were not retained under their full original cash bound')
    return write_new(OUT/'completed.json', {'version': VERSION, 'intent': intent, 'unix': time.time(),
        'before': before, 'after': after, 'requests_after': updated,
        'reserved_requests_after': after['inflight_count'], 'unknown_reservations_released': False,
        'new_API_cash_budget': False, 'new_model_calls': 0, 'settled_usage_changed': False,
        'provider_HTTP_or_transport_error_fabricated': False,
        'administrative_classification': 'APIUncertainFailure after proven owner OOM; no provider response observed'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(execute(), ensure_ascii=False))
