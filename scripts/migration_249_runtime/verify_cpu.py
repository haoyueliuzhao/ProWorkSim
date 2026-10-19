"""One bounded import probe; no model, tests, tensor creation, or GPU access."""

from __future__ import annotations

import argparse
import ctypes
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--packages", nargs="*", default=["proworksim", "openpyxl", "duckdb"])
arguments = parser.parse_args()
libc = ctypes.CDLL("libc.so.6")
libc.gnu_get_libc_version.restype = ctypes.c_char_p
result = {
    "executable": sys.executable,
    "python": sys.version,
    "prefix": sys.prefix,
    "base_prefix": sys.base_prefix,
    "glibc": libc.gnu_get_libc_version().decode(),
    "cwd": str(Path.cwd()),
    "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
    "nvidia_device_nodes_present": any(
        path.is_char_device() for path in Path("/dev").glob("nvidia*")
    ),
    "packages": {},
    "new_model_calls": 0,
    "new_gpu_execution": False,
    "new_experiment_or_test_execution": False,
}
for name in arguments.packages:
    module = importlib.import_module(name)
    try:
        version = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        version = None
    result["packages"][name] = {
        "version": version,
        "module_path": getattr(module, "__file__", None),
    }
print(json.dumps(result, indent=2))
