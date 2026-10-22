"""Freeze or watch the separate terminal-generation REF GPU handoff policy."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_ref_handoff_pool_v054_r1 import freeze, HandoffProvisioner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    command = commands.add_parser("freeze")
    command.add_argument("--output", type=Path, required=True)
    command = commands.add_parser("run")
    command.add_argument("--overlay", type=Path, required=True)
    command.add_argument("--sha256", required=True)
    command.add_argument("--once", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    if args.operation == "freeze":
        print(json.dumps(freeze(args.output)))
        return 0
    ref = reference(args.overlay)
    if ref["sha256"] != args.sha256:
        raise ValueError("Independent retirement overlay SHA differs")
    HandoffProvisioner(ref).run(once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
