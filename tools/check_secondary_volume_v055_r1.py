"""One programmed MATCH lifecycle on a new project-visible data1 bind mount.

Reuse the already qualified host checker in this dedicated process. Only its
executor filters out the redundant PROJECT case; no frozen file is edited.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
BIND = ROOT / "runs/software-benchmark-v055/secondary-volume-r1"
SOURCE = Path("/data1/proworksim-zhuxinrui/v055-worker-volume-r1")
CHECKER = ROOT / "tools/check_deepseek_host_lifecycle_v055.py"


def reference(path):
    raw = Path(path).read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-config", required=True, type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.absolute()
    if (output.exists() or not output.is_relative_to(BIND) or output == BIND
            or output.resolve() != output or SOURCE.resolve(strict=True) != SOURCE):
        raise ValueError("A fresh output under the exact project-visible bind is required")
    source_stat, target_stat, primary_stat = SOURCE.stat(), BIND.stat(), ROOT.stat()
    if ((source_stat.st_dev, source_stat.st_ino) != (target_stat.st_dev, target_stat.st_ino)
            or target_stat.st_dev == primary_stat.st_dev
            or (target_stat.st_uid, target_stat.st_gid) != (1021, 1022)
            or stat.S_IMODE(target_stat.st_mode) != 0o700):
        raise ValueError("The independently mounted owner-only data1 volume is not present")
    mounts = [line for line in Path("/proc/self/mountinfo").read_text().splitlines()
              if len(line.split()) > 5 and line.split()[4] == str(BIND)]
    if len(mounts) != 1 or reference(args.source_config)["sha256"] != args.source_sha256:
        raise ValueError("Exact bind identity or source configuration differs")
    config = json.loads(args.source_config.read_bytes())
    lock_path = Path(config["lazy_native_preparation"]["cache_root"]) / "locks" / (
        config["public_task"]["instance_id"] + ".lock")
    lock = lock_path.open("r")
    fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
    sys.path.insert(0, str(ROOT / "src"))
    spec = importlib.util.spec_from_file_location("v055_existing_host_volume_fixture", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from proworksim import software_benchmark_runner_v055 as runner
    original_executor, original_clone = module.ThreadPoolExecutor, runner.clone_prepared_rootfs
    cloned = []

    class OneMatchExecutor:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def map(self, function, slots):
            selected = [slot for slot in slots if slot["arm"] == "MATCH"]
            if len(selected) != 1:
                raise ValueError("Exactly one native MATCH control is allowed")
            return [function(selected[0])]

    def observed_clone(environment, destination):
        result = original_clone(environment, destination)
        rootfs = Path(result["rootfs"])
        info = rootfs.stat()
        if info.st_dev != target_stat.st_dev:
            raise ValueError("Actual cloned rootfs is not on the admitted data1 volume")
        cloned.append({"rootfs": str(rootfs), "device": info.st_dev,
                       "owner_uid": info.st_uid, "owner_gid": info.st_gid})
        return result

    module.ThreadPoolExecutor, runner.clone_prepared_rootfs = OneMatchExecutor, observed_clone
    try:
        status = module.host_control(args.source_config, output)
    finally:
        module.ThreadPoolExecutor, runner.clone_prepared_rootfs = original_executor, original_clone
        lock.close()
    lifecycle = json.loads((output / "receipt.json").read_bytes())
    passed = (status == 0 and lifecycle["passed"] and len(cloned) == 1
              and [row["arm"] for row in lifecycle["cases"]] == ["MATCH"]
              and all(not Path(item["rootfs"]).exists() for item in cloned))
    receipt = {"version": "v055-data1-single-native-host-control-r1", "passed": passed,
        "source": reference(__file__), "existing_checker": reference(CHECKER),
        "source_config": reference(args.source_config), "bind": str(BIND),
        "physical_source": str(SOURCE), "mountinfo": mounts[0],
        "primary_device": primary_stat.st_dev, "secondary_device": target_stat.st_dev,
        "cloned_rootfs_observations": cloned, "lifecycle_receipt": reference(output / "receipt.json"),
        "declared_local_fixture_arms": ["MATCH", "PROJECT"], "executed_fixture_arms": ["MATCH"],
        "unexecuted_PROJECT_is_not_a_test_result": True, "shared_cache_read_lock_held": True,
        "real_API_calls": 0, "formal_3000_claims": 0, "official_grader_calls": 0,
        "existing_data_moved": False, "shared_monetary_ledger_used": False,
        "changes_are_process_local_fixture_observation_only": True}
    with (output / "volume-control.json").open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": passed, "real_API_calls": 0, "clones": len(cloned),
                      "secondary_device": target_stat.st_dev, "receipt": str(output / "volume-control.json")}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
