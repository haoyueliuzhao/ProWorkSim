"""Read frozen outcomes/usage; uniformly exclude unknown and cash-ended tasks."""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = Path(__file__).resolve().parents[1]
SCORES = ROOT / 'artifacts/software-benchmark-v134/final-score-audit-r1/per-task.json'
USAGE = ROOT / 'artifacts/software-benchmark-v133/token-comparison-r2/per-task.json'
BEHAVIOR = ROOT / 'artifacts/software-benchmark-v133/collaboration-cost-evidence-r1/per-task.json'
S1 = ROOT / 'artifacts/software-benchmark-v128/independent-count-audit-r1/selected-per-task.json'
GROUPS = ('CHIEF', 'PIPELINE', 'REVIEW', 'SPRINT', 'MATRIX')
FIELDS = ('input_tokens', 'output_tokens', 'total_tokens', 'cache_hit_tokens', 'cache_miss_tokens')
VERSION = 'v136-known-code-and-no-cash-cutoff-usage-r1'


def read(path):
    return json.loads(checked(reference(path)).read_bytes())


def aggregate(rows):
    totals = {key: sum(row['usage']['known_tokens'][key] for row in rows) for key in FIELDS}
    return {'n': len(rows), 'known_token_totals': totals,
        'mean_known_tokens': {key: value / len(rows) if rows else None for key, value in totals.items()},
        'provider_requests': sum(row['usage']['requests'] for row in rows),
        'settled_CNY': str(sum((Decimal(row['usage']['settled_CNY']) for row in rows), Decimal(0))),
        'uncertain_reserved_CNY': str(sum((Decimal(row['usage']['uncertain_reserved_CNY']) for row in rows), Decimal(0))),
        'inflight_reserved_CNY': str(sum((Decimal(row['usage']['inflight_reserved_CNY']) for row in rows), Decimal(0))),
        'all_task_usage_known': all(row['usage']['all_request_usage_known'] for row in rows)}


def paired_s1(rows, baseline):
    selected = [baseline[row['instance_id']] for row in rows]
    totals = {key: sum(row['usage']['known_token_totals'][key] for row in selected) for key in FIELDS}
    return {'n': len(selected), 'code_passed': sum(row['resolved'] is True for row in selected),
        'known_token_totals': totals,
        'mean_tokens': {key: value / len(selected) if selected else None for key, value in totals.items()},
        'provider_requests': sum(row['usage']['requests'] for row in selected),
        'settled_CNY': str(sum((Decimal(row['usage']['settled_cost_nanoyuan']) / 10**9 for row in selected), Decimal(0))),
        'selection': 'Same issues as this team subset, from the unchanged v128 PROJECT adopted attempts'}


def analyze(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    scores = read(SCORES)
    usage = {row['slot_id']: row for row in read(USAGE)}
    behavior = {row['slot_id']: row for row in read(BEHAVIOR)}
    baseline = {row['instance_id']: row for row in read(S1) if row['arm'] == 'PROJECT'}
    if len(scores) != 250 or len(usage) != 250 or len(baseline) != 50:
        raise ValueError('Use the exact original 250 team identities and adopted50 S1 issues')
    rows = []
    for score in scores:
        slot = score['slot_id']
        account, actions = usage[slot], behavior.get(slot)
        valid = (score['code_classification'] in {'passed', 'failed'}
                 and type(score['code']['resolved']) is bool)
        if valid and (actions is None or account['all_request_usage_known'] is not True):
            raise ValueError('A valid-code row lacks trustworthy end-class or final measured usage')
        if actions is not None and bool(actions['cash_censored']) != (actions['exclusive_end_class'] == 'cash_boundary'):
            raise ValueError('Cash flag and classified boundary disagree')
        cash = actions is not None and actions['exclusive_end_class'] == 'cash_boundary'
        keep = valid and not cash
        reasons = ([] if valid else ['code_not_determined']) + (['cash_boundary'] if cash else [])
        rows.append({'slot_id': slot, 'slot_index': score['slot_index'], 'instance_id': score['instance_id'],
            'organization_id': score['organization_id'], 'included': keep,
            'valid_official_code': valid, 'cash_boundary': cash, 'exclusion_reasons': reasons,
            'code_resolved': score['code']['resolved'], 'delivery_resolved': score['delivery']['resolved'],
            'generation_category': score['generation_category'],
            'exclusive_end_class': actions['exclusive_end_class'] if actions else None,
            'legal_delivery_evidence': actions['legal_delivery_evidence'] if actions else None,
            'usage': {key: account[key] for key in ('requests', 'settled_requests', 'statuses', 'known_tokens',
                'all_request_usage_known', 'settled_CNY', 'uncertain_reserved_CNY', 'inflight_reserved_CNY')},
            'S1_PROJECT': {'slot_id': baseline[score['instance_id']]['slot_id'],
                'resolved': baseline[score['instance_id']]['resolved'],
                'known_token_totals': baseline[score['instance_id']]['usage']['known_token_totals']}})
    groups = {}
    for group in GROUPS:
        all_rows = [row for row in rows if row['organization_id'] == group]
        included = [row for row in all_rows if row['included']]
        excluded = [row for row in all_rows if not row['included']]
        cash = [row for row in all_rows if row['cash_boundary']]
        unknown = [row for row in all_rows if not row['valid_official_code']]
        current = aggregate(included)
        reference_s1 = paired_s1(included, baseline)
        passed = sum(row['code_resolved'] is True for row in included)
        groups[group] = {'planned_original_tasks': 50, 'retained_tasks': len(included),
            'code_passed': passed, 'code_failed': len(included) - passed,
            'subset_code_completion_rate': passed / len(included) if included else None,
            'official_delivery_passed': sum(row['delivery_resolved'] is True for row in included),
            'retained_end_classes': dict(Counter(row['exclusive_end_class'] for row in included)),
            'team_retained': current, 'same_task_S1': reference_s1,
            'team_to_same_task_S1_total_token_ratio': current['known_token_totals']['total_tokens']
                / reference_s1['known_token_totals']['total_tokens'] if included else None,
            'excluded_tasks': len(excluded), 'excluded_code_unknown_tasks': len(unknown),
            'excluded_cash_boundary_tasks_all_outcomes': len(cash),
            'cash_excluded_code_passed': sum(row['code_resolved'] is True for row in cash),
            'cash_excluded_code_failed': sum(row['code_resolved'] is False for row in cash),
            'cash_excluded_legal_submission_tasks': sum(row['legal_delivery_evidence'] is True for row in cash),
            'cash_excluded_official_delivery_passed': sum(row['delivery_resolved'] is True for row in cash),
            'all50_actual_accounting_retained': aggregate(all_rows),
            'excluded_actual_accounting_retained': aggregate(excluded),
            'cash_excluded_actual_accounting_retained': aggregate(cash),
            'code_unknown_actual_accounting_retained': aggregate(unknown),
            'retained_instances': [row['instance_id'] for row in included]}
    included = [row for row in rows if row['included']]
    excluded = [row for row in rows if not row['included']]
    all_cost = aggregate(rows)
    kept_cost, removed_cost = aggregate(included), aggregate(excluded)
    assert all(all_cost['known_token_totals'][k] == kept_cost['known_token_totals'][k]
               + removed_cost['known_token_totals'][k] for k in FIELDS)
    assert Decimal(all_cost['settled_CNY']) == Decimal(kept_cost['settled_CNY']) + Decimal(removed_cost['settled_CNY'])
    summary = {'version': VERSION, 'scope': 'New reporting view only, no new generation plan or budget',
        'predicate': 'valid official code (resolved is a bool, classification passed/failed) AND NOT cash_boundary',
        'filter_uses_success_to_choose_rows': False,
        'all_cash_boundaries_excluded_even_if_code_or_delivery_succeeded': True,
        'team_token_boundary_retained': True, 'original_plan_denominator_unchanged': 50,
        'subset_rates_are_not_original_full50_scores': True, 'selected_by_runtime_end_state_not_random_sample': True,
        'retained_tasks': len(included), 'excluded_tasks': len(excluded),
        'excluded_code_unknown_tasks': sum(not row['valid_official_code'] for row in rows),
        'excluded_cash_boundary_tasks': sum(row['cash_boundary'] for row in rows),
        'cash_and_unknown_overlap': sum(row['cash_boundary'] and not row['valid_official_code'] for row in rows),
        'groups': groups, 'all250_accounting': all_cost, 'retained_accounting': kept_cost,
        'excluded_accounting_preserved': removed_cost,
        'accounting_partition_reconciles': True,
        'boundaries': ['Each group has its own retained task set; compare against S1 on exactly those issues.',
            'This filtering removes cash-censored observations rather than estimates what they would achieve without cash limits.',
            'Kept5M-boundary episodes remain budget-limited; this is not unconstrained model capability.',
            'Historical S1 uses its unchanged adopted v128 outcomes, including prior explicitly authorized independent recoveries.',
            'Exclusion changes this report only; all old usage, settlement and uncertain reservations stay in the ledger.',
            'Role/implementation/cash-admission differences from S1 remain; no causal organization effect is isolated.'],
        'sources': {name: reference(path) for name, path in [('official_scores', SCORES),
            ('frozen_usage', USAGE), ('end_class_and_behavior', BEHAVIOR), ('S1_selection', S1)]},
        'reader_source': reference(__file__), 'new_API_calls': 0, 'new_scoring_calls': 0,
        'Docker_operations': 0, 'ledger_writes': 0, 'new_generation_plan': False}
    write_new(output / 'per-task.json', rows)
    write_new(output / 'retained-task-ids.json', {g: value['retained_instances'] for g, value in groups.items()})
    return write_new(output / 'summary.json', summary)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/software-benchmark-v136/cash-excluded-usage-r1')
    print(json.dumps(analyze(parser.parse_args().output)))
