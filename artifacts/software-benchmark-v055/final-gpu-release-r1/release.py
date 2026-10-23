"""Release only the four completed, registered project resident services."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT = ROOT / 'runs/software-benchmark-v055/final-gpu-release-r1'
sys.path.insert(0, str(ROOT / 'src'))
from proworksim.software_benchmark_resident_session_v054 import admin_client, interleaved_status

MONITOR = 'proworksim-v054-dynamic-pool-ref-handoff-r1.service'
TARGETS = {3: ('mp-g3-7cbe8217', 'proworksim-v054-resident-mp-g3-7cbe8217.service'),
           5: ('mp-g5-a21ce1c9', 'proworksim-v054-resident-mp-g5-a21ce1c9.service'),
           6: ('mp-g6-kernel-r6', 'proworksim-v054-resident-mp-g6-kernel-r6.service'),
           7: ('mp-g7-0303dcc7', 'proworksim-v054-resident-mp-g7-0303dcc7.service')}


def now():
    return datetime.now(timezone.utc).isoformat()


def reference(path):
    path = Path(path)
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def load(ref):
    assert reference(ref['path']) == ref
    return json.loads(Path(ref['path']).read_bytes())


def write(name, body):
    path = OUT / name
    with path.open('x') as stream:
        json.dump(body, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    return reference(path)


def command(argv, timeout=15):
    return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=timeout)


def unit(name):
    result = command(['systemctl', '--user', 'show', name,
        '--property=Id,ActiveState,SubState,MainPID,InvocationID,ControlGroup,KillMode,Restart,Result'])
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)


def process(pid):
    path = Path('/proc') / str(pid)
    try:
        text = (path / 'stat').read_text()
        fields = text[text.rfind(')') + 2:].split()
        return {'pid': int(pid), 'start_ticks': int(fields[19]), 'state': fields[0],
                'uid': path.stat().st_uid, 'cgroup': (path / 'cgroup').read_text().strip()}
    except FileNotFoundError:
        return None


def group_processes(group):
    path = Path('/sys/fs/cgroup' + group)
    if not path.exists():
        return []
    pids = {int(pid) for file in path.rglob('cgroup.procs') for pid in file.read_text().split()}
    return [item for pid in sorted(pids) if (item := process(pid)) is not None]


def gpu_snapshot():
    cards = []
    for line in command(['nvidia-smi', '-i', '3,5,6,7', '--query-gpu=index,uuid,memory.used,memory.free',
                         '--format=csv,noheader,nounits']).stdout.splitlines():
        index, uuid, used, free = [part.strip() for part in line.split(',')]
        cards.append({'index': int(index), 'uuid': uuid, 'used_mib': int(used), 'free_mib': int(free)})
    apps = []
    for line in command(['nvidia-smi', '-i', '3,5,6,7', '--query-compute-apps=gpu_uuid,pid,used_gpu_memory',
                         '--format=csv,noheader,nounits']).stdout.splitlines():
        if not line.strip():
            continue
        uuid, pid, used = [part.strip() for part in line.split(',')]
        apps.append({'gpu_uuid': uuid, 'pid': int(pid), 'used_mib': int(used) if used.isdigit() else None})
    return {'cards': cards, 'compute_apps': apps}


def queue_terminal():
    queues = []
    for name, relative, expected in [('qwen', 'v054/formal-queue-r1', 1500), ('deepseek', 'v055/queue-r1', 3000)]:
        path = ROOT / ('runs/software-benchmark-' + relative) / 'state.json'
        ref = reference(path)
        state = load(ref)
        active = [r['slot']['slot_id'] for r in state['rows'] if r['generation']['status'] in {'pending', 'intent', 'running'}]
        assert len(state['rows']) == expected and not active
        queues.append({'family': name, 'state': ref, 'status': state['status'], 'active_or_pending_generation': 0})
    recovery = reference(ROOT / 'runs/software-benchmark-v055/pre-entry-recovery-r1/summary.json')
    recovered = load(recovery)
    assert recovered['generation_terminal'] == 6 and recovered['scoring_endpoints_terminal'] == 3
    return {'queues': queues, 'preentry_recovery_summary': recovery}


def current_generation_units():
    result = command(['systemctl', '--user', 'list-units', '--type=service', '--state=active', '--no-legend', '--plain'])
    names = [line.split()[0] for line in result.stdout.splitlines() if line.strip()]
    return [name for name in names if name.startswith('proworksim-') and any(
        key in name for key in ('generation-', 'formal-queue-', 'deepseek-six-conditions-', 'preentry-generation-'))]


def registrations():
    selected = []
    for index, (resident_id, expected_unit) in TARGETS.items():
        events = (ROOT / 'runs/software-benchmark-v054/kernel-optimization-r1/deployment-r6/pool/events'
                  if index == 6 else ROOT / 'runs/software-benchmark-v054/dynamic-pool-r4/events')
        active = {}
        for path in sorted(events.glob('*.json')):
            ref = reference(path)
            event = load(ref)
            if event['event'] == 'register':
                active[event['resident_id']] = (ref, event)
            elif event['event'] == 'retire':
                active.pop(event['resident_id'], None)
        reg_ref, event = active[resident_id]
        declaration = load(event['declaration'])
        assert declaration['unit'] == expected_unit and declaration['gpu_index'] == index
        ready_ref = reference(declaration['ready_path'])
        ready = load(ready_ref)
        identity_ref = ready['identity']
        identity = load(identity_ref)
        assert ready['source_spec'] == declaration['source_spec'] and ready['gpu_uuid'] == declaration['gpu_uuid']
        state = unit(expected_unit)
        observed = process(int(state['MainPID']))
        assert state['ActiveState'] == 'active' and state['KillMode'] == 'control-group'
        assert observed['pid'] == ready['host_process']['pid'] and observed['start_ticks'] == ready['host_process']['start_ticks']
        assert state['ControlGroup'].endswith('/' + expected_unit)
        assert ready.get('invocation_id', state['InvocationID']) == state['InvocationID']
        assert ready.get('cgroup', state['ControlGroup']) == state['ControlGroup']
        members = group_processes(state['ControlGroup'])
        assert members and all(item['uid'] == os.getuid() for item in members)
        status = admin_client(declaration, identity, timeout=5).call('status')
        assert interleaved_status(status) == [] and status['inflight'] is None and status['sessions'] == {}
        selected.append({'gpu_index': index, 'gpu_uuid': declaration['gpu_uuid'], 'resident_id': resident_id,
            'registration': reg_ref, 'declaration': event['declaration'], 'ready': ready_ref,
            'identity': identity_ref, 'unit': expected_unit, 'unit_state': state,
            'host_process': observed, 'cgroup_processes': members, 'idle_admin_status': status})
    return selected


def prepare():
    assert os.getuid() == 1021
    terminal = queue_terminal()
    assert current_generation_units() == []
    residents = registrations()
    gpu = gpu_snapshot()
    cards = {x['index']: x for x in gpu['cards']}
    for row in residents:
        assert row['gpu_uuid'] == cards[row['gpu_index']]['uuid']
        pids = {x['pid'] for x in row['cgroup_processes']}
        row['own_gpu_processes'] = [x for x in gpu['compute_apps'] if x['pid'] in pids]
        assert row['own_gpu_processes'] and all(x['gpu_uuid'] == row['gpu_uuid'] for x in row['own_gpu_processes'])
    monitor = unit(MONITOR)
    assert monitor['ActiveState'] == 'active' and monitor['KillMode'] == 'process'
    return write('before.json', {'version': 'v055-final-owned-GPU-release-r1', 'observed_utc': now(),
        'source': reference(__file__), 'authorization': 'User explicitly requested release of project GPUs after all experiments complete',
        'terminal': terminal, 'active_generation_units': [], 'pool_monitor': monitor,
        'pool_monitor_process': process(int(monitor['MainPID'])), 'residents': residents, 'gpu_snapshot': gpu,
        'new_model_calls': 0, 'model_or_image_files_deleted': False, 'other_user_processes_to_signal': 0})


def release():
    before_ref = reference(OUT / 'before.json')
    before = load(before_ref)
    assert reference(__file__) == before['source']
    queue_terminal()
    assert current_generation_units() == []
    monitor = unit(MONITOR)
    assert monitor['InvocationID'] == before['pool_monitor']['InvocationID']
    assert monitor['MainPID'] == before['pool_monitor']['MainPID']
    write('release-intent.json', {'created_utc': now(), 'before': before_ref,
        'stop_order': [MONITOR, *[row['unit'] for row in before['residents']]],
        'normal_systemctl_stop_only': True, 'GPU_reset': False, 'other_processes_signalled': 0,
        'model_files_deleted': False, 'new_model_calls': 0})
    command(['systemctl', '--user', 'stop', MONITOR], timeout=20)
    after_monitor = unit(MONITOR)
    assert after_monitor['MainPID'] == '0' and after_monitor['ActiveState'] in {'inactive', 'failed'}
    write('pool-monitor-stopped.json', {'observed_utc': now(), 'unit': after_monitor, 'auto_reacquisition_stopped': True})
    for row in before['residents']:
        state = unit(row['unit'])
        assert state['MainPID'] == row['unit_state']['MainPID'] and state['InvocationID'] == row['unit_state']['InvocationID']
        declaration, identity = load(row['declaration']), load(row['identity'])
        status = admin_client(declaration, identity, timeout=5).call('status')
        assert interleaved_status(status) == [] and status['inflight'] is None and status['sessions'] == {}
    command(['systemctl', '--user', 'stop', *[row['unit'] for row in before['residents']]], timeout=60)
    released = []
    for row in before['residents']:
        state = unit(row['unit'])
        assert state['MainPID'] == '0' and state['ActiveState'] in {'inactive', 'failed'}
        assert group_processes(row['unit_state']['ControlGroup']) == []
        remaining = [x for x in row['cgroup_processes'] if (current := process(x['pid'])) is not None
                     and current['start_ticks'] == x['start_ticks'] and current['state'] != 'Z']
        assert not remaining
        released.append({'gpu_index': row['gpu_index'], 'gpu_uuid': row['gpu_uuid'], 'unit': row['unit'],
                         'unit_after': state, 'original_cgroup_empty': True, 'original_process_identities_gone': True})
    own = {x['pid'] for r in before['residents'] for x in r['own_gpu_processes']}
    deadline = time.monotonic() + 20
    after = gpu_snapshot()
    while own.intersection(x['pid'] for x in after['compute_apps']):
        if time.monotonic() >= deadline:
            raise RuntimeError('NVML still lists an original owned GPU process')
        time.sleep(0.5)
        after = gpu_snapshot()
    return write('released.json', {'version': 'v055-final-owned-GPU-release-r1', 'completed_utc': now(),
        'before': before_ref, 'pool_monitor': after_monitor, 'residents': released, 'gpu_snapshot_after': after,
        'own_gpu_processes_remaining': 0,
        'own_gpu_memory_before_mib': sum(x['used_mib'] or 0 for r in before['residents'] for x in r['own_gpu_processes']),
        'other_user_processes_signalled': 0, 'model_files_deleted': False, 'GPU_reset': False,
        'new_model_calls': 0, 'historical_registrations_rewritten': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['prepare', 'release'])
    args = parser.parse_args()
    print(json.dumps(prepare() if args.operation == 'prepare' else release()))
