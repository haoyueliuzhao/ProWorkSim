"""Prepare a new v052 server protocol inside the migration private CPU runtime."""
from __future__ import annotations

import argparse
import json

from proworksim.server_bridge_runtime_v052 import prepare_runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-runtime", default="artifacts/software-bridge-v052/source-qualification/runtime.json")
    parser.add_argument("--output", required=True, help="New immutable manifest path; an existing file is never overwritten")
    args = parser.parse_args()
    print(json.dumps(prepare_runtime(original_runtime=args.original_runtime, output=args.output), indent=2))


if __name__ == "__main__":
    main()
