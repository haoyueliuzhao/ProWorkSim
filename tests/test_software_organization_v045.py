"""Finite CPU controls for new initialization and legal result round trips."""
import copy

import pytest

from proworksim import software_organization_v042 as paging
from proworksim.software_organization_v045 import (
    CASE_IDS, CONDITIONS, MEMBERS, PROJECT, TEAM_LIMITS, SoftwareCollaborationPort,
    assess_software_collaboration, build_software_collaboration_case, case_spec, material,
    member_instruction, validate_case,
)


def prepare(tmp_path, condition):
    return build_software_collaboration_case(case_spec(CASE_IDS[0], condition=condition), tmp_path / condition)


def call(world, member, name, **arguments):
    response = world.session(member, PROJECT).call(name, **arguments)
    assert response['ok'], response
    return response['result']


def test_four_new_roots_share_neutral_prose_and_unchanged_quotas_across_regimes():
    assert len(CASE_IDS) == 4
    assert CONDITIONS == ('S1', 'F2', 'O3')
    for root in CASE_IDS:
        cases = [case_spec(root, condition=c) for c in CONDITIONS]
        assert len({member_instruction(case) for case in cases}) == 1
        for case in cases:
            assert validate_case(case) == case
            assert case['team_limits'] == TEAM_LIMITS
            assert case['information_condition'] == 'shared'
            assert case['framing_condition'] == 'neutral'
            assert case['predefined_execution_tasks'] is False
            assert case['training_eligible'] is case['contribution_eligible'] is case['independent_confirmation_eligible'] is False
        changed = copy.deepcopy(cases[0])
        changed['active_roles'].append(MEMBERS[1])
        with pytest.raises(ValueError):
            validate_case(changed)
    with pytest.raises(ValueError):
        case_spec(condition='SB')
    with pytest.raises(ValueError):
        case_spec(condition='S1', first_member=MEMBERS[1])


@pytest.mark.parametrize('condition,count', [('S1', 1), ('F2', 2), ('O3', 2)])
def test_initial_world_has_exact_real_members_and_same_public_environment_facts(tmp_path, condition, count):
    p = prepare(tmp_path, condition)
    world = p.world
    state, facts = world.store.load(), world._software()
    expected = list(MEMBERS[:count])
    assert list(facts['registry']) == expected
    assert set(state['actors']) == {*expected, 'operator'}
    assert [role['actor'] for role in p.scenario['roles']] == expected
    assert set(a['owner'] for a in state['artifacts'].values()) == {*expected, 'operator'}
    assert len(state['artifacts']) == count + 1
    assert facts['tasks'] == {} and facts['deliveries'] == [] and facts['patches'] == {}
    assert state['software_events'] == []
    assert world.test_budget.snapshot()['used'] == 0
    assert p.prefix['actual_work_copy_count'] == count
    observations = [SoftwareCollaborationPort(world.session(m, PROJECT), m).observe() for m in expected]
    assert all(o['initial_diagnostics'] == observations[0]['initial_diagnostics'] for o in observations)
    assert len(observations[0]['initial_diagnostics']) == 2
    for member, observation in zip(expected, observations):
        assert observation['profile'] == 'software-organization-v0.45:' + member
        assert observation['execution_condition']['active_executors'] == expected
        assert observation['initial_diagnostic_provenance']['current_member_credit'] is False
        assert world.session(member, PROJECT).tools() == paging.TOOLS
    if condition == 'S1':
        assert all(set(share['actor_ids']) <= {MEMBERS[0]} for share in state['shares'])
        assert not world.session(MEMBERS[0], PROJECT).call('send_message', recipient=MEMBERS[1], task_id='root_goal', body='No hidden receiver')['ok']
        assert not world.session(MEMBERS[0], PROJECT).call('spawn_member', briefing='No hidden birth')['ok']
        assert set(world._software()['registry']) == {MEMBERS[0]}
        call(world, MEMBERS[0], 'create_task', task_id='chosen', description='Self-defined local work')
        call(world, MEMBERS[0], 'claim_task', task_id='chosen')
        call(world, MEMBERS[0], 'return_task', task_id='chosen', reason='Reconsider plan')
        assert world._software()['tasks']['chosen']['owner'] is None


def test_f2_retirement_keeps_condition_and_obligation_without_replacement(tmp_path):
    p = prepare(tmp_path, 'F2')
    world = p.world
    call(world, MEMBERS[1], 'create_task', task_id='owned', description='Member-chosen investigation')
    call(world, MEMBERS[1], 'claim_task', task_id='owned')
    call(world, MEMBERS[1], 'retire_member', reason='Stop voluntarily')
    assert world._software()['tasks']['owned']['owner'] == MEMBERS[1]
    response = world.session(MEMBERS[0], PROJECT).call('spawn_member', briefing='Replace retired colleague', replaces=MEMBERS[1])
    assert response['ok'] is False
    assert world._software()['case']['condition'] == 'F2'
    assert world.live_members() == [MEMBERS[0]]
    assert set(world._software()['registry']) == set(MEMBERS[:2])
    call(world, MEMBERS[0], 'claim_task', task_id='owned', reason='Take over the retained obligation')
    assert world._software()['tasks']['owned']['owner'] == MEMBERS[0]


def test_o3_live_and_cumulative_caps_are_real_and_retired_ids_never_reused(tmp_path):
    p = prepare(tmp_path, 'O3')
    world = p.world
    for expected in MEMBERS[2:4]:
        assert call(world, MEMBERS[0], 'spawn_member', briefing='Neutral current member invitation')['member_id'] == expected
    assert len(world.live_members()) == 4
    assert not world.session(MEMBERS[0], PROJECT).call('spawn_member', briefing='No fifth active member')['ok']
    for old, new in zip(MEMBERS[2:4], MEMBERS[4:6]):
        call(world, old, 'retire_member', reason='Free a live position')
        assert call(world, MEMBERS[0], 'spawn_member', briefing='New identity after a retirement', replaces=old)['member_id'] == new
    call(world, MEMBERS[4], 'retire_member', reason='No reuse of historical identity')
    assert not world.session(MEMBERS[0], PROJECT).call('spawn_member', briefing='Would exceed six births')['ok']
    assert list(world._software()['registry']) == list(MEMBERS)
    assert world.test_budget.snapshot()['used'] == 0
    for member in MEMBERS:
        assert world._software()['initial_diagnostic_assignments'][member] == list(world._software()['initial_diagnostics'])
        assert world._software()['registry'][member]['private_history_copied'] is False


def test_published_version_and_private_report_round_trip_use_new_root_and_old_pages(tmp_path):
    p = prepare(tmp_path, 'O3')
    world, author, partner = p.world, MEMBERS[0], MEMBERS[1]
    files = material(p.case['case_id'])['files']
    path = next(name for name in p.case['editable_paths'] if name != 'test_member.py')
    shared_text = files[path] + '\n# published CPU revision\n'
    call(world, author, 'write_file', path=path, text=shared_text)
    patch = call(world, author, 'fix_patch', task_ids=[], message='Explicit version chosen by member')
    call(world, author, 'write_file', path=path, text=shared_text + '# PRIVATE_UNPUBLISHED_REVISION\n')
    call(world, partner, 'integrate_patch', patch_id=patch['patch_id'])
    assert call(world, partner, 'read_file', path=path, start_line=1, max_lines=len(shared_text.splitlines()))['text'] == '\n'.join(shared_text.splitlines())
    child = call(world, author, 'spawn_member', briefing='Only this public patch and explicit briefing', patch_id=patch['patch_id'])['member_id']
    assert call(world, child, 'read_file', path=path, start_line=1, max_lines=len(shared_text.splitlines()))['text'] == '\n'.join(shared_text.splitlines())
    child_observation = SoftwareCollaborationPort(world.session(child, PROJECT), child).observe()
    assert len(child_observation['initial_diagnostics']) == 2
    assert 'PRIVATE_UNPUBLISHED_REVISION' not in str(child_observation)
    first = call(world, author, 'run_tests')
    assert first['version'] == paging.PAGING_VERSION and first['page']['index'] == 0
    assert len(first['page']['text']) <= 3072
    report = world._software()['test_reports'][first['report_id']]
    assert p.case['case_id'] in str(report['visible_result']['public_diagnostics'])
    assert world.test_budget.snapshot()['used'] == 1
    reread = call(world, author, 'read_test_result', report_id=first['report_id'], cursor=first['page']['cursor'])
    assert reread['page'] == first['page']
    assert world.test_budget.snapshot()['used'] == 1
    assert not world.session(child, PROJECT).call('read_test_result', report_id=first['report_id'], cursor=first['page']['cursor'])['ok']
    before = world.test_budget.snapshot()
    assessment = assess_software_collaboration(p, run_root=tmp_path/'unused-private-assessment')
    assert assessment['R'] == 0 and assessment['submitted'] is False
    assert world.test_budget.snapshot() == before
