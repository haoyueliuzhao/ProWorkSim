"""Saved selected-combination binding and fail-stop controls; no model loads."""
import copy
import json

import pytest

from proworksim.candidate_runtime_v017 import candidate_profile
from proworksim.storage import read_json
from scripts.harness_report_v017 import select_combination
from scripts.retail_project_model_v017 import execute, reference, validate_binding


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def fixture(tmp_path):
    models = []
    for index, candidate in enumerate(('qwen35-9b', 'qwen38-27b')):
        root = tmp_path / candidate
        model = root / 'weights'
        model.mkdir(parents=True)
        manifest = model / 'manifest.json'
        write(manifest, {'fixture': 'no actual weight tensors'})
        identity = {'policy_version': 'fixture-0', 'adapter_sha256': 'a' * 64,
                    'base_manifest_sha256': reference(manifest)['sha256']}
        profile = candidate_profile('qwen3.5-9b' if index == 0 else 'qwen3.8-27b', devices=2 if index == 0 else 4)
        protocol = {'version': 'harness-study-v0.17', 'candidate_id': candidate,
                    'runtime': {'kind': 'qwen_hybrid_diagnostics', 'profile': profile},
                    'recipe': {'seed': 2026093041, 'temperature': 0.7, 'max_length': 16384, 'max_output_tokens': 2048}}
        owner = {'recipe': protocol['recipe'], 'inference_profile': profile, 'initial_actor_identity': identity,
                 'base_identity': {'path': str(model), 'manifest': reference(manifest)}}
        write(root / 'launch-protocol.json', protocol)
        write(root / 'launch.json', {'end': 1.0, 'exit_code': 0, 'command': ['runner', '--output', str(root)]})
        write(root / 'resident/owner.json', owner)
        write(root / 'online/report.json', {'actor_steps_total': 0, 'critic_steps_total': 0, 'final_actor_identity': identity})
        source = {'code_commit': 'f' * 40, 'code_dirty': False, 'source_tree_sha256': 'c' * 64}
        arms = [{'candidate_id': candidate, 'harness': h, 'eligible': True,
                 'complete_implement_review': 8-index-j, 'complete_pair_chain': 4-index,
                 'allocated_device_seconds': 100.0 + 100 * index + 10 * j}
                for j, h in enumerate(('native_v15', 'openhands_v16'))]
        models.append({'candidate_id': candidate, 'ended': True, 'arms': arms,
                       'fresh_shared_owner': True, 'actor_steps_total': 0, 'critic_steps_total': 0,
                       'actual_initial_actor_identity': identity, 'actual_final_actor_identity': identity,
                       'source_before': source, 'source_after': source,
                       'references': {label: reference(root / name) for label, name in
                                      [('protocol', 'launch-protocol.json'), ('launch', 'launch.json'),
                                       ('owner', 'resident/owner.json'), ('runner', 'online/report.json')]}})
    report = {'version': 'harness-readonly-report-v0.17', 'models': models, 'selection': select_combination(models)}
    path = tmp_path / 'selection-report.json'
    write(path, report)
    kwargs = {'model': tmp_path / 'qwen35-9b/weights', 'weight_manifest': tmp_path / 'qwen35-9b/weights/manifest.json', 'harness': 'native_v15'}
    return path, report, kwargs


def test_exact_final_selection_required_and_resource_change_is_explicit(tmp_path):
    path, report, kwargs = fixture(tmp_path)
    result = validate_binding(path, **kwargs)
    assert result['passed'] and result['selected_candidate'] == 'qwen35-9b'
    assert result['model_loads_during_validation'] == 0
    wrapper_path = tmp_path / 'selection.json'
    write(wrapper_path, {**report['selection'], 'report_ref': reference(path)})
    assert validate_binding(wrapper_path, **kwargs)['selected_candidate'] == 'qwen35-9b'
    with pytest.raises(ValueError, match='not selected'):
        validate_binding(path, **kwargs, candidate='qwen38-27b')
    with pytest.raises(ValueError, match='selected harness'):
        validate_binding(path, **{**kwargs, 'harness': 'openhands_v16'})
    with pytest.raises(ValueError, match='weight manifest'):
        validate_binding(path, **{**kwargs, 'weight_manifest': tmp_path / 'qwen38-27b/weights/manifest.json'})
    changed = copy.deepcopy(result['profile'])
    changed['devices'] = 1
    profile_path = tmp_path / 'placement.json'
    write(profile_path, changed)
    with pytest.raises(ValueError, match='explicit reason'):
        validate_binding(path, **kwargs, runtime_profile=profile_path)
    moved = validate_binding(path, **kwargs, runtime_profile=profile_path, placement_reason='Explicit fixture resource allocation')
    assert moved['placement_revision']['effective_devices'] == 1
    changed['temperature'] = 0.9
    write(profile_path, changed)
    with pytest.raises(ValueError, match='Only explicitly declared'):
        validate_binding(path, **kwargs, runtime_profile=profile_path, placement_reason='Cannot change sampling')
    report['models'][1]['ended'] = False
    write(path, report)
    with pytest.raises(ValueError, match='Both actual H1'):
        validate_binding(path, **kwargs)


def test_unknown_collector_result_stops_without_retry_or_zero_fill(tmp_path, monkeypatch):
    import proworksim.retail_project_collection as collection
    calls = []

    def fail(owner, case_id, folder, *, harness):
        calls.append(case_id)
        folder.mkdir()
        return {'assessment': {'eligible': False, 'reward': None, 'completed': None, 'reason': 'worker_error'},
                'termination': {'status': 'environment_error'}, 'opportunities': 1, 'actions': 0}

    monkeypatch.setattr(collection, 'collect_project_episode', fail)

    class FakeOwner:
        actor_steps = critic_steps = 0

        def freeze_identity(self):
            return {'fixture': 'unchanged'}

        def capture_evaluation_state(self):
            return 'fixture-state'

        def begin_window(self, window):
            calls.append(window)

        def reseed(self, seed, *, label):
            pass

        def finish_evaluation(self, entries, output):
            assert entries == []
            return {'actor_optimizer_steps': 0, 'critic_optimizer_steps': 0}

        def finish_evaluation_guard(self, snapshot):
            assert snapshot == 'fixture-state'
            return {'learning_unchanged': True, 'rng_restored_exactly': True}

    root = tmp_path / 'evaluation'
    root.mkdir()
    slots = [{'slot_id': 'case-' + str(i), 'case_id': 'fixture-case', 'sampling_seed': i} for i in range(4)]
    result = execute(FakeOwner(), {'selected_candidate': 'fixture', 'selected_harness': 'native_v15'}, root, {'slots': slots})
    assert result['status'] == 'stopped_unknown_execution'
    assert len(result['episodes']) == 1 and calls == ['case-0', 'fixture-case']
    assert result['episodes'][0]['assessment']['reward'] is None
    assert result['unstarted_slots'] == ['case-1', 'case-2', 'case-3']
    assert read_json(root / 'case-0/evaluation-guard.json')['learning_unchanged'] is True
