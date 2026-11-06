"""Materialize the already selected40 x three pilot without opening runtime resources."""
from __future__ import annotations

from collections import Counter
import copy
import json
import os

from proworksim import software_benchmark_scope_v142 as scope
from proworksim.software_benchmark_alignment_contract_v141 import GROUP_IDS, condition
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import declaration


def prepare():
    if (scope.API_ROOT/'execution-started.json').exists():
        raise PermissionError('An entered experiment cannot be prepared again')
    panel = scope.load(reference(scope.PANEL_FILE))
    previous = scope.load(reference(scope.SOURCE_PLAN_FILE))
    source_rows = {r['instance_id']: r for r in previous['rows']}
    cpu = scope.retain(scope.CPU_POOL_FILE, {'version': scope.VERSION, 'uid': os.getuid(),
        'cpu_ids': sorted(os.sched_getaffinity(0)), 'captured_before_run': True})
    conditions = {g: scope.retain(scope.BATCH_ROOT/'conditions'/(g+'.json'), condition(g)) for g in GROUP_IDS}
    rows, resources, environments, sources = [], {}, {}, {}
    for selected in panel['rows']:
        row = copy.deepcopy(selected)
        task, group, index = row['instance_id'], row['organization_id'], row['slot_index']
        original = scope.load(source_rows[task]['configuration'])
        spec = condition(group)
        config = {**copy.deepcopy(original), **row, 'version': 'v142-role-pilot-config-r1',
            'configuration': conditions[group], 'preparation_only': False,
            'fixed_organization': spec['fixed_organization'], 'execution_alignment': spec['execution_strategy']}
        # The source public task is checked directly against the score-blind panel.
        public = next(t for t in panel['public_tasks'] if t['instance_id'] == task)
        if config['public_task'] != public:
            raise ValueError('The source public task differs from the prespecified panel')
        row['configuration'] = scope.retain(scope.BATCH_ROOT/'configs'/(str(index)+'.json'), config)
        rows.append(row)
        env = previous['environments'][task]
        environments.setdefault(task, {**copy.deepcopy(env), 'configuration': row['configuration']})
        sources.setdefault(task, copy.deepcopy(previous['environment_sources'][task]))
        for role in ('actor', 'controller', 'volume', 'score', 'delivery-score'):
            resources[f'{role}-{index}'] = {'role': 'delivery_score' if role == 'delivery-score' else role,
                'slot_id': row['slot_id'], 'instance_id': task, 'group_id': group, 'organization_id': group,
                'image_id': env['image_id'] if role in {'score','delivery-score'} else env['actor_image_id'],
                'endpoint': 'code' if role == 'score' else 'delivery' if role == 'delivery-score' else None}
            if role == 'delivery-score':
                resources[f'{role}-{index}'].update(skip_when_no_legal_delivery=True,
                                                  same_tree_can_reuse_own_code_result=True)
    for task in panel['task_ids']:
        for kind in ('gold','empty'):
            resources[f'control-v142-{task}-{kind}'] = {'role': 'control', 'instance_id': task,
                'patch_kind': kind, 'image_id': environments[task]['image_id'],
                'endpoint': 'environment_control', 'skip_if_exact_unchanged_qualification_proven': True}
    diagnostics = []
    requested = [(group, 'psf__requests-2931', 'actual_sdk_actor_public_test_and_export') for group in GROUP_IDS]
    requested.append(('FREE2', 'scikit-learn__scikit-learn-14894', 'large_repository_initialization_peak'))
    for index, (group, task, purpose) in enumerate(requested, 1):
        row = next(r for r in rows if r['instance_id'] == task and r['organization_id'] == group)
        diagnostic = {'index': index, 'arm':'PROJECT', 'organization_id':group, 'group_id':group,
            'slot_id':row['slot_id'], 'instance_id':task, 'model_calls':0, 'purpose':purpose}
        diagnostics.append(diagnostic)
        for role in ('actor','controller','volume'):
            resources[f'diagnostic-{index}-{role}'] = {**resources[f"{role}-{row['slot_index']}"],
                'diagnostic':True, 'diagnostic_index':index, 'execution_arm':'PROJECT', 'model_calls':0}
    inventory = scope.retain(scope.INVENTORY_FILE, {'version':scope.VERSION, 'rows':rows,
        'panel':reference(scope.PANEL_FILE), 'generation':{}, 'scores':{}, 'deliveries':{}})
    plan = {'version':scope.VERSION, 'root':str(scope.BATCH_ROOT), 'panel':reference(scope.PANEL_FILE),
        'matrix':reference(scope.PANEL_FILE), 'rows':rows, 'generation_rows':rows, 'host_cpu_pool':cpu,
        'inventory':inventory, 'constraints':scope.CONSTRAINTS, 'environments':environments,
        'environment_sources':sources, 'resources':resources,
        'resource_role_counts':dict(Counter(v['role'] for v in resources.values())),
        'diagnostics':diagnostics, 'training':False, 'old_results_preserved':True,
        'new_runtime_scope':True, 'model_calls_during_preparation':0,
        'dispatch_admission':declaration(scope.BATCH_ROOT)}
    scope.validate_plan(plan)
    return {'plan':scope.retain(scope.PLAN_FILE,plan), 'API_calls':0,'Docker_operations':0,
            'execution_authorized':False}


if __name__ == '__main__':
    print(json.dumps(prepare(), ensure_ascii=False))
