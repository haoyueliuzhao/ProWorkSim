"""Necessary CPU world controls: no API, Docker or actual test process."""
from __future__ import annotations

import copy
import json

from proworksim import software_benchmark_tooling_v117 as tooling
from proworksim.repository_sources_v054 import capture_repository
from proworksim.software_benchmark_public_tests_v110 import VERSION as SELECTION_VERSION
from proworksim.software_organization_runtime_v047 import DispatchDeadline


def fixture(tmp_path):
    source = tmp_path/'public'
    (source/'pkg').mkdir(parents=True)
    (source/'protected').mkdir()
    (source/'protected/read.py').write_text('protected = 1\n')
    (source/'sample.py').write_text('first = 1\nrepeat\nrepeat\n')
    for index in range(85):
        (source/'pkg'/f'file{index:03}.py').write_text('value = 1\n')
    (source/'pkg2').mkdir()
    (source/'pkg2/not_under_pkg.py').write_text('other = 1\n')
    task = 'fixture__tooling117'
    manifest = capture_repository(source, tmp_path/'snapshot', task_id=task,
        problem_statement='Synthetic issue, no real benchmark task.',
        source_identity={'instance_id': task, 'repo': 'fixture/tooling',
            'base_commit': 'a'*40, 'dataset_revision': 'b'*40},
        file_policy={'readonly_prefixes': ['protected']})
    entry = {'version': 'v064-repository-public-test-entry-r1', 'instance_id': task,
        'argv': ['/scripted/python', '-m', 'pytest'], 'cwd': '/testbed',
        'timeout_seconds': 600, 'hidden_material_used': False}
    calls = []

    def callback(*, files, entry_metadata, request):
        calls.append(copy.deepcopy(request))
        return {'passed': True, 'execution': {'executed': True,
            'input_tree_sha256': request['tree_sha256'],
            'argv': entry['argv'], 'public_test_selection': request['public_test_selection'],
            'public_test_selection_revision': SELECTION_VERSION,
            'actual_test_processes': 0, 'fixture_only': True},
            'groups': {'public_repository_tests': {'status': 'passed', 'executed': True,
                'passed': True, 'output': 'scripted\n'*1200,
                'tests': [{'test_id': 'scripted', 'passed': True}]}},
            'repository_collection_errors': []}

    prepared = tooling.prepare_case(manifest, tmp_path/'prepared', max_total_tokens=5_000_000,
        public_test_callback=callback, deadline=DispatchDeadline(soft_seconds=21600, hard_seconds=23400),
        public_test_entry=entry)
    port = tooling.SoftwareCollaborationPort(
        prepared.world.session(tooling.MEMBERS[0], tooling.PROJECT), tooling.MEMBERS[0])
    return prepared, port, calls


def call(port, tool, **arguments):
    result = port.call(tool, **arguments)
    assert result['ok'], result
    return result['result']


def rejected(port, tool, code, **arguments):
    result = port.call(tool, **arguments)
    assert result['ok'] is False, result
    assert result['error']['rejection']['code'] == code, result
    return result['error']['rejection']['context']


def test_real_navigation_separates_directory_patch_identity_and_stale_cursors(tmp_path):
    prepared, port, calls = fixture(tmp_path)
    assert prepared.source_provider.runner.world is prepared.world
    schemas = {tool['name']: tool for tool in port.tools()}
    assert 'NOT a directory' in schemas['list_files']['parameters']['properties']['patch_id']['description']
    assert 'path_prefix' in schemas['list_files']['parameters']['properties']
    assert 'staff_done' in tooling.member_instruction(prepared.case)
    start = port.observe()['workspace_reference']
    for bad in ('pkg', 'p1', start['object_id'], 'none'):
        error = rejected(port, 'list_files', 'published_patch_not_found', patch_id=bad)
        assert error['automatic_source_fallback'] is False
        assert error['recovery'] == {'tool': 'list_files', 'arguments': {},
                                     'purpose': 'Explicitly inspect your current workspace instead'}
    assert port.observe()['workspace_reference'] == start
    first = call(port, 'list_files', path_prefix='pkg/')
    assert first['total_files'] == 85 and first['repository_total_files'] == 88
    rows = list(first['files'])
    page = first
    while page['next_cursor']:
        page = call(port, 'list_files', path_prefix='pkg', cursor=page['next_cursor'])
        rows.extend(page['files'])
    assert len(rows) == len({row['path'] for row in rows}) == 85
    assert all(row['path'].startswith('pkg/') for row in rows)
    assert page['complete'] is True
    rejected(port, 'list_files', 'source_cursor_invalid', path_prefix='pkg2', cursor=first['next_cursor'])
    call(port, 'write_file', path='sample.py', text='first = 2\n')
    stale = rejected(port, 'list_files', 'source_cursor_invalid', path_prefix='pkg', cursor=first['next_cursor'])
    assert stale['recovery'] == {'tool': 'list_files', 'arguments': {'path_prefix': 'pkg'}}
    patch = call(port, 'fix_patch', task_ids=[], message='Explicit fixture fixed patch')
    patch_id = patch['patch_id']
    fixed_first = call(port, 'list_files', patch_id=patch_id, path_prefix='pkg')
    call(port, 'write_file', path='sample.py', text='first = 3\n')
    fixed_next = call(port, 'list_files', patch_id=patch_id, path_prefix='pkg', cursor=fixed_first['next_cursor'])
    assert fixed_next['source_reference'] == fixed_first['source_reference']
    assert call(port, 'read_file', path='sample.py', patch_id=patch_id)['text'] == 'first = 2\n'
    missing = rejected(port, 'read_file', 'source_path_not_found', path='pkg/missing.py', patch_id=patch_id)
    assert missing['recovery']['arguments'] == {'path_prefix': 'pkg', 'patch_id': patch_id}
    for prefix in ('../', '/tmp', '.git', 'pkg/../pkg2'):
        assert not port.call('list_files', path_prefix=prefix)['ok']
    assert not prepared.world.session('operator', tooling.PROJECT).call('list_files')['ok']
    assert calls == []


def test_missing_paths_unique_replace_and_readonly_never_guess_or_mutate(tmp_path):
    prepared, port, calls = fixture(tmp_path)
    before = port.observe()['workspace_reference']
    missing = rejected(port, 'write_file', 'source_path_not_found', path='new.py', text='new')
    assert missing['automatic_path_substitution'] is False
    assert missing['recovery']['arguments'] == {}
    for old, count in [('repeat', 2), ('not present', 0)]:
        error = rejected(port, 'replace_file', 'replacement_not_unique', path='sample.py', old=old, new='new')
        assert error['exact_occurrences'] == count
        assert error['source_reference'] == before
        assert error['automatic_match_selection'] is False
    assert not port.call('replace_file', path='protected/read.py', old='protected = 1', new='protected = 2')['ok']
    assert not port.call('replace_file', path='sample.py', old='', new='new')['ok']
    assert port.observe()['workspace_reference'] == before
    call(port, 'replace_file', path='sample.py', old='first = 1\nrepeat\n', new='first = 2\nrepeat\n')
    assert call(port, 'read_file', path='sample.py')['text'] == 'first = 2\nrepeat\nrepeat\n'
    assert calls == [] and not prepared.world.store.load()['projects'][tooling.PROJECT]['software']['deliveries']


def test_saved_test_pages_restart_explicitly_keep_owner_and_version_without_rerun(tmp_path):
    prepared, port, calls = fixture(tmp_path)
    report = call(port, 'run_tests')
    report_id = report['report_id']
    assert report['page']['next_cursor'] and len(calls) == 1
    before = port.observe()['workspace_reference']
    error = rejected(port, 'read_test_result', 'test_report_cursor_invalid', report_id=report_id,
                     cursor='11:invented-not-an-existing-page')
    assert error['recovery'] == {'tool': 'read_test_result', 'arguments': {'report_id': report_id}}
    assert error['test_rerun'] is False
    restored = call(port, 'read_test_result', report_id=report_id)
    assert restored['page'] == report['page']
    call(port, 'write_file', path='sample.py', text='new version\n')
    next_page = call(port, 'read_test_result', report_id=report_id, cursor=report['page']['next_cursor'])
    assert next_page['source_reference'] == before != port.observe()['workspace_reference']
    assert len(calls) == prepared.world.test_budget.snapshot()['used'] == 1
    assert not port.observe()['delivery_status']['public_test_executed']
    with prepared.world.store.lock():
        state = prepared.world.store.load()
        reports = state['projects'][tooling.PROJECT]['software']['test_reports']
        reports['foreign'] = {**copy.deepcopy(reports[report_id]), 'actor_id': 'member_002'}
        prepared.world.store.save(state)
    for bad in ('unknown', 'foreign'):
        context = rejected(port, 'read_test_result', 'test_report_not_readable', report_id=bad)
        assert 'recovery' not in context and 'cursor' not in json.dumps(context)
    assert not prepared.world.store.load()['projects'][tooling.PROJECT]['software']['deliveries']


def test_no_tool_feedback_delegates_once_preserving_response_and_other_failures():
    records = []
    class Delegate:
        def _fail(self, status, reason, **details):
            records.append((status, reason, details))
            return 'original rejection'
    class Worker(tooling.ToolFeedbackWorkerMixin, Delegate):
        pass
    worker = Worker.__new__(Worker)
    body = {'id': 'original', 'choices': [{'message': {'role': 'assistant', 'content': 'Done.'}}]}
    worker._last_body = copy.deepcopy(body)
    original_details = {'parser_failure': {'reason': tooling.NO_TOOL_REASON}, 'model_call_id': 'real-call'}
    assert worker._fail('model_format_error', tooling.NO_TOOL_REASON, **original_details) == 'original rejection'
    assert len(records) == 1 and worker._last_body == body
    assert records[-1][1] == tooling.NO_TOOL_RECOVERY
    assert records[-1][2]['parser_failure']['reason'] == tooling.NO_TOOL_RECOVERY
    assert original_details['parser_failure']['reason'] == tooling.NO_TOOL_REASON
    assert records[-1][2]['managed_tool_recovery']['automatic_retry'] is False
    worker._fail('model_budget_exhausted', 'original budget stop')
    assert records[-1] == ('model_budget_exhausted', 'original budget stop', {})
    worker._last_body['choices'][0]['message']['tool_calls'] = [{}, {}]
    worker._fail('model_format_error', tooling.NO_TOOL_REASON)
    assert records[-1] == ('model_format_error', tooling.NO_TOOL_REASON, {})


def test_six_cursor_executors_only_restore_explicit_admitted_null():
    from types import SimpleNamespace

    import pytest

    schemas = {item['name']: item['parameters'] for item in tooling.tool_definitions({})}
    class Action:
        def __init__(self, value):
            self.value = copy.deepcopy(value)
        def model_dump(self, **_):
            return copy.deepcopy(self.value)
        @classmethod
        def model_validate(cls, value):
            return cls(value)
    for name in sorted(tooling.CURSOR_TOOLS):
        required = schemas[name]['required']
        original = {field: ('sample.py' if field == 'path' else 'needle') for field in required}
        original['cursor'] = None
        receipts, dispatched = [], []
        worker = SimpleNamespace(_pending={'name': name, 'arguments': original, 'tool_call_id': 'original-call'},
            _executions=0, _emit=lambda kind, value: receipts.append((kind, value)))
        def gateway(action, conversation):
            assert action.model_dump() == original
            dispatched.append(action.model_dump())
            return 'unchanged gateway'
        executor = tooling._NullableCursorExecutor(gateway, worker, name, schemas[name])
        without = {key: value for key, value in original.items() if key != 'cursor'}
        assert executor(Action(without)) == 'unchanged gateway'
        assert dispatched == [original] and receipts[0][1]['other_arguments_changed'] is False
        with pytest.raises(ValueError):
            executor(Action({**without, 'cursor': ''}))
        with pytest.raises(ValueError):
            executor(Action({**without, 'invented_argument': True}))
        original['cursor'] = 'original-non-null-cursor'
        with pytest.raises(ValueError):
            executor(Action(without))
        assert len(dispatched) == len(receipts) == 1
