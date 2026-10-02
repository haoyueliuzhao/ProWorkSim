#!/usr/bin/env python3
"""Reproduce the bounded source import and CPU witnesses; never launch models.

    .venv/bin/python scripts/import_software_sources_v028.py --qualify
    .venv/bin/python scripts/import_software_sources_v028.py --download

The checked-in task files are usable offline. Downloads are pinned and verified,
kept in runs/, and no Docker build, installation or training is performed.
"""
from __future__ import annotations

import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from proworksim.software_tasks_v028 import (  # noqa: E402
    ASSETS, TASK_IDS, _mutation, apply_mutation, assess, build_case,
    reference_solution, run_public_tests,
)
from proworksim.software_sources_v027 import validate_derived_tasks  # noqa: E402


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def download(run_root):
    manifest = json.loads((ASSETS / "source-manifest.json").read_text())
    items = [("dataset-shard.parquet",
              f"https://huggingface.co/datasets/{manifest['dataset']}/resolve/"
              f"{manifest['dataset_revision']}/{manifest['dataset_shard']}",
              manifest["shard_sha256"])]
    items += [(row["name"] + "-source.tar.gz", row["archive_url"], row["archive_sha256"])
              for row in manifest["rows"]]
    reports = []
    for name, url, expected in items:
        target = run_root / "downloads" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raw = target.read_bytes()
        else:
            with urllib.request.urlopen(url, timeout=90) as response:
                raw = response.read(15_000_001)
            if len(raw) > 15_000_000:
                raise ValueError("Download exceeds the frozen per-asset bound")
            target.write_bytes(raw)
        if sha(raw) != expected:
            raise ValueError("Pinned download hash differs: " + name)
        reports.append({"url": url, "path": str(target.resolve()),
                        "sha256": expected, "bytes": len(raw)})
    # Check complete raw selected rows against the actual fixed Parquet bytes.
    # This is metadata verification, not loading/executing downloaded code.
    import duckdb
    connection = duckdb.connect()
    selected = []
    for row in manifest["rows"]:
        query = connection.execute(
            "SELECT * FROM read_parquet(?) WHERE instance_id = ?",
            [str(run_root / "downloads/dataset-shard.parquet"), row["instance_id"]])
        names = [item[0] for item in query.description]
        matches = query.fetchall()
        if len(matches) != 1:
            raise ValueError("Original task is not unique in frozen dataset")
        actual = dict(zip(names, matches[0], strict=True))
        expected = json.loads((ASSETS / row["name"] / "original-task.json").read_text())
        if actual != expected:
            raise ValueError("Selected raw dataset task differs: " + row["instance_id"])
        selected.append(row["instance_id"])
    connection.close()
    save(run_root / "download-report.json", {"downloads": reports, "exact_dataset_rows_verified": selected})
    return reports


def qualify_one(task_id, run_root):
    case = build_case(task_id)
    initial = case["files"]
    joint = reference_solution(task_id)
    producer = apply_mutation(initial, _mutation(task_id), reverse=True)
    consumer = dict(initial)
    consumer["consumer.py"] = joint["consumer.py"]
    traces = {"task_id": task_id, "purpose": case["purpose"], "upstream_tests": {}, "dependency": {}}
    for name, files in (("baseline", producer), ("defect", initial), ("repaired", joint)):
        traces["upstream_tests"][name] = run_public_tests(task_id, files, run_root=run_root / "sandbox")
    for name, files in (("initial", initial), ("producer_only", producer),
                        ("consumer_only", consumer), ("joint", joint)):
        traces["dependency"][name] = assess(task_id, files, run_root=run_root / "sandbox")
    manifest = json.loads((ASSETS / "source-manifest.json").read_text())
    row = next(row for row in manifest["rows"] if task_id.startswith(row["name"] + "-"))
    tests = traces["upstream_tests"]
    defect = {row["test_id"]: row["passed"] for row in tests["defect"]["tests"] or []}
    upstream_ok = (tests["baseline"]["passed"] and tests["repaired"]["passed"]
                   and all(defect.get(test) is False for test in row["selected_FAIL_TO_PASS"])
                   and all(defect.get(test) is True for test in row["selected_PASS_TO_PASS"]))
    controls = traces["dependency"]
    dependency_ok = (controls["joint"]["passed"]
                     and all(not controls[name]["passed"] for name in ("initial", "producer_only", "consumer_only"))
                     and any(not check["passed"] for check in controls["consumer_only"]["checks"]
                             if check["group"] == "consumer"))
    traces["qualification_passed"] = bool(upstream_ok and dependency_ok)
    traces["upstream_subset_passed"] = bool(upstream_ok)
    traces["dependency_controls_passed"] = bool(dependency_ok)
    save(run_root / "traces" / (task_id + ".json"), traces)
    return traces


def qualify(run_root):
    started = time.monotonic()
    partition = json.loads((ASSETS / "source-partition.json").read_text())
    tasks = [json.loads(path.read_text()) for path in sorted(ASSETS.glob("*/derived-task.json"))]
    declaration = validate_derived_tasks(partition, tasks)
    # The source admission work is three independent, CPU-limited sandboxes.
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        traces = list(pool.map(lambda task: qualify_one(task, run_root), TASK_IDS))
    docker = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                            capture_output=True, text=True, timeout=10, check=False)
    result = {"schema": "software-sources-v028-qualification", "date_utc": datetime.now(timezone.utc).isoformat(),
              "declaration_gate": declaration, "source_partition_sha256": partition["sha256"],
              "all_qualified": all(row["qualification_passed"] for row in traces),
              "tasks": traces, "wall_seconds": time.monotonic() - started,
              "model_episodes": 0, "training_updates": 0, "teacher_trajectories_used": 0,
              "docker_probe": {"returncode": docker.returncode, "stdout": docker.stdout, "stderr": docker.stderr},
              "official_docker_harness_executed": False,
              "source_adapter_sha256": sha((ROOT / "src/proworksim/software_tasks_v028.py").read_bytes()),
              "sandbox_sha256": sha((ROOT / "src/proworksim/software_sandbox.py").read_bytes()),
              "scope": "Three source CPU qualifications and scripted dependency witnesses; not policy support or allocation effects",
              "trajectory_preservation": "All raw sandbox outputs, API observations and parent comparisons retained in this report and per-task traces"}
    save(run_root / "qualification.json", result)
    print(json.dumps({"all_qualified": result["all_qualified"],
                      "tasks": [{"id": r["task_id"], "passed": r["qualification_passed"]} for r in traces],
                      "report": str(run_root / "qualification.json")}, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--qualify", action="store_true")
    parser.add_argument("--run-root", type=Path, default=ROOT / "runs/software-sources-v028/reproduction")
    args = parser.parse_args()
    args.run_root.mkdir(parents=True, exist_ok=True)
    if args.download:
        download(args.run_root)
    if args.qualify:
        return 0 if qualify(args.run_root)["all_qualified"] else 1
    if not args.download:
        parser.error("Choose --download and/or --qualify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
