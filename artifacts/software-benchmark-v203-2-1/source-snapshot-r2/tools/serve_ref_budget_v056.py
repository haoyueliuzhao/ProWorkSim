"""Run one separately frozen v056 persistent REF engine on an admitted GPU."""
from __future__ import annotations

import argparse
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_ref_service_v056 import run_service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    ref = reference(args.spec)
    if ref["sha256"] != args.sha256:
        raise ValueError("Frozen REF resident specification changed")
    return run_service(ref)


if __name__ == "__main__":
    raise SystemExit(main())
