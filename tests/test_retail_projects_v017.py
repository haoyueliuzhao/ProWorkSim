"""Necessary new domain and model-collector boundaries, not legacy regression."""
import copy
import json

import pytest

from proworksim.domains.retail_projects import evaluate_check, expected_integration
from proworksim.retail_project_collection import ProjectPort, collect_project_episode
from proworksim.storage import read_json
from proworksim.templates.retail_projects_v017 import package


def table(columns, rows):
    return {'columns': [{'name': name, 'type': 'VARCHAR' if name == 'CustomerID' else 'BIGINT'} for name in columns], 'rows': rows}


def test_p3_difference_is_fidelity_not_shared_truth_and_missing_keys_are_kept():
    left = [{'CustomerID': 'A', 'revenue_pence': 51, 'invoice_count': 2}]
    right = [{'CustomerID': 'B', 'revenue_pence': 21, 'invoice_count': 1}]
    joined = expected_integration(left, right)
    assert len(joined) == 2
    assert all(r['difference_pence'] is None and r['invoice_difference'] is None for r in joined)
    assert joined[0]['analysis_pence'] is None and joined[1]['metrics_pence'] is None
    pkg = package('P3')
    check = pkg['works'][0]['deliverable_contract']['content_checks'][0]
    from proworksim.templates.retail_projects import request
    columns = ['CustomerID', 'revenue_pence', 'invoice_count']
    sources = {'metrics': {'tables': {'metrics': table(columns, [['A', 999999, 99]])}},
               'analysis': {'tables': {'customer_analysis': table(columns, [['A', 999999, 99]])}}, 'basis': request(1)}
    expected = expected_integration([{'CustomerID': 'A', 'revenue_pence': 999999, 'invoice_count': 99}],
                                    [{'CustomerID': 'A', 'revenue_pence': 999999, 'invoice_count': 99}])
    result = {'tables': {'integration': table(list(expected[0]), [list(expected[0].values())])}}
    assert evaluate_check(check, result, sources.__getitem__)['passed']
    result['tables']['integration']['rows'][0][3] = 1
    assert not evaluate_check(check, result, sources.__getitem__)['passed']


def test_model_collection_has_real_roles_but_no_hidden_evaluator_or_auto_work(tmp_path):
    from proworksim.templates.retail_projects_v017 import build_project_case
    prepared = build_project_case('retail-projects-v17-static', tmp_path / 'prepared')
    port = ProjectPort(prepared.world.session('metrics_engineer', 'P1'))
    assert not {'evaluate', 'assess', 'shell', 'bash'} & {t['name'] for t in port.tools()}
    assert not port.call('assess')['ok']
    scenario = prepared.scenario
    assert scenario['variation']['project_case']['target_policy_edition'] == 1
    assert not scenario['events']
    initial = copy.deepcopy(prepared.world.state)
    assert all(not w['submissions'] for w in initial['work_items'].values())
    assert not any(v.get('execution_provenance') for a in initial['artifacts'].values() for v in a['versions'].values())
    assert read_json(tmp_path / 'prepared/preparation.json')['preparation_credit'] is False


@pytest.mark.parametrize('harness', ['native_v15', 'openhands_v16'])
def test_four_role_collection_records_no_automatic_work(tmp_path, harness):
    if harness == 'openhands_v16':
        pytest.importorskip('openhands.sdk')
    class FakeOwner:
        recipe = {'temperature': 0.7, 'max_output_tokens': 128, 'max_length': 16384}

        def __init__(self):
            self.transport = self
            self.calls = 0

        def freeze_identity(self):
            return {'policy_version': 'fake-unchanged', 'fixture': True}

        def complete(self, request, *, timeout_seconds):
            self.calls += 1
            body = {'id': f'fake-{self.calls}', 'model': 'offline-fixture', 'actor_identity': self.freeze_identity(),
                    'choices': [{'message': {'role': 'assistant', 'content': None,
                         'tool_calls': [{'id': f'done-{self.calls}', 'type': 'function',
                                         'function': {'name': 'staff_done', 'arguments': '{"reason":"fixture stop"}'}}]},
                                 'finish_reason': 'tool_calls'}],
                    'usage': {'prompt_tokens': 2, 'completion_tokens': 2, 'total_tokens': 4},
                    'token_trace': {'input_ids': [11, 12], 'output_ids': [21, 22],
                                    'behavior_logprobs': [-0.1, -0.2], 'fixture_only': True}}
            return {'http_status': 200, 'body': body, 'raw_body': json.dumps(body)}
    owner = FakeOwner()
    result = collect_project_episode(owner, 'retail-projects-v17-static', tmp_path / 'model-fixture', harness=harness)
    assert owner.calls == 4
    assert result['assessment']['eligible'] is True and result['assessment']['reward'] == 0
    runtime = read_json(tmp_path / 'model-fixture/runtime.json')
    assert set(runtime['roles']) == {'P0', 'P1', 'P2', 'P3'}
    assert runtime['actions'] == 0
    assert all(r['status'] == 'completed' for r in runtime['roles'].values())
    assert result['model_identity'] == owner.freeze_identity()
    from proworksim.storage import digest, json_bytes
    startup = read_json(tmp_path / 'model-fixture/initial-workers.json')
    assert digest(json_bytes(startup)) == result['diagnostics']['initial_worker_snapshot_sha256']


def test_sdk_done_worker_handles_actual_new_obligation_without_budget_reset(tmp_path):
    pytest.importorskip('openhands.sdk')
    from proworksim.experience import ExperienceRecorder, capture_port
    from proworksim.harness_port import HarnessPort
    from proworksim.harness_runtime import SDKStaffRuntime
    from proworksim.harness_sdk import HarnessWorker
    from proworksim.retail_project_collection import reactivate_new_obligation
    from proworksim.templates.retail_projects_v017 import build_project_case
    from test_harness_sdk_v016 import CONFIG, FixtureTransport, call

    prepared = build_project_case('retail-projects-v17-change', tmp_path / 'case')
    recorder, holder, captured = ExperienceRecorder(), {}, []
    base = capture_port(ProjectPort(prepared.world.session('metrics_engineer', 'P1')), captured)
    port = HarnessPort(base, 'P1', project_id='P1',
        public_sink=lambda kind, payload: recorder.record(kind, payload, worker_id='P1'),
        world_sink=lambda payload, association: holder['runtime'].record_world_call('P1', payload, association),
        harness_sink=lambda payload, association: holder['runtime'].record_harness_call('P1', payload, association))
    transport = FixtureTransport([call('work_note', {'key': 'retained', 'text': 'private-note-stays'}, 'note'),
                                  call('staff_done', {'reason': 'original duty finished'}, 'first-done'),
                                  call('staff_done', {'reason': 'new duty observed'}, 'second-done')])
    config = {**copy.deepcopy(CONFIG), 'context_policy': 'full_history',
              'budget': {**CONFIG['budget'], 'max_decisions': 3, 'max_http_attempts': 3}}
    worker = HarnessWorker('P1', port.tools(), config, transport=transport,
        execute=lambda name, arguments, association: holder['runtime'].execute('P1', name, arguments, association),
        event_sink=lambda kind, payload: recorder.record(kind, payload, worker_id='P1'), directory=tmp_path / 'sdk')
    runtime = holder['runtime'] = SDKStaffRuntime({'P1': port}, {'P1': worker}, recorder=recorder)
    try:
        assert runtime.step()['status'] == 'running'
        assert runtime.step()['status'] == 'completed'
        before = worker.snapshot()
        assert before['meter']['decisions'] == 2 and before['done']
        revised = prepared.world.session('operator', 'P1').call('revise', work_id='P1::build',
            updates={'goal': 'A declared new client obligation is now assigned'}, reason='CPU new-obligation control')
        assert revised['ok']
        from proworksim.core.work import current_id
        new = current_id(prepared.world.state, 'P1::build')
        assert new != 'P1::build'
        reactivate_new_obligation(runtime, 'P1', 'P1::build', new)
        resumed = worker.snapshot()
        assert resumed['conversation_id'] == before['conversation_id']
        assert resumed['meter'] == before['meter'] and resumed['done'] is None
        assert port.notes == {'retained': 'private-note-stays'}
        assert runtime.step()['status'] == 'completed'
        assert worker.snapshot()['meter']['decisions'] == 3
        assert len(transport.requests) == 3
        text = json.dumps(transport.requests[-1], ensure_ascii=False)
        assert 'environment_new_obligation' in text and new in text and 'private-note-stays' in text
        assert len([e for e in recorder.events if e['kind'] == 'new_obligation_reactivation']) == 1
        assert not any(r['kind'] == 'tool_call' for r in captured)
    finally:
        worker.close()
