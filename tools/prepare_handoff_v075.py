"""Operate the explicitly scoped, naturally drained coordinator handoff."""
from __future__ import annotations

import argparse
import json

from proworksim import software_benchmark_handoff_v075 as handoff


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['stage', 'gate', 'observe', 'stop', 'restore', 'rollback'])
    args = parser.parse_args()
    from proworksim.software_benchmark_adaptive_scope_v076 import require_allowed
    function = {'stage': handoff.stage, 'gate': handoff.gate, 'observe': handoff.observe,
        'stop': handoff.stop_quiescent, 'restore': handoff.restore_ready, 'rollback': handoff.rollback_gate}[args.operation]
    value = function(guard=require_allowed)
    if args.operation == 'observe':
        value.pop('snapshots', None)
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    main()
