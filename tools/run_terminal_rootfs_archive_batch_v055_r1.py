"""Finite two-lane driver for the sealed 63-rootfs lossless archive plan.

The user process only coordinates. Each actual archive/release runs in its own
bounded system service. Partial work is retained and never implicitly retried.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
ARCHIVE = ROOT / 'runs/software-benchmark-v055/terminal-rootfs-archive-r1'
PLAN = ARCHIVE / 'plan.json'
PLAN_SHA = '2842e8a4ce9476706fce081e9c1b710f29be89dd2caf86c014b850200bd6d8fb'
HELPER = ROOT / 'tools/archive_terminal_rootfs_v055_r1.py'
HELPER_SHA = 'a1929b16a0deb0884e08ea66b542451d7bd8780ef6a6e936fd47a1661b233e13'
OUT = ROOT / 'runs/software-benchmark-v055/terminal-rootfs-archive-batch-r1'
VERSION = 'v055-terminal-rootfs-archive-finite-batch-r1'
TERMINAL = {'released', 'already_released', 'partial_skipped', 'failed', 'batch_guard_stopped'}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sealed_plan():
    if os.geteuid() != 1021 or os.getuid() != 1021:
        raise PermissionError('Only the registered unprivileged project owner coordinates this batch')
    if PLAN.resolve() != PLAN or digest(PLAN) != PLAN_SHA or digest(HELPER) != HELPER_SHA:
        raise ValueError('Original approved plan or archival implementation changed')
    value = json.loads(PLAN.read_bytes())
    if len(value['items']) != 63 or len({x['item_id'] for x in value['items']}) != 63:
        raise ValueError('This batch accepts exactly the frozen 63 unique items')
    return value


def groups_for(items):
    groups = {}
    claims = {}
    for item in items:
        slot = item['slot_id']
        claim = item['quiescence']['path']
        if slot in claims and claims[slot] != claim:
            raise ValueError('One slot must bind one original claim')
        claims[slot] = claim
        groups.setdefault(slot, []).append(item)
    if len(set(claims.values())) != len(claims):
        raise ValueError('Distinct slots cannot acquire the same original claim concurrently')
    return list(groups.values())


def verified_proof(item):
    path = ARCHIVE / item['item_id'] / 'verified.json'
    value = json.loads(path.read_bytes())
    if (value.get('original_rootfs') != item['rootfs'] or value.get('item_id') != item['item_id']
            or value.get('plan', {}).get('sha256') != PLAN_SHA
            or value.get('archive', {}).get('path') != str(Path(item['archive_directory']) / 'rootfs.tar.zst')
            or value.get('verification', {}).get('full_decompression_content_and_metadata_verified') is not True):
        raise ValueError('Successful full archive verification is not bound to this item')
    return value


def released_summary(item):
    value = json.loads((ARCHIVE / item['item_id'] / 'released.json').read_bytes())
    proof = verified_proof(item)
    source = Path(item['rootfs'])
    if (value.get('rootfs_removed') is not True or value.get('original_rootfs') != item['rootfs']
            or value.get('archive') != proof['archive'] or source.exists() or source.is_symlink()):
        raise ValueError('Released receipt and actual source disappearance do not agree')
    archive = Path(proof['archive']['path'])
    st = archive.stat()
    if not archive.is_file() or archive.is_symlink() or st.st_size != proof['archive']['bytes']:
        raise ValueError('Retained compressed archive is missing or changed size')
    allocated = st.st_blocks * 512
    return {'source_allocated_bytes': value['source_allocated_bytes'],
            'compressed_allocated_bytes': allocated, 'compressed_logical_bytes': st.st_size,
            'net_reclaimed_before_small_metadata_bytes': value['source_allocated_bytes'] - allocated,
            'release_receipt': str(ARCHIVE / item['item_id'] / 'released.json')}


def inspect_item(item):
    directory = ARCHIVE / item['item_id']
    payload = Path(item['archive_directory'])
    if (directory / 'released.json').exists():
        return {'state': 'released', 'summary': released_summary(item)}
    if not Path(item['rootfs']).is_dir() or Path(item['rootfs']).is_symlink():
        raise ValueError('Original source vanished without a trusted release receipt')
    if Path(item['rootfs']).with_name('rootfs.lossless-archive-r1.json').exists():
        return {'state': 'partial'}
    if (directory / 'verified.json').exists():
        verified_proof(item)
        return {'state': 'verified'}
    if directory.exists() or payload.exists():
        return {'state': 'partial'}
    return {'state': 'new'}


class Progress:
    def __init__(self, plan, source_sha):
        self.lock = threading.Lock()
        self.value = {'version': VERSION, 'started_utc': now(), 'updated_utc': now(),
                      'status': 'running', 'source_sha256': source_sha,
                      'plan_sha256': PLAN_SHA, 'archive_source_sha256': HELPER_SHA,
                      'maximum_parallel_slot_groups': 2, 'planned_items': 63,
                      'rows': {x['item_id']: {'slot_id': x['slot_id'], 'status': 'pending'} for x in plan['items']},
                      'model_calls': 0, 'partial_or_failed_items_automatically_retried': False}
        self.flush()

    def flush(self):
        rows = list(self.value['rows'].values())
        self.value['updated_utc'] = now()
        self.value['processed_items'] = sum(r['status'] in TERMINAL for r in rows)
        self.value['released_items'] = sum(r['status'] in {'released', 'already_released'} for r in rows)
        for key in ('source_allocated_bytes', 'compressed_allocated_bytes', 'net_reclaimed_before_small_metadata_bytes'):
            self.value[key] = sum(r.get('summary', {}).get(key, 0) for r in rows)
        raw = (json.dumps(self.value, sort_keys=True, indent=2) + '\n').encode()
        partial = OUT / 'state.json.next'
        with partial.open('wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(partial, OUT / 'state.json')

    def record(self, item, status, **detail):
        with self.lock:
            self.value['rows'][item['item_id']].update({'status': status, 'updated_utc': now(), **detail})
            event = {'utc': now(), 'item_id': item['item_id'], 'slot_id': item['slot_id'], 'status': status, **detail}
            with (OUT / 'progress.jsonl').open('a') as stream:
                stream.write(json.dumps(event, sort_keys=True) + '\n')
                stream.flush()
            self.flush()

    def finish(self, guarded):
        with self.lock:
            self.value['status'] = 'stopped_by_worker_liveness_guard' if guarded else 'complete'
            self.value['finished_utc'] = now()
            self.flush()


class BoundedInvoker:
    def __init__(self, stop):
        self.stop = stop

    def __call__(self, operation, item):
        unit = f'proworksim-v055-terminal-batch-r1-{item["item_id"]}-{operation}.service'
        log = OUT / (item['item_id'] + '-' + operation + '.log')
        command = ['sudo', '-n', '/usr/bin/systemd-run', '--wait', '--pipe', '--collect', '--quiet',
                   '--unit=' + unit, '--property=CPUQuota=200%', '--property=MemoryMax=2G',
                   '--property=IOWeight=10', '--property=Nice=10', '--property=RuntimeMaxSec=1800',
                   '--property=KillMode=control-group', '--property=Restart=no',
                   '--setenv=SUDO_UID=1021', '--setenv=SUDO_GID=1022', '/usr/bin/python3', str(HELPER), operation,
                   '--plan', str(PLAN), '--sha256', PLAN_SHA, '--source-sha256', HELPER_SHA, '--item-id', item['item_id']]
        failure = None
        with log.open('x') as stream:
            try:
                result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=1900, check=False)
                if result.returncode:
                    failure = RuntimeError(f'{operation} failed with exit {result.returncode}; retained log {log}')
            except subprocess.TimeoutExpired:
                failure = RuntimeError(f'{operation} systemd wait exceeded 1900 seconds; retained log {log}')
        if failure is not None:
            # Ordinary closed failures continue. If closure itself is unknown,
            # do not replace an unaccounted live worker with a third worker.
            try:
                observed = subprocess.run(['/usr/bin/systemctl', 'show', unit, '--property=ActiveState,MainPID'],
                                          capture_output=True, text=True, timeout=30, check=False)
            except (OSError, subprocess.TimeoutExpired):
                self.stop.set()
                raise RuntimeError('Failed worker liveness observation is unavailable; no new cleanup work starts') from failure
            state = dict(x.split('=', 1) for x in observed.stdout.splitlines() if '=' in x)
            if state.get('ActiveState') not in {'inactive', 'failed'} or state.get('MainPID') != '0':
                self.stop.set()
                raise RuntimeError('Cannot prove failed archive worker is closed; no new cleanup work starts') from failure
            raise failure


def process_item(item, inspect, invoke, record, summarize, stop):
    if stop.is_set():
        record(item, 'batch_guard_stopped')
        return
    try:
        before = inspect(item)
        if before['state'] == 'released':
            record(item, 'already_released', summary=before['summary'])
            return
        if before['state'] == 'partial':
            record(item, 'partial_skipped', reason='Preserve prior partial/failure; no automatic retry')
            return
        if before['state'] == 'new':
            record(item, 'running_archive')
            invoke('archive', item)
            if inspect(item)['state'] != 'verified':
                raise RuntimeError('Archive closed without the required full verification receipt')
        record(item, 'running_release')
        invoke('release', item)
        record(item, 'released', summary=summarize(item))
    except Exception as error:
        record(item, 'failed', error={'type': type(error).__name__, 'message': str(error)}, automatic_retry=False)


def schedule(groups, handle):
    def one_group(items):
        for item in items:
            handle(item)
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix='rootfs-archive-slot') as executor:
        futures = [executor.submit(one_group, group) for group in groups]
        for future in futures:
            future.result()


def control():
    """Pure in-memory scheduler control: no filesystem I/O, subprocess or sudo."""
    items = []
    for index, (slot, state) in enumerate([('a', 'released'), ('a', 'verified'), ('b', 'partial'),
                                         ('b', 'new'), ('c', 'new'), ('c', 'new'), ('d', 'new')]):
        items.append({'item_id': str(index), 'slot_id': slot, 'quiescence': {'path': '/fixture/' + slot}, 'initial': state})
    states = {x['item_id']: x['initial'] for x in items}
    actions, records, active, peak = [], [], set(), [0]
    lock = threading.Lock()
    stop = threading.Event()
    def inspect(item):
        return {'state': states[item['item_id']], 'summary': {'fixture': True}}
    def invoke(operation, item):
        with lock:
            assert item['slot_id'] not in active
            active.add(item['slot_id'])
            peak[0] = max(peak[0], len(active))
            assert len(active) <= 2
            actions.append((item['item_id'], operation))
        try:
            time.sleep(0.005)
            if item['item_id'] == '4' and operation == 'archive':
                raise RuntimeError('Fixture archive failure')
            if item['item_id'] == '6' and operation == 'release':
                raise RuntimeError('Fixture release failure')
            states[item['item_id']] = 'verified' if operation == 'archive' else 'released'
        finally:
            with lock:
                active.remove(item['slot_id'])
    def record(item, status, **details):
        with lock:
            records.append((item['item_id'], status))
    schedule(groups_for(items), lambda x: process_item(x, inspect, invoke, record, lambda _: {'fixture': True}, stop))
    assert ('0', 'already_released') in records and not any(i == '0' for i, _ in actions)
    assert [op for i, op in actions if i == '1'] == ['release']
    assert ('2', 'partial_skipped') in records and not any(i == '2' for i, _ in actions)
    assert ('4', 'failed') in records and ('5', 'released') in records and ('6', 'failed') in records
    assert ('4', 'release') not in actions and peak[0] == 2
    print(json.dumps({'version': VERSION, 'passed': True, 'actual_sudo_calls': 0, 'actual_filesystem_writes': 0,
                      'controls': ['released_skipped_and_counted', 'verified_release_only', 'partial_preserved_without_retry',
                                   'archive_failure_does_not_release', 'next_same_claim_continues_after_failure',
                                   'release_failure_isolated', 'maximum_two_distinct_claims_and_claim_serial_execution'],
                      'observed_peak_parallel_claims': peak[0]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('run', 'control'))
    parser.add_argument('--source-sha256')
    args = parser.parse_args()
    if args.operation == 'control':
        control()
        return
    if args.source_sha256 is None or digest(__file__) != args.source_sha256:
        raise ValueError('Explicit exact batch implementation SHA is required')
    plan = sealed_plan()
    with (ARCHIVE / 'finite-batch-r1.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        OUT.mkdir(mode=0o700, exist_ok=False)
        progress = Progress(plan, args.source_sha256)
        stop = threading.Event()
        invoke = BoundedInvoker(stop)
        schedule(groups_for(plan['items']), lambda x: process_item(x, inspect_item, invoke, progress.record, released_summary, stop))
        progress.finish(stop.is_set())
        print(json.dumps({key: progress.value[key] for key in ('status', 'processed_items', 'released_items',
                         'source_allocated_bytes', 'compressed_allocated_bytes', 'net_reclaimed_before_small_metadata_bytes')}))


if __name__ == '__main__':
    main()
