"""Host orchestrator for two independent SDK/isolated-worker CPU controls."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import traceback

from check_native_worker_v054 import ROOT, RUNTIME, make_root, read_message, reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--arms", nargs="+", choices=["REF", "MATCH"], default=["REF", "MATCH"])
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sdk_runtime = output / "sdk-runtime"
    shutil.copytree(RUNTIME, sdk_runtime / "sysroot", symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    (sdk_runtime / "sysroot/testbed").mkdir(exist_ok=True)
    result = {"version": "v054-native-binding-cpu-control-v1", "passed": False,
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "model_calls": 0, "gpu_launches": 0, "actual_verified_tasks": 0,
              "source_files": [reference(ROOT / name) for name in (
                  "src/proworksim/software_benchmark_native_worker_v054.py",
                  "src/proworksim/software_benchmark_native_binding_v054.py",
                  "tools/run_native_worker_cpu_v054.sh",
                  "tools/run_native_sdk_controller_v054.sh",
                  "tools/check_native_proxy_v054.py", "tools/check_native_binding_v054.py")]}
    interfaces, arms = {}, {}
    try:
        for arm in args.arms:
            folder = output / arm
            folder.mkdir()
            root, stdlib, secret = make_root(folder)
            environment = folder / "public-environment.json"
            environment.write_text(json.dumps({
                "version": "v054-native-public-environment-v1", "kind": "synthetic_cpu_fixture",
                "image_id": None, "source_config_sha256": None, "public_python": "/usr/bin/python",
                "environment": {"PATH": "/usr/bin:/bin", "HOME": "/home/actor",
                                "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TMPDIR": "/tmp"},
            }, sort_keys=True, indent=2) + "\n")
            worker = controller = None
            with (folder / "worker.stderr").open("wb") as worker_errors, (
                    folder / "controller.stderr").open("wb") as controller_errors:
                try:
                    worker = subprocess.Popen([
                        str(ROOT / "tools/run_native_worker_cpu_v054.sh"),
                        "--rootfs", str(root), "--stdlib", str(stdlib),
                        "--environment-manifest", str(environment)],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=worker_errors, text=True, bufsize=1, start_new_session=True)
                    ready = read_message(worker)
                    (folder / "ready.json").write_text(json.dumps(ready, indent=2) + "\n")
                    assert ready["type"] == "ready", ready
                    controller = subprocess.Popen([
                        str(ROOT / "tools/run_native_sdk_controller_v054.sh"),
                        str(sdk_runtime), str(root), str(ROOT / "tools/check_native_proxy_v054.py"),
                        "--ready", str(folder / "ready.json"), "--output", str(folder / "sdk"),
                        "--outside-marker", str(secret), "--arm", arm],
                        stdin=worker.stdout, stdout=worker.stdin, stderr=controller_errors,
                        start_new_session=True)
                    assert controller.wait(timeout=90) == 0
                    assert worker.wait(timeout=20) == 0
                    receipt = json.loads((folder / "sdk/receipt.json").read_bytes())
                    assert receipt["passed"]
                    assert receipt["host_executor_constructions"] == 0
                    assert receipt["model_calls"] == 0
                    assert (root / "testbed/sub/two.py").read_text() == "OTHER = 3\n"
                    assert secret.read_text() == "SYNTHETIC_HOST_MUST_NOT_BE_READ\n"
                    arms[arm] = receipt
                    interfaces[arm] = json.loads((folder / "sdk/interface.json").read_bytes())
                finally:
                    for process in (controller, worker):
                        if process is not None and process.poll() is None:
                            os.killpg(process.pid, 15)
                            try:
                                process.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                os.killpg(process.pid, 9)
                                process.wait(timeout=10)
        if len(interfaces) == 2:
            assert interfaces["REF"] == interfaces["MATCH"]
        result.update({
            "passed": True, "arms": arms,
            "interfaces_identical": True if len(interfaces) == 2 else None,
            "independent_worker_and_rootfs_per_arm": True,
            "host_default_executor_constructions": 0,
            "schema_description_and_worker_rendered_content_unchanged": True})
    except BaseException as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)}
        result["traceback"] = traceback.format_exc()
    result["ended_utc"] = datetime.now(timezone.utc).isoformat()
    (output / "receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("passed", "model_calls", "gpu_launches")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
