"""Read-only joint view of the original250 identities and their recovery scores.

Each original team/issue is counted once. Derived host-export repairs retain the
original unknown record and its one provider ledger; they are not new attempts.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys

os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))

from proworksim import software_benchmark_scope_v132 as scope  # noqa: E402
from proworksim.software_benchmark_candidates_v054 import checked, reference  # noqa: E402

_spec = importlib.util.spec_from_file_location('v132_official_score_reader',
    Path(__file__).with_name('summarize_interface_panel_v106.py'))
_scores = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_scores)
EXPECTED_EXPORT_ERROR = {'type': 'KeyError', 'message': "'project_candidate_lock'"}
RECOVERY_ROOT = ROOT/'runs/software-benchmark-v132/candidate-recovery-r1/episodes'


def read(path, default=None):
    return json.loads(Path(path).read_bytes()) if Path(path).is_file() else default


def bound(ref):
    return json.loads(checked(ref).read_bytes())


def cny(value):
    return str(Decimal(value)/Decimal(1_000_000_000))


def ledger_snapshot(group):
    path = Path(scope.LEDGER_FILES[group])
    if not path.is_file():
        return [], {'state': 'not_initialized', 'cap_CNY': '100', 'ledger_present': False}
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=30) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        records = [dict(row) for row in db.execute(
            'SELECT r.*,m.group_id,m.member_id FROM requests r LEFT JOIN member_requests m USING(request_id) ORDER BY request_id')]
        metadata = dict(db.execute('SELECT name,value FROM metadata'))
    for record in records:
        record['usage'] = json.loads(record.pop('usage_json')) if record.get('usage_json') else None
    settled = sum(row['settled_nanoyuan'] or 0 for row in records if row['status'] == 'settled')
    uncertain = sum(row['reserved_nanoyuan'] for row in records if row['status'] == 'uncertain')
    inflight = sum(row['reserved_nanoyuan'] for row in records if row['status'] == 'reserved')
    committed = sum(row['settled_nanoyuan'] if row['settled_nanoyuan'] is not None else row['reserved_nanoyuan'] for row in records)
    return records, {'ledger_present': True, 'cap_CNY': '100', 'settled_CNY': cny(settled),
        'uncertain_reservation_CNY': cny(uncertain), 'inflight_reservation_CNY': cny(inflight),
        'committed_upper_CNY': cny(committed), 'available_after_reservations_CNY': cny(100_000_000_000-committed),
        'request_statuses': dict(Counter(row['status'] for row in records)),
        'halt_reason': metadata.get('halted'), 'reservation_is_actual_consumption': False,
        'scope': 'Original group ledger, including all historical and continuation requests exactly once'}


def candidate_view(row, old_item):
    folder = scope.BATCH_ROOT/'episodes'/str(row['slot_index'])
    path = folder/'result.json'
    original = read(path)
    if original and any(original.get(key) != row[key] for key in ('slot_id', 'configuration', 'organization_id', 'group_id')):
        raise ValueError('Original generation identity changed')
    result_ref = reference(path) if original is not None else None
    selected, selected_ref = original, result_ref
    repaired = False
    recovery_path = RECOVERY_ROOT/str(row['slot_index'])/'result.json'
    if recovery_path.is_file():
        selected_ref = reference(recovery_path)
        selected = bound(selected_ref)
        proof = bound(selected['recovery_proof'])
        if (original is None or original.get('status') != 'technical_unknown'
                or original.get('error') != EXPECTED_EXPORT_ERROR
                or selected.get('measurement_recovery_only') is not True or selected.get('status') != 'closed'
                or selected.get('original_result') != result_ref or proof.get('original_result') != result_ref
                or proof.get('original_plan') != reference(scope.PLAN_FILE)
                or selected.get('original_episode_folder') != str(folder)
                or selected.get('candidate_content_changed') is not False
                or selected.get('new_model_calls') != 0 or selected.get('original_records_overwritten') is not False
                or any(selected.get(key) != row[key] for key in ('slot_id', 'configuration', 'organization_id', 'group_id'))):
            raise ValueError('Derived candidate does not bind the one original closed attempt')
        repaired = True
    return original, selected, {'original_status': original.get('status') if original else old_item.get('status', 'pending'),
        'original_result': result_ref, 'selected_candidate_result': selected_ref,
        'effective_status': selected.get('status') if selected else 'pending',
        'host_export_measurement_repaired': repaired,
        'original_unknown_retained': repaired,
        'original_error': original.get('error') if original else None,
        'original_not_started_reason': old_item.get('not_started_reason'),
        'closure_reason': (selected or {}).get('closure_reason')}


def generation_category(row, original, selected, view, old_item, eligible, running, deferred_reason=None):
    if view['host_export_measurement_repaired']:
        return 'closed_candidate_measurement_repaired'
    if selected and selected.get('status') == 'closed':
        return 'closed_candidate'
    if original:
        writers_ref = original.get('writer_quiescence')
        writers = bound(writers_ref).get('writers', []) if isinstance(writers_ref, dict) else []
        if any(item.get('state', {}).get('OOMKilled') is True for item in writers):
            return 'writer_OOM'
        if original.get('error') == EXPECTED_EXPORT_ERROR:
            return 'closed_export_repair_pending'
        if original.get('error', {}).get('type') == 'InterruptedError':
            return 'administratively_interrupted'
        return 'generation_technical_unknown'
    reason = old_item.get('not_started_reason')
    if reason == 'environment_not_qualified':
        return 'environment_not_qualified_not_started'
    if deferred_reason in {'cash_exhausted', 'api_monetary_budget_exhausted'}:
        return 'cash_budget_not_started'
    if deferred_reason == 'original_environment_not_qualified':
        return 'environment_not_qualified_not_started'
    if deferred_reason:
        return 'continuation_deferred_not_started'
    if row['slot_id'] in eligible:
        folder = scope.BATCH_ROOT/'episodes'/str(row['slot_index'])
        claimed = any((scope.BATCH_ROOT/'resource-claims'/f"{role}-{row['slot_index']}.json").exists()
                      for role in ('actor', 'controller', 'volume'))
        return 'continuation_in_progress' if running and (folder.exists() or claimed) else 'continuation_pending'
    if reason == 'api_monetary_budget_exhausted':
        return 'cash_budget_not_started'
    if reason:
        return 'other_not_started'
    return 'pending'


def score_view(row, selected, selected_ref, endpoint):
    key = ('score-' if endpoint == 'code' else 'delivery-score-')+str(row['slot_index'])
    folder = scope.GRADING_ROOT/key
    if (folder/'request.json').is_file():
        request = read(folder/'request.json')
        field = 'candidate_lock' if endpoint == 'code' else 'delivery_candidate_lock'
        if (selected is None or request.get('generation_result') != selected_ref
                or request.get('candidate_lock') != selected.get(field)
                or any(request.get(k) != row[k] for k in ('slot_id', 'group_id', 'organization_id'))):
            raise ValueError('Scoring points outside the selected original candidate')
    value = _scores.official_score(folder, row)
    if value['state'] == 'not_scored':
        if (folder/'started.json').exists() and not (folder/'completion.json').exists():
            value['state'] = 'scoring_in_progress'
        elif (folder/'completion.json').exists():
            value['state'] = 'scoring_technical_unknown'
        else:
            value['state'] = 'scoring_pending' if selected and selected.get('status') == 'closed' else 'candidate_pending_or_unknown'
    return value


def delivery_view(row, selected, selected_ref, code):
    endpoint_path = scope.COORDINATOR_ROOT/'delivery-endpoints'/f"{row['slot_index']}.json"
    endpoint = read(endpoint_path)
    if endpoint is None:
        return score_view(row, selected, selected_ref, 'delivery')
    if (endpoint.get('generation_result') != selected_ref or endpoint.get('slot_id') != row['slot_id']
            or endpoint.get('instance_id') != row['instance_id'] or endpoint.get('plan') != reference(scope.PLAN_FILE)):
        raise ValueError('Delivery measurement belongs to another team attempt')
    state = endpoint['status']
    if state == 'no_legal_delivery':
        if endpoint.get('legal_submission') is not False or endpoint.get('resolved') is not False:
            raise ValueError('No-delivery endpoint has inconsistent evidence')
        return {'resolved': False, 'state': state, 'receipt': reference(endpoint_path)}
    if state == 'same_tree_official_result_reused':
        if (type(code.get('resolved')) is not bool or endpoint.get('resolved') is not code['resolved']
                or endpoint.get('code_scoring_receipt') != code.get('receipt')
                or endpoint.get('code_candidate_lock') != selected.get('candidate_lock')
                or endpoint.get('delivery_candidate_lock') != selected.get('delivery_candidate_lock')
                or endpoint.get('same_tree') is not True):
            raise ValueError('Delivery reuse must come from this attempt and its exact same-tree code score')
        return {'resolved': code['resolved'], 'state': state, 'receipt': reference(endpoint_path)}
    return {'resolved': None, 'state': state, 'receipt': reference(endpoint_path)}


def summarize():
    plan_ref = reference(scope.PLAN_FILE)
    plan = scope.validate_plan(bound(plan_ref))
    continuation = read(scope.CONTINUATION_FILE, {})
    eligible = {row['slot_id'] for row in continuation.get('eligible_first_generation', [])}
    progress = read(scope.API_ROOT/'progress.json', {})
    final = read(scope.API_ROOT/'run-summary.json')
    started = (scope.API_ROOT/'execution-started.json').is_file()
    lifecycle = 'closed' if final is not None else 'running' if started else 'pending'
    tasks, groups = [], {}
    for group in scope.GROUP_IDS:
        old = read(scope.prior.API_ROOT/'groups'/group/'run-summary.json', {})
        records, cash = ledger_snapshot(group)
        by_slot = defaultdict(list)
        for record in records:
            by_slot[record['slot_id']].append(record)
        rows = [row for row in plan['rows'] if row['organization_id'] == group]
        if len(rows) != 50 or set(by_slot)-{row['slot_id'] for row in rows}:
            raise ValueError('Every organization retains exactly its50 original identities and ledger')
        outcomes = []
        for row in rows:
            calls = by_slot[row['slot_id']]
            if any(call['condition'] != row['condition_id'] or call['group_id'] != group
                   or call['member_id'] not in row['fixed_members'] for call in calls):
                raise ValueError('Billed requests cross team/member identities')
            item = old.get('generation', {}).get(row['slot_id'], {})
            original, selected, view = candidate_view(row, item)
            deferred_reason = (final or {}).get('deferred', {}).get(row['slot_id'], {}).get('reason')
            view['continuation_deferred_reason'] = deferred_reason
            prepared = read(scope.API_ROOT/'generation-records'/f"{row['slot_index']}.json", {})
            view['continuation_preparation_status'] = prepared.get('status')
            category = generation_category(row, original, selected, view, item, eligible,
                                           lifecycle == 'running', deferred_reason)
            known = [call for call in calls if call['status'] == 'settled' and call['usage'] is not None]
            totals = {out: sum(call['usage'][key] for call in known) for out, key in (
                ('input_tokens', 'prompt_tokens'), ('output_tokens', 'completion_tokens'), ('total_tokens', 'total_tokens'))}
            cache = sum(call['usage'].get('prompt_cache_hit_tokens',
                call['usage'].get('prompt_tokens_details', {}).get('cached_tokens', 0)) for call in known)
            issues = []
            try:
                code = score_view(row, selected, view['selected_candidate_result'], 'code')
                delivery = delivery_view(row, selected, view['selected_candidate_result'], code)
            except (ValueError, KeyError, OSError) as error:
                code, delivery = ({'resolved': None, 'state': 'measurement_identity_unknown'} for _ in range(2))
                issues.append(str(error))
            complete = cash['ledger_present'] and len(known) == len(calls) and (
                original is not None or (not calls and category.endswith('not_started')))
            outcome = {key: row[key] for key in ('slot_index', 'slot_id', 'instance_id', 'organization_id', 'seed', 'fixed_members')}
            outcome.update(generation=view, generation_category=category, code=code, delivery=delivery,
                provider_requests=len(calls), request_statuses=dict(Counter(call['status'] for call in calls)),
                known_tokens=totals, cache_hit_input_tokens=cache,
                known_settled_CNY=cny(sum(call['settled_nanoyuan'] or 0 for call in calls if call['status'] == 'settled')),
                usage_complete=complete, measurement_issues=issues)
            outcomes.append(outcome)
        tasks.extend(outcomes)
        known_outcomes = sum(type(item['code']['resolved']) is bool for item in outcomes)
        passed = sum(item['code']['resolved'] is True for item in outcomes)
        complete_called = [item for item in outcomes if item['usage_complete'] and item['provider_requests']]
        tokens = {key: sum(item['known_tokens'][key] for item in outcomes) for key in ('input_tokens', 'output_tokens', 'total_tokens')}
        groups[group] = {'planned_team_tasks': 50, 'generation_categories': dict(Counter(item['generation_category'] for item in outcomes)),
            'original_generation_statuses': dict(Counter(item['generation']['original_status'] for item in outcomes)),
            'measurement_repaired_closed_candidates': sum(item['generation']['host_export_measurement_repaired'] for item in outcomes),
            'code_passed': passed, 'code_failed': sum(item['code']['resolved'] is False for item in outcomes),
            'code_pending_or_unknown': 50-known_outcomes, 'code_states': dict(Counter(item['code']['state'] for item in outcomes)),
            'full_panel_accuracy': passed/50 if known_outcomes == 50 else None,
            'accuracy_lower_bound': passed/50, 'accuracy_upper_bound': (passed+50-known_outcomes)/50,
            'delivery_passed': sum(item['delivery']['resolved'] is True for item in outcomes),
            'delivery_states': dict(Counter(item['delivery']['state'] for item in outcomes)),
            'provider_called_teams': sum(bool(item['provider_requests']) for item in outcomes),
            'known_token_totals': tokens, 'cache_hit_input_tokens': sum(item['cache_hit_input_tokens'] for item in outcomes),
            'usage_complete_called_teams': len(complete_called),
            'mean_actual_tokens_per_usage_complete_called_team': {
                key: sum(item['known_tokens'][key] for item in complete_called)/len(complete_called) if complete_called else None
                for key in tokens},
            'mean_known_token_lower_bound_per_planned_team': tokens['total_tokens']/50,
            'cash': cash}
    report = {'version': 'v132-original250-joint-readonly-progress-r1',
        'observed_utc': datetime.now(timezone.utc).isoformat(), 'original_plan': plan_ref,
        'lifecycle': lifecycle, 'execution_phase': progress.get('execution_phase', 'pending' if not started else 'unknown'),
        'normal_phase_complete': progress.get('normal_phase_complete', False),
        'historical_recovery_started': progress.get('historical_started', False),
        'normal_phase_closure': progress.get('normal_phase_closure'),
        'runtime_progress': progress, 'groups': groups, 'planned_team_tasks': 250, 'distinct_issues': 50,
        'scoring_root': str(scope.GRADING_ROOT), 'old_v131_zero_score_tree_used': False,
        'candidate_selection_rule': 'Original identity once; use only its exact host-export repair sidecar when present, never choose by score',
        'billing_rule': 'Read each original group request once; restored measurements create no model usage',
        'unknowns_are_not_model_failures': True, 'reservations_are_not_measured_tokens': True,
        'read_only_ledger': True, 'Docker_operations': 0, 'API_calls': 0}
    return report, tasks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Optional new report directory; no existing report is overwritten')
    args = parser.parse_args()
    report, tasks = summarize()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        for name, value in (('summary.json', report), ('per-task.json', tasks)):
            (args.output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
