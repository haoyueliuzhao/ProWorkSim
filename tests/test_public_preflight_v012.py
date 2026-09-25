"""Actual bound-session preflight never repairs or evaluates business values."""

import copy
import json

import pytest

from proworksim.core.world import WorldSpec
from proworksim.world_core import WorldCore


@pytest.fixture
def world(tmp_path):
    w = WorldCore.create(tmp_path / 'world', WorldSpec(
        'preflight', {'operator': {}, 'worker': {}, 'holder': {}}, applications=['files', 'sql'],
        bootstrap_grants=[{'actor_id': 'operator', 'power': 'install_project', 'scope': 'world'}]))
    package = {
        'project_id': 'P', 'goal': 'Public source-derived deliverable',
        'participants': ['worker', 'holder'],
        'objects': [
            {'alias': 'basis', 'filename': 'basis.json', 'kind': 'json', 'owner': 'holder',
             'readers': ['worker', 'holder'], 'data': {'value': 123}},
            {'alias': 'private', 'filename': 'private.json', 'kind': 'json', 'owner': 'holder',
             'readers': ['holder'], 'data': {'secret': 'private-never-preflight'}},
            {'alias': 'result', 'filename': 'result.json', 'kind': 'json', 'owner': 'worker',
             'readers': ['worker'], 'deliverable_role': 'report', 'data': {}},
        ],
        'works': [{'work_id': 'work', 'owner': 'worker', 'goal': 'Return source value',
                   'deliverables': ['result'], 'approval_policy': 'delivery_only',
                   'requirements': {'sql_project': {'query_alias': 'result'}},
                   'deliverable_contract': {'min_files': 1, 'max_files': 1,
                     'allowed_kinds': ['json'], 'allowed_roles': ['report'],
                     'required_fields': ['answer', 'sources'],
                     'content_checks': [{'kind': 'json_matches_source_field', 'path': ['answer'],
                                        'reference_path': ['sources', 'basis'],
                                        'adoption_alias': 'basis', 'source_path': ['value']}]}}],
        'grants': [{'actor_id': 'worker', 'power': power, 'subject': 'artifact', 'work_nodes': ['work']}
                   for power in ['adopt', 'execute_sql', 'create_object']],
    }
    response = w.session('operator').call('install_project', package=package)
    assert response['ok'], response
    return w


def call(w, tool, **kw):
    response = w.session('worker', 'P').call(tool, **kw)
    assert response['ok'], response
    return response['result']


def test_missing_structure_is_public_and_readonly(world):
    before = copy.deepcopy(world.state)
    result = call(world, 'preflight_submission', work_id='work', artifacts=['result'])
    assert not result['structurally_ready']
    assert {'missing_field', 'missing_source_reference', 'missing_work_adoption'} <= {x['code'] for x in result['issues']}
    assert 'private-never-preflight' not in json.dumps(result)
    for key in ['artifacts', 'adoptions', 'work_items', 'knowledge']:
        assert world.state[key] == before[key]


def test_good_structure_does_not_claim_business_correctness_or_adopt(world, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Private evaluator must not be called')
    monkeypatch.setattr('proworksim.world_core.evaluate_work_product', forbidden)
    ref = {'object_id': world.state['workspaces']['P']['basis'], 'version_id': 'v1'}
    call(world, 'write_object', alias='result', data={'answer': -987, 'sources': {'basis': ref}})
    out = call(world, 'preflight_submission', work_id='work', artifacts=['result'])
    assert {'missing_work_adoption', 'missing_file_dependency'} <= {i['code'] for i in out['issues']}
    assert world.state['adoptions'] == {}
    call(world, 'adopt', alias='basis', **ref, policy='fixed', work_ids=['work'])
    call(world, 'write_object', alias='result', data={'answer': -987, 'sources': {'basis': ref}}, dependencies=[ref])
    out = call(world, 'preflight_submission', work_id='work', artifacts=['result'])
    assert out['structurally_ready'] and out['issues'] == []
    assert '123' not in json.dumps(out)
    assert world.state['work_items']['P::work']['submissions'] == []


def test_private_selected_file_denied_before_structure_feedback(world):
    response = world.session('worker', 'P').call('preflight_submission', work_id='work', artifacts=['private'])
    assert not response['ok']
    assert 'private-never-preflight' not in json.dumps(response)


def test_reference_representation_normalized_but_wrong_exact_version_fails(world):
    oid = world.state['workspaces']['P']['basis']
    call(world, 'adopt', alias='basis', object_id=oid, version_id='v1', policy='fixed', work_ids=['work'])
    ref = {'artifact_id': oid, 'version_id': 'v2'}
    # A content reference may name a nonexistent version. Preflight reports a
    # mismatch to this work's binding, never guesses or creates the right source.
    call(world, 'write_object', alias='result', data={'answer': 0, 'sources': {'basis': ref}})
    out = call(world, 'preflight_submission', work_id='work', artifacts=['result'])
    assert 'reference_differs_from_work_adoption' in {x['code'] for x in out['issues']}
    ref['version_id'] = 'v1'
    call(world, 'write_object', alias='result', data={'answer': 0, 'sources': {'basis': ref}}, dependencies=[ref])
    assert call(world, 'preflight_submission', work_id='work', artifacts=['result'])['structurally_ready']


def test_work_argument_schema_exposes_public_obligations_not_project_ids(world):
    tools = {tool['name']: tool for tool in world.session('worker', 'P').tools()}
    assert tools['preflight_submission']['parameters']['properties']['work_id']['enum'] == ['P::work', 'work']
    assert tools['adopt']['parameters']['properties']['work_ids']['items']['enum'] == ['P::work', 'work']
    assert 'private-never-preflight' not in json.dumps(tools)


def test_actual_query_input_is_not_reported_as_empty_execution_lineage(world):
    call(world, 'create_object', alias='query_input', filename='query_input.json', work_id='work',
         data={'tables': {'values_table': {'columns': [{'name': 'amount', 'type': 'BIGINT'}], 'rows': [[4]]}}})
    call(world, 'sql_query', work_id='work', source_alias='query_input',
         sql='SELECT amount FROM values_table', output_alias='result')
    report = call(world, 'preflight_submission', work_id='work', artifacts=['result'])
    assert report['execution_lineage'][0]['actual_inputs'] == [
        {'object_id': world.state['workspaces']['P']['query_input'], 'version_id': 'v1'}]


def test_explicit_public_table_contract_catches_names_without_computing_values(world):
    # Pure public-shape contract control: no domain evaluator or expected
    # business values are supplied to this checker.
    from proworksim.public_preflight import inspect_structure
    item = {'work_item_id': 'P::work', 'requirements': {'public_structure': {
        'sql_result': {'required_paths': [['tables', 'metrics']],
                       'table_columns': {'metrics': ['customer_id', 'revenue_cents', 'order_count']}}}}}
    document = {'alias': 'result', 'object_id': 'result-id', 'version_id': 'v1',
                'kind': 'json', 'role': 'sql_result', 'dependencies': [],
                'data': {'tables': {'customer_metrics': {'columns': [], 'rows': [[1, 1000, 1]]}}}}
    wrong_name = inspect_structure(item, [document], {})
    assert {'code': 'missing_public_path', 'role': 'sql_result', 'path': ['tables', 'metrics']} in wrong_name['issues']
    document['data']['tables'] = {'metrics': {'columns': [{'name': x} for x in ['customer_id', 'revenue_cents']], 'rows': [[1, -999]]}}
    assert any(i['code'] == 'public_table_columns' for i in inspect_structure(item, [document], {})['issues'])
    document['data']['tables']['metrics']['columns'].append({'name': 'order_count'})
    document['data']['tables']['metrics']['rows'] = [[1, -999, 1]]
    assert inspect_structure(item, [document], {})['structurally_ready']
    # Existing declarations without this field remain a narrower check.
    item['requirements'] = {}
    document['data']['tables'] = {'anything': {}}
    assert inspect_structure(item, [document], {})['structurally_ready']
