"""Prepare/execute/finalize the authorized remaining-CNY45 amendment once."""
from __future__ import annotations

import argparse
import json

from proworksim import software_benchmark_cash_amendment_v122 as amendment


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--execute', action='store_true')
    modes.add_argument('--finalize', action='store_true')
    args = parser.parse_args()
    operation = amendment.prepare if args.prepare else amendment.execute if args.execute else amendment.finalize
    print(json.dumps(operation(), ensure_ascii=False))
