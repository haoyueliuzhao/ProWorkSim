"""Prepare exactly the36 original wave2 rows, without dispatch or new attempts."""
from __future__ import annotations

import argparse
import copy
import json
from collections import Counter

from proworksim import software_benchmark_scope_v169 as scope
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import declaration
from proworksim.software_benchmark_wave2_account_v168 import audit, validate_recovery_plan


def prepare():
    if scope.PLAN_FILE.exists():
        return {'plan': reference(scope.PLAN_FILE), 'already_prepared': True}
    old = scope.original_scope
    original = old.validate_plan(scope.load(reference(old.PLAN_FILE)))
    snapshot = audit(scope.LEDGER_FILE, original)
    rows = [copy.deepcopy(r) for r in original['rows'] if r['wave'] == 2]
    if len(rows) != 36 or set(snapshot['admitted_original_slots']) != {r['slot_id'] for r in rows}:
        raise PermissionError('Only the36 exact original second-wave identities with zero requests may enter')
    predecessor = scope.coexistence_status()
    proof = scope.retain(scope.ARTIFACT_ROOT/'predecessor-cleanup-r1/summary.json', predecessor)
    account = scope.retain(scope.ARTIFACT_ROOT/'account-admission-r1/summary.json', snapshot)
    resources = {f"{role}-{r['slot_index']}": copy.deepcopy(original['resources'][f"{role}-{r['slot_index']}"])
        for r in rows for role in ('actor', 'controller', 'volume', 'score', 'delivery-score')}
    for r in rows:
        for version, directory in ((157, 'communication-pilot24-r1'), (159, 'communication-pilot-recovery-r1'), (168, 'communication-wave2-r1')):
            historical = scope.ROOT/f'runs/software-benchmark-v{version}/{directory}/resource-claims'
            if any((historical/f"{role}-{r['slot_index']}.json").exists() for role in ('actor', 'controller', 'volume')):
                raise PermissionError('An uncalled task has consumed environment identity; requires separate review')
    inventory = scope.retain(scope.INVENTORY_FILE, {'version': scope.VERSION, 'rows': rows,
        'generation': {}, 'scores': {}, 'deliveries': {}, 'original_plan': reference(old.PLAN_FILE)})
    tasks = {r['instance_id'] for r in rows}
    plan = {'version': scope.VERSION, 'root': str(scope.BATCH_ROOT),
        'original_plan': reference(old.PLAN_FILE), 'panel': reference(scope.PANEL_FILE),
        'matrix': reference(scope.PANEL_FILE), 'rows': rows, 'generation_rows': rows,
        'admitted_original_slots': [r['slot_id'] for r in rows], 'used_original_slots': snapshot['used_original_slots'],
        'original72_planned_denominator': 72, 'original_ledger': str(scope.LEDGER_FILE),
        'new_cash_budget_CNY': '0.00', 'input_plus_output_token_upper_bound_for_remaining': 180_000_000,
        'predecessor_drain': proof, 'account_admission': account, 'constraints': scope.CONSTRAINTS,
        'host_cpu_pool': reference(scope.CPU_POOL_FILE), 'inventory': inventory,
        'environments': {k: v for k, v in original['environments'].items() if k in tasks},
        'environment_sources': copy.deepcopy(original['environment_sources']), 'resources': resources,
        'resource_role_counts': dict(Counter(v['role'] for v in resources.values())),
        'diagnostics': [], 'training': False, 'old_results_preserved': True,
        'model_calls_during_preparation': 0, 'dispatch_admission': declaration(scope.BATCH_ROOT),
        'wave_policy': {'wave': 2, 'task_wave_and_order_unchanged': True,
            'scores_consulted': False, 'new_attempts_beyond_original72': 0,
            'requires_completed_physical_wave1_audit': True}}
    scope.validate_plan(plan)
    validate_recovery_plan(plan, original, snapshot, coexistence=predecessor)
    ref = scope.retain(scope.PLAN_FILE, plan)
    scope.retain(scope.STATE_ROOT/'admission-control.json', {'version': 'v132-fair-group-admission-r1',
        'batch_root': str(scope.BATCH_ROOT), 'mode': 'run', 'groups': [], 'maximum_generations': 16,
        'revision': 0, 'reason': 'original_wave2_after_measurement_and_predecessor_cleanup'})
    return {'plan': ref, 'original_uncalled_episodes': 36, 'new_model_calls': 0, 'new_cash_budget': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__); parser.add_argument('--bundle', action='store_true')
    args = parser.parse_args()
    if args.bundle:
        from proworksim.software_benchmark_sdk_bundle_v168 import prepare_bundle
        result = prepare_bundle()
        print(json.dumps({'version': result['version'], 'archive': result['archive'], 'probe': result['probe']}))
    else:
        print(json.dumps(prepare()))
