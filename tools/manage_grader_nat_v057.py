"""Start/inspect/close only v057's two private grader NAT namespaces."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_grader_nat_v057 import close_registry, start_registry, validate_registry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "inspect", "close"))
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "start":
        try:
            result = start_registry(args.root)
        except BaseException:
            if (args.root / "intent.json").exists() and not (args.root / "registry.json").exists():
                close_registry(args.root)
            raise
    elif args.action == "close":
        result = close_registry(args.root)
    else:
        result = validate_registry(reference(args.root / "registry.json"))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
