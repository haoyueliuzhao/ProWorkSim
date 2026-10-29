"""Natural API-only handoff; no Qwen discovery or model lifecycle operations."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import threading
import time

from . import software_benchmark_api_scope_v079 as scope
from . import software_benchmark_adaptive_scope_v076 as prior
from . import software_benchmark_handoff_v075 as helpers
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_ref_resident_v066 import user_manager_environment
from .storage import atomic_write, json_bytes

VERSION = 'v079-natural-API-only-handoff-r1'
ROOT = scope.ROOT
OUT = scope.HANDOFF_ROOT
OLD = scope.OLD_API_ROOT
CONTROL = OLD/'concurrency-control.json'


def load(path):
    return json.loads(Path(path).read_bytes())


def show():
    result = subprocess.run(['systemctl', '--user', 'show', scope.OLD_API_UNIT, '--no-pager',
        '--property=Description,ExecStart,ControlGroup,MainPID,ActiveState,SubState,Restart,KillMode'],
        env=user_manager_environment(), capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError('Cannot inspect the exact old API service')
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)


def identity(spec, properties):
    if (spec.get('role') != 'api' or spec.get('unit') != scope.OLD_API_UNIT
            or spec.get('user_id') != os.getuid() or spec.get('reporting_root') != str(OLD)
            or spec.get('entrypoint', {}).get('path') != str(ROOT/'tools/run_adaptive_v076.py')
            or spec.get('restart') != 'no' or spec.get('kill_mode') != 'mixed'):
        raise PermissionError('Not this project exact old API specification')
    checked(spec['entrypoint'])
    if properties.get('MainPID') == '0' and properties.get('ActiveState') in {'inactive', 'failed'}:
        return None
    if (properties.get('Description') != 'ProWorkSim v076 api coordinator '+spec['ownership_token']
            or spec['entrypoint']['path'] not in properties.get('ExecStart', '')
            or not properties.get('ControlGroup', '').endswith('/'+scope.OLD_API_UNIT)
            or properties.get('ActiveState') != 'active' or properties.get('Restart') != 'no'
            or properties.get('KillMode') != 'mixed'):
        raise PermissionError('The old API service ownership changed')
    return helpers.process_identity(int(properties['MainPID']))


def stage():
    scope.require_allowed('v079.handoff')
    path = OUT/'stage.json'
    if path.exists():
        return reference(path)
    ref = reference(OLD/'coordinator-unit.json')
    spec, props = scope.load(ref), show()
    process = identity(spec, props)
    if process is None:
        raise ValueError('Stage requires the exact active predecessor')
    progress = load(OLD/'progress.json')
    if progress.get('failure') is not None or progress.get('provider_failures'):
        raise ValueError('Predecessor has a shared or provider failure requiring separate review')
    original = CONTROL.read_bytes() if CONTROL.exists() else None
    OUT.mkdir(parents=True, exist_ok=True)
    saved = write_new(OUT/'control-before.json', original) if original is not None else None
    return write_new(path, {'version': VERSION, 'source': reference(__file__), 'unix': time.time(),
        'specification': ref, 'properties': props, 'process': process,
        'original_control': saved, 'control_was_absent': original is None,
        'original_desired': progress['configured_generation_limit'], 'Qwen_affected': False})


def stage_value():
    value = load(OUT/'stage.json')
    if value.get('version') != VERSION or value.get('source') != reference(__file__):
        raise ValueError('Handoff source or staged evidence changed')
    return value


def gate():
    scope.require_allowed('v079.handoff')
    stage()
    value = stage_value()
    marker = OUT/'gate.json'
    if marker.exists():
        if load(CONTROL).get('desired') != 0:
            raise ValueError('The exact predecessor pause changed')
        return reference(marker)
    if identity(scope.load(value['specification']), show()) != value['process']:
        raise ValueError('Original coordinator process identity changed')
    before = checked(value['original_control']).read_bytes() if value['original_control'] else None
    if (CONTROL.read_bytes() if CONTROL.exists() else None) != before:
        raise ValueError('Another operator changed the concurrency control')
    atomic_write(CONTROL, json_bytes({'desired': 0, 'reason': VERSION}))
    return write_new(marker, {'version': VERSION, 'unix': time.time(), 'stage': reference(OUT/'stage.json'),
        'old_tasks_cancelled': False, 'Qwen_affected': False, 'control': reference(CONTROL)})


def quiet_reasons(progress, cursor, api_claims, reserved, *, now, gate_unix):
    reasons = []
    if (not isinstance(progress.get('unix'), (int, float)) or not -5 <= now-progress['unix'] <= 60
            or progress['unix'] <= gate_unix):
        reasons.append('stale_or_pre_gate_progress')
    if progress.get('failure') is not None or cursor.get('failure') is not None:
        reasons.append('shared_failure')
    if progress.get('effective_generation_limit') != 0:
        reasons.append('pause_not_observed')
    for name in ('active_generation', 'active_grading', 'pending_scores', 'pending_controls'):
        if cursor.get(name) or progress.get(name) != 0:
            reasons.append(name+'_not_empty')
    if progress.get('actual_generation_futures') != 0:
        reasons.append('generation_futures_not_empty')
    if api_claims:
        reasons.append('API_resources_still_active')
    if reserved:
        reasons.append('API_requests_inflight')
    return reasons


def observe():
    scope.require_allowed('v079.handoff')
    value = stage_value()
    if not (OUT/'gate.json').exists() or load(CONTROL).get('desired') != 0:
        raise ValueError('The exact API admission pause is required')
    if identity(scope.load(value['specification']), show()) != value['process']:
        raise ValueError('Original API process changed')
    progress_raw, cursor_raw = (OLD/'progress.json').read_bytes(), (OLD/'cursor.json').read_bytes()
    progress, cursor = json.loads(progress_raw), json.loads(cursor_raw)
    directory = scope.original.BATCH_ROOT/'resource-claims'
    with (directory/'allocation.lock').open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        active = [load(path) for path in directory.glob('active-*.json')]
    api_claims = [item['key'] for item in active if ':DEEPSEEK_' in item.get('spec', {}).get('slot_id', '')]
    ledger = scope.original.PREDECESSOR_ROOT/'api-budget/ledger.sqlite3'
    with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True) as db:
        reserved = db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0]
    reasons = quiet_reasons(progress, cursor, api_claims, reserved,
        now=time.time(), gate_unix=load(OUT/'gate.json')['unix'])
    return {'version': VERSION, 'unix': time.time(), 'ready': not reasons, 'reasons': reasons,
        'cursor': cursor, 'cursor_raw': cursor_raw, 'progress_raw': progress_raw,
        'cursor_sha256': hashlib.sha256(cursor_raw).hexdigest(), 'API_claims': api_claims,
        'reserved_requests': reserved, 'Qwen_resources_ignored_and_unchanged': True}


def stop_quiet():
    proof = observe()
    if not proof['ready']:
        raise ValueError('The API physical boundary is not quiet')
    value = stage_value()
    process = identity(scope.load(value['specification']), show())
    if process != value['process']:
        raise ValueError('Original API process was replaced')
    props = show()
    processes = (Path('/sys/fs/cgroup')/props['ControlGroup'].lstrip('/')/'cgroup.procs').read_text().split()
    if processes != [str(process['pid'])]:
        raise ValueError('Old API cgroup contains another process')
    boundary = OUT/'boundary'
    boundary.mkdir(exist_ok=False)
    before = write_new(boundary/'cursor.json', proof['cursor_raw'])
    progress = write_new(boundary/'progress.json', proof['progress_raw'])
    descriptor = helpers.open_process_handle(process['pid'])
    try:
        if helpers.process_identity(process['pid']) != process or reference(OLD/'cursor.json')['sha256'] != proof['cursor_sha256']:
            raise ValueError('Quiet API identity or checkpoint changed before signal')
        write_new(OUT/'signal-intent.json', {'version': VERSION, 'process': process,
            'signal': 'SIGKILL', 'only_quiet_API_main_PID': True, 'Qwen_affected': False,
            'parent_slice_retained': True, 'cursor': before, 'progress': progress})
        signal.pidfd_send_signal(descriptor, signal.SIGKILL)
    finally:
        os.close(descriptor)
    deadline = time.monotonic()+30
    while identity(scope.load(value['specification']), show()) is not None:
        if time.monotonic() >= deadline:
            raise TimeoutError('Signalled old API has not become inactive')
        time.sleep(.2)
    release = prior.release_api_coordinator(reference(prior.CLAIM_FILE))
    return write_new(OUT/'stopped.json', {'version': VERSION, 'unix': time.time(),
        'signal': reference(OUT/'signal-intent.json'), 'cursor': before, 'progress': progress,
        'old_auxiliary_release': release, 'Qwen_lifecycle_operations': 0,
        'API_parent_stopped_or_recreated': False, 'inflight_tasks_cancelled': False})


def rollback():
    scope.require_allowed('v079.handoff')
    if (OUT/'signal-intent.json').exists():
        return {'performed': False, 'reason': 'signal_already_recorded'}
    value = stage_value()
    if identity(scope.load(value['specification']), show()) != value['process'] or load(CONTROL).get('desired') != 0:
        raise ValueError('Cannot restore an unrecognized old dispatcher')
    if value['control_was_absent']:
        CONTROL.unlink()
    else:
        atomic_write(CONTROL, checked(value['original_control']).read_bytes())
    return {'performed': True, 'Qwen_affected': False}


def validate_dead_cursor(before, after):
    """Original terminal history is immutable; consumed orphans remain accounted."""
    if any(after.get(key) for key in ('active_generation', 'active_grading', 'pending_controls')):
        raise ValueError('Administrative recovery still has active API work')
    for key in ('generation', 'scores', 'deliveries'):
        if any(after.get(key, {}).get(slot) != entry for slot, entry in before.get(key, {}).items()):
            raise ValueError('Administrative recovery changed an original terminal record')
    for slot in before.get('active_generation', []):
        if after.get('generation', {}).get(slot, {}).get('status') not in {'closed', 'technical_unknown', 'not_started'}:
            raise ValueError('An original inflight API identity was lost from recovery accounting')
    return after


def accept_dead_owner(proof_ref):
    """Import an independently completed orphan/fee recovery; never perform it."""
    scope.require_allowed('v079.handoff')
    if (OUT/'stopped.json').exists():
        existing = scope.load(reference(OUT/'stopped.json'))
        if existing.get('dead_owner_recovery') != proof_ref:
            raise ValueError('Another completed handoff already owns this continuation')
        return reference(OUT/'stopped.json')
    proof = scope.load(proof_ref)
    if (proof.get('version') != 'v079-dead-owner-API-recovery-r1'
            or proof.get('old_unit') != scope.OLD_API_UNIT
            or proof.get('original_results_changed') is not False
            or proof.get('new_model_calls') != 0 or proof.get('replayed_episodes') != 0):
        raise PermissionError('Exact independent dead-owner recovery evidence is required')
    spec_ref = reference(OLD/'coordinator-unit.json')
    if proof.get('old_unit_specification') != spec_ref or identity(scope.load(spec_ref), show()) is not None:
        raise ValueError('The original API owner is not proved inactive')
    scope.load(proof['exit_evidence'])
    quiet = scope.load(proof['quiescence'])
    cash = scope.load(proof['cash_reconciliation'])
    if (quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []
            or quiet.get('foreign_objects_modified') is not False
            or cash.get('reserved_requests_after') != 0
            or cash.get('unknown_reservations_released') is not False
            or cash.get('new_API_cash_budget') is not False):
        raise ValueError('Orphan cleanup or conservative money reconciliation is incomplete')
    before = scope.load(proof['original_cursor'])
    after = validate_dead_cursor(before, scope.load(proof['administrative_cursor']))
    release = scope.load(proof['old_auxiliary_release'])
    if (release.get('claim') != reference(prior.CLAIM_FILE) or release.get('quiescent') is not True
            or prior.LEASE_FILE.exists()):
        raise ValueError('Dead predecessor auxiliary reservation is not exactly released')
    directory = scope.original.BATCH_ROOT/'resource-claims'
    with (directory/'allocation.lock').open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        active = [load(path) for path in directory.glob('active-*.json')]
        if any(':DEEPSEEK_' in item.get('spec', {}).get('slot_id', '') for item in active):
            raise ValueError('API physical claims remain active')
        from . import software_benchmark_api_parent_v076 as parent
        parent.require_qualified()
        if any(path.is_dir() for path in (Path('/sys/fs/cgroup')/parent.SLICE).iterdir()):
            raise ValueError('Owned API container cgroups remain under the existing parent')
        ledger = scope.original.PREDECESSOR_ROOT/'api-budget/ledger.sqlite3'
        with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True) as db:
            if db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0]:
                raise ValueError('API requests remain reserved after recovery')
    OUT.mkdir(parents=True, exist_ok=True)
    return write_new(OUT/'stopped.json', {'version': VERSION, 'unix': time.time(),
        'kind': 'independent_dead_owner_recovery', 'dead_owner_recovery': proof_ref,
        'cursor': proof['administrative_cursor'], 'original_cursor': proof['original_cursor'],
        'progress': proof['old_progress'], 'old_auxiliary_release': proof['old_auxiliary_release'],
        'Qwen_lifecycle_operations': 0, 'API_parent_stopped_or_recreated': False,
        'inflight_tasks_cancelled': False, 'orphan_cleanup_happened_after_owner_death': True,
        'retained_generation_entries': len(after['generation']), 'new_model_calls': 0})


def wait_and_stop(*, stop=None, maximum_wait=8*3600, interval=15):
    stop = stop or threading.Event()
    started, quiet_at = time.monotonic(), None
    while not stop.is_set():
        if time.monotonic()-started >= maximum_wait:
            raise TimeoutError('Eight-hour API natural completion wait expired')
        proof = observe()
        atomic_write(scope.API_ROOT/'bootstrap-progress.json', json_bytes({'version': VERSION,
            'unix': time.time(), 'phase': 'waiting_for_old_API_completion', 'ready': proof['ready'],
            'reasons': proof['reasons'], 'elapsed_seconds': time.monotonic()-started,
            'Qwen_affected': False, 'old_inflight_tasks_cancelled': False}))
        if proof['ready']:
            if quiet_at is None:
                quiet_at = time.monotonic()
            elif time.monotonic()-quiet_at >= 3:
                return stop_quiet()
        else:
            quiet_at = None
        stop.wait(3 if proof['ready'] else interval)
    raise InterruptedError('API handoff cancelled before its quiet boundary')
