"""Metadata fixture for pre-load software bindings; no Torch/model execution."""
import copy
import hashlib
import json

import pytest

from proworksim.storage import json_bytes
from scripts.build_learning_pilot_v015 import build_protocols as build_pilot
from scripts.build_software_eval_v015 import build_protocols as build_software
from scripts.software_model_v015 import main, validate_software_binding


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def _ref(path):
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'bytes': path.stat().st_size}


def _complete_n1(root, protocol, model, manifest):
    """Fixture bytes deliberately are not a loadable checkpoint; only hash read."""
    online = root / 'online'
    _write(root / 'launch-protocol.json', protocol)
    _write(online / 'protocol.json', protocol)
    identity = {'version': 'fixture', 'policy_version': protocol['condition'] + '-4',
                'base_manifest_sha256': _ref(manifest)['sha256']}
    records = []
    for index, window in enumerate(protocol['windows']):
        record = {'window_id': window['window_id'], 'mode': window['mode'], 'status': 'complete',
                  'after_actor_identity': identity}
        records.append(record)
        if index == len(protocol['windows']) - 1:
            checkpoint = online / ('window-' + str(index)) / 'checkpoint'
            checkpoint.mkdir(parents=True)
            (checkpoint / 'shared-state.pt').write_bytes(b'CPU metadata fixture, not a Torch checkpoint')
            metadata = {'version': 'fixture', 'state': _ref(checkpoint / 'shared-state.pt'),
                        'actor_identity': identity, 'actor_steps': 4, 'critic_steps': 4,
                        'serialized_reload_exact': True}
            _write(checkpoint / 'checkpoint.json', metadata)
            record['checkpoint'] = metadata
            guard = {'learning_unchanged': True, 'rng_restored_exactly': True}
            record['evaluation_guard'] = guard
            _write(checkpoint.parent / 'evaluation-guard.json', guard)
    report = {'version': 'fixture', 'status': 'complete', 'mode': 'online', 'windows': records,
              'protocol_sha256': hashlib.sha256(json_bytes(protocol)).hexdigest(),
              'final_actor_identity': identity, 'actor_steps_total': 4, 'critic_steps_total': 4}
    _write(online / 'report.json', report)
    _write(root / 'resident/owner.json', {'version': 'fixture', 'recipe': protocol['recipe'], 'base_identity': {'path': str(model.resolve()), 'manifest': _ref(manifest)}})
    return checkpoint


def test_initial_and_both_final_bindings_reject_wrong_sources_before_any_model_load(tmp_path):
    model = tmp_path / 'public-model'
    model.mkdir()
    weights = tmp_path / 'weight-manifest.json'
    _write(weights, {'version': 'explicit-cpu-fixture'})
    screen = {'version': 'fixture', 'candidate_id': 'fixture-model', 'runtime': {'kind': 'fixture-do-not-load'},
              'recipe': {'seed': 1}}
    pilot = build_pilot(screen)
    protocols, _ = build_software(screen)
    initial, mc, rtg = [protocols['software-' + node + '.json'] for node in ('initial', 'mc-final', 'rtg-final')]
    mc_checkpoint = _complete_n1(tmp_path / 'n1-mc', pilot['pilot-mc.json'], model, weights)
    rtg_checkpoint = _complete_n1(tmp_path / 'n1-rtg', pilot['pilot-rtg.json'], model, weights)

    def check(protocol, checkpoint):
        return validate_software_binding(protocol, restore_checkpoint=checkpoint, model=model, weight_manifest=weights)

    for protocol, checkpoint in ((initial, None), (mc, mc_checkpoint), (rtg, rtg_checkpoint)):
        result = check(protocol, checkpoint)
        assert result['passed'] and result['model_loads'] == result['tensor_loads'] == 0
        assert result['evaluation_episodes'] == 3 and result['training_episodes'] == 0
    for protocol, checkpoint, message in (
        (initial, mc_checkpoint, 'forbids any restored'),
        (mc, None, 'requires the matching'),
        (mc, rtg_checkpoint, 'matching N1 pilot condition'),
        (rtg, mc_checkpoint, 'matching N1 pilot condition'),
    ):
        with pytest.raises(ValueError, match=message):
            check(protocol, checkpoint)
    for alter in ('seed', 'budget', 'count', 'case', 'binding'):
        modified = copy.deepcopy(initial)
        if alter == 'seed':
            modified['episodes'][1]['sampling_seed'] += 9
        elif alter == 'budget':
            modified['role_decision_limits']['implementer'] = 19
        elif alter == 'count':
            modified['episodes'].append(copy.deepcopy(modified['episodes'][0]))
        elif alter == 'case':
            modified['fixed_case']['case_id'] = 'different'
        else:
            modified['checkpoint_binding']['restore_checkpoint_forbidden'] = False
        with pytest.raises(ValueError):
            check(modified, None)

    source_root = mc_checkpoint.parent.parent.parent
    launch_path = source_root / 'launch-protocol.json'
    online_protocol_path = source_root / 'online/protocol.json'
    report_path = source_root / 'online/report.json'
    original_launch, original_report = launch_path.read_bytes(), report_path.read_bytes()
    for stage in ('screen', 'bridge'):
        changed = json.loads(original_launch)
        changed['stage'] = stage
        _write(launch_path, changed)
        _write(online_protocol_path, changed)
        with pytest.raises(ValueError, match='matching N1 pilot condition'):
            check(mc, mc_checkpoint)
    launch_path.write_bytes(original_launch)
    online_protocol_path.write_bytes(original_launch)
    restored = source_root / 'restored-checkpoint.json'
    _write(restored, {'source': 'N0 bridge'})
    with pytest.raises(ValueError, match='restored an external'):
        check(mc, mc_checkpoint)
    restored.unlink()
    for mutate in ('incomplete', 'missing_window', 'identity', 'state_digest', 'guard'):
        changed = json.loads(original_report)
        if mutate == 'incomplete':
            changed['status'] = 'stopped_probability_mismatch'
        elif mutate == 'missing_window':
            changed['windows'].pop(0)
        elif mutate == 'identity':
            changed['final_actor_identity'] = {'policy_version': 'different'}
        elif mutate == 'state_digest':
            changed['windows'][-1]['checkpoint']['state']['sha256'] = 'incorrect'
        else:
            changed['windows'][-1]['evaluation_guard']['learning_unchanged'] = False
        _write(report_path, changed)
        with pytest.raises(ValueError):
            check(mc, mc_checkpoint)
    report_path.write_bytes(original_report)
    earlier = source_root / 'online/window-0/checkpoint'
    earlier.mkdir(parents=True)
    with pytest.raises(ValueError, match='earlier/best'):
        check(mc, earlier)
    state_path = mc_checkpoint / 'shared-state.pt'
    original_state = state_path.read_bytes()
    state_path.write_bytes(original_state + b'changed')
    with pytest.raises(ValueError, match='path/hash/size'):
        check(mc, mc_checkpoint)
    state_path.write_bytes(original_state)
    assert check(mc, mc_checkpoint)['passed']

    # Real CLI rejects before its deliberately un-loadable runtime is imported.
    protocol_path = tmp_path / 'initial.json'
    _write(protocol_path, initial)
    output = tmp_path / 'rejected-cli'
    with pytest.raises(ValueError, match='forbids any restored'):
        main(['--protocol', str(protocol_path), '--model', str(model), '--weight-manifest', str(weights),
              '--output', str(output), '--restore-checkpoint', str(mc_checkpoint)])
    assert json.loads((output / 'report.json').read_text())['status'] == 'rejected_binding'
    assert not (output / 'resident').exists()
