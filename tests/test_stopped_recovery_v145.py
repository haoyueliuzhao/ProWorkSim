"""Necessary source identity and uncertain-accounting counterexamples."""
import copy
import json
import sqlite3

import pytest

from proworksim import software_benchmark_stopped_recovery_v145 as recovery
from proworksim import software_benchmark_recovered_validation_v145 as bounded


def test_actor_test_tree_and_other_member_cannot_replace_stopped_source():
    folder = recovery.BATCH/'episodes/10066'
    row = next(r for r in recovery.load(recovery.reference(
        recovery.BATCH/'deployment-v143/execution-plan.json'))['rows'] if r['slot_index'] == 10066)
    result = recovery.load(recovery.reference(folder/'result.json'))
    values = [row, result, recovery.load(result['writer_quiescence']),
        recovery.load(result['quiescence']), recovery.load(result['controller_output_transfer']),
        recovery.load(result['interrupted_worktree']),
        recovery.load(recovery.reference(folder/'baseline-snapshot-provenance.json'))]
    for kind in ('actor_substitution', 'wrong_roster', 'live_writer'):
        bad = copy.deepcopy(values)
        if kind == 'actor_substitution':
            bad[4]['transfer']['role'] = 'actor'
        elif kind == 'wrong_roster':
            bad[0]['fixed_members'] = ['member_002']
        else:
            bad[2]['writers'][0]['state']['Running'] = True
        with pytest.raises(ValueError):
            recovery.validate_original(*bad)


@pytest.mark.parametrize('settled,uncertain,accept', [(0,1,True),(1,1,True),(1,0,False),(1,2,False)])
def test_unsettled_provider_call_is_never_converted_to_actual_zero(tmp_path, monkeypatch, settled, uncertain, accept):
    monkeypatch.setattr(recovery, 'BATCH', tmp_path)
    (tmp_path/'ledgers').mkdir()
    path = tmp_path/'ledgers/pilot.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE requests (request_id TEXT,condition TEXT,usage_id TEXT,status TEXT,usage_json TEXT,settled_nanoyuan INTEGER,reserved_nanoyuan INTEGER,slot_id TEXT)')
        for i in range(settled):
            db.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?,?)',
                (f's{i}','condition','agent','settled',json.dumps({'prompt_tokens':7,'completion_tokens':3,'total_tokens':10}),5,11,'slot'))
        for i in range(uncertain):
            db.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?,?)',
                (f'u{i}','condition','agent','uncertain',None,None,13,'slot'))
    before = path.read_bytes()
    row = {'slot_index':10066,'slot_id':'slot','condition_id':'condition'}
    if not accept:
        with pytest.raises(ValueError):
            recovery.provider_usage([row])
    else:
        usage = recovery.provider_usage([row])[10066]
        assert usage['total_tokens'] == settled*10
        assert usage['total_tokens_is_lower_bound'] is True
        assert usage['usage_complete'] is False
        assert usage['all_settled'] is False
        assert usage['uncertain_reserved_nanoyuan'] == 13
        assert usage['unresolved_requests'] == 1
    assert path.read_bytes() == before


def test_bounded_validator_rejects_large_json_metadata_before_loading(monkeypatch):
    def unexpected_load(_):
        raise AssertionError('Oversized JSON must never be loaded')
    monkeypatch.setattr(recovery, 'load', unexpected_load)
    with pytest.raises(ValueError, match='bounded'):
        bounded._small({'path':'unused','bytes':bounded.MAXIMUM_SMALL_RECORD+1,'sha256':'0'*64})


def test_bounded_stream_verification_detects_changed_frozen_bytes(tmp_path):
    path = tmp_path/'candidate.json'
    path.write_bytes(b'original committed bytes')
    ref = recovery.stream_reference(path)
    path.write_bytes(b'changed! committed bytes')
    with pytest.raises(ValueError, match='bytes changed'):
        bounded._bytes(ref)
