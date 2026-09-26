"""Read saved per-device samples and declared allocation, never infer GPU compute."""

import argparse
import json
from pathlib import Path

from scripts.learning_resources_v014 import csv_rows, summarize


def resource_report(launch_directory):
    paths = sorted(Path(launch_directory).glob('*.launch.json'))
    pids = {str(json.loads(p.read_text())['pid']) for p in paths}
    runs = []
    for path in paths:
        row = summarize(path, pids)
        row['unregistered_process_on_any_device_samples'] = row.pop('other_project_on_any_device_samples')
        row['unregistered_process_on_any_device_pids'] = row.pop('other_project_on_any_device_pids')
        declared = str(row['visible_devices']).split(',')
        if any(not part.strip().isdigit() for part in declared):
            raise ValueError('This study records an explicit physical GPU index list')
        row['declared_accelerator_count'] = len(declared)
        row['declared_accelerator_indices'] = [int(part) for part in declared]
        row['allocated_device_seconds'] = (row['elapsed_process_seconds'] * len(declared)
                                            if row['elapsed_process_seconds'] is not None else None)
        sample_path = path.with_name(path.name.replace('.launch.json', '.resources.jsonl'))
        lines = sample_path.read_bytes().splitlines(keepends=True) if sample_path.exists() else []
        complete = [json.loads(line) for line in lines if line.endswith(b'\n')]
        peaks, max_total, seen = {}, None, set()
        for sample in complete:
            mine = [p for p in csv_rows(sample, 'processes') if len(p) >= 3 and p[1] == str(row['pid'])]
            values = []
            for device, _, memory, *_ in mine:
                if memory.isdigit():
                    amount = int(memory)
                    peaks[device] = max(peaks.get(device, 0), amount)
                    values.append(amount)
                    seen.add(device)
            if values:
                max_total = max(max_total or 0, sum(values))
        row.update(sampled_own_per_device_peak_MiB=peaks,
                   sampled_simultaneous_own_total_peak_MiB=max_total,
                   sampled_devices_seen=sorted(seen))
        runs.append(row)
    return {'version': 'learning-resources-v0.15', 'runs': runs,
        'completed_process_seconds': sum(r['elapsed_process_seconds'] for r in runs if r['elapsed_process_seconds'] is not None),
        'completed_allocated_device_seconds': sum(r['allocated_device_seconds'] for r in runs if r['allocated_device_seconds'] is not None),
        'scope': 'Allocated device-time = declared CUDA_VISIBLE_DEVICES count times process duration, including startup/CPU/I/O/idle periods. Not measured GPU kernel time, occupancy integration, FLOPs or a causal speed comparison. Sampled peaks can be missed; unknown in-progress final times are not filled. Unregistered PIDs may be other projects or this project calibration processes absent from the launcher directory, so they are not attributed to a project.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launch-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = resource_report(args.launch_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'runs': len(result['runs']), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
