"""One finite CPU fixture for independent health; no real admin/model requests."""
from pathlib import Path
import importlib.util

import pytest

from proworksim.software_benchmark_candidates_v054 import reference, write_new

STAGE = Path('/tmp/v054-deferred-pool-r1')
SOURCE = STAGE / 'src/proworksim/software_benchmark_deferred_pool_v054.py'
spec = importlib.util.spec_from_file_location('proworksim.software_benchmark_deferred_pool_v054_control', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_one_bad_resident_does_not_cancel_healthy(monkeypatch):
    rows = [{'resident_id': rid, 'declaration': {'path': rid}, 'event_reference': {'path': rid + '-event'},
             'mode': 'MATCH_PROJECT', 'gpu_index': index} for rid, index in [('bad', 6), ('healthy', 3)]]
    monkeypatch.setattr(module, 'validate_pool_policy', lambda _: {'maximum_residents': 8})
    monkeypatch.setattr(module, 'registrations', lambda _: rows)
    poisoned = {'bad'}
    seen = []
    def observe(declaration, **kwargs):
        assert kwargs['query'] is False
        rid = declaration['path']
        return {'declaration': {'mode': 'MATCH_PROJECT'}, 'identity': {'resident': rid}, 'session_capacity': 2,
                'resident_id': rid, 'registration': {'path': rid + '-event'}, 'preparation_only': False}
    class Client:
        def __init__(self, identity, timeout):
            self.identity = identity
            assert timeout == 2
        def call(self, operation):
            assert operation == 'status'
            rid = self.identity['resident']
            seen.append(rid)
            return {'resident': True, 'state': 'poisoned' if rid in poisoned else 'idle',
                    'poisoned': {'synthetic_fault': True} if rid in poisoned else None,
                    'active_claims': [], 'sessions': {}, 'available_session_slots': [0, 1], 'inflight': None}
    monkeypatch.setattr(module, 'admitted_resident', observe)
    monkeypatch.setattr(module, 'admin_client', lambda _, identity, *, timeout: Client(identity, timeout))
    result = module.healthy_residents({'synthetic_policy': True})
    assert result['status'] == 'ready' and set(result['available']) == {'healthy'}
    assert [x['resident_id'] for x in result['deferred']] == ['bad']
    assert seen == ['bad', 'healthy']
    poisoned.add('healthy')
    waiting = module.healthy_residents({'synthetic_policy': True})
    assert waiting['status'] == 'waiting' and waiting['reason'] == 'no_healthy_registered_resident'
    assert not waiting['available'] and len(waiting['deferred']) == 2
    def corrupt(_):
        raise ValueError('synthetic immutable registration digest mismatch')
    monkeypatch.setattr(module, 'registrations', corrupt)
    before = list(seen)
    with pytest.raises(module.SharedPoolIntegrityError, match='Immutable pool evidence'):
        module.healthy_residents({'synthetic_policy': True})
    assert seen == before
    write_new(STAGE / 'control-receipt.json', {'version': 'v054-deferred-live-pool-CPU-control-r1',
        'passed': True, 'one_bad_one_healthy_preserves_healthy_dispatch': True,
        'all_bad_waits_without_global_cancellation': True, 'immutable_corruption_is_shared_stop': True,
        'actual_model_calls': 0, 'actual_admin_requests': 0, 'services_modified': False,
        'formal_slots_claimed': 0, 'source': reference(SOURCE)})
