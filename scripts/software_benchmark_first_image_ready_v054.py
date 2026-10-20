#!/usr/bin/env python3
"""Wait on verified local bytes, then load the prelocked first Verified image."""
from __future__ import annotations

import fcntl
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.verified_image_metadata_v054 import load_inventory  # noqa: E402
from tools.verified_image_prepare_v054 import cached_blob_proof, merged_official, save  # noqa: E402


def main():
    folder = ROOT / "runs/software-benchmark-v054/images/preparation-r1"
    rows, sha = load_inventory(ROOT / "config/v054-verified-image-inventory.json")
    identities, _ = merged_official(
        ROOT / "runs/software-benchmark-v054/images/official-ci-39437579123", sha)
    first = identities[sorted(rows, key=lambda row: row["instance_id"])[0]["instance_id"]]
    status_path = folder / "first-ready-watcher.json"
    started = time.time()
    while time.time() - started < 86400:
        missing = []
        for descriptor in [first["config"], *first["layers"]]:
            blob = {"digest": descriptor["digest"], "bytes": descriptor["size"],
                    "path": str(folder / "blobs" / (descriptor["digest"].split(":")[1] + ".blob"))}
            if cached_blob_proof(blob) is None:
                missing.append(descriptor["digest"])
        status = {
            "instance_id": first["instance_id"], "inventory_sha256": sha,
            "at_epoch": time.time(), "missing_blob_digests": missing,
            "status": "waiting_verified_local_assets", "network_requests": 0,
            "model_calls": 0, "candidate_generation": 0,
        }
        save(status_path, status)
        if not missing:
            with (folder / "preparation.lock").open("a+b") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    status["status"] = "active_preparation_owns_local_loading"
                    save(status_path, status)
                    return 0
            command = [
                sys.executable, "-B", str(ROOT / "tools/verified_image_prepare_v054.py"),
                "--inventory", str(ROOT / "config/v054-verified-image-inventory.json"),
                "--official-root", str(ROOT / "runs/software-benchmark-v054/images/official-ci-39437579123"),
                "--mirror-summary", str(ROOT / "runs/software-benchmark-v054/images/mirror-metadata-r1/summary.json"),
                "--output", str(folder), "--load-ready-only",
            ]
            with (folder / "first-ready-local-load.log").open("ab") as log:
                result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            status.update(status="local_load_closed", returncode=result.returncode)
            save(status_path, status)
            return result.returncode
        time.sleep(30)
    status["status"] = "waiting_expired_without_model_failure"
    save(status_path, status)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
