import copy

from proworksim.scenarios import build_scenario
from proworksim.templates.decision_team import scenario_spec
from proworksim.work_interface import WorkInterface, _schema_errors


def make(tmp_path):
    deployment = build_scenario(scenario_spec(), tmp_path / 'world')
    assert deployment.status == 'ready'
    world = deployment.world
    return world, WorkInterface(world.session('provider', 'TEAM'), 'provider', audit_dir=tmp_path / 'view')


def test_two_explicit_readers_keep_auth_exact_versions_and_actual_receipts(tmp_path):
    world, port = make(tmp_path)
    old = world.session('provider', 'TEAM')
    oid = world.state['workspaces']['TEAM']['basis']
    before = copy.deepcopy(world.state['knowledge']['provider'])
    ambiguous = old.call('read_object', alias='basis', object_id=oid)
    assert not ambiguous['ok']
    assert world.state['knowledge']['provider'] == before
    extra = port.call('read_alias', alias='basis', object_id=oid)
    assert not extra['ok'] and extra['error']['rejection']['code'] == 'public_argument_schema'
    assert world.state['knowledge']['provider'] == before
    read = port.call('read_alias', alias='basis', work_id='TEAM::build')
    assert read['ok'], read
    reference = read['result']['reference']
    assert reference == {'object_id': oid, 'version_id': 'v1'}
    exact = port.call('read_version', reference=reference, work_id='TEAM::build')
    assert exact['ok'] and exact['result'] == read['result']
    bad = port.call('read_version', reference={**reference, 'version_id': 'missing'})
    assert not bad['ok']
    assert world.state['adoptions'] == {}
    assert world.state['handoffs'] == {}
    private = world.state['workspaces']['TEAM']['audit_basis']
    denied = port.call('read_version', reference={'object_id': private, 'version_id': 'v1'})
    assert not denied['ok']
    # Both successes are real core commands, not a renamed fake public return.
    assert read['command_committed'] and exact['command_committed']
    assert read['command_id'] != exact['command_id']
    assert world.state['knowledge']['provider']['read_artifacts'][-1]['version_id'] == 'v1'


def test_profile_schema_rejects_nested_reference_without_mutating_world(tmp_path):
    world, port = make(tmp_path)
    definitions = {d['name']: d for d in port.tools()}
    assert 'read_object' not in definitions
    params = definitions['read_version']['parameters']
    assert _schema_errors(params, {'reference': {'alias': 'basis', 'version_id': 'v1'}})
    before = copy.deepcopy(world.state['knowledge']['provider'])
    bad = port.call('read_version', reference={'alias': 'basis', 'version_id': 'v1'})
    assert not bad['ok']
    assert world.state['knowledge']['provider'] == before
    # No silent fallback to the old operation, and no automatic correct source.
    hidden = port.call('read_object', alias='basis')
    assert not hidden['ok'] and hidden['error']['rejection']['code'] == 'tool_not_in_profile'
    assert world.state['knowledge']['provider'] == before
    handoff = definitions['handoff_information']['parameters']
    base = {'route_id': 'basis', 'work_id': 'TEAM::build', 'handoff_key': 'one', 'body': 'Actual reply'}
    assert _schema_errors(handoff, base)
    assert _schema_errors(handoff, {**base, 'status': 'unavailable'})
    assert not _schema_errors(handoff, {**base, 'status': 'unavailable', 'request_id': 'real-request-to-be-checked-by-world'})
    assert world.state['handoffs'] == {}


def test_projection_keeps_all_contracts_and_visible_information_and_logs_raw(tmp_path):
    _, port = make(tmp_path)
    original = port._session.observe()
    selected = port.observe()
    for key in original:
        if key != 'projects':
            assert selected[key] == original[key]
    assert port.projections[-1]['raw_observation'] == original
    assert len(list((tmp_path / 'view').glob('*.json'))) == 1
    assert len(str(port.tools())) < len(str(port._session.tools()))
    # Neither projection nor syntax definitions can read the reviewer private body.
    assert 'audit_basis' not in selected['workspaces']['TEAM']
