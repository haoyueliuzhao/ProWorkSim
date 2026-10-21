"""Remove exactly one evidence-bound, quiescent clone using the fixed safe reader."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = args.request.resolve()
    if (os.geteuid() != 0 or os.environ.get("SUDO_UID") != "1021"
            or not path.is_relative_to(root / "runs/software-benchmark-v055")):
        raise PermissionError("Only the registered owner may clean a project episode clone")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.sha256:
        raise ValueError("Cleanup request changed after dispatch")
    # Import this stdlib-only module directly: host system Python does not need
    # the project SDK/dependency installation and never enters a model runtime.
    source = root / "src/proworksim/software_benchmark_rootfs_io_v055.py"
    spec = importlib.util.spec_from_file_location("pws_native_cleanup", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.remove_validated_root(json.loads(raw))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
