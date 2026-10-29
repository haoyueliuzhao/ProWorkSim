"""Prepare exactly the original budget-cutoff panel as fresh recovery attempts."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import time

from proworksim import software_benchmark_api_scope_v089 as scope
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

VERSION = 'v089-fresh-budget-recovery-inventory-r1'


def selected_budget_cutoffs(summary, inventory, original_rows, events):
    if (summary.get('failure') is not None or summary.get('provider_failures', {}).get('DEEPSEEK', {}).get('reason')
            != 'api_monetary_budget_exhausted'):
        raise ValueError('Require the original final monetary-stop record')
    stops = [e for e in events if e.get('kind') == 'provider_stopped'
             and e.get('provider') == 'DEEPSEEK' and e.get('reason') == 'cash_exhausted']
    if len(stops) != 1:
        raise ValueError('Require the unique recorded cash exhaustion boundary')
    stopped = stops[0]['unix']
    ended = {e['slot_id']: e['unix'] for e in events if e.get('kind') == 'generation_finished'}
    by_id = {r['slot_id']: r for r in original_rows}
    selected = []
    for slot in inventory['allowed_generation_slot_ids']:
        entry = summary['generation'].get(slot, {})
        if entry.get('status') != 'technical_unknown':
            continue
        result = scope.load(entry['result'])
        error = result.get('error', {})
        expected = (error.get('type') == 'InterruptedError'
                    and error.get('message') == 'Capability coordinator requested owned-episode cancellation')
        expected |= error.get('type') == 'PreDispatchBudgetStopped'
        row = by_id[slot]
        quiet = scope.load(result['quiescence'])
        if (not expected or ended.get(slot, 0) < stopped
                or result.get('slot_id') != slot or result.get('configuration') != row['configuration']
                or row['model_key'] != 'DEEPSEEK' or row['input_plus_output_tokens'] != 5_000_000
                or quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []
                or quiet.get('create_result_unknown') is not False or result.get('retained_objects')):
            raise ValueError('A selected result lacks exact administrative-cutoff and cleanup evidence')
        selected.append((row, entry['result'], result['quiescence'], error))
    selected.sort(key=lambda item: item[0]['slot_index'])
    if len(selected) != scope.RECOVERY_COUNT:
        raise ValueError('The full predefined administrative panel must remain exactly 44')
    return selected, stopped


def recovery_row(source, physical_index, config_ref):
    return {**source, 'slot_index': physical_index,
        'slot_id': source['slot_id']+scope.RECOVERY_SUFFIX, 'configuration': config_ref,
        'original_slot_id': source['slot_id'], 'original_slot_index': source['slot_index'],
        'recovery_attempt': 1}


def build_resources(rows, original_plan):
    resources = {}
    for row in rows:
        for prefix in ('actor', 'controller', 'volume', 'score', 'delivery-score'):
            old = original_plan['resources'].get(f"{prefix}-{row['original_slot_index']}")
            if old is not None:
                resources[f"{prefix}-{row['slot_index']}"] = {**old, 'slot_id': row['slot_id'],
                    'original_slot_id': row['original_slot_id'], 'recovery_attempt': 1}
    expected = {'actor': 44, 'controller': 44, 'volume': 44, 'score': 44, 'delivery_score': 23}
    if dict(Counter(x['role'] for x in resources.values())) != expected:
        raise ValueError('The exact recovery container/volume scope changed')
    return resources


def prepare():
    explicit_approval = scope.require_explicit_recovery_authorization()
    original_auth = scope.original.require_v066_allowed('v066.run')
    if scope.INVENTORY_FILE.exists() or scope.AUTH_FILE.exists():
        raise ValueError('The recovery preparation identity is single use')
    response = subprocess.run(['systemctl', '--user', 'show', scope.OLD_API_UNIT, '--no-pager',
        '--property=ActiveState,SubState,MainPID'], env=user_manager_environment(), capture_output=True,
        text=True, timeout=20)
    props = dict(line.split('=', 1) for line in response.stdout.splitlines() if '=' in line)
    if response.returncode or props.get('MainPID') != '0' or props.get('ActiveState') not in ('inactive', 'failed'):
        raise ValueError('The original API owner is still alive')
    if scope.predecessor.LEASE_FILE.exists():
        raise ValueError('The original API owner lease remains active')
    summary_ref = reference(scope.OLD_API_ROOT/'run-summary.json')
    summary = scope.load(summary_ref)
    first_counts = dict(Counter(value['status'] for value in summary['generation'].values()))
    if first_counts != {'closed': 722, 'technical_unknown': 249, 'not_started': 29}:
        raise ValueError('Original two-group terminal accounting changed')
    initial_ref = summary['continuation_inventory']
    initial = scope.load(initial_ref)
    events_ref = reference(scope.OLD_API_ROOT/'events.jsonl')
    events = [json.loads(x) for x in checked(events_ref).read_bytes().splitlines() if x]
    original_plan = scope.load(original_auth['plan'])
    selected, cutoff = selected_budget_cutoffs(summary, initial, original_plan['rows'], events)
    active_dir = scope.original.BATCH_ROOT/'resource-claims'
    for path in active_dir.glob('active-*.json'):
        if ':DEEPSEEK_' in scope.load(reference(path)).get('spec', {}).get('slot_id', ''):
            raise ValueError('An original API object remains active')
    ledger = scope.original.PREDECESSOR_ROOT/'api-budget/ledger.sqlite3'
    with closing(sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        if db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0]:
            raise ValueError('Cash amendment/recovery requires settled request accounting')
        existing_slots = {x[0] for x in db.execute('SELECT DISTINCT slot_id FROM requests')}
    scope.BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    configs = scope.BATCH_ROOT/'configs'
    configs.mkdir()
    rows, lineage = [], []
    for offset, (source, result, quiet, error) in enumerate(selected):
        index = scope.FIRST_PHYSICAL_INDEX+offset
        if any((active_dir/f'{role}-{index}.json').exists() for role in ('actor', 'controller', 'volume', 'score', 'delivery-score')):
            raise ValueError('Fresh recovery physical resource identity is already consumed')
        if (scope.original.BATCH_ROOT/'episodes'/str(index)).exists():
            raise ValueError('Fresh recovery work directory already exists')
        original_config = scope.load(source['configuration'])
        config = {**original_config, 'slot_id': source['slot_id']+scope.RECOVERY_SUFFIX, 'slot_index': index}
        config_ref = write_new(configs/f'{index}.json', config)
        row = recovery_row(source, index, config_ref)
        scope.validate_mapping(row, source, config, original_config)
        if row['slot_id'] in existing_slots:
            raise ValueError('Fresh recovery API identity already has requests')
        rows.append(row)
        lineage.append({'recovery_slot_id': row['slot_id'], 'original_slot_id': source['slot_id'],
            'original_configuration': source['configuration'], 'recovery_configuration': config_ref,
            'original_result': result, 'original_quiescence': quiet, 'original_error': error,
            'exact_continuation_checkpoint': False, 'original_records_overwritten': False,
            'additional_attempt_token_limit': 5_000_000})
    stage_two = [dict(slot_id=slot, status=value['status'], result=value.get('result'),
                      stage='after_all_44_budget_recoveries', automatic_generation=False)
                 for slot, value in summary['generation'].items()
                 if value['status'] == 'technical_unknown' and slot not in {r['original_slot_id'] for r in rows}]
    if len(stage_two) != 205:
        raise ValueError('Historical technical-unknown follow-up population changed')
    scoring_unknown = []
    for slot, entry in summary['scores'].items():
        request = entry.get('request')
        if not request:
            scoring_unknown.append({'slot_id': slot, 'score_record': entry,
                'reason': 'missing_fixed_request', 'automatic_scoring_replay': False})
            continue
        request_value = scope.load(request)
        receipt_path = Path(request_value['directory'])/'receipt.json'
        receipt = scope.load(reference(receipt_path)) if receipt_path.exists() else {}
        if receipt.get('status') != 'official_report' or type(receipt.get('resolved')) is not bool:
            scoring_unknown.append({'slot_id': slot, 'request': request,
                'receipt': reference(receipt_path) if receipt_path.exists() else None,
                'reason': receipt.get('status', 'missing_official_receipt'),
                'automatic_scoring_replay': False})
    inventory = write_new(scope.INVENTORY_FILE, {'version': VERSION, 'rows': rows,
        'explicit_recovery_authorization': explicit_approval,
        'original_summary': summary_ref, 'original_inventory': initial_ref,
        'original_events': events_ref, 'budget_cutoff_unix': cutoff, 'API_ledger': str(ledger),
        'generation': {}, 'scores': {}, 'deliveries': {},
        'qualifications': summary['qualifications'], 'usage_record_files': {},
        'allowed_generation_slot_ids': [row['slot_id'] for row in rows],
        'continuation_slot_ids': [row['slot_id'] for row in rows], 'retry_mapping': {r['slot_id']: r['original_slot_id'] for r in rows},
        'lineage': lineage, 'first_attempt_counts_unchanged': first_counts,
        'later_technical_unknown_queue': stage_two, 'stage_two_started': False,
        'later_scoring_unknown_queue': scoring_unknown,
        'exact_checkpoint_resume_supported': False, 'new_fresh_recovery_attempts': 44,
        'resume_assessment': {'host_always_creates_fresh_actor_controller': reference(
            scope.ROOT/'src/proworksim/software_benchmark_episode_v066.py'),
            'managed_controller_declares_no_resume': reference(scope.ROOT/'tools/run_project_controller_v066.py'),
            'REF_persistence_is_not_a_validated_cross_process_checkpoint': True,
            'inflight_API_response_and_environment_state_not_reconstructed': True},
        'additional_input_plus_output_upper_bound': 220_000_000,
        'historical_costs_counted_once': True, 'old_unknown_reservations_released': False,
        'predecessor_unit': props, 'prepared_unix': time.time()})
    tasks = {r['instance_id'] for r in rows}
    plan = write_new(scope.PLAN_FILE, {'version': scope.VERSION, 'rows': rows,
        'explicit_recovery_authorization': explicit_approval,
        'resources': build_resources(rows, original_plan),
        'environments': {task: copy.deepcopy(original_plan['environments'][task]) for task in tasks},
        'inventory': inventory, 'original_plan': original_auth['plan'],
        'root': str(scope.original.BATCH_ROOT), 'administrative_root': str(scope.BATCH_ROOT),
        'original_panel_denominator': 1000, 'recovery_panel_denominator': 44,
        'fresh_model_token_upper_bound': 220_000_000, 'original_seed_and_condition_preserved': True,
        'original_model_visible_bundle_changed': False, 'old_first_attempts_reclassified': False})
    scope.COORDINATOR_ROOT.mkdir()
    spec = importlib.util.spec_from_file_location('v089_launch_prepare', scope.ROOT/'tools/launch_api_budget_recovery_v089.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    unit = launcher.prepare()
    prior_auth = scope.load(reference(scope.predecessor.AUTH_FILE))
    sources = {x['path']: x for x in scope.load(prior_auth['source_index'])['files']}
    for path in (*scope.ROOT.glob('src/proworksim/*v089*.py'), *scope.ROOT.glob('tools/*v089*.py')):
        sources[str(path)] = reference(path)
    index = write_new(scope.SOURCE_FILE, {'version': scope.VERSION, 'files': [sources[k] for k in sorted(sources)]})
    auth = write_new(scope.AUTH_FILE, {'version': scope.VERSION, 'status': 'approved',
        'explicit_recovery_authorization': explicit_approval,
        'prior_authorization': reference(scope.predecessor.AUTH_FILE), 'source_index': index, 'plan': plan,
        'fresh_recovery_attempts': 44, 'generation_token_upper_bound': 220_000_000,
        'API_cash_cap_CNY': '1700.00', 'original_first_attempts_overwritten': False,
        'Qwen_lifecycle_operations': 0, 'model_visible_configuration_changes': ['fresh operational slot identity only'],
        'basis': '用户明确回复启动44个独立恢复回合；44预算行政中断为完整面板，原结果保留，其他205未知随后处理',
        'unit': unit['specification']})
    seal = write_new(scope.BATCH_ROOT/'plan-seal.json', {'authorization': auth, 'plan': plan})
    return {'inventory': inventory, 'plan': plan, 'seal': seal, 'fresh_recovery_attempts': 44,
        'later_technical_unknown_tasks': 205, 'new_model_calls': 0, 'original_records_changed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', required=True, action='store_true')
    parser.parse_args()
    print(json.dumps(prepare(), ensure_ascii=False))
