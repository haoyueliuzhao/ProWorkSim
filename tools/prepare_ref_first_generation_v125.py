"""Prepare exactly the original two REF tasks that have never invoked the model."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import json
import sqlite3
from proworksim import software_benchmark_scope_v125 as scope
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import declaration


def prepare():
    old = scope.load(reference(scope.ORIGINAL_PLAN_FILE))
    rows = [copy.deepcopy(r) for r in old['rows'] if r['slot_index'] in {7239, 7267}]
    if len(rows) != 2 or any(r['arm'] != 'REF' for r in rows):
        raise ValueError('The original Requests REF inventory changed')
    tasks = {r['instance_id'] for r in rows}
    resources, inventory = {}, []
    with sqlite3.connect(scope.LEDGER_FILE.as_uri()+'?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        for row in rows:
            n = db.execute('SELECT count(*) FROM requests WHERE slot_id=?', (row['slot_id'],)).fetchone()[0]
            if n:
                raise ValueError('A previously called REF task cannot enter this continuation')
            for role in ('actor', 'controller', 'volume', 'score'):
                key = f"{role}-{row['slot_index']}"
                if (scope.ORIGINAL_BATCH_ROOT/'resource-claims'/(key+'.json')).exists():
                    raise ValueError('The original physical identity was already consumed')
                resources[key] = copy.deepcopy(old['resources'][key])
            if (scope.ORIGINAL_BATCH_ROOT/'episodes'/str(row['slot_index'])).exists():
                raise ValueError('The original generation environment was already entered')
            inventory.append({'row': row, 'provider_request_count': 0, 'original_environment_entered': False})
    inv = scope.retain(scope.HELD_INVENTORY_FILE, {'rows': inventory, 'model_calls': 0})
    panel = scope.retain(scope.PANEL_FILE, {'version': scope.VERSION, 'rows': rows,
        'source_plan': reference(scope.ORIGINAL_PLAN_FILE), 'source_inventory': inv,
        'selection': 'Both original REF Requests tasks with zero prior calls; no score-based selection',
        'planned_tasks': 2, 'first_model_calls_only': True, 'thinking': False,
        'API_cash_cap_CNY': scope.CASH_CAP_CNY, 'new_generation_token_upper_bound': 10_000_000})
    proposal = scope.retain(scope.USER_PROPOSAL_FILE, {'version': scope.VERSION,
        'user_instruction': '对ref的未定做分析处理', 'panel': panel, 'inventory': inv,
        'original_authorization': reference(scope.PARENT_AUTH_FILE), 'new_generation_attempts': 2,
        'old_called_attempts_resampled': False, 'maximum_new_containers': 6,
        'maximum_new_volumes': 2, 'generation_pairs': 2, 'graders': 2,
        'CPU': 28, 'memory_GiB': 128, 'new_controls': 0, 'new_neutral_calls': 0,
        'maximum_TLS_sessions': 2, 'maximum_TLS_connections': 1024,
        'maximum_TLS_application_bytes': 128*1024**2,
        'same_scoring_CA_and_DNS_as_qualified_v119': True,
        'no_host_binds_ports_GPU_or_shared_configuration_changes': True,
        'cash_amendment': reference(scope.CASH_AMENDMENT_FILE), 'extra_cash_authorized': 0,
        'wait_for_v123_cleanup': True, 'API_or_Docker_calls_during_preparation': 0})
    grant = scope.retain(scope.USER_GRANT_FILE, {'status': 'approved',
        'explicit_user_instruction': '对ref的未定做分析处理', 'proposal': proposal,
        'original_authorization': reference(scope.PARENT_AUTH_FILE),
        'scope': 'Only the previously authorized two never-called original REF attempts; no replay',
        'recorded_utc': datetime.now(timezone.utc).isoformat(), 'runtime_started_by_this_record': False})
    plan = {'version': scope.VERSION, 'root': str(scope.BATCH_ROOT), 'rows': rows,
        'generation_rows': rows, 'panel': panel, 'matrix': panel,
        'host_cpu_pool': reference(scope.CPU_POOL_FILE), 'constraints': scope.CONSTRAINTS,
        'resources': resources, 'resource_role_counts': {'actor': 2, 'controller': 2, 'volume': 2, 'score': 2},
        'environments': {t: {**copy.deepcopy(old['environments'][t]),
                            'configuration': next(r['configuration'] for r in rows if r['instance_id'] == t)} for t in tasks},
        'environment_sources': {t: copy.deepcopy(old['environment_sources'][t]) for t in tasks},
        'diagnostics': [], 'score_recoveries': [], 'original_plan': reference(scope.ORIGINAL_PLAN_FILE),
        'prior_stage_plan': reference(scope.PRIOR_PLAN_FILE), 'inventory': inv, 'user_grant': grant,
        'dispatch_admission': declaration(scope.BATCH_ROOT), 'old_results_preserved': True}
    scope.validate_plan(plan)
    plan_ref = scope.retain(scope.PLAN_FILE, plan)
    recovery = {'version': scope.VERSION, 'original_plan': reference(scope.ORIGINAL_PLAN_FILE),
        'prior_preparation_qualification': reference(scope.ORIGINAL_BATCH_ROOT/'diagnostic-1/result.json'),
        'prior_API_qualification': reference(scope.ORIGINAL_BATCH_ROOT/'api-qualification/result.json'),
        'model_calls_before': {r['slot_id']: 0 for r in rows}, 'first_generation_attempts': 2,
        'new_neutral_calls': 0, 'new_diagnostics': 0, 'new_controls': 0,
        'old_called_attempts_resampled': False, 'cash_amendment': reference(scope.CASH_AMENDMENT_FILE)}
    return {'plan': plan_ref, 'recovery': scope.retain(scope.RECOVERY_FILE, recovery), 'proposal': proposal}


if __name__ == '__main__':
    print(json.dumps(prepare(), ensure_ascii=False))
