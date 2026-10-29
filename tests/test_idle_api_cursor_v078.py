import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('idle_cursor_v078', ROOT/'tools/reconcile_idle_api_cursor_v078.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def fixture():
    slot = 'v064:fixture:DEEPSEEK_PROJECT_B5000K:1'
    cursor = {'unix': 100, 'failure': None, 'active_generation': [slot], 'generation': {},
              'scores': {'old': {'preserved': True}}, 'deliveries': {}, 'pending_generation': ['unstarted'],
              'active_grading': [], 'pending_scores': [], 'pending_controls': []}
    progress = {'unix': 120, 'phase': 'waiting', 'capacity_wait_reason': 'invalid_concurrency_control',
                'effective_generation_limit': 0, 'actual_generation_futures': 0,
                'active_generation': 0, 'failure': None}
    return slot, cursor, progress


def test_idle_requires_fresh_pause_and_no_physical_or_remote_work():
    slot, cursor, progress = fixture()
    assert tool.require_idle(progress, cursor, [], 0, {'desired': 0}, now=121, gate_unix=110) == [slot]
    cases = [({'phase': 'running'}, [], 0, 121), ({'actual_generation_futures': 1}, [], 0, 121),
             ({}, [{'spec': {'slot_id': slot}}], 0, 121), ({}, [], 1, 121), ({}, [], 0, 200)]
    for change, active, reserved, now in cases:
        with pytest.raises(ValueError):
            tool.require_idle({**progress, **change}, cursor, active, reserved, {'desired': 0}, now=now, gate_unix=110)


def test_result_requires_exact_identity_real_close_event_and_cleanup():
    slot, _, _ = fixture()
    row = {'slot_id': slot, 'model_key': 'DEEPSEEK', 'input_plus_output_tokens': 5_000_000,
           'instance_id': 'fixture', 'configuration': {'source': 'same'}, 'condition_id': 'project', 'seed': 1}
    result = {**row, 'status': 'closed', 'automatic_replay': False, 'model_dispatch_started': True,
              'model_calls': 4, 'retained_objects': []}
    quiet = {'quiescent': True, 'cleanup_errors': [], 'create_result_unknown': False,
             'all_owned_objects_removed': True, 'retained_objects': [],
             'removed_roles': ['actor', 'controller', 'volume']}
    events = [{'slot_id': slot, 'kind': 'generation_finished', 'status': 'closed', 'unix': 115}]
    assert tool.validate_result(row, {}, result, quiet, events, cursor_unix=100, progress_unix=120)
    for changed_result, changed_quiet, changed_events in [({**result, 'seed': 2}, quiet, events),
            (result, {**quiet, 'quiescent': False}, events), (result, quiet, []),
            (result, quiet, [{**events[0], 'unix': 99}])]:
        with pytest.raises(ValueError):
            tool.validate_result(row, {}, changed_result, changed_quiet, changed_events, cursor_unix=100, progress_unix=120)


def test_reconciliation_only_adds_closed_record_and_removes_matching_active():
    slot, cursor, _ = fixture()
    original = copy.deepcopy(cursor)
    replacement = {slot: {'status': 'closed', 'result': {'original': True}}}
    revised = tool.revised_cursor(cursor, replacement, {'evidence': True}, now=121)
    assert cursor == original
    assert revised['active_generation'] == [] and revised['generation'] == replacement
    for key in ('scores', 'deliveries', 'pending_generation', 'active_grading', 'pending_scores', 'pending_controls'):
        assert revised[key] == cursor[key]
    with pytest.raises(ValueError):
        tool.revised_cursor(cursor, {'foreign': {}}, {}, now=121)


def test_apply_archives_original_and_does_not_touch_candidate_or_score(tmp_path, monkeypatch):
    slot, cursor, progress = fixture()
    api, claims, out = tmp_path/'api', tmp_path/'claims', tmp_path/'audit'
    api.mkdir()
    claims.mkdir()
    (claims/'allocation.lock').touch()
    raw = json.dumps(cursor).encode()
    (api/'cursor.json').write_bytes(raw)
    control = b'{"desired":0}\n'
    events = b'[]\n'
    (api/'concurrency-control.json').write_bytes(control)
    (api/'events.jsonl').write_bytes(events)
    candidate = tmp_path/'candidate.patch'
    candidate.write_bytes(b'original candidate')
    score = tmp_path/'score.json'
    score.write_bytes(b'{"resolved":false}')
    monkeypatch.setattr(tool, 'API_ROOT', api)
    monkeypatch.setattr(tool, 'CURSOR', api/'cursor.json')
    monkeypatch.setattr(tool, 'CLAIMS', claims)
    monkeypatch.setattr(tool, 'OUT', out)
    monkeypatch.setattr(tool.handoff, 'API_CONTROL', api/'concurrency-control.json')
    monkeypatch.setattr(tool.scope, 'require_allowed', lambda *a, **kw: {})
    monkeypatch.setattr(tool, 'inspect_locked', lambda: {'cursor': cursor, 'cursor_raw': raw,
        'progress_raw': json.dumps(progress).encode(), 'control_raw': control, 'events_raw': events,
        'replacements': {slot: {'status': 'closed', 'entered': True, 'result': {'original': True}}},
        'evidence': [], 'gate': {'existing': True}})
    assert tool.execute(apply=False)['eligible'] and not out.exists()
    applied = tool.execute(apply=True)
    assert applied['status'] == 'applied'
    assert (out/'cursor-before.json').read_bytes() == raw
    revised = json.loads((api/'cursor.json').read_bytes())
    assert not revised['active_generation'] and revised['generation'][slot]['status'] == 'closed'
    assert candidate.read_bytes() == b'original candidate' and score.read_bytes() == b'{"resolved":false}'
    assert tool.execute(apply=True)['status'] == 'already_applied'
