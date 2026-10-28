"""Seal and launch an API-only worker beside the unchanged live Qwen queue."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess

from proworksim import software_benchmark_api_scope_v067 as scope
from proworksim import software_benchmark_dispatch_v066 as primary
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment
from proworksim.storage import atomic_write, json_bytes

ROOT, RUN_ROOT = scope.ROOT, scope.RUN_ROOT
OUT = ROOT / 'artifacts/software-benchmark-v067/runtime-authorization-r1'


def prepare():
    if scope.AUTH_FILE.exists() or (RUN_ROOT / 'coordinator/execution-started.json').exists():
        raise ValueError('Do not overwrite or replay an already sealed API-only worker')
    primary.require_v066_allowed('v066.run')
    paused = scope.primary_cursor()
    inventory = primary.load(primary.reference(primary.RESUME_FILE))
    rows = primary.load(primary.reference(primary.PLAN_FILE))['rows']
    allowed = [row for row in rows if row['model_key'] == 'DEEPSEEK'
               and row['slot_id'] in set(inventory['allowed_generation_slot_ids'])]
    if len(allowed) != 2968:
        raise ValueError('The API supplement must bind the exact original remaining inventory')
    for row in allowed:
        if (primary.BATCH_ROOT / 'resource-claims' / f"actor-{row['slot_index']}.json").exists():
            raise ValueError('An API creation identity was already consumed')
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    pause_ref = write_new(OUT / 'primary-api-pause.json', {
        'provider_failure': paused['provider_failures']['DEEPSEEK'],
        'active_primary_generation': paused['active_generation'],
        'primary_cursor_sha256_at_inspection': reference(primary.COORDINATOR_RUN_ROOT / 'cursor.json')['sha256'],
        'primary_API_active': False, 'primary_source_files_changed': False})
    plan = {'version': scope.VERSION, 'primary_plan': reference(primary.PLAN_FILE),
        'primary_authorization': reference(primary.AUTHORIZATION_FILE),
        'inventory': reference(primary.RESUME_FILE), 'primary_pause': pause_ref,
        'allowed_rows': allowed, 'planned_API_groups': 6, 'planned_API_slots': 3000,
        'remaining_API_slots': len(allowed), 'maximum_active_API_generations': 4,
        'API_ledger': str(primary.PREDECESSOR_ROOT / 'api-budget/ledger.sqlite3'),
        'API_total_cash_cap_CNY': '1500.00', 'new_API_qualification_calls': 0,
        'new_model_residents': 0, 'new_environment_controls': 0,
        'primary_actor_controller_grader_claims_and_limits_reused': True,
        'auxiliary_coordinator_reserved_cpu': 4, 'auxiliary_coordinator_reserved_memory_bytes': 16 * 1024**3,
        'combined_cpu_cap': 152, 'combined_memory_cap_GiB': 832,
        'allocation_lock': str(primary.BATCH_ROOT / 'resource-claims/allocation.lock'),
        'separate_reporting_root': str(RUN_ROOT / 'coordinator'),
        'local_model_lifecycle_operations': 0, 'automatic_model_replay': False}
    plan_ref = write_new(scope.PLAN_FILE, plan)
    spec = {'version': scope.VERSION, 'unit': scope.UNIT, 'user_id': os.getuid(),
        'ownership_token': secrets.token_hex(16), 'plan': plan_ref, 'source': reference(__file__),
        'cpu_affinity': scope.cpu_affinity(), 'cpu_quota_percent': 400,
        'memory_max_bytes': 16 * 1024**3, 'memory_swap_max_bytes': 0,
        'tasks_max': 512, 'restart': 'no', 'timeout_stop_seconds': 420, 'kill_mode': 'mixed'}
    unit_ref = write_new(scope.SPEC_FILE, spec)
    source_paths = sorted({*list((ROOT / 'src/proworksim').glob('*v067*.py')),
        *list((ROOT / 'tools').glob('*v067*.py')), primary.SOURCE_INDEX_FILE,
        primary.AUTHORIZATION_FILE, primary.PLAN_FILE, primary.RESUME_FILE})
    sources_ref = write_new(scope.SOURCE_FILE, {'version': scope.VERSION,
        'files': [reference(path) for path in source_paths], 'no_v066_source_overridden': True})
    proposal = {'version': scope.VERSION, 'plan': plan_ref, 'source_index': sources_ref,
        'unit': unit_ref, 'primary_authorization': reference(primary.AUTHORIZATION_FILE),
        'user_authorization': '处理并恢复实验，此外健壮度太差，因为这么一个小问题就导致12组实验全部停止',
        'runtime_change': 'API-only continuation fixes canonical neutral usage validation; Qwen stays running',
        'resource_boundary': 'One ordinary-user 4CPU/16GiB coordinator reserved inside the existing shared pool; '
            'only the already authorized unconsumed API task container/volume/score identities; no extra GPU or environment controls',
        'model_task_seed_tool_budget_changed': False, 'new_API_cash_cap': False,
        'shared_host_configuration_changed': False, 'other_units_stopped_or_restarted': False,
        'runtime_operations_in_preparation': 0}
    proposal_ref = write_new(scope.PROPOSAL_FILE, proposal)
    auth = {'version': scope.VERSION, 'status': 'approved',
        'primary_authorization': reference(primary.AUTHORIZATION_FILE),
        'plan': plan_ref, 'source_index': sources_ref, 'proposal': proposal_ref,
        'basis': proposal['user_authorization'], 'automatic_replay': False,
        'only_remaining_original_API_slots': True, 'no_Qwen_lifecycle_authority': True}
    write_new(OUT / 'approved-authorization.json', auth)
    atomic_write(scope.AUTH_FILE, json_bytes(auth))
    return {'plan': plan_ref, 'proposal': proposal_ref, 'remaining_API_slots': len(allowed),
            'new_cash_budget': False, 'runtime_operations': 0}


def launch():
    scope.require_allowed()
    spec = scope.load(reference(scope.SPEC_FILE))
    proposal = scope.load(reference(scope.PROPOSAL_FILE))
    fixed = {'version': scope.VERSION, 'unit': scope.UNIT, 'user_id': os.getuid(),
        'plan': reference(scope.PLAN_FILE), 'source': reference(__file__),
        'cpu_affinity': scope.cpu_affinity(), 'cpu_quota_percent': 400,
        'memory_max_bytes': 16 * 1024**3, 'memory_swap_max_bytes': 0, 'tasks_max': 512,
        'restart': 'no', 'timeout_stop_seconds': 420, 'kill_mode': 'mixed'}
    token = spec.get('ownership_token')
    if (proposal.get('unit') != reference(scope.SPEC_FILE)
            or any(spec.get(key) != value for key, value in fixed.items())
            or set(spec) != set(fixed) | {'ownership_token'}
            or not isinstance(token, str) or len(token) != 32
            or any(char not in '0123456789abcdef' for char in token)):
        raise ValueError('The owned supplementary unit specification changed')
    claim = scope.reserve_coordinator()
    command = ['systemd-run', '--user', '--collect', '--no-block', '--unit=' + scope.UNIT,
        '--description=ProWorkSim v067 API coordinator ' + spec['ownership_token'],
        '--setenv=PYTHONHOME=', '--setenv=PYTHONPATH=', '--setenv=LD_LIBRARY_PATH=', '--setenv=LD_PRELOAD=',
        '--property=Restart=no', '--property=KillMode=mixed', '--property=CPUQuota=400%',
        '--property=CPUAffinity=' + ' '.join(map(str, spec['cpu_affinity'])),
        '--property=MemoryMax=16G', '--property=MemorySwapMax=0', '--property=TasksMax=512',
        '--property=OOMPolicy=stop', '--property=TimeoutStopSec=420',
        '--property=WorkingDirectory=' + str(ROOT),
        '--property=StandardOutput=append:' + str(RUN_ROOT / 'coordinator.stdout.log'),
        '--property=StandardError=append:' + str(RUN_ROOT / 'coordinator.stderr.log'),
        str(ROOT / '.venv/bin/python'), '-B', str(ROOT / 'tools/run_offline_scorer_v058.py'),
        str(ROOT / 'tools/run_api_continuation_v067.py'), '--execute']
    write_new(RUN_ROOT / 'launch-intent.json', {'unit': reference(scope.SPEC_FILE), 'claim': claim, 'command': command})
    try:
        result = subprocess.run(command, env=user_manager_environment(), capture_output=True, text=True, timeout=30)
    except BaseException:
        # Do not assume a timed-out start created no service. Retain its bounded
        # reservation until the owned-unit result can be established.
        raise
    saved = {'version': scope.VERSION, 'returncode': result.returncode, 'stdout': result.stdout,
             'stderr': result.stderr, 'unit': scope.UNIT, 'claim': claim}
    write_new(RUN_ROOT / 'launch-result.json', saved)
    if result.returncode != 0:
        raise RuntimeError('API supplementary unit did not start; inspect owned unit before releasing its reservation')
    return saved


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else launch(), ensure_ascii=False))
