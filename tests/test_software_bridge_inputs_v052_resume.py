"""Only the changed counter and new remaining-inventory boundary; no SDK."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.software_bridge_inputs_v052 import validate_capture_counters
from scripts.software_bridge_inputs_v052_resume import (
    FIRST_OH, FIRST_PS1, capture_counters, remaining_inventory,
)


def test_completion_entry_is_not_a_returned_response():
    worker = SimpleNamespace(meter={'decisions': 1, 'http_attempts': 0}, _completions=1, _last_body=None)
    budget = {'decisions': 1, 'attempts': 0, 'held_tokens': 0, 'charged_tokens': 0}
    counters = capture_counters(worker, budget, 0)
    assert counters['LLM_entries'] == 1 and counters['responses'] == 0
    assert counters['harness_decisions'] == counters['team_decisions'] == 1
    assert validate_capture_counters('PS1', counters)
    worker._last_body = {'choices': []}
    with pytest.raises(ValueError):
        validate_capture_counters('PS1', capture_counters(worker, budget, 0))


def test_only_original_ten_are_available_and_old_shapes_cannot_repeat():
    project = Path(__file__).resolve().parents[1]
    rows = json.loads((project/'docs/experiments/software-bridge-v052-design.json').read_bytes())['rows']
    oh = {'slot_id': FIRST_OH}
    recovered = {'slot_id': FIRST_PS1, 'source_derived_rematerialization': True,
                 'original_provider_request_persisted': False, 'original_request_sha256': None}
    remaining = remaining_inventory(rows, oh, recovered)
    assert len(remaining) == 10
    assert not {FIRST_OH, FIRST_PS1} & {row['slot_id'] for row in remaining}
    assert remaining == rows[2:]
    bad = copy.deepcopy(rows)
    bad[-1] = bad[0]
    with pytest.raises(ValueError):
        remaining_inventory(bad, oh, recovered)
    with pytest.raises(ValueError):
        remaining_inventory(rows, {'slot_id': FIRST_PS1}, recovered)
    with pytest.raises(ValueError):
        remaining_inventory(rows, oh, {**recovered, 'original_provider_request_persisted': True})
