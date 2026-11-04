"""Fresh five-group assembly and source/organization closure; scripted tests only."""
import copy

import pytest

from proworksim import software_fixed_organization_world_v131 as world
from proworksim.repository_sources_v054 import capture_repository
from proworksim.software_organization_runtime_v047 import DispatchDeadline
from proworksim.storage import digest, json_bytes


def fixture(folder, group='REVIEW'):
    source = folder/'source'
    source.mkdir(parents=True)
    (source/'sample.py').write_text('value = 1\n')
    task = 'fixture__team-1'
    manifest = capture_repository(source, folder/'snapshot', task_id=task,
        problem_statement='Change value from 1 to 2 in sample.py. Synthetic CPU fixture.',
        source_identity={'instance_id': task, 'repo': 'fixture/team',
                         'base_commit': 'a'*40, 'dataset_revision': 'b'*40})
    entry = {'version': 'v064-repository-public-test-entry-r1', 'instance_id': task,
        'argv': ['/scripted/python', '-m', 'pytest'], 'cwd': '/testbed',
        'timeout_seconds': 600, 'hidden_material_used': False}
    calls = []
    def callback(*, files, entry_metadata, request):
        calls.append(copy.deepcopy(request))
        passed = files['sample.py'] == 'value = 2\n'
        counts = {'collected': 1, 'passed': int(passed), 'failed': int(not passed),
                  'errors': 0, 'skipped': 0, 'xfailed': 0, 'xpassed': 0, 'tests_run': 1}
        return {'passed': passed, 'execution': {'executed': True,
            'input_tree_sha256': request['tree_sha256'], 'actor_id': request['actor_id'],
            'organization_id': group, 'managed_request_sha256': digest(json_bytes(request)),
            'argv': entry['argv'], 'public_test_selection': request['public_test_selection'],
            'public_test_selection_revision': 'v110-public-test-selection-r1',
            'validation_status': 'verified' if passed else 'failed', 'counts': counts,
            'test_evidence': {'source': 'scripted CPU fixture', 'actual_test_processes': 0}},
            'groups': {'public_repository_tests': {'passed': passed, 'executed': True,
                'status': 'passed' if passed else 'failed', 'output': 'scripted public evidence',
                'tests': [{'test_id': 'scripted', 'passed': passed}]}},
            'repository_collection_errors': []}
    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    prepared = world.prepare_case(manifest, folder/'prepared', organization_id=group,
        max_total_tokens=5_000_000, public_test_callback=callback, deadline=deadline,
        public_test_entry=entry)
    return prepared, deadline, calls


@pytest.mark.parametrize('group', world.GROUP_IDS)
def test_five_fresh_rosters_private_versions_and_original_authority(tmp_path, group):
    prepared, _, calls = fixture(tmp_path, group)
    actual = prepared.world
    members = prepared.case['active_roles']
    assert members == world.organization(group)['fixed_members']
    assert list(actual._software()['registry']) == members
    assert prepared.case['team_limits'] == {'max_decisions': 512, 'max_attempts': 512,
                                           'max_total_tokens': 5_000_000, 'max_test_runs': 512}
    assert prepared.source_provider.runner.world is actual
    assert actual._software()['organization_state']['opportunities_consumed'] == 0
    if group == 'SPRINT':
        assert prepared.case['fixed_organization']['sprint_opportunities'] == 24
    ports = {member: world.SoftwareCollaborationPort(actual.session(member, world.PROJECT), member)
             for member in members}
    expected = {item['name']: item for item in world.tool_definitions(prepared.case)}
    assert expected['read_file']['parameters']['properties']['path']['description'] == world.tooling.PATH_DESCRIPTION
    assert all({item['name']: item for item in port.tools()} == expected for port in ports.values())
    assert ports[members[0]].call('write_file', path='sample.py', text='value = 9\n')['ok']
    own = ports[members[1]].call('read_file', path='sample.py')
    assert own['ok'] and 'value = 1' in str(own['result']) and 'value = 9' not in str(own['result'])
    denied = ports[members[1]].call('submit_integration', message='Cannot bypass designated deliverer')
    assert denied['ok'] is False and actual._software()['deliveries'] == []
    assert calls == []
