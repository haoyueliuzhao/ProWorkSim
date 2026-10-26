#!/usr/bin/env python3
"""Prepare the fixed v062 development panel without resource operations."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from proworksim.software_benchmark_ref_plan_v062 import prepare  # noqa: E402


if __name__ == "__main__":
    result = prepare(ROOT, ROOT / "artifacts/software-benchmark-v062/preparation-r1")
    print(json.dumps(result, ensure_ascii=False, indent=2))
