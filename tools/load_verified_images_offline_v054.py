"""Load the pinned Verified500 images from existing SHA-bound local assets only."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verified_image_prepare_v054 import (  # noqa: E402
    cached_blob_proof, daemon_identity, now, save, stream_load,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("at most four concurrent offline loads")
    source = ROOT / "runs/software-benchmark-v054/images/preparation-r1"
    output = ROOT / "runs/software-benchmark-v054/images/offline-load-r1"
    output.mkdir(parents=True, exist_ok=True)
    with (output / "controller.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = json.loads((source / "image-inventory.json").read_bytes())
        if len(plan["images"]) != 500 or len(plan["blobs"]) != 1195:
            raise ValueError("fixed complete batch required")
        proofs = {}
        for digest, blob in plan["blobs"].items():
            proof = cached_blob_proof(blob)
            if proof is None:
                raise ValueError("complete local SHA-bound input missing: " + digest)
            proofs[digest] = proof
        receipt = {
            "schema": "proworksim.v054.offline-image-load-r1", "started_at_utc": now(),
            "inventory_sha256": plan["inventory_sha256"], "daemon": daemon_identity(),
            "network_requests": 0, "model_calls": 0, "old_preflight_repeated": 0,
            "workers": args.workers, "complete_local_blobs": len(proofs),
            "status": "loading", "results": {},
        }
        save(output / "state.json", receipt)
        selected = [row for row in plan["images"] if row.get("status") != "loaded"]
        def load(row):
            return stream_load(row, plan["blobs"], proofs, output, 200 * 1024 ** 3)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(load, row): row for row in selected}
            for future in as_completed(futures):
                row = futures[future]
                try:
                    result = future.result()
                    row.update(result, status="loaded", environment_ready=False)
                    receipt["results"][row["instance_id"]] = {"status": "loaded", **result}
                except Exception as error:
                    receipt["results"][row["instance_id"]] = {
                        "status": "technical_unknown", "error_type": type(error).__name__,
                        "error": str(error)[:1000],
                    }
                plan["loaded_count"] = sum(item.get("status") == "loaded" for item in plan["images"])
                receipt["loaded_count"] = plan["loaded_count"]
                save(source / "image-inventory.json", plan)
                save(output / "state.json", receipt)
        receipt.update(completed_at_utc=now(), status=(
            "all_500_loaded" if plan["loaded_count"] == 500 else "partial_load_technical_unknown"))
        save(output / "state.json", receipt)
        print(json.dumps({key: value for key, value in receipt.items() if key != "results"}))


if __name__ == "__main__":
    main()
