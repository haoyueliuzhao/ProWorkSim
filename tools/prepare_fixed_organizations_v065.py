"""Prepare six review-only organization conditions; no execution subcommand.

Reads the already local public task identities and new implementation sources.
Does not load credentials, historical outcomes, a model or container runtime.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_fixed_organization_v065 import (
    COMMON, VERSION, catalog, catalog_sha256, validate_organization,
)
from proworksim.storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[1]
IDENTITIES = ROOT / 'artifacts/software-benchmark-v054/manifests/identities.json'
DEFAULT_OUTPUT = ROOT / 'artifacts/software-fixed-organization-v065/preparation-r2'
CONFIG = ROOT / 'config/software-fixed-organizations-v065.json'


def build_plan(identity_file=IDENTITIES):
    public = json.loads(Path(identity_file).read_bytes())
    tasks = public.get('tasks')
    if (public.get('task_count') != 500 or not isinstance(tasks, list) or len(tasks) != 500
            or len({task['instance_id'] for task in tasks}) != 500
            or set(public.get('projection', [])) != {'instance_id', 'repo', 'base_commit', 'image'}):
        raise ValueError('Use the existing complete 500 public identities, never an outcome-selected subset')
    organizations = [validate_organization(spec) for spec in catalog()]
    payload = {
        'version': VERSION,
        'status': 'implementation_complete_review_pending_no_evaluation',
        'authorization': {'real_evaluation_enabled': False, 'model_calls': 0,
                          'API_cash_CNY': 0, 'GPU_sessions': 0, 'Docker_containers': 0,
                          'inherits_v064_authorization': False},
        'catalog_sha256': catalog_sha256(),
        'common_harness': COMMON,
        'superseded_four_member_review': reference(ROOT / 'artifacts/software-fixed-organization-v065/superseded-four-member-r1/manifest.json'),
        'public_task_pool': {'dataset': 'SWE-bench/SWE-bench_Verified', 'split': 'test',
            'identity_file': reference(identity_file), 'task_count': 500,
            'repositories': public['repository_counts'],
            'dataset_revision': public['source']['revision'],
            'selection': 'All existing public identities; no historical scores or answer material read'},
        'conditions': [{'organization_id': spec['id'], 'organization_name': spec['name'],
            'members': spec['fixed_members'], 'member_count': len(spec['fixed_members']), 'model': None, 'team_token_budget': None,
            'task_seed_manifest': None, 'replicates': None, 'execution_slots': [],
            'intended_task_pool_size': 500, 'specification': spec} for spec in organizations],
        'awaiting_single_model_study': {
            'study': 'v064 full Verified token-budget study with its separately versioned continuations',
            'model_candidates': ['original Qwen3.5-9B', 'DeepSeek Flash thinking'],
            'selected_models': None, 'selected_team_token_budget': None,
            'additional_API_cash_budget': None,
            'required_before_execution': [
                'Review the completed single-model budget and censoring evidence.',
                'Select model identities, one common team budget and any further API cash cap.',
                'Freeze task seeds, repeats, full execution matrix and resource authorization.',
                'Ensure a comparable same-harness S1 reference; do not equate old revisions automatically.',
                'Qualify a separately scoped isolated deployment without editing the running v064 sources.',
            ],
            'automatic_activation_after_study': False,
            'six_architectures_is_not_automatic_cross_product': True,
        },
        'measurement_contract': {
            'unit': 'one issue, one fixed organization and one shared team budget',
            'code': 'official grading of the unique locked final member_001 workspace',
            'delivery': 'last legal member_001 submission with its own same-version evidence',
            'no_best_of_members_or_midrun_candidates': True,
            'full_planned_denominator_retained': True,
            'unknown_and_unstarted_separate_from_model_failure': True,
            'required_costs': ['team input tokens', 'team output tokens', 'team actual mean total tokens',
                'per-member actual tokens', 'reasoning and cache subsets without double counting',
                'model attempts', 'public tests', 'communication actions', 'handoff and merge actions',
                'responsibility transfers', 'rejections', 'waiting', 'wall time', 'conflicts'],
            'mean_rule': 'Full-panel actual mean only with complete actual usage for the complete '
                'executed panel; interim subset mean carries its denominator and coverage.',
            'comparison': 'paired tasks and repository-aware uncertainty for representative combinations '
                'of team size, roles, routes and scheduling; not isolated topology or team-size causality',
            'separate_team_size_effect_requires_additional_ablation': True,
            'additional_size_ablation_automatically_authorized': False,
            'public_publication_channel_preserved': True,
        },
        'implementation_sources': [reference(path) for path in sorted([
            ROOT / 'src/proworksim/software_fixed_organization_v065.py',
            ROOT / 'src/proworksim/software_fixed_organization_world_v065.py',
            ROOT / 'src/proworksim/software_fixed_organization_runtime_v065.py',
            Path(__file__).resolve(),
        ])],
        'running_experiment_files_modified': False,
        'model_calls_performed_by_preparation': 0,
    }
    return payload


def prepare(output=DEFAULT_OUTPUT):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / 'artifacts/software-fixed-organization-v065'):
        raise ValueError('Preparation output must stay inside this new review-only artifact root')
    value = build_plan()
    output.mkdir(parents=True, exist_ok=True)
    # These are explicitly mutable review drafts, never execution receipts.
    atomic_write(output / 'plan.json', json_bytes(value))
    atomic_write(CONFIG, json_bytes({'version': VERSION, 'status': value['status'],
        'catalog_sha256': value['catalog_sha256'], 'common_harness': COMMON,
        'organizations': catalog(), 'real_evaluation_enabled': False,
        'formal_model_calls_authorized': 0, 'automatic_activation': False}))
    return {'plan': reference(output / 'plan.json'), 'configuration': reference(CONFIG),
            'conditions': len(value['conditions']), 'public_task_pool': 500,
            'real_evaluation_enabled': False, 'new_model_calls': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output), ensure_ascii=False))
