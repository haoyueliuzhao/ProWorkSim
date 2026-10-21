"""Host-only deferred exception inventory or end-stage one-attempt scoring pass."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
from proworksim.software_benchmark_candidates_v054 import write_new  # noqa: E402
from proworksim.software_benchmark_deferred_scoring_v054 import (  # noqa: E402
    collect_inventory, read_snapshot, run_deferred,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    inventory = actions.add_parser('inventory')
    inventory.add_argument('--queue-state', type=Path, required=True)
    inventory.add_argument('--output', type=Path, required=True)
    run = actions.add_parser('run')
    run.add_argument('--primary-completion', type=Path, required=True)
    run.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'inventory':
        args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
        os.chmod(args.output, 0o700)
        state, state_ref = read_snapshot(args.queue_state)
        result = write_new(args.output / 'inventory.json', collect_inventory(state, state_ref))
    else:
        result = run_deferred(args.primary_completion, args.output)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
