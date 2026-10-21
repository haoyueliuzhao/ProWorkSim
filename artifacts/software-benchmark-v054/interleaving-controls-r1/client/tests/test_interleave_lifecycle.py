"""New lifecycle gates only: real CPU flocks, programmed admin, synthetic receipts."""
from pathlib import Path
import copy
import importlib.util
import json
import os
import sys
import uuid

import pytest

from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_supervision_v054 import process_identity

STAGE = Path('/tmp/v054-interleave-session-r1')
ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')


def load(name):
    full = 'proworksim.' + name
    spec = importlib.util.spec_from_file_location(full, STAGE / 'src/proworksim' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


pool = load('software_benchmark_resident_pool_v054')
module = load('software_benchmark_resident_session_v054')


def test_dual_session_lifecycle_and_admission(tmp_path, monkeypatch):
    monkeypatch.setattr(pool, 'ROOT', ROOT)
    spec = write_new(tmp_path / 'spec.json', {'session_protocol': 'mp-interleave-v1', 'maximum_sessions': 2})
    declaration = {'mode': 'MATCH_PROJECT', 'source_spec': spec, 'session_protocol': 'mp-interleave-v1',
                   'maximum_sessions': 2, 'session_lock_path': str(tmp_path / 'session.lock')}
    identity = {'session_protocol': 'mp-interleave-v1', 'maximum_sessions': 2}
    ready = {**identity, 'host_process': process_identity(os.getpid())}
    declaration_ref = write_new(tmp_path / 'declaration.json', declaration)
    observed = {'declaration': declaration, 'identity': identity, 'ready': ready, 'session_capacity': 2,
                'resident_id': 'synthetic-owner', 'active_claims': []}
    monkeypatch.setattr(module, 'admitted_resident', lambda *args, **kwargs: observed)
    sessions, operations, stopped = {}, [], []
    shared_fault = False

    def status():
        active = sorted(sessions)
        dispatched = [(claim, value['dispatched']) for claim, value in sessions.items() if value['dispatched']]
        return {'resident': True, 'state': 'busy' if active else 'idle', 'poisoned': None,
                'active_claims': active, 'sessions': copy.deepcopy(sessions),
                'available_session_slots': sorted({0, 1} - {x['session_slot'] for x in sessions.values()}),
                'inflight': ({'claim_id': dispatched[0][0], 'ticket_id': dispatched[0][1], 'operation': 'match_complete'}
                             if dispatched else None)}

    class Client:
        def call(self, operation, **arguments):
            operations.append(operation)
            if operation == 'status':
                return status()
            claim = arguments['claim_id']
            if operation == 'acquire':
                index = arguments['session_slot']
                assert index not in {x['session_slot'] for x in sessions.values()}
                sessions[claim] = {'session_slot': index, 'phase': 'acquired', 'queued': False, 'dispatched': False}
                return {'state': 'acquired', 'acquired': True, 'claim_id': claim,
                        'session_slot': index, **identity, 'session_identity': {**identity, 'claim_id': claim},
                        'session_socket': str(tmp_path / (claim + '.sock'))}
            if operation == 'release':
                sessions.pop(claim)
                other = sorted(sessions)
                inflight = status()['inflight']
                return {'state': 'released', 'claim_id': claim, 'quiescence': {
                    'session_quiescent': True, 'own_inflight': 0, 'queued_removed': True,
                    'learning_unchanged': True, 'rng_restored_exactly': True, 'session_rng_closed': True,
                    'weights_reloaded': False, 'model_object_retained': True, 'old_session_socket_removed': True,
                    'resident_still_loaded': True, 'other_active_claims': other,
                    'resident_generator_active': inflight['claim_id'] if inflight else None}}
            if operation == 'abort_session':
                if shared_fault:
                    return {'claim_id': claim, 'shared_poisoned': True, 'inflight': status()['inflight']}
                sessions.pop(claim)
                return {'claim_id': claim, 'session_aborted': True, 'shared_poisoned': False,
                        'own_dispatched': False, 'not_dispatched_receipts': [], 'resident_still_loaded': True}
            raise AssertionError(operation)

    monkeypatch.setattr(module, 'admin_client', lambda *args, **kwargs: Client())
    monkeypatch.setattr(module, 'suspend_registered', lambda *args: stopped.append('synthetic') or {'synthetic': True})

    def acquire(label):
        directory = tmp_path / label
        directory.mkdir()
        return module.ResidentSession(declaration_ref, slot={'arm': 'MATCH', 'slot_id': 'synthetic-' + label},
            claim_id=uuid.uuid4().hex, authorization={'synthetic': True}, directory=directory,
            pool_policy_reference={'synthetic': True}, registration_reference={'synthetic': True})

    first, second = acquire('first'), acquire('second')
    assert first.session['session_slot'] == 0 and second.session['session_slot'] == 1
    operations_before = list(operations)
    with pytest.raises(BlockingIOError):
        acquire('third-rejected')
    assert operations == operations_before
    assert len(module.interleaved_status(status())) == 2
    sessions[second.session['claim_id']].update(phase='collecting', dispatched='synthetic-ticket-B')
    first.release(controller_result={'ledger': {'inflight': None, 'held_tokens': 0, 'complete_actual_tokens': 7}},
                  finish_receipt={'synthetic': True})
    guard = first.poison('synthetic post-release CPU failure')
    assert guard['poisoned'] is False and not stopped
    assert guard['evidence']['status']['inflight']['claim_id'] == second.session['claim_id']
    sessions[second.session['claim_id']].update(dispatched=False, queued='synthetic-queued-B')
    local = second.poison('synthetic CPU host disappeared before dispatch')
    assert local['shared_poisoned'] is False and local['other_sessions_undisturbed'] is True and not stopped
    first.close()
    second.close()
    third = acquire('third-after-release')
    sessions[third.session['claim_id']].update(phase='collecting', dispatched='synthetic-ticket-C')
    shared_fault = True
    fault = third.poison('synthetic dispatched request unknown')
    assert fault['shared_poisoned'] is True and stopped == ['synthetic']
    third.close()
    with pytest.raises(ValueError):
        pool.declared_session_capacity({**declaration, 'mode': 'REF'})
    assert pool.declared_session_capacity({'mode': 'REF'}) == 1

    # Validate real small-file references; all qualification contents below are
    # explicitly programmed fixtures, never claimed to be actual GPU evidence.
    generic = write_new(tmp_path / 'generic.json', {'synthetic': True})
    baseline = write_new(tmp_path / 'baseline.json', {'contract': generic, 'capacity_receipt': generic, 'model_manifest': generic})
    template = write_new(tmp_path / 'template.json', {'source_spec': baseline})
    policy = {'version': 'v054-resident-pool-policy-v2-interleaved', 'physical_gpus': list(range(8)),
        'maximum_residents': 8, 'minimum_free_mib': 46080, 'minimum_total_mib': 81920,
        'allowed_gpu_names': ['NVIDIA A800-SXM4-80GB'], 'allow_co_residency': True, 'require_idle': False,
        'maximum_actual_load_attempts_per_gpu': 1, 'maximum_preparation_calls_per_new_resident': 6,
        'automatic_retry_after_load_failure': False, 'model_loading_authorized': True,
        'preparation_generation_authorized': True, 'ref_to_mp_after_all_500_scored': True,
        'training_authorized': False, 'inherit_modes': ['REF'], 'MP_session_protocol': 'mp-interleave-v1',
        'maximum_MP_sessions_per_resident': 2, 'maximum_REF_sessions_per_resident': 1,
        'pool_root': str(ROOT / 'runs/software-benchmark-v054/synthetic-unstarted-pool'),
        'queue_state_path': str(ROOT / 'runs/software-benchmark-v054/synthetic-unstarted-queue'),
        'source_manifest': generic, 'inherited_registry': generic, 'inherited_admission': generic,
        'match_template_declaration': template, 'slots': generic}
    policy_ref = write_new(tmp_path / 'policy.json', policy)
    assert pool.validate_pool_policy(policy_ref)['maximum_preparation_calls_per_new_resident'] == 6
    deployment = {**json.loads(Path(spec['path']).read_text()), 'version': 'v054-match-resident-spec-v3',
                  'pool_policy': policy_ref, 'resident_id': 'synthetic-new', 'preparation_permit': generic,
                  'contract': generic, 'capacity_receipt': generic, 'model_manifest': generic}
    deployment_ref = write_new(tmp_path / 'deployment.json', deployment)
    declaration2 = {**declaration, 'source_spec': deployment_ref, 'gpu_index': 6, 'gpu_uuid': 'synthetic-GPU'}
    declaration2_ref = write_new(tmp_path / 'declaration2.json', declaration2)
    identity2 = {**identity, 'resource_binding': {'gpu_index': 6, 'gpu_uuid': 'synthetic-GPU'}}
    identity2_ref = write_new(tmp_path / 'identity2.json', identity2)
    ready2 = {**identity, 'ready': True, 'resident': True, 'source_spec': deployment_ref,
              'gpu_index': 6, 'gpu_uuid': 'synthetic-GPU', 'gpu_lease_held': True, 'identity': identity2_ref}
    ready2_ref = write_new(tmp_path / 'ready2.json', ready2)
    control = {'version': 'v054-mp-interleave-control-r1', 'status': 'passed', **identity,
        'declaration': declaration2_ref, 'authorization': generic, 'actual_model_generation_requests': 6,
        'completed_sessions': 4, 'unsettled_requests': 0, 'formal_slots_claimed': 0, 'model_loads': 1,
        'weights_reloaded_between_sessions': False, 'resident_identity': identity2,
        **{key: True for key in ['same_resident_PID_and_model', 'isolated_sessions', 'per_request_FIFO_serialization',
             'all_three_outputs_equal', 'all_three_token_traces_equal', 'all_three_rng_transitions_equal']}}
    control_ref = write_new(tmp_path / 'control.json', control)
    admission = {'version': pool.ADMISSION_VERSION, 'passed': True, 'pool_policy': policy_ref,
        'declaration': declaration2_ref, 'source_spec': deployment_ref, 'resident_id': 'synthetic-new',
        'formal_slots_claimed': 0, 'ready': ready2_ref, 'kind': 'new_interleaved_model_device',
        'check_receipt': control_ref, 'interleaving_check_receipt': control_ref}
    admission_ref = write_new(tmp_path / 'admission.json', admission)
    event = {'event': 'register', 'pool_policy': policy_ref, 'resident_id': 'synthetic-new',
        'mode': 'MATCH_PROJECT', 'gpu_index': 6, 'gpu_uuid': 'synthetic-GPU', 'source_spec': deployment_ref,
        'declaration': declaration2_ref, 'admission': admission_ref}
    assert pool._static_registration(event, policy_ref) == event
    stale_control = write_new(tmp_path / 'old-sequential-control.json', {**control, 'actual_model_generation_requests': 2})
    stale_admission = write_new(tmp_path / 'stale-admission.json', {**admission, 'check_receipt': stale_control,
                                                                 'interleaving_check_receipt': stale_control})
    with pytest.raises(ValueError, match='six-request'):
        pool._static_registration({**event, 'admission': stale_admission}, policy_ref)
    write_new(STAGE / 'control-receipt.json', {'version': 'v054-interleave-client-CPU-control-r1', 'passed': True,
        'actual_model_calls': 0, 'GPU_loads': 0, 'formal_claims': 0,
        'real_flock_two_slots_and_third_rejected': True, 'release_while_other_session_dispatched': True,
        'post_release_failure_preserves_other_session': True, 'queued_CPU_failure_is_session_local': True,
        'dispatched_unknown_fault_is_shared': True, 'REF_capacity_unchanged': True,
        'synthetic_admission_schema_accepts_six_request_proof_rejects_sequential_two': True,
        'synthetic_proofs_are_not_actual_GPU_qualification': True,
        'sources': [reference(STAGE / 'src/proworksim' / (name + '.py')) for name in
                    ['software_benchmark_resident_pool_v054', 'software_benchmark_resident_session_v054',
                     'software_benchmark_service_factory_v054']]})
