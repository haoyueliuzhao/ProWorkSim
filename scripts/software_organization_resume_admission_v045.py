"""Bind the unchanged v045 work protocol to its original 23 unopened slots.

The sole change is host measurement accepting the already declared v045
interface label. Original results, stops, costs and model-visible sources stay
immutable. This module consumes saved evidence; no projection, tokenizer,
business test, model, GPU diagnostic or training work runs here.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
from pathlib import Path

from proworksim.storage import digest, json_bytes
from scripts.run_ne_v021 import write
from scripts.software_organization_admission_v044 import EvidenceReader, reference
from scripts.software_organization_admission_v045 import source_files
from scripts.software_organization_v045 import assignments

VERSION = 'software-organization-resume-admission-v0.45'
SOURCE = Path(__file__).resolve().parents[1]
ORIGINAL_COMMIT = '757b603d3a48d003ddd8af69f154fd3e31622858'
ORIGINAL_TREE = '944e4ae925423b62af54db5c5bd1bef8c5c7f7684ed23a89a533ae4c73035163'
ORIGINAL_PLAN = 'd1db9ae8b6487792bd0e021751d0153ecdc5f1bf73800b5fc5b33e8c64f1f82b'
COST_SHA = 'd48acf9eca74b9f96ab2bbdc5c2ca3f54f3dff35220d0c98f8ed3896d50b5306'
FIRST_BLOCK = 'block-r0-s0'
FIRST_SLOT = 'org45-r0-s0-S1'
ALLOWED_NEW_CODE = frozenset({
    'scripts/measure_organization_projection_v045.py',
    'scripts/measure_organization_feedback_v045r1.py',
    'tests/test_measure_organization_projection_v045.py',
    'scripts/software_organization_resume_admission_v045.py',
    'scripts/software_organization_resume_v045.py',
    'tests/test_software_organization_resume_admission_v045.py',
    'tests/test_software_organization_resume_v045.py',
})
OLD_ACTUAL = {'decisions': 7, 'attempts': 7, 'total_tokens': 87890, 'run_tests': 2}
NEW_CAPS = {'decisions': 2944, 'attempts': 2944, 'total_tokens': 11500000, 'run_tests': 736}
COMBINED_CAPS = {'decisions': 2951, 'attempts': 2951, 'total_tokens': 11587890, 'run_tests': 738}
TEAM_LIMITS = {'max_decisions': 128, 'max_attempts': 128, 'max_total_tokens': 500000, 'max_test_runs': 32}


def require(value, reason):
    if not value:
        raise ValueError('v045 resume admission rejected: ' + reason)


def read_path(reader, path):
    ref = reference(path)
    return reader.read(ref), ref


def bind_refs(value, reader):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            reader.path(value)
        else:
            for child in value.values():
                bind_refs(child, reader)
    elif isinstance(value, list):
        for child in value:
            bind_refs(child, reader)


def budget_caps():
    require({k: OLD_ACTUAL[k] + NEW_CAPS[k] for k in OLD_ACTUAL} == COMBINED_CAPS,
            'cost upper bound arithmetic changed')
    return {'old_actual': dict(OLD_ACTUAL), 'new': dict(NEW_CAPS), 'combined': dict(COMBINED_CAPS),
        'unused_old_tokens': 412110, 'transfer_old_unused': False,
        'optional_probe_budget_authorized': False}


def remaining_inventory(plan):
    require(plan.get('assignments') == assignments(), 'original 24 identities, seeds or order changed')
    require(set(plan['cases']) == set(plan['assignments']), 'case inventory incomplete')
    for worker, units in plan['assignments'].items():
        cases = plan['cases'][worker]
        require(len(cases) == len(units), 'original cases incomplete')
        for unit, case in zip(units, cases, strict=True):
            require(all(case.get(k) == unit[k] for k in ('case_id', 'condition', 'first_member'))
                    and case.get('team_limits') == TEAM_LIMITS, 'case identity or shared budget changed')
    result = copy.deepcopy(plan['assignments'])
    require(result[FIRST_BLOCK][0]['slot_id'] == FIRST_SLOT, 'original first slot changed')
    result[FIRST_BLOCK] = result[FIRST_BLOCK][1:]
    ids = [u['slot_id'] for units in result.values() for u in units]
    require(len(ids) == len(set(ids)) == 23 and FIRST_SLOT not in ids, 'remaining inventory replays or adds work')
    return result


def source_audit(plan, source_root=SOURCE):
    root = Path(source_root).resolve()
    old, current = plan['source_files'], source_files(root)
    require(bool(old) and all(current.get(name) == sha for name, sha in old.items()),
            'original plan source bytes changed or disappeared')
    added = set(current) - set(old)
    require(added == ALLOWED_NEW_CODE, 'require only the seven declared additional host source/test files')
    src_hash = hashlib.sha256()
    for name in sorted(name for name in current if name.startswith('src/') and name.endswith('.py')):
        src_hash.update(name.encode())
        src_hash.update((root / name).read_bytes())
    require(src_hash.hexdigest() == ORIGINAL_TREE == plan['source']['source_tree_sha256'],
            'original model-visible src tree changed')
    return {'all_prior_bytes_unchanged': True, 'original_file_count': len(old),
        'original_files': dict(old), 'new_files': {name: current[name] for name in sorted(added)},
        'source_tree_sha256': src_hash.hexdigest(), 'source_files': current,
        'scope': 'Every original plan source path is byte-identical; only declared host measurement/admission/resume files are added. No old implementation is rewritten.'}


def validate_unstarted(root, plan, supervisor, report, progress):
    root = Path(root)
    require(supervisor.get('status') == 'closed_with_unknowns' and 'ended_at' in supervisor,
            'original supervisor is not terminal')
    require(set(supervisor.get('states', {})) == set(plan['assignments']), 'original worker inventory changed')
    require(sorted(p.name for p in root.glob('block-*')) == [FIRST_BLOCK], 'another original worker directory exists')
    require(report.get('status') == 'global_pause' and report.get('rows') == progress
            and [r.get('slot_id') for r in progress] == [FIRST_SLOT], 'not the exact original one-slot prefix')
    require(sorted(p.name for p in (root / FIRST_BLOCK / 'actual/episodes').iterdir()) == [FIRST_SLOT],
            'original first block contains a started suffix')
    for worker, state in supervisor['states'].items():
        require(state.get('status') == 'stopped', 'old worker is not stopped')
        if worker == FIRST_BLOCK:
            require(state.get('attempted') is True and state.get('exit_code') == 0
                    and state.get('stop_reason') is None and 'ended_at' in state, 'original worker closure changed')
        else:
            require(state.get('attempted') is False and state.get('stop_reason') == 'unopened_work_paused'
                    and state.get('elapsed_gpu_seconds') == 0, 'another original worker started')
    checks = []
    for worker, units in remaining_inventory(plan).items():
        for unit in units:
            path = root / worker / 'actual/episodes' / unit['slot_id']
            require(not path.exists() and not path.is_symlink(), 'remaining slot has a partial original launch')
            checks.append({'slot_id': unit['slot_id'], 'worker': worker, 'checked_absent_path': str(path),
                'never_started_in_original_run': True, 'replay_permitted': False})
    return checks


def validate_review(summary, old_feedback, old_stop, new_feedback, new_stop, result):
    require(summary.get('version') == 'v045-first-slot-interface-remeasurement-r1'
            and summary.get('passed') is True and summary.get('old_slot_id') == FIRST_SLOT,
            'wrong or failed first-slot remeasurement')
    for key in ('original_result_fees_inputs_outputs_and_stop_files_unchanged',
                'feedback_records_and_presentations_unchanged', 'feedback_denominators_unchanged',
                'original_projection_issues_all_interface_only', 'source_delta_verified'):
        require(summary.get(key) is True, 'remeasurement proof missing: ' + key)
    require(summary.get('actual_requests') == summary.get('revised_projection_verified') == 7
            and summary.get('revised_batch_decision') == 'continue', 'remeasured actual input coverage incomplete')
    require(old_stop.get('decision') == 'global_pause' and len(old_stop.get('global_violations', [])) == 1
            and len(old_stop['global_violations'][0].get('projection_violations', [])) == 7
            and old_stop.get('unresolved') == ['actual_input_verification_incomplete'], 'original stop evidence changed')
    require(new_stop.get('decision') == 'continue' and new_stop.get('global_violations') == []
            and new_stop.get('unresolved') == [] and new_stop.get('local_context_events') == [],
            'same batch-stop algorithm has not cleared the corrected measurement')
    expected = {key: result[key] for key in ('status', 'R', 'submitted', 'complete_delivery')}
    require(old_stop.get('formal_result') == new_stop.get('formal_result') == expected,
            'measurement changed formal result')
    require(old_stop.get('version') == new_stop.get('version') == 'v045-batch-stop-scope-v044r2',
            'batch-stop semantics changed')
    require(summary.get('result') == expected and summary.get('usage') == result['usage'],
            'remeasurement result or usage summary changed')
    require(old_feedback.get('denominators') == new_feedback.get('denominators')
            and old_feedback.get('feedback_records') == new_feedback.get('feedback_records'),
            'feedback content or denominator changed')
    require(summary.get('feedback_denominators') == old_feedback.get('denominators'),
            'remeasurement denominator summary differs')
    require(len(old_feedback.get('projection_audit', [])) == len(new_feedback.get('projection_audit', [])) == 7,
            'projection receipt must cover exactly original seven calls')
    for old, new in zip(old_feedback['projection_audit'], new_feedback['projection_audit'], strict=True):
        require(old.get('issues') == ['old_or_missing_paged_world_interface'] and new.get('status') == 'verified'
                and new.get('issues') == []
                and {k:v for k,v in old.items() if k not in {'status','issues'}}
                == {k:v for k,v in new.items() if k not in {'status','issues'}},
                'projection repair exceeds the single interface-label measurement issue')
    for key in ('R_used_for_scope', 'restart_current_member', 'feedback_visibility_changed', 'model_visible_Gamma_changed'):
        require(new_stop.get(key) is False, 'remeasurement changed episode/model-visible treatment')
    for key in ('new_model_calls', 'new_tokenizer_calls', 'new_test_or_acceptance_executions', 'new_world_actions'):
        require(new_stop.get(key) == 0, 'remeasurement performed execution work')


def build_admission(original_run, review_path, *, source_root=SOURCE):
    root, source_root = Path(original_run).resolve(), Path(source_root).resolve()
    reader = EvidenceReader()
    refs = {}
    def original(name):
        value, refs[name] = read_path(reader, root / name)
        return value
    plan = original('plan.json')
    require(plan.get('plan_sha256') == ORIGINAL_PLAN == digest(json_bytes({k:v for k,v in plan.items() if k != 'plan_sha256'}))
            and plan.get('source') == {'code_commit': ORIGINAL_COMMIT, 'code_dirty': False, 'source_tree_sha256': ORIGINAL_TREE},
            'wrong or edited original plan')
    source = source_audit(plan, source_root)
    inventory = remaining_inventory(plan)
    finish, supervisor = original('finish.json'), original('supervisor.json')
    require(finish.get('status') == 'closed_with_unknowns' and 'ended_at' in finish
            and finish.get('publication', {}).get('status') == 'pushed', 'original finish not preserved')
    report = original(FIRST_BLOCK + '/actual/report.json')
    progress = original(FIRST_BLOCK + '/actual/progress.json')
    untouched = validate_unstarted(root, plan, supervisor, report, progress)
    ep = FIRST_BLOCK + '/actual/episodes/' + FIRST_SLOT + '/'
    result = original(ep + 'slot-result.json')
    budget, guard = original(ep + 'team-budget.json'), original(ep + 'evaluation-guard.json')
    old_feedback, old_stop = original(ep + 'feedback-loop.json'), original(ep + 'batch-stop-assessment.json')
    for path in sorted((root / 'mechanism-stops').glob('*.json')):
        original(str(path.relative_to(root)))
    require(len([name for name in refs if name.startswith('mechanism-stops/')]) == 2, 'original stop records incomplete')
    require(result.get('status') == 'closed' and result.get('R') == 1 and result.get('submitted') is True
            and result.get('complete_delivery') is True, 'sole original successful delivery changed')
    actual = {k: result['usage'][k] for k in ('decisions', 'attempts', 'total_tokens')}
    actual['run_tests'] = budget['tests']['used']
    require(actual == OLD_ACTUAL and result['usage']['prompt_tokens'] == 86263
            and result['usage']['completion_tokens'] == 1627, 'original seven-call cost changed')
    require(report['rows'] == [{**plan['assignments'][FIRST_BLOCK][0], **result}], 'original published result differs')
    require(all(guard.get(k) is True for k in ('learning_unchanged', 'rng_restored_exactly',
            'software_binding_unchanged', 'actor_identity_unchanged'))
            and guard['learning_before_sha256'] == guard['learning_after_sha256']
            and guard['rng_before_sha256'] == guard['rng_after_restore_sha256'], 'original frozen evaluation guard failed')
    restored = original(FIRST_BLOCK + '/actual/common-restore.json')
    common = reader.read(plan['common'])
    require(restored.get('complete_state_exact') is True and restored['actor_steps'] == restored['critic_steps'] == 3
            and restored['state_sha256'] == plan['expected_state_sha256'] == common['state_tensor_digest']
            and restored['rng_sha256'] == common['training_rng_sha256']
            and restored['actor_identity'] == result['actor_identity'] == plan['expected_actor_identity'],
            'original complete common3/3 identity changed')
    require(report['source_before'] == report['source_after'] == plan['source']
            and report['actor_steps'] == report['critic_steps'] == 3
            and all(report.get(k) == 0 for k in ('new_actor_steps', 'new_critic_steps', 'new_backward_calls'))
            and all(result.get(k) == 0 for k in ('actor_updates', 'critic_updates', 'new_backward_calls')),
            'original worker source or zero-update state changed')
    cost_ref = {'path': str(root.parent / 'v045-final-analysis/cost-review.json'), 'sha256': COST_SHA}
    cost = reader.read(cost_ref)
    require(cost.get('final') is True and cost.get('source_identity') == plan['source']
            and [s['slot_id'] for s in cost['slots']] == [FIRST_SLOT]
            and cost['slots'][0]['usage'] == result['usage'] and cost['totals']['actual_model_calls'] == 7
            and cost['inventory']['not_started'] == 23 and cost['issues'] == [], 'original cost proof changed')
    require(all(cost['guard_summary'].get(k) is True for k in ('all_actual_workers_source_unchanged',
            'all_actual_workers_common_3_3_exact', 'all_actual_workers_profile_identity_exact',
            'all_actual_slot_rng_restored_exactly', 'all_actual_slot_usage_reconciliations_pass'))
            and cost['resource_guard_summary']['all_observed_resource_checks_pass'] is True,
            'saved cost/source/resource proof incomplete')
    bind_refs([plan['common'], plan['model_references'], plan['qualification']], reader)
    qualification = reader.read(plan['qualification'])
    require(qualification.get('passed') is True, 'original qualification did not pass')
    review_path = Path(review_path)
    if review_path.is_dir():
        review_path = review_path / 'summary.json'
    summary, summary_ref = read_path(reader, review_path)
    bind_refs(summary.get('sources', {}), reader)
    for name, expected_ref in (('old_feedback', refs[ep+'feedback-loop.json']),
                               ('old_batch_stop', refs[ep+'batch-stop-assessment.json']),
                               ('result', refs[ep+'slot-result.json']), ('budget', refs[ep+'team-budget.json'])):
        require(summary['sources'][name]['sha256'] == expected_ref['sha256']
                and Path(summary['sources'][name]['path']).resolve() == Path(expected_ref['path']),
                'corrected review refers to another original artifact: ' + name)
    controls = reader.read(summary['sources']['controls'])
    require(controls.get('passed') is True and controls.get('exit_code') == 0
            and controls.get('source_unchanged') is True, 'measurement CPU controls failed')
    bind_refs(controls.get('log'), reader)
    require(all(source['source_files'].get(k) == sha for k,sha in controls['source_files'].items()),
            'measurement controls no longer bind current sources')
    revised_feedback = reader.read(summary['revised_feedback'])
    revised_stop = reader.read(summary['revised_batch_stop'])
    validate_review(summary, old_feedback, old_stop, revised_feedback, revised_stop, result)
    for key in ('new_model_calls', 'new_native_tokenizer_calls', 'new_test_or_acceptance_executions'):
        require(summary.get(key) == 0, 'read-only review executed work: ' + key)
    output = {'version': VERSION, 'passed': True, 'original_run_root': str(root),
        'original_execution_source': plan['source'], 'original_plan': refs['plan.json'],
        'original_refs': refs, 'source_audit': source, 'source_files': source['source_files'],
        'retained_slot': {'slot_id': FIRST_SLOT, 'R': 1, 'submitted': True,
            'slot_result': refs[ep+'slot-result.json'], 'usage': result['usage'], 'run_tests': 2,
            'recollection_permitted': False},
        'original_cost_review': cost_ref, 'corrected_first_slot': {'summary': summary_ref,
            'revised_feedback': summary['revised_feedback'], 'revised_batch_stop': summary['revised_batch_stop'],
            'original_feedback': refs[ep+'feedback-loop.json'], 'original_batch_stop': refs[ep+'batch-stop-assessment.json']},
        'remaining_assignments': inventory,
        'remaining_cases': {w: plan['cases'][w][1:] if w == FIRST_BLOCK else plan['cases'][w] for w in inventory},
        'never_started_evidence': untouched, 'budget_caps': budget_caps(),
        'model_identity': {key: plan[key] for key in ('common', 'model_references', 'expected_actor_identity',
            'expected_state_sha256', 'runtime_dependency_path', 'feedback_protocol', 'batch_stop_policy')},
        'qualification_reuse': plan['qualification'],
        'bound_evidence': list(reader.checked.values()),
        'new_model_calls': 0, 'new_tokenizer_calls': 0, 'new_test_or_acceptance_executions': 0,
        'new_backward_calls': 0, 'new_world_actions': 0,
        'scope': 'Repair only the host measurement interface allowlist; preserve old global_pause and first success. Continue exactly original unopened23; model-visible Gamma, lifecycle, stop scope, budgets and acceptance are unchanged. No old unused budget transfers.'}
    output['admission_sha256'] = digest(json_bytes(output))
    return output


def create_admission(original_run, review_path, output, *, source_root=SOURCE):
    output = Path(output)
    require(not output.exists(), 'admission output already exists; preserve prior receipt')
    value = build_admission(original_run, review_path, source_root=source_root)
    write(output, value)
    return value


def validate_admission(path, *, source_root=SOURCE):
    reader = EvidenceReader()
    value, _ = read_path(reader, path)
    require(value.get('version') == VERSION and value.get('passed') is True
            and value.get('admission_sha256') == digest(json_bytes({k:v for k,v in value.items() if k != 'admission_sha256'})),
            'saved admission digest or status changed')
    rebuilt = build_admission(value['original_run_root'], value['corrected_first_slot']['summary']['path'],
                              source_root=source_root)
    require(rebuilt == value, 'saved admission differs from current unchanged evidence and declared inventory')
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('create', 'validate'))
    parser.add_argument('--original-run', type=Path)
    parser.add_argument('--review', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = (create_admission(args.original_run, args.review, args.output) if args.mode == 'create'
             else validate_admission(args.output))
    print({'passed': value['passed'], 'remaining': 23, 'admission_sha256': value['admission_sha256']})


if __name__ == '__main__':
    main()
