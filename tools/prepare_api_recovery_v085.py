"""Freeze original API outcomes after EMFILE; admit only untouched identities."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import fcntl
from functools import lru_cache
import importlib.util
import json
import resource
import sqlite3
import subprocess
import time

from proworksim import software_benchmark_api_scope_v085 as scope
from proworksim import software_benchmark_api_parent_v085 as parent
from proworksim.software_benchmark_async_queue_v082 import not_consumed
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

VERSION = 'v085-API-EMFILE-original-identity-recovery-r1'


@lru_cache(maxsize=1)
def original_coordinator():
    spec = importlib.util.spec_from_file_location('v085_original_coordinator', scope.ROOT/'tools/run_full_benchmark_v066.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def old_inactive():
    response = subprocess.run(['systemctl', '--user', 'show', scope.OLD_API_UNIT, '--no-pager',
        '--property=ActiveState,SubState,MainPID'], env=user_manager_environment(),
        capture_output=True, text=True, timeout=20)
    props = dict(line.split('=', 1) for line in response.stdout.splitlines() if '=' in line)
    if response.returncode or props.get('MainPID') != '0' or props.get('ActiveState') not in ('inactive', 'failed'):
        raise ValueError('The exact failed predecessor is not inactive')
    return {'unit': scope.OLD_API_UNIT, 'properties': props, 'unix': time.time()}


def terminal_result(row, ref):
    value = scope.load(ref)
    if (any(value.get(key) != row[key] for key in ('slot_id', 'configuration', 'condition_id', 'model_key'))
            or value.get('status') not in ('closed', 'technical_unknown')):
        raise ValueError('Retained terminal result belongs to another original identity')
    quiet = scope.load(value['quiescence'])
    if (quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []
            or quiet.get('create_result_unknown') is not False or value.get('retained_objects')):
        raise ValueError('Retained API result lacks complete physical quiescence')
    return {'result': ref, 'status': value['status'], 'entered': True,
        'administrative_truncation': original_coordinator().administrative_truncation(value),
        'retained_objects': [], 'prior_zero_generation_attempt': None}


def original_score(row, generation, endpoint):
    """Return retained score or untouched prepared job; no test is executed."""
    key = ('score-' if endpoint == 'code' else 'delivery-score-')+str(row['slot_index'])
    directory = scope.original.GRADING_ROOT/key
    path = directory/'request.json'
    if not path.exists():
        return None, (endpoint, row, generation['result'], False) if endpoint == 'code' else None
    ref = reference(path)
    request = scope.load(ref)
    if (request.get('slot_id') != row['slot_id'] or request.get('configuration') != row['configuration']
            or request.get('generation_result') != generation['result'] or request.get('resource_key') != key
            or request.get('directory') != str(directory)):
        raise ValueError('A scoring identity changed its candidate or original task')
    completion = directory/'completion.json'
    if completion.exists():
        done = scope.load(reference(completion))
        if done.get('request') != ref:
            raise ValueError('The original scoring completion has another request')
        from proworksim.software_benchmark_grading_recovery_v068 import original_grading
        if not original_grading().trustworthy_cleanup(ref):
            raise ValueError('Consumed original score lacks trustworthy cleanup')
        value = {'request': ref, 'completion': done}
        if endpoint == 'delivery':
            value['status'] = 'official_attempt_completed'
        return value, None
    if not not_consumed(ref):
        return {'status': 'technical_unknown', 'request': ref,
            'error': 'Consumed official attempt without a completed score; no replay'}, None
    return None, (endpoint, row, ref, True)


def prepare():
    scope.original.require_v066_allowed('v066.run')
    parent.require_qualified()
    if scope.INVENTORY_FILE.exists() or scope.AUTH_FILE.exists():
        raise FileExistsError('Recovery preparation is single use')
    if resource.getrlimit(resource.RLIMIT_NOFILE)[1] < scope.NOFILE:
        raise PermissionError('The host hard NOFILE is below the private unit limit')
    inactive = old_inactive()
    summary_ref = reference(scope.OLD_API_ROOT/'run-summary.json')
    summary = scope.load(summary_ref)
    failure = summary.get('failure', {})
    if (failure.get('kind') != 'coordinator_error' or failure.get('error', {}).get('type') != 'OSError'
            or 'Too many open files' not in failure.get('error', {}).get('message', '')):
        raise ValueError('This recovery is restricted to the recorded predecessor EMFILE')
    # Verify frozen old dependencies directly; its old parent cycle is released.
    prior_auth = scope.load(reference(scope.prior.AUTH_FILE))
    for ref in scope.load(prior_auth['source_index'])['files']:
        checked(ref)
    rows = [row for row in scope.load(reference(scope.original.PLAN_FILE))['rows']
            if row['model_key'] == 'DEEPSEEK' and row['input_plus_output_tokens'] == 5_000_000]
    if len(rows) != 1000:
        raise ValueError('The original two-group complete API panel must be retained')
    by_id = {row['slot_id']: row for row in rows}
    generations, scores, deliveries = (dict(summary[key]) for key in ('generation', 'scores', 'deliveries'))
    claims_root = scope.original.BATCH_ROOT/'resource-claims'
    with (claims_root/'allocation.lock').open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        for path in claims_root.glob('active-*.json'):
            value = scope.load(reference(path))
            if ':DEEPSEEK_' in value.get('spec', {}).get('slot_id', ''):
                raise ValueError('An original API object still holds an active claim')
    events_ref = reference(scope.OLD_API_ROOT/'events.jsonl')
    events = [json.loads(line) for line in checked(events_ref).read_bytes().splitlines() if line]
    scheduled = {event['slot_id'] for event in events if event.get('kind') == 'generation_scheduled'}
    ledger = scope.original.PREDECESSOR_ROOT/'api-budget/ledger.sqlite3'
    with closing(sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        requested = {slot for (slot,) in db.execute('SELECT DISTINCT slot_id FROM requests')}
        request_states = dict(db.execute('SELECT status,COUNT(*) FROM requests GROUP BY status'))
    eligible, recovered, audit = [], [], []
    for row in rows:
        slot, index = row['slot_id'], row['slot_index']
        physical = [str(path) for base in (scope.original.BATCH_ROOT, scope.original.PREDECESSOR_ROOT)
            for role in ('actor', 'controller', 'volume')
            if (path := base/'resource-claims'/f'{role}-{index}.json').exists()]
        folders = [base/'episodes'/str(index) for base in (scope.original.BATCH_ROOT, scope.original.PREDECESSOR_ROOT)
                   if (base/'episodes'/str(index)).exists()]
        if slot in generations:
            reason = 'original_terminal_preserved'
        elif slot in scheduled or slot in requested or physical or folders:
            path = scope.original.BATCH_ROOT/'episodes'/str(index)/'result.json'
            if path.exists():
                generations[slot] = terminal_result(row, reference(path))
                recovered.append(slot)
                reason = 'existing_original_terminal_reconciled'
            else:
                generations[slot] = {'status': 'technical_unknown', 'entered': bool(physical or slot in requested),
                    'result': None, 'error': 'Consumed identity has no trusted terminal result', 'automatic_replay': False}
                reason = 'consumed_without_terminal_never_replay'
        else:
            eligible.append(slot)
            reason = 'unused_original_identity'
        audit.append({'slot_id': slot, 'slot_index': index, 'reason': reason, 'consumed_claims': physical})
    jobs, reconciliations = [], []
    pending_delivery = {'waiting_for_own_code_score', 'requires_separate_official_score'}
    for slot, entry in generations.items():
        if entry.get('status') != 'closed':
            continue
        row = by_id[slot]
        if slot not in scores:
            retained, job = original_score(row, entry, 'code')
            if retained is not None:
                scores[slot] = retained
            if job:
                jobs.append(job)
        if row['arm'] != 'PROJECT':
            continue
        old_delivery = deliveries.get(slot)
        if old_delivery is None or old_delivery.get('status') in pending_delivery:
            retained, job = original_score(row, entry, 'delivery')
            if retained is not None:
                deliveries[slot] = retained
            elif job:
                jobs.append(job)
            elif scores.get(slot, {}).get('request'):
                # Import a completed code request through a new local job. Its
                # original completion is reused; only delivery validation runs.
                jobs.append(('code', row, scores[slot]['request'], True))
                reconciliations.append(slot)
    # Each fixed endpoint appears once, including independently recovered jobs.
    unique = {}
    for job in jobs:
        key = job[0], job[1]['slot_id']
        if key in unique and unique[key] != job:
            raise ValueError('Recovery proposes two candidates for one endpoint')
        unique[key] = job
    prior_inventory = scope.load(summary['continuation_inventory'])
    usage = {slot: ref for slot, ref in prior_inventory['usage_record_files'].items() if slot in generations}
    for path in (scope.OLD_API_ROOT/'usage-records').glob('*.json'):
        ref = reference(path)
        value = scope.load(ref)
        if value.get('slot_id') in generations:
            usage[value['slot_id']] = ref
    scope.BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    scope.API_ROOT.mkdir(exist_ok=True)
    proof = write_new(scope.PREDECESSOR_PROOF, {'version': VERSION, 'summary': summary_ref,
        'events': events_ref, 'inactive': inactive, 'active_API_claims': 0,
        'ledger_request_states': request_states, 'ledger_modified': False,
        'recovered_original_results': recovered, 'old_release': reference(scope.OLD_API_ROOT/'coordinator-capacity-released.json')})
    audit_ref = write_new(scope.BATCH_ROOT/'slot-audit.json', {'rows': audit})
    inventory = write_new(scope.INVENTORY_FILE, {'version': VERSION,
        'generation': generations, 'scores': scores, 'deliveries': deliveries,
        'qualifications': summary['qualifications'], 'allowed_generation_slot_ids': eligible,
        'allowed_generation_slot_indices': [by_id[slot]['slot_index'] for slot in eligible],
        'excluded_old_scheduled_slot_ids': sorted(scheduled|set(generations)),
        'old_owned_slot_ids': sorted(generations), 'retry_zero_generation': {},
        'usage_record_files': usage, 'unused_score_jobs': list(unique.values()),
        'pending_grading_jobs': [], 'completed_controls': {}, 'exceptions': summary.get('exceptions', []),
        'API_ledger': str(ledger), 'handoff': proof, 'prior_failure': failure,
        'recovered_original_results': recovered, 'delivery_reconciliation_slots': reconciliations,
        'slot_audit': audit_ref, 'new_API_cash_budget': False, 'automatic_replay': False})
    spec = importlib.util.spec_from_file_location('v085_launcher', scope.ROOT/'tools/launch_api_recovery_v085.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    unit = launcher.prepare()
    plan = write_new(scope.PLAN_FILE, {'version': scope.VERSION, 'original_plan': reference(scope.original.PLAN_FILE),
        'inventory': inventory, 'handoff': proof, 'planned_API_slots': 1000,
        'API_ledger': str(ledger), 'new_preparation_model_calls': 0,
        'API_parent': reference(parent.CREATED), 'unit': unit['specification'], 'nofile_soft_limit': scope.NOFILE})
    files = sorted([*scope.ROOT.glob('src/proworksim/*v085.py'), *scope.ROOT.glob('tools/*v085.py')])
    inherited = {ref['path']: ref for ref in scope.load(prior_auth['source_index'])['files']}
    inherited.update({str(path): reference(path) for path in files})
    sources = write_new(scope.SOURCE_FILE, {'version': scope.VERSION, 'files': [inherited[key] for key in sorted(inherited)]})
    auth = write_new(scope.AUTH_FILE, {'version': scope.VERSION, 'status': 'approved',
        'prior_authorization': reference(scope.prior.AUTH_FILE), 'source_index': sources,
        'parent_authorization': reference(parent.AUTHORIZATION), 'desired_API_concurrency': 48,
        'maximum_API_concurrency': 48, 'maximum_starting_pairs': 8, 'API_cash_cap_CNY': '1500.00',
        'coordinator_memory_bytes': scope.API_MEMORY_BYTES, 'nofile_soft_limit': scope.NOFILE,
        'Qwen_lifecycle_operations': 0, 'per_container_limits_changed': False,
        'basis': '用户授权恢复原实验并提高并发；仅新普通用户服务提高NOFILE并按真实FD余量准入'})
    seal = write_new(scope.BATCH_ROOT/'plan-seal.json', {'authorization': auth, 'plan': plan})
    return {'inventory': inventory, 'seal': seal, 'unused_API_slots': len(eligible),
        'recovered_results': len(recovered), 'statuses': dict(Counter(e['status'] for e in generations.values())),
        'pending_score_jobs': len(unique), 'new_model_calls': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', required=True, action='store_true')
    parser.parse_args()
    print(json.dumps(prepare(), ensure_ascii=False))
