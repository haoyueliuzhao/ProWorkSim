"""CPU-only admission counterexamples; no execution of old or new episodes."""
import copy
import hashlib
from pathlib import Path

import pytest

from proworksim.storage import digest
from scripts import software_organization_resume_admission_v045 as admission


def plan_fixture():
    units = admission.assignments()
    return {'assignments': units, 'cases': {worker: [
        {**{k:u[k] for k in ('case_id', 'condition', 'first_member')},
         'team_limits': dict(admission.TEAM_LIMITS)} for u in rows] for worker, rows in units.items()}}


def test_remaining_inventory_removes_only_original_first_slot_without_reordering():
    plan = plan_fixture()
    before = copy.deepcopy(plan)
    remaining = admission.remaining_inventory(plan)
    assert plan == before
    assert len([u for rows in remaining.values() for u in rows]) == 23
    for worker, rows in remaining.items():
        assert rows == plan['assignments'][worker][1 if worker == admission.FIRST_BLOCK else 0:]
    assert admission.budget_caps()['unused_old_tokens'] == 412110
    assert admission.budget_caps()['combined'] == {
        'decisions': 2951, 'attempts': 2951, 'total_tokens': 11587890, 'run_tests': 738}
    assert admission.budget_caps()['transfer_old_unused'] is False


@pytest.mark.parametrize('change', ['seed', 'order', 'budget', 'case'])
def test_remaining_inventory_rejects_sample_or_protocol_changes(change):
    plan = plan_fixture()
    worker = 'block-r1-s0'
    if change == 'seed':
        plan['assignments'][worker][0]['sampling_seed'] += 1
    elif change == 'order':
        plan['assignments'][worker].reverse()
    elif change == 'budget':
        plan['cases'][worker][0]['team_limits']['max_total_tokens'] += 412110
    else:
        plan['cases'][worker][0]['condition'] = 'S1'
    with pytest.raises(ValueError):
        admission.remaining_inventory(plan)


def source_fixture(tmp_path, monkeypatch):
    path = tmp_path / 'src/model.py'
    path.parent.mkdir()
    content = b'# frozen model-visible code\n'
    path.write_bytes(content)
    sha = hashlib.sha256(b'src/model.py' + content).hexdigest()
    monkeypatch.setattr(admission, 'ORIGINAL_TREE', sha)
    for name in admission.ALLOWED_NEW_CODE:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_text('# host addition\n')
    return {'source_files': {'src/model.py': digest(content)}, 'source': {'source_tree_sha256': sha}}


def test_source_reuse_requires_exact_original_bytes_and_only_declared_additions(tmp_path, monkeypatch):
    plan = source_fixture(tmp_path, monkeypatch)
    assert admission.source_audit(plan, tmp_path)['all_prior_bytes_unchanged'] is True
    (tmp_path / 'src/model.py').write_text('# visible mutation\n')
    with pytest.raises(ValueError, match='original plan source bytes'):
        admission.source_audit(plan, tmp_path)


def test_source_reuse_rejects_undeclared_new_dependency(tmp_path, monkeypatch):
    plan = source_fixture(tmp_path, monkeypatch)
    (tmp_path / 'src/hidden.py').write_text('# undeclared\n')
    with pytest.raises(ValueError, match='seven declared'):
        admission.source_audit(plan, tmp_path)


def unstarted_fixture(tmp_path):
    plan = plan_fixture()
    episodes = tmp_path / admission.FIRST_BLOCK / 'actual/episodes'
    (episodes / admission.FIRST_SLOT).mkdir(parents=True)
    states = {w: {'status':'stopped', 'attempted':False, 'stop_reason':'unopened_work_paused',
                  'elapsed_gpu_seconds':0} for w in plan['assignments']}
    states[admission.FIRST_BLOCK] = {'status':'stopped', 'attempted':True, 'exit_code':0,
                                    'stop_reason':None, 'ended_at':10}
    supervisor = {'status':'closed_with_unknowns', 'ended_at':11, 'states':states}
    progress = [{'slot_id':admission.FIRST_SLOT}]
    report = {'status':'global_pause', 'rows':progress}
    return plan, supervisor, report, progress


def test_partial_suffix_directory_rejects_even_without_slot_result(tmp_path):
    args = unstarted_fixture(tmp_path)
    assert len(admission.validate_unstarted(tmp_path, *args)) == 23
    path = tmp_path / admission.FIRST_BLOCK / 'actual/episodes/org45-r0-s0-F2'
    path.mkdir()
    with pytest.raises(ValueError, match='started suffix'):
        admission.validate_unstarted(tmp_path, *args)


def test_original_running_or_second_attempted_worker_rejects(tmp_path):
    args = unstarted_fixture(tmp_path)
    args[1]['states']['block-r0-s1']['attempted'] = True
    with pytest.raises(ValueError, match='another original worker started'):
        admission.validate_unstarted(tmp_path, *args)


def review_fixture():
    formal = {'status':'closed', 'R':1, 'submitted':True, 'complete_delivery':True}
    result = {**formal, 'usage':{'attempts':7, 'total_tokens':87890}}
    denominators = {'all_saved_feedback_units':7, 'presented_in_first_actual_followup':6}
    old_feedback = {'denominators':denominators, 'feedback_records':[{'id':'feedback-1'}],
        'projection_audit':[{'actual_input':{'call_id':str(i)}, 'status':'violation',
            'issues':['old_or_missing_paged_world_interface']} for i in range(7)]}
    new_feedback = copy.deepcopy(old_feedback)
    for row in new_feedback['projection_audit']:
        row.update(status='verified', issues=[])
    old_stop = {'version':'v045-batch-stop-scope-v044r2', 'decision':'global_pause',
        'global_violations':[{'projection_violations':[str(i) for i in range(7)]}],
        'unresolved':['actual_input_verification_incomplete'], 'formal_result':formal}
    new_stop = {**old_stop, 'decision':'continue', 'global_violations':[], 'unresolved':[], 'local_context_events':[],
        **{k:False for k in ('R_used_for_scope', 'restart_current_member', 'feedback_visibility_changed', 'model_visible_Gamma_changed')},
        **{k:0 for k in ('new_model_calls', 'new_tokenizer_calls', 'new_test_or_acceptance_executions', 'new_world_actions')}}
    summary = {'version':'v045-first-slot-interface-remeasurement-r1', 'passed':True,
        'old_slot_id':admission.FIRST_SLOT, 'actual_requests':7, 'revised_projection_verified':7,
        'revised_batch_decision':'continue', 'result':formal, 'usage':result['usage'], 'feedback_denominators':denominators,
        **{k:True for k in ('original_result_fees_inputs_outputs_and_stop_files_unchanged',
            'feedback_records_and_presentations_unchanged', 'feedback_denominators_unchanged',
            'original_projection_issues_all_interface_only', 'source_delta_verified')}}
    return summary, old_feedback, old_stop, new_feedback, new_stop, result


def test_interface_only_remeasurement_keeps_old_pause_and_input_facts():
    data = review_fixture()
    original = copy.deepcopy(data)
    admission.validate_review(*data)
    assert data == original


@pytest.mark.parametrize('change', ['missing_call', 'other_issue', 'changed_input', 'denominator', 'reward', 'policy', 'resume_member'])
def test_remeasurement_rejects_unproven_or_behavior_changing_correction(change):
    data = review_fixture()
    if change == 'missing_call':
        data[3]['projection_audit'].pop()
    elif change == 'other_issue':
        data[1]['projection_audit'][0]['issues'].append('missing_feedback')
    elif change == 'changed_input':
        data[3]['projection_audit'][0]['actual_input']['call_id'] = 'replacement'
    elif change == 'denominator':
        data[3]['denominators']['all_saved_feedback_units'] = 6
    elif change == 'reward':
        data[4]['formal_result'] = {**data[4]['formal_result'], 'R':0}
    elif change == 'policy':
        data[4]['version'] = 'new_stop_scope'
    else:
        data[4]['restart_current_member'] = True
    with pytest.raises(ValueError):
        admission.validate_review(*data)


def test_existing_admission_output_is_never_overwritten(tmp_path):
    path = tmp_path / 'saved.json'
    path.write_text('original')
    with pytest.raises(ValueError, match='preserve prior receipt'):
        admission.create_admission(Path('missing'), Path('missing'), path)
    assert path.read_text() == 'original'
