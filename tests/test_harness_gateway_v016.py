"""Actual world gateway controls; fake workers below are not real SDK runs."""
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from proworksim.experience import capture_port
from proworksim.harness_port import HarnessPort
from proworksim.harness_runtime import SDKStaffRuntime
from proworksim.scenarios import initial_business_state
from proworksim.storage import digest, json_bytes
from proworksim.templates.retail_harness import build_harness_case
from proworksim.work_interface import WorkInterface

CONTROLS = []
ASSOCIATION = {'model_call_id': 'cpu-fake-call', 'model_tool_call_id': 'cpu-fake-tool', 'decision_id': 'cpu-fake-decision'}


def _sources():
    root = Path(__file__).resolve().parents[1]
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in ('src/proworksim/harness_port.py', 'src/proworksim/harness_runtime.py', __file__.removeprefix(str(root) + '/'))}


@pytest.fixture(scope='module', autouse=True)
def control_report():
    before = _sources()
    yield
    report_path = os.environ.get('PWS_HARNESS_CONTROLS_REPORT')
    if report_path:
        Path(report_path).write_text(json.dumps({
            'version': 'harness-world-gateway-controls-v0.16',
            'actual_world': True, 'model_execution': False,
            'sdk_execution': False,
            'scope': 'Actual entity-disjoint UCI development worlds through HarnessPort; SDKStaffRuntime uses explicitly fake workers. Genuine SDK Conversation/Executor controls are separate.',
            'source_before': before, 'source_after': _sources(),
            'controls': CONTROLS, 'passed_controls': len(CONTROLS),
            'world_or_assets_modified_by_private_memory': False,
            'preliminary_control_attempts': [
                {'passed': 4, 'total': 6, 'evidence': '/tmp/harness-gateway-v016-initial.json',
                 'issues': ['Test helper key argument collided with work_note key (fixture only)', 'Runtime emit incorrectly called setdefault on actual tools list before fake worker execution']},
                {'passed': 5, 'total': 6, 'evidence': '/tmp/harness-gateway-v016-second.json',
                 'issues': ['Runtime actual tools-list integration error persisted; helper fixed']},
                {'passed': 6, 'total': 7, 'evidence': '/tmp/harness-gateway-v016-third.json',
                 'issues': ['Test expected old policy_error label for deliberately repeated SDK execution; corrected runtime classifies it environment_error and retains first effect']},
            ],
        }, ensure_ascii=False, indent=2) + '\n')


@pytest.fixture
def prepared(tmp_path):
    return build_harness_case('uci-harness-f4-pair', tmp_path / 'case')


def gateway(prepared, role):
    record = {'capture': [], 'public': [], 'world': [], 'harness': []}
    base = capture_port(WorkInterface(prepared.world.session(role, 'TEAM'), role, variant='v14'), record['capture'])
    port = HarnessPort(base, role, project_id='TEAM',
                       public_sink=lambda kind, payload: record['public'].append((kind, copy.deepcopy(payload))),
                       world_sink=lambda payload, association: record['world'].append((copy.deepcopy(payload), copy.deepcopy(association))),
                       harness_sink=lambda payload, association: record['harness'].append((copy.deepcopy(payload), copy.deepcopy(association))))
    port.tools()
    port.observe()
    return port, record


def call(port, action, request_id, **arguments):
    return port.call(action, request_key=request_id, association=ASSOCIATION, **arguments)


def business_hash(prepared):
    return digest(json_bytes(initial_business_state(prepared.world)))


def edit_args(ref, *, alias='code', text='SELECT 7 AS marker', dependencies=None):
    return {'alias': alias, 'reference': ref, 'locator': ['models', 0, 'sql'],
            'new_text': text, 'dependencies': [] if dependencies is None else dependencies}


def test_private_notes_and_todos_never_change_business_facts(prepared):
    worker, records = gateway(prepared, 'implementer')
    other, _ = gateway(prepared, 'provider')
    before, commits = business_hash(prepared), len(prepared.world.state['operation_commits'])
    assert call(worker, 'work_note', 'private-note', key='working_guess', text='private-sentinel-941')['ok']
    assert call(worker, 'work_todo', 'private-todo', key='check', text='My guess is not an approval', status='done')['ok']
    visible = worker.observe()['personal_workbench']
    assert visible['notes'] == {'working_guess': 'private-sentinel-941'}
    assert visible['todos']['check']['status'] == 'done'
    assert other.observe()['personal_workbench']['notes'] == {}
    assert business_hash(prepared) == before
    assert len(prepared.world.state['operation_commits']) == commits
    assert records['world'] == []
    assert not any(r['kind'] == 'tool_call' for r in records['capture'])
    assert all(r[0]['response']['world_effect'] is False for r in records['harness'])
    CONTROLS.append({'name': 'private_memory_does_not_create_world_facts', 'passed': True,
                     'business_state_unchanged': True, 'world_calls': 0, 'private_calls': 2})


def test_history_contains_only_that_roles_actual_observations_and_returns(prepared):
    provider, provider_records = gateway(prepared, 'provider')
    implementer, _ = gateway(prepared, 'implementer')
    unseen = call(implementer, 'work_history_search', 'unseen-search', query='policy_origin', limit=5)
    assert unseen['ok'] and unseen['matches'] == []
    observed = call(provider, 'read_alias', 'actual-basis-read', alias='basis', work_id='TEAM::build')
    assert observed['ok'] and 'policy_origin' in observed['result']['data']
    before = business_hash(prepared)
    found = call(provider, 'work_history_search', 'provider-search', query='policy_origin', limit=5)
    assert found['ok'] and found['matches']
    restored = call(provider, 'work_history_read', 'provider-recall', entry_id=found['matches'][0]['entry_id'])
    entry = restored['entry']
    assert entry['kind'] == 'tool_call'
    assert entry['payload']['response'] == observed
    assert entry['payload_sha256'] == digest(json_bytes(entry['payload']))
    assert business_hash(prepared) == before
    assert call(implementer, 'work_history_search', 'isolated-search', query='policy_origin', limit=5)['matches'] == []
    assert len(provider_records['world']) == 1
    assert len([r for r in provider_records['capture'] if r['kind'] == 'tool_call']) == 1
    CONTROLS.append({'name': 'role_local_history_requires_real_observation', 'passed': True,
                     'provider_real_reads': 1, 'recall_additional_world_reads': 0,
                     'recipient_received_provider_history': False})


def test_actual_exact_edit_and_explicit_dependencies_match_world_lineage(prepared):
    port, records = gateway(prepared, 'implementer')
    code = call(port, 'read_alias', 'read-code', alias='code', work_id='TEAM::build')['result']
    data = call(port, 'read_alias', 'read-data', alias='data', work_id='TEAM::build')['result']
    dependencies = [data['reference']]
    text = 'SELECT 37 AS customer_work_marker'
    arguments = {**edit_args(code['reference'], text=text, dependencies=dependencies), 'work_id': 'TEAM::build'}
    response = call(port, 'work_replace_text', 'edit-code', **arguments)
    assert response['ok']
    new_ref = response['result']
    assert new_ref == {'object_id': code['reference']['object_id'], 'version_id': 'v2'}
    world = prepared.world
    version = world.state['artifacts'][new_ref['object_id']]['versions']['v2']
    assert version['derived_from'] == [{'artifact_id': data['reference']['object_id'], 'version_id': data['reference']['version_id']}]
    assert response['command_id'] in world.state['operation_commits']
    base_write = [r['payload'] for r in records['capture'] if r['kind'] == 'tool_call' and r['payload']['action'] == 'write_object']
    assert len(base_write) == 1
    assert base_write[0]['arguments']['dependencies'] == dependencies
    assert base_write[0]['arguments']['work_id'] == 'TEAM::build'
    work_edits = world.state['work_items']['TEAM::build']['artifact_edits']
    assert any(e['artifact_id'] == new_ref['object_id'] and e['version_id'] == 'v2' for e in work_edits)
    assert base_write[0]['arguments']['data']['models'][0]['sql'] == text
    assert base_write[0]['response'] == response
    recorded_write = [r for r in records['world'] if r[0]['action'] == 'write_object']
    assert len(recorded_write) == 1 and recorded_write[0][1] == ASSOCIATION
    assert recorded_write[0][0]['response']['command_id'] == response['command_id']
    assert records['harness'][-1][0]['response'] == response
    # Repeating the same request must not create a second edit/version.
    repeated = call(port, 'work_replace_text', 'edit-code', **arguments)
    assert repeated == response
    assert world.state['artifacts'][new_ref['object_id']]['current_version'] == 'v2'
    assert len([r for r in records['capture'] if r['kind'] == 'tool_call' and r['payload']['action'] == 'write_object']) == 1
    content = call(port, 'read_version', 'read-new-code', reference=new_ref)['result']['data']
    expected = copy.deepcopy(code['data'])
    expected['models'][0]['sql'] = text
    assert content == expected
    CONTROLS.append({'name': 'exact_edit_has_one_real_write_and_explicit_lineage', 'passed': True,
                     'new_version': 'v2', 'actual_write_calls': 1,
                     'dependency_count': 1, 'automatic_dependencies_added': 0,
                     'actual_command_id': response['command_id'], 'explicit_work_id_preserved': True})


def test_unread_wrong_alias_and_stale_bases_reject_without_extra_write(prepared):
    port, records = gateway(prepared, 'implementer')
    oid = port.latest['workspaces']['TEAM']['code']
    ref = {'object_id': oid, 'version_id': 'v1'}
    before = business_hash(prepared)
    assert not call(port, 'work_replace_text', 'unread', **edit_args(ref))['ok']
    assert business_hash(prepared) == before
    assert not records['world']
    assert call(port, 'read_alias', 'actually-read', alias='code')['ok']
    before = business_hash(prepared)
    assert not call(port, 'work_replace_text', 'wrong-alias', **edit_args(ref, alias='result'))['ok']
    assert business_hash(prepared) == before
    first = call(port, 'work_replace_text', 'first-edit', **edit_args(ref))
    assert first['ok']
    before = business_hash(prepared)
    # No new observation: a repeated stale base still must not overwrite v2.
    stale = call(port, 'work_replace_text', 'new-request-old-base', **edit_args(ref, text='SELECT 8 AS stale_marker'))
    assert not stale['ok'], 'Stale base created another version before a fresh observation'
    assert business_hash(prepared) == before
    assert prepared.world.state['artifacts'][oid]['current_version'] == 'v2'
    assert len([r for r in records['capture'] if r['kind'] == 'tool_call' and r['payload']['action'] == 'write_object']) == 1
    version = prepared.world.state['artifacts'][oid]['versions']['v2']
    assert version['derived_from'] == []
    CONTROLS.append({'name': 'unread_wrong_alias_and_stale_base_fail_closed', 'passed': True,
                     'actual_write_calls': 1, 'explicit_empty_dependencies_preserved': True})



def test_stale_base_after_another_managed_command_never_overwrites(prepared):
    port, records = gateway(prepared, 'implementer')
    old = call(port, 'read_alias', 'old-code-read', alias='code')['result']
    changed = copy.deepcopy(old['data'])
    changed['models'][0]['sql'] = 'SELECT 91 AS another_managed_edit'
    other = prepared.world.session('implementer', 'TEAM').call(
        'write_object', request_key='another-managed-command', alias='code',
        data=changed, dependencies=[], work_id='TEAM::build')
    assert other['ok'] and other['result']['version_id'] == 'v2'
    before = business_hash(prepared)
    rejected = call(port, 'work_replace_text', 'stale-external-base', **edit_args(old['reference']))
    assert not rejected['ok']
    assert business_hash(prepared) == before
    assert prepared.world.state['artifacts'][old['reference']['object_id']]['current_version'] == 'v2'
    assert not any(r['kind'] == 'tool_call' and r['payload']['action'] == 'write_object' for r in records['capture'])
    mechanical = [r for r in port.history if r['kind'] == 'editor_current_metadata']
    assert mechanical and mechanical[-1]['payload']['included_in_model_input'] is False
    CONTROLS.append({'name': 'intervening_world_edit_invalidates_old_harness_base', 'passed': True,
                     'external_version_preserved': 'v2', 'harness_write_calls': 0,
                     'fresh_metadata_not_claimed_as_model_input': True})


def test_provider_profile_cannot_gain_edit_rights(prepared):
    provider, records = gateway(prepared, 'provider')
    definition_names = {d['name'] for d in provider.tools()}
    assert 'work_replace_text' not in definition_names and 'write_object' not in definition_names
    result = call(provider, 'read_alias', 'provider-code-read', alias='code')
    assert result['ok']
    before = business_hash(prepared)
    denied = call(provider, 'work_replace_text', 'provider-write-attempt', **edit_args(result['result']['reference']))
    assert not denied['ok']
    assert business_hash(prepared) == before
    assert len(records['world']) == 1
    assert not any(r['kind'] == 'tool_call' and r['payload']['action'] == 'write_object' for r in records['capture'])
    CONTROLS.append({'name': 'provider_read_access_never_grants_edit_rights', 'passed': True,
                     'actual_write_calls': 0})


def test_fake_workers_runtime_one_execution_and_local_pause(prepared):
    ports, captures = {}, {}
    runtime_box = {}
    for role in ('provider', 'implementer'):
        captures[role] = []
        base = capture_port(WorkInterface(prepared.world.session(role, 'TEAM'), role, variant='v14'), captures[role])
        ports[role] = HarnessPort(base, role, project_id='TEAM',
            public_sink=lambda kind, value, r=role: runtime_box['runtime'].emit(r, kind, value),
            world_sink=lambda payload, association, r=role: runtime_box['runtime'].record_world_call(r, payload, association),
            harness_sink=lambda payload, association, r=role: runtime_box['runtime'].record_harness_call(r, payload, association))

    class FakeWorker:
        config = {'weight_identity': {'fixture': 'no_model_or_sdk'}}

        def __init__(self, role):
            self.role, self.calls = role, 0

        def snapshot(self):
            return {'explicit_fake_worker': True, 'calls': self.calls}

        def step(self, observation, *, opportunity, model_identity):
            self.calls += 1
            runtime = runtime_box['runtime']
            if self.role == 'provider':
                runtime.execute(self.role, 'staff_wait', {'reason': 'Pause this role only'}, ASSOCIATION)
            else:
                runtime.execute(self.role, 'read_alias', {'alias': 'data'}, ASSOCIATION)
                runtime.execute(self.role, 'read_alias', {'alias': 'code'}, ASSOCIATION)
            return {'kind': 'act', 'memory': self.snapshot()}

    workers = {r: FakeWorker(r) for r in ports}
    runtime = runtime_box['runtime'] = SDKStaffRuntime(ports, workers)
    first, second = runtime.step(), runtime.step()
    assert first['worker_id'] == 'provider' and first['status'] == 'worker_waiting', first
    assert second['worker_id'] == 'implementer' and second['status'] == 'environment_error'
    assert second['action_performed'] is True
    assert workers['provider'].calls == workers['implementer'].calls == 1
    assert runtime.roles['provider']['status'] == 'worker_waiting'
    assert len([r for r in captures['implementer'] if r['kind'] == 'tool_call']) == 1
    assert not any(r['kind'] == 'tool_call' for r in captures['provider'])
    events = runtime.recorder.snapshot()['events']
    for role in ports:
        for kind in ('public_tools', 'public_observation'):
            actual = [e['payload'] for e in events if e['worker_id'] == role and e['kind'] == kind]
            independently_captured = [row['payload'] for row in captures[role] if row['kind'] == kind]
            assert actual == independently_captured
    links = [e for e in events if e['kind'] == 'model_action_link']
    assert len(links) == 1 and links[0]['worker_id'] == 'implementer'
    assert links[0]['payload']['world_command_id'] in prepared.world.state['operation_commits']
    assert any(e['kind'] == 'interface_error' and 'second SDK tool' in e['payload']['message'] for e in events)
    CONTROLS.append({'name': 'fake_worker_runtime_single_execution_and_role_local_pause', 'passed': True,
                     'real_sdk_or_model': False, 'world_tool_calls': 1,
                     'second_execution_rejected': True, 'other_role_cancelled': False,
                     'rejection_is_environment_error_not_business_zero': True,
                     'canonical_public_events_equal_base_capture': True})
