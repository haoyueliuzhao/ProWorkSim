"""Pause or resume NEW generation only on a plan declaring the v120 control."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import write_control


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--mode', choices=('drain', 'run'), required=True)
    parser.add_argument('--reason', required=True)
    args = parser.parse_args()
    print(json.dumps(write_control(reference(args.plan), mode=args.mode, reason=args.reason), ensure_ascii=False))
