"""Publish a proved natural budget exit for the unchanged live v086 reader.

Ordinary-user administrative bookkeeping only: no signals, Docker operations,
parent lifecycle calls, model execution, ledger writes, or original-record edits.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import signal
import sqlite3
import threading
import time

from proworksim import software_benchmark_rolling_scope_v086 as scope
from proworksim import software_benchmark_rolling_handoff_v086 as handoff
from proworksim import software_benchmark_api_scope_v085 as old_scope
from proworksim import software_benchmark_api_parent_v085 as parent
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.storage import atomic_write, json_bytes

VERSION = 'v087-readonly-proof-natural-budget-exit-administrative-handoff-r1'
OUT = scope.HANDOFF_ROOT/'natural-exit-v087'
WATCH_ROOT = scope.ROOT/'runs/software-benchmark-v087/natural-exit-watch-r1'


def read(path):
    return json.loads(Path(path).read_bytes())


def validate_summary(summary, cursor, *, old_owned, gate_unix):
    if (summary.get('version') != 'v085-FD-bounded-original-API-recovery-r1'
            or summary.get('failure') is not None or cursor.get('failure') is not None
            or summary.get('last_api_status', {}).get('state') != 'cash_exhausted'
            or summary.get('provider_failures', {}).get('DEEPSEEK', {}).get('reason') != 'api_monetary_budget_exhausted'
            or not isinstance(summary.get('finished_unix'), (int, float))
            or summary['finished_unix'] <= gate_unix):
        raise ValueError('Only an intact official natural monetary-budget exit is eligible')
    for value, names in ((summary, ('pending_grading_jobs', 'unentered_controls', 'unentered_scores', 'retained_objects')),
                         (cursor, ('active_generation', 'active_grading', 'active_grading_jobs',
                                   'pending_grading_jobs', 'pending_scores', 'pending_controls'))):
        if any(value.get(name) for name in names):
            raise ValueError('Official asynchronous work or owned objects remain unsettled')
    if not set(old_owned) <= summary.get('generation', {}).keys():
        raise ValueError('A predecessor-owned original identity is missing from its final summary')
    for key in ('generation', 'scores', 'deliveries'):
        if summary.get(key) != cursor.get(key):
            raise ValueError('The final cursor and official summary disagree')
    return {key: {slot: entry for slot, entry in summary[key].items() if slot in old_owned}
            for key in ('generation', 'scores', 'deliveries')}


def require_inactive(staged):
    specification = scope.load(staged['specification'])
    properties = handoff.show()
    if handoff.identity(specification, properties) is not None:
        raise ValueError('The exact old user service is still active')
    process = staged['process']
    stat = Path('/proc')/str(process['pid'])/'stat'
    try:
        start = int(stat.read_text().rsplit(')', 1)[1].split()[19])
    except FileNotFoundError:
        pid_state = 'original_PID_absent'
    else:
        if start == process['start_ticks']:
            raise ValueError('The original coordinator process is still alive')
        pid_state = 'PID_reused_by_different_start_time_original_process_gone'
    cgroup = Path('/sys/fs/cgroup')/staged['properties']['ControlGroup'].lstrip('/')
    if cgroup.exists() and (cgroup/'cgroup.procs').read_text().strip():
        raise ValueError('The old service cgroup still contains processes')
    return {'properties': properties, 'original_process': process, 'PID_state': pid_state,
            'service_cgroup_absent_or_empty': True, 'observed_unix': time.time()}


def require_quiet_receipt(ref):
    value = scope.load(ref)
    if (value.get('quiescent') is not True or value.get('cleanup_errors') != []
            or value.get('create_result_unknown') is not False or value.get('retained_objects')):
        raise ValueError('An original operation lacks trustworthy owned-object cleanup')
    for identity in value.get('owned_container_ids', []):
        if not isinstance(identity, str) or len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
            raise ValueError('Cleanup references an invalid container identity')
        for owner in ('system.slice', parent.SLICE):
            if (Path('/sys/fs/cgroup')/owner/f'docker-{identity}.scope').exists():
                raise ValueError('A supposedly removed owned container still has a kernel cgroup')
    return value


def verify_changed_results(history, inventory, rows):
    """Trust unchanged sealed history; verify each newly finished original result."""
    by_id = {row['slot_id']: row for row in rows}
    verified = []
    for slot, entry in history['generation'].items():
        before = inventory['generation'].get(slot)
        if entry == before and before.get('status') != 'external_running':
            if entry.get('result'):
                checked(entry['result'])
            continue
        row = by_id[slot]
        if entry.get('status') == 'not_started' and entry.get('entered') is False and not entry.get('result'):
            verified.append({'slot_id': slot, 'state': 'original_unentered_budget_record'})
            continue
        if entry.get('status') not in ('closed', 'technical_unknown') or not entry.get('result'):
            raise ValueError('A newly closed predecessor generation lacks its original result')
        result = scope.load(entry['result'])
        if (result.get('slot_id') != slot or result.get('configuration') != row['configuration']
                or result.get('status') != entry['status'] or result.get('retained_objects')):
            raise ValueError('An original result changed task, configuration or terminal status')
        require_quiet_receipt(result['quiescence'])
        verified.append({'slot_id': slot, 'state': entry['status'], 'result': entry['result'],
                         'quiescence': result['quiescence']})
    return verified


def verify_async_outcomes(history):
    records = []
    for path in sorted((scope.OLD_API_ROOT/'async-grading-jobs').glob('*/job.json')):
        job_ref, job = reference(path), read(path)
        slot = job.get('slot_id')
        if slot not in history['generation']:
            raise ValueError('Old asynchronous work names an identity owned by the successor')
        entry = history['generation'][slot]
        if job.get('generation_result') != entry.get('result'):
            raise ValueError('Old asynchronous scoring changed its frozen candidate')
        outcome_path = path.parent/'outcome.json'
        if not outcome_path.exists():
            raise ValueError('An old asynchronous job has no sealed outcome')
        outcome_ref, outcome = reference(outcome_path), read(outcome_path)
        if outcome.get('job') != job_ref or outcome.get('fatal') is not False:
            raise ValueError('An old asynchronous outcome lacks exact identity or safe cleanup')
        request_ref = outcome.get('request')
        if request_ref:
            request = scope.load(request_ref)
            folder = Path(request['directory'])
            if (folder != scope.original.GRADING_ROOT/request['resource_key']
                    or Path(request_ref['path']) != folder/'request.json'
                    or request.get('slot_id') != slot
                    or request.get('generation_result') != entry.get('result')
                    or outcome.get('status') != 'completed' or outcome.get('cleanup_proven') is not True):
                raise ValueError('Consumed score lacks exact completed request identity')
            done = scope.load(reference(folder/'completion.json'))
            if done.get('request') != request_ref or done != outcome.get('completion'):
                raise ValueError('The original scoring completion and sealed async outcome disagree')
            require_quiet_receipt(reference(folder/'quiescence.json'))
            target = history['scores' if job['kind'] == 'code' else 'deliveries'].get(slot, {})
            if target.get('request') != request_ref or target.get('completion') != done:
                raise ValueError('The official summary omitted a completed old score')
        elif outcome.get('status') != 'preparation_unknown':
            raise ValueError('A request-less scoring outcome is not a closed preparation exception')
        records.append({'job': job_ref, 'outcome': outcome_ref, 'request': request_ref})
    return records


def observe():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Administrative history publication is ordinary-user only')
    scope.original.require_v066_allowed('v066.run')
    for owner in (scope, old_scope):
        authority = scope.load(reference(owner.AUTH_FILE))
        for source in scope.load(authority['source_index'])['files']:
            checked(source)
    if (scope.HANDOFF_ROOT/'signal-intent.json').exists():
        raise ValueError('A signal attempt already exists; this is not a purely natural exit')
    staged = handoff.stage_value()
    inactive = require_inactive(staged)
    inventory_ref = reference(scope.INVENTORY_FILE)
    inventory = scope.load(inventory_ref)
    old_owned = set(inventory['old_owned_slot_ids'])
    if old_owned & set(inventory['allowed_generation_slot_ids']):
        raise ValueError('The frozen rolling ownership sets overlap')
    summary_ref = reference(scope.OLD_API_ROOT/'run-summary.json')
    cursor_ref = reference(scope.OLD_API_ROOT/'cursor.json')
    summary, cursor = scope.load(summary_ref), scope.load(cursor_ref)
    history = validate_summary(summary, cursor, old_owned=old_owned,
        gate_unix=scope.load(reference(scope.HANDOFF_ROOT/'gate.json'))['unix'])
    rows = scope.load(reference(scope.original.PLAN_FILE))['rows']
    results = verify_changed_results(history, inventory, rows)
    outcomes = verify_async_outcomes(history)
    directory = scope.original.BATCH_ROOT/'resource-claims'
    with (directory/'allocation.lock').open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        claims = [read(path) for path in directory.glob('active-*.json')]
        if any(item.get('spec', {}).get('slot_id') in old_owned for item in claims):
            raise ValueError('Old-owned resources still have active claims')
        ledger = scope.original.PREDECESSOR_ROOT/'api-budget/ledger.sqlite3'
        with closing(sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True)) as db:
            reserved = [key for key, slot in db.execute("SELECT request_id,slot_id FROM requests WHERE status='reserved'")
                        if slot in old_owned]
            used_slots = {slot for (slot,) in db.execute('SELECT DISTINCT slot_id FROM requests')}
        if reserved:
            raise ValueError('Old-owned API reservations are still in flight')
        for slot, entry in history['generation'].items():
            if entry.get('status') == 'not_started' and slot in used_slots:
                raise ValueError('An original unentered record already has API request evidence')
    release_ref = reference(scope.OLD_API_ROOT/'coordinator-capacity-released.json')
    release = scope.load(release_ref)
    if (old_scope.LEASE_FILE.exists() or release.get('claim') != reference(old_scope.CLAIM_FILE)
            or release.get('quiescent') is not True):
        raise ValueError('The exact old auxiliary lease lacks its existing release receipt')
    # No live-parent qualification is required: the natural finally may already
    # have released an empty parent. This helper never changes its lifecycle.
    parent_release = reference(parent.RELEASED) if parent.RELEASED.exists() else None
    try:
        reader_progress = read(scope.API_ROOT/'progress.json')
        reader = {key: reader_progress.get(key) for key in ('unix', 'phase', 'failure', 'active_generation', 'active_grading')}
    except (OSError, ValueError) as error:
        reader = {'observation_unavailable': type(error).__name__+': '+str(error)}
    return {'version': VERSION, 'source': reference(__file__), 'observed_unix': time.time(),
        'stage': reference(scope.HANDOFF_ROOT/'stage.json'), 'inventory': inventory_ref,
        'inactive': inactive, 'summary': summary_ref, 'cursor': cursor_ref,
        'progress': reference(scope.OLD_API_ROOT/'progress.json'),
        'history': history, 'old_owned_slot_ids': sorted(old_owned),
        'newly_verified_generation': results, 'verified_async_outcomes': outcomes,
        'old_active_claims': [], 'old_reserved_requests': [], 'old_auxiliary_release': release_ref,
        'parent_release_already_present': parent_release, 'helper_parent_operations': 0,
        'successor_progress_observed_not_modified': reader,
        'successor_failures_repaired_or_reclassified': False,
        'signals_sent': 0, 'ledger_records_modified': False, 'original_results_rewritten': False}


def publish():
    marker = scope.HANDOFF_ROOT/'stopped.json'
    if marker.exists():
        return {'status': 'handoff_already_completed', 'receipt': reference(marker), 'mutations': 0}
    proof = observe()
    # Recheck exact dead identity after scanning original artifacts; never take
    # over a restarted unit or race the frozen monitor's signal path.
    require_inactive(handoff.stage_value())
    if (scope.HANDOFF_ROOT/'signal-intent.json').exists():
        raise ValueError('A signal path appeared during natural-exit observation')
    OUT.mkdir(parents=True, exist_ok=True)
    proof_path = OUT/'proof.json'
    if proof_path.exists():
        saved = scope.load(reference(proof_path))
        for key in ('version', 'source', 'stage', 'inventory', 'summary', 'cursor', 'history', 'old_auxiliary_release'):
            if saved.get(key) != proof.get(key):
                raise ValueError('Existing natural-exit proof describes a different final identity')
    else:
        write_new(proof_path, proof)
    proof_ref = reference(proof_path)
    historical = {'version': handoff.VERSION, 'kind': 'natural_budget_exit',
        'natural_exit_proof': proof_ref, 'old_cursor': proof['cursor'], 'old_progress': proof['progress'],
        'old_owned_slot_ids': proof['old_owned_slot_ids'], 'pending_score_jobs': [],
        **proof['history'], 'old_auxiliary_release': proof['old_auxiliary_release'],
        'old_results_rewritten': False, 'new_model_calls': 0}
    target = scope.API_ROOT/'historical-results.json'
    if target.exists():
        if scope.load(reference(target)) != historical:
            raise ValueError('The live reader already has a different sealed historical result')
    else:
        write_new(target, historical)
    receipt = write_new(marker, {'version': handoff.VERSION, 'kind': 'natural_budget_exit',
        'unix': time.time(), 'natural_exit_proof': proof_ref, 'signal': None, 'signals_sent': 0,
        'cursor': proof['cursor'], 'progress': proof['progress'],
        'old_auxiliary_release': proof['old_auxiliary_release'],
        'old_live_tasks_cancelled': False, 'Qwen_lifecycle_operations': 0,
        'parent_stopped_or_recreated': False, 'helper_parent_operations': 0,
        'parent_release_already_present': proof['parent_release_already_present']})
    return {'status': 'natural_exit_history_published', 'receipt': receipt,
            'historical_results': reference(target), 'signals_sent': 0, 'model_calls': 0}


def watch(*, interval_seconds=15, maximum_seconds=4*3600):
    if not 1 <= interval_seconds <= 60 or not 1 <= maximum_seconds <= 4*3600:
        raise ValueError('Watch is bounded to 1..60-second polling and at most four hours')
    stop = threading.Event()
    handlers = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
    WATCH_ROOT.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        while not stop.is_set() and time.monotonic()-started < maximum_seconds:
            try:
                if (not (scope.HANDOFF_ROOT/'stopped.json').exists()
                        and not (scope.OLD_API_ROOT/'run-summary.json').exists()):
                    value = {'status': 'waiting_for_predecessor_summary',
                        'full_evidence_validation_performed': False, 'signals_sent': 0}
                else:
                    value = publish()
            except Exception as error:
                value = {'status': 'waiting_for_proven_natural_exit',
                    'error': {'type': type(error).__name__, 'message': str(error)[:4000]},
                    'runtime_objects_modified': False, 'signals_sent': 0}
            atomic_write(WATCH_ROOT/'progress.json', json_bytes({'version': VERSION,
                'unix': time.time(), 'elapsed_seconds': time.monotonic()-started,
                'maximum_seconds': maximum_seconds, 'interval_seconds': interval_seconds, **value}))
            if value['status'] in ('handoff_already_completed', 'natural_exit_history_published'):
                return value
            stop.wait(min(interval_seconds, max(0, maximum_seconds-(time.monotonic()-started))))
        value = {'status': 'watch_stopped' if stop.is_set() else 'watch_deadline_reached',
                 'history_completion_claimed': False, 'runtime_objects_modified': False, 'signals_sent': 0}
        atomic_write(WATCH_ROOT/'progress.json', json_bytes({'version': VERSION, 'unix': time.time(), **value}))
        return value
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--observe', '--inspect', dest='observe', action='store_true')
    group.add_argument('--publish', '--execute', dest='publish', action='store_true')
    group.add_argument('--watch', action='store_true')
    parser.add_argument('--interval-seconds', type=int, default=15)
    parser.add_argument('--maximum-seconds', type=int, default=4*3600)
    args = parser.parse_args()
    if args.observe:
        proof = observe()
        value = {'status': 'natural_exit_verified_read_only', 'version': VERSION,
            'summary': proof['summary'], 'cursor': proof['cursor'], 'inactive': proof['inactive'],
            'old_owned_slots': len(proof['old_owned_slot_ids']),
            'verified_async_jobs': len(proof['verified_async_outcomes']),
            'parent_release_already_present': proof['parent_release_already_present'],
            'successor_progress_observed_not_modified': proof['successor_progress_observed_not_modified'],
            'signals_sent': 0, 'mutations': 0}
    else:
        value = (publish() if args.publish else
                 watch(interval_seconds=args.interval_seconds, maximum_seconds=args.maximum_seconds))
    print(json.dumps(value, ensure_ascii=False))
