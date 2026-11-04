"""One explicit remaining-CNY45 grant on the original v105 cash ledger.

This changes only the cap and adds an audit marker. It never refunds an unknown
request, changes a response, dispatches a request, or starts an experiment.
"""
from __future__ import annotations

from contextlib import ExitStack, closing, contextmanager
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time

from . import software_benchmark_deepseek_api_v105 as prior
from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_ref_resident_v066 import user_manager_environment

ROOT = Path(__file__).resolve().parents[2]
VERSION = 'v122-explicit-remaining-cny45-cash-amendment-r1'
LEDGER = ROOT / 'runs/software-benchmark-v105/nonthinking-interface-r1/api-ledger.sqlite'
OUT = ROOT / 'artifacts/software-benchmark-v122/cash-amendment-r1'
GRANT_FILE = ROOT / 'config/v122-cash-amendment.json'
BACKUP = ROOT / 'runs/software-benchmark-v122/cash-amendment-r1/ledger-before.sqlite3'
COMPLETED = OUT / 'completed.json'
INTENT = OUT / 'intent.json'
MARKER = 'cash_amendment_v122'
MAX_CONCURRENCY = 16
REMAINING_NANOYUAN = 45 * prior.NANOYUAN
OLD_POLICY = {**prior.POLICY, 'max_concurrency': MAX_CONCURRENCY}
CLAIM_ROOTS = tuple(ROOT / 'runs' / batch / 'resource-claims' for batch in (
    'software-benchmark-v105/nonthinking-interface-r1',
    'software-benchmark-v111/aligned-interface-r1',
    'software-benchmark-v118/project-repaired-r1',
    'software-benchmark-v121/project-independent-recovery-r1',
))
UNITS = ('proworksim-v105-nonthinking.service', 'proworksim-v111-aligned.service',
         'proworksim-v118-project.service')


def encode(value):
    return prior.transport._json(value).encode()


def cny(value):
    return format(Decimal(value) / prior.NANOYUAN, 'f')


def write_once(path, value, *, raw=False):
    path = Path(path)
    data = value if raw else encode(value) + b'\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return reference(path)


def fingerprint(db, query):
    digest, count = hashlib.sha256(), 0
    for row in db.execute(query):
        values = [{'blob_hex': item.hex()} if isinstance(item, bytes) else item for item in row]
        data = encode(values)
        digest.update(len(data).to_bytes(8, 'big'))
        digest.update(data)
        count += 1
    return {'rows': count, 'sha256': digest.hexdigest()}


def snapshot(db):
    row = db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()
    if row is None:
        raise ValueError('Original money policy is missing')
    tables = [item[0] for item in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name!='metadata' ORDER BY name")]
    # Hash every existing non-policy table, including any future audit table.
    preserved = {name: fingerprint(db, 'SELECT * FROM "' + name.replace('"', '""') + '" ORDER BY rowid')
                 for name in tables}
    preserved['metadata_except_policy_and_marker'] = fingerprint(db,
        "SELECT name,value FROM metadata WHERE name NOT IN ('policy','cash_amendment_v122') ORDER BY name")
    preserved['schema'] = fingerprint(db,
        'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')
    return {'policy': json.loads(row[0]), 'policy_raw': row[0],
            'policy_sha256': hashlib.sha256(row[0].encode()).hexdigest(),
            'preserved': preserved, 'totals': prior.BudgetLedger._totals(db),
            'statuses': dict(db.execute('SELECT status,COUNT(*) FROM requests GROUP BY status'))}


def validate_before(db, *, expected=None):
    value = snapshot(db)
    if value['policy_raw'] != prior.transport._json(OLD_POLICY):
        raise ValueError('Only the exact old CNY350 policy can be amended')
    if db.execute('SELECT 1 FROM metadata WHERE name=?', (MARKER,)).fetchone():
        raise ValueError('This one-use cash amendment was already consumed')
    if value['totals']['inflight'] or value['statuses'].get('reserved', 0):
        raise ValueError('There is still an in-flight API reservation')
    committed = value['totals']['committed']
    if type(committed) is not int or not 0 <= committed <= prior.CAP_NANOYUAN:
        raise ValueError('Invalid or overcommitted original cash ledger')
    if committed + REMAINING_NANOYUAN <= prior.CAP_NANOYUAN:
        raise ValueError('This grant is an increase, not a reduction of existing available cash')
    if expected is not None and value != expected:
        raise ValueError('The original ledger changed after grant preparation')
    return value


def validate_grant(grant):
    before = grant['before']
    cap = before['totals']['committed'] + REMAINING_NANOYUAN
    if (grant.get('version') != VERSION or grant.get('authorized_remaining_nanoyuan') != REMAINING_NANOYUAN
            or grant.get('ledger') != str(LEDGER) or grant.get('old_policy') != OLD_POLICY
            or grant.get('new_policy') != {**OLD_POLICY, 'cap_nanoyuan': cap}
            or grant.get('new_cap_nanoyuan') != cap
            or grant.get('increase_nanoyuan') != cap - prior.CAP_NANOYUAN
            or grant.get('user_authorization') != '将剩余可用预算调整为45元'
            or before['policy'] != OLD_POLICY or before['totals']['inflight']
            or before['statuses'].get('reserved', 0)
            or cap <= prior.CAP_NANOYUAN):
        raise ValueError('The sealed remaining-CNY45 grant differs from the user authorization')
    return grant


def owner_quiet():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('The cash amendment must run as the ordinary project user')
    units = {}
    for unit in UNITS:
        result = subprocess.run(['systemctl', '--user', 'show', unit, '--no-pager',
            '--property=ActiveState,SubState,MainPID'], env=user_manager_environment(),
            capture_output=True, text=True, timeout=10)
        props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if result.returncode or props.get('MainPID') != '0' or props.get('ActiveState') not in ('inactive', 'failed'):
            raise PermissionError('Existing API owner is not proven stopped: ' + unit)
        units[unit] = props
    claims = {}
    for directory in CLAIM_ROOTS:
        if not directory.is_dir() or not (directory / 'allocation.lock').is_file():
            raise ValueError('A known API resource allocation root is missing')
        names = []
        for path in sorted(directory.glob('active-*.json')):
            item = json.loads(path.read_bytes())
            role = item.get('spec', {}).get('role', '')
            if 'coordinator' in path.name or role in ('auxiliary_coordinator', 'actor', 'controller'):
                raise ValueError('A previous API owner or generation environment is still leased: ' + str(path))
            names.append(path.name)
        claims[str(directory)] = {'no_api_or_generation_lease': True, 'other_active_names': names}
    release = ROOT / 'runs/software-benchmark-v121/project-independent-recovery-r1/api-coordinator/coordinator-capacity-released.json'
    release_value = json.loads(release.read_bytes())
    if (release_value.get('released') is not True or
            release_value.get('claim') != reference(release.parent / 'coordinator-capacity.json')):
        raise ValueError('The latest API coordinator release is not intact')
    return {'units': units, 'claims': claims, 'latest_release': reference(release), 'observed_unix': time.time()}


@contextmanager
def owner_locks():
    # Same locks used by the four original managers; no new owner can reserve
    # capacity while the old policy is being checked and replaced.
    with ExitStack() as stack:
        for directory in sorted(CLAIM_ROOTS):
            stream = stack.enter_context((directory / 'allocation.lock').open('rb'))
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def open_read(path=LEDGER):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    return db


def prepare():
    if GRANT_FILE.exists() or INTENT.exists() or COMPLETED.exists():
        raise FileExistsError('Do not overwrite the one-use v122 grant')
    with owner_locks():
        quiet = owner_quiet()
        with closing(open_read()) as db:
            before = validate_before(db)
    cap = before['totals']['committed'] + REMAINING_NANOYUAN
    old_policy = write_once(OUT / 'old-policy.json', before['policy_raw'].encode(), raw=True)
    sources = [reference(path) for path in (__file__, prior.__file__, prior.transport.__file__,
               ROOT / 'src/proworksim/software_benchmark_deepseek_api_v122.py',
               ROOT / 'tools/amend_api_budget_v122.py')]
    grant = {'version': VERSION, 'user_authorization': '将剩余可用预算调整为45元',
        'ledger': str(LEDGER), 'authorized_remaining_nanoyuan': REMAINING_NANOYUAN,
        'old_policy': OLD_POLICY, 'new_policy': {**OLD_POLICY, 'cap_nanoyuan': cap},
        'new_cap_nanoyuan': cap, 'increase_nanoyuan': cap - prior.CAP_NANOYUAN,
        'old_cap_CNY': cny(prior.CAP_NANOYUAN), 'new_cap_CNY': cny(cap),
        'increase_CNY': cny(cap - prior.CAP_NANOYUAN), 'available_CNY_at_commit': '45',
        'before': before, 'old_policy_backup': old_policy, 'owner_quiet': quiet,
        'sqlite_backup_path': str(BACKUP), 'sources': sources, 'prepared_unix': time.time(),
        'only_live_mutations': ['metadata.policy.cap_nanoyuan', 'metadata.' + MARKER],
        'old_requests_preserved': True, 'old_uncertain_reservations_released': False,
        'model_calls_authorized_by_this_grant': 0, 'new_neutral_calls': 0,
        'root_operations': 0, 'experiment_start_authorized_by_this_grant': False}
    validate_grant(grant)
    return write_once(GRANT_FILE, grant)


def verified_grant():
    ref = reference(GRANT_FILE)
    grant = validate_grant(json.loads(checked(ref).read_bytes()))
    for source in grant['sources']:
        checked(source)
    checked(grant['old_policy_backup'])
    return ref, grant


def apply_policy_change(db, *, grant, grant_ref, backup_ref, require_quiet):
    if not db.in_transaction:
        raise ValueError('Cash amendment requires the caller-owned immediate transaction')
    validate_grant(grant)
    quiet = require_quiet()
    before = validate_before(db, expected=grant['before'])
    marker = {'version': VERSION, 'grant': grant_ref, 'backup': backup_ref,
        'old_cap_nanoyuan': prior.CAP_NANOYUAN, 'new_cap_nanoyuan': grant['new_cap_nanoyuan'],
        'available_after_nanoyuan': REMAINING_NANOYUAN,
        'increase_nanoyuan': grant['increase_nanoyuan'], 'totals_before': before['totals'],
        'preserved_fingerprints': before['preserved'], 'old_policy_sha256': before['policy_sha256'],
        'new_policy_sha256': hashlib.sha256(encode(grant['new_policy'])).hexdigest(),
        'unknown_reservations_released': False, 'old_requests_replayed': False}
    changed = db.execute("UPDATE metadata SET value=? WHERE name='policy' AND value=?",
        (prior.transport._json(grant['new_policy']), before['policy_raw']))
    if changed.rowcount != 1:
        raise ValueError('Exact old policy changed during the amendment')
    db.execute('INSERT INTO metadata(name,value) VALUES(?,?)', (MARKER, prior.transport._json(marker)))
    after = snapshot(db)
    if (after['policy'] != grant['new_policy'] or after['preserved'] != before['preserved']
            or after['totals'] != before['totals'] or after['statuses'] != before['statuses']
            or after['policy']['cap_nanoyuan'] - after['totals']['committed'] != REMAINING_NANOYUAN):
        raise ValueError('A financial row or non-cap policy setting changed')
    return {'marker': marker, 'after': after, 'owner_quiet': quiet}


def execute():
    grant_ref, grant = verified_grant()
    if INTENT.exists() or COMPLETED.exists() or BACKUP.exists():
        raise FileExistsError('Single-use mutation already started; inspect or finalize, never repeat')
    with owner_locks():
        quiet = owner_quiet()
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        with closing(open_read()) as source, closing(sqlite3.connect(BACKUP)) as target:
            validate_before(source, expected=grant['before'])
            source.backup(target)
        with BACKUP.open('rb') as stream:
            os.fsync(stream.fileno())
        directory_fd = os.open(BACKUP.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        with closing(open_read(BACKUP)) as copied:
            if snapshot(copied) != grant['before']:
                raise ValueError('SQLite backup does not preserve the exact old logical state')
        backup_ref = reference(BACKUP)
        intent = write_once(INTENT, {'version': VERSION, 'grant': grant_ref, 'backup': backup_ref,
            'owner_quiet': quiet, 'allowed_mutations': 1, 'created_unix': time.time()})
        with closing(sqlite3.connect(LEDGER, timeout=30)) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN IMMEDIATE')
            try:
                apply_policy_change(db, grant=grant, grant_ref=grant_ref,
                                    backup_ref=backup_ref, require_quiet=owner_quiet)
                db.commit()
            except BaseException:
                db.rollback()
                raise
    return finalize(intent_ref=intent)


def finalize(*, intent_ref=None):
    if COMPLETED.exists():
        return {'status': 'already_completed', 'receipt': reference(COMPLETED), 'mutations': 0}
    grant_ref, grant = verified_grant()
    intent_ref = intent_ref or reference(INTENT)
    intent = json.loads(checked(intent_ref).read_bytes())
    checked(intent['backup'])
    with closing(open_read()) as db:
        after = snapshot(db)
        raw = db.execute('SELECT value FROM metadata WHERE name=?', (MARKER,)).fetchone()
    marker = json.loads(raw[0]) if raw else {}
    if (intent.get('grant') != grant_ref or marker.get('grant') != grant_ref
            or marker.get('backup') != intent['backup'] or marker.get('version') != VERSION
            or after['policy'] != grant['new_policy'] or after['preserved'] != grant['before']['preserved']
            or after['totals'] != grant['before']['totals'] or after['statuses'] != grant['before']['statuses']):
        raise ValueError('No matching committed amendment, or historical evidence changed')
    return write_once(COMPLETED, {'version': VERSION, 'committed': True, 'grant': grant_ref,
        'intent': intent_ref, 'backup': intent['backup'], 'old_policy_backup': grant['old_policy_backup'],
        'ledger': str(LEDGER), 'new_cap_nanoyuan': grant['new_cap_nanoyuan'],
        'available_nanoyuan': REMAINING_NANOYUAN, 'increase_nanoyuan': grant['increase_nanoyuan'],
        'new_cap_CNY': cny(grant['new_cap_nanoyuan']), 'available_CNY': '45',
        'increase_CNY': cny(grant['increase_nanoyuan']), 'before': grant['before'], 'after': after,
        'amendment_metadata': marker, 'all_existing_rows_preserved': True,
        'old_uncertain_reservations_released': False, 'new_model_calls': 0,
        'root_operations': 0, 'finished_unix': time.time()})
