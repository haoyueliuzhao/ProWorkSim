"""CLI historic boundaries remain independent of later colleague completion."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cli(*args):
    result = subprocess.run([sys.executable, '-m', 'proworksim', *map(str, args)],
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_historical_cut_does_not_inherit_later_success_or_require_live_world(tmp_path):
    world = tmp_path / 'world'
    cli('scenario-build', world, '--spec', ROOT / 'examples/scenarios-v10/report-direct.json')
    cut, continued = tmp_path / 'cut.json', tmp_path / 'continued.json'
    cli('staff-run', world, '--max-opportunities', 1, '--output', cut)
    assert cli('staff-run', world, '--checkpoint', cut, '--output', continued)['status'] == 'completed'
    history = tmp_path / 'historical.json'
    current = tmp_path / 'current.json'
    cli('episode-assess', world, '--experience', cut, '--output', history)
    cli('world-assess', world, '--experience', cut, '--output', current)
    fixed = json.loads(history.read_text())['assessment']
    assert all(v['submission_id'] is None for v in fixed['historical_episode']['fixed_deliveries'].values())
    live = json.loads(current.read_text())['assessment']
    assert live['institutional_progress'] != fixed['institutional_progress']
    world.rename(tmp_path / 'world-removed-from-live-path')
    detached = tmp_path / 'detached.json'
    cli('episode-assess', world, '--experience', cut, '--output', detached)
    assert json.loads(detached.read_text())['assessment'] == fixed
