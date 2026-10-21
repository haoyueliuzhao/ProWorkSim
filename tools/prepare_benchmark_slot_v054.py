"""Create one fixed slot config, without acquiring resources or starting any episode."""
import argparse
import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_slot_factory_v054 import build_slot_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--condition", type=Path, required=True)
    parser.add_argument("--model-service", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--scorer-manifest", type=Path, required=True)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_slot_config(
        slot_id=args.slot_id, condition_reference=reference(args.condition),
        model_service=json.loads(args.model_service.read_text()), registry_reference=reference(args.registry),
        scorer_manifest_reference=reference(args.scorer_manifest), output=args.output,
        authorization=reference(args.authorization) if args.authorization else None)))


if __name__ == "__main__":
    main()
