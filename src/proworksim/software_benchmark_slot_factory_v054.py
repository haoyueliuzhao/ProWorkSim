"""Materialize a formal single-slot configuration from fixed public assets and an admitted service."""
from __future__ import annotations

import json
from pathlib import Path

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_service_factory_v054 import condition_reference as fixed_condition, validate_service
from .software_benchmark_source_freeze_v054 import verify_sources

ROOT = Path(__file__).resolve().parents[2]
VERSION = "software-benchmark-slot-factory-v054"


def build_slot_config(*, slot_id, condition_reference, model_service, registry_reference,
                      scorer_manifest_reference, output, authorization=None, prewarm_policy_reference=None):
    """No model, Docker, GPU lease or slot claim occurs while freezing this config.

    model_service supplies argv (never a shell string), ready/identity/socket
    paths, one GPU UUID and its independent owner-admission receipt. It must be
    the normal per-episode service, not a used capacity-smoke resident.
    """
    slots_path = ROOT / "artifacts/software-benchmark-v054/manifests/slots.json"
    slots = reference(slots_path)
    slot = next(row for row in json.loads(slots_path.read_text())["slots"] if row["slot_id"] == slot_id)
    registry = json.loads(checked(registry_reference).read_text())
    if (registry.get("planned_tasks") != 500 or registry.get("actual_repository_entries_admitted") != 500
            or len({row["instance_id"] for row in registry["entries"]}) != 500):
        raise ValueError("The complete public-test registry is required")
    entry = next(row for row in registry["entries"] if row["instance_id"] == slot["instance_id"])
    if not entry["admitted"]:
        raise ValueError("This planned task's public frontend is unresolved")
    mapping = json.loads(checked(entry["baseline_mapping"]).read_text())
    public = {"path": str(ROOT / "artifacts/software-benchmark-v054/source/public-tasks.json"),
              "bytes": 1018814, "sha256": "65d130536d04fda752b6ab36534ec657a8cd9bb0243b36067a1eb45413245aaf"}
    task = next(row for row in json.loads(checked(public).read_text()) if row["instance_id"] == slot["instance_id"])
    condition = json.loads(checked(condition_reference).read_text())
    if condition.get("arm") != slot["arm"] or condition_reference != fixed_condition(slot["arm"]):
        raise ValueError("Condition differs from the original arm allocation")
    verify_sources(condition["source_manifest"])
    checked(scorer_manifest_reference)
    checked(model_service["owner_admission"])
    service_reference = validate_service(model_service, slot["arm"])
    command = model_service["command"]
    if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
        raise ValueError("An exact service argv is required")
    if authorization is not None:
        permit = json.loads(checked(authorization).read_text())
        if (permit.get("execution_authorized") is not True or permit.get("slots_sha256") != slots["sha256"]
                or slot_id not in permit.get("slot_ids", [])):
            raise ValueError("Slot execution/budget permit is absent or differs")
    official = json.loads((ROOT / "runs/software-benchmark-v054/images/preparation-r1/image-inventory.json").read_text())
    image = next(row for row in official["images"] if row["instance_id"] == slot["instance_id"])
    if image["image_id"] != mapping["official_image_id"]:
        raise ValueError("Official scorer image changed")
    result = {
        "version": VERSION, "slot_id": slot_id, "arm": slot["arm"], "seed": slot["seed"],
        "slots": slots, "public_tasks": public, "public_task": task, "preparation_only": False,
        "configuration": condition_reference, "owner_admission": model_service["owner_admission"],
        "model_service": service_reference,
        "resident_reference": model_service.get("resident_reference"),
        "prewarm_policy": prewarm_policy_reference,
        'resident_pool_policy': model_service.get('resident_pool_policy'),
        'resident_registration': model_service.get('resident_registration'),
        'resident_id': model_service.get('resident_id'), 'gpu_index': model_service.get('gpu_index'),
        "resident_session_directory": model_service.get("session_directory"),
        "authorization": authorization,
        "all_solver_admissions_passed": bool(authorization is not None and model_service.get("admission_passed") is True),
        "model_command": command, "model_ready": model_service["ready_path"],
        "model_identity": model_service["identity_path"], "model_socket": model_service.get("socket_path"),
        "ref_endpoint": model_service.get("endpoint"), "gpu_uuid": model_service["gpu_uuid"],
        "ref_api_key_file": model_service.get("api_key_file"),
        "model_start_timeout": model_service.get("startup_timeout_seconds", 600),
        "model_local": str(ROOT / "runs/assets/models/Qwen3.5-9B-c20223623576"),
        "public_test_registry": registry_reference, "public_test_entry": entry,
        "lazy_native_preparation": {"cache_root": str(ROOT / "runs/software-benchmark-v054/native-lazy-cache")},
        "stdlib": str(ROOT / "runs/software-benchmark-v054/native-binding-control/r3/REF/control-stdlib"),
        "sdk_runtime": str(ROOT / "runs/software-benchmark-v054/native-binding-control/r3/sdk-runtime"),
        "dataset_revision": "78f471bf655a3137b2e8a75af1501690ec009ec3",
        "source_manifest": condition["source_manifest"],
        "scorer_request_base": {
            "scorer_manifest": scorer_manifest_reference, "baseline_mapping": entry["baseline_mapping"],
            "image": image, "docker_socket": str(ROOT / "runs/software-panel-v053/docker/docker.sock"),
            "docker_cli": reference(ROOT / "runs/software-benchmark-v054/scorer-venv/bin/docker"),
            "dataset": {"path": str(ROOT / "artifacts/software-benchmark-v054/source/trusted-evaluation.json"),
                        "bytes": 9795256, "sha256": "bdd44ad7182b9cb9dd8d679fbdf119b4372e925f3c08c5a30178db818284cfbb"},
            "limits": {"network_mode": "none", "nano_cpus": 4000000000, "memory_bytes": 17179869184,
                       "pids_limit": 16384, "timeout_seconds": 1800},
            "trusted_output_root": str(ROOT / "runs/software-benchmark-v054/official-output")},
    }
    return write_new(output, result)
