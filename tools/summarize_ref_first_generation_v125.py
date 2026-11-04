"""Summarize two previously uncalled original REF attempts; other outcomes remain separate."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path

from proworksim import software_benchmark_scope_v125 as scope
from proworksim.software_benchmark_alignment_contract_v110 import shared_strategy, validate_plan_identity
from proworksim.software_benchmark_host_api_v125 import NEUTRAL_SLOT

_spec = importlib.util.spec_from_file_location('v106_bound_score_metrics',
    Path(__file__).with_name('summarize_interface_panel_v106.py'))
previous = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(previous)
read, ref, bound = previous.read, previous.ref, previous.bound
ledger_snapshot, official_score = previous.ledger_snapshot, previous.official_score
generation_record, diagnostics = previous._previous.generation_record, previous._previous.diagnostics
FIELDS, TERMINAL = previous._previous.FIELDS, previous._previous.TERMINAL
PLAN, BATCH = scope.PLAN_FILE, scope.BATCH_ROOT


def analyze(panel, calls, snapshot, batch, coordinator):
    if not panel['rows'] or any(row['arm'] != 'REF' for row in panel['rows']):
        raise ValueError('Only the two original REF attempts may be summarized')
    for row in panel['rows']:
        validate_plan_identity(row)
    by_slot = defaultdict(list)
    planned = {r['slot_id']: r for r in panel['rows']}
    for request in calls:
        if request['slot_id'] in planned:
            if request['condition'] != planned[request['slot_id']]['condition_id']:
                raise ValueError('Ledger condition differs from frozen panel')
            by_slot[request['slot_id']].append(request)
    rows = []
    for row in panel['rows']:
        detail = {k: row[k] for k in ('slot_id', 'slot_index', 'instance_id', 'arm', 'condition_id', 'seed')}
        records = by_slot[row['slot_id']]
        known = [r['usage'] for r in records if r['usage'] is not None]
        issues = []
        try:
            state, result, evidence = generation_record(batch, coordinator, row)
        except (ValueError, KeyError, OSError) as error:
            state, result, evidence = 'technical_unknown', None, None
            issues.append({'stage': 'generation', 'error': str(error)})
        settled = all(r['status'] == 'settled' and r['usage'] is not None for r in records)
        complete = snapshot['present'] and state in TERMINAL and settled
        detail.update(generation_state=state, generation_result=evidence,
            ledger_requests=len(records), settled_requests=sum(r['status'] == 'settled' for r in records),
            request_status_counts=dict(Counter(r['status'] for r in records)),
            usage_complete_and_called=complete and bool(records), usage_final=complete,
            usage_prefix_complete=bool(records) and settled,
            no_API_request_in_snapshot=not records,
            token_known_lower_bounds={k: sum(u[k] for u in known if u[k] is not None) for k in FIELDS},
            optional_field_reported_requests={k: sum(u[k] is not None for u in known)
                                              for k in FIELDS[3:]},
            exact_final_tokens={k: sum(u[k] for u in known) if complete and all(u[k] is not None for u in known) else None
                                for k in FIELDS},
            unexpected_positive_reasoning_requests=sum((u['reasoning_tokens'] or 0) > 0 for u in known),
            settled_upper_cny=sum(r['settled_nanoyuan'] or 0 for r in records if r['status'] == 'settled') / 1e9,
            unresolved_reserved_cny=sum(r['reserved_nanoyuan'] for r in records if r['status'] != 'settled') / 1e9,
            interface_diagnostics=diagnostics(result))
        try:
            detail['code'] = official_score(batch / 'grading' / f'score-{row["slot_index"]}', row)
        except (ValueError, KeyError, OSError) as error:
            detail['code'] = {'resolved': None, 'state': 'technical_unknown'}
            issues.append({'stage': 'code_score', 'error': str(error)})
        detail['delivery'] = None
        detail['measurement_issues'] = issues
        rows.append(detail)
    groups = {}
    for arm in ('REF',):
        items = [r for r in rows if r['arm'] == arm]
        known_scores = [r for r in items if type(r['code']['resolved']) is bool]
        complete_called = [r for r in items if r['usage_complete_and_called']]
        exact_full = all(r['usage_final'] for r in items)
        groups[arm] = {'planned': len(items),
            'generation_states': dict(Counter(r['generation_state'] for r in items)),
            'code_passed': sum(r['code']['resolved'] is True for r in items),
            'code_failed': sum(r['code']['resolved'] is False for r in items),
            'code_pending_or_unknown': len(items) - len(known_scores),
            'first_generation_2_accuracy_if_fully_scored': sum(r['code']['resolved'] is True for r in items) / len(items) if len(known_scores) == len(items) else None,
            'scored_subset_accuracy_diagnostic': sum(r['code']['resolved'] is True for r in items) / len(known_scores) if known_scores else None,
            'delivery_passed': None,
            'complete_called_usage_tasks': len(complete_called),
            'mean_input_output_complete_called_subset': {key: sum(r['exact_final_tokens'][key] for r in complete_called)/len(complete_called) if complete_called else None for key in FIELDS[:3]},
            'mean_actual_tokens_complete_called_subset': sum(r['exact_final_tokens']['total_tokens'] for r in complete_called) / len(complete_called) if complete_called else None,
            'mean_actual_tokens_all_stage_tasks': sum(r['exact_final_tokens']['total_tokens'] for r in items) / len(items) if exact_full else None,
            'known_token_lower_bounds': {k: sum(r['token_known_lower_bounds'][k] for r in items) for k in FIELDS},
            'exact_group_tokens': {k: sum(r['exact_final_tokens'][k] for r in items)
                                   if exact_full and all(r['exact_final_tokens'][k] is not None for r in items) else None for k in FIELDS},
            'reported_optional_field_requests': {k: sum(r['optional_field_reported_requests'][k] for r in items) for k in FIELDS[3:]},
            'ledger_requests': sum(r['ledger_requests'] for r in items),
            'settled_requests': sum(r['settled_requests'] for r in items),
            'unexpected_positive_reasoning_requests': sum(r['unexpected_positive_reasoning_requests'] for r in items),
            'settled_upper_cny': sum(r['settled_upper_cny'] for r in items),
            'unresolved_reserved_cny': sum(r['unresolved_reserved_cny'] for r in items)}
    other = [r for r in calls if r['slot_id'] not in planned]
    summary = {'version': 'v125-first-generation2-authoritative-token-summary-r1',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'groups': groups, 'ledger_snapshot': snapshot,
        'paired_PROJECT_comparison_run_in_this_batch': False,
        'batch_budget_cny': panel['api_total_budget_cny'],
        'all_batch_settled_upper_cny': sum(r['settled_nanoyuan'] or 0 for r in calls if r['status'] == 'settled') / 1e9,
        'all_batch_unresolved_reserved_cny': sum(r['reserved_nanoyuan'] for r in calls if r['status'] != 'settled') / 1e9,
        'auxiliary_requests_outside_task_means': len(other),
        'auxiliary_settled_upper_cny': sum(r['settled_nanoyuan'] or 0 for r in other if r['status'] == 'settled') / 1e9,
        'measurement_issues': sum(bool(r['measurement_issues']) for r in rows),
        'notes': ['Known usage sums are lower bounds until every request is settled.',
                  'Optional cache/reasoning fields remain unknown when omitted; reasoning is already inside completion.',
                  'Live request count includes admitted reservations; settled count is separately reported.',
                  'Final task means require terminal generation and complete usage; zero-call tasks excluded from called-subset mean.',
                  'Budget and preparation requests share this batch cash ledger but are excluded from task means.',
                  'Recorded interface-error absence is not comprehensive proof that every repair is complete.'],
        'model_calls_by_summarizer': 0, 'Docker_operations': 0, 'ledger_rows_changed': False}
    return summary, rows


def run(plan_path=PLAN, batch=BATCH, output=None):
    plan = read(plan_path)
    if len(plan.get('rows', [])) != 2 or {row['slot_index'] for row in plan['rows']} != {7239, 7267}:
        raise ValueError('Use the frozen two-task first-generation REF plan')
    stage = {'rows': plan['rows'], 'api_total_budget_cny': scope.CASH_CAP_CNY}
    candidates = [batch/'api-coordinator'/name for name in ('progress.json', 'run-summary.json')]
    present = [path for path in candidates if path.exists()]
    latest = max(present, key=lambda path: path.stat().st_mtime_ns) if present else None
    coordinator = read(latest) if latest else {}
    calls, snapshot = ledger_snapshot(scope.LEDGER_FILE if batch == BATCH else batch/'api-ledger.sqlite')
    slots = {row['slot_id'] for row in stage['rows']}
    selected = [call for call in calls if call['slot_id'] in slots]
    summary, rows = analyze(stage, selected, snapshot, batch, coordinator)
    preparation = [call for call in calls if call['request_id'] == NEUTRAL_SLOT+':0001']
    summary.update(plan=ref(plan_path), panel=plan['panel'], original_plan=ref(scope.ORIGINAL_PLAN_FILE),
        coordinator_source=ref(latest) if latest else None,
        official_scoring_validation_source=ref(previous.__file__),
        previous_lifecycle_history_overwritten=False, previous_attempts_imported=0,
        execution_strategy=shared_strategy(), first_generation_tasks=2,
        original_logical_IDs_and_seeds_preserved=True, model_resampling=False,
        original_REF_preparation_usage={'requests': len(preparation), 'new_preparation_requests': 0,
            'known_tokens': sum(call['usage']['total_tokens'] for call in preparation if call['usage'] is not None),
            'excluded_from_stage_cost_and_task_means': True},
        other_lifecycle_ledger_requests_excluded=len(calls)-len(selected),
        full_original50_accuracy=None,
        ledger_scope='Cumulative cash is shared; this report includes only the two original previously uncalled REF identities. No other original unknown is overwritten or resampled.')
    output = output or batch/'reporting'
    output.mkdir(parents=True, exist_ok=True)
    for name, value in [('summary.json', summary), ('per-task.json', rows)]:
        path = output/name
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
        temporary.replace(path)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=PLAN)
    parser.add_argument('--batch-root', type=Path, default=BATCH)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.plan, args.batch_root, args.output), ensure_ascii=False))
