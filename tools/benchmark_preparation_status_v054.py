"""Summarize saved preparation receipts without running models or rechecking assets."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

try:
    from .verified_image_prepare_v054 import cached_blob_proof, file_stat
except ImportError:
    from verified_image_prepare_v054 import cached_blob_proof, file_stat

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError) as error:
        return {"status": "receipt_unreadable", "error": type(error).__name__}


def complete_blob_summary(inventory, prior_proofs, planned):
    """Reuse complete SHA receipts plus unchanged stat; never read blob payloads."""
    expected = inventory.get("blobs", {})
    complete = {}
    for digest, blob in expected.items():
        if blob.get("digest") != digest:
            continue
        try:
            proof = cached_blob_proof(blob)
            if proof is None:
                proof = prior_proofs.get(digest, {})
                path = Path(proof.get("path", ""))
                if (not path.is_file() or path.suffix in {".part", ".partial", ".writing"}
                        or proof.get("sha256") != digest.split(":", 1)[1]
                        or file_stat(path) != proof.get("stat")):
                    continue
            if (proof.get("bytes") == blob["bytes"]
                    and proof.get("stat", {}).get("bytes") == blob["bytes"]):
                complete[digest] = blob["bytes"]
        except (OSError, ValueError, KeyError, TypeError):
            continue  # Missing/changing receipts are incomplete, never partial credit.
    ready = set()
    for row in inventory.get("images", []):
        descriptors = [row.get("config", {}), *row.get("layers", [])]
        if (row.get("instance_id") in planned and row.get("layers")
                and all(item.get("digest") in complete
                        and complete[item["digest"]] == item.get("size")
                        for item in descriptors)):
            ready.add(row["instance_id"])
    return {
        "unique_compressed_blob_count": len(expected),
        "complete_blob_count_from_receipts": len(complete),
        "complete_blob_bytes_from_receipts": sum(complete.values()),
        "images_with_complete_blob_dependencies": len(ready),
        "complete_blob_evidence": "Per-blob verified receipt or prior proof, exact size and unchanged file stat; deduplicated by fixed digest",
        "blob_payloads_rehashed": False,
    }


def status(root=ROOT):
    artifacts = root / "artifacts/software-benchmark-v054"
    run = root / "runs/software-benchmark-v054"
    data = read(artifacts / "manifests/data-preparation.json")
    slots = read(artifacts / "manifests/slots.json")
    identities = read(artifacts / "manifests/identities.json")
    planned = {row["instance_id"] for row in identities.get("tasks", [])}
    images = {}
    inventory_paths = [run / "images/preparation-r1/image-inventory.json"]
    if not inventory_paths[0].exists():
        plans = sorted((run / "images/preparation-r1").glob("plan-*.json"))
        inventory_paths = plans[-1:]
    inventory_paths += [run / "images/first-image-control-r1/image-inventory.json"]
    inventory = {}
    for path in inventory_paths:
        current = read(path)
        if (current.get("planned_images") == 500
                and current.get("unique_compressed_blob_bytes") is not None):
            inventory = current
        for row in current.get("images", []):
            previous = images.get(row["instance_id"], {})
            if previous.get("status") != "loaded" or row.get("status") == "loaded":
                images[row["instance_id"]] = row
    relevant = [row for name, row in images.items() if name in planned]
    loaded = sum(row.get("status") == "loaded" for row in relevant)
    bounded_passed = sum(row.get("environment_ready") is True for row in relevant)
    scorer = read(artifacts / "scorer/preparation-receipt.json")
    scorer_status = run / "scorer-preflight-r2/controller-status.json"
    if not scorer_status.exists():
        scorer_status = run / "scorer-preflight-r1/controller-status.json"
    seam = read(scorer_status)
    native = read(root / "docs/experiments/software-benchmark-v054-native-sdk-construction-r2.json")
    match = read(root / "docs/experiments/software-benchmark-v054-match-seam-control-r2.json")
    codec = read(root / "docs/experiments/software-benchmark-v054-match-codec-control-r3.json")
    exact = read(root / "docs/experiments/software-benchmark-v054-exact-transport-control-r1.json")
    worker = read(artifacts / "native-worker/preparation-manifest.json")
    lifecycle = read(artifacts / "lifecycle/preparation-manifest.json")
    ref = read(artifacts / "native-environment/ref-followup-status.json")
    apiba = read(run / "images/apiba-prefetch-r1/state.json")
    proof = read(run / "images/preparation-r1/blob-proofs.json")
    blob_summary = complete_blob_summary(inventory, proof, planned)
    apiba_summary = {key: apiba.get(key) for key in (
        "source", "status", "inventory_sha256", "planned_instances", "unique_blob_count",
        "maximum_connections", "registry_start_interval_seconds", "model_calls", "gpu_requests")}
    apiba_summary["outcome_counts"] = dict(Counter(
        outcome.get("status", "unknown") for outcome in apiba.get("outcomes", {}).values()
        if isinstance(outcome, dict)))
    dataset_ready = (
        data.get("dataset_rows") == 500 and len(planned) == 500
        and slots.get("planned_slot_count") == 1500
        and slots.get("formal_execution_authorized") is False)
    scoring_seam_ready = (
        seam.get("status") == "completed"
        and seam.get("official_scoring_status") == "official_report")
    return {
        "version": "v054-preparation-status-v1",
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Saved receipts and file stat only; no repeated payload hashing or execution.",
        "data_ready": dataset_ready,
        "planned_tasks": len(planned),
        "planned_slots": slots.get("planned_slot_count", 0),
        "images": {
            "inventory_status": inventory.get("status", "pending"),
            "planned": 500,
            "loaded": loaded,
            "bounded_preflight_passed": bounded_passed,
            "preflight_states": dict(Counter(
                row.get("preflight_status", "not_checked") for row in relevant)),
            "unique_compressed_bytes": inventory.get("unique_compressed_blob_bytes"),
            **blob_summary,
            "partial_download_bytes_included": False,
            "alternative_domestic_source": apiba_summary,
        },
        "official_scorer_500_specs_ready": scorer.get("all_500_specs_compatible") is True,
        "official_container_seam": seam,
        "native_sdk_construction_passed": native.get("passed") is True,
        "match_synthetic_numerical_bridge_passed": match.get("passed") is True,
        "official_output_codec_cpu_passed": codec.get("passed") is True,
        "shared_exact_counting_cpu_passed": exact.get("passed") is True,
        "native_worker_preparation": worker.get("status", {}),
        "episode_lifecycle_preparation": {
            key: lifecycle.get(key) for key in (
                "status", "all_passed", "actual_model_runner_assembled",
                "formal_execution_authorized")
        },
        "ref_dependency_finalizer": ref,
        "scoring_environment_prepared": (
            dataset_ready and loaded == 500 and bounded_passed == 500
            and scorer.get("all_500_specs_compatible") is True and scoring_seam_ready),
        "all_three_solver_environments_ready": False,
        "remaining_solver_gates": [
            "actual_Docker_actor_isolation_binding",
            "native_numeric_ownership_and_common_resource_limits",
            "actual_episode_runner_owner_guard_and_watchdog_binding",
            "actual_MATCH_model_owner_and_token_accounting_admission",
            "REF_model_capacity_and_execution_admission",
        ],
        "model_execution_authorized": False,
        "automatic_model_dispatch": False,
        "model_calls_from_this_reporter": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = status()
    body = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(".writing")
        temporary.write_text(body)
        temporary.replace(args.output)
    print(body, end="")


if __name__ == "__main__":
    main()
