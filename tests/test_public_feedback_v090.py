import copy

from proworksim import software_benchmark_public_feedback_v090 as feedback
from proworksim import software_benchmark_native_control_v090 as control


def response(text, index=1, *, command='python -m pytest', code=0):
    return {'id': index, 'type': 'observation', 'tool': 'terminal',
        'observation': {'content': [{'type': 'text', 'text': text}], 'is_error': False,
            'exit_code': code, 'timeout': False, 'command': command, 'metadata': {'exit_code': code}},
        'llm_content': [{'type': 'text', 'text': text + '\nFull output: /tmp/native-output.txt'}]}


def test_public_failure_zero_collection_and_pipeline_are_not_false_success():
    examples = [('FAILED (failures=1)\nRan 1 test in 0.004s', 'failure_reported'),
        ("ModuleNotFoundError: No module named 'db'\nRan 1 test\nFAILED (errors=1)", 'import_or_collection_error'),
        ('Ran 0 tests in 0.000s\nOK', 'zero_tests_observed'),
        ('collected 0 items\nno tests ran', 'zero_tests_observed'),
        ('Ran 47 tests in 0.410s\nOK', 'success_reported_in_visible_output'),
        ('tests started; output cut here', 'no_conclusive_test_summary')]
    for text, expected in examples:
        status = feedback.public_test_status('python runtests.py module 2>&1 | head -50', response(text))
        assert status['kind'] == expected
        assert status['test_process_exit_code'] is None
        assert status['official_correctness_inferred'] is False
        assert status['shell_exit_code'] == 0


def test_identical_empty_search_notifies_once_without_rejecting_or_claiming_source_identity():
    monitor = feedback.PublicExecutionFeedback()
    action = {'command': 'grep -rn dirty /testbed/source | head -50'}
    notes = []
    originals = []
    for i in range(1, 5):
        raw = response('\x1b[?2004l\x1b[?2004h', i, command=action['command'])
        originals.append(copy.deepcopy(raw))
        projected = monitor.observe('terminal', action, raw)
        assert raw == originals[-1]
        assert projected['response']['observation'] == raw['observation']
        notes.extend(projected['events'])
    repeated = [event for event in notes if event['kind'] == 'repeated_public_result']
    assert len(repeated) == 1
    assert repeated[0]['same_source_revision_proved'] is False
    assert repeated[0]['command_rejected'] is False
    saved = monitor.read_observation(1)
    saved['llm_content'].clear()
    assert monitor.read_observation(1) == originals[0]


def test_test_repeat_requires_trusted_before_and_after_revision_and_changed_revision_is_not_same():
    monitor = feedback.PublicExecutionFeedback()
    action = {'command': 'python runtests.py model_inheritance --noinput'}
    records = []
    for i, before, after in [(1, 'tree-a', 'tree-a'), (2, 'tree-a', 'tree-a'),
                              (3, 'tree-b', 'tree-c')]:
        raw = response(f'Ran 47 tests in 0.{410+i}s\nOK', i, command=action['command'])
        records.append(monitor.observe('terminal', action, raw, revision_before=before, revision_after=after))
    assert records[1]['events'][0]['same_source_revision_proved'] is True
    assert records[2]['events'][0]['same_source_revision_proved'] is False
    assert 'completion requirement' in records[1]['response']['llm_content'][-1]['text']


def test_output_filter_variants_recall_existing_summary_without_claiming_execution_equivalence():
    monitor = feedback.PublicExecutionFeedback()
    base = 'cd /testbed/tests && python runtests.py model_inheritance --noinput 2>&1'
    first, second, third = [monitor.observe('terminal', {'command': cmd},
        response('Ran 47 tests in 0.410s\nOK', i, command=cmd))
        for i, cmd in enumerate((base+' | tail -50', base, base+' | tail -30'), 1)]
    assert first['events'][0]['kind'] == 'public_test_status'
    repeats = [e for e in second['events'] if e['kind'] == 'repeated_public_result']
    assert len(repeats) == 1 and repeats[0]['commands_identical'] is False
    assert repeats[0]['same_source_revision_proved'] is False
    assert not third['events']
    for command in ("python -c 'print(\"| head -20\")'", 'python -m pytest | grep FAILED',
                    'python -m pytest <<EOF\ntext\nEOF', 'python $(echo runtests.py) | tail -50'):
        assert feedback.public_command_identity(command) == (command, 'exact_command')


def test_rpc_keeps_native_actions_schema_results_and_output_links_and_calls_once():
    class Native:
        def __init__(self):
            self.calls, self.transcript = [], []

        def request(self, tool, action, *, timeout_seconds=None):
            self.calls.append((tool, copy.deepcopy(action), timeout_seconds))
            raw = response('Ran 0 tests\nOK', len(self.calls), command=action['command'])
            self.transcript.append({'request': {'tool': tool, 'action': action}, 'response': raw})
            return raw

    wrapped = feedback.feedback_rpc_class(Native)()
    wrapped.public_python = '/usr/bin/python'
    action = {'command': 'python -m pytest | tail -10', 'timeout': 30}
    raw = copy.deepcopy(action)
    projected = wrapped.request('terminal', action, timeout_seconds=45)
    assert action == raw and wrapped.calls == [('terminal', raw, 45)]
    assert projected['observation'] == wrapped.transcript[0]['response']['observation']
    assert projected['llm_content'][0] == wrapped.transcript[0]['response']['llm_content'][0]
    assert projected['observation']['exit_code'] == 0
    assert len(projected['llm_content']) == 2
    assert wrapped.public_feedback.read_observation(1) == wrapped.transcript[0]['response']


def test_concise_guidance_preserves_issue_context_native_control_and_lifecycle_limits():
    from proworksim import software_benchmark_native_control_v062 as old
    problem, context = 'Original issue unchanged.', 'Only admitted public execution facts.'
    text = control.initial_message(problem, public_context=context)
    assert text == '\n\n'.join((problem, control.WORKFLOW_GUIDANCE, context))
    assert len(control.WORKFLOW_GUIDANCE) < len(old.WORKFLOW_GUIDANCE)
    assert len(control.STUCK_CORRECTION) < len(old.STUCK_CORRECTION)
    assert len(control.FINISH_REVIEW) < len(old.FINISH_REVIEW)
    assert control.run_controlled_conversation.__code__ is old.run_controlled_conversation.__code__
    assert control.create_conversation is old.create_conversation
    assert control.MAX_STUCK_CORRECTIONS == 2 and control.MAX_FINISH_REVIEWS == 1
    assert control.run_controlled_conversation.__globals__['WORKFLOW_GUIDANCE'] == control.WORKFLOW_GUIDANCE
    assert control.run_controlled_conversation.__globals__['recovery_admission'] is old.recovery_admission
