"""Affected v045 inventory, window binding and conservative result controls."""
import copy
import json

import pytest

from proworksim.storage import digest, json_bytes
from scripts import software_organization_v045 as run
from scripts import software_organization_stop_policy_v045 as stop
from scripts import measure_organization_feedback_v045 as feedback
from test_organization_stop_policy_v044 import fixture, seal
from test_organization_feedback_v044r1 import fixture as retirement_fixture


def translate(value, replacements, seen=None):
    seen = set() if seen is None else seen
    if isinstance(value, str):
        for old, new in replacements.items():
            value = value.replace(old, new)
        return value
    if not isinstance(value, (dict, list)) or id(value) in seen:
        return value
    seen.add(id(value))
    if isinstance(value, list):
        value[:] = [translate(v, replacements, seen) for v in value]
    else:
        for key, item in list(value.items()):
            value[key] = translate(item, replacements, seen)
        for key in ('preparation_sha256', 'state_sha256'):
            if key in value:
                seal(value, key)
    return value


def test_inventory_is_unique_balanced_and_only_new_authorized_twentyfour():
    blocks = run.assignments()
    rows = [u for group in blocks.values() for u in group]
    assert len(blocks) == 8 and len(rows) == len({u['slot_id'] for u in rows}) == 24
    assert {u['sampling_seed'] for u in rows} == {202610100451, 202610100452}
    for condition in run.CONDITIONS:
        assert sum(u['condition'] == condition for u in rows) == 8
        assert all(sum(group[pos]['condition'] == condition for group in blocks.values()) in {2, 3} for pos in range(3))
    for group in blocks.values():
        assert {u['condition'] for u in group} == set(run.CONDITIONS)
        assert len({u['first_member'] for u in group if u['condition'] != 'S1'}) == 1
        assert all(u['first_member'] == 'member_001' for u in group if u['condition'] == 'S1')
    assert run.budget_caps()['new']['total_tokens'] == 12000000
    assert run.budget_caps()['optional_probe_budget_authorized'] is False
    assert run.GPU_ORDER == (3, 4, 5, 7)


def result_rows():
    return [{**u, 'status': 'closed', 'R': int(u['condition'] != 'S1'), 'submitted': u['condition'] != 'S1'}
            for group in run.assignments().values() for u in group]


def test_complete_comparison_uses_eight_blocks_and_missing_result_stays_null():
    rows = result_rows()
    value = run.summarize_rows(rows)
    assert value['full_inventory_mean_contrasts'] == {'F2_minus_S1': 1.0, 'O3_minus_F2': 0.0}
    assert value['by_condition']['F2']['cost']['closed_worker_gpu_seconds'] is None
    rows[0].update(status='not_started', R=None, submitted=None)
    assert all(v is None for v in run.summarize_rows(rows)['full_inventory_mean_contrasts'].values())
    assert run.summarize_rows(rows)['by_condition']['S1']['mean_R'] is None


@pytest.mark.parametrize('fault', ['duplicate', 'seed', 'condition'])
def test_invalid_inventory_is_rejected_before_indexing(fault):
    rows = result_rows()
    if fault == 'duplicate':
        rows[-1] = copy.deepcopy(rows[0])
    elif fault == 'seed':
        rows[-1]['sampling_seed'] += 1
    else:
        rows[-1]['condition'] = 'F2' if rows[-1]['condition'] != 'F2' else 'S1'
    with pytest.raises(ValueError):
        run.summarize_rows(rows)


@pytest.mark.parametrize(('R', 'submitted'), [(0, False), (0, True), (1, True)])
def test_new_window_safe_local_context_has_same_scope_and_preserves_feedback(R, submitted):
    values = translate(fixture(R=R, submitted=submitted), {'organization-v044:': 'organization-v045:'})
    before = copy.deepcopy(values)
    result = stop.assess_records(**values)
    assert result['decision'] == 'continue'
    assert result['context_blocked_feedback_ids'] == ['feedback-2']
    assert values == before


def test_old_window_or_actual_feedback_omission_is_not_exempted():
    assert stop.assess_records(**fixture())['decision'] == 'global_pause'
    values = translate(fixture(), {'organization-v044:': 'organization-v045:'})
    values['feedback']['mechanism_gate_inputs']['feedback_missing_from_first_actual_followup'] = ['lost']
    assert stop.assess_records(**values)['decision'] == 'global_pause'


def test_missing_new_window_evidence_remains_pending():
    values = translate(fixture(), {'organization-v044:': 'organization-v045:'})
    values['events'].pop()
    assert stop.assess_records(**values)['decision'] == 'measurement_pending'


@pytest.mark.parametrize('R', [0, 1])
def test_new_window_committed_self_retirement_is_bound_without_inventing_visibility(tmp_path, R):
    f = retirement_fixture(tmp_path, reward=R)
    old_hash = digest(json_bytes(f.body))
    seen = set()
    for name in ('row', 'state', 'result', 'evidence', 'budget', 'experience', 'body', 'returned'):
        translate(getattr(f, name), {'organization-v044:': 'organization-v045:'}, seen)
    new_hash = digest(json_bytes(f.body))
    seen = set()
    for name in ('evidence', 'budget', 'experience'):
        translate(getattr(f, name), {old_hash: new_hash}, seen)
    (f.raw / 'response.json').write_text(json.dumps({'http_status': 200, 'body': f.body}))
    proof = feedback.bind_self_retirement(f.row, state=f.state, result=f.result, evidence=f.evidence,
        budget=f.budget, inputs=f.inputs, experience=f.experience, folder=f.folder)
    assert proof['reason'] == 'voluntary_self_retirement'
    assert proof['window_id'] == 'organization-v045:fixture'
    assert proof['actual_feedback_presentation_added'] is False
    assert proof['R_used_for_classification'] is False


def test_worker_cannot_replay_or_write_outside_its_unique_output(tmp_path):
    root = tmp_path / 'run'
    name = run.WORKERS[0]
    target = root / name / 'actual'
    with pytest.raises(ValueError):
        run.validate_worker_target(root, name, root / 'elsewhere')
    target.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        run.validate_worker_target(root, name, target)
