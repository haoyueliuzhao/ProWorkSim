"""Execute a frozen resident-model protocol; no offline good-trajectory selection."""

import argparse
import importlib
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.online_training import SharedActor, run_online_windows
from proworksim.storage import atomic_write, json_bytes, read_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--weight-manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--restore-checkpoint")
    parser.add_argument("--collector", default="proworksim.online_collection:collect_window")
    parser.add_argument("--startup-reserve-gib", type=float, default=0)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    protocol = read_json(Path(args.protocol))
    before = code_identity()
    atomic_write(output / "source-before.json", json_bytes(before))
    module, name = args.collector.split(":", 1)
    collector = getattr(importlib.import_module(module), name)
    try:
        owner = SharedActor.from_pretrained(
            args.model, weight_manifest=args.weight_manifest, output=output / "resident",
            recipe=protocol.get("recipe"), attention=protocol.get("attention", "sdpa_explicit_kv"),
            matmul_precision=protocol.get("matmul_precision", "high"),
            startup_reserve_gib=args.startup_reserve_gib,
        )
        if args.restore_checkpoint:
            restored = owner.restore_checkpoint(args.restore_checkpoint)
            atomic_write(output / "restored-checkpoint.json", json_bytes(restored))
        result = run_online_windows(owner, protocol, output / "online", collector)
        print(json_bytes({"status": result["status"], "actor_steps": owner.actor_steps,
                          "critic_steps": owner.critic_steps, "output": str(output)}).decode())
    finally:
        after = code_identity()
        atomic_write(output / "source-after.json", json_bytes(after))
        atomic_write(output / "source-comparison.json", json_bytes({"unchanged": before == after}))


if __name__ == "__main__":
    main()
