"""Declared preparation roles produce real shared inputs before target work."""

import json
import subprocess
import sys

import pytest

from proworksim.scenarios import validate_scenario
from proworksim.templates.executable_project import scenario_spec


def test_published_prefix_is_real_and_target_episode_starts_after_it(tmp_path):
    spec = scenario_spec(changed=False)
    spec['start'] = {'kind': 'executed_prefix', 'roles': ['P0'], 'max_opportunities': 120,
                     'when': {'work': {'project': 'P0', 'node': 'build', 'phase': 'published'}}}
    path = tmp_path / 'spec.json'
    path.write_text(json.dumps(spec))
    world = tmp_path / 'world'
    output = tmp_path / 'run.json'
    for args in [
        ['scenario-build', str(world), '--spec', str(path)],
        ['staff-run', str(world), '--max-opportunities', '0', '--output', str(output)],
    ]:
        result = subprocess.run([sys.executable, '-m', 'proworksim', *args], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    saved = json.loads(output.read_text())
    assert saved['result']['status'] == 'budget_exhausted'
    checkpoint = saved['worker_checkpoint']
    assert checkpoint['roles']['P0']['actions'] > 0
    assert all(value['opportunities'] == 0 for key, value in checkpoint['roles'].items() if key != 'P0')
    manifest = json.loads(open(saved['episode_manifest']).read())
    assert manifest['experience']['start'] > 0
    state = json.loads((tmp_path / 'run.json.episode/start/control/state.json').read_text())
    assert state['work_items']['P0::build']['status'] == 'accepted'
    assert state['releases']
    assert not state['work_items']['P1::build']['submissions']
    actual = [e for e in checkpoint['experience']['events'] if e['kind'] == 'tool_call']
    assert all(e['worker_id'] == 'P0' for e in actual)
    assert {'sql_build', 'submit', 'share', 'publish'} <= {e['payload']['action'] for e in actual}


def test_unknown_prefix_role_is_unbuildable_without_silently_changing_schedule():
    spec = scenario_spec()
    spec['start'] = {'kind': 'executed_prefix', 'roles': ['not-a-worker'], 'max_opportunities': 10,
                     'when': {'work': {'project': 'P0', 'node': 'build', 'phase': 'published'}}}
    with pytest.raises(ValueError, match='role'):
        validate_scenario(spec)


def test_accepted_without_publication_is_never_a_published_prefix(tmp_path):
    from pathlib import Path
    from proworksim.scenarios import build_scenario, run_scenario, ScenarioController

    spec = json.loads((Path(__file__).resolve().parents[1] / 'examples/scenarios-v10/report-direct.json').read_text())
    built = build_scenario(spec, tmp_path / 'accepted')
    assert run_scenario(built)['status'] == 'completed'
    assert not built.world.state['releases']
    predicate = {'work': {'project': 'REPORT', 'node': 'research', 'phase': 'published'}}
    assert ScenarioController(built).matches(predicate) is False
    spec['start'] = {'kind': 'executed_prefix', 'when': predicate, 'max_opportunities': 20}
    rejected = build_scenario(spec, tmp_path / 'unbuildable')
    assert rejected.status == 'unbuildable'
    assert 'public_delivery.publish' in ' '.join(rejected.diagnostics)
