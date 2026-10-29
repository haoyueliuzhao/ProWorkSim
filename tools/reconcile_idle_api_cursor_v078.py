"""Repair one idle API scheduling checkpoint from immutable completed results.

This never edits an experiment result, patch, score, ledger or running source.
The original cursor is archived before replacing only its stale active entries.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import time

from proworksim import software_benchmark_adaptive_scope_v076 as scope
from proworksim import software_benchmark_dispatch_v066 as policy
from proworksim import software_benchmark_handoff_v075 as handoff
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.storage import atomic_write

VERSION = 'v078-proven-idle-API-checkpoint-reconciliation-r1'
API_ROOT = handoff.OLD_ROOTS['api']
CURSOR = API_ROOT / 'cursor.json'
CLAIMS = policy.BATCH_ROOT / 'resource-claims'
OUT = policy.ROOT / 'artifacts/software-benchmark-v078/idle-api-cursor-r1'


def load(ref):
    return json.loads(checked(ref).read_bytes())


def frozen_coordinator():
    spec = importlib.util.spec_from_file_location('v078_frozen_coordinator',
        policy.ROOT / 'tools/run_full_benchmark_v066.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_idle(progress, cursor, active, reserved, control, *, now, gate_unix):
    if (control.get('desired') != 0 or progress.get('phase') != 'waiting'
            or progress.get('capacity_wait_reason') != 'invalid_concurrency_control'
            or progress.get('effective_generation_limit') != 0
            or progress.get('actual_generation_futures') != 0
            or progress.get('active_generation') != 0
            or progress.get('failure') is not None or cursor.get('failure') is not None
            or not isinstance(progress.get('unix'), (int, float))
            or not -5 <= now-progress['unix'] <= 60 or progress['unix'] <= gate_unix):
        raise ValueError('The original API dispatcher is not demonstrably paused and idle')
    if reserved != 0 or any(':DEEPSEEK_' in item.get('spec', {}).get('slot_id', '') for item in active):
        raise ValueError('An API request or owned physical resource remains active')
    ghosts = cursor.get('active_generation')
    if not isinstance(ghosts, list) or not ghosts or len(ghosts) != len(set(ghosts)):
        raise ValueError('A nonempty unique stale generation list is required')
    if cursor.get('active_grading') or cursor.get('pending_scores') or cursor.get('pending_controls'):
        raise ValueError('This narrow repair does not rewrite active or pending scoring queues')
    return ghosts


def validate_result(row, result_ref, result, quiet, events, *, cursor_unix, progress_unix):
    slot = row['slot_id']
    if (row.get('model_key') != 'DEEPSEEK' or row.get('input_plus_output_tokens') != 5_000_000
            or result.get('status') != 'closed' or result.get('model_key') != 'DEEPSEEK'
            or result.get('slot_id') != slot or result.get('instance_id') != row['instance_id']
            or result.get('configuration') != row['configuration']
            or result.get('condition_id') != row['condition_id'] or result.get('seed') != row['seed']
            or result.get('automatic_replay') is not False
            or result.get('model_dispatch_started') is not True
            or type(result.get('model_calls')) is not int or result['model_calls'] <= 0
            or result.get('retained_objects') != [] or result.get('shared_integrity_fault')):
        raise ValueError('The stale entry does not identify the exact completed original API episode')
    if (quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []
            or quiet.get('create_result_unknown') is not False
            or quiet.get('all_owned_objects_removed') is not True
            or quiet.get('retained_objects') != []
            or set(quiet.get('removed_roles', [])) != {'actor', 'controller', 'volume'}):
        raise ValueError('Original episode cleanup is not fully proven')
    episode_events = [item for item in events if item.get('slot_id') == slot
                      and item.get('kind') in {'generation_scheduled', 'generation_finished'}]
    if (not episode_events or episode_events[-1].get('kind') != 'generation_finished'
            or episode_events[-1].get('status') != 'closed'
            or not cursor_unix < episode_events[-1].get('unix', 0) <= progress_unix):
        raise ValueError('No later original closed event reconciles the stale cursor')
    return {'slot_id': slot, 'result': result_ref, 'finished_event': episode_events[-1]}


def inspect_locked():
    """Called under the original allocation lock; all other evidence is read-only."""
    stage = handoff.stage_value()
    gate = load(reference(scope.HANDOFF_ROOT / 'gate.json'))
    if not handoff.gate_intact(stage) or (scope.HANDOFF_ROOT / 'coordinators-stopped.json').exists():
        raise ValueError('The still-running original handoff gate must be intact')
    actor = stage['coordinators']['api']
    if handoff.validate_unit('api', load(actor['specification']), handoff.show('api')) != actor['process']:
        raise ValueError('Original API coordinator ownership changed')
    raw = CURSOR.read_bytes()
    cursor = json.loads(raw)
    progress_raw = (API_ROOT / 'progress.json').read_bytes()
    progress = json.loads(progress_raw)
    control_raw = handoff.API_CONTROL.read_bytes()
    active = [load(reference(path)) for path in CLAIMS.glob('active-*.json')]
    ledger = policy.PREDECESSOR_ROOT / 'api-budget/ledger.sqlite3'
    with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        reserved = db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0]
    ghosts = require_idle(progress, cursor, active, reserved, json.loads(control_raw),
                          now=time.time(), gate_unix=gate['unix'])
    event_raw = (API_ROOT / 'events.jsonl').read_bytes()
    events = [json.loads(line) for line in event_raw.splitlines() if line]
    if any(item.get('kind') == 'generation_scheduled' and item['unix'] > gate['unix'] for item in events):
        raise ValueError('New generation was scheduled after the administrative gate')
    rows = {row['slot_id']: row for row in load(reference(policy.PLAN_FILE))['rows']}
    replacements, evidence = {}, []
    base = frozen_coordinator()
    for slot in ghosts:
        row = rows[slot]
        if slot in cursor['generation']:
            raise ValueError('This repair cannot replace an existing terminal generation record')
        folder = policy.BATCH_ROOT / 'episodes' / str(row['slot_index'])
        result_ref = reference(folder / 'result.json')
        result = load(result_ref)
        quiet_ref = result['quiescence']
        if Path(quiet_ref['path']).resolve() != folder / 'quiescence.json':
            raise ValueError('Cleanup evidence is outside the exact original episode')
        quiet = load(quiet_ref)
        item = validate_result(row, result_ref, result, quiet, events,
                               cursor_unix=cursor['unix'], progress_unix=progress['unix'])
        if set(quiet.get('claims', {})) != {'actor', 'controller', 'volume'}:
            raise ValueError('All original physical creation claims are required')
        releases = {}
        for role, claim_ref in quiet['claims'].items():
            key = f"{role}-{row['slot_index']}"
            if Path(claim_ref['path']).resolve() != CLAIMS / (key+'.json'):
                raise ValueError('Cleanup binds another physical identity')
            claim = load(claim_ref)
            if (claim.get('key') != key or claim.get('spec', {}).get('role') != role
                    or claim['spec'].get('slot_id') != slot
                    or claim['spec'].get('instance_id') != row['instance_id']):
                raise ValueError('Physical claim does not identify this original episode')
            release_ref = reference(CLAIMS / (key+'.released.json'))
            release = load(release_ref)
            if release.get('claim') != claim_ref or release.get('quiescent') is not True:
                raise ValueError('Original owned object release is unproven')
            releases[role] = release_ref
        replacements[slot] = {'result': result_ref, 'status': 'closed', 'entered': True,
            'administrative_truncation': base.administrative_truncation(result),
            'retained_objects': [], 'prior_zero_generation_attempt': None}
        evidence.append({**item, 'quiescence': quiet_ref, 'physical_releases': releases,
            'score_request_exists': (policy.GRADING_ROOT/f"score-{row['slot_index']}"/'request.json').exists(),
            'score_completion_exists': (policy.GRADING_ROOT/f"score-{row['slot_index']}"/'completion.json').exists()})
    return {'cursor': cursor, 'cursor_raw': raw, 'progress_raw': progress_raw,
        'control_raw': control_raw, 'events_raw': event_raw, 'replacements': replacements,
        'evidence': evidence, 'reserved_requests': reserved,
        'API_active_physical_claims': 0, 'gate': reference(scope.HANDOFF_ROOT/'gate.json')}


def revised_cursor(cursor, replacements, evidence_ref, *, now):
    revised = copy.deepcopy(cursor)
    if set(replacements) != set(cursor['active_generation']) or set(replacements) & cursor['generation'].keys():
        raise ValueError('Only the stale active generation identities may be reconciled')
    revised['generation'].update(replacements)
    revised['active_generation'] = []
    revised['unix'] = now
    revised['administrative_cursor_reconciliation'] = {'version': VERSION, 'evidence': evidence_ref,
        'immutable_generation_results_changed': False, 'scores_changed': False,
        'money_ledger_changed': False, 'new_model_calls': 0}
    return revised


def execute(*, apply=False):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Only the project ordinary user may repair this checkpoint')
    scope.require_allowed('v076.handoff')
    with (CLAIMS/'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX if apply else fcntl.LOCK_SH)
        completed = OUT/'completed.json'
        if completed.exists():
            receipt = load(reference(completed))
            if receipt['after'] != reference(CURSOR):
                raise ValueError('The checkpoint has moved since the recorded one-time reconciliation')
            return {'status': 'already_applied', 'receipt': reference(completed)}
        observation = inspect_locked()
        summary = {'version': VERSION, 'eligible': True, 'apply_requested': apply,
            'stale_slots': list(observation['replacements']), 'evidence': observation['evidence'],
            'new_model_calls': 0, 'immutable_records_modified': False}
        if not apply:
            return summary
        if OUT.exists():
            raise FileExistsError('Inspect the existing reconciliation archive before any retry')
        OUT.mkdir(parents=True)
        originals = {}
        for name, key in [('cursor','cursor_raw'),('progress','progress_raw'),
                          ('concurrency-control','control_raw'),('events','events_raw')]:
            originals[name] = write_new(OUT/(name+'-before.json' if name != 'events' else 'events-before.jsonl'),
                                        observation[key])
        proof_ref = write_new(OUT/'evidence.json', {**summary, 'originals': originals,
            'tool_source': reference(__file__), 'gate': observation['gate'],
            'reserved_requests': 0, 'active_API_physical_claims': 0,
            'reason': 'The paused frozen admission loop reports zero live futures but does not flush its cursor',
            'prepared_unix': time.time()})
        revised = revised_cursor(observation['cursor'], observation['replacements'], proof_ref, now=time.time())
        replacement = write_new(OUT/'cursor-reconciled.json', revised)
        # Preserve evidence first and refuse any unexpected concurrent cursor or
        # control-file writer. The held allocation lock excludes new resources.
        if (CURSOR.read_bytes() != observation['cursor_raw']
                or handoff.API_CONTROL.read_bytes() != observation['control_raw']
                or (API_ROOT/'events.jsonl').read_bytes() != observation['events_raw']):
            raise ValueError('Original dispatcher state changed before the checkpoint commit')
        atomic_write(CURSOR, checked(replacement).read_bytes())
        receipt = write_new(completed, {'version': VERSION, 'applied_unix': time.time(),
            'before': originals['cursor'], 'after': reference(CURSOR), 'prepared_replacement': replacement,
            'evidence': proof_ref, 'stale_slots_removed': list(observation['replacements']),
            'immutable_results_scores_fees_sources_modified': False, 'new_model_calls': 0,
            'old_coordinator_signalled': False})
        return {'status': 'applied', 'receipt': receipt, 'slots': summary['stale_slots']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--check', action='store_true')
    action.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(execute(apply=args.apply), ensure_ascii=False))
