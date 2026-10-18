"""Synthesize already generated audit artifacts; never reopen v051 trajectories."""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path('/data1/zhuxinrui/projects/ProWorkSim')
BASE = ROOT / 'artifacts/software-bridge-v052/hold-process-audit'


def read(path):
    return json.loads(Path(path).read_bytes())


def ref(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def main():
    source = read(BASE / 'r2/summary.json')
    mechanisms = read(ROOT / 'artifacts/software-calibration-v051/hold-final-mechanisms/report.json')
    records = {r['slot_id']: r['mechanisms'] for r in mechanisms['rows'] if r['mechanisms']}
    rows, imports, tested_unsubmitted, problems = [], [], [], {}
    rejection_counts, action_counts, rejection_costs = Counter(), Counter(), Counter()
    counts = ('source_version_edits', 'executed_public_tests', 'public_tests_passed', 'public_tests_failed',
              'fixed_patches', 'successful_submissions', 'peer_messages_or_handoffs', 'peer_fixed_code_reads',
              'peer_imports', 'nonidentical_peer_imports', 'explicit_peer_import_test_delivery_chains')
    cost_keys = ('same_member_exact_repeat_reads', 'other_member_exact_content_overlap_reads',
                 'nochange_version_edits', 'returns_to_earlier_tree_edits', 'repeated_same_edit_attempts')
    all_messages, all_repeated = [], []
    for entry in source['rows']:
        detail = read(entry['artifact']['path'])
        s = entry['summary']
        problems.setdefault(entry['task_id'], detail['initial_visible_problems'][0])
        actions = detail['actions']
        action_counts.update(s['action_counts'])
        submissions = [a for a in actions if a['action'] == 'submit_integration' and a['ok'] is True]
        for a in actions:
            if a['ok'] is False:
                rejection = (a['error'] or {}).get('message', 'unknown')
                rejection_counts[rejection] += 1
                rejection_costs[rejection] += a.get('usage', {}).get('total_tokens', 0)
            if a.get('read', {}).get('same_member_exact_repeat_of_sequence') is not None:
                all_repeated.append({'slot_id': entry['slot_id'], 'sequence': a['sequence'], 'member': a['member'],
                    'action': a['action'], 'arguments': a['arguments'], 'read': a['read'], 'usage': a['usage'],
                    'decision_source': a['decision_source']})
        failed_scope = None
        if not entry['original_submitted']:
            failed_scope = ('public_pass_observed_but_no_legal_fixed_submission' if s['public_tests_passed'] else
                'no_public_test_observed' if not s['executed_public_tests'] else 'public_tests_observed_without_all_pass_candidate')
            for chain in detail['test_to_fixed_submission']:
                if chain['passed'] is True:
                    tested_unsubmitted.append({'slot_id': entry['slot_id'], 'source': entry['artifact'], 'chain': chain,
                        'following_actor_actions': [{k: a.get(k) for k in ('sequence', 'member', 'action', 'arguments', 'ok',
                            'error', 'usage', 'decision_source', 'first_exact_feedback_presentation')} for a in actions
                            if a['sequence'] > chain['test_sequence'] and a['member'] == chain['member']],
                        'legal_contract_rejections_are_not_runtime_bugs': True,
                        'original_F_remains': entry['original_F'], 'unsubmitted_candidate_retested': False})
        for patch in detail['partner_patch_chains']:
            for imported in patch['explicit_imports']:
                prior = [a for a in submissions if a['sequence'] < imported['sequence']
                    and a['result'].get('files_sha256') == imported['after_files_sha256']]
                endpoint = submissions[-1]['result'] if submissions else None
                imports.append({'slot_id': entry['slot_id'], 'source': entry['artifact'], 'patch_id': patch['patch_id'],
                    'author': patch['author'], 'import': imported,
                    'prior_identical_tree_submissions': [{k: a[k] for k in ('sequence', 'member', 'result')} for a in prior],
                    'author_already_submitted_same_tree': any(a['member'] == patch['author'] for a in prior),
                    'last_fixed_delivery': endpoint,
                    'receiver_submission_is_last_endpoint': any(d['delivery_id'] == endpoint['delivery_id']
                        for d in imported['receiver_delivery_lineage']) if endpoint else None,
                    'additional_episode_success_attributable_to_import': None})
        for message in detail['partner_messages']:
            all_messages.append({'slot_id': entry['slot_id'], **message})
        rows.append({'slot_id': entry['slot_id'], 'task_id': entry['task_id'], 'condition': entry['condition'],
            'original_F': entry['original_F'], 'original_submitted': entry['original_submitted'],
            'observed_process_class_for_no_submit': failed_scope, 'audit': entry['artifact'],
            **{k: s[k] for k in counts}, **{k: s[k] for k in cost_keys},
            'actual_calls': s['actual_calls'], 'actual_tokens': s['reported_usage']['total_tokens'],
            'actor_policy_actions': s['actions'],
            'stop': records[entry['slot_id']]['stop'], 'original_actor_guard': detail['original_guard']})
    report = {'version': 'v052-hold-process-audit-final-v1', 'purpose': 'StageA diagnosis of all16 existing HOLD runs; not new scoring',
        'sources': {'audit_summary_r2': ref(BASE / 'r2/summary.json'), 'first_audit_summary': ref(BASE / 'summary.json'),
            'method_before_execution': ref(BASE / 'method-before-execution.json'),
            'first_parser_source': ref(BASE / 'first-execution-source.py'), 'final_parser_source': source['script'],
            'synthesis_source': ref(__file__), 'original_mechanism_summary': ref(ROOT / 'artifacts/software-calibration-v051/hold-final-mechanisms/report.json')},
        'original32_inventory': source['original32_inventory'], 'audited_unique_slots': len(rows),
        'original_successes': sum(r['original_F'] == 1 for r in rows), 'original_no_submit': sum(not r['original_submitted'] for r in rows),
        'parser_execution': {'first_attempted_slots': 16, 'first_succeeded': 11, 'first_failed': 5,
            'failure': 'Legal Gamma1 same-input patch reference treated as list by analysis parser',
            'reprocessed_only_failed_slots': source['source_slots_reprocessed'], 'reused_successful_slots': source['successful_prior_slots_reused'],
            'final_successful_slots': 16, 'remaining_parser_errors': 0,
            'experimental_technical_unknowns_created': 0, 'old_experiment_status_changed': False},
        'totals': {k: sum(r[k] for r in rows) for k in counts},
        'repeat_costs': {k: {'actions': sum(r[k]['actions'] for r in rows),
            'known_actual_tokens': sum(r[k]['known_actual_tokens'] for r in rows),
            'unknown_action_costs': sum(r[k]['unknown_action_costs'] for r in rows)} for k in cost_keys},
        'action_counts': dict(action_counts), 'legal_or_tool_rejection_counts': dict(rejection_counts),
        'rejected_action_original_generation_tokens': dict(rejection_costs),
        'policy_action_count': sum(r['actor_policy_actions'] for r in rows),
        'original_format_feedback_units': sum((records[r['slot_id']]['feedback_by_tool'] or {}).get('format_feedback', {}).get('feedback_units', 0) for r in rows),
        'no_submit_process_classes': dict(Counter(r['observed_process_class_for_no_submit'] for r in rows if not r['original_submitted'])),
        'initial_visible_problem_by_task': problems, 'rows': rows,
        'tested_but_unsubmitted_cases': tested_unsubmitted, 'partner_import_chronologies': imports,
        'partner_messages': all_messages, 'exact_same_member_repeat_reads': all_repeated,
        'partner_summary': {'import_actions': len(imports), 'unique_slots_with_import': len({x['slot_id'] for x in imports}),
            'nonidentical_import_actions': sum(x['import']['nonidentical_tree_import'] for x in imports),
            'identical_tree_import_actions': sum(not x['import']['nonidentical_tree_import'] for x in imports),
            'all_imports_followed_author_same_tree_submission': all(x['author_already_submitted_same_tree'] for x in imports),
            'unique_slots_with_receiver_as_last_endpoint': len({x['slot_id'] for x in imports if x['receiver_submission_is_last_endpoint']}),
            'messages_or_handoffs': len(all_messages),
            'message_events_with_actual_observation_presentation': sum(bool(x['actual_public_observation_presentations']) for x in all_messages),
            'free_text_semantic_uptake': None, 'causal_success_gain': None},
        'actionable_scope': ['Preserve PS1 Gamma and lawful tested/fixed/submit contract. The observed differences motivate prospectively distinct R_code and R_joint endpoints in v052, not retrospective scoring or bypassing ownership/fix prerequisites.',
            'Repeated exact reads and procedural actions are measurable resource consumers, not automatically removable waste. No budget/context change is inferred.',
            'All six CAL2 bridge tasks remain predeclared; this audit selects no tasks or outcomes.'],
        'limitations': ['Public-test passing unsubmitted candidates were not privately or finally tested.',
            'Absent public tests do not prove the final tree was wrong.', 'Failed public tests do not prove the model never correctly localized any defect.',
            'Semantic understanding and message-based uptake remain unknown without stronger text-level evidence.',
            'No causal gain follows from later peer uptake after the author already submitted identical code.',
            'Repeat-cost categories overlap; do not add them. Costs are full original calls, not estimated savings.'],
        'new_model_calls': 0, 'new_tokenizer_calls': 0, 'new_tests_or_acceptance': 0,
        'new_parameter_updates': 0, 'new_backward_calls': 0, 'old_F_guard_or_report_modified': False}
    target = ROOT / 'docs/experiments/software-bridge-v052-hold-process-audit.json'
    if target.exists():
        raise FileExistsError(str(target))
    target.write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps({'report': ref(target), 'process_classes': report['no_submit_process_classes'],
                      'partner': report['partner_summary'], 'format_feedback': report['original_format_feedback_units']}))


if __name__ == '__main__':
    main()
