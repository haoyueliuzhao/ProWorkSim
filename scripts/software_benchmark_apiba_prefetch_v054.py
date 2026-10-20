#!/usr/bin/env python3
"""After the first APIBA full SHA succeeds, fetch only absent complete blobs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.verified_apiba_blob_v054 import download_blob  # noqa: E402
from tools.domestic_asset_download import DownloadPaused  # noqa: E402
from tools.verified_image_metadata_v054 import load_inventory  # noqa: E402
from tools.verified_image_prepare_v054 import (  # noqa: E402
    cached_blob_proof, disk_gate, file_stat, merged_official, save, GiB,
)


def main():
    output = ROOT / "runs/software-benchmark-v054/images/apiba-prefetch-r1"
    output.mkdir(parents=True, exist_ok=True)
    cache = ROOT / "runs/software-benchmark-v054/images/preparation-r1/blobs"
    _, identity = load_inventory(ROOT / "config/v054-verified-image-inventory.json")
    rows, _ = merged_official(
        ROOT / "runs/software-benchmark-v054/images/official-ci-39437579123", identity)
    first_digest = "sha256:fd7a87c0b95ba9470ab5b292bee0cde8f8f4b91a5c9755052c1b36b06f71c7d3"
    first = {"digest": first_digest, "bytes": 420167964,
             "path": str(cache / (first_digest.split(":")[1] + ".blob"))}
    state = {
        "inventory_sha256": identity, "planned_instances": 500,
        "source": "docker.apiba.cn", "maximum_connections": 4,
        "registry_start_interval_seconds": 2, "status": "waiting_first_complete_sha",
        "model_calls": 0, "gpu_requests": 0,
        "first_required_sha256": first_digest, "outcomes": {},
    }
    save(output / "state.json", state)
    started = time.monotonic()
    while cached_blob_proof(first) is None:
        if time.monotonic() - started > 86400:
            state["status"] = "waiting_expired_without_model_failure"
            save(output / "state.json", state)
            return 2
        time.sleep(30)
    # A whole image layer, rather than only a small metadata body, now proves
    # this transport can deliver the authoritative bytes without Range support.
    receipt = json.loads(Path(first["path"] + ".verified.json").read_bytes())
    if receipt.get("verification") != "apiba_complete_download_incremental_sha256":
        state["status"] = "first_blob_completed_by_other_source_api_full_delivery_unproven"
        save(output / "state.json", state)
        return 2
    blobs = {}
    for key in sorted(rows):
        row = rows[key]
        for descriptor in [row["config"], *row["layers"]]:
            digest = descriptor["digest"]
            blobs.setdefault(digest, {
                "digest": digest, "bytes": descriptor["size"], "image_name": row["image_name"],
                "path": str(cache / (digest.split(":")[1] + ".blob")),
            })
    state.update(status="fetching_absent_whole_blobs", unique_blob_count=len(blobs))
    save(output / "state.json", state)
    stop, throttle = threading.Event(), threading.Lock()
    previous_start = [0.0]

    def fetch(blob):
        digest = blob["digest"]
        if stop.is_set():
            return digest, {"status": "not_started_after_public_fault"}
        proof = cached_blob_proof(blob)
        if proof is not None:
            return digest, {"status": "existing_verified", "proof": proof}
        with Path(blob["path"] + ".download.lock").open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return digest, {"status": "deferred_active_transfer"}
        partial = Path(blob["path"] + ".part")
        if partial.exists() and partial.stat().st_size:
            return digest, {"status": "deferred_preserved_partial", "bytes": partial.stat().st_size}
        disk_gate(cache, 200 * GiB, blob["bytes"])
        with throttle:
            delay = 2.0 - (time.monotonic() - previous_start[0])
            if delay > 0:
                time.sleep(delay)
            previous_start[0] = time.monotonic()
        if stop.is_set():
            return digest, {"status": "not_started_after_public_fault"}
        try:
            result = download_blob(blob["image_name"], digest, blob["path"], expected_bytes=blob["bytes"])
        except BlockingIOError:
            return digest, {"status": "deferred_competing_transfer"}
        except DownloadPaused as error:
            if "Range unsupported" in str(error) and partial.exists() and partial.stat().st_size:
                return digest, {"status": "deferred_competing_partial",
                                "bytes": partial.stat().st_size}
            raise
        return digest, {"status": result["status"], "result": result,
                        "stat": file_stat(Path(blob["path"]))}

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch, blob) for blob in blobs.values()]
        try:
            for future in as_completed(futures):
                digest, outcome = future.result()
                state["outcomes"][digest] = outcome
                save(output / "state.json", state)
        except Exception as error:
            stop.set()
            state.update(status="pausing_public_fault", error_type=type(error).__name__,
                         error=str(error)[:500])
            save(output / "state.json", state)
            for future in futures:
                future.cancel()
            raise
    state["status"] = "bounded_prefetch_closed_with_deferred_assets_preserved"
    save(output / "state.json", state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
