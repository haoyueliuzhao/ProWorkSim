"""New inventory and mechanism-only release controls; no model/GPU."""
from collections import Counter

import pytest

from scripts import software_organization_v044 as runner
from scripts.run_ne_v021 import write


def test_balanced_new_inventory_and_mechanism_only_release():
    inventory = runner.assignments()
    units = [u for group in inventory.values() for u in group]
    assert len(units) == len({u['slot_id'] for u in units}) == 16
    assert {u['sampling_seed'] for u in units} == {202610100441, 202610100442}
    assert Counter(group[0]['condition'] for group in inventory.values()) == dict.fromkeys(runner.CONDITIONS, 1)
    for field in ('first_member', 'diagnostic_a_owner'):
        assert Counter(group[0][field] for group in inventory.values()) == {'member_001': 2, 'member_002': 2}
    assert Counter(group[0]['first_member'] == group[0]['diagnostic_a_owner'] for group in inventory.values()) == {True: 2, False: 2}
    states = {name: {'status': 'not_started'} for name in runner.WORKERS}
    assert runner.eligible_workers(states, None) == [runner.FIRST_BLOCK]
    states[runner.FIRST_BLOCK]['status'] = 'running'
    assert runner.eligible_workers(states, None) == []
    states[runner.FIRST_BLOCK]['status'] = 'complete'
    assert runner.eligible_workers(states, {'passed': False}) == []
    assert runner.eligible_workers(states, {'passed': True}) == [n for n in runner.WORKERS if n != runner.FIRST_BLOCK]
    assert runner.GPU_ORDER == (3, 4, 5, 7)
    assert runner.FIRST_BLOCK == 'block-r1-s0'
    assert all(u['slot_id'].startswith('org44-') for u in units)



def test_unstarted_inventory_is_retained_when_first_block_gate_stops(tmp_path):
    write(tmp_path / 'plan.json', {'source': {'code_commit': 'CPU'}, 'assignments': runner.assignments()})
    write(tmp_path / 'supervisor.json', {'status': 'stopped_by_first_block_gate',
        'states': {name: {'status': 'stopped', 'attempted': False} for name in runner.WORKERS}})
    result = runner.results(tmp_path)
    assert result['known'] == 0 and result['scheduled'] == 16
    assert len(result['rows']) == 16
    assert all(row['status'] == 'not_started' and row['R'] is None for row in result['rows'])
    assert all(v is None for v in result['full_inventory_mean_contrasts'].values())


def test_direct_worker_entry_cannot_bypass_first_block_gate(tmp_path):
    plan = {"assignments": runner.assignments()}
    runner.require_worker_release(tmp_path, runner.FIRST_BLOCK, plan)
    for worker in (n for n in runner.WORKERS if n != runner.FIRST_BLOCK):
        with pytest.raises(ValueError, match="mechanism gate"):
            runner.require_worker_release(tmp_path, worker, plan)
    write(tmp_path / 'first-block-gate.json', {'passed': True, 'first_block': runner.FIRST_BLOCK})
    with pytest.raises(ValueError, match="mechanism gate"):
        runner.require_worker_release(tmp_path, runner.WORKERS[0], plan)


def test_new_gamma_changes_format_feedback_but_retains_test_page_world():
    assert 'src/proworksim/software_organization_v042.py' in runner.CONTROL_SOURCES
    assert 'src/proworksim/software_context_v042.py' in runner.CONTROL_SOURCES
    assert 'scripts/software_organization_v044.py' in runner.CONTROL_SOURCES
    assert 'src/proworksim/harness_sdk.py' in runner.CONTROL_SOURCES
    assert set(runner.SEEDS).isdisjoint({202610100401, 202610100402})
