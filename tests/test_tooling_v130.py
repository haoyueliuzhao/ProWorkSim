"""Small schema and saved-public-feedback controls; no real tests or model."""
import copy

import pytest

from proworksim import software_benchmark_tooling_v120 as old
from proworksim import software_benchmark_tooling_v130 as new
from proworksim.repository_sources_v054 import capture_repository
from proworksim.software_benchmark_public_tests_v110 import VERSION as SELECTION_VERSION
from proworksim.software_organization_runtime_v047 import DispatchDeadline


def mutable_paths(value):
    paths = {}
    def visit(item, path):
        if isinstance(item, (dict, list)):
            paths.setdefault(id(item), []).append(path)
            children = item.items() if isinstance(item, dict) else enumerate(item)
            for key, child in children:
                visit(child, (*path, key))
    visit(value, ())
    return [locations for locations in paths.values() if len(locations) > 1]


@pytest.mark.parametrize('case', [new.schema_inventory_case(), {}])
def test_all_schema_occurrences_independent_only_observed_description_changes(case):
    before = old.tool_definitions(case)
    after = new.tool_definitions(case)
    original = copy.deepcopy(before)
    old_read = next(tool for tool in before if tool['name'] == 'read_file')
    assert old_read['parameters']['properties']['path'] is old_read['parameters']['properties']['patch_id']
    expected = copy.deepcopy(before)
    entry = next(tool for tool in expected if tool['name'] == 'read_file')
    entry['parameters']['properties']['path'] = {
        **entry['parameters']['properties']['path'], 'description': new.PATH_DESCRIPTION}
    assert after == expected  # No other schema, rule or description changes.
    assert mutable_paths(after) == []
    read = next(tool for tool in after if tool['name'] == 'read_file')
    read['parameters']['properties']['patch_id']['description'] = 'mutation control'
    assert read['parameters']['properties']['path']['description'] == new.PATH_DESCRIPTION
    assert old.tool_definitions(case) == original
    assert new.tool_definitions(case) == expected
    assert new.ToolFeedbackWorkerMixin is old.ToolFeedbackWorkerMixin
    assert new.NullableCursorExecutor is old.NullableCursorExecutor
    assert new.canonical_arguments({'b': 1.0, 'a': None}) == old.canonical_arguments({'a': None, 'b': 1})


def test_zero_test_summary_stays_same_source_private_and_does_not_rerun(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'sample.py').write_text('value = 1\n')
    task = 'fixture__schema130'
    manifest = capture_repository(source, tmp_path / 'snapshot', task_id=task,
        problem_statement='Synthetic public fixture only.', source_identity={
            'instance_id': task, 'repo': 'fixture/schema', 'base_commit': 'a' * 40,
            'dataset_revision': 'b' * 40})
    entry = {'version': 'v064-repository-public-test-entry-r1', 'instance_id': task,
        'argv': ['/scripted/python', '-m', 'pytest'], 'cwd': '/testbed',
        'timeout_seconds': 600, 'hidden_material_used': False}
    calls = []
    counts = {key: 0 for key in ('collected', 'passed', 'failed', 'errors', 'skipped',
                                'xfailed', 'xpassed', 'tests_run')}
    evidence = {'framework': 'pytest', 'source': 'scripted structured count',
                'stdout_used_for_verdict': False}
    def callback(*, files, entry_metadata, request):
        calls.append(request)
        return {'passed': False, 'execution': {'executed': True, 'command_executed': True,
            'input_tree_sha256': request['tree_sha256'], 'validation_status': 'no_tests',
            'argv': entry['argv'], 'public_test_selection': request['public_test_selection'],
            'public_test_selection_revision': SELECTION_VERSION,
            'counts': counts, 'test_evidence': evidence},
            'groups': {'public_repository_tests': {'status': 'failed', 'executed': True,
                'passed': False, 'output': 'no tests ran\n', 'tests': []}},
            'repository_collection_errors': []}
    prepared = new.prepare_case(manifest, tmp_path / 'prepared', max_total_tokens=5_000_000,
        public_test_callback=callback, deadline=DispatchDeadline(soft_seconds=21600, hard_seconds=23400),
        public_test_entry=entry)
    world = prepared.world
    assert type(world) is new.SoftwareCollaborationWorld and prepared.source_provider.runner.world is world
    assert prepared.port_factory is new.SoftwareCollaborationPort
    port = new.SoftwareCollaborationPort(world.session(new.MEMBERS[0], new.PROJECT), new.MEMBERS[0])
    assert port.call('write_file', path='sample.py', text='value = 2\n')['ok']
    response = port.call('run_tests')
    assert response['ok'], response
    first = response['result']
    assert first['executed'] is True and first['command_executed'] is True and first['passed'] is False
    assert first['validation_status'] == 'no_tests' and first['counts'] == counts
    assert first['test_evidence'] == evidence
    saved = copy.deepcopy(world._software()['test_reports'][first['report_id']])
    second = port.call('read_test_result', report_id=first['report_id'])['result']
    assert second['validation_status'] == 'no_tests' and second['counts'] == counts
    assert second['source_reference'] == first['source_reference']
    assert world._software()['test_reports'][first['report_id']] == saved
    assert len(calls) == world.test_budget.snapshot()['used'] == 1
    denied = port.call('read_test_result', report_id='not-owned-report')
    assert denied['ok'] is False and 'counts' not in denied
    # Keep the existing contract: actual same-version testing is required,
    # rather than public passing or an invented independent acceptance.
    assert port.call('fix_patch', task_ids=[], message='Explicit synthetic zero-test evidence')['ok']
    assert port.call('submit_integration', message='Synthetic failed public verification')['ok']
    assert len(calls) == 1
