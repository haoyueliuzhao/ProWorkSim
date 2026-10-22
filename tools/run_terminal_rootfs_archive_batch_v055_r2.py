"""Run the fixed 51-new-terminal-clone plan through the original two-slot scheduler."""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import threading

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
RUN = ROOT / 'runs/software-benchmark-v055'
ARCHIVE = RUN / 'terminal-rootfs-archive-r2'
PLAN = ARCHIVE / 'plan.json'
PLAN_SHA = '0a221e788e1730e934ea68433d6111407efa7d76866b2c2e10f369ac53a1eb83'
HELPER = ROOT / 'tools/archive_terminal_rootfs_v055_r2.py'
HELPER_SHA = '875d0a44f5bad804848722b5ff59a731858555e8c01edf5f36c69d23c0a7341e'
ORIGINAL_BATCH = ROOT / 'tools/run_terminal_rootfs_archive_batch_v055_r1.py'
ORIGINAL_BATCH_SHA = '71020bcdcbad655763b938665dc8183f219c9bda24a7db626739f45d7d664bf2'
OUT = RUN / 'terminal-rootfs-archive-batch-r2'
VERSION = 'v055-terminal-rootfs-archive-finite-batch-r2'
COUNT = 51


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(path, name, expected_sha):
    if digest(path) != expected_sha:
        raise ValueError('A frozen dependency changed: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def engine():
    base = load_module(ORIGINAL_BATCH, 'terminal_batch_r2_original', ORIGINAL_BATCH_SHA)
    base.ARCHIVE, base.PLAN, base.PLAN_SHA = ARCHIVE, PLAN, PLAN_SHA
    base.HELPER, base.HELPER_SHA, base.OUT, base.VERSION = HELPER, HELPER_SHA, OUT, VERSION
    return base


def sealed_plan():
    if os.getuid() != 1021 or os.geteuid() != 1021:
        raise PermissionError('Only the unprivileged project owner coordinates this finite batch')
    if PLAN.resolve() != PLAN or digest(PLAN) != PLAN_SHA:
        raise ValueError('The independent 51-item plan changed')
    wrapper = load_module(HELPER, 'terminal_batch_r2_namespace', HELPER_SHA)
    return wrapper.validate_plan(wrapper.original(), json.loads(PLAN.read_bytes()))


def worker_command(operation, item):
    if operation not in {'archive', 'release'}:
        raise ValueError('Batch only archives and releases exact allowlisted items')
    unit = f'proworksim-v055-terminal-batch-r2-{item["item_id"]}-{operation}.service'
    command = ['sudo', '-n', '/usr/bin/systemd-run', '--wait', '--pipe', '--collect', '--quiet',
               '--unit=' + unit, '--property=CPUQuota=200%', '--property=MemoryMax=2G',
               '--property=IOWeight=10', '--property=Nice=10', '--property=RuntimeMaxSec=1800',
               '--property=KillMode=control-group', '--property=Restart=no',
               '--setenv=SUDO_UID=1021', '--setenv=SUDO_GID=1022', '/usr/bin/python3', '-B',
               str(HELPER), operation, '--plan', str(PLAN), '--sha256', PLAN_SHA,
               '--source-sha256', HELPER_SHA, '--item-id', item['item_id']]
    return unit, command


class BoundedInvoker:
    """Use independent unit names with the original failure/liveness policy."""
    def __init__(self, stop):
        self.stop = stop

    def __call__(self, operation, item):
        unit, command = worker_command(operation, item)
        log = OUT / (item['item_id'] + '-' + operation + '.log')
        failure = None
        with log.open('x') as stream:
            try:
                result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                        timeout=1900, check=False)
                if result.returncode:
                    failure = RuntimeError(f'{operation} failed with exit {result.returncode}; retained log {log}')
            except subprocess.TimeoutExpired:
                failure = RuntimeError(f'{operation} systemd wait exceeded 1900 seconds; retained log {log}')
        if failure is not None:
            try:
                observed = subprocess.run(['/usr/bin/systemctl', 'show', unit, '--property=ActiveState,MainPID'],
                                          capture_output=True, text=True, timeout=30, check=False)
            except (OSError, subprocess.TimeoutExpired):
                self.stop.set()
                raise RuntimeError('Failed worker liveness observation unavailable; no new cleanup starts') from failure
            state = dict(x.split('=', 1) for x in observed.stdout.splitlines() if '=' in x)
            if state.get('ActiveState') not in {'inactive', 'failed'} or state.get('MainPID') != '0':
                self.stop.set()
                raise RuntimeError('Cannot prove failed archive worker closed; no new cleanup starts') from failure
            raise failure


def progress(base, plan, source_sha):
    class NewTerminalProgress(base.Progress):
        def __init__(self):
            self.lock = threading.Lock()
            self.value = {'version': VERSION, 'started_utc': base.now(), 'updated_utc': base.now(),
                          'status': 'running', 'source_sha256': source_sha,
                          'plan_sha256': PLAN_SHA, 'archive_source_sha256': HELPER_SHA,
                          'original_batch_source_sha256': ORIGINAL_BATCH_SHA,
                          'maximum_parallel_slot_groups': 2, 'planned_items': COUNT,
                          'rows': {x['item_id']: {'slot_id': x['slot_id'], 'status': 'pending'} for x in plan['items']},
                          'model_calls': 0, 'partial_or_failed_items_automatically_retried': False}
            self.flush()
    return NewTerminalProgress()


def control():
    """Only test new namespace binding; prior codec/scheduler controls stand."""
    value = sealed_plan()
    wrapper = load_module(HELPER, 'terminal_r2_control_namespace', HELPER_SHA)
    codec = wrapper.original()
    base = engine()
    assert codec.OUT == ARCHIVE and base.ARCHIVE == ARCHIVE and base.OUT == OUT
    assert len(value['items']) == COUNT
    old_plans = [json.loads(path.read_bytes()) for path in wrapper.OLD_PLANS]
    old_roots = {r['rootfs'] for old in old_plans for r in old['items']}
    old_ids = {r['item_id'] for old in old_plans for r in old['items']}
    assert not ({r['rootfs'] for r in value['items']} & old_roots)
    assert not ({r['item_id'] for r in value['items']} & old_ids)
    tertiary = [r for r in value['items'] if r['root_identity']['device'] == 66308]
    assert len(tertiary) == 16
    assert all(codec.source_path(r['rootfs']).relative_to(RUN).parts[0] == 'tertiary-volume-r1' for r in tertiary)
    rejected = []
    for label, mutate in (
        ('wrong_count', lambda x: x['items'].pop()),
        ('old_namespace', lambda x: x.update(version=old_plans[0]['version'])),
        ('cross_volume_payload', lambda x: x['items'][0].update(archive_directory='/data1/foreign')),
        ('wrong_tertiary_device', lambda x: next(r for r in x['items'] if r['root_identity']['device'] == 66308)['root_identity'].update(device=66307)),
        ('unregistered_volume', lambda x: x['items'][0].update(rootfs=x['items'][0]['rootfs'].replace('/queue-r1/', '/fourth-volume-r1/'))),
    ):
        changed = copy.deepcopy(value)
        mutate(changed)
        try:
            wrapper.validate_plan(codec, changed)
        except ValueError:
            rejected.append(label)
        else:
            raise AssertionError('Unsafe wrapper binding admitted: ' + label)
    item = value['items'][0]
    for operation in ('archive', 'release'):
        unit, command = worker_command(operation, item)
        assert unit.startswith('proworksim-v055-terminal-batch-r2-')
        assert str(PLAN) in command and PLAN_SHA in command and HELPER_SHA in command
        assert all(x in command for x in ('--property=CPUQuota=200%', '--property=MemoryMax=2G',
                                          '--property=IOWeight=10', '--property=KillMode=control-group',
                                          '--property=Restart=no'))
    assert len(base.groups_for(value['items'])) == len({r['slot_id'] for r in value['items']})
    print(json.dumps({'version': VERSION, 'passed': True, 'planned_items': COUNT,
                      'original_archive_and_scheduler_source_unchanged': True,
                      'old_63_and_primary_53_item_ids_and_sources_disjoint': True,
                      'tertiary_items_admitted_only_on_registered_device': len(tertiary),
                      'reject_controls': rejected, 'bounded_independent_worker_commands': True,
                      'actual_archive_calls': 0, 'actual_release_calls': 0, 'actual_sudo_calls': 0}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('run', 'control'))
    parser.add_argument('--source-sha256')
    args = parser.parse_args()
    if args.operation == 'control':
        control()
        return
    if args.source_sha256 is None or digest(__file__) != args.source_sha256:
        raise ValueError('Explicit exact independent batch implementation SHA is required')
    value = sealed_plan()
    base = engine()
    with (ARCHIVE / 'finite-batch-r1.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        OUT.mkdir(mode=0o700, exist_ok=False)
        state = progress(base, value, args.source_sha256)
        stop = threading.Event()
        invoke = BoundedInvoker(stop)
        base.schedule(base.groups_for(value['items']), lambda item: base.process_item(
            item, base.inspect_item, invoke, state.record, base.released_summary, stop))
        state.finish(stop.is_set())
        print(json.dumps({key: state.value[key] for key in ('status', 'processed_items', 'released_items',
                         'source_allocated_bytes', 'compressed_allocated_bytes',
                         'net_reclaimed_before_small_metadata_bytes')}))


if __name__ == '__main__':
    main()
