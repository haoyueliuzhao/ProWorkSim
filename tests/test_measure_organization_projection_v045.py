"""Finite synthetic JSON controls for the v045 interface binding only.

The character-count fixture is not the model tokenizer; there is no SDK,
model, business acceptance, old trajectory replay, or shared module mutation.
"""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path

import pytest

from proworksim.software_organization_v045 import INTERFACE_REVISION
from proworksim.storage import digest, json_bytes
from scripts import measure_organization_feedback_v044 as old
from scripts import measure_organization_projection_v045 as projection
from scripts import measure_organization_feedback_v045r1 as revision
from test_organization_feedback_v044 import fixture, project, save

ROOT = Path(__file__).resolve().parents[1]


def rebound_fixture(tmp_path, marker):
    value = fixture(tmp_path)
    original = copy.deepcopy(value.original)
    body = json.loads(original['messages'][1]['content'])
    body['observation']['interface_revision'] = marker
    original['messages'][1]['content'] = json.dumps(body)
    selected, details = project(original, value.ledger)
    for name, item in (('original-request.json', original), ('selected-request.json', selected), ('projection.json', details)):
        save(value.folder / name, item)
    value.original, value.selected, value.projection = original, selected, details
    value.call.update(selected_request_sha256=digest(json_bytes(selected)), input_ids_sha256=details['input_ids_sha256'])
    value.record['reservation']['preparation'].update(original_request_sha256=digest(json_bytes(original)),
        prompt_tokens=details['selected_prompt_tokens'])
    value.record['charge']['reported_usage']['prompt_tokens'] = details['selected_prompt_tokens']
    return value


def audit(module, value):
    return module.audit_projection(value.call, value.record, value.initial, value.assignments, value.ledger)


def test_projection_copy_changes_only_the_strict_interface_constant():
    before = (ROOT / 'scripts/measure_organization_feedback_v044.py').read_text()
    after = (ROOT / 'scripts/measure_organization_projection_v045.py').read_text()
    assert after == before.replace('PAGE_INTERFACE = "member-private-exact-test-pages-v0.42"',
                                  'PAGE_INTERFACE = "shared-facts-neutral-organization-regimes-v0.45"')
    assert projection.PAGE_INTERFACE == INTERFACE_REVISION
    assert old.PAGE_INTERFACE == 'member-private-exact-test-pages-v0.42'


def test_wrapper_keeps_v045_retirement_and_all_measurement_logic_exact():
    before = (ROOT / 'scripts/measure_organization_feedback_v045.py').read_text()
    after = (ROOT / 'scripts/measure_organization_feedback_v045r1.py').read_text()
    expected = before.replace('from scripts import measure_organization_feedback_v044 as previous',
                              'from scripts import measure_organization_projection_v045 as previous')
    expected = expected.replace('VERSION = "organization-feedback-opportunities-v0.45"',
                                'VERSION = "organization-feedback-opportunities-v0.45r1"')
    assert after == expected
    assert revision.previous is projection


@pytest.mark.parametrize('marker', [INTERFACE_REVISION, 'member-private-exact-test-pages-v0.42', 'unrecognized-world'])
def test_v045_binding_accepts_only_its_declared_interface(tmp_path, marker):
    result = audit(projection, rebound_fixture(tmp_path, marker))
    if marker == INTERFACE_REVISION:
        assert result['status'] == 'verified' and result['issues'] == []
    else:
        assert result['status'] == 'violation'
        assert result['issues'] == ['old_or_missing_paged_world_interface']


def test_parallel_old_and_new_measurements_do_not_change_each_others_binding(tmp_path):
    old_value = fixture(tmp_path / 'old')
    new_value = rebound_fixture(tmp_path / 'new', INTERFACE_REVISION)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(audit, old, old_value), pool.submit(audit, projection, new_value)]
        assert [future.result()['status'] for future in futures] == ['verified', 'verified']
    assert audit(old, new_value)['status'] == 'violation'
    assert audit(projection, old_value)['status'] == 'violation'


def test_correct_interface_never_exempts_a_changed_actual_request(tmp_path):
    value = rebound_fixture(tmp_path, INTERFACE_REVISION)
    changed = copy.deepcopy(value.selected)
    changed['messages'][0]['content'] = 'Changed input despite a valid interface label'
    save(value.folder / 'selected-request.json', changed)
    result = audit(projection, value)
    assert result['status'] == 'violation'
    assert 'request_or_actual_input_hash_mismatch' in result['issues']
