"""Read-only W1 milestone diagnostics using the bound frozen evaluator source.

No world reconstruction, SQL execution, model call, or original-score rewrite.
The final score is copied verbatim; intermediate immutable build contents are
checked by the original Decimal predicate as predeclared diagnostic milestones.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess

import proworksim
from proworksim.episode import _read_boundary
from proworksim.online_rewards import _ref
from proworksim.retail_rewards import RetailEvidence
from proworksim.storage import atomic_write, digest, json_bytes, read_json
from proworksim.templates import retail_collaboration_v021 as shared
from proworksim.templates import retail_collaboration_v022 as template

VERSION = 'readonly-work-view-milestones-v0.22'


def ref(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': digest(path.read_bytes())}


def validated_evidence(folder):
    root = Path(folder) / 'episode'
    manifest = read_json(root / 'manifest.json')
    if manifest['status'] != 'closed':
        raise ValueError('Only actually closed episodes have diagnostic milestones')
    _read_boundary(root, manifest['start'])
    _read_boundary(root, manifest['end'])
    experience_path = root / manifest['experience']['path']
    if digest(experience_path.read_bytes()) != manifest['experience']['sha256']:
        raise ValueError('Original experience changed')
    case = template.case_spec(manifest['scenario']['variation']['online_case']['case_id'])
    spec = template.reward_spec(case)
    if manifest['scenario']['variation']['online_reward'] != spec:
        raise ValueError('Frozen case/reward declaration differs')
    # RetailEvidence verifies exact world receipts and consuming request evidence;
    # it does not require invoking the terminal scoring function again.
    return RetailEvidence(root, spec, {'scope': 'read-only milestone analysis'}), case


def milestone(e, event, limits):
    role, sequence = event['worker_id'], event['sequence']
    call_id = event['payload'].get('model_call_id')
    associated = [r for r in e.events if r.get('worker_id') == role and r['kind'] == 'model_call'
                  and r['payload'].get('call_id') == call_id and r['sequence'] <= sequence]
    indices = {r['payload'].get('decision_index') for r in associated}
    indices.discard(None)
    if len(indices) != 1:
        raise ValueError('World action lacks one actual model decision index')
    used = next(iter(indices))
    finished = {r['payload'].get('call_id'): r['payload'] for r in e.events
                if r.get('worker_id') == role and r['kind'] == 'model_attempt'
                and r['sequence'] < sequence and r['payload'].get('stage') == 'finished'}
    generated = sum(r.get('response', {}).get('http_status') == 200 for r in finished.values())
    return {'experience_sequence': sequence, 'worker_id': role, 'model_call_id': call_id,
            'opportunity_id': event['payload'].get('opportunity_id'),
            'world_action_id': event['payload']['response'].get('action_id'),
            'world_logical_time_after': event['payload']['response'].get('logical_time'),
            'world_command_id': event['payload']['response'].get('command_id'),
            'role_model_decisions_consumed': used, 'role_decisions_remaining': limits[role] - used,
            'role_actual_generations_so_far': generated,
            'budget_semantics': 'Actual association decision_index; includes consumed malformed/local-rejected decisions, excludes later non-generating budget-flush opportunities. Successful resident generation count separately stated.'}


def one(row, run_root):
    folder = run_root / f"slot-{row['slot']}"
    e, case = validated_evidence(folder)
    policy_limits = {r: p['config']['budget']['max_decisions'] for r, p in e.manifest['policies'].items()}
    builds, submissions = [], []
    for event in e.successful:
        payload = event['payload']
        if event['worker_id'] != 'implementer':
            continue
        if payload['action'] == 'sql_build':
            result = payload['response']['result']
            target = _ref(result.get('reference'))
            passed = False
            if target:
                version = e.state['artifacts'][target[0]]['versions'][target[1]]
                provenance = version.get('execution_provenance', {})
                document = e.document(target)
                sources = document.get('sources', {})
                authentic = (provenance.get('kind') == 'sql_build' and provenance.get('work_id') == template.WORK
                             and provenance.get('requirement_version') == e.item['requirement_version']
                             and provenance.get('source_references') == sources)
                passed = bool(authentic and result.get('execution_status') == 'success'
                              and e.applicable_basis(_ref(sources.get('basis'))) and e.check_document(document))
            builds.append({**milestone(e, event, policy_limits), 'reference': list(target) if target else None,
                           'execution_status': result.get('execution_status'), 'independent_content_correct': passed})
        elif payload['action'] == 'submit':
            sid = payload['response']['result']['submission_id']
            sub = next(s for s in e.item['submissions'] if s['submission_id'] == sid)
            quality = shared._quality(e, sub)
            submissions.append({**milestone(e, event, policy_limits), 'submission_id': sid,
                                'artifact_versions': sub['artifact_versions'], 'independent_content_correct': bool(quality['passed'])})
    judgments = shared._judgments(e)
    valid_judgments = []
    for judgment in judgments:
        if judgment['valid']:
            event = next(r for r in e.successful if r['sequence'] == judgment['sequence'])
            valid_judgments.append({**milestone(e, event, policy_limits), 'decision': judgment['action'],
                                    'submission_id': judgment['submission_id'], 'issue_id': judgment['issue_id']})
    attempts = [r['payload'] for r in e.events if r['kind'] == 'model_attempt' and r['payload'].get('stage') == 'finished']
    classifications = Counter(str(r.get('response', {}).get('http_status')) for r in attempts)
    flush = [r for r in e.events if r['kind'] == 'model_boundary_error'
             and r['payload'].get('status') == 'model_budget_exhausted'
             and 'max_decisions' in r['payload'].get('limits', []) and not r['payload'].get('model_call_id')]
    formats = [r for r in e.events if r['kind'] == 'model_format_feedback']
    terminal_role_budgets = {}
    for role, cap in policy_limits.items():
        used = max((event['payload'].get('decision_index', 0) for event in e.events
                    if event.get('worker_id') == role and event['kind'] == 'model_call'), default=0)
        terminal_role_budgets[role] = {'model_decisions_consumed': used, 'remaining_declared_decisions': cap - used,
                                       'non_generating_flush_opportunities': sum(event.get('worker_id') == role for event in flush)}
    return {'slot': row['slot'], 'case_id': row['case_id'], 'arm': row['arm'],
            'original_assessment_ref': ref(folder / 'assessment.json'),
            'original_reward': row['assessment']['reward'], 'original_completed': row['assessment']['completed'],
            'first_correct_build': next((r for r in builds if r['independent_content_correct']), None),
            'first_fixed_submission': submissions[0] if submissions else None,
            'first_correct_fixed_submission': next((r for r in submissions if r['independent_content_correct']), None),
            'first_supported_formal_judgment': valid_judgments[0] if valid_judgments else None,
            'all_current_build_diagnostics': builds, 'all_current_fixed_submissions': submissions,
            'all_formal_judgment_diagnostics': judgments, 'role_decision_limits': policy_limits,
            'resident_attempt_status_counts': dict(classifications),
            'length_or_format_feedbacks': len(formats), 'non_generating_budget_flush_opportunities': len(flush),
            'terminal_opportunities': e.manifest['termination'].get('opportunities'),
            'terminal_role_budgets': terminal_role_budgets,
            'role_stops': e.manifest['termination'].get('role_stops'),
            'model_and_rng_guards': {k: row.get('evaluation_guard', {}).get(k) for k in ('learning_unchanged', 'rng_restored_exactly')},
            'prefix_excluded': True, 'episode_ref': ref(folder / 'episode/manifest.json'),
            'experience_ref': ref(folder / 'episode' / e.manifest['experience']['path'])}


def main(run_root, source_root, output, *, allow_partial=False):
    run_root, source_root, output = Path(run_root).resolve(), Path(source_root).resolve(), Path(output)
    if output.exists():
        raise ValueError('Diagnostic output must be new; never replace original scores')
    if Path(proworksim.__file__).resolve().parents[2] != source_root:
        raise ValueError('Set PYTHONPATH to the actual frozen source/src before invoking this reporter')
    report = read_json(run_root / 'report.json')
    commit = subprocess.check_output(['git', '-C', str(source_root), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != report['source_before']['code_commit']:
        raise ValueError('Frozen evaluator source commit differs from the original execution')
    if subprocess.check_output(['git', '-C', str(source_root), 'status', '--porcelain', '--untracked-files=no'], text=True).strip():
        raise ValueError('Frozen evaluator source has tracked modifications')
    progress = read_json(run_root / 'progress.json')
    if not allow_partial and (report['status'] == 'evaluating' or any(r['status'] != 'closed' for r in progress)):
        raise ValueError('Use explicit --allow-partial for a closed-subset snapshot')
    rows = [one(row, run_root) for row in progress if row['status'] == 'closed']
    result = {'version': VERSION, 'scope': 'New predeclared read-only CPU milestone diagnostics on actual closed history; no model generation, SQL rerun, terminal score replacement or learning.',
              'status': 'closed_subset_snapshot' if report['status'] == 'evaluating' else 'terminal_snapshot',
              'run_report_ref': ref(run_root / 'report.json'), 'progress_ref': ref(run_root / 'progress.json'),
              'frozen_source_root': str(source_root), 'frozen_source_commit': commit,
              'frozen_predicate_refs': [ref(Path(proworksim.__file__).resolve().parent / name) for name in ['retail_rewards.py', 'domains/retail_work.py', 'templates/retail_collaboration_v021.py', 'templates/retail_collaboration_v022.py']],
              'rows': rows, 'model_calls': 0, 'gpu_calls': 0,
              'first_fixed_submission_definition': 'First actual current-episode submit regardless of correctness; correctness and first correct fixed submission are separate.',
              'first_correct_build_definition': 'Earliest actual current-episode immutable successful sql_build whose own exact sources satisfy the frozen Decimal content check; not selected using final-score success or terminal latest version.',
              'opportunity_definition': 'Role decision_index linked to the actual action, remaining=declared role policy cap-index. Successful generations and non-generating tail flush are separately counted.'}
    atomic_write(output, json_bytes(result))
    print(json.dumps({'output': str(output), 'closed': len(rows), 'milestones': [{'slot': r['slot'], 'build': r['first_correct_build'] and r['first_correct_build']['experience_sequence'], 'submit': r['first_fixed_submission'] and r['first_fixed_submission']['experience_sequence'], 'judgment': r['first_supported_formal_judgment'] and r['first_supported_formal_judgment']['experience_sequence']} for r in rows]}))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--allow-partial', action='store_true')
    args = parser.parse_args()
    main(args.run, args.source_root, args.output, allow_partial=args.allow_partial)
