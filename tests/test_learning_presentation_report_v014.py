"""Pure saved-record diagnostics; these fixtures perform no environment work."""

import copy
import json

import pytest

from scripts.learning_presentation_report_v014 import build_report, work_diagnostics


def call(sequence, action, arguments, *, ok=True, result=None, error=None, member='implementer'):
    response = {'ok': ok, 'result': result or {}}
    if error:
        response['error'] = {'message': error}
    return {'sequence': sequence, 'kind': 'tool_call', 'worker_id': member,
            'payload': {'action': action, 'arguments': arguments, 'model_call_id': 'call-' + str(sequence), 'response': response}}


def visible_feedback(failed, later, *, include=True):
    message = {'role': 'tool', 'content': json.dumps(failed['payload']['response'])}
    return [
        {'sequence': later['sequence'] - 2, 'kind': 'model_tool_result', 'worker_id': failed['worker_id'],
         'payload': {'call_id': failed['payload']['model_call_id'], 'message': message}},
        {'sequence': later['sequence'] - 1, 'kind': 'model_attempt', 'worker_id': later['worker_id'],
         'payload': {'stage': 'finished', 'call_id': later['payload']['model_call_id'],
                     'request': {'messages': [message] if include else []}}},
    ]


def test_tool_change_is_not_obligation_repair_and_read_fixed_version_is_literal():
    failure = call(1, 'sql_build', {'work_id': 'TEAM::build'}, ok=False,
                   error="SQL input requires this work's exact adoption: basis")
    changed = call(5, 'read_alias', {'alias': 'basis'}, result={'reference': {'object_id': 'basis-object', 'version_id': 'v1'}})
    wrong = call(6, 'read_version', {}, member='reviewer', result={'reference': {'object_id': 'code-object', 'version_id': 'v1'}})
    events = [failure, *visible_feedback(failure, changed), changed, wrong]
    state = {'workspaces': {'TEAM': {'basis': 'basis-object', 'code': 'code-object'}},
             'work_items': {'TEAM::build': {'submissions': [{'artifact_versions': {'code-object': 'v2'}}]}}}
    reward = {'reward': 0, 'components': [{'term_id': 'correct_actual_build', 'achieved': False}]}
    before = copy.deepcopy((events, state, reward))
    report = work_diagnostics(events, state, reward)
    assert report['feedback_repairs'][0]['status'] == 'no_verified_obligation_repair'
    assert report['feedback_repairs'][0]['later_calls_with_actual_feedback'] == [5]
    assert report['reviewer_fixed_version_mismatches'][0]['fixed_version_id'] == 'v2'
    assert report['reviewer_fixed_version_mismatches'][0]['reference']['version_id'] == 'v1'
    assert (events, state, reward) == before


@pytest.mark.parametrize('feedback,work_id,expected', [
    (True, 'TEAM::build', 'verified_adoption_prerequisite_then_execution'),
    (False, 'TEAM::build', 'no_verified_obligation_repair'),
    (True, 'OTHER::build', 'same_operation_accepted_only'),
])
def test_adoption_repair_requires_actual_feedback_same_work_and_successful_execution(feedback, work_id, expected):
    failed = call(1, 'sql_build', {'work_id': 'TEAM::build'}, ok=False,
                  error="SQL input requires this work's exact adoption: basis")
    adopted = call(5, 'adopt', {'alias': 'basis', 'work_ids': [work_id]})
    resumed = call(9, 'sql_build', {'work_id': 'TEAM::build'}, result={'execution_status': 'success'})
    events = [failed, *visible_feedback(failed, adopted, include=feedback), adopted,
              *visible_feedback(failed, resumed, include=feedback), resumed]
    report = work_diagnostics(events, {}, {'reward': 0})
    assert report['feedback_repairs'][0]['status'] == expected
    if expected.startswith('verified'):
        assert report['feedback_repairs'][0]['evidence_sequences'] == [5, 9]


def test_context_stop_reports_unmet_outcomes_without_imputing_success():
    event = {'sequence': 7, 'kind': 'model_attempt', 'worker_id': 'reviewer',
             'payload': {'stage': 'finished', 'response': {'body': {'generation_started': False,
                'error': {'code': 'context_length_exceeded', 'prompt_tokens': 8000, 'requested_output': 512, 'context_limit': 8192}}}}}
    report = work_diagnostics([event], {}, {'components': [{'term_id': 'correct_review_decision', 'achieved': False}]})
    assert report['context_stops'][0]['final_unmet_terms'] == ['correct_review_decision']
    assert report['context_stops'][0]['generation_started'] is False


def test_no_final_comparison_is_emitted_for_running_inputs(tmp_path):
    root = tmp_path / 'ongoing'
    (root / 'online').mkdir(parents=True)
    (root / 'online/report.json').write_text('{"status":"running"}')
    with pytest.raises(ValueError, match='has not completed'):
        build_report({'running': root})
