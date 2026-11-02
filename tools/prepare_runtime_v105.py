"""Prepare 100 independent paired attempts and exact owned object identities."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
import os

from proworksim import software_benchmark_scope_v105 as scope
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_deepseek_contract_v105 import condition

VERSION = 'v105-paired-nonthinking-runtime-preparation-r1'
OLD_PLAN = scope.ROOT/'runs/software-benchmark-v066/v064-continuation-r3/plan.json'
OLD_SHORT_SUMMARY = scope.ROOT/'runs/software-benchmark-v062/capability-probe-r1-20261026/coordinator-r2/run-summary.json'


def prepare():
    if (scope.API_ROOT/'execution-started.json').exists():
        raise PermissionError('Never reprepare an entered experiment')
    panel = scope.load(reference(scope.PANEL_FILE))
    planned = panel['rows']
    if len(planned) != 100 or {r['slot_index'] for r in planned} != set(range(7000, 7100)):
        raise ValueError('Freeze the complete new paired panel first')
    old = scope.load(reference(OLD_PLAN))
    short = scope.load(reference(OLD_SHORT_SUMMARY))
    indexed = {(r['instance_id'], r['arm']): r for r in old['rows']
               if r['model_key'] == 'DEEPSEEK' and r['input_plus_output_tokens'] == 5_000_000}
    collisions = []
    for index in range(7000, 7100):
        for root in (scope.BATCH_ROOT, scope.original.BATCH_ROOT):
            if ((root/'episodes'/str(index)).exists()
                    or any((root/'resource-claims'/f'{role}-{index}.json').exists()
                           for role in ('actor', 'controller', 'volume', 'score', 'delivery-score'))):
                collisions.append((str(root), index))
    if collisions:
        raise PermissionError('Physical identity was already consumed: '+str(collisions[:10]))
    scope.BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    scope.retain(scope.CPU_POOL_FILE, {'version': VERSION, 'uid': os.getuid(),
        'cpu_ids': sorted(os.sched_getaffinity(0)), 'captured_before_run': True})
    conditions = {arm: scope.retain(scope.BATCH_ROOT/'conditions'/f'{arm}.json', condition(arm))
                  for arm in ('REF', 'PROJECT')}
    rows, environments, resources, sources = [], {}, {}, {}
    for entry in planned:
        source = indexed[(entry['instance_id'], entry['arm'])]
        old_config = scope.load(source['configuration'])
        if old_config['public_task']['repo'] != entry['repo']:
            raise ValueError('Panel repository differs from the original public environment')
        row = {**copy.deepcopy(entry), 'group_id': entry['condition_id'], 'replicate': 0,
            'execution_arm': entry['arm'], 'measurement_kind': 'full_verified_comparison',
            'panel_kind': 'interface_repair_probe_50', 'thinking': False,
            'generation_token_upper_bound': 5_000_000, 'input_plus_output_tokens': 5_000_000,
            'source_slot_id': f"v054-{entry['arm']}-{entry['instance_id']}",
            'provider_seed_sent': False, 'model': 'deepseek-flash'}
        config = {**old_config, **{k: v for k, v in row.items() if k != 'configuration'},
            'version': 'v105-private-nonthinking-config-r1',
            'configuration': conditions[entry['arm']], 'preparation_only': False}
        row['configuration'] = scope.retain(scope.BATCH_ROOT/'configs'/f"{row['slot_index']}.json", config)
        rows.append(row)
        env = old['environments'][entry['instance_id']]
        for role in ('actor', 'controller', 'volume', 'score'):
            resources[f"{role}-{row['slot_index']}"] = {'role': role, 'slot_id': row['slot_id'],
                'instance_id': row['instance_id'],
                'image_id': env['image_id'] if role == 'score' else env['actor_image_id'],
                'endpoint': 'code' if role == 'score' else None}
        if row['arm'] == 'PROJECT':
            resources[f"delivery-score-{row['slot_index']}"] = {'role': 'delivery_score',
                'slot_id': row['slot_id'], 'instance_id': row['instance_id'], 'image_id': env['image_id'],
                'endpoint': 'delivery', 'skip_when_no_legal_delivery': True,
                'same_tree_can_reuse_own_code_result': True}
        environments.setdefault(row['instance_id'], {'configuration': row['configuration'],
            'image_id': env['image_id'], 'actor_image_id': env['actor_image_id']})
        if row['instance_id'] not in sources:
            qualification = short['qualifications'][row['instance_id']]
            if qualification['status'] != 'qualified':
                raise ValueError('The old preselected panel has an unresolved control identity')
            proof = scope.load(qualification['qualification'])
            qplan = scope.load(proof['plan'])
            sources[row['instance_id']] = {'original_configuration': source['configuration'],
                'qualification': qualification['qualification'], 'qualification_plan': proof['plan'],
                'qualification_configuration': qplan['environments'][row['instance_id']]['configuration'],
                'qualified_before_model_scores': True, 'new_equivalence_still_required': True}
    for task, env in environments.items():
        for kind in ('gold', 'empty'):
            resources[f'control-{task}-{kind}'] = {'role': 'control', 'instance_id': task,
                'patch_kind': kind, 'image_id': env['image_id'], 'endpoint': 'environment_control'}
    diagnostics = []
    for number, arm in enumerate(('REF', 'PROJECT'), 1):
        # Repository kind is selected without consulting model outcomes.
        row = next((r for r in rows if r['arm'] == arm and r['repo'] == 'matplotlib/matplotlib'),
                   next(r for r in rows if r['arm'] == arm))
        diagnostics.append({'index': number, 'arm': arm, 'slot_id': row['slot_id'],
                            'instance_id': row['instance_id'], 'model_calls': 0})
        for role in ('actor', 'controller', 'volume'):
            resources[f'diagnostic-{number}-{role}'] = {
                **resources[f"{role}-{row['slot_index']}"], 'diagnostic': True,
                'diagnostic_index': number, 'execution_arm': arm, 'model_calls': 0}
    inventory = scope.retain(scope.INVENTORY_FILE, {'version': VERSION, 'rows': rows,
        'panel': reference(scope.PANEL_FILE), 'generation': {}, 'scores': {}, 'deliveries': {},
        'qualifications': {}, 'candidate_qualifications': sources, 'usage_record_files': [],
        'allowed_generation_slot_ids': [r['slot_id'] for r in rows],
        'API_ledger': str(scope.LEDGER_FILE), 'API_cash_cap_CNY': scope.CASH_CAP_CNY,
        'new_attempts': True, 'old_records_modified': False})
    plan = {'version': scope.VERSION, 'root': str(scope.BATCH_ROOT), 'rows': rows,
        'panel': reference(scope.PANEL_FILE), 'matrix': reference(scope.PANEL_FILE),
        'host_cpu_pool': reference(scope.CPU_POOL_FILE), 'inventory': inventory,
        'constraints': copy.deepcopy(scope.CONSTRAINTS), 'environments': environments,
        'environment_sources': sources, 'resources': resources,
        'resource_role_counts': dict(Counter(v['role'] for v in resources.values())),
        'diagnostics': diagnostics, 'historical_results_preserved': True,
        'training': False, 'model_calls_during_preparation': 0,
        'new_runtime_scope': True, 'system_parent_slice_required': False}
    scope.validate_plan(plan)
    scope.retain(scope.PLAN_FILE, plan)
    return {'version': VERSION, 'plan': reference(scope.PLAN_FILE), 'inventory': inventory,
            'physical_ids_unconsumed': True, 'new_generation_attempts': 100,
            'model_calls': 0, 'Docker_operations': 0, 'runtime_authorized': scope.AUTH_FILE.is_file()}


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(prepare(), ensure_ascii=False))
