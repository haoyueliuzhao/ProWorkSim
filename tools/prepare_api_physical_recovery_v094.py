"""Derive a complete 44-launch plan, then seal only after execution-path CPU checks."""
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

from proworksim import software_benchmark_api_scope_v094 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

VERSION = 'v094-complete-plan-and-CPU-gated-preparation-r1'


def owner_exited_and_ids_available():
    response = subprocess.run(['systemctl', '--user', 'show', scope.OLD_API_UNIT, '--no-pager',
        '--property=MainPID,ActiveState'], env=user_manager_environment(), capture_output=True,
        text=True, timeout=20)
    state = dict(line.split('=', 1) for line in response.stdout.splitlines() if '=' in line)
    if (response.returncode or state.get('MainPID') != '0' or state.get('ActiveState') not in ('inactive', 'failed')
            or scope.previous_owner.LEASE_FILE.exists()):
        raise PermissionError('Previous manager must be fully exited and its lease released')
    rows = scope.canonical_rows()
    root = scope.original.BATCH_ROOT
    for row in rows:
        index = scope.physical_fields(row)['slot_index']
        if (root/'episodes'/str(index)).exists() or any((root/'resource-claims'/f'{prefix}-{index}.json').exists()
                for prefix in ('actor', 'controller', 'volume', 'score', 'delivery-score')):
            raise PermissionError('New physical identity is already consumed')
    ledger = scope.original.PREDECESSOR_ROOT/'api-budget/ledger.sqlite3'
    with closing(sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True)) as database:
        count = database.execute('SELECT COUNT(*) FROM requests WHERE slot_id IN ('+
            ','.join('?' for _ in rows)+')', [row['slot_id'] for row in rows]).fetchone()[0]
        inflight = database.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0]
    if count or inflight:
        raise PermissionError('An authorized model attempt has already dispatched or accounting is in flight')
    return {'old_unit': state, 'API_requests_for_44': count, 'global_API_inflight': inflight,
        'new_physical_indices': list(range(6046, 6090)), 'new_physical_identities_unconsumed': True}


def prepare_plan():
    audit_ref = scope.require_physical_audit()
    old_authority = scope.canonical.require_allowed(grading_only=True)
    ready = owner_exited_and_ids_available()
    if scope.PLAN_FILE.exists() or scope.INVENTORY_FILE.exists():
        raise ValueError('Physical plan preparation is single use')
    ancestor = scope.load(reference(scope.original.PLAN_FILE))
    canonical_plan = scope.load(old_authority['plan'])
    canonical_inventory = scope.load(reference(scope.CANONICAL_INVENTORY_FILE))
    audit = scope.load(audit_ref)
    prior_rows = {row['slot_id']: row for row in scope.load(audit['prior_physical_inventory'])['rows']}
    rows, configs, resources = [], [], {}
    for old in canonical_inventory['rows']:
        fields = scope.physical_fields(old)
        index = fields['slot_index']
        config = {**scope.load(old['configuration']), 'slot_index': index}
        if old['slot_index'] in (6000, 6001):
            path = scope.BATCH_ROOT/'configs'/f'{index}.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            config_ref = write_new(path, config)
            row = {**old, **fields, 'configuration': config_ref}
        else:
            row = copy.deepcopy(prior_rows[old['slot_id']])
            config_ref = row['configuration']
        scope.validate_physical_mapping(row, old, config, scope.load(old['configuration']))
        rows.append(row)
        configs.append({'slot_id': row['slot_id'], 'slot_index': index, 'configuration': config_ref,
            'canonical_configuration': old['configuration']})
        for prefix in ('actor', 'controller', 'volume', 'score', 'delivery-score'):
            prior = canonical_plan['resources'].get(f'{prefix}-{old["slot_index"]}')
            if prior is not None:
                resources[f'{prefix}-{index}'] = {**prior,
                    'prior_physical_slot_index': row['prior_physical_slot_index'],
                    'physical_launch_attempt': row['physical_launch_attempt']}
    config_index = write_new(scope.BATCH_ROOT/'active-configurations.json', {'version': VERSION, 'rows': configs})
    inventory = write_new(scope.INVENTORY_FILE, {**canonical_inventory, 'version': VERSION, 'rows': rows,
        'canonical_model_attempt_inventory': reference(scope.CANONICAL_INVENTORY_FILE),
        'physical_zero_model_audit': audit_ref, 'physical_launch_revision': 3,
        'prior_physical_indices_consumed': list(range(6000, 6046)),
        'new_physical_indices': list(range(6046, 6090)), 'additional_model_attempts': 0,
        'previous_created_containers': 4, 'previous_created_named_volumes': 2,
        'canonical_model_attempt_lineage': canonical_inventory['lineage'],
        'lineage': [{'slot_id': row['slot_id'], 'new_physical_index': row['slot_index'],
                    'prior_physical_index': row['prior_physical_slot_index'], 'configuration': row['configuration']}
                   for row in rows]})
    from proworksim.software_benchmark_recovery_runtime_v094 import bindings
    constraints = copy.deepcopy(bindings.dispatch_view(lambda *args, **kwargs: None).CONSTRAINTS)
    tasks = {row['instance_id'] for row in rows}
    plan_value = {**copy.deepcopy(ancestor), 'version': scope.VERSION, 'rows': rows, 'resources': resources,
        'environments': {task: copy.deepcopy(canonical_plan['environments'][task]) for task in tasks},
        'resource_role_counts': dict(Counter(value['role'] for value in resources.values())),
        'constraints': constraints, 'continuation_inventory': inventory, 'inventory': inventory,
        'remaining_generation_slots': 44, 'remaining_original_token_upper_bound': 220_000_000,
        'historical_results_preserved': True, 'training': False, 'model_calls_during_preparation': 0,
        'original_plan': reference(scope.original.PLAN_FILE), 'canonical_recovery_plan': old_authority['plan'],
        'active_configurations': config_index, 'inherited_matrix_and_configurations_are_source_lineage': True,
        'administrative_root': str(scope.BATCH_ROOT), 'physical_zero_model_audit': audit_ref,
        'physical_launch_revision': 3, 'logical_model_attempts': 44, 'additional_model_attempts': 0,
        'previous_created_containers': 4, 'previous_created_named_volumes': 2,
        'cumulative_container_upper_bound': 159, 'cumulative_named_volume_upper_bound': 46,
        'startup_health_gate': {'maximum_unconfirmed_launches': 2, 'required_interfaces': ['REF', 'PROJECT'],
            'success_criterion': 'at_least_one_settled_paid_API_request_per_preselected_interface',
            'task_scores_used': False, 'after_gate_generation_limit': 48}}
    plan = write_new(scope.PLAN_FILE, plan_value)
    scope.validate_complete_plan(plan_value, scope.load(inventory))
    return write_new(scope.BATCH_ROOT/'plan-prepared.json', {'version': VERSION, 'plan': plan,
        'inventory': inventory, 'read_only_admission': ready, 'source_sealed': False,
        'model_calls': 0, 'Docker_operations': 0, 'service_operations': 0})


def seal(cpu_control):
    ready = owner_exited_and_ids_available()
    control_ref = reference(cpu_control)
    control = scope.load(control_ref)
    if (control.get('passed') is not True or control.get('full_required_CPU_control_complete') is not True
            or control.get('broker_controls_complete') is not True
            or control.get('interfaces_checked') != ['REF', 'PROJECT']):
        raise PermissionError('The actual episode and broker CPU controls must pass before source sealing')
    plan = scope.load(reference(scope.PLAN_FILE))
    scope.validate_complete_plan(plan, scope.load(reference(scope.INVENTORY_FILE)))
    if scope.AUTH_FILE.exists() or scope.SOURCE_FILE.exists():
        raise ValueError('Source sealing is single use')
    spec = importlib.util.spec_from_file_location('v094_launcher', scope.ROOT/'tools/launch_api_physical_recovery_v094.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    unit = launcher.prepare()
    scope.COORDINATOR_ROOT.mkdir(exist_ok=True)
    previous = scope.load(reference(scope.previous_owner.AUTH_FILE))
    sources = {ref['path']: ref for ref in scope.load(previous['source_index'])['files']}
    paths = [*scope.ROOT.glob('src/proworksim/*v094*.py')]
    paths += [scope.ROOT/'tools'/name for name in ('prepare_api_physical_recovery_v094.py',
        'run_api_physical_recovery_v094.py', 'launch_api_physical_recovery_v094.py',
        'check_model_bridge_v094.py')]
    for path in paths:
        sources[str(path)] = reference(path)
    index = write_new(scope.SOURCE_FILE, {'version': scope.VERSION, 'files': [sources[key] for key in sorted(sources)]})
    auth = write_new(scope.AUTH_FILE, {'version': scope.VERSION, 'status': 'approved',
        'prior_authorization': reference(scope.previous_owner.AUTH_FILE), 'source_index': index,
        'plan': reference(scope.PLAN_FILE), 'inventory': reference(scope.INVENTORY_FILE),
        'physical_zero_model_audit': scope.require_physical_audit(), 'logical_model_attempts': 44,
        'additional_model_attempts': 0, 'API_cash_cap_CNY': '1700.00', 'old_records_overwritten': False,
        'Qwen_lifecycle_operations': 0, 'unit': unit['specification'], 'CPU_execution_control': control_ref,
        'explicit_44_model_attempt_authorization': scope.require_explicit_recovery_authorization()})
    return write_new(scope.BATCH_ROOT/'preparation.json', {'version': VERSION, 'unix': time.time(),
        'authorization': auth, 'read_only_admission': ready, 'CPU_execution_control': control_ref,
        'new_model_calls': 0, 'additional_model_attempts': 0, 'service_operations': 0})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--plan-only', action='store_true')
    group.add_argument('--seal', action='store_true')
    parser.add_argument('--cpu-control', type=Path)
    args = parser.parse_args()
    if args.seal and args.cpu_control is None:
        parser.error('--seal requires --cpu-control')
    print(json.dumps(prepare_plan() if args.plan_only else seal(args.cpu_control), ensure_ascii=False))
