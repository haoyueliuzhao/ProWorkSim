"""Seal unused-resource continuation before starting either bounded user unit."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from proworksim import software_benchmark_dispatch_v066 as primary
from proworksim import software_benchmark_recovery_scope_v068 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = scope.ROOT


def prepare():
    if scope.AUTH_FILE.exists():
        raise ValueError('A sealed recovery cannot be rewritten')
    primary.require_v066_allowed('v066.run')
    scope.PROPOSAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    inventory_ref = reference(scope.INVENTORY_FILE)
    inventory = scope.load(inventory_ref)
    if list((primary.BATCH_ROOT / 'resource-claims').glob('active-*.json')):
        raise ValueError('Predecessor resource reservations must be closed before preparation')
    predecessor_paths = [primary.COORDINATOR_RUN_ROOT / 'run-summary.json',
        ROOT / 'runs/software-benchmark-v067/api-continuation-r1/coordinator/run-summary.json']
    for path in predecessor_paths:
        old = scope.load(reference(path))
        if old.get('retained_objects'):
            raise ValueError('Predecessor retains owned resources')
    allowed = set(inventory['allowed_generation_slot_ids'])
    rows = primary.load(primary.reference(primary.PLAN_FILE))['rows']
    if len(rows) != 6000 or len(allowed) != len(inventory['allowed_generation_slot_ids']):
        raise ValueError('Original experiment identities must remain unique')
    prior_allowed = set(primary.load(primary.reference(primary.RESUME_FILE))['allowed_generation_slot_ids'])
    if not allowed <= prior_allowed:
        raise ValueError('Recovery cannot consume identities outside the prior remaining plan')
    for row in rows:
        if row['slot_id'] in allowed and (primary.BATCH_ROOT / 'resource-claims' / f"actor-{row['slot_index']}.json").exists():
            raise ValueError('A recovery actor identity was already consumed')
    module_spec = importlib.util.spec_from_file_location('v068_launcher_prepare', ROOT / 'tools/launch_recovery_v068.py')
    launcher = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(launcher)
    launcher.prepare()
    units = {key: reference(folder / 'coordinator-unit.json')
             for key, folder in [('primary', scope.PRIMARY_ROOT), ('api', scope.API_ROOT)]}
    plan = {'version': scope.VERSION, 'original_plan': reference(primary.PLAN_FILE),
        'inventory': inventory_ref, 'predecessor_summaries': [reference(path) for path in predecessor_paths],
        'original_full_panel_slots': 6000, 'remaining_original_slots': len(allowed),
        'remaining_slots_by_provider': {key: sum(row['slot_id'] in allowed and row['model_key'] == key for row in rows)
                                      for key in ('QWEN', 'DEEPSEEK')},
        'API_ledger': str(primary.PREDECESSOR_ROOT / 'api-budget/ledger.sqlite3'),
        'API_total_cash_cap_CNY': '1500.00', 'new_API_cash_cap': False,
        'combined_cpu_cap': 152, 'combined_memory_cap_GiB': 832,
        'existing_resource_identities_only': True, 'maximum_original_actor_lanes': 12,
        'API_desired_concurrency_default': 32, 'API_desired_concurrency_range': [1, 64],
        'actual_concurrency_resource_bounded': True, 'API_internal_request_limit': 64,
        'new_resident_identity_indices': [index for index in range(6)
            if not (primary.BATCH_ROOT / 'resource-claims' / f'model-{index}.json').exists()],
        'maximum_simultaneous_recovery_residents': 2, 'unused_original_controls_only': True,
        'allocation_lock': str(primary.BATCH_ROOT / 'resource-claims/allocation.lock'),
        'units': units, 'automatic_model_replay': False, 'shared_host_configuration_changed': False,
        'model_task_seed_tool_budget_changed': False}
    plan_ref = write_new(scope.PLAN_FILE, plan)
    source_paths = sorted({*list((ROOT / 'src/proworksim').glob('*v068*.py')),
        *list((ROOT / 'tools').glob('*v068*.py')), primary.SOURCE_INDEX_FILE,
        primary.AUTHORIZATION_FILE, primary.PLAN_FILE, primary.RESUME_FILE,
        *(Path(ref['path']) for ref in units.values())})
    sources_ref = write_new(scope.SOURCE_FILE, {'version': scope.VERSION,
        'files': [reference(path) for path in source_paths], 'old_frozen_source_files_changed': False})
    proposal = {'version': scope.VERSION, 'plan': plan_ref, 'source_index': sources_ref,
        'primary_authorization': reference(primary.AUTHORIZATION_FILE), 'units': units,
        'user_authorization': '上一个任务未完成修复，并行处理恢复；api的并发应该可以提高到30以上，分析制约瓶颈，尽量调整，同时尽快修复本地模型的实验',
        'scope': 'Restore original unconsumed Qwen/API episodes and grading through the existing owned resource allocator; '
                 'new ordinary-user API coordinator shares the original 152CPU/832GiB cap, no shared-host changes',
        'TLS_change': 'Measure original CA identity and finish relay before container cleanup; physical cleanup and scoring evidence classified independently',
        'remaining_resources_only': True, 'automatic_model_replay': False,
        'API_direct_no_proxy': True, 'API_cash_cap_CNY': '1500.00',
        'host_mount_network_driver_daemon_or_other_user_changes': False,
        'runtime_operations_in_preparation': 0}
    proposal_ref = write_new(scope.PROPOSAL_FILE, proposal)
    auth = {'version': scope.VERSION, 'status': 'approved',
        'primary_authorization': reference(primary.AUTHORIZATION_FILE),
        'plan': plan_ref, 'source_index': sources_ref, 'proposal': proposal_ref,
        'basis': proposal['user_authorization'], 'original_model_configuration_and_cash_cap_unchanged': True}
    write_new(scope.PROPOSAL_FILE.parent / 'approved-authorization.json', auth)
    write_new(scope.AUTH_FILE, auth)
    return {'plan': plan_ref, 'proposal': proposal_ref, 'remaining': plan['remaining_slots_by_provider'],
            'runtime_operations': 0}


if __name__ == '__main__':
    print(json.dumps(prepare(), ensure_ascii=False))
