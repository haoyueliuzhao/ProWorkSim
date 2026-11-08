import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.software_collaboration_runtime_observer_v167 import RuntimeObservationBridge, root_sessions
from proworksim.software_collaboration_observation_v167 import ObservationError

M1, M2 = 'member_001', 'member_002'


def ref(n):
    return {'object_id': 'source', 'version_id': 'v'+str(n)}


def setup_review(tmp_path, decision='accept'):
    bridge = RuntimeObservationBridge(tmp_path, team_id='fixture', members=[M1, M2])
    pub = {'source_reference': ref(1), 'files_sha256': 'a'*64, 'entry_metadata_sha256': 'b'*64}
    current = {**pub, 'source_reference': ref(5)}
    bridge.log.record('pub', 'artifact_published', M1, patch_id='p1', source_reference=ref(1),
        content_identity={k: pub[k] for k in ('files_sha256', 'entry_metadata_sha256')}, evidence={'CPU': True})
    bridge.log.record('chance', 'artifact_opportunity', M2, publication='pub', eligible=True, evidence={'CPU': True})
    bridge.log.record('take', 'artifact_acquired', M2, opportunity='chance', adopted_reference=ref(2), evidence={'CPU': True})
    bridge.log.record('old-test', 'artifact_validated', M2, acquisition='take', tested_reference=ref(2),
        executed=True, passed=True, evidence={'CPU': True})
    bridge.log.record('edit-restore', 'version_transition', M2, from_reference=ref(2), to_reference=ref(5), evidence={'CPU': True})
    bridge.publications['p1'] = ('pub', M1)
    bridge.validations[(M2, 'p1')] = ('old-test', True)
    receipt = {'review_id': 'review-1', 'patch_id': 'p1', 'actor_id': M2, 'author': M1,
        'identity': pub, 'decision': decision, 'reason': 'actual World receipt', 'event_sequence': 17,
        'adopted_source_reference': ref(5) if decision == 'accept' else None,
        'test_evidence': {**current, 'actor_id': M2, 'executed': True, 'passed': False, 'sequence': 16}
                         if decision == 'accept' else None}
    world = SimpleNamespace(org_current_identity=lambda _: current, org_state=lambda: {'reviews': [receipt]})
    bridge.runtime = SimpleNamespace(prepared=SimpleNamespace(world=world))
    bridge.tool_requests[(M2, 'tc')] = 'request1'
    return bridge, receipt


def execute_review(bridge, receipt):
    bridge.executed(M2, 'org_review_patch', {'patch_id': 'p1', 'decision': receipt['decision']},
        {'model_tool_call_id': 'tc', 'model_call_id': 'request1'}, {'ok': True, 'result': receipt}, ref(5))


def test_accept_after_edit_restore_uses_current_world_test_not_stale_acquisition(tmp_path):
    bridge, receipt = setup_review(tmp_path)
    execute_review(bridge, receipt)
    assert bridge.log.summary()['review']['current_version_acceptances'] == 1
    event = next(r for r in bridge.log._rows.values() if r['kind'] == 'world_review')
    assert event['data']['receipt']['test_evidence']['source_reference'] == ref(5)
    assert event['data']['receipt']['test_evidence']['passed'] is False
    assert bridge.validations[(M2, 'p1')] == ('old-test', True)  # No fabricated acquisition/test.
    bridge.log.record('later-edit', 'version_transition', M2, from_reference=ref(5), to_reference=ref(6), evidence={'CPU': True})
    assert bridge.log.summary()['review']['current_version_acceptances'] == 0
    bridge.log.close()


def test_request_changes_is_legal_with_old_test_and_new_current_version(tmp_path):
    bridge, receipt = setup_review(tmp_path, 'request_changes')
    execute_review(bridge, receipt)
    assert bridge.log.summary()['review']['authoritative_world_receipts'] == 1
    assert bridge.log.summary()['review']['accept_decisions'] == 0
    bridge.log.close()


@pytest.mark.parametrize('fault', ['stale_test', 'foreign_actor', 'changed_patch'])
def test_invalid_world_review_never_becomes_acceptance(tmp_path, fault):
    bridge, receipt = setup_review(tmp_path)
    if fault == 'stale_test':
        receipt['test_evidence']['source_reference'] = ref(2)
    elif fault == 'foreign_actor':
        receipt['test_evidence']['actor_id'] = M1
    else:
        receipt['identity']['files_sha256'] = 'c'*64
    with pytest.raises(ObservationError):
        execute_review(bridge, receipt)
    assert bridge.log.summary()['review']['accept_decisions'] == 0
    bridge.log.close()


def test_model_supplied_receipt_cannot_override_world_state(tmp_path):
    bridge, receipt = setup_review(tmp_path)
    spoof = copy.deepcopy(receipt); spoof['reason'] = 'forged'
    with pytest.raises(ValueError, match='authoritative World receipt'):
        execute_review(bridge, spoof)
    bridge.log.close()


def test_real_177_session_pytest_report_kept_whole_with_bounded_event(tmp_path):
    root = Path(__file__).resolve().parents[1]
    reports = root/'runs/software-benchmark-v159/communication-pilot-recovery-r1/episodes/15730/controller-output/model-ledger/collaboration-observation/public-test-reports'
    originals = [p for p in reports.glob('*.json') if len(json.loads(p.read_bytes()).get('sessions', [])) == 177]
    assert len(originals) == 1
    report = json.loads(originals[0].read_bytes())
    bridge = RuntimeObservationBridge(tmp_path, team_id='large-report', members=[M1])
    result = {'source_reference': ref(1), 'test_evidence': report, 'passed': False,
        'execution': {'executed': True, 'argv': ['pytest'], 'returncode': 1, 'timed_out': False}}
    event = bridge.observe_public_test(M1, result)
    assert bridge.observe_public_test(M1, result) == event
    data = bridge.log._rows[event]['data']
    assert data['session_count'] == 177 and len(data['sessions']) == 1
    assert json.loads(Path(data['report']['path']).read_bytes()) == report
    assert bridge.log.summary()['public_tests']['executed'] == 1
    bridge.log.close()


def test_missing_or_cyclic_nested_session_cannot_claim_valid_report():
    for parent in ('missing', 'child'):
        with pytest.raises(ValueError, match='cyclic or missing'):
            root_sessions({'sessions': [{'run_id': 'root', 'root': True},
                {'run_id': 'child', 'parent_run_id': parent, 'root': False}]})
