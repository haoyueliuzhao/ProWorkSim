"""Write five implementation configurations and an inactive review plan only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_fixed_organization_v104 import (
    COMMON, VERSION, catalog, catalog_sha256, validate_organization,
)
from proworksim.storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[1]
IDENTITIES = ROOT / 'artifacts/software-benchmark-v054/manifests/identities.json'
DEFAULT_OUTPUT = ROOT / 'artifacts/software-fixed-organization-v104/preparation-r1'
CONFIG = ROOT / 'config/software-fixed-organizations-v104.json'


def build_plan(identity_file=IDENTITIES):
    identities = json.loads(Path(identity_file).read_bytes())
    tasks = identities.get('tasks')
    if (identities.get('task_count') != 500 or not isinstance(tasks, list) or len(tasks) != 500
            or len({task['instance_id'] for task in tasks}) != 500
            or set(identities.get('projection', [])) != {'instance_id', 'repo', 'base_commit', 'image'}):
        raise ValueError('Only the complete existing public task identity pool may be prepared')
    specs = [validate_organization(spec) for spec in catalog()]
    sources = [ROOT / 'src/proworksim' / name for name in (
        'software_fixed_organization_v104.py', 'software_fixed_organization_world_v104.py',
        'software_fixed_organization_runtime_v104.py', 'software_organization_governance_v104.py',
        'software_organization_flow_v104.py')]
    sources.append(Path(__file__).resolve())
    return {'version': VERSION, 'status': 'implementation_available_no_evaluation',
        'authorization': {'real_evaluation_enabled': False, 'model_calls': 0, 'API_cash_CNY': 0,
            'GPU_sessions': 0, 'Docker_containers': 0, 'inherits_prior_experiment_authorization': False},
        'catalog_sha256': catalog_sha256(), 'common_harness': COMMON,
        'selection': 'CHIEF4 PIPELINE3 REVIEW2 SPRINT4 MATRIX4; PEER absent from current user design',
        'previous_implementation': reference(ROOT / 'config/software-fixed-organizations-v065.json'),
        'public_task_pool': {'dataset': 'SWE-bench/SWE-bench_Verified', 'split': 'test',
            'identity_file': reference(identity_file), 'task_count': 500,
            'repositories': identities['repository_counts'], 'dataset_revision': identities['source']['revision'],
            'selection': 'Complete public identity pool, no outcomes or answer materials read'},
        'conditions': [{'organization_id': spec['id'], 'organization_name': spec['name'],
            'members': spec['fixed_members'], 'member_count': spec['member_count'],
            'model': None, 'team_token_budget': None, 'task_seed_manifest': None, 'replicates': None,
            'execution_slots': [], 'specification': spec} for spec in specs],
        'future_execution': {'automatic_activation': False, 'selected_models': None,
            'selected_team_token_budget': None, 'additional_API_cash_budget': None,
            'formal_sprint_quota_frozen': False,
            'required_before_execution': ['Freeze actual model, common team budget and seed matrix.',
                'Review episode deadlines, sprint quota and organization treatment comparability.',
                'Qualify a separately authorized deployment and matched S1 reference.']},
        'measurement_contract': {'code': 'Unique final member_001 working tree after closure',
            'delivery': 'Last legal member_001 submission, independently evidenced',
            'no_best_of_members_or_midrun_candidates': True, 'unknown_and_unstarted_not_model_failure': True,
            'organization_compliance_separate_from_code_score': True,
            'same_publication_and_private_workspace_rules': True,
            'comparison': 'Whole organization treatments; size and decision rules both differ',
            'required_costs': ['team and per-member input/output tokens', 'all actual attempts',
                'organization decisions and rejections', 'public tests', 'handoffs and merges',
                'waiting and conflicts', 'wall time']},
        'implementation_sources': [reference(path) for path in sources],
        'model_calls_performed_by_preparation': 0, 'running_experiment_files_modified': False}


def prepare(output=DEFAULT_OUTPUT):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / 'artifacts/software-fixed-organization-v104'):
        raise ValueError('Use the new implementation preparation artifact root only')
    plan = build_plan()
    output.mkdir(parents=True, exist_ok=True)
    atomic_write(output / 'plan.json', json_bytes(plan))
    atomic_write(CONFIG, json_bytes({'version': VERSION, 'status': plan['status'],
        'catalog_sha256': plan['catalog_sha256'], 'common_harness': COMMON,
        'organizations': catalog(), 'real_evaluation_enabled': False,
        'formal_model_calls_authorized': 0, 'automatic_activation': False}))
    return {'plan': reference(output / 'plan.json'), 'configuration': reference(CONFIG),
            'organizations': len(plan['conditions']), 'real_evaluation_enabled': False,
            'model_calls': 0, 'GPU_operations': 0, 'Docker_operations': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    print(json.dumps(prepare(parser.parse_args().output), ensure_ascii=False))
