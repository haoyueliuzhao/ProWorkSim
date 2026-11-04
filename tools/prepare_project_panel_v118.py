"""Freeze the existing stratified 50-task identities for a new paired API test.

This preparation reads public tasks and historical environment controls only.
It does not authorize or start generation, containers, services, or scoring.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from proworksim.software_benchmark_alignment_contract_v117 import condition
from proworksim.software_benchmark_deepseek_contract_v105 import model_profile
from proworksim import software_benchmark_scope_v118 as scope

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'artifacts/software-benchmark-v062/preparation-r1/panel.json'
QUALIFICATIONS = ROOT / 'runs/software-benchmark-v062/capability-probe-r1-20261026/coordinator-r2/qualifications'
OUTPUT = ROOT / 'artifacts/software-benchmark-v118/preparation-r1'
BATCH = ROOT / 'runs/software-benchmark-v118/project-repaired-r1'
VERSION = 'v118-nonthinking-paired-interface-panel-r1'
SEED_BASE = 202611040118
FIRST_PHYSICAL_INDEX = 8000
PUBLIC_FIELDS = ('instance_id', 'repo', 'base_commit', 'problem_statement')
REQUESTS = ('psf__requests-2931', 'psf__requests-5414', 'psf__requests-1766', 'psf__requests-1921')


def reference(path):
    path = Path(path).resolve()
    body = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}


def immutable_write(path, value):
    body = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != body:
            raise ValueError('Refusing to overwrite frozen preparation: ' + str(path))
    else:
        with path.open('xb') as stream:
            stream.write(body)
    return reference(path)


def make_panel(source):
    identifiers = source['task_ids']
    if len(identifiers) != 50 or len(set(identifiers)) != 50:
        raise ValueError('The original prespecified panel must contain exactly 50 different tasks')
    by_id = {row['instance_id']: row for row in source['public_tasks']}
    public = [{key: by_id[task][key] for key in PUBLIC_FIELDS} for task in identifiers]
    counts = dict(Counter(row['repo'] for row in public))
    if counts != source['repository_counts'] or len(counts) != 12:
        raise ValueError('Original repository-stratified identity coverage changed')
    rows = []
    for task_index, task in enumerate(public):
        seed = SEED_BASE + task_index
        arms = ('PROJECT',)
        for arm in arms:
            condition_id = condition(arm)['condition_id']
            physical = FIRST_PHYSICAL_INDEX + len(rows)
            rows.append({'logical_index': len(rows) + 1, 'slot_index': physical,
                'task_index': task_index, 'slot_id': f'v117:{task["instance_id"]}:{condition_id}:{seed}',
                'source_slot_id': f'v054-{arm}-{task["instance_id"]}',
                'instance_id': task['instance_id'], 'repo': task['repo'],
                'group_id': condition_id, 'condition_id': condition_id, 'model_key': 'DEEPSEEK',
                'model': 'deepseek-flash', 'arm': arm, 'thinking': False, 'seed': seed,
                'provider_seed_sent': False, 'replicate': 0, 'repeat_index': 0,
                'input_plus_output_tokens': 5_000_000, 'budget_tokens': 5_000_000,
                'generation_token_upper_bound': 5_000_000})
    return {'version': VERSION, 'scope': 'v117_repaired_PROJECT_single_group_development_retest',
        'selection': 'Reuse the prespecified repository-stratified v062 primary 50 identities; no outcome-based replacement',
        'task_ids': identifiers, 'repository_counts': counts, 'planned_distinct_tasks': 50,
        'planned_groups': 1, 'planned_episodes': 50, 'extra_repeats': 0,
        'conditions': [condition(arm)['condition_id'] for arm in ('PROJECT',)],
        'condition_configurations': {arm: condition(arm) for arm in ('PROJECT',)},
        'physical_index_range': [8000, 8049], 'physical_identity_uniqueness': 'Must be verified by runtime scope before dispatch',
        'seed_base': SEED_BASE, 'seed_rule': 'seed_base + zero-based original task order; fresh independent rerun identity; no provider seed field',
        'provider_seed_sent': False, 'same_seed_does_not_guarantee_same_actions': True,
        'order': 'Original task order, PROJECT only',
        'rows': rows, 'public_tasks': public, 'actor_public_fields': list(PUBLIC_FIELDS),
        'common_inference': condition('PROJECT')['inference'],
        'model_profile': model_profile(),
        'common_limits': condition('PROJECT')['episode_limits'],
        'aggregate_input_output_token_upper_bound': 250_000_000,
        'token_upper_bound_is_expected_usage': False, 'api_total_budget_cny': '350.00',
        'API_ledger': str(scope.LEDGER_FILE), 'budget_scope': scope.CASH_MODE,
        'old_settled_and_uncertain_reservations_retained': True,
        'budget_guarantees_completion': False,
        'independent_initial_states': True, 'historical_workspaces_or_feedback_reused': False,
        'selection_uses_previous_scores': False, 'hidden_fields_or_scores_to_actor': False,
        'automatic_replay': False, 'full_500_benchmark_score_claim': False,
        'independent_confirmation_set': False, 'training': False,
        'old_results_overwritten': False, 'runtime_authorized_by_this_plan_file': False,
        'preparation_operations': {'model_calls': 0, 'API_calls': 0, 'Docker_operations': 0, 'GPU_operations': 0},
        'sources': {'original_prespecified_panel': reference(SOURCE)}}


def environment_inventory(panel):
    rows = []
    for task in panel['task_ids']:
        path = QUALIFICATIONS / (task + '.json')
        qualification = json.loads(path.read_bytes()) if path.exists() else None
        if qualification is not None and qualification.get('instance_id') != task:
            raise ValueError('Historical qualification belongs to another task')
        rows.append({'instance_id': task, 'historical_qualification': reference(path) if qualification else None,
            'historical_control_passed': qualification.get('passed') if qualification else None,
            'historical_control_version': qualification.get('version') if qualification else None,
            'current_v118_admission': 'pending_runtime_identity_and_environment_check',
            'generation_network': 'none; API bridge only; no web search',
            'grading_exception': ('private HTTP fixture' if task in REQUESTS[:2] else
                                  'bounded httpbin.org 80/443 real TLS channel' if task in REQUESTS[2:] else None)})
    return {'version': VERSION, 'rows': rows,
        'historical_controls_present': sum(r['historical_qualification'] is not None for r in rows),
        'historical_controls_passed': sum(r['historical_control_passed'] is True for r in rows),
        'existing_control_pass_does_not_grant_new_runtime_authority': True,
        'source_replacement_on_failure': False, 'selected_Requests_instances': list(REQUESTS),
        'qualification_failures_remain_planned_tasks': True,
        'model_scores_read_by_environment_inventory': False, 'new_controls_executed': 0}


def metrics_contract():
    return {'version': 'v118-token-and-interface-metrics-r1',
        'score_endpoint': 'The one final locked code candidate evaluated by the official scorer',
        'PROJECT_extra_endpoint': 'Last legal project delivery; no auto-submit or retroactive delivery',
        'request_accounting_fields': ['prompt_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens',
            'completion_tokens', 'completion_tokens_details.reasoning_tokens', 'settled_nanoyuan', 'reserved_nanoyuan'],
        'total_tokens': 'prompt_tokens + completion_tokens; cached input and reasoning are not added again',
        'unknown_cache_or_reasoning_counts': 'null with coverage counts; absent fields are never replaced by zero',
        'actual_call_count': 'Every financially dispatched agent/condenser request; never planned attempts',
        'reported_means': ['Complete-called subset mean with its denominator',
            'Full 50-task mean only after all tasks terminal and all token accounting complete; no-call terminal tasks then count zero',
            'Matched-task mean for tasks complete in both arms, as diagnostic'],
        'pending_or_failed_usage': 'Retain known lower bounds and uncertain cash reservations; do not omit affected tasks',
        'code_denominator': 50, 'missing_scores_not_model_failures': True,
        'cost_definition': 'Ledger-accounted upper bound in CNY, not provider invoice verification',
        'separate_preparation_cash': True,
        'interface_diagnostics': [
            'PermissionError during managed synchronization, before public test',
            'Truthful executed=false permission refusal and subsequent explicit RPC request',
            'Nullable cursor restoration or schema rejection',
            'Common remaining-budget output cap and actual wire limit',
            'Same-version test, fixed patch, legal delivery and final candidate identity',
            'Native finish, budget, time and SDK-stuck boundaries',
            'Unexpected nonzero reported reasoning tokens in requested nonthinking mode'],
        'repair_success_claim': 'Observed successful paths and remaining exceptions; CPU success alone is not complete runtime certification',
        'causal_limit': 'PROJECT is a fresh rerun on a reused calibration panel; old REF/PROJECT are historical controls, and joint implementation changes are not a single-factor causal effect',
        'no_score_based_retry_or_candidate_reselection': True}


def prepare(output=OUTPUT):
    source = json.loads(SOURCE.read_bytes())
    panel = make_panel(source)
    refs = {'panel': immutable_write(output / 'panel.json', panel),
        'metrics_contract': immutable_write(output / 'metrics-contract.json', metrics_contract()),
        'environment_inventory': immutable_write(output / 'environment-inventory.json', environment_inventory(panel))}
    text = """# v118 PROJECT修复后重测

准备阶段；原50题，DeepSeek Flash非思考，v117受管接口，每题5M累计输入输出预算。
仅PROJECT重新独立生成，旧REF/PROJECT作为历史对照，旧记录不覆盖。
累计现金仍350元，原支出和未定预约保留。完整结果及输入/输出/cache/费用均附覆盖分母。
尚无本轮真实模型或评分结果，不称完整500题成绩。
"""
    path = output / 'report-scaffold.md'
    if path.exists() and path.read_text() != text:
        raise ValueError('Do not overwrite an edited report scaffold')
    if not path.exists():
        path.write_text(text)
    return refs


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output), ensure_ascii=False, indent=2))
