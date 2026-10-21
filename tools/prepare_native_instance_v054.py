"""One-stop, local-only initialization before an evaluation slot/model claim."""
import argparse
import json
from pathlib import Path

from proworksim.software_benchmark_native_lazy_v054 import ensure_native_instance
from proworksim.software_benchmark_scorer_v054 import file_reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--mapping-sha256", required=True)
    parser.add_argument("--public-tasks", required=True, type=Path)
    parser.add_argument("--public-tasks-sha256", required=True)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--stdlib", required=True, type=Path)
    parser.add_argument("--docker-socket", required=True)
    parser.add_argument("--continue-exported", action="store_true",
                        help="Finish an explicitly retained complete export; no new Docker export or payload hashing")
    args = parser.parse_args()
    mapping, public = file_reference(args.mapping), file_reference(args.public_tasks)
    if mapping["sha256"] != args.mapping_sha256 or public["sha256"] != args.public_tasks_sha256:
        raise ValueError("Explicit task/public source digest changed")
    value = ensure_native_instance(
        args.instance_id, mapping_reference=mapping, cache_root=args.cache_root,
        stdlib=args.stdlib, public_tasks_reference=public, docker_socket=args.docker_socket,
        continue_exported=args.continue_exported)
    print(json.dumps({**value, "status": "qualified", "slot_claimed": False, "model_calls": 0}))


if __name__ == "__main__":
    main()
