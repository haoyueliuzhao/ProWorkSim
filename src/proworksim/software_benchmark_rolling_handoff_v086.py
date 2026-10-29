"""Pause only old admissions; its existing episodes finish beside the successor."""
from __future__ import annotations

from contextlib import closing
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import threading
import time

from . import software_benchmark_api_handoff_v079 as previous
from . import software_benchmark_api_scope_v085 as old_scope
from . import software_benchmark_rolling_scope_v086 as scope
from . import software_benchmark_handoff_v075 as helpers
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace
from .storage import atomic_write, json_bytes

VERSION = 'v086-disjoint-original-API-rolling-handoff-r1'
ROOT, OUT, OLD = scope.ROOT, scope.HANDOFF_ROOT, scope.OLD_API_ROOT
CONTROL = OLD/'concurrency-control.json'


def identity(spec, properties):
    if (spec.get('role') != 'api' or spec.get('unit') != scope.OLD_API_UNIT
            or spec.get('user_id') != os.getuid() or spec.get('reporting_root') != str(OLD)
            or spec.get('entrypoint', {}).get('path') != str(ROOT/'tools/run_api_recovery_v085.py')
            or spec.get('restart') != 'no' or spec.get('kill_mode') != 'mixed'):
        raise PermissionError('Not the exact predecessor API service specification')
    checked(spec['entrypoint'])
    if properties.get('MainPID') == '0' and properties.get('ActiveState') in {'inactive', 'failed'}:
        return None
    if (properties.get('Description') != 'ProWorkSim v085 api coordinator '+spec['ownership_token']
            or spec['entrypoint']['path'] not in properties.get('ExecStart', '')
            or not properties.get('ControlGroup', '').endswith('/'+scope.OLD_API_UNIT)
            or properties.get('ActiveState') != 'active' or properties.get('Restart') != 'no'
            or properties.get('KillMode') != 'mixed'):
        raise PermissionError('The predecessor process no longer has its exact owned identity')
    return helpers.process_identity(int(properties['MainPID']))


_namespace = clone_namespace(previous, scope=scope, prior=old_scope, ROOT=ROOT,
    OUT=OUT, OLD=OLD, CONTROL=CONTROL, VERSION=VERSION, __file__=__file__, identity=identity)
_namespace['identity'] = identity
show, stage, stage_value, gate = (_namespace[key] for key in ('show', 'stage', 'stage_value', 'gate'))


def rollback_before_launch():
    if any((scope.API_ROOT/name).exists() for name in ('launch-intent.json', 'execution-started.json')):
        raise PermissionError('Never reopen old admissions after successor ownership was launched')
    return _namespace['rollback']()


def validate_launch_pause():
    """A rolled-back gate must never authorize a later overlapping launch."""
    if (OUT/'stopped.json').exists():
        return
    boundary = load(OUT/'inventory-boundary.json')
    staged = stage_value()
    if (load(CONTROL).get('desired') != 0
            or identity(scope.load(staged['specification']), show()) != staged['process']
            or not acknowledged(load(OLD/'progress.json'), gate_unix=load(OUT/'gate.json')['unix'], now=time.time())):
        raise PermissionError('The acknowledged predecessor pause is not intact at launch')
    scheduled = {event['slot_id'] for line in (OLD/'events.jsonl').read_bytes().splitlines()
                 if line and (event := json.loads(line)).get('kind') == 'generation_scheduled'}
    if scheduled != set(boundary['old_scheduled_slot_ids']):
        raise PermissionError('Old scheduling advanced after the frozen ownership boundary')


def load(path):
    return json.loads(Path(path).read_bytes())


def acknowledged(progress, *, gate_unix, now):
    return (progress.get('failure') is None and not progress.get('provider_failures')
        and isinstance(progress.get('unix'), (int, float))
        and gate_unix < progress['unix'] <= now+5 and now-progress['unix'] <= 60
        and progress.get('configured_generation_limit') == 0
        and progress.get('effective_generation_limit') == 0)


def capture_boundary():
    scope.require_allowed('v086.handoff')
    if (OUT/'inventory-boundary.json').exists():
        return reference(OUT/'inventory-boundary.json')
    gate_value = load(OUT/'gate.json')
    staged = stage_value()
    if load(CONTROL).get('desired') != 0 or identity(scope.load(staged['specification']), show()) != staged['process']:
        raise PermissionError('The exact live predecessor pause is not intact')
    raw = (OLD/'progress.json').read_bytes()
    progress = json.loads(raw)
    if not acknowledged(progress, gate_unix=gate_value['unix'], now=time.time()):
        return {'status': 'waiting_for_pause_acknowledgement', 'progress_unix': progress.get('unix')}
    events_raw = (OLD/'events.jsonl').read_bytes()
    events = [json.loads(line) for line in events_raw.splitlines() if line]
    # An old loop may have scheduled before observing the new desired value.
    # Freeze after a fresh acknowledgement and include every such identity.
    scheduled = {event['slot_id'] for event in events if event.get('kind') == 'generation_scheduled'}
    cursor_raw = (OLD/'cursor.json').read_bytes()
    cursor = json.loads(cursor_raw)
    if cursor.get('failure') is not None:
        raise ValueError('Predecessor reported a failure while partitioning ownership')
    if not set(cursor.get('active_generation', [])) <= scheduled:
        raise ValueError('An active predecessor future lacks a scheduling record')
    folder = OUT/'boundary'
    folder.mkdir()
    cursor_ref = write_new(folder/'cursor.json', cursor_raw)
    progress_ref = write_new(folder/'progress.json', raw)
    events_ref = write_new(folder/'events.jsonl', events_raw)
    return write_new(OUT/'inventory-boundary.json', {'version': VERSION, 'unix': time.time(),
        'stage': reference(OUT/'stage.json'), 'gate': reference(OUT/'gate.json'),
        'cursor': cursor_ref, 'progress': progress_ref, 'events': events_ref,
        'old_scheduled_slot_ids': sorted(scheduled), 'old_tasks_cancelled': False,
        'old_final_history_is_pending': True, 'Qwen_lifecycle_operations': 0})


def quiet_reasons(progress, cursor, claims, reserved, *, now, gate_unix):
    reasons = previous.quiet_reasons(progress, cursor, claims, reserved, now=now, gate_unix=gate_unix)
    for name in ('active_grading_jobs', 'pending_grading_jobs'):
        if cursor.get(name):
            reasons.append(name+'_not_empty')
    return reasons


def old_observation(old_owned, *, allocation_locked=False):
    """Restrict old-owner tests to old IDs; new tasks never prevent retirement."""
    control = load(CONTROL)
    if control.get('desired') != 0:
        raise PermissionError('Predecessor admissions reopened during rolling execution')
    cursor_raw = (OLD/'cursor.json').read_bytes()
    progress_raw = (OLD/'progress.json').read_bytes()
    cursor, progress = json.loads(cursor_raw), json.loads(progress_raw)
    folder = scope.original.BATCH_ROOT/'resource-claims'
    if allocation_locked:
        active = [load(path) for path in folder.glob('active-*.json')]
    else:
        with (folder/'allocation.lock').open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            active = [load(path) for path in folder.glob('active-*.json')]
    claims = [item['key'] for item in active if item.get('spec', {}).get('slot_id') in old_owned]
    ledger = scope.original.PREDECESSOR_ROOT/'api-budget/ledger.sqlite3'
    with closing(sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        pending_requests = [key for (key,slot) in db.execute("SELECT request_id,slot_id FROM requests WHERE status='reserved'")
                            if slot in old_owned]
    gate_unix = load(OUT/'gate.json')['unix']
    reasons = quiet_reasons(progress, cursor, claims, len(pending_requests),
                                    now=time.time(), gate_unix=gate_unix)
    # The old async scoring lifecycle must finish naturally. A prepared request
    # is not proof that its archive validation or delivery work has stopped.
    return {'ready': not reasons, 'reasons': reasons, 'cursor': cursor,
        'cursor_raw': cursor_raw, 'progress_raw': progress_raw,
        'cursor_sha256': hashlib.sha256(cursor_raw).hexdigest(),
        'old_active_claims': claims, 'old_reserved_requests': pending_requests,
        'pending_score_jobs': []}


def retire_old(old_owned):
    scope.require_allowed('v086.handoff')
    marker = OUT/'stopped.json'
    if marker.exists():
        return reference(marker)
    existing_intent = OUT/'signal-intent.json'
    if existing_intent.exists():
        staged = stage_value()
        if identity(scope.load(staged['specification']), show()) is not None:
            raise ValueError('A recorded predecessor signal still needs inactive-process verification')
        return finish_retirement(reference(existing_intent), old_owned)
    proof = old_observation(old_owned)
    if not proof['ready']:
        raise ValueError('Old API work is still active')
    staged = stage_value()
    spec = scope.load(staged['specification'])
    props = show()
    process = identity(spec, props)
    if process != staged['process']:
        raise PermissionError('The exact old API process changed')
    processes = (Path('/sys/fs/cgroup')/props['ControlGroup'].lstrip('/')/'cgroup.procs').read_text().split()
    if processes != [str(process['pid'])]:
        raise ValueError('The old API service still contains another process')
    final = OUT/'final-old'/proof['cursor_sha256']
    final.mkdir(parents=True, exist_ok=True)
    cursor_ref = reference(final/'cursor.json') if (final/'cursor.json').exists() else write_new(final/'cursor.json', proof['cursor_raw'])
    # Progress can advance without the cursor changing. Each final proof keeps
    # its own bytes; an earlier pre-signal race does not poison later attempts.
    progress_path = final/(hashlib.sha256(proof['progress_raw']).hexdigest()+'.json')
    progress_ref = reference(progress_path) if progress_path.exists() else write_new(progress_path, proof['progress_raw'])
    if checked(cursor_ref).read_bytes() != proof['cursor_raw']:
        raise ValueError('A frozen old cursor differs from its exact content identity')
    with (scope.original.BATCH_ROOT/'resource-claims/allocation.lock').open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # No old worker can claim/create a grader between the last proof and
        # the signal. Never block a live official test: active claims reject.
        final_proof = old_observation(old_owned, allocation_locked=True)
        fd = helpers.open_process_handle(process['pid'])
        try:
            if (not final_proof['ready'] or helpers.process_identity(process['pid']) != process
                    or final_proof['cursor_sha256'] != proof['cursor_sha256']):
                raise PermissionError('Old quiet boundary changed before the exact signal')
            intent = write_new(OUT/'signal-intent.json', {'process': process, 'signal': 'SIGKILL',
                'old_owner_quiet': True, 'cursor': cursor_ref, 'progress': progress_ref,
                'transferable_scoring_jobs': proof['pending_score_jobs'],
                'old_live_tasks_cancelled': False, 'parent_cleanup_finally_intentionally_skipped': True})
            signal.pidfd_send_signal(fd, signal.SIGKILL)
        finally:
            os.close(fd)
    deadline = time.monotonic()+30
    while identity(spec, show()) is not None:
        if time.monotonic() > deadline:
            raise TimeoutError('Signalled old owner is not yet inactive')
        time.sleep(.2)
    return finish_retirement(intent, old_owned)


def finish_retirement(intent_ref, old_owned):
    """Resume only bookkeeping after a recorded exact signal and proved death."""
    intent = scope.load(intent_ref)
    staged = stage_value()
    if (intent.get('process') != staged['process'] or intent.get('signal') != 'SIGKILL'
            or intent.get('old_live_tasks_cancelled') is not False
            or identity(scope.load(staged['specification']), show()) is not None):
        raise PermissionError('Finalization requires the exact recorded inactive predecessor')
    cursor_ref, progress_ref = intent['cursor'], intent['progress']
    cursor = scope.load(cursor_ref)
    release = old_scope.release_api_coordinator(reference(old_scope.CLAIM_FILE))
    value = {'version': VERSION,
        'old_cursor': cursor_ref, 'old_progress': progress_ref,
        'old_owned_slot_ids': sorted(old_owned),
        'pending_score_jobs': intent['transferable_scoring_jobs'],
        **{key: {slot: entry for slot, entry in cursor.get(key, {}).items() if slot in old_owned}
           for key in ('generation', 'scores', 'deliveries')},
        'old_auxiliary_release': release, 'old_results_rewritten': False,
        'new_model_calls': 0}
    historical = scope.API_ROOT/'historical-results.json'
    if historical.exists():
        if scope.load(reference(historical)) != value:
            raise ValueError('The predecessor final history is already sealed differently')
    else:
        write_new(historical, value)
    return write_new(OUT/'stopped.json', {'version': VERSION, 'unix': time.time(), 'cursor': cursor_ref,
        'progress': progress_ref, 'signal': intent_ref, 'old_auxiliary_release': release,
        'old_live_tasks_cancelled': False, 'Qwen_lifecycle_operations': 0,
        'parent_stopped_or_recreated': False})


class OldDrainMonitor:
    def __init__(self, old_owned, event, *, interval=15):
        self.old_owned, self.event, self.interval = set(old_owned), event, interval
        self.stop, self.finished = threading.Event(), threading.Event()
        self.thread = threading.Thread(target=self._run, name='v086-old-API-drain', daemon=False)
        self.last, self.first_quiet = {}, None

    def start(self):
        self.thread.start()

    def _run(self):
        while not self.stop.is_set():
            try:
                if (OUT/'stopped.json').exists():
                    self.finished.set()
                    return
                proof = old_observation(self.old_owned)
                self.last = {'unix': time.time(), 'ready': proof['ready'], 'reasons': proof['reasons'],
                    'old_active_claims': proof['old_active_claims'], 'old_reserved_requests': proof['old_reserved_requests']}
                atomic_write(OUT/'drain-progress.json', json_bytes(self.last))
                if proof['ready']:
                    if self.first_quiet is None:
                        self.first_quiet = time.monotonic()
                    elif time.monotonic()-self.first_quiet >= 3:
                        ref = retire_old(self.old_owned)
                        self.event('predecessor_retired', receipt=ref)
                        self.finished.set()
                        return
                else:
                    self.first_quiet = None
            except Exception as error:
                self.first_quiet = None
                self.last = {'unix': time.time(), 'ready': False, 'error': str(error)}
                atomic_write(OUT/'drain-progress.json', json_bytes(self.last))
                self.event('predecessor_drain_requires_review', error=str(error), new_tasks_cancelled=False)
            self.stop.wait(self.interval)

    def close(self):
        self.stop.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=60)
        if self.thread.is_alive():
            raise RuntimeError('Owned old-drain monitor did not close')
