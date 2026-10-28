"""Seal the two original 5M API groups and expanded shared environment lanes."""
from __future__ import annotations

import importlib.util
import json

from proworksim import software_benchmark_dispatch_v066 as primary
from proworksim import software_benchmark_api_expansion_scope_v069 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = scope.ROOT


def prepare():
    if scope.AUTH_FILE.exists():
        raise ValueError('An authorized expansion cannot be rewritten')
    primary.require_v066_allowed('v066.run')
    scope.require_predecessor_admission_paused()
    inventory_ref = reference(scope.INVENTORY_FILE)
    inventory = scope.load(inventory_ref)
    rows = primary.load(primary.reference(primary.PLAN_FILE))['rows']
    targets = [row for row in rows if row['model_key'] == 'DEEPSEEK' and row['input_plus_output_tokens'] == 5_000_000]
    allowed = set(inventory['allowed_generation_slot_ids'])
    if (len(targets) != 1000 or set(inventory['target_slot_ids']) != {row['slot_id'] for row in targets}
            or not allowed <= set(inventory['target_slot_ids'])
            or len(allowed) != len(inventory['allowed_generation_slot_ids'])
            or inventory['retry_zero_generation']):
        raise ValueError('Only the original two complete 5M API groups may be selected')
    for row in targets:
        if row['slot_id'] in allowed and (primary.BATCH_ROOT / 'resource-claims' / f"actor-{row['slot_index']}.json").exists():
            raise ValueError('An eligible API physical identity was consumed after the frozen handoff')
    module_spec = importlib.util.spec_from_file_location('v069_launcher_prepare', ROOT / 'tools/launch_api_expansion_v069.py')
    launcher = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(launcher)
    launcher.prepare()
    unit_ref = reference(scope.API_ROOT / 'coordinator-unit.json')
    plan = {'version': scope.VERSION, 'original_plan': reference(primary.PLAN_FILE),
        'inventory': inventory_ref, 'handoff': reference(scope.HANDOFF_FILE),
        'planned_API_slots': 1000, 'input_plus_output_tokens': 5_000_000,
        'groups': ['DEEPSEEK_REF_B5000K', 'DEEPSEEK_PROJECT_B5000K'],
        'remaining_original_slots': len(allowed),
        'old_high_budget_new_dispatch_allowed': False,
        'old_active_episodes_finish_without_cancellation': True,
        'old_API_unit_drain': 'stop only the exact owned coordinator after all scheduled episode/transport/container work is proved quiescent; preserve and finalize old original scoring evidence',
        'old_API_unit': 'proworksim-v068-api-continuation.service',
        'old_API_unit_spec': reference(scope.OLD_API_ROOT / 'coordinator-unit.json'),
        'API_ledger': str(primary.PREDECESSOR_ROOT / 'api-budget/ledger.sqlite3'),
        'API_total_cash_cap_CNY': '1500.00', 'new_API_cash_cap': False,
        'combined_cpu_cap': 152, 'combined_memory_cap_GiB': 832,
        'existing_resource_identities_only': True,
        'maximum_shared_actor_lanes': 18, 'minimum_grader_capacity_reserved': 2,
        'existing_actor_lanes': list(range(12)), 'additional_actor_lanes': list(range(12, 18)),
        'extra_lane_cpu_mapping': 'lane>=12 uses original actor/controller CPU slice lane%12, retains Docker 4/2 CPU ceilings; no model/grader CPU slices are borrowed',
        'actor_memory_GiB': 16, 'controller_memory_GiB': 16,
        'generation_pair_reserved_CPU': 6, 'generation_pair_reserved_memory_GiB': 32,
        'new_coordinator_CPU': 4, 'new_coordinator_memory_GiB': 16,
        'new_coordinator_CPU_affinity': scope.cpu_affinity(),
        'API_desired_concurrency': 32, 'API_internal_request_limit': 64,
        'allocation_lock': str(primary.BATCH_ROOT / 'resource-claims/allocation.lock'),
        'additional_Qwen_resident_supplement': reference(ROOT / 'artifacts/software-benchmark-v070/local-expansion-r1/authorization.json'),
        'unit': unit_ref, 'automatic_model_replay': False,
        'model_task_seed_tool_budget_changed': False,
        'shared_host_configuration_changed': False}
    plan_ref = write_new(scope.PLAN_FILE, plan)
    source_paths = sorted({*list((ROOT / 'src/proworksim').glob('*v069*.py')),
        *list((ROOT / 'tools').glob('*v069*.py')), primary.SOURCE_INDEX_FILE,
        primary.AUTHORIZATION_FILE, primary.PLAN_FILE, primary.RESUME_FILE,
        ROOT / 'runs/software-benchmark-v068/recovery-r1/runtime-sources.json',
        scope.API_ROOT / 'coordinator-unit.json'})
    sources_ref = write_new(scope.SOURCE_FILE, {'version': scope.VERSION,
        'files': [reference(path) for path in source_paths], 'old_frozen_source_files_changed': False})
    proposal = {'version': scope.VERSION, 'plan': plan_ref, 'source_index': sources_ref,
        'primary_authorization': reference(primary.AUTHORIZATION_FILE), 'unit': unit_ref,
        'user_authorization': ['太慢了，提高并发', 'deepseek调整一下，只做500万tokens的一档', '本地评测也过慢'],
        'scope': 'Continue only original unused 5M API REF/PROJECT slots; expand owned environment lanes within original shared CPU/RAM and CNY1500 budget; let previous active episodes finish and finalize only original scoring identities',
        'unchanged_pair_limits': 'actor4CPU16GiB/controller2CPU16GiB/networknone/dropALL/nohostbinds',
        'maximum_shared_actor_lanes': 18, 'extra_CPU_affinity_shares_existing_actor_pool': True,
        'reserve_at_least_two_graders': True, 'fresh_model_probe_calls': 0,
        'API_direct_no_proxy_or_search': True,
        'host_mount_network_driver_daemon_or_other_user_changes': False,
        'Qwen_live_tasks_or_services_interrupted': False, 'runtime_operations_in_preparation': 0}
    scope.PROPOSAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    proposal_ref = write_new(scope.PROPOSAL_FILE, proposal)
    auth = {'version': scope.VERSION, 'status': 'approved',
        'primary_authorization': reference(primary.AUTHORIZATION_FILE),
        'plan': plan_ref, 'source_index': sources_ref, 'proposal': proposal_ref,
        'basis': proposal['user_authorization'], 'original_model_configuration_and_cash_cap_unchanged': True}
    write_new(scope.PROPOSAL_FILE.parent / 'approved-authorization.json', auth)
    write_new(scope.AUTH_FILE, auth)
    return {'plan': plan_ref, 'proposal': proposal_ref, 'remaining_5M_slots': len(allowed),
            'runtime_operations': 0}


if __name__ == '__main__':
    print(json.dumps(prepare(), ensure_ascii=False))
