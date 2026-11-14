"""Withdraw discovery, then hand over only physically quiet owned coordinators.

The old Qwen SIGTERM path cancels actors and stops resident GPUs.  This module
never sends it: after a persistent empty boundary, pidfd SIGKILL targets only the
ordinary-user coordinator process.  Independent resident units are untouched.
"""
from __future__ import annotations

import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import sqlite3
import subprocess
import time

from . import software_benchmark_dispatch_v066 as primary
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_ref_resident_v066 import user_manager_environment
from .storage import atomic_write, json_bytes

ROOT = primary.ROOT
OUT = ROOT / 'runs/software-benchmark-v076/adaptive-concurrency-r1/handoff'
HANDOFF_OPERATION = 'v076.handoff'
VERSION = 'v075-quiescent-coordinator-handoff-r1'
MODEL_ROOT = primary.BATCH_ROOT / 'residents'
CLAIMS = primary.BATCH_ROOT / 'resource-claims'
OLD_ROOTS = {
    'primary': ROOT / 'runs/software-benchmark-v068/recovery-r1/primary-coordinator',
    'api': ROOT / 'runs/software-benchmark-v072/api-5m-bounded-uncertain-r1/api-coordinator',
}
OLD_UNITS = {'primary': 'proworksim-v066-continuation.service', 'api': 'proworksim-v072-api-5m.service'}
ENTRYPOINTS = {'primary': 'run_full_benchmark_v068.py', 'api': 'run_api_continuation_v072.py'}
API_CONTROL = OLD_ROOTS['api'] / 'concurrency-control.json'


def load(path):
    return json.loads(Path(path).read_bytes())


def ordinary_user():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Handoff requires the existing ordinary user')


def authorize(guard):
    ordinary_user()
    if not callable(guard):
        raise PermissionError('An explicit deployment handoff authority is required')
    return guard(HANDOFF_OPERATION)


def show(role):
    result = subprocess.run(['systemctl', '--user', 'show', OLD_UNITS[role], '--no-pager',
        '--property=Description,ExecStart,ControlGroup,MainPID,ActiveState,SubState,Restart,KillMode'],
        env=user_manager_environment(), capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise RuntimeError('Cannot inspect the exact owned coordinator')
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)


def open_process_handle(pid):
    """Use pidfd even when this Python build omitted its os wrapper."""
    if type(pid) is not int or pid <= 0:
        raise ValueError('A positive exact process ID is required')
    if hasattr(os, 'pidfd_open'):
        return os.pidfd_open(pid)
    # The shared host's installed x86_64 Linux UAPI header declares 434. This
    # ordinary-user syscall has the same kernel permission checks as the wrapper.
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise RuntimeError('No reviewed pidfd_open implementation for this platform')
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.syscall(ctypes.c_long(434), ctypes.c_int(pid), ctypes.c_uint(0))
    if result < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return int(result)


def process_identity(pid):
    folder = Path('/proc') / str(pid)
    stat = (folder / 'stat').read_text()
    status = (folder / 'status').read_text().splitlines()
    uid = next(line.split()[1:] for line in status if line.startswith('Uid:'))
    if any(int(value) != os.getuid() for value in uid):
        raise PermissionError('Coordinator UID differs from this ordinary user')
    return {'pid': pid, 'start_ticks': int(stat.rsplit(')', 1)[1].split()[19]),
        'uid': os.getuid(), 'cmdline_sha256': hashlib.sha256((folder / 'cmdline').read_bytes()).hexdigest()}


def validate_unit(role, spec, properties):
    entrypoint = ROOT / 'tools' / ENTRYPOINTS[role]
    if (spec.get('role') != role or spec.get('unit') != OLD_UNITS[role]
            or spec.get('user_id') != os.getuid() or spec.get('reporting_root') != str(OLD_ROOTS[role])
            or spec.get('entrypoint', {}).get('path') != str(entrypoint)
            or spec.get('restart') != 'no' or spec.get('kill_mode') != 'mixed'):
        raise ValueError('The coordinator specification is not the exact old owned unit')
    checked(spec['entrypoint'])
    if properties.get('MainPID') == '0' and properties.get('ActiveState') in {'inactive', 'failed'}:
        return None
    expected = f"ProWorkSim {'v068' if role == 'primary' else 'v072'} {role} coordinator {spec['ownership_token']}"
    if (properties.get('Description') != expected or str(entrypoint) not in properties.get('ExecStart', '')
            or not properties.get('ControlGroup', '').endswith('/' + OLD_UNITS[role])
            or properties.get('Restart') != 'no' or properties.get('KillMode') != 'mixed'
            or properties.get('ActiveState') != 'active' or not properties.get('MainPID', '').isdigit()):
        raise ValueError('Refuse to address a changed coordinator service')
    return process_identity(int(properties['MainPID']))


def stage(*, guard):
    authorize(guard)
    path = OUT / 'stage.json'
    if path.exists():
        return reference(path)
    OUT.mkdir(parents=True, exist_ok=True)
    residents = []
    for folder in sorted(MODEL_ROOT.glob('model-*')):
        ready = folder / 'ready.json'
        if not ready.exists() or (folder / 'closed.json').exists():
            continue
        spec = load(folder / 'spec.json')
        if spec['index'] not in {1, 3, 4, 5} or spec['unit'] != f"proworksim-v066-model-{spec['index']}.service":
            raise ValueError('Only the four current resident identities may be hidden')
        residents.append({'index': spec['index'], 'unit': spec['unit'], 'original': reference(ready),
            'hidden_path': str(folder / 'ready.v076-handoff.json'), 'specification': reference(folder / 'spec.json')})
    if {item['index'] for item in residents} != {1, 3, 4, 5}:
        raise ValueError('All four intended resident discovery markers are required')
    units = {}
    for role, folder in OLD_ROOTS.items():
        spec_ref = reference(folder / 'coordinator-unit.json')
        spec, properties = load(spec_ref['path']), show(role)
        identity = validate_unit(role, spec, properties)
        if identity is None:
            raise ValueError('Stage expects both original coordinators to be active')
        units[role] = {'specification': spec_ref, 'properties': properties, 'process': identity}
    raw = API_CONTROL.read_bytes()
    original = OUT / 'original-api-concurrency-control.json'
    with original.open('xb') as stream:
        stream.write(raw)
    return write_new(path, {'version': VERSION, 'source': reference(__file__), 'created_unix': time.time(),
        'residents': residents, 'coordinators': units, 'API_control': reference(original),
        'API_control_original_path': str(API_CONTROL), 'operations_performed': 'snapshot_only'})


def stage_value():
    value = load(OUT / 'stage.json')
    if value.get('version') != VERSION or value.get('source') != reference(__file__):
        raise ValueError('Handoff source or prepared evidence changed')
    return value


def gate(*, guard):
    authorize(guard)
    value = stage_value()
    marker = OUT / 'gate.json'
    if (OUT / 'gate-rolled-back.json').exists():
        raise ValueError('A rolled-back handoff is terminal; prepare a separately identified handoff')
    if marker.exists():
        return reference(marker)
    for role, entry in value['coordinators'].items():
        if validate_unit(role, load(checked(entry['specification'])), show(role)) != entry['process']:
            raise ValueError('Original coordinator process identity changed before admission gate')
    # The API administrative pause does not cancel its existing transport calls.
    current = API_CONTROL.read_bytes()
    original = checked(value['API_control']).read_bytes()
    paused = json_bytes({'desired': 0, 'reason': VERSION})
    if current not in (original, paused):
        raise ValueError('The API concurrency control changed outside this handoff')
    atomic_write(API_CONTROL, paused)
    with (MODEL_ROOT / 'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for item in value['residents']:
            source, destination = Path(item['original']['path']), Path(item['hidden_path'])
            if destination.exists():
                if source.exists() or hashlib.sha256(destination.read_bytes()).hexdigest() != item['original']['sha256']:
                    raise ValueError('A hidden discovery marker is not the original byte sequence')
                continue
            checked(item['original'])
            os.rename(source, destination)
    return write_new(marker, {'version': VERSION, 'unix': time.time(), 'stage': reference(OUT / 'stage.json'),
        'model_units_signalled': False, 'inflight_tasks_cancelled': False, 'API_control': reference(API_CONTROL)})


def gate_intact(value):
    if load(API_CONTROL).get('desired') != 0:
        return False
    return all(not Path(item['original']['path']).exists()
        and Path(item['hidden_path']).is_file()
        and hashlib.sha256(Path(item['hidden_path']).read_bytes()).hexdigest() == item['original']['sha256']
        for item in value['residents'])


def request_physically_closed(ref):
    request = json.loads(checked(ref).read_bytes())
    folder = Path(request['directory'])
    completion, quiet = folder / 'completion.json', folder / 'quiescence.json'
    if not completion.exists() or not quiet.exists():
        return False
    value = load(quiet)
    return (value.get('quiescent') is True and value.get('cleanup_errors') == []
        and value.get('create_result_unknown') is False)


def quiet_reasons(progress, cursor, active_claims, *, role, now):
    reasons = []
    if not isinstance(progress.get('unix'), (int, float)) or not -5 <= now-progress['unix'] <= 180:
        reasons.append('stale_progress')
    if progress.get('failure') is not None or cursor.get('failure') is not None:
        reasons.append('unresolved_shared_failure')
    if progress.get('active_generation') != 0 or cursor.get('active_generation'):
        reasons.append('generation_not_naturally_complete')
    if role == 'primary' and (progress.get('active_grading') != 0
            or progress.get('pending_scores') != 0 or progress.get('pending_controls') != 0
            or cursor.get('active_grading') or cursor.get('pending_scores') or cursor.get('pending_controls')):
        reasons.append('primary_grading_not_naturally_complete')
    if role == 'api' and (progress.get('effective_generation_limit') != 0
            or progress.get('actual_generation_futures') != 0
            or progress.get('phase') != 'waiting'
            or progress.get('capacity_wait_reason') != 'invalid_concurrency_control'):
        reasons.append('api_admission_pause_not_observed')
    if any(item.get('spec', {}).get('role') not in {'model', 'auxiliary_coordinator'} for item in active_claims):
        reasons.append('owned_non_model_resources_still_active')
    # API's frozen admission wait may retain completed grader futures in its
    # cursor. Require physical completion and carry that exact request forward.
    if any(not request_physically_closed(ref) for ref in cursor.get('active_grading', [])):
        reasons.append('grader_still_running_or_cleanup_unproven')
    return reasons


def observe(*, guard):
    authorize(guard)
    value = stage_value()
    if not (OUT / 'gate.json').exists() or not gate_intact(value):
        raise ValueError('The exact discovery/API admission gate is not intact')
    snapshots = {}
    reasons = []
    with (CLAIMS / 'allocation.lock').open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        claims = [load(path) for path in CLAIMS.glob('active-*.json')]
    now = time.time()
    for role, folder in OLD_ROOTS.items():
        cursor_raw = (folder / 'cursor.json').read_bytes()
        progress_raw = (folder / 'progress.json').read_bytes()
        cursor, progress = json.loads(cursor_raw), json.loads(progress_raw)
        role_reasons = quiet_reasons(progress, cursor, claims, role=role, now=now)
        prior_signal = saved_signal(role, value['coordinators'][role]['process'])
        if prior_signal is not None:
            spec = json.loads(checked(value['coordinators'][role]['specification']).read_bytes())
            if validate_unit(role, spec, show(role)) is None:
                frozen = OUT / 'administrative-boundary' / f'{role}-cursor.json'
                if not frozen.is_file() or frozen.read_bytes() != cursor_raw:
                    role_reasons.append('stopped_cursor_changed')
                else:
                    role_reasons = [reason for reason in role_reasons if reason != 'stale_progress']
        reasons.extend(role + ':' + reason for reason in role_reasons)
        snapshots[role] = {'cursor': cursor, 'progress': progress,
            'cursor_sha256': hashlib.sha256(cursor_raw).hexdigest(),
            'cursor_bytes': cursor_raw.decode(), 'progress_bytes': progress_raw.decode()}
    ledger = primary.PREDECESSOR_ROOT / 'api-budget/ledger.sqlite3'
    with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True) as db:
        count = db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0]
    if count:
        reasons.append('API_requests_still_inflight')
    return {'version': VERSION, 'unix': now, 'ready': not reasons, 'reasons': reasons,
        'snapshots': snapshots, 'active_claim_keys': [item.get('key') for item in claims],
        'reserved_API_requests': count, 'pending_unstarted_scores_and_controls_are_carried': True}


def unit_members(properties):
    """No child process may be caught by the unit's subsequent own cleanup."""
    group = properties.get('ControlGroup', '')
    if not group.startswith('/user.slice/') or '..' in Path(group).parts:
        raise ValueError('Coordinator cgroup path is outside the ordinary-user hierarchy')
    path = Path('/sys/fs/cgroup') / group.lstrip('/') / 'cgroup.procs'
    return sorted(int(value) for value in path.read_text().split())


def saved_signal(role, identity):
    path = OUT / f'{role}-signal-intent.json'
    if not path.exists():
        return None
    value = load(path)
    if (value.get('version') != VERSION or value.get('role') != role
            or value.get('process') != identity or value.get('signal') != 'SIGKILL'
            or value.get('discovery_gate') != reference(OUT / 'gate.json')):
        raise ValueError('A previous signal intent is not this exact handoff')
    return value


def stop_quiescent(*, guard):
    authorize(guard)
    value = stage_value()
    if (OUT / 'coordinators-stopped.json').exists():
        return reference(OUT / 'coordinators-stopped.json')
    proof = observe(guard=guard)
    if not proof['ready']:
        return {'status': 'waiting', 'reasons': proof['reasons']}
    if not hasattr(signal, 'pidfd_send_signal'):
        raise RuntimeError('Pidfd-safe process signalling is required')
    snapshots = OUT / 'administrative-boundary'
    snapshots.mkdir(exist_ok=True)
    for role, item in proof['snapshots'].items():
        for kind in ('cursor', 'progress'):
            path = snapshots / f'{role}-{kind}.json'
            raw = item[kind+'_bytes'].encode()
            if path.exists():
                if kind == 'cursor' and path.read_bytes() != raw:
                    raise ValueError('A previously frozen administrative cursor changed')
            else:
                with path.open('xb') as stream:
                    stream.write(raw)
    records, descriptors = [], {}
    try:
        # Verify both processes and pin both PID identities before the first
        # signal. An already signalled, inactive own unit can finish a partial
        # handoff; an unrelated disappearance cannot be adopted.
        for role in ('api', 'primary'):
            entry = value['coordinators'][role]
            expected = entry['process']
            spec = json.loads(checked(entry['specification']).read_bytes())
            properties = show(role)
            identity = validate_unit(role, spec, properties)
            prior_signal = saved_signal(role, expected)
            if identity is None:
                if prior_signal is None:
                    raise ValueError('Coordinator disappeared without this handoff signal proof')
                records.append(prior_signal)
                continue
            if identity != expected or unit_members(properties) != [identity['pid']]:
                raise ValueError('Coordinator identity changed or its cgroup contains a child process')
            fd = open_process_handle(identity['pid'])
            descriptors[role] = fd
            if process_identity(identity['pid']) != identity:
                raise ValueError('Coordinator changed before the pidfd was pinned')
        for role in ('api', 'primary'):
            if role not in descriptors:
                continue
            identity = value['coordinators'][role]['process']
            cursor_path = OLD_ROOTS[role] / 'cursor.json'
            if (not gate_intact(value)
                    or hashlib.sha256(cursor_path.read_bytes()).hexdigest() != proof['snapshots'][role]['cursor_sha256']
                    or process_identity(identity['pid']) != identity):
                raise ValueError('Admission gate, cursor or process changed at the quiet boundary')
            intent = saved_signal(role, identity)
            if intent is None:
                intent = {'version': VERSION, 'role': role, 'process': identity,
                    'signal': 'SIGKILL', 'only_quiescent_coordinator_main_PID': True,
                    'discovery_gate': reference(OUT / 'gate.json'), 'shared_host_configuration_changed': False}
                write_new(OUT / f'{role}-signal-intent.json', intent)
            signal.pidfd_send_signal(descriptors[role], signal.SIGKILL)
            records.append(intent)
    finally:
        for fd in descriptors.values():
            os.close(fd)
    return write_new(OUT / 'coordinators-stopped.json', {'version': VERSION, 'unix': time.time(),
        'signals': records, 'administrative_boundary': str(snapshots),
        'resident_units_stopped': False, 'new_generation': 0, 'clean_python_finalization_claimed': False})


def rollback_gate(*, guard):
    """Undo a preparation pause only while neither coordinator was signalled."""
    authorize(guard)
    value = stage_value()
    if list(OUT.glob('*-signal-intent.json')) or (OUT / 'coordinators-stopped.json').exists():
        raise ValueError('A signalled coordinator cannot be resumed by gate rollback')
    for role, entry in value['coordinators'].items():
        if validate_unit(role, json.loads(checked(entry['specification']).read_bytes()), show(role)) != entry['process']:
            raise ValueError('Rollback requires both original live coordinator identities')
    for item in value['residents']:
        hidden, ready = Path(item['hidden_path']), Path(item['original']['path'])
        if ready.exists():
            checked(item['original'])
            if hidden.exists():
                raise ValueError('Conflicting readiness markers')
        else:
            if hashlib.sha256(hidden.read_bytes()).hexdigest() != item['original']['sha256']:
                raise ValueError('Hidden readiness marker no longer matches its original')
            os.rename(hidden, ready)
    atomic_write(API_CONTROL, checked(value['API_control']).read_bytes())
    return write_new(OUT / 'gate-rolled-back.json', {'version': VERSION, 'unix': time.time(),
        'original_API_control_restored': True, 'models_reloaded': False})


def restore_ready(*, guard):
    authorize(guard)
    value = stage_value()
    if not (OUT / 'coordinators-stopped.json').exists():
        raise ValueError('Do not reopen discovery while the old coordinator can dispatch')
    for role, entry in value['coordinators'].items():
        if validate_unit(role, json.loads(checked(entry['specification']).read_bytes()), show(role)) is not None:
            raise ValueError('The old coordinator is still active')
    for item in value['residents']:
        source, destination = Path(item['hidden_path']), Path(item['original']['path'])
        if destination.exists():
            checked(item['original'])
            if source.exists():
                raise ValueError('Duplicated resident discovery marker')
            continue
        if hashlib.sha256(source.read_bytes()).hexdigest() != item['original']['sha256']:
            raise ValueError('The original resident marker bytes changed')
        os.rename(source, destination)
        checked(item['original'])
    marker = OUT / 'ready-restored.json'
    return reference(marker) if marker.exists() else write_new(marker, {'version': VERSION, 'unix': time.time(),
        'restored_original_residents': [item['original'] for item in value['residents']],
        'resident_units_reloaded': False, 'old_API_admission_remains_paused': True})
