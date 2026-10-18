"""Read-only all16 HOLD work-process audit. Never execute candidate code/tests.

All input evidence is immutable v051 material. Existing actual-input and fee
bindings are reused; no tokenizer, model, world or measurement is instantiated.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import copy
import difflib
import hashlib
import json
from pathlib import Path
import traceback

VERSION = 'v052-hold-process-audit-v1'
MEMBERS = ('member_001', 'member_002')


def jb(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def ref(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': digest(raw), 'bytes': len(raw)}


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(str(path))
    path.write_bytes(jb(value))


def point(path, event, line=None):
    value = {'path': str(Path(path).resolve()), 'experience_sequence': event.get('sequence')}
    if line is not None:
        value['jsonl_line'] = line
    return value


def key(reference):
    return (reference.get('object_id'), reference.get('version_id')) if isinstance(reference, dict) else None


def receipt(value):
    return {k: value[k] for k in ('source_reference', 'files_sha256', 'patch_id', 'delivery_id',
        'report_id', 'executed', 'passed', 'included_patch_ids', 'conflicts', 'status', 'exact_files_match') if k in value}


def decode(message):
    try:
        value = json.loads(message.get('content', ''))
        return value if isinstance(value, dict) else None
    except (ValueError, TypeError):
        return None


def counter_cost(actions):
    known = [a['usage']['total_tokens'] for a in actions if type(a.get('usage', {}).get('total_tokens')) is int]
    return {'actions': len(actions), 'known_actual_tokens': sum(known),
            'unknown_action_costs': len(actions) - len(known),
            'complete_actual_tokens': sum(known) if len(known) == len(actions) else None}


def audit_slot(row):
    report_path = Path(row['worker_report']['path'])
    report_raw = report_path.read_bytes()
    if digest(report_raw) != row['worker_report']['sha256']:
        raise ValueError('Original worker report changed')
    report = json.loads(report_raw)
    result, measurement = report['result'], report['measurement']
    episode = Path(result['episode_manifest']).parent
    manifest = read(episode / 'manifest.json')
    end = episode / manifest['end']['path']
    state = read(end / manifest['end']['state']['path'])
    software = state['projects']['SOFTWARE27']['software']
    event_path = Path(result['evidence_path']).parent / 'experience.jsonl'
    raw = event_path.read_bytes()
    events = [json.loads(line) for line in raw.splitlines() if line]
    evidence = {'worker_report': row['worker_report'], 'episode_manifest': ref(episode / 'manifest.json'),
        'experience': {'path': str(event_path), 'sha256': digest(raw), 'bytes': len(raw)},
        'archived_end_state': ref(end / manifest['end']['state']['path'])}
    versions, version_sources, initial_refs = {}, {}, {}
    for file in manifest['end']['files']:
        path = end / file['path']
        raw_file = path.read_bytes()
        if digest(raw_file) != file['sha256']:
            raise ValueError('Archived immutable file version differs from episode manifest')
        bundle = json.loads(raw_file)
        if isinstance(bundle, dict) and isinstance(bundle.get('files'), dict):
            reference = {'object_id': file['object_id'], 'version_id': file['version_id']}
            versions[key(reference)] = bundle
            version_sources[key(reference)] = {'path': str(path), 'sha256': file['sha256'], 'bytes': len(raw_file)}
            for member in MEMBERS:
                if path.name == member + '.json' and file['version_id'] == 'v1':
                    initial_refs[member] = reference

    def tree(reference):
        value = versions.get(key(reference))
        return digest(jb(value['files'])) if value else None

    feedback = measurement['feedback']
    feedback_by_call = defaultdict(list)
    for f in feedback['feedback_records']:
        feedback_by_call[f['originating_call_id']].append(f)
    calls = {}
    for projection in feedback['projection_audit']:
        actual = projection['actual_input']
        request_path = Path(actual['path'])
        request_bytes = request_path.read_bytes()
        request = json.loads(request_bytes)
        if digest(jb(request)) != actual['selected_request_sha256']:
            raise ValueError('Actual selected request differs from previously bound measurement')
        observations = []
        for index, message in enumerate(request['messages']):
            payload = decode(message)
            if payload and isinstance(payload.get('observation'), dict):
                observations.append((index, payload['observation']))
        calls[actual['call_id']] = {**actual, 'observations': observations,
            'request_file_sha256': digest(request_bytes),
            'messages': request['messages']}
    ordered_calls = sorted(calls.values(), key=lambda c: c['experience_sequence'])
    ledger = result['team_budget']['model']['records']
    raw_responses = {}
    raw_receipts = defaultdict(list)
    decisions = []
    for number, event in enumerate(events, 1):
        payload = event.get('payload')
        if not isinstance(payload, dict):
            continue
        if event['kind'] == 'model_tool_result':
            raw_responses[payload['call_id']] = (payload.get('world_response') or {}, point(event_path, event, number))
        if event['kind'] in ('tool_call', 'harness_tool_call'):
            raw_receipts[payload.get('model_call_id')].append(point(event_path, event, number))
        if event['kind'] == 'policy_decision' and isinstance(payload.get('decision'), dict):
            decision = payload['decision']
            decisions.append((event, number, decision))
    current = copy.deepcopy(initial_refs)
    seen_trees = {member: {tree(reference)} for member, reference in current.items()}
    actions, read_seen, cross_seen, edit_seen = [], {}, {}, {}
    for event, line, decision in decisions:
        call_id = decision.get('model_call_id') or decision.get('call_id')
        member = event['worker_id']
        response, response_source = raw_responses.get(call_id, ({}, None))
        value = response.get('result') or {}
        args = decision.get('arguments') or {}
        action = decision.get('action')
        charge = ledger.get(call_id, {}).get('charge') or {}
        usage = charge.get('reported_usage') or {}
        fb = feedback_by_call.get(call_id, [])
        first_presented = next((f['presentation']['first_exact_presentation'] for f in fb
                                if f['presentation'].get('first_exact_presentation')), None)
        before = copy.deepcopy(current.get(member))
        after = value.get('source_reference') if isinstance(value, dict) else None
        item = {'sequence': event['sequence'], 'member': member, 'call_id': call_id, 'action': action,
            'actual_generation_bound': call_id in calls, 'arguments': args, 'ok': response.get('ok'),
            'result': receipt(value) if isinstance(value, dict) else {}, 'error': response.get('error'),
            'before_private_reference': before, 'before_files_sha256': tree(before),
            'decision_source': point(event_path, event, line), 'response_source': response_source,
            'world_call_sources': raw_receipts.get(call_id, []), 'usage': usage,
            'charged_tokens': charge.get('charged_tokens'),
            'first_exact_feedback_presentation': first_presented,
            'no_actual_followup': [f['no_actual_followup'] for f in fb if f.get('no_actual_followup')],
            'feedback_ids': [f['feedback_id'] for f in fb]}
        if (response.get('ok') is True and after and key(after) in versions and before
                and after['object_id'] == before['object_id'] and after != before):
            before_files, after_files = versions[key(before)]['files'], versions[key(after)]['files']
            changed = [name for name in sorted(set(before_files) | set(after_files))
                       if before_files.get(name) != after_files.get(name)]
            item['edit'] = {'before_reference': before, 'after_reference': after,
                'before_files_sha256': tree(before), 'after_files_sha256': tree(after),
                'changed_paths': changed, 'files_unchanged': not changed,
                'returns_to_earlier_member_tree': tree(after) in seen_trees[member],
                'before_archive': version_sources[key(before)], 'after_archive': version_sources[key(after)],
                'changes': [{'path': name, 'before_sha256': digest(before_files[name].encode()) if name in before_files else None,
                    'after_sha256': digest(after_files[name].encode()) if name in after_files else None,
                    'diff_excerpt': ''.join(difflib.unified_diff(before_files.get(name, '').splitlines(True),
                        after_files.get(name, '').splitlines(True), fromfile='before/' + name, tofile='after/' + name))[:12000]}
                    for name in changed]}
            seen_trees[member].add(tree(after))
            current[member] = copy.deepcopy(after)
        if action in ('replace_file', 'write_file', 'apply_patch', 'edit_file'):
            edit_key = (member, item['before_files_sha256'], digest(jb([action, args])))
            item['repeated_same_edit_attempt'] = edit_seen.get(edit_key)
            edit_seen.setdefault(edit_key, item['sequence'])
        if action in ('read_file', 'search_file') and response.get('ok') is True:
            content = value.get('text') if action == 'read_file' else value.get('matches')
            content_sha = digest(jb(content))
            read_key = (member, args.get('path'), key(value.get('source_reference')),
                        digest(jb({k: v for k, v in args.items() if k != 'patch_id'})), content_sha)
            cross_key = (args.get('path'), content_sha, digest(jb({k: v for k, v in args.items() if k != 'patch_id'})))
            item['read'] = {'source_reference': value.get('source_reference'), 'returned_content_sha256': content_sha,
                'returned_characters': len(content) if isinstance(content, str) else None,
                'same_member_exact_repeat_of_sequence': read_seen.get(read_key),
                'same_content_other_member_prior': cross_seen.get(cross_key) if cross_seen.get(cross_key, {}).get('member') != member else None,
                'returned_text_excerpt': content[:1000] if isinstance(content, str) and args.get('patch_id') else None}
            read_seen.setdefault(read_key, item['sequence'])
            cross_seen.setdefault(cross_key, {'member': member, 'sequence': item['sequence']})
        if action in ('run_tests', 'read_test_result') and isinstance(value, dict):
            page = value.get('page') or {}
            item['test_feedback'] = {'report_id': value.get('report_id'), 'source_reference': value.get('source_reference'),
                'files_sha256': value.get('files_sha256'), 'passed': value.get('passed'), 'executed': value.get('executed'),
                'matches_archived_files_hash': value.get('files_sha256') == tree(value.get('source_reference')),
                'page_index': page.get('index'), 'page_sha256': page.get('sha256'),
                'page_characters': len(page.get('text', '')), 'first_exact_actual_presentation': first_presented,
                'visible_return_excerpt': page.get('text', '')[:4000],
                'semantic_counterexample_understood': None}
        actions.append(item)

    by_member_calls = {m: [c for c in ordered_calls if c['member'] == m] for m in MEMBERS}
    problems = []
    for member in MEMBERS:
        call = by_member_calls[member][0] if by_member_calls[member] else None
        obs = call['observations'][-1] if call and call['observations'] else None
        problems.append({'member': member, 'actual_input': {k: call[k] for k in
            ('call_id', 'path', 'experience_sequence', 'selected_request_sha256', 'input_ids_sha256')} if call else None,
            'message_index': obs[0] if obs else None, 'original_visible_issue': obs[1].get('contract') if obs else None,
            'initial_diagnostics': obs[1].get('initial_diagnostics') if obs else None,
            'correct_semantic_localization': None})
    tests = [a for a in actions if a['action'] == 'run_tests' and a.get('test_feedback', {}).get('executed') is True]
    fixes = [a for a in actions if a['action'] == 'fix_patch' and a['ok'] is True]
    submissions = [a for a in actions if a['action'] == 'submit_integration' and a['ok'] is True]
    test_chains = []
    for test in tests:
        test_ref = test['test_feedback']['source_reference']
        matching_fixes = [a for a in fixes if a['member'] == test['member'] and a['sequence'] > test['sequence']
                          and a['result'].get('source_reference') == test_ref]
        matching_submits = [a for a in submissions if a['member'] == test['member'] and a['sequence'] > test['sequence']
                           and a['result'].get('source_reference') == test_ref]
        later = [c for c in by_member_calls[test['member']] if c['experience_sequence'] > test['sequence']]
        attempts = [a for a in actions if a['member'] == test['member'] and a['sequence'] > test['sequence']
                    and a['action'] in ('fix_patch', 'submit_integration')]
        edits = [a for a in actions if a.get('edit') and a['member'] == test['member'] and a['sequence'] < test['sequence']
                 and a['edit']['after_reference'] == test_ref]
        test_chains.append({'test_sequence': test['sequence'], 'member': test['member'],
            'tested_source_reference': test_ref, 'files_sha256': test['test_feedback']['files_sha256'],
            'passed': test['test_feedback']['passed'], 'preceding_exact_version_edit_sequences': [a['sequence'] for a in edits],
            'first_actual_feedback': test['first_exact_feedback_presentation'],
            'later_actual_same_member_generations': len(later), 'first_later_actual_call': later[0]['call_id'] if later else None,
            'same_version_fixed_sequences': [a['sequence'] for a in matching_fixes],
            'same_version_submitted_sequences': [a['sequence'] for a in matching_submits],
            'subsequent_fix_submit_attempts': [{'sequence': a['sequence'], 'action': a['action'], 'ok': a['ok'],
                'source_reference': a['result'].get('source_reference'), 'error': a['error']} for a in attempts],
            'unsubmitted_passing_public_candidate': test['test_feedback']['passed'] is True and not matching_submits,
            'interpretation': 'Original executed public test only. No unsubmitted private/final acceptance inferred.'})

    patch_chains = []
    for patch_id, patch in software.get('patches', {}).items():
        author = patch['author']
        fixed = next((a for a in fixes if a['result'].get('patch_id') == patch_id), None)
        presented, acquired, imported = [], [], []
        for call in ordered_calls:
            if call['member'] == author:
                continue
            for message_index, obs in call['observations']:
                if any(p.get('patch_id') == patch_id for p in obs.get('patches', [])):
                    presented.append({'member': call['member'], 'call_id': call['call_id'], 'input': call['path'],
                        'message_index': message_index, 'kind': 'public_fixed_patch_metadata_not_source_read'})
                    break
        for action in actions:
            if action['member'] == author or action['arguments'].get('patch_id') != patch_id:
                continue
            if action['action'] in ('read_file', 'search_file') and action['ok'] is True:
                acquired.append({'sequence': action['sequence'], 'member': action['member'],
                    'source_reference': action['result'].get('source_reference'),
                    'actual_feedback_presentation': action['first_exact_feedback_presentation']})
            if action['action'] in ('adopt_candidate', 'integrate_patch') and action['ok'] is True:
                after = action.get('edit', {}).get('after_reference') or action['result'].get('source_reference')
                receiver_tests = [t for t in tests if t['member'] == action['member'] and t['sequence'] > action['sequence']
                                  and t['test_feedback']['source_reference'] == after]
                delivery_rows = []
                for delivery in software.get('deliveries', []):
                    included = versions.get(key(delivery.get('source_reference')), {}).get('included_patch_ids', [])
                    if delivery.get('actor_id') == action['member'] and patch_id in included:
                        delivered_action = next((a for a in submissions if a['result'].get('delivery_id') == delivery['delivery_id']), None)
                        if not delivered_action or delivered_action['sequence'] <= action['sequence']:
                            continue
                        delivery_rows.append({'delivery_id': delivery['delivery_id'], 'source_reference': delivery['source_reference'],
                            'files_sha256': delivery['files_sha256'], 'included_patch_ids': included,
                            'submission_sequence': delivered_action['sequence'] if delivered_action else None,
                            'same_imported_tree': delivery['files_sha256'] == tree(after),
                            'retains_dependency_lineage': True})
                imported.append({'sequence': action['sequence'], 'member': action['member'], 'action': action['action'],
                    'before_reference': action['before_private_reference'], 'after_reference': after,
                    'before_files_sha256': action['before_files_sha256'], 'after_files_sha256': tree(after),
                    'nonidentical_tree_import': action['before_files_sha256'] != tree(after),
                    'receiver_exact_imported_version_tests': [{'sequence': t['sequence'], 'passed': t['test_feedback']['passed'],
                        'actual_feedback_presentation': t['first_exact_feedback_presentation']} for t in receiver_tests],
                    'receiver_delivery_lineage': delivery_rows,
                    'explicit_import_test_delivery_chain': any(d['same_imported_tree'] and
                        t['sequence'] < d['submission_sequence'] and t['first_exact_feedback_presentation'] and
                        t['first_exact_feedback_presentation']['experience_sequence'] < d['submission_sequence']
                        for t in receiver_tests for d in delivery_rows)})
        patch_chains.append({'patch_id': patch_id, 'author': author, 'source_reference': patch['source_reference'],
            'files_sha256': patch['files_sha256'], 'changed_paths': patch.get('changed_paths'),
            'fixed_sequence': fixed['sequence'] if fixed else None, 'public_to_other_stable_member': True,
            'metadata_actual_presentations': presented, 'peer_source_reads': acquired, 'explicit_imports': imported,
            'semantic_use_without_explicit_import': 'unknown_not_inferred_from_visibility_or_messages'})

    messages = []
    for event in state.get('software_events', []):
        if event.get('kind') not in ('work_message', 'handoff', 'delegate', 'task_returned'):
            continue
        shown = []
        for call in ordered_calls:
            if call['member'] != event.get('recipient'):
                continue
            for index, obs in call['observations']:
                visible = [*obs.get('messages', []), *obs.get('handoffs', [])]
                if any(m.get('sequence') == event['sequence'] for m in visible):
                    shown.append({'call_id': call['call_id'], 'path': call['path'], 'message_index': index})
                    break
        messages.append({'world_event_sequence': event['sequence'], 'kind': event['kind'],
            'author': event.get('actor_id'), 'recipient': event.get('recipient'),
            'body_or_message': event.get('body', event.get('message', event.get('reason'))),
            'actual_public_observation_presentations': shown, 'semantic_use': None})
    repeated_reads = [a for a in actions if a.get('read', {}).get('same_member_exact_repeat_of_sequence') is not None]
    overlap_reads = [a for a in actions if a.get('read', {}).get('same_content_other_member_prior')]
    nochange_edits = [a for a in actions if a.get('edit', {}).get('files_unchanged')]
    returned_edits = [a for a in actions if a.get('edit', {}).get('returns_to_earlier_member_tree')]
    repeat_edits = [a for a in actions if a.get('repeated_same_edit_attempt') is not None]
    imports = [i for p in patch_chains for i in p['explicit_imports']]
    summary = {'actual_calls': len(calls), 'reported_usage': result['usage'], 'actions': len(actions),
        'action_counts': dict(Counter(a['action'] for a in actions)), 'successful_actions': sum(a['ok'] is True for a in actions),
        'rejected_actions': [{'sequence': a['sequence'], 'action': a['action'], 'error': a['error']} for a in actions if a['ok'] is False],
        'source_version_edits': sum('edit' in a for a in actions), 'executed_public_tests': len(tests),
        'public_tests_passed': sum(t['test_feedback']['passed'] is True for t in tests),
        'public_tests_failed': sum(t['test_feedback']['passed'] is False for t in tests),
        'fixed_patches': len(patch_chains), 'successful_submissions': len(submissions),
        'passing_test_candidates_without_same_version_submission': sum(t['unsubmitted_passing_public_candidate'] for t in test_chains),
        'same_member_exact_repeat_reads': counter_cost(repeated_reads),
        'other_member_exact_content_overlap_reads': counter_cost(overlap_reads),
        'nochange_version_edits': counter_cost(nochange_edits), 'returns_to_earlier_tree_edits': counter_cost(returned_edits),
        'repeated_same_edit_attempts': counter_cost(repeat_edits),
        'peer_messages_or_handoffs': len(messages),
        'peer_fixed_code_reads': sum(len(p['peer_source_reads']) for p in patch_chains),
        'peer_imports': len(imports), 'nonidentical_peer_imports': sum(i['nonidentical_tree_import'] for i in imports),
        'explicit_peer_import_test_delivery_chains': sum(i['explicit_import_test_delivery_chain'] for i in imports),
        'semantic_use_other_than_explicit_import': 'unknown',
        'fees_scope': 'Full original per-action generation cost; overlapping repeat categories must not be added or called avoidable waste.'}
    return {'version': VERSION, 'slot_id': row['slot_id'], 'task_id': row['task_id'], 'condition': row['condition'],
        'original_F': row['F'], 'original_submitted': row['submitted'], 'original_guard': report['guard']['passed'],
        'sources': evidence, 'actual_input_sources': [{k: c[k] for k in ('call_id', 'member', 'path',
            'experience_sequence', 'selected_request_sha256', 'input_ids_sha256', 'request_file_sha256')} for c in ordered_calls],
        'initial_visible_problems': problems, 'actions': actions, 'test_to_fixed_submission': test_chains,
        'partner_patch_chains': patch_chains, 'partner_messages': messages, 'summary': summary,
        'semantic_diagnosis': {'correct_localization': None, 'why_candidate_not_submitted': None,
            'larger_budget_would_succeed': None, 'free_text_partner_uptake': None},
        'new_model_calls': 0, 'new_tests_or_acceptance': 0, 'new_tokenizer_calls': 0,
        'original_results_modified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--final-report', type=Path, required=True)
    parser.add_argument('--method', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / 'summary.json').exists() or (args.output / 'execution-declaration.json').exists():
        raise FileExistsError('Preserve the unique audit execution; do not silently retry')
    final = read(args.final_report)
    rows = [r for r in final['rows'] if r['status'] == 'closed']
    if len(final['rows']) != 32 or len(rows) != 16:
        raise ValueError('Audit the unchanged original16 executed HOLD rows without outcome selection')
    declaration = {'version': VERSION, 'script': ref(__file__), 'method': ref(args.method),
        'original_final_report': ref(args.final_report), 'ordered_slots': [r['slot_id'] for r in rows],
        'all_outcomes_included': True, 'parallel_readers': 4, 'new_tests_or_model_calls': 0}
    write(args.output / 'execution-declaration.json', declaration)

    def run(row):
        try:
            value = audit_slot(row)
            path = args.output / 'slots' / (row['slot_id'] + '.json')
            write(path, value)
            return {'slot_id': row['slot_id'], 'task_id': row['task_id'], 'condition': row['condition'],
                'original_F': row['F'], 'original_submitted': row['submitted'], 'status': 'audited',
                'artifact': ref(path), 'summary': value['summary']}
        except Exception as error:
            value = {'slot_id': row['slot_id'], 'status': 'audit_error', 'type': type(error).__name__,
                     'message': str(error), 'traceback': traceback.format_exc()}
            write(args.output / 'errors' / (row['slot_id'] + '.json'), value)
            return value

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(run, rows))
    report = {**declaration, 'rows': results, 'original32_inventory': [
        {k: r.get(k) for k in ('slot_id', 'task_id', 'condition', 'status', 'F', 'submitted')} for r in final['rows']],
        'completed_slots': sum(r['status'] == 'audited' for r in results),
        'audit_errors': [r for r in results if r['status'] != 'audited'],
        'new_model_calls': 0, 'new_tests_or_acceptance': 0, 'new_tokenizer_calls': 0,
        'new_measurement_executions': 0, 'original_results_modified': False,
        'no_new12_task_selection_from_results': True}
    write(args.output / 'summary.json', report)
    print(json.dumps({'summary': ref(args.output / 'summary.json'), 'completed_slots': report['completed_slots'],
                      'audit_errors': len(report['audit_errors'])}), flush=True)


if __name__ == '__main__':
    main()
