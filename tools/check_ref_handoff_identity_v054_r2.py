"""Narrow CPU controls using the real legacy ready schema; no service or GPU call."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
from unittest.mock import patch

import repair_ref_handoff_identity_v054_r2 as repair
from check_ref_handoff_pool_v054_r1 import fixture


def rejects(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError('Unsafe recovery input was admitted')


def main():
    checks = []
    # Reuse retained bytes, rather than adding fields the real legacy service
    # never produced. No admin request, PID lookup, CUDA or systemctl occurs.
    intent = repair.read(repair.OLD_INTENT)
    ready = repair.handoff.pool.read_ref(intent['ready'])
    registration = repair.handoff.pool.read_ref(intent['registration'])
    declaration = repair.handoff.pool.read_ref(registration['declaration'])
    assert 'invocation_id' not in ready and 'cgroup' not in ready
    original_ready = deepcopy(ready)
    owner = repair.normalized_owner(ready, intent['unit_state'], declaration)
    assert ready == original_ready
    assert owner['invocation_id'] == intent['unit_state']['InvocationID']
    assert owner['cgroup'] == intent['unit_state']['ControlGroup']
    repair.verify_fresh_owner(owner, intent['unit_state'], ready['host_process'])
    for changed in ({'InvocationID': 'a' * 32}, {'ControlGroup': '/user.slice/another.service'}, {'MainPID': '1'}):
        rejects(lambda changed=changed: repair.verify_fresh_owner(owner, {**intent['unit_state'], **changed}, ready['host_process']))
    rejects(lambda: repair.verify_fresh_owner(owner, intent['unit_state'], {**ready['host_process'], 'start_ticks': 1}))
    rejects(lambda: repair.normalized_owner({**ready, 'invocation_id': 'a' * 32}, intent['unit_state'], declaration))
    rejects(lambda: repair.normalized_owner({**ready, 'cgroup': '/incorrect'}, intent['unit_state'], declaration))
    checks.append('real_legacy_ready_missing_both_fields_accepted_via_attested_unit_optional_conflicts_and_fresh_changes_rejected')

    overlay_ref, intent_ref = repair.reference(repair.OVERLAY), repair.reference(repair.OLD_INTENT)
    failed = {'status': 'failed_manual_action_required', 'error': "KeyError('invocation_id')", 'automatic_retry': False,
        'previous': {'status': 'retirement_intent', 'intent': intent_ref, 'resource_retirement_overlay': overlay_ref}}
    repair.validate_failed_conversion(failed, overlay_ref, intent_ref)
    rejects(lambda: repair.validate_failed_conversion({**failed, 'error': 'different failure'}, overlay_ref, intent_ref))
    checks.append('only_exact_old_pre_stop_failure_is_admitted_without_clearing_its_history')

    with tempfile.TemporaryDirectory(prefix='v054-ref-identity-r2-control-') as directory:
        root = Path(directory)
        out = root / 'stop-once'
        out.mkdir()
        with patch.object(repair, 'OUT', out), \
                patch.object(repair.handoff.original, 'unit_state', return_value=intent['unit_state']), \
                patch.object(repair, 'process_identity', return_value=ready['host_process']), \
                patch.object(repair.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='', stderr='')) as stop:
            first = repair.stop_exact_once(owner, intent_ref)
            assert repair.stop_exact_once(owner, intent_ref) == first
            stop.assert_called_once()
            assert stop.call_args.args[0] == ['systemctl', '--user', 'stop', repair.REF_UNIT]
            (out / 'stop-receipt.json').unlink()
            rejects(lambda: repair.stop_exact_once(owner, intent_ref))
            assert stop.call_count == 1
        checks.append('durable_stop_receipt_reused_but_ambiguous_stop_intent_never_replayed')

        out = root / 'identity-change'
        out.mkdir()
        with patch.object(repair, 'OUT', out), \
                patch.object(repair.handoff.original, 'unit_state', return_value={**intent['unit_state'], 'InvocationID': 'a' * 32}), \
                patch.object(repair, 'process_identity', return_value=ready['host_process']), \
                patch.object(repair.subprocess, 'run') as stop:
            rejects(lambda: repair.stop_exact_once(owner, intent_ref))
            stop.assert_not_called()
            assert not (out / 'stop-intent.json').exists()
        checks.append('fresh_service_identity_change_blocks_before_any_stop_intent_or_signal')

        prior = repair.write_new(root / 'prior.json', {'conversion': failed, 'conversion_sha256': repair.content_sha(failed),
            'devices_sha256': repair.content_sha({'unrelated': {'status': 'failed_manual_action_required'}})})
        state = {'pool_policy': {}, 'devices': {'unrelated': {'status': 'failed_manual_action_required'}},
            'conversion': failed, 'formal_slots_claimed': 0, 'automatically_replayed_formal_episodes': 0}
        plan = {'pool_policy': {}, 'prior_failure': prior, 'overlay': overlay_ref}
        changed = repair.adopt_state(state, plan, {'plan': 'r2'}, intent_ref)
        assert state['conversion'] == failed and changed['devices'] == state['devices']
        assert changed['conversion']['previous_failure'] == prior and changed['conversion']['status'] != 'none'
        final = repair.adopt_state(changed, plan, {'plan': 'r2'}, intent_ref, closure_ref={'closure': True}, retirement_ref={'event': True})
        assert final['conversion']['status'] == 'ref_retired_waiting_for_mp_capacity'
        assert final['conversion']['previous_failed_conversion_sha256'] == repair.content_sha(failed)
        assert final['devices'] == state['devices']
        checks.append('failed_to_recovery_to_retired_preserves_exact_failed_reference_devices_and_formal_counters')

        chain = root / 'original-reader'
        chain.mkdir()
        value = fixture(chain)
        augmented = repair.write_new(chain / 'r2-closure.json', {**value['closure'],
            'operational_recovery': {'plan': 'r2'}, 'previous_failure': prior,
            'validated_unit_identity': {'owner': True}, 'stop_receipt': {'stop': True}})
        plan = {'pool_policy': value['policy_ref'], 'registration': value['registration'], 'overlay': value['overlay_ref']}
        with patch.object(repair.handoff, 'validate_overlay', return_value=value['overlay']), \
                patch.object(repair.handoff.pool, 'validate_pool_policy', return_value=value['policy']), \
                patch.object(repair.handoff.pool, '_static_registration'), \
                patch.object(repair.handoff, 'read_pool', side_effect=lambda ref: repair.handoff._read_target_pool(
                    ref, value['overlay_ref'], value['overlay'])):
            event = repair.retire_once(plan, augmented)
            assert repair.retire_once(plan, augmented) == event
            current = repair.handoff._read_target_pool(value['policy_ref'], value['overlay_ref'], value['overlay'])
            assert not current['active'] and len(current['events']) == 2
            assert repair.handoff.pool.read_ref(event)['retirement_rule'] == repair.handoff.VERSION
            rejects(lambda: repair.retire_once(plan, value['closure_ref']))
        checks.append('existing_r1_reader_accepts_recovery_closure_and_append_interruption_reuses_the_unique_event')
    print(json.dumps({'version': repair.VERSION, 'passed': True, 'checks': checks,
        'real_service_calls': 0, 'real_process_signals': 0, 'GPU_probes': 0, 'model_calls': 0,
        'model_loads': 0, 'formal_claims': 0, 'actual_pool_state_written': False,
        'actual_ready_modified': False}, indent=2))


if __name__ == '__main__':
    main()
