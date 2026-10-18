"""One terminal-only read of worker reports; never replay measurement/trajectories."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

VERSION = 'v051-holdout-terminal-mechanism-summary-v1'
FEEDBACK = ('all_saved_feedback_units', 'protocol_feedback_saved_exactly',
    'with_later_actual_generation', 'presented_in_later_actual_generation',
    'presented_in_first_actual_followup', 'without_later_actual_generation')
PAGES = ('reports_saved', 'reports_storage_verified', 'reports_with_directory_presented',
    'reports_with_any_page_presented', 'reports_historically_fully_presented',
    'verified_page_feedback_returns', 'actual_page_read_requests')
USAGE = ('decisions', 'attempts', 'prompt_tokens', 'completion_tokens', 'total_tokens',
    'output_bearing_calls', 'budget_charged_tokens', 'uncertain_usage_attempts')
GATE_LISTS = ('page_protocol_violations', 'page_protocol_unresolved', 'projection_violations',
    'projection_unresolved', 'feedback_missing_from_first_actual_followup',
    'context_blocked_feedback_ids', 'unresolved_no_followup_ids')


def read(path):
    return json.loads(Path(path).read_bytes())


def reference(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def pick(value, names):
    return {key: value.get(key) for key in names}


def length(value):
    return len(value) if isinstance(value, (dict, list)) else None


def bool_counts(values):
    return {'true': sum(v is True for v in values), 'false': sum(v is False for v in values),
            'unknown': sum(v is not True and v is not False for v in values)}


def totals(values):
    known = [v for v in values if type(v) in (int, float)]
    return {'known_sum': sum(known), 'known_reports': len(known),
        'unknown_reports': len(values) - len(known),
        'complete_sum': sum(known) if len(known) == len(values) else None}


def compact_report(report, report_ref, expected_row, plan_ref):
    issues = []
    if report.get('row') != expected_row or report.get('source_plan') != plan_ref:
        issues.append('report_row_or_source_plan_binding_differs')
    result, measurement = report.get('result') or {}, report.get('measurement') or {}
    feedback, stop = measurement.get('feedback') or {}, measurement.get('stop_assessment') or {}
    denominator, pages = feedback.get('denominators') or {}, feedback.get('page_denominators') or {}
    gate = feedback.get('mechanism_gate_inputs') or {}
    boundary, lifecycle = result.get('boundary') or {}, result.get('member_lifecycle') or {}
    guard, episode_guard = report.get('guard') or {}, report.get('episode_guard') or {}
    by_tool = denominator.get('by_tool')
    run_tests = by_tool.get('run_tests', {}).get('feedback_units', 0) if isinstance(by_tool, dict) else None
    resources = stop.get('local_resource_rejections')
    if resources is None:
        resources = feedback.get('local_resource_rejections')
    elif feedback.get('local_resource_rejections') is not None and resources != feedback['local_resource_rejections']:
        issues.append('duplicated_resource_rejection_summaries_differ')
    resource_counts = Counter(item.get('reason', 'unknown') for item in resources.values()) if isinstance(resources, dict) else None
    work = boundary.get('work_boundaries')
    work_counts = Counter(item.get('cause', 'unknown') for item in work) if isinstance(work, list) else None
    role_stops = boundary.get('role_stops')
    role_counts = Counter(role_stops.values()) if isinstance(role_stops, dict) else None
    state = measurement.get('state_binding') or {}
    updates = {'report_new_parameter_updates': report.get('new_parameter_updates'),
        'report_new_backward_calls': report.get('new_backward_calls'),
        'result_actor_updates': result.get('actor_updates'), 'result_critic_updates': result.get('critic_updates'),
        'result_new_backward_calls': result.get('new_backward_calls'),
        **{'guard_' + key: guard.get(key) for key in ('new_actor_steps', 'new_critic_steps', 'new_backward_calls')},
        **{'episode_guard_' + key: episode_guard.get(key) for key in ('new_actor_steps', 'new_critic_steps', 'new_backward_calls')}}
    return {'report': report_ref, 'report_status': report.get('status'), 'binding_issues': issues,
        'raw_F': result.get('F'), 'raw_submitted': result.get('submitted'),
        'verdict': pick(report.get('verdict') or {}, ('decision', 'reasons', 'F_used_for_selection')),
        'measurement_decision': measurement.get('decision'), 'feedback_status': feedback.get('status'),
        'usage': pick(result.get('usage') or {}, USAGE),
        'feedback': pick(denominator, FEEDBACK), 'no_followup_reasons': denominator.get('no_followup_reasons'),
        'feedback_by_tool': by_tool, 'pagination': pick(pages, PAGES),
        'page_read_outcomes': pages.get('page_read_outcomes'), 'page_continuation_reasons': pages.get('continuation_reasons'),
        'tests': {'run_tests_feedback_units': run_tests, 'report_histories': length(feedback.get('report_histories')),
            'shared_test_budget_used': result.get('team_budget', {}).get('tests', {}).get('used'),
            'host_final_evaluation_attempts': result.get('host_final_evaluation_attempts'),
            'host_final_test_executions': result.get('host_final_test_executions')},
        'stop': {'boundary_status': boundary.get('status'), 'closure_reason': boundary.get('closure_reason'),
            'role_stops': role_stops, 'role_stop_counts': dict(role_counts) if role_counts is not None else None,
            'work_boundary_counts': dict(work_counts) if work_counts is not None else None,
            'classification': stop.get('classification'), 'decision': stop.get('decision'),
            'global_violation_count': length(stop.get('global_violations')), 'unresolved_count': length(stop.get('unresolved')),
            'local_resource_rejection_counts': dict(resource_counts) if resource_counts is not None else None,
            'local_context_event_count': length(stop.get('local_context_events')),
            'administrative_censoring': result.get('administrative_censoring')},
        'member_lifecycle': pick(lifecycle, ('initial_members', 'stable_member_ids', 'cumulative_births',
            'member_requested_births', 'external_births', 'live_at_end', 'peak_live', 'actual_output_participants',
            'participating_members', 'permanent_retirement_enabled', 'current_work_ended')),
        'mechanism_gate': {**pick(gate, ('resolved', 'actual_generated_requests', 'requests_verified_under_v049')),
            **{key + '_count': length(gate.get(key)) for key in GATE_LISTS}},
        'native_accounting': pick(measurement.get('native_accounting') or {}, ('mode', 'formal_model_admission_eligible',
            'actual_model_generations', 'actual_native_generations', 'known_actual_tokens',
            'exact_response_multiset_bound', 'all_started_settled')),
        'state_binding': pick(state, ('heldout_condition', 'historical_steps', 'state_registry_sha256')),
        'fixed_endpoint_binding': pick(measurement.get('fixed_endpoint_binding') or {}, ('status', 'submitted', 'F',
            'host_final_test_executions', 'terminal_working_tree_assessed', 'no_submit_F0_does_not_bypass_mechanical_gate')),
        'guard': pick(guard, ('passed', 'all_parameters_frozen', 'all_gradients_absent', 'optimizer_constructed', 'critic_constructed')),
        'episode_guard': pick(episode_guard, ('learning_unchanged', 'rng_restored_exactly', 'software_binding_unchanged',
            'actor_identity_unchanged')),
        'reported_update_counters': updates,
        'all_present_update_counters_zero': all(type(v) is int and v == 0 for v in updates.values())
            if all(v is not None for v in updates.values()) else None,
        'semantic_partner_use': {'status': 'not_analyzed', 'proven_chain_count': None,
            'reason': 'No raw semantic-use analysis performed; messages, tests, pages and shared activity do not establish partner uptake.'}}


def reason_totals(reports, getter):
    values = [getter(r) for r in reports]
    counter = Counter()
    for value in values:
        if isinstance(value, dict):
            counter.update(value)
    return {'known_counts': dict(sorted(counter.items())),
            'known_reports': sum(isinstance(v, dict) for v in values),
            'unknown_reports': sum(not isinstance(v, dict) for v in values)}


def summarize(root):
    root = Path(root).resolve()
    plan, supervisor = read(root / 'plan.json'), read(root / 'supervisor.json')
    if supervisor.get('status') not in ('complete', 'paused') or any(
            state.get('status') == 'running' for state in supervisor.get('states', {}).values()):
        raise ValueError('Wait for terminal inventory and all in-flight workers to close')
    plan_ref = reference(root / 'plan.json')
    if supervisor.get('plan') != plan_ref or len(plan['rows']) != 32:
        raise ValueError('Original fixed32 inventory and exact plan binding are required')
    rows, reports, used = [], [], set()
    for original in plan['rows']:
        slot = original['slot_id']
        state = supervisor['states'][slot]
        row = {**pick(original, ('slot_id', 'task_id', 'condition')), 'host_status': state['status'],
            'mechanisms': None, 'attempt_reports': [], 'mechanism_status': 'unknown'}
        attempts = state.get('attempts', [])
        if state['status'] == 'source_or_input_blocked':
            if attempts:
                raise ValueError('Blocked inventory has worker attempts')
            row.update(mechanism_status='not_applicable_blocked', qualification=plan['blocked_cases'][original['task_id']])
        elif not attempts:
            row['mechanism_status'] = 'not_started'
        for attempt in attempts:
            path = Path(attempt['output']).resolve() / 'report.json'
            if str(path) in used:
                raise ValueError('Duplicate worker report would double-count costs or feedback')
            used.add(str(path))
            if not path.exists():
                row['attempt_reports'].append({'path': str(path), 'status': 'missing_technical_unknown'})
                continue
            report = read(path)
            value = compact_report(report, reference(path), original, plan_ref)
            row['attempt_reports'].append(value)
            reports.append(value)
        if len(row['attempt_reports']) == 1 and 'report' in row['attempt_reports'][0]:
            row['mechanisms'] = row['attempt_reports'][0]
            row['mechanism_status'] = 'reported_closed' if row['mechanisms']['report_status'] == 'closed' else 'reported_nonclosed'
        rows.append(row)
    aggregate = {'usage': {key: totals([r['usage'][key] for r in reports]) for key in USAGE},
        'feedback': {key: totals([r['feedback'][key] for r in reports]) for key in FEEDBACK},
        'pagination': {key: totals([r['pagination'][key] for r in reports]) for key in PAGES},
        'tests': {key: totals([r['tests'][key] for r in reports]) for key in
            ('run_tests_feedback_units', 'report_histories', 'shared_test_budget_used',
             'host_final_evaluation_attempts', 'host_final_test_executions')},
        'no_followup_reasons': reason_totals(reports, lambda r: r['no_followup_reasons']),
        'page_read_outcomes': reason_totals(reports, lambda r: r['page_read_outcomes']),
        'page_continuation_reasons': reason_totals(reports, lambda r: r['page_continuation_reasons']),
        'role_stops': reason_totals(reports, lambda r: r['stop']['role_stop_counts']),
        'work_boundaries': reason_totals(reports, lambda r: r['stop']['work_boundary_counts']),
        'local_resource_rejections': reason_totals(reports, lambda r: r['stop']['local_resource_rejection_counts']),
        'closure_reasons': dict(Counter(r['stop']['closure_reason'] or 'unknown' for r in reports)),
        'stop_classifications': dict(Counter(r['stop']['classification'] or 'unknown' for r in reports)),
        'verdict_decisions': dict(Counter(r['verdict']['decision'] or 'unknown' for r in reports)),
        'fixed_endpoint_statuses': dict(Counter(r['fixed_endpoint_binding']['status'] or 'unknown' for r in reports)),
        'actor_guard_passed': bool_counts([r['guard']['passed'] for r in reports]),
        'episode_guard': {key: bool_counts([r['episode_guard'][key] for r in reports]) for key in
            ('learning_unchanged', 'rng_restored_exactly', 'software_binding_unchanged', 'actor_identity_unchanged')},
        'mechanism_gate_resolved': bool_counts([r['mechanism_gate']['resolved'] for r in reports]),
        'native_exact_response_multiset_bound': bool_counts([r['native_accounting']['exact_response_multiset_bound'] for r in reports]),
        'native_all_started_settled': bool_counts([r['native_accounting']['all_started_settled'] for r in reports]),
        'reported_new_parameter_updates': totals([r['reported_update_counters']['report_new_parameter_updates'] for r in reports]),
        'reported_new_backward_calls': totals([r['reported_update_counters']['report_new_backward_calls'] for r in reports]),
        'member_requested_births': totals([r['member_lifecycle']['member_requested_births'] for r in reports]),
        'external_births': totals([r['member_lifecycle']['external_births'] for r in reports]),
        'all_present_update_counters_zero': bool_counts([r['all_present_update_counters_zero'] for r in reports])}
    return {'version': VERSION, 'root': str(root), 'script': reference(__file__),
        'plan': plan_ref, 'supervisor': reference(root / 'supervisor.json'), 'host_status': supervisor['status'],
        'inventory_rows': len(rows), 'inventory_tasks': len({r['task_id'] for r in rows}),
        'row_statuses': dict(Counter(r['mechanism_status'] for r in rows)), 'unique_worker_reports_read': len(reports),
        'aggregate_scope': 'Only observed worker reports. Blocked/not-started/missing evidence stays explicit and is not filled with zero.',
        'interpretation': {'feedback_first_followup': 'Recorded measurement denominator; not remeasured.',
            'tests': 'run_tests feedback, saved report histories, consumed shared test units and final host test executions are separate counters; do not add them together.',
            'semantic_partner_use': 'Not analyzed; no claim from message/page/test frequencies.',
            'historical_actor_steps': '4/4 and5/5 are historical retained states, not new updates.',
            'safety': 'No raw trajectories, native generations, test artifacts or external guard files opened; no measurement replay.'},
        'new_model_calls': 0, 'new_tokenizer_calls': 0, 'new_test_executions': 0,
        'new_measurement_executions': 0, 'raw_trajectory_files_read': 0, 'rows': rows, 'aggregate': aggregate}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Do not overwrite a terminal mechanism summary')
    result = summarize(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'report': reference(args.output), 'row_statuses': result['row_statuses'],
                      'unique_worker_reports_read': result['unique_worker_reports_read']}))


if __name__ == '__main__':
    main()
