"""Read final owned records only; no model, Docker, network or runtime mutation."""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BATCH = ROOT / 'runs/software-benchmark-v105/nonthinking-interface-r1'
OUT = Path(__file__).parent


def read(path):
    return json.loads(Path(path).read_bytes())


def ref(path):
    path = Path(path)
    raw = path.read_bytes()
    return {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def main():
    rows, unknown, scoring = [], [], []
    for f in sorted((BATCH / 'episodes').glob('*/result.json')):
        result = read(f)
        slot = int(f.parent.name)
        child_ref = result.get('controller_result')
        child = read(child_ref['path']) if child_ref else {}
        row = {'slot_index': slot, 'instance_id': result['instance_id'], 'arm': result['arm'],
               'status': result['status'], 'result': ref(f), 'model_calls': result.get('model_calls'),
               'closure_reason': result.get('closure_reason'),
               'boundary_reason': child.get('terminal_boundary', {}).get('reason'),
               'budget_kind': child.get('terminal_boundary'),
               'execution_policy': {key: child.get('execution_policy', {}).get(key)
                    for key in ('sdk_runs', 'stuck_corrections', 'finish_reviews', 'final_sdk_status')},
               'final_review_messages_sent': sum(event.get('kind') == 'policy_message_sent'
                    and event.get('phase') == 'finish_review'
                    for event in child.get('execution_policy', {}).get('events', []))}
        if result['status'] != 'closed':
            error = child.get('error') or result.get('error', {})
            classification = ('budget_boundary_type_not_recognized'
                              if 'episode_token_reservation_exhausted' in json.dumps(error)
                              else 'coordinator_administrative_cancellation')
            unknown.append({**row, 'classification': classification, 'error': error,
                            'host_error': result.get('error')})
        if result['arm'] == 'PROJECT' and child.get('managed_boundary'):
            outcomes = child['managed_boundary']['outcomes']
            counts, rejected, statuses, reason_counts = Counter(), Counter(), Counter(), Counter()
            examples, nulls, searches, public_test_results = [], [], [], []
            for outcome in outcomes:
                statuses[outcome.get('status', 'missing')] += 1
                decision = outcome.get('decision', {})
                action, args = decision.get('action'), decision.get('arguments', {})
                response = outcome.get('response', {})
                body = response.get('result', {})
                if action:
                    counts[action] += 1
                    if isinstance(args, dict) and 'cursor' in args and args['cursor'] is None:
                        nulls.append({'action': action, 'ok': response.get('ok'), 'status': outcome.get('status')})
                if response.get('ok') is False or outcome.get('status') == 'model_format_feedback':
                    rejected[action or 'pre_dispatch_format'] += 1
                    message = outcome.get('reason') or response.get('error') or response.get('result')
                    text = json.dumps(message, ensure_ascii=False) if not isinstance(message, str) else message
                    reason_counts[text[:240]] += 1
                    if len(examples) < 12:
                        examples.append({'action': action, 'arguments': args, 'message': text[:500]})
                if action == 'search_repository' and response.get('ok') is True:
                    searches.append({'complete': body.get('complete'), 'matches': len(body.get('matches', [])),
                        'scanned_characters': body.get('scanned_characters'),
                        'cursor_supplied': 'cursor' in args})
                if action == 'run_tests':
                    public_test_results.append({'ok': response.get('ok'), 'executed': body.get('executed'),
                        'passed': body.get('passed'), 'source_reference': body.get('source_reference'),
                        'files_sha256': body.get('files_sha256'), 'total_pages': body.get('total_pages'),
                        'body_characters': body.get('body_characters')})
            tests = []
            for response_path in sorted((f.parent / 'controller-output/public-test-rpc').glob('*/response.json')):
                response = read(response_path)
                execution = response.get('execution', {})
                tests.append({'response': ref(response_path), 'passed': response.get('passed'),
                    **{key: execution.get(key) for key in ('executed', 'input_tree_sha256', 'source_reference',
                       'argv', 'returncode', 'timed_out', 'wall_seconds')}})
            tree_counts = Counter(t['input_tree_sha256'] for t in tests if t['executed'])
            seen_trees, seen_versions, repeated_seconds, same_version_repeats = set(), set(), 0, 0
            for test in tests:
                key = test['input_tree_sha256']
                version = json.dumps(test['source_reference'], sort_keys=True)
                if key in seen_trees:
                    repeated_seconds += test['wall_seconds'] or 0
                if (key, version) in seen_versions:
                    same_version_repeats += 1
                seen_trees.add(key)
                seen_versions.add((key, version))
            wire_call_counts, wire_nulls, rejected_multi_tokens = Counter(), [], 0
            for response_path in sorted((f.parent / 'controller-output/model-ledger').glob('response-*.json')):
                response = read(response_path)
                calls = response['choices'][0]['message'].get('tool_calls') or []
                wire_call_counts[len(calls)] += 1
                if len(calls) > 1:
                    rejected_multi_tokens += response['usage']['total_tokens']
                for call in calls:
                    try:
                        arguments = json.loads(call['function']['arguments'])
                    except (ValueError, TypeError):
                        continue
                    if isinstance(arguments, dict) and 'cursor' in arguments and arguments['cursor'] is None:
                        wire_nulls.append({'tool': call['function']['name'], 'response': ref(response_path)})
            preflight = read(result['initial_sync_preflight']['path']) if result.get('initial_sync_preflight') else {}
            row['managed'] = {'outcome_count': len(outcomes), 'operation_counts': dict(counts),
                'status_counts': dict(statuses), 'rejected_counts': dict(rejected),
                'rejection_reasons': dict(reason_counts), 'rejection_examples': examples,
                'explicit_null_cursor_calls': nulls, 'searches': searches,
                'public_test_results': public_test_results, 'public_test_executions': tests,
                'test_wall_seconds': sum(t['wall_seconds'] or 0 for t in tests if t['executed']),
                'repeated_identical_test_tree_executions': sum(n - 1 for n in tree_counts.values()),
                'repeated_identical_test_tree_wall_seconds': repeated_seconds,
                'repeated_same_tree_and_version_executions': same_version_repeats,
                'wire_tool_call_count_histogram': dict(wire_call_counts),
                'multi_tool_response_tokens': rejected_multi_tokens,
                'wire_explicit_null_cursor_calls': wire_nulls,
                'preflight_passed': preflight.get('passed'), 'terminal_sync': child.get('terminal_sync'),
                'actor_close': child.get('actor_close'),
                'terminal_details': child['managed_boundary'].get('terminal_details'),
                'role_stops': child['managed_boundary'].get('role_stops')}
        rows.append(row)
    for f in sorted((BATCH / 'grading').glob('score-*/receipt.json')):
        result = read(f)
        report = result.get('official_result', [None, {}])[1].get(result['instance_id'], {})
        quiet = read(f.parent / 'quiescence.json')
        scoring.append({'slot_index': int(f.parent.name.split('-')[1]), 'instance_id': result['instance_id'],
            'condition_id': result['condition_id'], 'status': result['status'], 'resolved': result.get('resolved'),
            'receipt': ref(f), 'quiescent': quiet.get('quiescent'), 'cleanup_errors': quiet.get('cleanup_errors'),
            'official_report_flags': {key: report.get(key) for key in
                 ('patch_successfully_applied', 'resolved', 'infra_failure', 'infra_failure_reason')},
            'scoring_validity': result.get('scoring_validity'), 'error': result.get('error')})
    scores_by_slot = {r['slot_index']: r for r in scoring}
    by_task = {}
    for r in rows:
        score = scores_by_slot.get(r['slot_index'], {})
        r['code_status'] = score.get('status', 'not_scored')
        r['code_resolved'] = score.get('resolved')
        by_task.setdefault(r['instance_id'], {})[r['arm']] = r
    ref_only = [pair['PROJECT']['slot_index'] for pair in by_task.values()
                if pair['REF']['code_resolved'] is True and pair['PROJECT']['code_resolved'] is False]
    project = [r for r in rows if 'managed' in r]
    ops, rejects, statuses = Counter(), Counter(), Counter()
    for r in project:
        ops.update(r['managed']['operation_counts'])
        rejects.update(r['managed']['rejected_counts'])
        statuses.update(r['managed']['status_counts'])
    summary = {'version': 'v109-final-failure-interface-evidence-r1',
        'generation_counts': dict(Counter(r['status'] for r in rows)),
        'new_v108_generation_counts': dict(Counter(r['status'] for r in rows if r['slot_index'] >= 7043)),
        'generation_unknown_counts': dict(Counter(r['classification'] for r in unknown)),
        'scoring_counts': dict(Counter(r['status'] for r in scoring)),
        'PROJECT_closed_records_covered': len(project), 'PROJECT_operation_counts': dict(ops),
        'PROJECT_rejected_counts': dict(rejects), 'PROJECT_status_counts': dict(statuses),
        'PROJECT_public_test_execution_count': sum(len(r['managed']['public_test_executions']) for r in project),
        'PROJECT_public_test_wall_seconds': sum(r['managed']['test_wall_seconds'] for r in project),
        'PROJECT_repeated_identical_test_tree_executions': sum(r['managed']['repeated_identical_test_tree_executions'] for r in project),
        'PROJECT_repeated_identical_test_tree_wall_seconds': sum(r['managed']['repeated_identical_test_tree_wall_seconds'] for r in project),
        'PROJECT_repeated_same_tree_and_version_executions': sum(r['managed']['repeated_same_tree_and_version_executions'] for r in project),
        'PROJECT_explicit_null_cursor_calls': sum(len(r['managed']['explicit_null_cursor_calls']) for r in project),
        'PROJECT_wire_tool_call_count_histogram': dict(sum((Counter(r['managed']['wire_tool_call_count_histogram']) for r in project), Counter())),
        'PROJECT_multi_tool_response_tokens': sum(r['managed']['multi_tool_response_tokens'] for r in project),
        'PROJECT_tasks_with_multi_tool_responses': sum(any(int(n) > 1 for n in r['managed']['wire_tool_call_count_histogram']) for r in project),
        'PROJECT_wire_explicit_null_cursor_calls': sum(len(r['managed']['wire_explicit_null_cursor_calls']) for r in project),
        'PROJECT_tasks_with_invalid_test_cursor': sum(r['managed']['rejected_counts'].get('read_test_result', 0) > 0 for r in project),
        'PROJECT_public_tests_passed': sum(t['passed'] is True for r in project for t in r['managed']['public_test_executions']),
        'PROJECT_public_tests_timed_out': sum(t['timed_out'] is True for r in project for t in r['managed']['public_test_executions']),
        'PROJECT_largest_public_test_page_count': max(t.get('total_pages') or 0 for r in project for t in r['managed']['public_test_results']),
        'PROJECT_code_passed_without_any_whole_public_suite_pass': sum(r['code_resolved'] is True and not any(t['passed'] is True for t in r['managed']['public_test_executions']) for r in project),
        'REF_final_review_messages_sent': sum(r['final_review_messages_sent'] for r in rows if r['arm'] == 'REF'),
        'new_REF_budget_boundaries_closed': [r['slot_index'] for r in rows if r['status'] == 'closed' and r['arm'] == 'REF' and r['boundary_reason'] == 'episode_token_reservation_exhausted'],
        'PROJECT_initial_and_terminal_sync_passed': sum(r['managed']['preflight_passed'] is True and r['managed']['terminal_sync']['exact_complete_tree'] is True for r in project),
        'REF_pass_PROJECT_fail_slot_indices': ref_only,
        'limitations': ['Managed action counts cover only 44 closed PROJECT records; administrative cancellations are excluded.',
            'Physical cleanup/technical unknown is not a normal code failure.',
            'Aggregate public-test wall time is not batch elapsed time or CPU-core seconds.',
            'Action and pagination counts show observed burden, not causal attribution of the score gap.'],
        'model_calls_by_analysis': 0, 'Docker_operations': 0, 'old_results_modified': False}
    for name, data in [('summary.json', summary), ('per-task.json', rows), ('generation-unknown.json', unknown),
                       ('scoring-unknown.json', [r for r in scoring if r['status'] != 'official_report'])]:
        (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
