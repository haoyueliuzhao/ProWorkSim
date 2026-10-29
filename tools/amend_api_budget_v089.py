"""Seal and apply the explicitly authorized CNY1500 -> CNY1700 ledger amendment.

Only --execute writes the existing ledger. No request, fee, uncertain outcome,
cooldown or hard halt is cleared. A durable backup and intent precede one atomic
transaction, and --finalize can finish its receipt without repeating mutation.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time

from proworksim import software_benchmark_deepseek_api_v064 as prior
from proworksim import software_benchmark_deepseek_budget_v072 as old_budget
from proworksim import software_benchmark_deepseek_budget_v089 as amended
from proworksim import software_benchmark_dispatch_v066 as original
from proworksim import software_benchmark_api_scope_v088 as old_scope
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

VERSION = amended.VERSION
LEDGER = amended.LEDGER
OUT = amended.AMENDMENT_ROOT
PROPOSAL = OUT/'proposal.json'
INTENT = OUT/'intent.json'
COMPLETED = amended.AMENDMENT_COMPLETED
BACKUP = original.ROOT/'runs/software-benchmark-v089/budget-amendment-r1/ledger-before.sqlite3'
MARKER = amended.AMENDMENT_METADATA_KEY
USER_AUTHORIZATION = 'deepseek组增补两百预算，完成后对技术未知进行处理。Qwen速度过慢，排查原因'
OLD_POLICY = {**prior.POLICY, 'max_concurrency': 64}
NEW_POLICY = {**amended.POLICY, 'max_concurrency': 64}
TABLES = ('requests', 'response_observations', 'provider_protocol_events')


def load(path):
    return json.loads(Path(path).read_bytes())


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode()


def rows_fingerprint(db, query):
    digest, count = hashlib.sha256(), 0
    for row in db.execute(query):
        values = [{'blob_hex': item.hex()} if isinstance(item, bytes) else item for item in row]
        raw = encode(values)
        digest.update(len(raw).to_bytes(8, 'big'))
        digest.update(raw)
        count += 1
    return {'rows': count, 'sha256': digest.hexdigest()}


def snapshot(db):
    raw = db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()
    if raw is None:
        raise ValueError('The original ledger has no money policy')
    fingerprints = {name: rows_fingerprint(db, 'SELECT * FROM '+name+' ORDER BY 1') for name in TABLES}
    fingerprints['metadata_except_policy_and_amendment'] = rows_fingerprint(db,
        "SELECT name,value FROM metadata WHERE name NOT IN ('policy','"+MARKER+"') ORDER BY name")
    fingerprints['schema'] = rows_fingerprint(db,
        "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")
    return {'policy': json.loads(raw[0]), 'policy_sha256': hashlib.sha256(raw[0].encode()).hexdigest(),
        'preserved_fingerprints': fingerprints, 'totals': prior.BudgetLedger._totals(db),
        'request_statuses': dict(db.execute('SELECT status,COUNT(*) FROM requests GROUP BY status'))}


def validate_before(db, *, expected=None, original_rows=None):
    value = snapshot(db)
    if value['policy'] != OLD_POLICY:
        raise ValueError('Only the exact prior CNY1500 policy may be amended once')
    if db.execute('SELECT 1 FROM metadata WHERE name=?', (MARKER,)).fetchone():
        raise ValueError('The amendment identity is already consumed')
    if value['totals']['inflight'] or value['request_statuses'].get('reserved', 0):
        raise ValueError('Every original in-flight cash reservation must first be terminal')
    if value['totals']['committed'] > prior.CAP_NANOYUAN:
        raise ValueError('An overcommitted original ledger requires separate investigation')
    old_budget.validate_bounded_uncertainty(db, rows=original_rows)
    if expected is not None and value != expected:
        raise ValueError('Original ledger evidence changed after the sealed proposal')
    return value


def apply_policy_change(db, *, expected, proposal_ref, backup_ref):
    if not db.in_transaction:
        raise ValueError('Amend only inside the caller-owned immediate transaction')
    before = snapshot(db)
    if before != expected or before['policy'] != OLD_POLICY or before['totals']['inflight']:
        raise ValueError('The transaction no longer sees the exact authorized old ledger')
    if db.execute('SELECT 1 FROM metadata WHERE name=?', (MARKER,)).fetchone():
        raise ValueError('The exact increase has already been applied')
    if ({key for key in OLD_POLICY if OLD_POLICY[key] != NEW_POLICY[key]} != {'version', 'cap_nanoyuan'}
            or set(OLD_POLICY) != set(NEW_POLICY)
            or NEW_POLICY['cap_nanoyuan']-OLD_POLICY['cap_nanoyuan'] != 200*prior.NANOYUAN):
        raise ValueError('Only the explicitly approved CNY200 cap and version may change')
    marker = {'version': VERSION, 'proposal': proposal_ref, 'backup': backup_ref,
        'old_policy_sha256': before['policy_sha256'],
        'new_policy_sha256': hashlib.sha256(prior.transport._json(NEW_POLICY).encode()).hexdigest(),
        'old_cap_nanoyuan': prior.CAP_NANOYUAN, 'new_cap_nanoyuan': amended.CAP_NANOYUAN,
        'increase_nanoyuan': 200*prior.NANOYUAN,
        'preserved_fingerprints': before['preserved_fingerprints'],
        'totals_before': before['totals'], 'request_statuses_before': before['request_statuses'],
        'unknown_reservations_released': False, 'existing_requests_replayed': False}
    changed = db.execute("UPDATE metadata SET value=? WHERE name='policy' AND value=?",
        (prior.transport._json(NEW_POLICY), prior.transport._json(OLD_POLICY)))
    if changed.rowcount != 1:
        raise ValueError('The exact old policy bytes changed before the update')
    db.execute('INSERT INTO metadata(name,value) VALUES(?,?)', (MARKER, prior.transport._json(marker)))
    after = snapshot(db)
    if (after['policy'] != NEW_POLICY or after['preserved_fingerprints'] != before['preserved_fingerprints']
            or after['totals'] != before['totals'] or after['request_statuses'] != before['request_statuses']):
        raise ValueError('A financial row or non-policy setting changed inside the amendment')
    return marker, after


def exact_owner_quiet():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Budget amendment is an ordinary-user operation')
    spec_ref = reference(old_scope.API_ROOT/'coordinator-unit.json')
    spec = load(checked(spec_ref))
    if (spec.get('unit') != old_scope.API_UNIT or spec.get('user_id') != os.getuid()
            or spec.get('role') != 'api'
            or spec.get('entrypoint', {}).get('path') != str(original.ROOT/'tools/run_api_recovery_v088.py')):
        raise PermissionError('The latest API owner specification is not the expected project unit')
    checked(spec['entrypoint'])
    result = subprocess.run(['systemctl', '--user', 'show', old_scope.API_UNIT, '--no-pager',
        '--property=ActiveState,SubState,MainPID'], env=user_manager_environment(),
        capture_output=True, text=True, timeout=20)
    properties = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if result.returncode or properties.get('MainPID') != '0' or properties.get('ActiveState') not in ('inactive', 'failed'):
        raise PermissionError('The prior API manager has not stopped')
    summary_ref = reference(old_scope.API_ROOT/'run-summary.json')
    summary = load(checked(summary_ref))
    if (summary.get('failure') is not None
            or summary.get('provider_failures', {}).get('DEEPSEEK', {}).get('reason') != 'api_monetary_budget_exhausted'
            or summary.get('pending_grading_jobs') or summary.get('retained_objects')):
        raise ValueError('Require the completed original budget boundary, not an unresolved failure')
    release_ref = reference(old_scope.API_ROOT/'coordinator-capacity-released.json')
    release = load(checked(release_ref))
    if old_scope.LEASE_FILE.exists() or release.get('claim') != reference(old_scope.CLAIM_FILE) or release.get('quiescent') is not True:
        raise ValueError('The old exact API management reservation has not been released')
    for path in (original.BATCH_ROOT/'resource-claims').glob('active-*.json'):
        item = load(path)
        spec = item.get('spec', {})
        if ':DEEPSEEK_' in spec.get('slot_id', '') or str(spec.get('unit', '')).endswith('-api.service'):
            raise ValueError('An API resource or manager is still active')
    return {'unit_specification': spec_ref, 'unit': old_scope.API_UNIT, 'properties': properties,
            'run_summary': summary_ref, 'release': release_ref, 'observed_unix': time.time(),
            'Qwen_inspected_or_modified': False}


def open_read(path=LEDGER):
    db = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    return db


def prepare():
    if PROPOSAL.exists():
        raise FileExistsError('Do not overwrite a budget amendment proposal')
    quiet = exact_owner_quiet()
    with closing(open_read()) as db:
        before = validate_before(db)
    OUT.mkdir(parents=True, exist_ok=True)
    proposal = {'version': VERSION, 'status': 'approved_explicit_user_increase',
        'explicit_user_authorization': USER_AUTHORIZATION, 'ledger': str(LEDGER),
        'sources': [reference(path) for path in (
            __file__, amended.__file__, prior.__file__, prior.transport.__file__,
            old_budget.__file__, old_scope.__file__, original.__file__,
            amended.fd_policy.__file__, amended.wire.__file__, amended.original_reader.__file__)],
        'old_policy': OLD_POLICY, 'new_policy': NEW_POLICY,
        'old_cap_CNY': '1500.00', 'new_cap_CNY': '1700.00', 'increase_CNY': '200.00',
        'old_owner_quiet': quiet, 'before': before, 'backup_path': str(BACKUP),
        'only_mutations': ['metadata.policy cap and version', 'metadata.budget_amendment_v089 audit marker'],
        'request_rows_changed': False, 'old_unknown_reservations_released': False,
        'new_model_calls': 0, 'root_operations': 0, 'prepared_unix': time.time()}
    return write_new(PROPOSAL, proposal)


def verified_proposal():
    proposal_ref = reference(PROPOSAL)
    proposal = load(checked(proposal_ref))
    for ref in proposal['sources']:
        checked(ref)
    if (proposal.get('version') != VERSION or proposal.get('status') != 'approved_explicit_user_increase'
            or proposal.get('explicit_user_authorization') != USER_AUTHORIZATION
            or proposal.get('ledger') != str(LEDGER) or proposal.get('old_policy') != OLD_POLICY
            or proposal.get('new_policy') != NEW_POLICY or proposal.get('backup_path') != str(BACKUP)):
        raise PermissionError('The exact CNY200 same-ledger amendment differs')
    return proposal_ref, proposal


def execute():
    proposal_ref, proposal = verified_proposal()
    if INTENT.exists() or COMPLETED.exists() or BACKUP.exists():
        raise FileExistsError('This mutation identity is single use; inspect or finalize existing evidence')
    quiet = exact_owner_quiet()
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    with closing(open_read()) as source, closing(sqlite3.connect(BACKUP)) as destination:
        validate_before(source, expected=proposal['before'])
        source.backup(destination)
    with BACKUP.open('rb') as stream:
        os.fsync(stream.fileno())
    directory_fd = os.open(BACKUP.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    with closing(open_read(BACKUP)) as copied:
        if snapshot(copied) != proposal['before']:
            raise ValueError('The retained SQLite backup is not the exact old logical snapshot')
    backup_ref = reference(BACKUP)
    intent = write_new(INTENT, {'version': VERSION, 'proposal': proposal_ref,
        'backup': backup_ref, 'owner_quiet': quiet, 'unix': time.time(),
        'mutation_count_allowed': 1, 'existing_requests_replayed': False})
    lock_path = original.BATCH_ROOT/'resource-claims/allocation.lock'
    with lock_path.open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        exact_owner_quiet()
        with closing(sqlite3.connect(LEDGER, timeout=30)) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            try:
                validate_before(db, expected=proposal['before'])
                apply_policy_change(db, expected=proposal['before'], proposal_ref=proposal_ref, backup_ref=backup_ref)
                db.commit()
            except BaseException:
                db.rollback()
                raise
    return finalize(intent_ref=intent)


def finalize(*, intent_ref=None):
    """Finish receipt after a committed transaction, never repeat the cap write."""
    if COMPLETED.exists():
        return {'status': 'already_completed', 'receipt': reference(COMPLETED), 'mutations': 0}
    proposal_ref, proposal = verified_proposal()
    intent_ref = intent_ref or reference(INTENT)
    intent = load(checked(intent_ref))
    if intent.get('proposal') != proposal_ref:
        raise ValueError('Intent refers to another budget proposal')
    checked(intent['backup'])
    with closing(open_read()) as db:
        after = snapshot(db)
        raw = db.execute('SELECT value FROM metadata WHERE name=?', (MARKER,)).fetchone()
    if raw is None:
        raise ValueError('No committed amendment marker; never invent or repeat a transaction')
    marker = json.loads(raw[0])
    before = proposal['before']
    if (marker.get('proposal') != proposal_ref or marker.get('backup') != intent['backup']
            or after['policy'] != NEW_POLICY
            or after['preserved_fingerprints'] != before['preserved_fingerprints']
            or after['totals'] != before['totals'] or after['request_statuses'] != before['request_statuses']):
        raise ValueError('Committed ledger does not preserve the authorized original records')
    return write_new(COMPLETED, {'version': VERSION, 'committed': True, 'ledger': str(LEDGER),
        'proposal': proposal_ref, 'intent': intent_ref, 'backup': intent['backup'],
        'old_cap_nanoyuan': prior.CAP_NANOYUAN, 'new_cap_nanoyuan': amended.CAP_NANOYUAN,
        'explicit_increase_nanoyuan': 200*prior.NANOYUAN, 'before': before, 'after': after,
        'amendment_metadata': marker, 'all_existing_financial_rows_preserved': True,
        'unknown_reservations_released': False, 'original_requests_replayed': False,
        'new_model_calls': 0, 'root_operations': 0, 'finished_unix': time.time()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--execute', action='store_true')
    group.add_argument('--finalize', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else execute() if args.execute else finalize(), ensure_ascii=False))
