import json

from scripts.learning_resources_v015 import resource_report


def test_multidevice_cost_and_memory_are_not_single_process_or_sum_of_peaks(tmp_path):
    (tmp_path / 'case.launch.json').write_text(json.dumps({'pid': 12, 'CUDA_VISIBLE_DEVICES': '1,2', 'elapsed': 10, 'exit_code': 0}))
    records = []
    for stamp, x, y in [(1, 30, 10), (2, 20, 40)]:
        records.append({'time': stamp, 'pid': 12,
            'processes': {'returncode': 0, 'stdout': f'GPU-A, 12, {x}, python\nGPU-B, 12, {y}, python\nGPU-C, 99, 7, other'},
            'gpus': {'returncode': 0, 'stdout': '1, GPU-A, 32, 80, 90\n2, GPU-B, 44, 80, 85'},
            'host': {'returncode': 0, 'stdout': '12 100 1000 100 elapsed python'}})
    (tmp_path / 'case.resources.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in records))
    report = resource_report(tmp_path)
    row = report['runs'][0]
    assert report['completed_process_seconds'] == 10
    assert report['completed_allocated_device_seconds'] == 20
    assert row['sampled_own_per_device_peak_MiB'] == {'GPU-A': 30, 'GPU-B': 40}
    assert row['sampled_simultaneous_own_total_peak_MiB'] == 60
    assert row['same_device_other_process_samples'] == 0
    assert row['unregistered_process_on_any_device_samples'] == 2
