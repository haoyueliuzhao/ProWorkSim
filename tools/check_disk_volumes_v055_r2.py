"""CPU-only accounting/refusal controls; no real queue, service or disk mutation."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from proworksim import software_benchmark_disk_volumes_v055_r2 as module
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def run():
    identities = {'primary': {'path': str(module.ROOT), 'device': 66306},
        'secondary': {'path': str(module.SECONDARY_ROOT), 'device': 66307},
        'tertiary': {'path': str(module.TERTIARY_ROOT), 'device': 66308}}
    checks = []
    def refusal(label, callback):
        try:
            callback()
        except (ValueError, RuntimeError):
            checks.append(label)
        else:
            raise AssertionError('Missing required refusal: ' + label)
    alias = deepcopy(identities)
    alias['tertiary']['device'] = alias['secondary']['device']
    refusal('tertiary_device_alias_to_secondary_refused', lambda: module.assert_distinct_devices(alias))
    alias['tertiary']['device'] = alias['primary']['device']
    refusal('tertiary_device_alias_to_primary_refused', lambda: module.assert_distinct_devices(alias))
    def fake_stat(path, **kwargs):
        device = 66308 if path.is_relative_to(module.TERTIARY_ROOT) else 66307 if path.is_relative_to(module.SECONDARY_ROOT) else 66306
        return SimpleNamespace(st_dev=device)
    with patch.object(Path, 'resolve', lambda self, **kwargs: self), patch.object(Path, 'is_dir', return_value=True), patch.object(Path, 'stat', fake_stat):
        for label in identities:
            root = Path(identities[label]['path'])
            path = root / ('runs/software-benchmark-v055/queue-r1/workers/old' if label == 'primary' else 'workers/new')
            assert module._placement({'directory': str(path)}, family='v055', volumes=identities)[0] == label
        checks.append('legacy_primary_secondary_and_new_tertiary_workers_keep_exact_device_placement')
        wrong = deepcopy(identities)
        wrong['tertiary']['device'] = 999
        refusal('unregistered_actual_device_refused', lambda: module._placement({'directory': str(module.TERTIARY_ROOT / 'workers/new')}, family='v055', volumes=wrong))
        refusal('qwen_outside_original_primary_root_refused', lambda: module._placement({'worker_directory': str(module.TERTIARY_ROOT / 'workers/qwen')}, family='v054', volumes=identities))
        old = {'rows': [{'slot': {'slot_id': 'old'}, 'generation': {'fixture_volume': 'primary'}}]}
        new = {'rows': [{'slot': {'slot_id': 'new-' + name}, 'generation': {'fixture_volume': name}} for name in identities],
            'preparation': {'cold': {'worker': {'fixture_volume': 'primary'}}}}
        snapshot = {'v054_generations': [{'slot_id': 'old', 'peak_bytes': 100}],
            'v055_generations': [{'slot_id': 'new-' + name, 'peak_bytes': value} for name, value in [('primary', 200), ('secondary', 300), ('tertiary', 400)]],
            'v055_preparations': [{'instance_id': 'cold', 'peak_bytes': 50}]}
        def placement(record, **kwargs):
            label = record['fixture_volume']
            return label, {'device': identities[label]['device']}
        grouped, errors = module.partition_snapshot(snapshot, old, new, identities, placement=placement)
        assert not errors
        assert {key: value['active_peak_reserved_bytes'] for key, value in grouped.items()} == {'primary': 350, 'secondary': 300, 'tertiary': 400}
        checks.append('three_volume_reservations_and_primary_only_preparation_partition_exactly')
        broken = deepcopy(new)
        broken['rows'][1]['generation'] = {}
        grouped, errors = module.partition_snapshot(snapshot, old, broken, identities, placement=placement)
        assert errors
        assert {key: value['active_peak_reserved_bytes'] for key, value in grouped.items()} == {'primary': 650, 'secondary': 300, 'tertiary': 700}
        checks.append('unknown_placement_blocks_and_keeps_reservation_on_all_three_devices')
        misplaced = deepcopy(new)
        misplaced['preparation']['cold']['worker']['fixture_volume'] = 'tertiary'
        _, errors = module.partition_snapshot(snapshot, old, misplaced, identities, placement=placement)
        assert errors
        checks.append('preparation_on_tertiary_refused')
    with patch.object(module.os, 'statvfs', return_value=SimpleNamespace(f_bavail=10, f_bfree=40, f_frsize=4096)):
        value = module.available_space('/CPU-fixture')
        assert value['free_bytes'] == 40960 and value['free_including_reserved_bytes'] == 163840
        assert value['filesystem_reserved_unavailable_bytes'] == 122880
    checks.append('root_reserved_ext4_blocks_excluded_from_user_available_capacity')
    with patch.object(module, '_VOLUME_REF', {'path': 'CPU-fixture'}), patch.object(module, 'load', return_value={}), patch.object(module, '_live_identity', side_effect=ValueError('controlled mount loss')):
        result = module.shared_disk_snapshot(v054_state={}, v055_state={}, target_volume='tertiary')
        assert result['metadata_error'] and result['free_bytes'] == 0 and result['silent_primary_fallback'] is False
    checks.append('mount_loss_blocks_without_silent_primary_fallback')
    assert module.POLICY is module.stages.POLICY
    assert module.STAGE_POLICY is module.stages.STAGE_POLICY
    assert module.disk_dispatch_lock is module.stages.disk_dispatch_lock
    assert module.admission is module.stages.admission
    assert module.generation_estimate is module.stages.generation_estimate
    checks.append('original_floor_priority_phase_estimates_and_shared_lock_unchanged')
    return {'version': module.VERSION + '-CPU-control', 'passed': True, 'checks': checks,
        'source': reference(module.__file__), 'control_source': reference(__file__),
        'model_calls': 0, 'GPU_loads': 0, 'formal_claims': 0, 'real_disk_io_probes': 0,
        'queue_or_service_changes': 0, 'actual_mount_qualification_performed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(json.dumps(write_new(args.output, value)))


if __name__ == '__main__':
    main()
