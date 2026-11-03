"""Necessary provenance controls; no archive is exported or graded by these tests."""
from __future__ import annotations

import copy

import pytest

from proworksim import software_benchmark_stopped_recovery_v114 as recovery


@pytest.mark.parametrize('index', [7244, 7251])
def test_only_original_stopped_attempt_and_unexecuted_bad_call_are_admissible(index):
    folder = recovery.BATCH/'episodes'/str(index)
    plan = recovery.read_ref(recovery.reference(recovery.BATCH/'execution-plan-v113.json'))
    row = next(row for row in plan['rows'] if row['slot_index'] == index)
    result = recovery.read_ref(recovery.reference(folder/'result.json'))
    child = recovery.read_ref(result['controller_result'])
    interrupted = recovery.read_ref(result['interrupted_worktree'])
    writers = recovery.read_ref(result['writer_quiescence'])
    quiet = recovery.read_ref(result['quiescence'])
    provenance = recovery.read_ref(recovery.reference(folder/'baseline-snapshot-provenance.json'))
    args = (index, row, result, child, interrupted, writers, quiet, provenance)
    assert recovery.validate_records(*args) is True
    response_ref = recovery.controller_ref(child['ledger']['calls'][-1]['response'], folder/'controller-output')
    response = recovery.read_ref(response_ref)
    proof = recovery.rejected_action_evidence(folder, response)
    assert proof['bad_call_had_no_action'] is True and proof['bad_action_replayed'] is False
    assert proof['last_actual_command_exit_code'] == (1 if index == 7244 else 0)
    with pytest.raises(ValueError, match='unclosed REF'):
        recovery.validate_records(index, row, {**result, 'status': 'closed'}, *args[3:])
    bad_ledger = copy.deepcopy(child)
    bad_ledger['ledger']['inflight'] = {'uncertain': True}
    with pytest.raises(ValueError, match='uncertain model usage'):
        recovery.validate_records(index, row, result, bad_ledger, *args[4:])
    with pytest.raises(ValueError, match='complete writer'):
        recovery.validate_records(index, row, result, child, interrupted, writers,
                                  {**quiet, 'quiescent': False}, provenance)
    wrong = copy.deepcopy(interrupted)
    wrong['archive']['container_id'] = 'another-actor'
    with pytest.raises(ValueError, match='same original baseline actor'):
        recovery.validate_records(index, row, result, child, wrong, writers, quiet, provenance)


def test_second_candidate_selection_is_prohibited(tmp_path, monkeypatch):
    monkeypatch.setattr(recovery, 'OUTPUT', tmp_path)
    (tmp_path/'7244').mkdir()
    with pytest.raises(FileExistsError, match='never overwrite or reselect'):
        recovery.recover(7244)
