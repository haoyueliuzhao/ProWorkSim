"""Recovery is a fixed resource-failure suffix, never a new success selection."""

import copy

import pytest

from scripts.recover_collaboration_carrier_v026 import remaining_slots


def test_recovery_preserves_closed_prefix_and_fixed_seed_order():
    slots = [{'slot_id': str(i), 'sampling_seed': 100+i} for i in range(8)]
    progress = [{**s, 'status': 'closed' if i<3 else 'started'} for i,s in enumerate(slots[:4])]
    result = remaining_slots(slots, progress)
    assert result == slots[3:]
    result[0]['sampling_seed'] = -1
    assert slots[3]['sampling_seed'] == 103
    altered = copy.deepcopy(progress)
    altered[-1]['status'] = 'closed'
    with pytest.raises(ValueError, match='interrupted prefix'):
        remaining_slots(slots, altered)
    with pytest.raises(ValueError, match='interrupted prefix'):
        remaining_slots(slots, progress[::-1])
