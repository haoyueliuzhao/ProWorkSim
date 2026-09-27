"""Read-only reporting controls: fixed pairs, unknowns, recovery and accounting."""
import copy
import json
import sys
from pathlib import Path

import pytest

from scripts.report_learning_v023 import (
    STAGES, main, pair_evaluations, reference, summarize, training_report,
)

CATALOG = json.loads(Path('examples/retail-collaboration-v23/catalog.json').read_text())
ACTORS = {'initial': {'policy_version': 'cpu-initial'}, 'final': {'policy_version': 'cpu-final'}}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def rows(label, success=()):
    return [{**slot, 'status': 'closed', 'actor_identity': ACTORS[label],
             'initial_business_state_sha256': 'fixture-state-' + slot['case_id'],
             'evaluation_guard': {'learning_unchanged': True, 'rng_restored_exactly': True},
             'assessment': {'eligible': True, 'independent_assessability': 'known',
                'completed': i in success, 'reward': 1.0 if i in success else 0.0,
                'work_components': {'full_responsibility': i in success, 'business_product': i in success},
                'facts': {'judgments': []}, 'components': []}}
            for i, slot in enumerate(CATALOG['evaluation_slots'])]


def pair(initial, final):
    return pair_evaluations(CATALOG, initial, final, initial_actor=ACTORS['initial'], final_actor=ACTORS['final'])


def test_fixed_three_structure_macro_and_unknown_do_not_shrink_denominator():
    result = pair(rows('initial'), rows('final', range(8)))
    assert result['primary']['planned_pairs'] == 24 and result['primary']['known_pairs'] == 24
    assert result['primary']['mean_difference'] == result['structure_macro_difference'] == 1/3
    assert len(result['cases']) == 12 and all(c['planned_pairs'] == 2 for c in result['cases'])
    final = rows('final', (0,))
    final.pop()
    final[-1]['assessment']['eligible'] = False  # Default completed=False must not become a known failure.
    unknown = pair(rows('initial'), final)
    assert unknown['primary']['known_pairs'] == 22
    assert unknown['primary']['mean_difference'] is None
    assert unknown['primary']['full_denominator_bounds'] == [-1/24, 3/24]
    assert unknown['pairs'][-1]['final']['value'] is None
    assert unknown['pairs'][-2]['final']['value'] is None
    assert unknown['pairs'][1]['final']['value'] is False


def test_seed_material_and_repeated_slots_cannot_be_silently_matched():
    original = rows('final')
    for defect in ('seed', 'initial_business_state_sha256', 'duplicate'):
        changed = copy.deepcopy(original)
        if defect == 'duplicate':
            changed.append(changed[0])
        elif defect == 'seed':
            changed[0]['seed'] += 1
        else:
            changed[0][defect] += '-changed'
        with pytest.raises(ValueError):
            pair(rows('initial'), changed)


def fixture_run(tmp_path):
    root = tmp_path / 'run'
    catalog_path = tmp_path / 'catalog.json'
    write(catalog_path, CATALOG)
    plan_path = tmp_path / 'plan.json'
    write(plan_path, {'catalog': reference(catalog_path), 'external_enabled': True,
                     'resource_caps': {}, 'internal_gpu_seconds': 86400, 'external_gpu_seconds': 7200})
    write(root / 'supervisor.json', {'plan': reference(plan_path), 'status': 'running', 'source': {'fixture': True}})
    for stage in STAGES:
        write(root / stage / 'state.json', {'stage': stage, 'status': 'running', 'attempted': True,
                                           'started_at': 1, 'gpu': 2, 'pid': 123})
    for label in ('initial', 'final'):
        write(root / 'checkpoints' / f'{label}.json', {'actor_identity': ACTORS[label]})
        write(root / f'eval_{label}/actual/progress.json', rows(label))
    return root


def test_live_snapshot_refuses_terminal_output_and_closed_stop_keeps_costs(tmp_path, monkeypatch):
    root = fixture_run(tmp_path)
    snapshot = summarize(root)
    assert snapshot['report_kind'] == 'snapshot' and snapshot['final'] is False
    assert snapshot['planned_learning_effect_estimate'] is None
    output_json, output_md = tmp_path / 'result.json', tmp_path / 'result.md'
    monkeypatch.setattr(sys, 'argv', ['report', '--run', str(root), '--output-json', str(output_json),
                                    '--output-md', str(output_md), '--require-terminal'])
    with pytest.raises(ValueError, match='terminal report'):
        main()
    assert not output_json.exists() and not output_md.exists()
    supervisor = json.loads((root / 'supervisor.json').read_text())
    supervisor.update(status='closed_with_incomplete_stages', ended_at=10)
    write(root / 'supervisor.json', supervisor)
    for stage in STAGES:
        write(root / stage / 'state.json', {'stage': stage, 'status': 'stopped', 'attempted': True,
                'started_at': 1, 'ended_at': 10, 'elapsed_gpu_seconds': 9, 'exit_code': -15})
    closed = summarize(root)
    assert closed['execution_terminal'] and closed['report_kind'] == 'closed_incomplete'
    assert closed['planned_learning_effect_estimate'] is None
    assert closed['accounting']['final_gpu_seconds'] == 54  # original train + recovery both retained
    assert closed['accounting']['internal_gpu_seconds'] == 36
    main()
    assert json.loads(output_json.read_text())['final'] is False
    assert 'closed_incomplete' in output_md.read_text()


def test_recovery_uses_one_progress_and_original_window_artifact_roots(tmp_path):
    root = tmp_path / 'run'
    old = root / 'train/actual/window-0'
    current = root / 'train_recovery/actual'
    contract = CATALOG['training_windows'][0]
    completed_slots = [{**slot, 'status': 'closed'} for slot in contract['slots']]
    write(old / 'entries.json', [])
    write(old / 'progress.json', completed_slots)
    write(old / 'update/report.json', {'status': 'updated', 'actor_optimizer_steps': 1, 'critic_optimizer_steps': 1})
    write(old / 'work-signals.json', {'fixture_original_signal': True})
    original = [{'window_id': contract['window_id'], 'window_index': 0, 'status': 'closed',
                 'entries': reference(old / 'entries.json')}]
    write(root / 'train/actual/training-progress.json', original)
    write(current / 'training-progress.json', original)
    write(root / 'training-complete.json', {'progress': reference(current / 'training-progress.json')})
    report = training_report(root, CATALOG)
    assert report['complete_windows'] == 1 and len(report['windows']) == 4
    assert report['recovery_reuses_completed_windows_not_additional_samples']
    assert report['windows'][0]['work_signals'] == {'fixture_original_signal': True}
    assert report['windows'][0]['references']['update/report.json']['path'] == str((old / 'update/report.json').resolve())
