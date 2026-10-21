"""Materialize a fixed formal service declaration only after real capacity qualification."""
import argparse
import json
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_service_factory_v054 import build_service, templates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--templates-only", action="store_true")
    parser.add_argument("--arm", choices=["REF", "MATCH", "PROJECT"])
    parser.add_argument("--capacity-receipt", type=Path)
    parser.add_argument("--card", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.templates_only:
        print(json.dumps(templates(), ensure_ascii=False, indent=2))
        return
    if any(value is None for value in (args.arm, args.capacity_receipt, args.card, args.output)):
        parser.error("Actual arm/capacity/card/output are required; no fabricated admission defaults")
    print(json.dumps(build_service(arm=args.arm, capacity_reference=reference(args.capacity_receipt),
        card=json.loads(args.card.read_text()), directory=args.output)))


if __name__ == "__main__":
    main()
