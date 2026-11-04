"""Read-only 250-team result and actual-cost summary; never pool members as tasks."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path

from proworksim import software_benchmark_scope_v131 as scope
from proworksim.software_benchmark_alignment_contract_v131 import GROUP_IDS, validate_plan_identity
from proworksim.software_benchmark_host_api_v131 import ledger_read, budget_status
from proworksim.software_benchmark_candidates_v054 import reference

_spec = importlib.util.spec_from_file_location('v131_verified_official_score_reader',
    Path(__file__).with_name('summarize_interface_panel_v106.py'))
_scores = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_scores)
TERMINAL = {'closed', 'technical_unknown', 'not_started', 'cancelled'}


def read(path):
    return json.loads(Path(path).read_bytes())


def group_records(group):
    if not Path(scope.LEDGER_FILES[group]).exists():
        return [], False
    with ledger_read(group) as db:
        rows = [dict(row) for row in db.execute(
            'SELECT r.*,m.group_id,m.member_id FROM requests r LEFT JOIN member_requests m USING(request_id) '
            'ORDER BY request_id')]
    for row in rows:
        row['usage'] = json.loads(row.pop('usage_json')) if row.get('usage_json') else None
    return rows, True


def outcome(row, coordinator, records, ledger_present):
    validate_plan_identity(row)
    slot = row['slot_id']
    item = coordinator.get('generation', {}).get(slot, {})
    path = scope.BATCH_ROOT/'episodes'/str(row['slot_index'])/'result.json'
    result = read(path) if path.exists() else None
    if result and (result.get('slot_id') != slot or result.get('configuration') != row['configuration']):
        raise ValueError('Final generation belongs to another frozen team')
    state = result['status'] if result else item.get('status', 'pending')
    if any(r['condition'] != row['condition_id'] or r['group_id'] != row['organization_id']
           or r['member_id'] not in row['fixed_members'] for r in records):
        raise ValueError('Billed member identity is outside the frozen team')
    known = [r for r in records if r['usage'] is not None and r['status'] == 'settled']
    usage_complete = ledger_present and len(known) == len(records) and state in TERMINAL
    totals = {field: sum(r['usage'][key] for r in known) for field, key in (
        ('input_tokens','prompt_tokens'),('output_tokens','completion_tokens'),('total_tokens','total_tokens'))}
    errors = []
    try:
        code = _scores.official_score(scope.GRADING_ROOT/f"score-{row['slot_index']}", row)
    except (ValueError, KeyError, OSError) as error:
        code = {'resolved': None, 'state': 'technical_unknown'}
        errors.append({'stage': 'official_code_score', 'error': str(error)})
    delivery = {'resolved': None, 'state': 'pending'}
    evidence = (result or {}).get('delivery_validation', {})
    if evidence.get('submitted') is False:
        delivery = {'resolved': False, 'state': 'no_legal_delivery'}
    elif evidence.get('submitted') is True and evidence.get('same_tree') is True and type(code['resolved']) is bool:
        delivery = {**code, 'same_tree_code_result_reused': True}
    elif evidence.get('submitted') is True:
        try:
            delivery = _scores.official_score(scope.GRADING_ROOT/f"delivery-score-{row['slot_index']}", row)
        except (ValueError, KeyError, OSError) as error:
            delivery = {'resolved': None, 'state': 'technical_unknown'}
            errors.append({'stage': 'official_delivery_score', 'error': str(error)})
    by_member = {}
    for member in row['fixed_members']:
        selected = [r for r in known if r['member_id'] == member]
        by_member[member] = {'settled_requests': len(selected),
            'input_tokens': sum(r['usage']['prompt_tokens'] for r in selected),
            'output_tokens': sum(r['usage']['completion_tokens'] for r in selected),
            'total_tokens': sum(r['usage']['total_tokens'] for r in selected),
            'settled_nanoyuan': sum(r['settled_nanoyuan'] for r in selected)}
    return {key: row[key] for key in ('slot_id','slot_index','instance_id','organization_id','fixed_members','seed')} | {
        'generation_state': state, 'generation_result': reference(path) if path.exists() else None,
        'not_started_reason': item.get('not_started_reason'), 'requests': len(records),
        'request_statuses': dict(Counter(r['status'] for r in records)), 'known_token_totals': totals,
        'usage_complete': usage_complete, 'called': bool(records),
        'known_settled_nanoyuan': sum(r['settled_nanoyuan'] for r in known),
        'unresolved_reserved_nanoyuan': sum(r['reserved_nanoyuan'] for r in records if r['status'] != 'settled'),
        'by_member': by_member, 'by_purpose': dict(Counter(r['usage_id'] for r in records)),
        'code': code, 'delivery': delivery, 'measurement_issues': errors,
        'team_budget_tokens': 5_000_000, 'member_usage_is_not_an_independent_task': True}


def summarize():
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    groups, tasks = {}, []
    for group in GROUP_IDS:
        folder = scope.API_ROOT/'groups'/group
        source = folder/'run-summary.json'
        if not source.exists():
            source = folder/'cursor.json'
        coordinator = read(source) if source.exists() else {}
        records, present = group_records(group)
        by_slot = defaultdict(list)
        for record in records:
            by_slot[record['slot_id']].append(record)
        rows = [row for row in plan['rows'] if row['organization_id'] == group]
        if set(by_slot)-{row['slot_id'] for row in rows}:
            raise ValueError('A group ledger contains an unplanned or preparation request')
        selected = [outcome(row, coordinator, by_slot[row['slot_id']], present) for row in rows]
        tasks.extend(selected)
        known_scores = [r for r in selected if type(r['code']['resolved']) is bool]
        successes = sum(r['code']['resolved'] is True for r in selected)
        complete = [r for r in selected if r['usage_complete']]
        called_complete = [r for r in complete if r['called']]
        groups[group] = {'planned_tasks': len(rows), 'generation_states': dict(Counter(r['generation_state'] for r in selected)),
            'code_passed': successes, 'code_failed': sum(r['code']['resolved'] is False for r in selected),
            'code_pending_or_unknown': len(rows)-len(known_scores),
            'full_panel_accuracy': successes/len(rows) if len(known_scores) == len(rows) else None,
            'success_lower_bound_on_planned_panel': successes/len(rows),
            'unresolved_outcome_upper_bound': (successes+len(rows)-len(known_scores))/len(rows),
            'delivery_passed': sum(r['delivery']['resolved'] is True for r in selected),
            'mean_actual_tokens_per_called_complete_team': {key:
                sum(r['known_token_totals'][key] for r in called_complete)/len(called_complete)
                if called_complete else None for key in ('input_tokens','output_tokens','total_tokens')},
            'mean_actual_tokens_over_all_planned_tasks': sum(r['known_token_totals']['total_tokens'] for r in selected)/len(rows)
                if len(complete) == len(rows) else None,
            'mean_known_token_lower_bound_over_planned_tasks': sum(r['known_token_totals']['total_tokens'] for r in selected)/len(rows),
            'known_settled_nanoyuan': sum(r['known_settled_nanoyuan'] for r in selected),
            'unresolved_reserved_nanoyuan': sum(r['unresolved_reserved_nanoyuan'] for r in selected),
            'usage_complete_tasks': len(complete), 'called_complete_teams': len(called_complete),
            'cash': budget_status(group), 'coordinator': reference(source) if source.exists() else None,
            'member_count_not_used_as_denominator': True}
    return {'version': 'v131-five-organization-authoritative-team-summary-r1',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'plan': reference(scope.PLAN_FILE),
        'groups': groups, 'planned_distinct_tasks': 50, 'planned_team_episodes': 250,
        'cash_borrowing_between_groups': False, 'old_ledgers_opened_or_modified': False,
        'new_API_calls': 0, 'Docker_operations': 0,
        'interpretation': 'Each organization has50 task-level outcomes; member calls share one5M token pool. '
            'Pending, not-started and technical-unknown outcomes are not silently assigned failures. '
            'Unresolved reservations are financial bounds, not measured token consumption.'}, tasks


def main():
    report, tasks = summarize()
    output = scope.BATCH_ROOT/'reporting'
    output.mkdir(parents=True, exist_ok=True)
    for name, value in [('summary.json', report), ('per-task.json', tasks)]:
        path = output/name
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
        temporary.replace(path)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    main()
