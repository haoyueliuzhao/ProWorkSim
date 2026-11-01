"""CPU World assembly, eligibility and default-disable checks for five contracts."""
import copy
from types import SimpleNamespace

import pytest

from proworksim import software_fixed_organization_runtime_v104 as runtime
from proworksim import software_fixed_organization_v104 as catalog
from proworksim.repository_sources_v054 import capture_repository, tree_manifest
from proworksim.software_organization_runtime_v047 import DispatchDeadline


def prepare(tmp_path, organization):
    source = tmp_path / 'public'
    source.mkdir()
    (source / 'sample.py').write_text('value = 0\n')
    manifest = capture_repository(source, tmp_path / 'snapshot', task_id='fixture__runtime104',
        problem_statement='Synthetic public source: set value to one.', source_identity={
            'instance_id': 'fixture__runtime104', 'repo': 'fixture/runtime',
            'base_commit': 'a' * 40, 'dataset_revision': 'b' * 40})
    tests = []

    def callback(**payload):
        tests.append(copy.deepcopy(payload))
        return {'passed': False, 'execution': {'executed': True,
            'input_tree_sha256': tree_manifest(payload['files'], payload['entry_metadata'])['tree_sha256']},
            'groups': {'fixture': {'status': 'failed', 'executed': True, 'passed': False, 'tests': []}}}

    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    prepared = runtime.prepare_case(manifest, tmp_path / 'world', organization_id=organization,
        max_total_tokens=5_000_000, public_test_callback=callback, deadline=deadline)
    return prepared, tests, deadline


def owner(*, fixture=True):
    adapter = SimpleNamespace(limits={'context_limit': 131072}, maximum_input_tokens=98304,
        maximum_output_tokens=32768, model='scripted-cpu-only', thinking=True)
    if fixture:
        adapter.fixture_only, adapter.external_resources_enabled = True, False
    return runtime.ProjectOwner(adapter, window_id='runtime104', identity={'policy_version': 'cpu-fixture'})


def test_catalog_contains_exact_current_five_and_rejects_legacy_variants():
    assert catalog.MEMBER_COUNTS == {'CHIEF': 4, 'PIPELINE': 3, 'REVIEW': 2, 'SPRINT': 4, 'MATRIX': 4}
    for excluded in ('PEER', 'COUNCIL', 'DIALOGUE', 'SOP'):
        with pytest.raises(ValueError):
            catalog.get_organization(excluded)
    changed = catalog.get_organization('SPRINT')
    changed['sprint_opportunities'] += 1
    with pytest.raises(ValueError):
        catalog.validate_organization(changed)


@pytest.mark.parametrize('organization', catalog.ORGANIZATION_IDS)
def test_five_real_world_assemblies_keep_private_sessions_and_one_budget(tmp_path, organization):
    prepared, tests, deadline = prepare(tmp_path, organization)
    workers = []

    class InertWorker:
        def __init__(self, member, tools, config, **kwargs):
            self.member, self.config, self.kwargs = member, copy.deepcopy(config), kwargs
            self.tool_names = {tool['name'] for tool in tools}
            workers.append(self)

        def step(self, *_args, **_kwargs):
            pytest.fail('Assembly must not dispatch a model')

    before = copy.deepcopy(prepared.world.store.load())
    runner, _, interfaces = runtime.build_runtime(owner(), prepared, tmp_path / 'runtime',
        deadline=deadline, public_initial_message=prepared.case['root_goal'],
        worker_factory=InertWorker, offline_fixture=True)
    members = prepared.case['active_roles']
    assert [worker.member for worker in workers] == members
    assert len({id(worker.kwargs['team_budget']) for worker in workers}) == 1
    assert len({str(worker.kwargs['directory']) for worker in workers}) == len(members)
    assert runner.team_budget.snapshot()['limits']['max_total_tokens'] == 5_000_000
    assert all(worker.config['max_output_tokens'] == 32768 for worker in workers)
    assert all(worker.config['max_context_tokens'] == 131072 for worker in workers)
    assert all(worker.kwargs['context_selection'] == 'full_history' for worker in workers)
    assert all(any(name.startswith('org_') for name in worker.tool_names) for worker in workers)
    assert before == prepared.world.store.load() and tests == []
    assert set(interfaces) == set(members)
    if organization == 'PIPELINE':
        assert runner.select_next()['member'] == 'member_001'
        runner.waiting['member_001'] = 0
        assert runner.select_next() is None
        assert runner.organization_blocked is True
        boundary = runtime.run_fragment(prepared, runner)
        assert boundary['closure_reason'] == 'organization_contract_blocked'
        assert boundary['opportunities'] == 0


def test_real_dispatch_requires_explicit_fixture_and_no_external_adapter(tmp_path):
    prepared, _, deadline = prepare(tmp_path, 'REVIEW')
    for label, fixture_flag, fake_owner in [('default', False, owner()), ('unmarked', True, owner(fixture=False))]:
        with pytest.raises(PermissionError, match='execution remain disabled'):
            runtime.build_runtime(fake_owner, prepared, tmp_path / label, deadline=deadline,
                public_initial_message=prepared.case['root_goal'], offline_fixture=fixture_flag)
        assert not (tmp_path / label).exists()


def test_scheduler_does_not_create_handoffs_and_rechecks_membership():
    schedule = runtime.OrganizationSchedule(catalog.get_organization('PIPELINE'))
    seen = []
    for _ in range(9):
        chosen = schedule.choose({'member_001'})
        seen.append(chosen['member'])
        schedule.consume(chosen)
    assert seen == ['member_001'] * 9
    assert schedule.snapshot()['world_actions_created_by_scheduler'] == 0
    assert schedule.snapshot()['stage_changes_caused_by_round_robin'] == 0
    assert schedule.choose(set()) is None
    with pytest.raises(ValueError):
        schedule.choose({'member_004'})
    chosen = schedule.choose({'member_002'})
    schedule.consume(chosen)
    with pytest.raises(ValueError):
        schedule.consume(chosen)
