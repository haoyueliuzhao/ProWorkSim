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

from proworksim.software_benchmark_alignment_contract_v110 import condition
from proworksim.software_benchmark_deepseek_contract_v105 import model_profile
from proworksim import software_benchmark_scope_v111 as scope

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'artifacts/software-benchmark-v062/preparation-r1/panel.json'
QUALIFICATIONS = ROOT / 'runs/software-benchmark-v062/capability-probe-r1-20261026/coordinator-r2/qualifications'
OUTPUT = ROOT / 'artifacts/software-benchmark-v111/preparation-r1'
BATCH = ROOT / 'runs/software-benchmark-v111/aligned-interface-r1'
VERSION = 'v111-nonthinking-paired-interface-panel-r1'
SEED_BASE = 202611030111
FIRST_PHYSICAL_INDEX = 7200
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
        arms = ('REF', 'PROJECT') if task_index % 2 == 0 else ('PROJECT', 'REF')
        for arm in arms:
            condition_id = condition(arm)['condition_id']
            physical = FIRST_PHYSICAL_INDEX + len(rows)
            rows.append({'logical_index': len(rows) + 1, 'slot_index': physical,
                'task_index': task_index, 'slot_id': f'v110:{task["instance_id"]}:{condition_id}:{seed}',
                'source_slot_id': f'v054-{arm}-{task["instance_id"]}',
                'instance_id': task['instance_id'], 'repo': task['repo'],
                'group_id': condition_id, 'condition_id': condition_id, 'model_key': 'DEEPSEEK',
                'model': 'deepseek-flash', 'arm': arm, 'thinking': False, 'seed': seed,
                'provider_seed_sent': False, 'replicate': 0, 'repeat_index': 0,
                'input_plus_output_tokens': 5_000_000, 'budget_tokens': 5_000_000,
                'generation_token_upper_bound': 5_000_000})
    return {'version': VERSION, 'scope': 'v110_aligned_paired_interface_development_check',
        'selection': 'Reuse the prespecified repository-stratified v062 primary 50 identities; no outcome-based replacement',
        'task_ids': identifiers, 'repository_counts': counts, 'planned_distinct_tasks': 50,
        'planned_groups': 2, 'planned_episodes': 100, 'extra_repeats': 0,
        'conditions': [condition(arm)['condition_id'] for arm in ('REF', 'PROJECT')],
        'condition_configurations': {arm: condition(arm) for arm in ('REF', 'PROJECT')},
        'physical_index_range': [7200, 7299], 'physical_identity_uniqueness': 'Must be verified by runtime scope before dispatch',
        'seed_base': SEED_BASE, 'seed_rule': 'seed_base + zero-based original task order; same paired seed',
        'provider_seed_sent': False, 'same_seed_does_not_guarantee_same_actions': True,
        'order': 'Original task order; alternate REF/PROJECT priority by task index',
        'rows': rows, 'public_tasks': public, 'actor_public_fields': list(PUBLIC_FIELDS),
        'common_inference': condition('REF')['inference'],
        'model_profile': model_profile(),
        'common_limits': condition('REF')['episode_limits'],
        'aggregate_input_output_token_upper_bound': 500_000_000,
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
            'current_v111_admission': 'pending_runtime_identity_and_environment_check',
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
    return {'version': 'v111-token-and-interface-metrics-r1',
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
        'causal_limit': 'REF/PROJECT compare execution layers on this calibration panel; no frozen old-interface counterfactual is added',
        'no_score_based_retry_or_candidate_reselection': True}


def prepare(output=OUTPUT):
    source = json.loads(SOURCE.read_bytes())
    panel = make_panel(source)
    refs = {'panel': immutable_write(output / 'panel.json', panel),
        'metrics_contract': immutable_write(output / 'metrics-contract.json', metrics_contract()),
        'environment_inventory': immutable_write(output / 'environment-inventory.json', environment_inventory(panel))}
    text = '''# DeepSeek Flash非思考模式接口测试报告

状态：题单和计量口径已冻结，尚未将准备工作写成实验成绩。REF与PROJECT各50题，独立初态；每题累计输入＋输出上限500万token。继续原v105账本，历史与本批API费用累计上限仍350元，保留旧支出和未定预约。

结果由 `tools/summarize_aligned_interface_v111.py` 按原账本中的本批独立身份及原始回执生成。报告应包含每组计划数、已闭合数、官方代码通过／未通过、待定状态，PROJECT另报合法交付；输入、缓存命中／未命中输入、输出、思考token、请求数和费用均附覆盖范围。累计现金与本批费用分别说明。

完整50题点估计及精确均值须等全部终态与完整账单，不将运行中或技术未定任务计为0。旧50题属于开发校准材料，此次也不称独立确认集或完整500题成绩。

## 待生成结果

尚无本轮模型运行或评分结果。
'''
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
