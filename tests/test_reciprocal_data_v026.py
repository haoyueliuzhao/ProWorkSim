"""Reciprocal carrier reachability and exact-product evidence boundaries."""

import copy

import pytest

from proworksim.episode import begin_episode, finish_episode
from proworksim.experience import ExperienceRecorder
from proworksim.storage import digest, json_bytes
from proworksim.templates import reciprocal_data_v026 as carrier


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    root = tmp_path / 'assets'
    root.mkdir()
    fields = ['InvoiceNo', 'StockCode', 'Description', 'Quantity', 'InvoiceDate',
              'UnitPrice', 'CustomerID', 'Country', 'SourceRow']
    slices = []
    for index in range(2):
        rows = [['100', 'A', 'Fixture', 2, '2011-01-02 10:00:00', 1.25, '1', 'UK', 2],
                ['100', 'B', 'Fixture', 1, '2011-01-02 10:00:00', 2.00, '1', 'UK', 3],
                ['C101', 'A', 'Fixture', -1, '2011-01-03 10:00:00', 1.25, '1', 'UK', 4],
                ['102', 'C', 'Fixture', 1, '2011-01-04 10:00:00', 0.00, '2', 'UK', 5]]
        row_counts = {'100': 2, '102': 1, 'C101': 1}
        doc = {'slice_id': f'v026-material-{index:02d}', 'fields': fields, 'rows': rows,
               'customers': ['1', '2'], 'invoice_ids': ['100', '102', 'C101'],
               'complete_invoice_rows': row_counts, 'source_xlsx_sha256': carrier.SOURCE_PIN['xlsx_sha256']}
        path = root / f'v026-material-{index:02d}.json'
        path.write_bytes(json_bytes(doc))
        slices.append({'slice_id': doc['slice_id'], 'path': path.name, 'sha256': digest(path.read_bytes()),
                       'source_rows': [2, 3, 4, 5], 'invoice_ids': doc['invoice_ids'],
                       'complete_invoice_rows': row_counts})
    pin = {'slices': slices, 'doi': 'fixture-only', 'license': 'fixture-only', 'attribution': 'Synthetic test fixture'}
    (root / 'manifest.json').write_bytes(json_bytes(pin))
    monkeypatch.setattr(carrier, 'PIN_PATH', root / 'manifest.json')
    monkeypatch.setattr(carrier, 'DEFAULT_ASSETS', root)
    return carrier.registry()


def _run(tmp_path, case, *, approve=True, read_consumer=True, forge_consumer=False, constant_consumer=False, consumer_cte=False):
    prepared = carrier.build_case(case['case_id'], tmp_path / 'case')
    world = prepared.world
    recorder = ExperienceRecorder()
    episode = tmp_path / 'episode'
    begin_episode(world, episode, experience=recorder.snapshot(), work_ids=list(carrier.WORKS.values()),
                  scenario=prepared.scenario, policies={r: {'implementation': 'RuleWitness'} for r in carrier.ROLES})

    recorder.record('public_tools', world.session('maintainer', 'TEAM').tools(), 'maintainer')

    def call(role, action, **arguments):
        response = world.session(role, 'TEAM').call(action, **arguments)
        recorder.record('tool_call', {'action': action, 'arguments': arguments, 'response': response}, role)
        assert response['ok'], response
        return response['result']

    def read(role, alias, work):
        return call(role, 'read_alias', alias=alias, work_id=work)['reference']

    demand = read('consumer', 'demand', carrier.WORKS['consumer'])
    call('consumer', 'handoff_information', route_id='demand', work_id=carrier.WORKS['maintainer'],
         handoff_key='current-demand', body='Use this exact demand.',
         reference={'object_id': demand['object_id'], 'version_id': demand['version_id']})
    call('maintainer', 'wait', ticks=1)
    fixed = {}
    for role in carrier.ROLES:
        work = carrier.WORKS[role]
        if role == 'consumer':
            call(role, 'inspect_submission', work_id=carrier.WORKS['maintainer'], submission_id=fixed['maintainer']['submission_id'])
            read(role, 'm_code', work)
        refs = []
        for alias in carrier.SOURCE_ALIASES[role]:
            ref = read(role, alias, work)
            refs.append({'object_id': ref['object_id'], 'version_id': ref['version_id']})
            call(role, 'adopt', alias=alias, object_id=ref['object_id'], version_id=ref['version_id'],
                 policy='current_applicable' if alias == 'm_result' else 'fixed', work_ids=[work])
        code, result, _ = carrier.OWN_ALIASES[role]
        program = carrier.witness_code(case, role)
        if role == 'consumer' and constant_consumer:
            # Exactly correct fixed-slice values; real SQL runs and all inputs
            # were read/adopted, but no exported relation consumes upstream data.
            program['models'][0]['sql'] = (
                "SELECT '1' AS CustomerID,450::BIGINT AS revenue_pence,1::BIGINT AS invoice_count "
                "UNION ALL SELECT '2',0::BIGINT,0::BIGINT"
            )
            program['models'].insert(0, {'name': 'unused_dependency',
                                        'sql': 'SELECT * FROM invoice_view CROSS JOIN interface_meta'})
            program['tests'] = [{'name': 'source_is_read', 'sql': 'SELECT * FROM invoice_view WHERE FALSE'}]
        elif role == 'consumer' and consumer_cte:
            source_sql = program['models'][0]['sql']
            program['models'] = [{'name': 'calculated', 'sql': source_sql},
                                 {'name': 'metrics', 'sql': 'WITH same_values AS (SELECT * FROM calculated) SELECT * FROM same_values ORDER BY CustomerID DESC'}]
        call(role, 'write_object', alias=code, data=program, dependencies=refs, work_id=work)
        built = call(role, 'sql_build', work_id=work, code_alias=code, output_alias=result,
                     input_aliases=list(carrier.SOURCE_ALIASES[role]))
        assert built['execution_status'] == 'success', built
        if role == 'consumer' and forge_consumer:
            actual = call(role, 'read_alias', alias=result, work_id=work)['data']
            call(role, 'write_object', alias=result, data=actual, dependencies=refs, work_id=work)
        fixed[role] = call(role, 'submit', work_id=work, artifacts=[code, result])
    if approve:
        work = carrier.WORKS['consumer']
        call('maintainer', 'inspect_submission', work_id=work, submission_id=fixed['consumer']['submission_id'])
        if read_consumer:
            read('maintainer', 'c_code', work)
            read('maintainer', 'c_result', work)
        call('maintainer', 'approve', work_id=work, submission_id=fixed['consumer']['submission_id'])
    finish_episode(world, episode, experience=recorder.snapshot(), termination={'status': 'completed'})
    return carrier.assess_episode(episode)


def test_pair_local_observations_and_seed_are_identical_before_information(tmp_path, catalog):
    for pair, role in [(0, 'maintainer'), (2, 'consumer')]:
        views = []
        for case in catalog['cases'][pair:pair + 2]:
            prepared = carrier.build_case(case['case_id'], tmp_path / case['case_id'])
            view = prepared.world.observe(role, 'TEAM')
            for key in ('instance_id', 'branch_id'):
                view.pop(key)
            views.append(view)
            private_alias = 'demand' if role == 'maintainer' else 'source_contract'
            refused = prepared.world.session(role, 'TEAM').call('read_alias', alias=private_alias)
            assert not refused['ok']
        assert views[0] == views[1]
        assert carrier.reward_spec(catalog['cases'][pair]) == carrier.reward_spec(catalog['cases'][pair + 1])
    assert len(catalog['slots']) == 16
    for pair in range(2):
        for repeat in range(2):
            seeds = {s['sampling_seed'] for s in catalog['slots'] if s['case_index'] // 2 == pair and s['repeat_index'] == repeat}
            assert len(seeds) == 1


def test_independent_counterfactual_changes_source_processing_not_just_labels(tmp_path, catalog):
    products = []
    for case in catalog['cases']:
        objects = {o['alias']: o['data'] for o in carrier.package(case)['objects']}
        expected = carrier.expected_products(**{a: objects[a] for a in ('raw', 'demand', 'source_contract')})
        products.append(expected)
    assert products[0]['consumer']['metrics'] != products[1]['consumer']['metrics']
    assert products[2]['consumer'] == products[3]['consumer']
    left = products[2]['maintainer']['invoice_view'][0]['amount']
    right = products[3]['maintainer']['invoice_view'][0]['amount']
    assert right == left * 100
    wrong = {'tables': {'invoice_view': {'columns': [{'name': 'wrong', 'type': 'VARCHAR'}], 'rows': []},
                        'customers': {'columns': [{'name': 'CustomerID', 'type': 'VARCHAR'}], 'rows': []},
                        'interface_meta': {'columns': [{'name': 'amount_unit', 'type': 'VARCHAR'}], 'rows': []}}}
    assert not carrier._matches(wrong, {'invoice_view': [], 'customers': [], 'interface_meta': []})


@pytest.mark.parametrize('index', range(4))
def test_complete_current_reciprocal_work_is_reachable(tmp_path, catalog, index):
    result = _run(tmp_path, catalog['cases'][index])
    assert result['eligible'], result
    assert result['completed'], result
    assert result['reward'] == 1
    assert not result['mapper']['eligible']


@pytest.mark.parametrize('options', [{'approve': False}, {'read_consumer': False}, {'forge_consumer': True}])
def test_unclosed_or_unexecuted_current_product_is_not_full_responsibility(tmp_path, catalog, options):
    result = _run(tmp_path, catalog['cases'][0], **options)
    assert result['eligible'], result
    assert not result['completed'], result
    if options.get('forge_consumer'):
        assert result['facts']['consumer_current_fixed_build'] is None
    else:
        assert result['facts']['maintainer_revalidation'] is None


def test_unchanged_witness_can_legitimately_use_runtime_unit_metadata(catalog):
    assert carrier.witness_code(catalog['cases'][2], 'consumer') == carrier.witness_code(catalog['cases'][3], 'consumer')
    public = carrier.reward_spec()
    for case in catalog['cases']:
        assert case['case_id'] not in str(public)
    assert copy.deepcopy(carrier.ROLE_TASKS) == carrier.ROLE_TASKS


def test_real_sql_constants_do_not_count_as_counterparty_execution_consumption(tmp_path, catalog):
    result = _run(tmp_path, catalog['cases'][0], constant_consumer=True)
    assert result['eligible'], result
    assert result['facts']['maintainer_current_fixed_build']
    assert not result['completed'], result
    assert result['facts']['consumer_current_fixed_build'] is None


def test_equivalent_cte_and_intermediate_model_preserve_execution_consumption(tmp_path, catalog):
    result = _run(tmp_path, catalog['cases'][0], consumer_cte=True)
    assert result['eligible'], result
    assert result['completed'], result
