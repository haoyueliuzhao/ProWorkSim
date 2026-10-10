"""New-Gamma admission cannot be replaced by old flags or engineering margin."""
import copy

import pytest

from proworksim.storage import digest
from scripts import software_organization_admission_v044 as admission
from scripts.run_ne_v021 import write


def evidence(tmp_path, monkeypatch):
    src = tmp_path / 'source'
    (src / 'scripts').mkdir(parents=True)
    (src / admission.SELF).write_text('admission fixture')
    (src / 'context.py').write_text('single candidate')
    old = tmp_path / 'previous.json'
    write(old, {'passed': True})
    monkeypatch.setattr(admission, 'validate_previous', lambda *a, **k: {'source_files': {}})
    artifact = tmp_path / 'native.json'
    write(artifact, {'input_ids': [1, 2], 'latest_feedback_retained': True})
    common = {'source_files': {'context.py': digest((src / 'context.py').read_bytes())},
              'artifact_refs': [admission.reference(artifact)], 'new_model_calls': 0,
              'new_backward_calls': 0, 'passed': True, 'protected_margin_fits': False,
              'new_acceptance_executions': 0, 'model_weights_loaded': False,
              'context_limit': 16384, 'reserved_output_tokens': 2048,
              'protected_margin_tokens': 1024, 'protected_margin_diagnostic_only': True,
              'source_unchanged_during_measurement': True}
    history = {**copy.deepcopy(common), 'version': 'software-context-replay-v0.44',
               'expected_requests': 112, 'generated_requests': 108, 'hard_rejected_requests': 4,
               'original_reproduction_passed': True, 'new_selected_hard_capacity_passed': True,
               'latest_unpresented_feedback_retained': True}
    ids = list(admission.REQUIRED_ROUTE_IDS)
    routes = {**copy.deepcopy(common), 'version': 'software-feedback-route-qualification-v0.44',
              'required_route_ids': ids, 'route_results': [{'route_id': name, 'passed': True,
                'selected_hard_capacity_passed': True, 'mechanism_checks': {'exact': True}}
                for name in ids]}
    return src, admission.reference(old), history, routes, artifact


def build(tmp_path, src, old, history, routes):
    write(tmp_path / 'history.json', history)
    write(tmp_path / 'routes.json', routes)
    return admission.build_admission(old, admission.reference(tmp_path / 'history.json'),
        admission.reference(tmp_path / 'routes.json'), source_root=src)


def test_single_margin_deficit_remains_diagnostic_and_only_releases_four(tmp_path, monkeypatch):
    src, old, history, routes, _ = evidence(tmp_path, monkeypatch)
    value = build(tmp_path, src, old, history, routes)
    assert value['passed'] is True
    assert value['layers']['engineering_margin']['required_for_admission'] is False
    assert value['layers']['model_stage']['first_block_only'] == 4
    assert value['layers']['model_stage']['release_requires_actual_first_block_mechanism_gate'] is True


@pytest.mark.parametrize('change', [
    {'expected_requests': 111}, {'hard_rejected_requests': 3},
    {'original_reproduction_passed': False}, {'new_selected_hard_capacity_passed': False},
    {'latest_unpresented_feedback_retained': False},
])
def test_missing_hard_example_or_current_feedback_never_admits(tmp_path, monkeypatch, change):
    src, old, history, routes, _ = evidence(tmp_path, monkeypatch)
    history.update(change)
    with pytest.raises(ValueError, match='v044 admission rejected'):
        build(tmp_path, src, old, history, routes)


def test_failed_or_missing_lifecycle_route_cannot_be_hidden_by_passed_flag(tmp_path, monkeypatch):
    src, old, history, routes, _ = evidence(tmp_path, monkeypatch)
    routes['route_results'][0]['mechanism_checks']['exact'] = False
    with pytest.raises(ValueError, match='mechanism evidence'):
        build(tmp_path, src, old, history, routes)


def test_stale_context_source_and_changed_native_artifact_are_rejected(tmp_path, monkeypatch):
    src, old, history, routes, artifact = evidence(tmp_path, monkeypatch)
    (src / 'context.py').write_text('changed candidate')
    with pytest.raises(ValueError, match='implementation changed'):
        build(tmp_path, src, old, history, routes)
    (src / 'context.py').write_text('single candidate')
    artifact.write_text('changed encoding')
    with pytest.raises(ValueError, match='evidence content changed'):
        build(tmp_path, src, old, history, routes)
