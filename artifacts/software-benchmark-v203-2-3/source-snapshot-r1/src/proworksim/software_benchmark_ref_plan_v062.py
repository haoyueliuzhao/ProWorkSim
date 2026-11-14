"""Offline, immutable preparation for the v062 REF development panel.

This module deliberately has no Docker, service, GPU or model entry point. A
proposal is not a grant, and historical qualification is never self-admitting.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

VERSION = "v062-ref-development-panel-r1"
SEED_BASE = 20261026062000
ARMS = {"BASE5M": 5_000_000, "FIX5M": 5_000_000, "FIX10M": 10_000_000}
PUBLIC_FIELDS = ("instance_id", "repo", "base_commit", "problem_statement")
V061_TASKS = (
    "pylint-dev__pylint-4970", "sphinx-doc__sphinx-7889", "sympy__sympy-21930",
    "pylint-dev__pylint-4604", "scikit-learn__scikit-learn-14894",
    "pylint-dev__pylint-6528", "pydata__xarray-4966",
)
OFFLINE_REQUESTS = ("psf__requests-2931", "psf__requests-5414")
REAL_TLS_REQUESTS = ("psf__requests-1766", "psf__requests-1921")
COMMON_LIMITS = {
    "all_model_attempts": 512, "agent_decisions": 512, "sdk_iterations": 512,
    "soft_seconds": 21600, "hard_seconds": 23400,
    "generation_timeout_seconds": 1800,
}


def reference(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def load_reference(ref):
    if reference(ref["path"]) != ref:
        raise ValueError("Immutable input changed: " + ref["path"])
    return json.loads(Path(ref["path"]).read_bytes())


def retain(path, value):
    """Do not overwrite a different proposal or silently regenerate its seeds."""
    path = Path(path)
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("Prepared evidence is immutable: " + str(path))
    else:
        with path.open("xb") as stream:
            stream.write(data)
    return reference(path)


def build_panel(original_plan, original_slots, public_tasks):
    """Select by the old fixed order and repository only; accepts no scores."""
    tasks = original_plan["task_ids"]
    if len(tasks) != 50 or len(set(tasks)) != 50:
        raise ValueError("The complete original fifty-task panel is required")
    public = {row["instance_id"]: row for row in public_tasks}
    repositories = {}
    for row in original_slots:
        task, repo = row["instance_id"], row["repo"]
        if task in repositories and repositories[task] != repo:
            raise ValueError("A task has conflicting repository identities")
        repositories[task] = repo
    if set(repositories) != set(tasks) or len(set(repositories.values())) != 12:
        raise ValueError("The original twelve repositories must remain intact")
    if Counter(repositories.values()) != Counter(original_plan["repository_counts"]):
        raise ValueError("Repository counts changed")
    selected, seen, exported = [], set(), []
    for task in tasks:
        row = public[task]
        if row["repo"] != repositories[task] or not all(isinstance(row[k], str) for k in PUBLIC_FIELDS):
            raise ValueError("Public task identity is incomplete")
        exported.append({key: row[key] for key in PUBLIC_FIELDS})
        if row["repo"] not in seen:
            selected.append(task)
            seen.add(row["repo"])
    slots = []

    def add(task_index, arm, repeat):
        task = tasks[task_index]
        seed = SEED_BASE + task_index * 10 + repeat
        slots.append({
            "slot_index": len(slots) + 1, "task_index": task_index + 1,
            "slot_id": f"v062:{task}:{arm}:{seed}", "instance_id": task,
            "repo": repositories[task], "condition_id": arm, "seed": seed,
            "repeat_index": repeat, "input_plus_output_tokens": ARMS[arm],
            "execution_protocol": "frozen_v061" if arm == "BASE5M" else "fixed_v062",
        })

    arms = list(ARMS)
    for index in range(len(tasks)):
        offset = index % len(arms)
        for arm in arms[offset:] + arms[:offset]:
            add(index, arm, 0)
    for repeat in (1, 2):
        for task in selected:
            add(tasks.index(task), "FIX10M", repeat)
    return {
        "version": VERSION, "scope": "development_and_calibration_only",
        "task_ids": tasks, "repository_counts": dict(Counter(repositories.values())),
        "repeat_task_ids": selected,
        "repeat_selection": "first task of each repository in the original v056 fixed order",
        "selection_uses_previous_scores": False, "seed_base": SEED_BASE,
        "primary_order": "original task order; three arms cyclically rotated by task index",
        "repeat_order": "after all 150 primary slots; repeat 1 then repeat 2 in selected task order",
        "planned_episodes": len(slots), "primary_episodes": 150, "repeat_episodes": 24,
        "aggregate_input_output_token_upper_bound": sum(row["input_plus_output_tokens"] for row in slots),
        "arms": ARMS, "common_limits": COMMON_LIMITS, "slots": slots,
        "public_tasks": exported, "actor_public_fields": list(PUBLIC_FIELDS),
        "independent_initial_states": True, "same_primary_seed_across_arms": True,
        "old_workspace_or_feedback_reused": False, "official_test_or_gold_to_actor": False,
        "replace_task_or_seed_after_results": False, "automatic_replay": False,
        "full_500_benchmark_score_claim": False, "independent_confirmation_set": False,
    }


def qualification_inventory(root, panel):
    """Inventory evidence without equating changed scorer/guard identities."""
    paths = {}
    for task in V061_TASKS:
        paths[task] = ("v061_offline", root / "runs/software-benchmark-v061/unknown-recovery-r1-20261025"
                       / "qualifications" / (task + ".json"))
    for task in OFFLINE_REQUESTS:
        paths[task] = ("v058_offline_httpbin", root / "runs/software-benchmark-v058"
                       / "environment-admission-r3-approved-20261025/task-qualifications"
                       / task / "qualification.json")
    for task in REAL_TLS_REQUESTS:
        paths[task] = ("v060_real_tls", root / "runs/software-benchmark-v060"
                       / "original-ca-rescore-r1-20261025/environment-admission/task-qualifications"
                       / task / "qualification.json")
    rows = []
    for task in panel["task_ids"]:
        evidence = paths.get(task)
        row = {"instance_id": task, "historical_evidence_available": bool(evidence),
               "reuse_admitted": False, "new_runtime_identity_frozen": False,
               "control_resources_reserved": ["gold", "empty"]}
        if evidence:
            provider, path = evidence
            ref = reference(path)
            value = load_reference(ref)
            if (value.get("instance_id") != task or value.get("passed") is not True
                    or {x.get("patch_kind") for x in value.get("controls", [])} != {"gold", "empty"}
                    or len(value["controls"]) != 2):
                raise ValueError("Historical gold/empty evidence is incomplete: " + task)
            identities = []
            for control in value["controls"]:
                receipt = load_reference(control["receipt"])
                identity_ref = control.get("identity", receipt.get("identity"))
                identity = load_reference(identity_ref)
                identities.append({"patch_kind": control["patch_kind"], "identity": identity_ref,
                                   "bound_identity": {key: identity[key] for key in (
                                       "image", "dataset", "baseline_mapping", "scorer_manifest",
                                       "limits", "environment_revision") if key in identity}})
            row.update(provider=provider, qualification=ref, historical_control_identities=identities,
                       qualification_status="pending_new_scoring_identity_equivalence",
                       control_execution="only if exact scoring identity equivalence fails")
        else:
            row.update(provider="offline_official", qualification_status="new_gold_empty_required",
                       control_execution="required before any candidate score for this task")
        rows.append(row)
    return {
        "version": VERSION, "rows": rows,
        "historical_tasks": len(paths), "currently_admitted_reuses": 0,
        "mandatory_new_control_tasks": len(rows) - len(paths),
        "mandatory_new_control_containers": 2 * (len(rows) - len(paths)),
        "conditional_control_containers": 2 * len(paths),
        "maximum_new_control_containers": 2 * len(rows),
        "reuse_rule": "same image/dataset/baseline/interpreter/dependencies/eval script/scorer/provider/limits; "
                     "any administrative relocation requires explicit immutable equivalence evidence",
        "historical_grants_reopened": False, "qualification_pass_is_not_launch_permission": True,
    }


def resource_plan(panel, inventory):
    episodes = panel["planned_episodes"]
    diagnostics = 2  # One deployment control for each distinct execution protocol.
    controls = inventory["maximum_new_control_containers"]
    resources = []
    for row in panel["slots"]:
        for role in ("actor", "controller", "score", "volume"):
            resources.append({"resource_key": f"{role}-{row['slot_index']:03d}", "role": role,
                              "slot_id": row["slot_id"], "instance_id": row["instance_id"]})
    for protocol in ("frozen_v061", "fixed_v062"):
        for role in ("actor", "controller", "volume"):
            resources.append({"resource_key": f"diagnostic-{protocol}-{role}", "role": role,
                              "diagnostic": True, "execution_protocol": protocol})
    for row in inventory["rows"]:
        for kind in ("gold", "empty"):
            resources.append({"resource_key": f"control-{row['instance_id']}-{kind}", "role": "control",
                              "instance_id": row["instance_id"], "patch_kind": kind,
                              "conditional_on_failed_equivalence": row["historical_evidence_available"]})
    tls_candidates = sum(row["instance_id"] in REAL_TLS_REQUESTS for row in panel["slots"])
    tls_sessions = tls_candidates + 2 * len(REAL_TLS_REQUESTS)
    return {
        "version": VERSION, "preparation_only": True, "resources": resources,
        "maximum_actor_containers": episodes + diagnostics,
        "maximum_controller_containers": episodes + diagnostics,
        "maximum_score_containers": episodes, "maximum_control_containers": controls,
        "maximum_containers": 3 * episodes + 2 * diagnostics + controls,
        "minimum_containers_if_all_eleven_qualifications_reusable": 3 * episodes + 2 * diagnostics
            + inventory["mandatory_new_control_containers"],
        "maximum_named_volumes": episodes + diagnostics, "zero_model_diagnostic_pairs": diagnostics,
        "active_actor_limit": 2, "active_controller_limit": 2, "active_grader_limit": 2,
        "maximum_active_containers": 6, "maximum_model_residents": 2,
        "maximum_active_generation_episodes": 2, "maximum_episodes_per_model_resident": 2,
        "model_resident_cpu": 12, "model_resident_memory_gib": 96,
        "coordinator_cpu": 4, "coordinator_memory_gib": 16,
        "actor_cpu": 4, "actor_memory_gib": 16,
        "controller_cpu": 2, "controller_memory_gib": 4,
        "grader_cpu": 4, "grader_memory_gib": 16,
        "maximum_cpu": 48, "maximum_memory_gib": 280,
        "minimum_captured_cpu_pool": 48, "minimum_free_gpu_mib": 50176,
        "gpu_memory_utilization": 0.6, "allowed_physical_gpu_indices": list(range(8)),
        "model_context_tokens": 131072, "model_output_tokens": 32768,
        "model_dtype": "bfloat16", "model_max_sequences": 1,
        "full_context_cache_admission_required": True,
        "neutral_model_preparation_calls": 2, "neutral_model_preparation_token_upper_bound": 4096,
        "generation_token_upper_bound": panel["aggregate_input_output_token_upper_bound"],
        "all_new_model_token_upper_bound": panel["aggregate_input_output_token_upper_bound"] + 4096,
        "generation_attempt_upper_bound": episodes * COMMON_LIMITS["all_model_attempts"],
        "new_owned_user_units": ["proworksim-v062-model-0.service", "proworksim-v062-model-1.service",
                                 "proworksim-v062-ref-development.service"],
        "loopback_model_ports": [18163, 18164], "service_restart": "no", "swap_bytes": 0,
        "container_network": "none", "container_cap_drop": ["ALL"], "container_cap_add": [],
        "no_new_privileges": True, "host_bind_mounts": False, "privileged": False,
        "host_devices_or_gpu_in_containers": False, "published_ports": False,
        "public_actor_network": False, "shared_services_changed": False,
        "host_mount_namespace_network_driver_or_linger_changes": False,
        "daemon_start_restart_or_image_pull": False, "automatic_replay": False,
        "actor_lifecycle_seconds": 24000, "diagnostic_lifecycle_seconds": 180,
        "grader_test_seconds": 1800, "grader_lifecycle_seconds": 3600,
        "disk_minimum_free_gib": 128,
        "real_tls_grading": {
            "tasks": list(REAL_TLS_REQUESTS), "provider": "v060 bounded genuine TLS exec bridge",
            "candidate_sessions": tls_candidates, "conditional_control_sessions": 4,
            "maximum_sessions": tls_sessions, "target_hostname": "httpbin.org", "ports": [80, 443],
            "original_repository_ca_unchanged": True, "tls_verification_unchanged": True,
            "frozen_ipv4_resolution_required": True, "nat_or_host_network": False,
            "connections_per_session": 512, "maximum_active_connections_per_session": 16,
            "payload_bytes_per_session": 64 * 1024**2,
            "all_sessions_payload_bytes": tls_sessions * 64 * 1024**2,
            "automatic_retries": 0, "rootful_operations_outside_owned_containers": False,
        },
    }


def prepare(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output != root / "artifacts/software-benchmark-v062/preparation-r1":
        raise ValueError("Only the dedicated immutable v062 preparation directory is allowed")
    original_ref = reference(root / "artifacts/software-benchmark-v056/plan.json")
    original = load_reference(original_ref)
    original_slots = load_reference(original["slots"])["slots"]
    panel = build_panel(original, original_slots, load_reference(original["public_tasks"]))
    source_ref = reference(root / "runs/software-benchmark-v060/original-ca-rescore-r1-20261025"
                           / "requests-rescore/measurement-state.json")
    source = load_reference(source_ref)
    original_ids = {row["slot_id"] for row in original_slots}
    source_ids = [row["slot"]["slot_id"] for row in source["rows"]]
    if len(source_ids) != 200 or len(set(source_ids)) != 200 or set(source_ids) != original_ids:
        raise ValueError("Latest v060 source state does not cover the exact original two hundred slots")
    panel["sources"] = {"original_plan": original_ref, "original_slots": original["slots"],
                        "public_tasks": original["public_tasks"], "latest_v060_source_state": source_ref}
    inventory = qualification_inventory(root, panel)
    resources = resource_plan(panel, inventory)
    refs = {name: retain(output / (name + ".json"), value) for name, value in (
        ("panel", panel), ("qualification-inventory", inventory), ("resource-plan", resources))}
    proposal = {
        "version": VERSION, "status": "preparation_only_pending_explicit_rootful_authorization",
        "plan": refs, "formal_execution_authorized": False, "automatic_release": False,
        "old_completed_authorizations_reopened": False, "shared_server_hold_changed": False,
        "model_calls_during_preparation": 0, "rootful_operations_during_preparation": 0,
        "generation_and_grading": "two generation episodes plus two asynchronous grading jobs",
        "minimum_remaining_integration": [
            "v062 owned dispatch and durable claims bound to this panel and exact source manifest",
            "new v062 adapters or explicit-context core; no global monkeypatch of v061 policy",
            "BASE5M frozen behavior and FIX controller bundles frozen separately",
            "exact scorer/environment identity equivalence for eleven historical qualifications",
            "new controls for 39 tasks and only identity-changed historical tasks",
            "public-only actor archive and controller configuration, with independent leakage admission",
            "full runtime source hashes and host/GPU capacity admission before any execution",
            "explicit approval of the new bounded rootful proposal; old completed grants remain closed",
        ],
        "interpretation": "All fifty tasks are development/calibration; same-panel improvement is not "
                          "independent generalization and the highest budget is right-censored.",
    }
    refs["proposal"] = retain(output / "proposal.json", proposal)
    refs["pending-authorization"] = retain(output / "pending-authorization.json", {
        "version": VERSION, "status": "pending", "explicit_rootful_authorization": None,
        "formal_execution_authorized": False, "automatic_release": False,
        "proposal": refs["proposal"], "runtime_source_manifest": None,
        "cannot_be_used_as_a_runtime_grant": True,
    })
    return refs
