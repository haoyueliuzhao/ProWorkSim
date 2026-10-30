"""Administrative closure refuses intermediate trees and uncertain generation."""
import copy

import pytest

from proworksim.software_benchmark_managed_recovery_v095 import validate_boundary


def facts():
    result = {'arm': 'PROJECT', 'slot_id': 'fixed'}
    child = {'arm': 'PROJECT', 'slot_id': 'fixed', 'hidden_feedback_received': False,
        'automatic_retry': False, 'preparation_only': False, 'status': 'technical_unknown',
        'error': {'type': 'ManagedTransferError'}, 'traceback': 'synced = rpc.request("sync_terminal", ...)',
        'closure_reason': 'all_members_stopped_or_no_reachable_event',
        'ledger': {'complete_actual_tokens': 3, 'known_actual_tokens': 3, 'inflight': None,
            'uncertain_reserved_tokens': 0, 'attempts': 1,
            'calls': [{'usage': {'prompt_tokens': 2, 'completion_tokens': 1, 'total_tokens': 3}}]}}
    boundary = {'status': 'bounded_work_closed', 'execution_integrity_failure': None,
        'continuation': False, 'closure_reason': child['closure_reason']}
    quiet = {'quiescent': True, 'cleanup_errors': [], 'create_result_unknown': False, 'retained_objects': []}
    writers = {'all_quiet': True, 'errors': [], 'writers': [
        {'role': role, 'state': {'Running': False, 'Pid': 0}} for role in ('actor', 'controller')]}
    bridge = {'ready': True, 'status': 'channel_closed', 'generation_requests': 1,
              'failed_requests': 0, 'automatic_retries': 0}
    lock = {'version': 'software-benchmark-episode-candidates-v054', 'locked_before_grading': True,
        'same_world_transaction': True, 'terminal_code': {'path': 'original-lock'},
        'current_working_tree_substituted_for_delivery': False,
        'model_calls': 0, 'public_test_calls': 0, 'grading_calls': 0}
    return [result, child, boundary, quiet, writers, bridge, lock]


def test_existing_post_close_lock_is_eligible_but_does_not_fake_normal_exit():
    values = facts()
    before = copy.deepcopy(values)
    result = validate_boundary(*values)
    assert result['administrative_artifact_recovery_eligible']
    assert not result['original_controller_normal_exit']
    assert not result['actor_interrupted_tree_used'] and not result['model_rerun']
    assert values == before


@pytest.mark.parametrize('bad', ['inflight', 'before_lock', 'no_lock', 'writer_live', 'bad_usage', 'bridge_mismatch'])
def test_intermediate_or_uncertain_evidence_cannot_become_closed(bad):
    values = facts()
    if bad == 'inflight':
        values[1]['ledger']['inflight'] = {'reservation': 8}
    elif bad == 'before_lock':
        values[1]['traceback'] = 'runtime = build_runtime(...)'
    elif bad == 'no_lock':
        values[6]['terminal_code'] = None
    elif bad == 'writer_live':
        values[4]['writers'][0]['state']['Running'] = True
    elif bad == 'bad_usage':
        values[1]['ledger']['known_actual_tokens'] = 10
    else:
        values[5]['generation_requests'] = 2
    with pytest.raises(ValueError):
        validate_boundary(*values)
