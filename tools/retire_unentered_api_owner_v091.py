"""Retire only the proven zero-consumption v089 owner; preserve its API parent."""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import select
import signal
import sqlite3
import subprocess
import time

from proworksim import software_benchmark_api_scope_v089 as old
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

VERSION = 'v091-exact-zero-consumption-owner-handoff-r1'
OUT = old.ROOT/'artifacts/software-benchmark-v091/unentered-handoff-r1'


def inspect_owner():
    result = subprocess.run(['systemctl', '--user', 'show', old.API_UNIT, '--no-pager',
        '--property=MainPID,ActiveState,SubState,Description,ControlGroup'],
        env=user_manager_environment(), capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError('Cannot establish exact user-manager ownership')
    value = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    spec = json.loads((old.API_ROOT/'coordinator-unit.json').read_bytes())
    pid = int(value.get('MainPID', '0'))
    if (os.getuid() == 0 or spec['user_id'] != os.getuid() or spec['unit'] != old.API_UNIT
            or value.get('Description') != 'ProWorkSim v089 api coordinator '+spec['ownership_token']
            or value.get('ActiveState') != 'active' or pid <= 0
            or Path(value.get('ControlGroup', '')).name != old.API_UNIT
            or Path('/proc', str(pid)).stat().st_uid != os.getuid()):
        raise PermissionError('Only the original exact ordinary-user owner may be signalled')
    folder = Path('/sys/fs/cgroup')/value['ControlGroup'].lstrip('/')
    if set((folder/'cgroup.procs').read_text().split()) != {str(pid)}:
        raise PermissionError('The owner has another process; this handoff cannot proceed')
    if Path('/proc', str(pid), 'cgroup').read_text().splitlines() != ['0::'+value['ControlGroup']]:
        raise PermissionError('The kernel process is outside its exact owner cgroup')
    fields = Path('/proc', str(pid), 'stat').read_text().rpartition(')')[2].split()
    return {**value, 'pid': pid, 'start_ticks': int(fields[19]), 'uid': os.getuid()}


def prove_zero_consumption():
    old.require_allowed()
    inventory = old.load(reference(old.INVENTORY_FILE))
    rows = inventory['rows']
    slots = {r['slot_id'] for r in rows}
    if len(slots) != 44 or {r['slot_index'] for r in rows} != set(range(6000, 6044)):
        raise ValueError('The exact fixed recovery panel changed')
    ledger = Path(inventory['API_ledger'])
    with closing(sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        count = db.execute('SELECT COUNT(*) FROM requests WHERE slot_id IN ('+
                           ','.join('?' for _ in slots)+')', sorted(slots)).fetchone()[0]
        inflight = db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0]
    if count or inflight:
        raise PermissionError('Model use or live API accounting prevents a zero-consumption handoff')
    resources = old.load(reference(old.PLAN_FILE))['resources']
    claim_root = old.original.BATCH_ROOT/'resource-claims'
    claims = [str(path) for key in resources for path in
              (claim_root/(key+'.json'), claim_root/('active-'+key+'.json')) if path.exists()]
    episodes = [str(old.original.BATCH_ROOT/'episodes'/str(r['slot_index'])) for r in rows
                if (old.original.BATCH_ROOT/'episodes'/str(r['slot_index'])).exists()]
    if claims or episodes:
        raise PermissionError('A physical recovery identity was consumed; do not replay it')
    progress = old.load(reference(old.API_ROOT/'progress.json'))
    pressure = progress.get('pressure', {})
    if (progress.get('entered_generation') != 0 or progress.get('effective_generation_limit') != 0
            or progress.get('actual_active_api_actors') != 0
            or progress.get('finished_generation') != 0 or progress.get('active_grading') != 0
            or pressure.get('admit') is not False
            or pressure.get('observation_error', {}).get('message') !=
               'Pressure cancellation must bind an active owned 5M API episode'):
        raise PermissionError('The recorded startup-only pressure deadlock is not established')
    events_path = old.API_ROOT/'events.jsonl'
    events = [json.loads(line) for line in events_path.read_text().splitlines() if line]
    if (len(events) != 12 or any(e.get('kind') != 'generation_scheduled' or
            e.get('slot_id') not in slots for e in events)):
        raise PermissionError('Owner events include actual execution or another phase')
    cursor = old.load(reference(old.API_ROOT/'cursor.json'))
    if any(cursor.get(k) for k in ('generation', 'scores', 'deliveries', 'active_grading',
                                  'active_grading_jobs', 'pending_grading_jobs', 'pending_scores')):
        raise PermissionError('Completed or active work must be retained by another handoff method')
    parent = old.parent_module()
    parent.require_qualified()
    parent_folder = Path('/sys/fs/cgroup')/parent.CGROUP.lstrip('/')
    if any(p.is_dir() for p in parent_folder.iterdir()) or (parent_folder/'cgroup.procs').read_text().strip():
        raise PermissionError('The original API parent has children')
    snapshots = {}
    for name in ('progress.json', 'pressure.json', 'cursor.json', 'actual-usage-summary.json'):
        value = json.loads((old.API_ROOT/name).read_bytes())
        snapshots[name] = write_new(OUT/'before-retirement'/name, value)
    return {'inventory': reference(old.INVENTORY_FILE), 'plan': reference(old.PLAN_FILE),
        'events': reference(events_path), 'snapshots': snapshots, 'slot_count': 44,
        'API_request_count': count, 'global_inflight_requests': inflight,
        'consumed_resource_claims': claims, 'episode_directories': episodes,
        'parent_created': reference(parent.CREATED), 'parent_empty': True,
        'logical_recovery_attempts_consumed': 0, 'old_records_overwritten': False}


def retire():
    if (OUT/'intent.json').exists():
        raise PermissionError('This exact handoff is single-use; inspect its receipt')
    before = inspect_owner()
    (OUT/'before-retirement').mkdir(parents=True, exist_ok=True)
    intent = write_new(OUT/'intent.json', {'version': VERSION, 'unix': time.time(),
        'source': reference(__file__), 'owner': before,
        'signals': ['SIGSTOP', 'SIGKILL only after zero-consumption proof'],
        'failure_action': 'SIGCONT while the verified original process still exists',
        'shared_host_configuration_changes': 0, 'GPU_operations': 0})
    fd = os.pidfd_open(before['pid'])
    stopped, killed = False, False
    try:
        if inspect_owner() != before:
            raise PermissionError('Owner identity changed before pause')
        signal.pidfd_send_signal(fd, signal.SIGSTOP)
        stopped = True
        for _ in range(50):
            state = Path('/proc', str(before['pid']), 'stat').read_text().rpartition(')')[2].split()[0]
            if state in ('T', 't'):
                break
            time.sleep(.02)
        else:
            raise RuntimeError('The original owner did not enter stopped state')
        if inspect_owner() != before:
            raise PermissionError('Owner identity changed while paused')
        proof = write_new(OUT/'zero-consumption-proof.json', prove_zero_consumption())
        signal.pidfd_send_signal(fd, signal.SIGKILL)
        killed = True
        poller = select.poll()
        poller.register(fd, select.POLLIN)
        if not poller.poll(10000):
            raise RuntimeError('Exact owner exit not confirmed; leave its lease intact')
        folder = Path('/sys/fs/cgroup')/before['ControlGroup'].lstrip('/')
        if folder.exists() and (folder/'cgroup.procs').read_text().strip():
            raise RuntimeError('Owned process residue; leave its lease intact')
        released = old.release_api_coordinator(reference(old.CLAIM_FILE))
        parent = old.parent_module()
        parent.require_qualified()
        return write_new(OUT/'completed.json', {'version': VERSION, 'unix': time.time(),
            'intent': intent, 'zero_consumption_proof': proof,
            'old_unit': old.API_UNIT, 'old_main_pid_exited': True,
            'old_manager_lease_released': released,
            'all_44_model_attempts_unconsumed': True, 'all_44_physical_identities_unconsumed': True,
            'original_API_parent_preserved': reference(parent.CREATED),
            'original_API_parent_stopped': False, 'model_calls_replayed': 0,
            'shared_host_configuration_changes': 0, 'GPU_operations': 0})
    finally:
        if stopped and not killed:
            signal.pidfd_send_signal(fd, signal.SIGCONT)
        os.close(fd)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', required=True, action='store_true')
    parser.parse_args()
    print(json.dumps(retire(), ensure_ascii=False))
