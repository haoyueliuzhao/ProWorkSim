"""Wait for the preselected image, then run exactly one official CPU preflight."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from proworksim.software_benchmark_scorer_v054 import (
    canonical, file_reference, score_request, sha256,
)
from proworksim import software_benchmark_scorer_v054 as scorer_module

ROOT = Path(__file__).resolve().parents[1]
FIRST_INSTANCE = "astropy__astropy-12907"


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    temporary = path.with_suffix(".writing")
    temporary.write_bytes(canonical(value))
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-inventory", required=True, type=Path)
    parser.add_argument("--control-root", required=True, type=Path)
    parser.add_argument("--scorer-manifest", required=True, type=Path)
    parser.add_argument("--wait-seconds", type=int, default=345600)
    args = parser.parse_args()
    root = args.control_root.resolve()
    config_path = root / "config.json"
    config = json.loads(config_path.read_bytes())
    identities_path = ROOT / "artifacts/software-benchmark-v054/manifests/identities.json"
    identities = json.loads(identities_path.read_bytes())
    selected = sorted(identities["tasks"], key=lambda row: row["instance_id"])[0]
    if (selected["instance_id"] != FIRST_INSTANCE
            or config["instance_id"] != FIRST_INSTANCE
            or config.get("preparation_only") is not True):
        raise ValueError("Preflight selection is not the predeclared first task")
    initial_inventory = json.loads(args.image_inventory.read_bytes())
    initial_image = next(row for row in initial_inventory["images"]
                         if row["instance_id"] == FIRST_INSTANCE)
    pin_keys = ("instance_id", "image_name", "tag", "base_commit",
                "manifest_digest", "config_digest")
    image_pin = {key: initial_image[key] for key in pin_keys}
    frozen_files = {
        "config": file_reference(config_path), "script": file_reference(__file__),
        "scorer_adapter": file_reference(scorer_module.__file__),
        "scorer_manifest": file_reference(args.scorer_manifest),
    }
    with (root / "controller-claim.json").open("xb") as stream:
        stream.write(canonical({
            "started_utc": now(), **frozen_files,
            "identities": file_reference(identities_path), "pinned_image": image_pin,
            "wait_seconds": args.wait_seconds, "check_interval_seconds": 30,
        }))
    status_path = root / "controller-status.json"
    save(status_path, {
        "status": "waiting_for_fixed_image", "instance_id": FIRST_INSTANCE,
        "preparation_only": True, "started_utc": now(), "model_calls": 0})
    deadline = time.monotonic() + args.wait_seconds
    image = None
    while time.monotonic() < deadline:
        if args.image_inventory.exists():
            inventory = json.loads(args.image_inventory.read_bytes())
            image = next((row for row in inventory["images"]
                          if row["instance_id"] == FIRST_INSTANCE), None)
            if image is not None and image.get("status") == "loaded":
                if {key: image[key] for key in pin_keys} != image_pin:
                    save(status_path, {"status": "technical_unknown",
                                       "error": "Image identity changed while waiting"})
                    raise ValueError("Image identity changed while waiting")
                break
        time.sleep(30)
    else:
        save(status_path, {
            "status": "image_wait_expired", "instance_id": FIRST_INSTANCE,
            "finished_utc": now(), "model_calls": 0, "scoring_calls": 0})
        return
    assert image is not None
    if any(file_reference(value["path"]) != value for value in frozen_files.values()):
        save(status_path, {"status": "technical_unknown",
                           "error": "Predeclared software or configuration changed"})
        raise ValueError("Predeclared software or configuration changed")
    # Preparation-only empty candidate: immutable rootfs + fixed base commit.
    # The observer records the actual repository HEAD/tree in this same scoring
    # container. This is not a generated PROJECT candidate tree manifest.
    baseline_binding = {
        "scheme": "preparation_image_config_and_base_commit",
        "image_id": image["image_id"], "base_commit": selected["base_commit"]}
    binding_sha = sha256(canonical(baseline_binding))
    (root / "baseline-binding.json").write_bytes(canonical(baseline_binding))
    source_root = ROOT / "artifacts/software-benchmark-v054/source"
    dataset = {
        "path": str(source_root / "trusted-evaluation.json"), "bytes": 9795256,
        "sha256": "bdd44ad7182b9cb9dd8d679fbdf119b4372e925f3c08c5a30178db818284cfbb"}
    request = {
        "instance_id": FIRST_INSTANCE, "arm": "REF", "endpoint": "code", "attempt": 1,
        "preparation_only": True,
        "docker_socket": str(ROOT / "runs/software-panel-v053/docker/docker.sock"),
        "docker_cli": file_reference(
            ROOT / "runs/software-benchmark-v054/scorer-venv/bin/docker"),
        "scorer_manifest": frozen_files["scorer_manifest"],
        "dataset": dataset, "patch": file_reference(root / "empty.patch"),
        "baseline_tree_sha256": binding_sha, "candidate_tree_sha256": binding_sha,
        "image": image, "config_sha256": sha256(config_path.read_bytes()),
        "limits": config["limits"], "trusted_output_root": str(root / "official-output"),
    }
    if request["patch"]["bytes"] != 0:
        raise ValueError("Predeclared preparation candidate is empty")
    (root / "request.json").write_bytes(canonical(request))
    save(status_path, {
        "status": "official_scoring_in_progress", "instance_id": FIRST_INSTANCE,
        "started_utc": now(), "request": file_reference(root / "request.json"),
        "preparation_only": True, "model_calls": 0})
    try:
        receipt = score_request(request)
        save(status_path, {
            "status": "completed", "instance_id": FIRST_INSTANCE,
            "finished_utc": now(), "official_scoring_status": receipt["status"],
            "baseline_resolved": receipt["resolved"], "run_id": receipt["run_id"],
            "preparation_only": True, "counted_as_model_result": False,
            "model_calls": 0, "scoring_calls": 1,
            "official_receipt": file_reference(
                root / "official-output" / receipt["run_id"] / "receipt.json"),
        })
    except Exception as error:
        save(status_path, {
            "status": "technical_unknown", "instance_id": FIRST_INSTANCE,
            "finished_utc": now(), "error_type": type(error).__name__, "error": str(error),
            "preparation_only": True, "model_calls": 0, "automatic_retry": False})
        raise


if __name__ == "__main__":
    main()
