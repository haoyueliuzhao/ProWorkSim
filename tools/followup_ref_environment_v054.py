"""One-shot REF dependency preparation after an already-running download.

This user-service entry only waits, reuses local wheel cache, installs the
independent REF venv and performs a CPU import control. It never downloads,
starts a model server, loads weights, requests a GPU, or starts benchmark slots.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(
        value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    os.replace(temporary, path)


def process_ticks(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()[19]
    except FileNotFoundError:
        return None


def report_complete(path):
    try:
        report = json.loads(path.read_bytes())
        return (report.get("version") == "1"
                and report.get("environment", {}).get("python_version") == "3.12"
                and bool(report.get("install"))
                and all("download_info" in item and "metadata" in item
                        for item in report["install"]))
    except (FileNotFoundError, ValueError, TypeError):
        return False


def dry_run_success(log_path):
    try:
        with log_path.open("rb") as stream:
            stream.seek(max(0, log_path.stat().st_size - 65536))
            return any(line.startswith(b"Would install ")
                       for line in stream.read().splitlines())
    except FileNotFoundError:
        return False


def run(args):
    root = args.root.absolute()
    local = root / "runs/software-benchmark-v054/native-environment"
    evidence = root / "artifacts/software-benchmark-v054/native-environment"
    evidence.mkdir(parents=True, exist_ok=True)
    lock = (local / "ref-followup.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("A REF dependency follow-up already owns the lock")
    started_path = evidence / "ref-followup-started.json"
    if started_path.exists():
        raise RuntimeError("The one-shot preparation marker already exists")
    state = {
        "version": "software-benchmark-v054-ref-followup-v1",
        "started_at_utc": utc_now(), "status": "waiting_for_original_resolver",
        "resolver_pid": args.resolver_pid,
        "resolver_start_ticks": args.resolver_start_ticks,
        "resolver_exit_code": None,
        "max_wait_seconds": args.max_wait_seconds,
        "poll_seconds": args.poll_seconds,
        "formal_execution_authorized": False, "automatic_model_start": False,
        "model_calls": 0, "gpu_requested": False,
        "new_download_requests": 0, "stages": [],
        "source_files": {},
    }
    for relative in (
        "tools/followup_ref_environment_v054.py",
        "tools/finalize_ref_environment_v054.py",
        "tools/check_ref_environment_v054.py", "config/v054-ref-service.json",
    ):
        state["source_files"][relative] = hashlib.sha256((root / relative).read_bytes()).hexdigest()
    with started_path.open("x") as stream:
        json.dump(state, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    status_path = evidence / "ref-followup-status.json"
    atomic_json(status_path, state)
    deadline = time.monotonic() + args.max_wait_seconds
    report_path = local / "ref-install-plan.json"
    resolver_exit = local / "ref-resolver-exit.json"
    try:
        while True:
            alive = process_ticks(args.resolver_pid) == args.resolver_start_ticks
            exit_info = json.loads(resolver_exit.read_bytes()) if resolver_exit.exists() else {}
            if not alive:
                code = exit_info.get("exit_code")
                state["resolver_exit_code"] = code
                if code is not None and code != 0:
                    raise RuntimeError(f"Original dependency resolver exited with code {code}; cache retained")
                if not report_complete(report_path):
                    raise RuntimeError("Original resolver exited without a complete report; cache retained")
                if code is None and not dry_run_success(local / "ref-resolve.log"):
                    raise RuntimeError("Resolver exit code unknown and no complete dry-run success marker")
                state["resolver_completion_evidence"] = (
                    "original_exec_exit_zero_and_complete_report" if code == 0 else
                    "process_exited_complete_report_and_terminal_dry_run_success_log")
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("96-hour resolver waiting limit reached; cache retained")
            time.sleep(args.poll_seconds)

        wheelhouse = root / "runs/software-benchmark-v054/ref-wheelhouse"
        resident_python = root / "runs/v016-sdk/resident-venv/bin/python"
        target_python = root / "runs/software-benchmark-v054/ref-venv/bin/python"
        finalize = root / "tools/finalize_ref_environment_v054.py"
        temporary = local / "installation-tmp"
        temporary.mkdir(exist_ok=True)
        environment = dict(os.environ)
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                     "http_proxy", "https_proxy", "all_proxy"):
            environment.pop(name, None)
        cpu_prefix = [
            str(args.runtime_root / "run-cpu.sh"), "--write-project",
            "/usr/bin/env", "HF_HUB_OFFLINE=1", "TRANSFORMERS_OFFLINE=1",
            "LITELLM_LOCAL_MODEL_COST_MAP=True", "VLLM_NO_USAGE_STATS=1",
            "DO_NOT_TRACK=1", f"TMPDIR={temporary}",
        ]
        stages = [
            ("materialize_cached_wheels", [
                sys.executable, str(finalize), "--report", str(report_path),
                "--http-cache", str(args.runtime_root /
                                    "sysroot/home/zhuxinrui/.cache/pip/http-v2"),
                "--wheelhouse", str(wheelhouse), "--output-root", str(evidence),
            ]),
            ("offline_locked_install", [
                *cpu_prefix, str(resident_python), str(finalize),
                "--install-only", "--wheelhouse", str(wheelhouse),
                "--output-root", str(evidence), "--pip-python", str(resident_python),
                "--target-python", str(target_python),
            ]),
            ("cpu_import_control", [
                *cpu_prefix, str(target_python),
                str(root / "tools/check_ref_environment_v054.py"),
                "--pip-python", str(resident_python),
                "--output", str(evidence / "ref-cpu-import.json"),
            ]),
        ]
        for name, command in stages:
            state["status"] = name
            atomic_json(status_path, state)
            stage = {"name": name, "started_at_utc": utc_now(), "command": command}
            with (local / f"ref-followup-{name}.log").open("xb") as log:
                result = subprocess.run(
                    command, cwd=root, env=environment, stdout=log,
                    stderr=subprocess.STDOUT, check=False)
            stage.update(ended_at_utc=utc_now(), exit_code=result.returncode)
            state["stages"].append(stage)
            if result.returncode:
                raise RuntimeError(f"REF preparation stage {name} exited {result.returncode}")
        state["status"] = "dependencies_installed_cpu_import_passed_gpu_admission_pending"
    except Exception as error:
        state.update(status="failed_preparation_cache_retained",
                     error={"type": type(error).__name__, "message": str(error)})
    state["ended_at_utc"] = utc_now()
    atomic_json(status_path, state)
    atomic_json(evidence / "ref-followup-terminal.json", state)
    print(json.dumps(state, ensure_ascii=False, sort_keys=True))
    return 0 if state["status"].startswith("dependencies_installed") else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--resolver-pid", type=int, required=True)
    parser.add_argument("--resolver-start-ticks", required=True)
    parser.add_argument("--max-wait-seconds", type=int, default=96 * 60 * 60)
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.max_wait_seconds <= 96 * 60 * 60 or args.poll_seconds != 30:
        parser.error("Wait is at most 96 hours and polling is exactly 30 seconds")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
