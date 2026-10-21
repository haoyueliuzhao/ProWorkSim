"""Seal and watch the host-only, once-only post-primary scoring pass."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
VERSION = "v054-deferred-scoring-watch-r1"
SOURCE_FILES = (
    "tools/watch_deferred_scoring_v054.py", "tools/run_deferred_scoring_v054.py",
    "src/proworksim/software_benchmark_deferred_scoring_v054.py",
    "src/proworksim/software_benchmark_candidates_v054.py",
    "src/proworksim/repository_sources_v054.py", "src/proworksim/storage.py",
    "src/proworksim/software_benchmark_scorer_v054.py",
    "src/proworksim/software_benchmark_scorer_r5_v054.py",
    "src/proworksim/software_benchmark_baseline_v054.py",
    "artifacts/software-benchmark-v054/scorer/installation-manifest-r5.json",
    "tools/run_benchmark_runtime_v054.sh", "tools/enter_benchmark_runtime_v054.sh",
)


def now():
    return datetime.now(timezone.utc).isoformat()


def ref(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def checked(value):
    path = Path(value["path"])
    if not path.is_absolute() or ref(path) != value:
        raise ValueError("Deferred watcher sealed source or policy changed")
    return path


def read(value):
    return json.loads(checked(value).read_bytes())


def write_new(path, value):
    data = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
    with Path(path).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, 0o600)
    return ref(path)


def under_runs(path):
    path = Path(path).resolve()
    path.relative_to(ROOT / "runs/software-benchmark-v054")
    return str(path)


def seal(fault_policy, primary_completion, output, destination):
    from proworksim.software_benchmark_deferred_scoring_v054 import RETRY_POLICY
    policy = json.loads(Path(fault_policy).read_bytes())
    if policy.get("deferred_scoring") != RETRY_POLICY:
        raise ValueError("Original fault policy does not authorize this exact end-stage pass")
    result = {"version": VERSION, "created_utc": now(), "repository": str(ROOT),
        "fault_policy": ref(fault_policy), "sources": [ref(ROOT / p) for p in SOURCE_FILES],
        "python_executable": str(ROOT / ".venv/bin/python"),
        "python_version": sys.version, "primary_completion": under_runs(primary_completion),
        "output": under_runs(output), "poll_seconds": 30,
        "maximum_driver_dispatches": 1, "new_model_calls": 0}
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    return write_new(destination, result)


def verify_seal(value):
    if (value.get("version") != VERSION or value.get("repository") != str(ROOT)
            or value.get("poll_seconds") != 30 or value.get("maximum_driver_dispatches") != 1
            or value.get("new_model_calls") != 0
            or value.get("python_executable") != str(ROOT / ".venv/bin/python")):
        raise ValueError("Invalid immutable watcher deployment")
    expected = {str((ROOT / name).resolve()) for name in SOURCE_FILES}
    if {row["path"] for row in value["sources"]} != expected or len(value["sources"]) != len(expected):
        raise ValueError("Incomplete deferred source seal")
    for item in value["sources"]:
        checked(item)
    checked(value["fault_policy"])
    under_runs(value["primary_completion"])
    under_runs(value["output"])


def dispatch_if_complete(value, seal_reference):
    """Return waiting/terminal status; never automatically redispatch an intent."""
    verify_seal(value)
    output = Path(value["output"])
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output, 0o700)
    terminal = output / "watch-completion.json"
    if terminal.exists():
        return json.loads(terminal.read_bytes())
    trigger = output / "watch-trigger.json"
    if trigger.exists():
        return {"status": "previous_dispatch_not_replayed", "trigger": ref(trigger),
                "new_model_calls": 0}
    marker_path = Path(value["primary_completion"])
    if not marker_path.exists():
        return {"status": "waiting_for_primary_completion", "new_model_calls": 0}
    marker_reference = ref(marker_path)
    marker = read(marker_reference)
    if marker.get("overlay_policy") != value["fault_policy"]:
        raise ValueError("Primary completion belongs to a different original fault policy")
    from proworksim.software_benchmark_deferred_scoring_v054 import run_deferred, validate_primary
    validate_primary(marker)
    trigger_reference = write_new(trigger, {"version": VERSION, "seal": seal_reference,
        "primary_completion": marker_reference, "dispatched_utc": now(), "new_model_calls": 0})
    # Recheck sources after the terminal gate, immediately before execution.
    verify_seal(value)
    result = run_deferred(marker_path, output)
    body = {"version": VERSION, "status": "deferred_driver_finished", "seal": seal_reference,
            "trigger": trigger_reference, "summary": result, "completed_utc": now(), "new_model_calls": 0}
    write_new(terminal, body)
    return body


def watch(path, expected_sha):
    seal_reference = ref(path)
    if seal_reference["sha256"] != expected_sha:
        raise ValueError("The systemd launcher seal SHA changed")
    value = read(seal_reference)
    verify_seal(value)
    output = Path(value["output"])
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (output / "watch.lock").open("a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            result = dispatch_if_complete(value, seal_reference)
            if result["status"] != "waiting_for_primary_completion":
                return result
            if not (output / "watch-waiting.json").exists():
                write_new(output / "watch-waiting.json", {"version": VERSION, **result,
                    "seal": seal_reference, "since_utc": now(), "poll_seconds": 30})
            time.sleep(30)


def main():
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    build = actions.add_parser("seal")
    build.add_argument("--fault-policy", type=Path, required=True)
    build.add_argument("--primary-completion", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--seal", type=Path, required=True)
    monitor = actions.add_parser("watch")
    monitor.add_argument("--seal", type=Path, required=True)
    monitor.add_argument("--seal-sha256", required=True)
    args = parser.parse_args()
    if args.action == "seal":
        result = seal(args.fault_policy, args.primary_completion, args.output, args.seal)
    else:
        result = watch(args.seal, args.seal_sha256)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
