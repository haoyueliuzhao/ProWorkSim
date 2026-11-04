"""Stop only the owned v131 manager, then relieve archives after writers stop.

This is an administrative recovery, not a model continuation. Never replay an
entered episode. MemoryMax, CPU, swap, containers and shared host settings stay
unchanged. MemoryHigh can change only after every owned producer is stopped.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import signal
import sqlite3
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / 'runs/software-benchmark-v131/fixed-organization-50-r1'
OUT = ROOT / 'runs/software-benchmark-v132/quiesce-r1'
UNIT = 'proworksim-v131-fixed-organizations.service'
GIB = 1024**3


def read(path):
    return json.loads(Path(path).read_bytes())


def ref(path):
    data = Path(path).read_bytes()
    return {'path': str(Path(path).resolve()), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT/name
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return ref(path)


def manager():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Only the original ordinary user may manage this unit')
    result = subprocess.run(['systemctl', '--user', 'show', UNIT,
        '--property=MainPID,ActiveState,SubState,MemoryMax,MemoryHigh,ControlGroup'],
        text=True, capture_output=True, check=True, timeout=15)
    props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    pid = int(props['MainPID'])
    if props['ActiveState'] != 'active' or pid <= 1 or int(props['MemoryMax']) != 32*GIB:
        raise ValueError('The exact active original bounded manager is required')
    proc = Path('/proc')/str(pid)
    groups = [line[3:] for line in (proc/'cgroup').read_text().splitlines() if line.startswith('0::')]
    if groups != [props['ControlGroup']] or Path(groups[0]).name != UNIT:
        raise PermissionError('Manager PID and unit cgroup differ')
    args = (proc/'cmdline').read_bytes().split(b'\0')
    expected = str(ROOT/'tools/run_fixed_organization_v131.py').encode()
    if expected not in args:
        raise PermissionError('Do not signal a replacement lifecycle or another entrypoint')
    status = (proc/'status').read_text().splitlines()
    uid = next(line for line in status if line.startswith('Uid:')).split()[1:]
    if any(int(item) != os.getuid() for item in uid):
        raise PermissionError('The owned manager has another UID')
    props['pid_start_ticks'] = (proc/'stat').read_text().split(') ', 1)[1].split()[19]
    props['pid'] = pid
    return props


def request_stop():
    if (OUT/'stop-intent.json').exists():
        raise ValueError('A consumed signal intent is not automatically repeated')
    grant = ROOT/'config/v131-fixed-organization-user-grant.json'
    if read(grant).get('status') != 'approved':
        raise PermissionError('Original bounded batch grant is required')
    recovery_grant = ROOT/'config/v132-controlled-handoff-user-grant.json'
    if (read(recovery_grant).get('status') != 'approved'
            or read(recovery_grant).get('user_reply') != '授权受控停止并交接修复'):
        raise PermissionError('Explicit consent to interrupt the original running attempts is required')
    before = manager()
    fd = os.pidfd_open(before['pid'])
    try:
        if manager() != before:
            raise ValueError('Manager identity changed before the one signal')
        intent = save('stop-intent.json', {'version': 'v132-owned-recovery-quiesce-r1',
            'unix': time.time(), 'user_instruction': '授权受控停止并交接修复',
            'recovery_grant': ref(recovery_grant), 'original_grant': ref(grant),
            'before': before, 'signal': 'SIGTERM', 'recipient': 'exact original main PID via pidfd',
            'reason': 'systematic candidate-export failure and archive memory.high thrashing',
            'no_SIGKILL': True, 'systemctl_stop_not_used': True, 'no_restart_deadline': True,
            'new_model_attempts': 0, 'original_called_attempts_not_replayed': True})
        signal.pidfd_send_signal(fd, signal.SIGTERM)
        return save('stop-sent.json', {'intent': intent, 'signal_sent_unix': time.time()})
    finally:
        os.close(fd)


def quiet_proof():
    intent = read(OUT/'stop-intent.json')
    read(OUT/'stop-sent.json')
    active = []
    blockers = []
    claims = BATCH/'resource-claims'
    for path in sorted(claims.glob('active-actor-*.json')):
        try:
            claim = read(path)
        except FileNotFoundError:
            continue
        key = claim['key']
        if claim['spec']['role'] != 'actor' or not key.startswith('actor-'):
            raise PermissionError('Unexpected active claim identity')
        folder = BATCH/'episodes'/key.removeprefix('actor-')
        proofs = [folder/name for name in ('final-writer-quiescence.json', 'writer-quiescence.json')]
        proofs.append(OUT/'writer-observations'/f'{key}.json')
        found = next((p for p in proofs if p.exists()), None)
        if found is None:
            blockers.append({'key': key, 'reason': 'no_stopped_writer_evidence'})
            continue
        value = read(found)
        writers = value.get('writers', [])
        if (value.get('all_quiet') is not True or value.get('errors')
                or value.get('create_result_unknown_roles')
                or any(w['state'].get('Running') or w['state'].get('Pid') for w in writers)):
            blockers.append({'key': key, 'reason': 'writer_quiescence_not_proven'})
            continue
        active.append({'key': key, 'writer_proof': ref(found)})
    money = {}
    for group in ('CHIEF', 'PIPELINE', 'REVIEW', 'SPRINT', 'MATRIX'):
        path = BATCH/'ledgers'/f'{group}.sqlite'
        with sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=3) as db:
            counts = dict(db.execute('SELECT status,count(*) FROM requests GROUP BY status'))
        money[group] = counts
        if counts.get('reserved', 0):
            blockers.append({'group': group, 'reason': 'API_reservations_still_inflight'})
    return {'unix': time.time(), 'original_manager': intent['before'],
        'active_actor_claims': active, 'ledger_status_counts': money, 'blockers': blockers,
        'passed': not blockers, 'no_new_requests_after_stop': 'original stop handler cancels all routes before API guard'}


def inspect_remaining_writers():
    """Read exact previously-entered containers; never stop, create or delete."""
    stop = read(OUT/'stop-sent.json')
    plan = read(BATCH/'execution-plan.json')
    rows = {row['slot_index']: row for row in plan['rows']}
    observations = []
    for blocker in quiet_proof()['blockers']:
        if blocker.get('reason') != 'no_stopped_writer_evidence':
            continue
        key = blocker['key']
        index = int(key.removeprefix('actor-'))
        episode = BATCH/'episodes'/str(index)
        entered = (episode/'entered.json').is_file()
        config = read(rows[index]['configuration']['path'])
        address = str(Path(config['scorer_request_base']['docker_socket']).resolve())
        writers = []
        for role in ('controller', 'actor'):
            claim_path = BATCH/'resource-claims'/f'{role}-{index}.json'
            if not claim_path.is_file():
                writers.append({'role': role, 'no_claim_yet': True,
                                'state': {'Running': None, 'Pid': None}})
                continue
            claim = read(claim_path)
            if claim['spec']['slot_id'] != rows[index]['slot_id']:
                raise PermissionError('Container claim belongs to another team')
            client = http.client.HTTPConnection('localhost', timeout=10)
            client.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.sock.settimeout(10)
            client.sock.connect(address)
            try:
                client.request('GET', '/containers/'+claim['docker_name']+'/json')
                response = client.getresponse()
                raw = response.read()
                if response.status == 404:
                    writers.append({'role': role, 'claim': ref(claim_path),
                        'state': {'Running': False if entered else None, 'Pid': 0 if entered else None},
                        'previously_entered_object_now_absent': entered})
                    continue
                if response.status != 200:
                    raise RuntimeError(f'Unexpected owned-container inspect status {response.status}')
                value = json.loads(raw)
                labels = value['Config'].get('Labels', {})
                expected = {'proworksim.owner': 'v066-owned-private-docker-actor-pair-r1',
                            'proworksim.resource': claim['key'], 'proworksim.claim': ref(claim_path)['sha256']}
                if (value['Name'].removeprefix('/') != claim['docker_name']
                        or value['Image'] != claim['spec']['image_id']
                        or any(labels.get(k) != v for k, v in expected.items())):
                    raise PermissionError('Inspected container has different immutable ownership')
                writers.append({'role': role, 'container_id': value['Id'],
                                'claim': ref(claim_path), 'state': value['State']})
            finally:
                client.close()
        quiet = all(w['state'].get('Running') is False and w['state'].get('Pid') == 0 for w in writers)
        value = {'all_quiet': quiet, 'writers': writers, 'errors': [],
            'create_result_unknown_roles': [], 'only_read_operations': True,
            'stop_receipt': ref(OUT/'stop-sent.json'), 'after_stop_unix': stop['signal_sent_unix'],
            'observed_unix': time.time(), 'proof_kind': 'Exact already-entered owned-container read-only inspection'}
        if quiet:
            target = OUT/'writer-observations'/f'{key}.json'
            target.parent.mkdir(exist_ok=True)
            with target.open('x') as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
        observations.append({'key': key, 'all_quiet': quiet, 'entered': entered,
            'writers': [{'role': w['role'], 'id': w.get('container_id'),
                         'state': w['state']} for w in writers]})
    return observations


def relieve_archives():
    if (OUT/'memory-relief-intent.json').exists():
        raise ValueError('A consumed limit change is not repeated')
    before = manager()
    identity = read(OUT/'stop-intent.json')['before']
    if (before['pid'], before['pid_start_ticks']) != (identity['pid'], identity['pid_start_ticks']):
        raise PermissionError('Only the original stopped-generation lifecycle can receive relief')
    proof = quiet_proof()
    if not proof['passed']:
        amendment = ROOT/'config/v132-archive-relief-timing-user-grant.json'
        consent = read(amendment)
        if consent.get('status') != 'approved' or consent.get('user_reply') != '允许提前解除归档限流':
            raise PermissionError('Incomplete producer shutdown requires the explicit timing amendment')
        permitted = set(consent['remaining_pre_model_slot_indices'])
        rows = {row['slot_index']: row for row in read(BATCH/'execution-plan.json')['rows']}
        exceptions = []
        for blocker in proof['blockers']:
            if blocker.get('reason') != 'no_stopped_writer_evidence':
                raise ValueError('An API reservation or active model writer still blocks relief')
            index = int(blocker['key'].removeprefix('actor-'))
            folder = BATCH/'episodes'/str(index)
            if (index not in permitted or (folder/'model-dispatch-intent.json').exists()
                    or (folder/'entered.json').exists()):
                raise PermissionError('Only the specifically approved never-model-started environments may drain')
            row = rows[index]
            ledger = BATCH/'ledgers'/f"{row['organization_id']}.sqlite"
            with sqlite3.connect(f'file:{ledger}?mode=ro', uri=True, timeout=3) as db:
                if db.execute('SELECT 1 FROM requests WHERE slot_id=? LIMIT 1', (row['slot_id'],)).fetchone():
                    raise PermissionError('A supposed pre-model exception already called the provider')
            exceptions.append({'slot_index': index, 'slot_id': row['slot_id'], 'zero_model_requests': True})
        proof.update(timing_amendment=ref(amendment), permitted_pre_model_cleanup_exceptions=exceptions,
                     passed_under_explicit_timing_amendment=True)
    if int(before['MemoryHigh']) != 24*GIB:
        raise PermissionError('Unexpected original high-water mark')
    evidence = save('quiet-before-memory-relief.json', proof)
    intent = save('memory-relief-intent.json', {'before': before, 'quiet_proof': evidence,
        'memory_high_bytes_after': 30*GIB, 'memory_max_bytes_unchanged': 32*GIB,
        'API_generation_already_stopped': True, 'source_files_changed': False,
        'shared_host_configuration_changes': False, 'unix': time.time()})
    result = subprocess.run(['systemctl', '--user', 'set-property', '--runtime', UNIT, 'MemoryHigh=30G'],
        text=True, capture_output=True, timeout=15)
    receipt = save('memory-relief-result.json', {'intent': intent, 'returncode': result.returncode,
        'stdout': result.stdout, 'stderr': result.stderr, 'unix': time.time()})
    result.check_returncode()
    after = manager()
    if int(after['MemoryHigh']) != 30*GIB or int(after['MemoryMax']) != 32*GIB:
        raise RuntimeError('Requested owned-unit high-water mark not observed')
    return save('memory-relief-verified.json', {'result': receipt, 'after': after, 'unix': time.time()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inspect', 'request-stop', 'quiet-proof', 'inspect-writers', 'relieve-archives'))
    action = parser.parse_args().action
    value = {'inspect': manager, 'request-stop': request_stop,
             'quiet-proof': quiet_proof, 'inspect-writers': inspect_remaining_writers,
             'relieve-archives': relieve_archives}[action]()
    print(json.dumps(value, ensure_ascii=False))
