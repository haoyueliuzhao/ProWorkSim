"""Summarize saved resource samples without probing or changing running jobs."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path


def csv_rows(sample, field):
    record = sample.get(field, {})
    if record.get("returncode") != 0:
        return []
    return list(csv.reader(io.StringIO(record.get("stdout", "")), skipinitialspace=True))


def summarize(launch_path, study_pids):
    launch_path = Path(launch_path)
    launch_bytes = launch_path.read_bytes()
    launch = json.loads(launch_bytes)
    samples_path = launch_path.with_name(launch_path.name.replace(".launch.json", ".resources.jsonl"))
    raw = samples_path.read_bytes() if samples_path.exists() else b""
    complete_lines = raw.splitlines(keepends=True)
    incomplete_tail = bool(complete_lines and not complete_lines[-1].endswith(b"\n"))
    if incomplete_tail:
        complete_lines.pop()
    samples = [json.loads(line) for line in complete_lines if line.strip()]
    pid = str(launch["pid"])
    own_memory, device_memory, utilization, rss = [], [], [], []
    same_device_samples = other_project_samples = 0
    competitors, other_project_pids = set(), set()
    failed_gpu_queries = failed_process_queries = failed_host_queries = 0
    for sample in samples:
        failed_gpu_queries += sample.get("gpus", {}).get("returncode") != 0
        failed_process_queries += sample.get("processes", {}).get("returncode") != 0
        failed_host_queries += sample.get("host", {}).get("returncode") != 0
        processes = csv_rows(sample, "processes")
        mine = [row for row in processes if len(row) >= 3 and row[1] == pid]
        own_devices = {row[0] for row in mine}
        own_memory.extend(int(row[2]) for row in mine if row[2].isdigit())
        sharing = {row[1] for row in processes if len(row) >= 3 and row[0] in own_devices and row[1] != pid}
        external = {row[1] for row in processes if len(row) >= 3 and row[1] not in study_pids}
        same_device_samples += bool(sharing)
        other_project_samples += bool(external)
        competitors.update(sharing)
        other_project_pids.update(external)
        for row in csv_rows(sample, "gpus"):
            if len(row) >= 5 and row[1] in own_devices:
                device_memory.append(int(row[2]))
                utilization.append(int(row[4]))
        for line in sample.get("host", {}).get("stdout", "").splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[0] == pid and fields[1].isdigit():
                rss.append(int(fields[1]))
    return {
        "name": launch_path.name.removesuffix(".launch.json"), "pid": int(pid),
        "visible_devices": launch.get("CUDA_VISIBLE_DEVICES"),
        "status": "exited" if "exit_code" in launch else "launch_has_no_final_record",
        "exit_code": launch.get("exit_code"), "elapsed_process_seconds": launch.get("elapsed"),
        "sample_count": len(samples), "incomplete_tail_excluded": incomplete_tail,
        "first_sample_time": samples[0]["time"] if samples else None,
        "last_sample_time": samples[-1]["time"] if samples else None,
        "sampled_own_gpu_peak_MiB": max(own_memory, default=None),
        "sampled_own_host_rss_peak_KiB": max(rss, default=None),
        "sampled_device_memory_peak_MiB": max(device_memory, default=None),
        "sampled_device_utilization_range_percent": [min(utilization), max(utilization)] if utilization else None,
        "same_device_other_process_samples": same_device_samples,
        "same_device_other_process_pids": sorted(competitors),
        "other_project_on_any_device_samples": other_project_samples,
        "other_project_on_any_device_pids": sorted(other_project_pids),
        "failed_queries": {"gpus": failed_gpu_queries, "processes": failed_process_queries, "host": failed_host_queries},
        "sources": [
            {"path": str(launch_path.resolve()), "sha256": hashlib.sha256(launch_bytes).hexdigest()},
            {"path": str(samples_path.resolve()), "sha256": hashlib.sha256(raw).hexdigest()},
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    paths = sorted(args.launch_directory.glob("*.launch.json"))
    pids = {str(json.loads(path.read_text())["pid"]) for path in paths}
    rows = [summarize(path, pids) for path in paths]
    report = {
        "version": "learning-resources-v0.14", "runs": rows,
        "completed_process_seconds_sum": sum(row["elapsed_process_seconds"] for row in rows if row["elapsed_process_seconds"] is not None),
        "scope": "Saved 15-second samples only; peaks can be missed. Process duration is not GPU compute time. Concurrent PIDs do not identify a causal slowdown. Other-project means PID absent from this launch directory; same-device sharing is listed separately. In-progress runs have no imputed final duration.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "runs": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
