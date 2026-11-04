"""Read-only per-task REF comparison; recoveries never select the best old score."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'artifacts/software-benchmark-v124/ref-project-comparison-r1'
REF = ROOT/'artifacts/software-benchmark-v114/gap-evidence-recovery-r1/strict-original-episodes.json'
SOURCES = {
    'v120': ROOT/'runs/software-benchmark-v118/project-repaired-r1/reporting-v124-v120',
    'v121': ROOT/'runs/software-benchmark-v121/project-independent-recovery-r1/reporting-v124',
    'v123': ROOT/'runs/software-benchmark-v123/nine-api-recovery-r1/reporting-v124',
}
REVISION = ROOT/'artifacts/software-benchmark-v122/pylint-patch-repair-r1/derived-resolution.json'


def read(path):
    return json.loads(Path(path).read_bytes())


def original(row):
    purposes = row.get('usage', {}).values()
    values = list(purposes)
    return {'task': row['instance_id'], 'repo': row['repo'], 'slot_id': row['slot_id'],
        'code': row['code_result'], 'generation_state': row['generation_state'],
        'delivery': row.get('delivery_result'),
        'delivery_applicable': row['arm'] == 'PROJECT',
        'complete_usage': bool(row.get('entered') and row.get('usage_capture_complete')
                               and row.get('requests', 0) > 0),
        'tokens': {'input': sum(v['prompt_tokens'] for v in values),
                   'output': sum(v['completion_tokens'] for v in values),
                   'total': sum(v['total_tokens'] for v in values),
                   'hit': sum(v['prompt_cache_hit_tokens'] for v in values)},
        'requests': row['requests'], 'cost_CNY': sum(v['cost_CNY'] for v in values),
        'unresolved_calls': row.get('unresolved_usage_calls', 0)}


def revised(row, stage):
    final = row['exact_final_tokens']
    exact = final if final and final.get('total_tokens') is not None else row['token_known_lower_bounds']
    return {'task': row['instance_id'], 'repo': row['instance_id'].split('-')[0].replace('__', '/'),
        'slot_id': row['slot_id'], 'slot_index': row['slot_index'], 'stage': stage,
        'code': row['code']['resolved'], 'generation_state': row['generation_state'],
        'delivery': row['delivery']['resolved'],
        'delivery_applicable': True,
        'complete_usage': row['usage_complete_and_called'],
        'tokens': {'input': exact['input_tokens'], 'output': exact['output_tokens'],
                   'total': exact['total_tokens'], 'hit': exact['cache_hit_tokens']},
        'requests': row['ledger_requests'], 'cost_CNY': row['settled_upper_cny'],
        'reserved_unknown_CNY': row['unresolved_reserved_cny'],
        'code_evidence': row['code'], 'generation_evidence': row['generation_result'],
        'measurement_issues': row['measurement_issues']}


def aggregate(rows):
    rows = list(rows)
    complete = [r for r in rows if r['complete_usage']]
    passed = sum(r['code'] is True for r in rows)
    failed = sum(r['code'] is False for r in rows)
    unknown = len(rows)-passed-failed
    means = {k: sum(r['tokens'][k] for r in complete)/len(complete) if complete else None
             for k in ('input', 'output', 'total')}
    inputs = sum(r['tokens']['input'] for r in complete)
    hits = sum(r['tokens']['hit'] for r in complete)
    return {'planned': len(rows), 'passed': passed, 'failed': failed, 'unknown_or_pending': unknown,
        'confirmed_success_fraction': passed/len(rows),
        'complete_accuracy': passed/len(rows) if unknown == 0 else None,
        'unknown_outcome_bounds_not_confidence_interval': [passed/len(rows), (passed+unknown)/len(rows)],
        'scored_subset_rate_not_full_benchmark': passed/(passed+failed) if passed+failed else None,
        'complete_usage_tasks': len(complete), 'mean_actual_tokens': means,
        'full_plan_token_mean': means['total'] if len(complete) == len(rows) else None,
        'cache_hit_fraction_of_input': hits/inputs if inputs else None,
        'selected_attempt_known_tokens': sum(r['tokens']['total'] or 0 for r in rows),
        'selected_attempt_settled_upper_CNY': sum(r['cost_CNY'] for r in rows),
        'generation_states': dict(Counter(r['generation_state'] for r in rows)),
        'delivery_passed': (sum(r['delivery'] is True for r in rows)
                            if all(r['delivery_applicable'] for r in rows) else None)}


def paired(left, right):
    tasks = sorted(task for task in left if type(left[task]['code']) is bool
                   and type(right[task]['code']) is bool)
    names = {(True, True): 'both_passed', (True, False): 'left_only',
             (False, True): 'right_only', (False, False): 'both_failed'}
    groups = {name: [] for name in names.values()}
    for task in tasks:
        groups[names[(left[task]['code'], right[task]['code'])]].append(task)
    valid_usage = [task for task in tasks if left[task]['complete_usage'] and right[task]['complete_usage']]
    def mean(side):
        return sum(side[t]['tokens']['total'] for t in valid_usage)/len(valid_usage)
    lmean, rmean = mean(left), mean(right)
    return {'N': len(tasks), 'tasks': tasks, 'cell_counts': {k: len(v) for k, v in groups.items()},
        'cell_tasks': groups, 'left_passed': sum(left[t]['code'] for t in tasks),
        'right_passed': sum(right[t]['code'] for t in tasks),
        'token_matched_N': len(valid_usage), 'left_mean_tokens': lmean, 'right_mean_tokens': rmean,
        'relative_token_change_right_vs_left': rmean/lmean-1,
        'subset_only_not_replacement_for_planned50': True}


def run(output=OUT):
    output.mkdir(parents=True, exist_ok=True)
    old = read(REF)
    ref = {r['instance_id']: original(r) for r in old if r['arm'] == 'REF'}
    old_project = {r['instance_id']: original(r) for r in old if r['arm'] == 'PROJECT'}
    raw = {stage: read(folder/'per-task.json') for stage, folder in SOURCES.items()}
    summary = {stage: read(folder/'summary.json') for stage, folder in SOURCES.items()}
    assert len(raw['v120']) == 23 and len(raw['v121']) == 27 and len(raw['v123']) == 9
    selected = [(r, 'v120') for r in raw['v120']]
    selected += [(r, 'v121') for r in raw['v121'] if r['generation_state'] == 'closed']
    selected += [(r, 'v123') for r in raw['v123']]
    assert len(selected) == 50 and sum(stage == 'v121' for _, stage in selected) == 18
    interrupted = {r['instance_id'] for r in raw['v121'] if r['generation_state'] == 'technical_unknown'}
    assert interrupted == {r['instance_id'] for r in raw['v123']}
    project = {r['instance_id']: revised(r, stage) for r, stage in selected}
    assert len(project) == 50 and set(project) == set(ref) == set(old_project)
    # The sole revised old score is an evidence-bound classification correction.
    resolution = read(REVISION)
    row = project['pylint-dev__pylint-4604']
    assert (resolution['resolved'] is False and resolution['candidate_caused_collection_failure'] is True
            and resolution['actual_patch_application_succeeded'] is True
            and resolution['candidate_bytes_changed'] is False
            and resolution['original_report_changed'] is False
            and resolution['original_receipt'] == row['code_evidence']['receipt'])
    row['original_code_measurement'] = copy.deepcopy(row['code_evidence'])
    row.update(code=False, code_adjudication=reference(REVISION))
    comparison = paired(ref, project)
    improvement = paired(old_project, project)
    common_three = comparison['tasks']
    assert all(type(old_project[t]['code']) is bool and old_project[t]['complete_usage']
               for t in common_three)
    old_common_mean = sum(old_project[t]['tokens']['total'] for t in common_three)/len(common_three)
    previous27 = summary['v121']['preserved_original_attempt_context']
    previous9 = summary['v123']['preserved_original_attempt_context']
    overhead_tokens = (previous27['original_known_token_lower_bounds']['total_tokens']
                       + previous9['original_known_token_lower_bounds']['total_tokens'])
    overhead_cost = previous27['original_settled_upper_cny']+previous9['original_settled_upper_cny']
    metrics = {'version': 'v124-ref-vs-repaired-project-task-comparison-r1',
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'PROJECT_source_snapshot_utc': summary['v123']['created_utc'],
        'REF': aggregate(ref.values()), 'PROJECT': aggregate(project.values()),
        'OLD_PROJECT': aggregate(old_project.values()), 'REF_PROJECT_common_known': comparison,
        'OLD_PROJECT_NEW_PROJECT_common_known': improvement,
        'three_conditions_same_tasks': {'N': len(common_three),
            'REF_passed': comparison['left_passed'],
            'OLD_PROJECT_passed': sum(old_project[t]['code'] for t in common_three),
            'PROJECT_passed': comparison['right_passed'],
            'REF_mean_tokens': comparison['left_mean_tokens'],
            'OLD_PROJECT_mean_tokens': old_common_mean,
            'PROJECT_mean_tokens': comparison['right_mean_tokens'],
            'PROJECT_token_change_vs_OLD_PROJECT': comparison['right_mean_tokens']/old_common_mean-1},
        'selection_rule': 'All v120 first23, the18 normal v121 closes, and all preauthorized9 v123 new attempts, including pending outcomes; never choose between scores',
        'PROJECT_selected_attempts_are_original_first_attempts': False,
        'PROJECT_known_incomplete_tasks': [t for t, r in project.items() if r['code'] is None],
        'REF_unknown_tasks': [t for t, r in ref.items() if r['code'] is None],
        'same_model_and_mode': 'deepseek-flash nonthinking',
        'same_task_budget_tokens': 5_000_000, 'same_context_input_output_limits': [131072, 98304, 32768],
        'actual_multi_agent_collaboration': False,
        'historical_REF_vs_repaired_PROJECT_is_single_factor_randomized_causal_test': False,
        'PROJECT_excluded_interrupted_attempts_preserved': {
            'attempts': 36, 'known_tokens_lower_bound': overhead_tokens,
            'settled_upper_CNY': overhead_cost,
            'uncertain_reserved_CNY_not_spent': previous27['original_unresolved_reserved_cny'],
            'included_in_selected_task_mean': False, 'original_bills_refunded': False},
        'model_calls_by_analysis': 0, 'Docker_operations': 0, 'raw_results_modified': False}
    metrics['PROJECT_total_effort_including_interrupted_known_tokens'] = (
        metrics['PROJECT']['selected_attempt_known_tokens']+overhead_tokens)
    for task, row in project.items():
        if row['code'] is True:
            assert row['delivery'] is True, task
    sources = {'REF': reference(REF), 'classification_revision': reference(REVISION),
        'PROJECT': {stage: {'per_task': reference(folder/'per-task.json'),
                           'summary': reference(folder/'summary.json')} for stage, folder in SOURCES.items()}}
    for name, value in [('summary.json', metrics), ('sources.json', sources),
                        ('selected-project-tasks.json', list(project.values())),
                        ('ref-tasks.json', list(ref.values())),
                        ('old-project-tasks.json', list(old_project.values()))]:
        (output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    return metrics


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(run(args.output), ensure_ascii=False))
