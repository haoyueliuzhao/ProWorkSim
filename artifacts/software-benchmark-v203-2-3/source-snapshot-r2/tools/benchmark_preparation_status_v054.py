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
    historical_loaded = sum(row.get("status") == "loaded" for row in relevant)
    historical_bounded_passed = sum(row.get("environment_ready") is True for row in relevant)
    actor_r2 = read(artifacts / "actor/actor-baseline-completion-r2.json")
    actor = read(artifacts / "actor/actor-baseline-completion-r3.json")
    actor_progress = read(run / "images/actor-admission-r3/state.json")
    loaded = max(historical_loaded, actor_r2.get("official_images_loaded", 0),
                 actor.get("official_images_loaded", 0))
    actor_admitted = actor.get("shared_actor_baselines_admitted", actor_progress.get("admitted_count", 0))
    scorer = read(artifacts / "scorer/preparation-receipt.json")
    scorer_status = run / "scorer-preflight-r4/controller-status.json"
    if not scorer_status.exists():
        scorer_status = run / "scorer-preflight-r1/controller-status.json"
    seam = read(scorer_status)
    native = read(root / "docs/experiments/software-benchmark-v054-native-sdk-construction-r2.json")
    match = read(root / "docs/experiments/software-benchmark-v054-match-seam-control-r2.json")
    codec = read(root / "docs/experiments/software-benchmark-v054-match-codec-control-r3.json")
    exact = read(root / "docs/experiments/software-benchmark-v054-exact-transport-control-r1.json")
    worker = read(artifacts / "native-worker/preparation-manifest.json")
    lifecycle = read(artifacts / "lifecycle/preparation-manifest.json")
    native_real = read(artifacts / "native-environment/preparation-r2.json")
    runner = read(artifacts / "runner/cpu-integration.json")
    completion = read(artifacts / "preparation-completion-r1.json")
    capacity_paths = sorted(
        (path for path in run.glob("model-capacity-preparation-r*/state.json")
         if path.parent.name.rsplit("r", 1)[-1].isdigit()),
        key=lambda path: int(path.parent.name.rsplit("r", 1)[-1]))
    capacity_states = [read(path) for path in capacity_paths]
    capacity = next((value for value in reversed(capacity_states) if value), {})
    capacity_results = {}
    for state in capacity_states:
        capacity_results.update(state.get("results", {}))
    capacity_admission = read(artifacts / "native-environment/model-capacity-admission.json")
    formal_queue = read(run / "formal-queue-r1/state.json")
    active_bindings = read(Path(formal_queue.get("bindings", {}).get("path",
                                  str(run / "not-started-bindings.json"))))
    authorization = read(Path(active_bindings.get("authorization", {}).get("path",
                                  str(root / "config/v054-formal-authorization-r1.json"))))
    pool_policy = active_bindings.get("resident_pool_policy")
    prewarm_policy = active_bindings.get("prewarm_policy")
    resident_required = bool(read(root / "config/v054-condition-REF.json").get("residency_protocol"))
    resident = read(artifacts / "native-environment/resident-admission-r1.json")
    resident_ready = (resident.get("version") == "v054-resident-admission-v1"
                      and set(resident.get("admitted_modes", {})) == {"REF", "MATCH_PROJECT"}
                      and all(item.get("passed") is True for item in resident["admitted_modes"].values()))
    formal_authorized = (authorization.get("execution_authorized") is True
                         and authorization.get("planned_model_episodes") == 1500
                         and authorization.get("slots_sha256") ==
                         "55899d0b83a5bab1082bccb50496fb6c1d7111ecb951fc4d61c222be19d88676")
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
    assets_ready = (dataset_ready and loaded == 500
                    and blob_summary["images_with_complete_blob_dependencies"] == 500)
    actor_ready = (actor_admitted == 500 and actor.get("technical_unknown") == 0
                   and actor.get("all_runtime_versions_equal_official") is True
                   and actor.get("all_allowed_ancestry_only") is True
                   and actor.get("no_unreachable_objects") is True)
    cpu_ready = (assets_ready and actor_ready and scoring_seam_ready
                 and completion.get("cpu_environment_preparation_complete") is True
                 and runner.get("all_passed") is True)
    capacity_ready = (set(capacity_admission.get("admitted_modes", {})) == {"REF", "MATCH"}
                      and all(capacity_results.get(arm, {}).get("status") ==
                              "capacity_and_synthetic_accounting_passed" for arm in ("REF", "MATCH")))
    gates = []
    if not assets_ready:
        gates.append("fixed_assets_local")
    if not actor_ready:
        gates.append("all_500_version_preserving_actor_baselines")
    if not cpu_ready:
        gates.append("final_public_registry_lazy_runtime_and_runner_freeze")
    for arm in ("MATCH", "REF"):
        if capacity_results.get(arm, {}).get("status") != "capacity_and_synthetic_accounting_passed":
            gates.append(arm + "_actual_model_capacity_and_accounting")
    if resident_required and not resident_ready:
        gates.append("actual_persistent_resident_two_session_handoff")
    return {
        "version": "v054-preparation-status-v2",
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Saved receipts and file stat only; no repeated payload hashing or execution.",
        "data_ready": dataset_ready,
        "assets_ready": assets_ready,
        "cpu_environment_ready": cpu_ready,
        "model_capacity_ready": capacity_ready,
        "planned_tasks": len(planned),
        "planned_slots": slots.get("planned_slot_count", 0),
        "images": {
            "inventory_status": inventory.get("status", "pending"),
            "planned": 500,
            "loaded": loaded,
            "historical_strict_preflight_passed": historical_bounded_passed,
            "historical_preflight_states": dict(Counter(
                row.get("preflight_status", "not_checked") for row in relevant)),
            "historical_strict_preflight_superseded": True,
            "version_preserving_actor_baselines_admitted": actor_admitted,
            "final_actor_completion": actor,
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
        "actual_native_environment": native_real.get("status", {}),
        "three_arm_scripted_cpu_integration_passed": runner.get("all_passed") is True,
        "final_cpu_preparation_manifest": completion,
        "episode_lifecycle_preparation": {
            key: lifecycle.get(key) for key in (
                "status", "all_passed", "actual_model_runner_assembled",
                "formal_execution_authorized")
        },
        "ref_dependency_finalizer": ref,
        "scoring_environment_prepared": (
            dataset_ready and loaded == 500
            and scorer.get("all_500_specs_compatible") is True and scoring_seam_ready),
        "all_three_solver_environments_ready": (cpu_ready and capacity_ready
                                                and (not resident_required or resident_ready)),
        "persistent_resident_required": resident_required,
        "persistent_resident_sessions_admitted": resident_ready,
        "dynamic_gpu_policy": pool_policy,
        "cpu_prewarm_policy": prewarm_policy,
        "authorized_physical_gpus": authorization.get("physical_gpus", []),
        "maximum_active_generation_episodes": authorization.get("maximum_active_generation_episodes"),
        "remaining_solver_gates": gates,
        "model_capacity_preparation": {
            "status": capacity.get("status", "not_started"),
            "last_observed_utc": capacity.get("last_observed_utc"),
            "monitor": capacity.get("monitor"),
            "active": capacity.get("active"),
            "completed_modes": {arm: row.get("status") for arm, row in capacity_results.items()},
            "maximum_preparation_residents": capacity.get("maximum_preparation_residents"),
            "formal_task_episodes": capacity.get("formal_task_episodes", 0),
            "gpu_free_mib": {str(row["index"]): row["free_mib"]
                             for row in capacity.get("gpu_observation", [])},
        },
        "formal_execution_authorized": formal_authorized,
        "model_execution_authorized": formal_authorized,
        "formal_authorization": authorization.get("version"),
        "automatic_formal_model_dispatch": formal_queue.get("status") == "running",
        "formal_queue": {
            "status": formal_queue.get("status", "not_started"),
            "generation_states": dict(Counter(row.get("generation", {}).get("status", "unknown")
                                               for row in formal_queue.get("rows", []))),
            "dispatch_count": len(formal_queue.get("generation_dispatches", [])),
            "planned_denominator_per_arm": 500,
        },
        "bounded_capacity_monitor_registered": bool(capacity.get("monitor")),
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
