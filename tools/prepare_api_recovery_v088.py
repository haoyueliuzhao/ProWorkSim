"""Seal failed v086 outcomes while its older v085 work continues untouched."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import fcntl
import importlib.util
import json
import resource
import sqlite3
import subprocess
import time

from proworksim import software_benchmark_api_scope_v088 as scope
from proworksim import software_benchmark_api_parent_v085 as parent
from proworksim import software_benchmark_rolling_handoff_v086 as handoff
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_deepseek_runtime_v069 import private_function
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

VERSION = 'v088-original-API-high-FD-recovery-preparation-r1'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, scope.ROOT/'tools'/filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


legacy = module('v088_fixed_score_recovery', 'prepare_api_recovery_v085.py')
terminal_result = private_function(legacy.terminal_result, scope=scope)
original_score = private_function(legacy.original_score, scope=scope)


def failed_inactive():
    result = subprocess.run(['systemctl', '--user', 'show', scope.FAILED_API_UNIT, '--no-pager',
        '--property=ActiveState,SubState,MainPID'], env=user_manager_environment(),
        capture_output=True, text=True, timeout=20)
    props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if result.returncode or props.get('MainPID') != '0' or props.get('ActiveState') not in ('inactive', 'failed'):
        raise ValueError('The exact failed v086 owner remains active')
    if scope.prior.LEASE_FILE.exists():
        raise ValueError('The failed coordinator still has its auxiliary lease')
    release = scope.load(reference(scope.FAILED_API_ROOT/'coordinator-capacity-released.json'))
    if release.get('quiescent') is not True or release.get('claim') != reference(scope.prior.CLAIM_FILE):
        raise ValueError('The failed owner auxiliary release lacks exact ownership')
    return {'unit': scope.FAILED_API_UNIT, 'properties': props, 'unix': time.time(),
            'auxiliary_release': reference(scope.FAILED_API_ROOT/'coordinator-capacity-released.json')}


def validate_failure(summary):
    failure = summary.get('failure', {})
    if failure.get('kind') != 'shared_generation_integrity_failure' or not failure.get('result'):
        raise ValueError('Recovery requires the recorded high-descriptor bridge failure')
    result = scope.load(failure['result'])
    transport = scope.load(result['model_transport'])
    error = transport.get('error', {})
    if (result.get('shared_integrity_fault') != 'trusted_model_bridge_initialization_failed'
            or result.get('model_calls') != 0 or result.get('model_dispatch_started') is not False
            or transport.get('generation_requests') != 0 or error.get('type') != 'ValueError'
            or error.get('message') != 'filedescriptor out of range in select()'):
        raise ValueError('The predecessor failure differs from the audited select boundary')
    return failure


def continuing_history(inventory):
    """One original handoff identity is retained, including its existing watcher."""
    old_owned = set(inventory['old_owned_slot_ids'])
    already_final = (scope.HANDOFF_ROOT/'stopped.json').exists()
    if already_final:
        path = scope.HISTORY_ROOT/'historical-results.json'
    else:
        handoff.validate_launch_pause()
        path = scope.OLD_API_ROOT/'cursor.json'
    raw = path.read_bytes()
    current = json.loads(raw)
    if current.get('failure') is not None:
        raise ValueError('The still-owned predecessor has a separate unresolved shared failure')
    frozen = write_new(scope.BATCH_ROOT/'continuing-owner-at-preparation.json', raw)
    return {key: {slot: value for slot, value in current.get(key, {}).items() if slot in old_owned}
            for key in ('generation', 'scores', 'deliveries')}, sorted(old_owned), frozen, already_final


def recover_partition(rows, state, *, continuing, scheduled, requested, claims_root, roots):
    """Restore exact results, never turn external work or consumed IDs into new work."""
    by_id = {row['slot_id']: row for row in rows}
    generations = dict(state['generation'])
    eligible, recovered, audits = [], [], []
    for row in rows:
        slot, index = row['slot_id'], row['slot_index']
        claims = [str(path) for base in roots for role in ('actor', 'controller', 'volume')
                  if (path := base/'resource-claims'/f'{role}-{index}.json').exists()]
        folders = [base/'episodes'/str(index) for base in roots if (base/'episodes'/str(index)).exists()]
        entry = generations.get(slot)
        result_path = scope.original.BATCH_ROOT/'episodes'/str(index)/'result.json'
        if slot in continuing:
            # The older coordinator is the only writer/reader of these live
            # episodes until its original handoff is terminal.
            if entry is None:
                generations[slot] = {'status': 'external_running', 'entered': bool(claims or slot in requested),
                    'result': None, 'measurement_pending': True, 'automatic_replay': False}
            reason = 'continuing_original_owner_not_replayed'
        elif slot in scheduled or entry and entry.get('status') == 'external_running':
            if result_path.exists():
                restored = terminal_result(row, reference(result_path))
                if entry is None or entry.get('result') != restored['result']:
                    recovered.append(slot)
                generations[slot] = restored
                reason = 'failed_owner_original_terminal_verified'
            elif entry is not None and entry.get('status') in ('closed', 'technical_unknown') and entry.get('result'):
                generations[slot] = terminal_result(row, entry['result'])
                reason = 'failed_owner_retained_terminal_verified'
            elif not claims and not folders and slot not in requested:
                generations[slot] = {'status': 'technical_unknown', 'entered': False, 'result': None,
                    'error': 'Scheduled original identity without resource or request evidence; not automatically replayed',
                    'automatic_replay': False}
                reason = 'scheduled_identity_not_replayed'
            else:
                raise ValueError('A consumed failed-owner identity lacks a trustworthy terminal result')
        elif entry is not None:
            reason = 'retained_original_terminal'
        elif claims or folders or slot in requested:
            if result_path.exists():
                generations[slot] = terminal_result(row, reference(result_path))
                recovered.append(slot)
            else:
                generations[slot] = {'status': 'technical_unknown', 'entered': bool(claims or slot in requested),
                    'result': None, 'error': 'Consumed identity without a retained result; no replay',
                    'automatic_replay': False}
            reason = 'other_consumed_identity_excluded'
        else:
            eligible.append(slot)
            reason = 'unused_original_identity'
        audits.append({'slot_id': slot, 'slot_index': index, 'reason': reason, 'claims': claims})
    if set(eligible) & (set(continuing)|set(scheduled)|set(generations)|set(requested)):
        raise ValueError('New generation overlaps prior ownership or API use')
    return generations, eligible, recovered, audits, by_id


def recover_jobs(rows, generations, scores, deliveries, *, continuing):
    jobs, reconciled = {}, []
    pending_delivery = {'waiting_for_own_code_score', 'requires_separate_official_score'}
    for row in rows:
        slot = row['slot_id']
        entry = generations.get(slot, {})
        if slot in continuing or entry.get('status') != 'closed':
            continue
        old = scores.get(slot)
        if old is None or not old.get('completion') and old.get('request'):
            retained, job = original_score(row, entry, 'code')
            if retained is not None:
                if old is not None and old.get('request') not in (None, retained.get('request')):
                    raise ValueError('Recovered official score changed request identity')
                scores[slot] = retained
            if job:
                jobs['code', slot] = job
        if row['arm'] != 'PROJECT':
            continue
        old = deliveries.get(slot)
        if old is None or old.get('status') in pending_delivery:
            retained, job = original_score(row, entry, 'delivery')
            if retained is not None:
                deliveries[slot] = retained
            elif job:
                jobs['delivery', slot] = job
            elif scores.get(slot, {}).get('request'):
                jobs['code', slot] = ('code', row, scores[slot]['request'], True)
                reconciled.append(slot)
    return list(jobs.values()), reconciled


def prepare():
    scope.original.require_v066_allowed('v066.run')
    parent.require_qualified()
    if scope.AUTH_FILE.exists() or scope.INVENTORY_FILE.exists():
        raise FileExistsError('A recovery identity is immutable and single use')
    if resource.getrlimit(resource.RLIMIT_NOFILE)[1] < scope.NOFILE:
        raise PermissionError('The current hard descriptor limit cannot support the reviewed service')
    inactive = failed_inactive()
    summary_ref = reference(scope.FAILED_API_ROOT/'run-summary.json')
    summary = scope.load(summary_ref)
    failure = validate_failure(summary)
    prior_authority = scope.load(reference(scope.prior.AUTH_FILE))
    for ref in scope.load(prior_authority['source_index'])['files']:
        checked(ref)
    prior_inventory = scope.load(summary['continuation_inventory'])
    scope.BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    scope.API_ROOT.mkdir(exist_ok=True)
    old_history, continuing, old_snapshot, old_final = continuing_history(prior_inventory)
    state = {key: {**summary[key], **old_history[key]} for key in ('generation', 'scores', 'deliveries')}
    rows = [row for row in scope.load(reference(scope.original.PLAN_FILE))['rows']
            if row['model_key'] == 'DEEPSEEK' and row['input_plus_output_tokens'] == 5_000_000]
    if len(rows) != 1000:
        raise ValueError('Keep the original complete two-group 1000 task panel')
    events_ref = reference(scope.FAILED_API_ROOT/'events.jsonl')
    scheduled = {item['slot_id'] for line in checked(events_ref).read_bytes().splitlines()
                 if line and (item := json.loads(line)).get('kind') == 'generation_scheduled'}
    if scheduled & set(continuing):
        raise ValueError('The failed owner scheduled a task already owned by its predecessor')
    claims_root = scope.original.BATCH_ROOT/'resource-claims'
    with (claims_root/'allocation.lock').open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        active = [scope.load(reference(path)) for path in claims_root.glob('active-*.json')]
        if any(item.get('spec', {}).get('slot_id') in scheduled for item in active):
            raise ValueError('A failed-owner task still holds an active resource claim')
    ledger = scope.original.PREDECESSOR_ROOT/'api-budget/ledger.sqlite3'
    with closing(sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        requested = {slot for (slot,) in db.execute('SELECT DISTINCT slot_id FROM requests')}
        reserved = [key for key, slot in db.execute("SELECT request_id,slot_id FROM requests WHERE status='reserved'")
                    if slot in scheduled]
        request_states = dict(db.execute('SELECT status,COUNT(*) FROM requests GROUP BY status'))
    if reserved:
        raise ValueError('The failed-owner API request reservations have not reached terminal accounting')
    generations, eligible, recovered, audits, by_id = recover_partition(rows, state, continuing=set(continuing),
        scheduled=scheduled, requested=requested, claims_root=claims_root,
        roots=(scope.original.BATCH_ROOT, scope.original.PREDECESSOR_ROOT))
    scores, deliveries = state['scores'], state['deliveries']
    jobs, reconciliations = recover_jobs(rows, generations, scores, deliveries,
        continuing=set(continuing) if not old_final else set())
    usage = {slot: ref for slot, ref in prior_inventory['usage_record_files'].items() if slot in generations}
    # Preserve dynamic old-owner reports as captured bytes; do not bind mutable
    # old paths into a newly immutable inventory.
    usage_folder = scope.BATCH_ROOT/'usage-at-recovery'
    usage_folder.mkdir()
    for owner in (scope.FAILED_API_ROOT, scope.OLD_API_ROOT):
        for path in (owner/'usage-records').glob('*.json'):
            raw = path.read_bytes()
            value = json.loads(raw)
            slot = value.get('slot_id')
            if slot not in generations or owner == scope.OLD_API_ROOT and slot not in continuing:
                continue
            target = usage_folder/(owner.parent.name+'-'+path.name)
            usage[slot] = write_new(target, raw)
    proof = write_new(scope.PREDECESSOR_PROOF, {'version': VERSION, 'failed_summary': summary_ref,
        'failed_events': events_ref, 'failed_inactive': inactive, 'continuing_old_snapshot': old_snapshot,
        'original_handoff': reference(scope.HANDOFF_ROOT/'inventory-boundary.json'),
        'failed_owner_active_claims': 0, 'failed_owner_reserved_requests': [],
        'ledger_request_states': request_states, 'ledger_modified': False,
        'continuing_owner_interrupted': False, 'parent_recreated': False})
    audit = write_new(scope.BATCH_ROOT/'slot-audit.json', {'rows': audits})
    inventory = write_new(scope.INVENTORY_FILE, {'version': VERSION, 'generation': generations,
        'scores': scores, 'deliveries': deliveries, 'qualifications': summary['qualifications'],
        'allowed_generation_slot_ids': eligible, 'allowed_generation_slot_indices': [by_id[s]['slot_index'] for s in eligible],
        'excluded_old_scheduled_slot_ids': sorted(scheduled|set(generations)),
        'old_owned_slot_ids': continuing, 'continuing_old_owned_slot_ids': continuing,
        'continuing_history_final_at_preparation': old_final,
        'retry_zero_generation': {}, 'usage_record_files': usage, 'unused_score_jobs': jobs,
        'pending_grading_jobs': [], 'exceptions': summary.get('exceptions', []), 'API_ledger': str(ledger),
        'handoff': proof, 'original_handoff': reference(scope.HANDOFF_ROOT/'inventory-boundary.json'),
        'prior_failure': failure, 'recovered_original_results': recovered,
        'delivery_reconciliation_slots': reconciliations, 'slot_audit': audit,
        'new_API_cash_budget': False, 'automatic_replay': False})
    launcher = module('v088_launcher', 'launch_api_recovery_v088.py')
    unit = launcher.prepare()
    plan = write_new(scope.PLAN_FILE, {'version': scope.VERSION, 'original_plan': reference(scope.original.PLAN_FILE),
        'inventory': inventory, 'handoff': proof, 'planned_API_slots': 1000, 'API_ledger': str(ledger),
        'new_preparation_model_calls': 0, 'API_parent': reference(parent.CREATED), 'unit': unit['specification'],
        'continuing_handoff': reference(scope.HANDOFF_ROOT/'inventory-boundary.json')})
    files = sorted([*scope.ROOT.glob('src/proworksim/*v088.py'), *scope.ROOT.glob('tools/*v088.py')])
    inherited = {ref['path']: ref for ref in scope.load(prior_authority['source_index'])['files']}
    inherited.update({str(path): reference(path) for path in files})
    sources = write_new(scope.SOURCE_FILE, {'version': scope.VERSION, 'files': list(inherited.values())})
    authority = write_new(scope.AUTH_FILE, {'version': scope.VERSION, 'status': 'approved',
        'prior_authorization': reference(scope.prior.AUTH_FILE), 'source_index': sources,
        'parent_authorization': reference(parent.AUTHORIZATION), 'desired_API_concurrency': 48,
        'maximum_API_concurrency': 48, 'maximum_starting_pairs': scope.MAX_STARTING_PAIRS,
        'API_cash_cap_CNY': '1500.00', 'coordinator_memory_bytes': scope.API_MEMORY_BYTES,
        'coordinator_memory_high_bytes': scope.API_MEMORY_HIGH_BYTES, 'nofile_soft_limit': scope.NOFILE,
        'manager_CPU_count': scope.MANAGER_CPUS, 'Qwen_lifecycle_operations': 0,
        'per_container_limits_changed': False, 'grading_requires_live_API_parent': False,
        'basis': '用户要求修复高编号描述符与异常隔离并恢复原实验；原预算、已消费身份与候选不变'})
    seal = write_new(scope.BATCH_ROOT/'plan-seal.json', {'authorization': authority, 'plan': plan})
    return {'inventory': inventory, 'seal': seal, 'unused_API_slots': len(eligible),
        'retained_states': dict(Counter(value['status'] for value in generations.values())),
        'recovered_original_results': len(recovered), 'pending_score_jobs': len(jobs),
        'continuing_old_owner_slots': len(continuing), 'new_model_calls': 0, 'new_cash_budget': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', required=True, action='store_true')
    parser.parse_args()
    print(json.dumps(prepare(), ensure_ascii=False))
