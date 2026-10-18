"""Frozen eighteen-slot CAL2 host; no CAL1 replay, HOLD access or training."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from proworksim.online_training import sha_file
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.storage import read_json
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.software_calibration_v051 import (
    ASSETS, DEPS, MODEL, PYTHON, RESOURCE_SOURCE, SOURCE, checked, ref,
    resource_modules, sealed, unseal, write,
)

VERSION = "software-calibration-cal2-host-v0.51"
GPU_PREFERENCE = list(range(8))
CONTRACT = {"context_limit": 18432, "max_output_tokens": 2048,
    "enable_thinking": False, "preserve_thinking": False, "temperature": .7,
    "top_p": 1., "top_k": 0, "repetition_penalty": 1.,
    "eos_token_ids": [248044, 248046], "pad_token_id": 248044,
    "max_generation_seconds": 600}
LIMITS = {"max_residents": 4, "reservation_seconds": 900, "loading_seconds": 900,
    "preparation_seconds": 600, "generation_seconds": 900, "episode_seconds": 6000,
    "scoring_seconds": 600, "measurement_seconds": 600,
    "rss_bytes": 64 * 1024**3, "artifact_bytes": 128 * 1024**3,
    "minimum_volume_free_bytes": 20 * 1024**3, "poll_seconds": 5}
DOCS = SOURCE / "docs/experiments"
INVENTORY = DOCS / "software-calibration-v051-repository-inventory.json"
RELEASE = DOCS / "software-calibration-v051-cal1-to-cal2-release.json"
SOURCE_QUALIFIED = DOCS / "software-calibration-v051-cal2-source-qualified.json"
ADMISSION = DOCS / "software-calibration-v051-cal2-admission.json"
RESOURCE_POLICY = DOCS / "software-calibration-v051-resource-policy-20261018.json"
MINI_MANIFEST = ASSETS / "mini-source/manifest.json"
CAL1_CHECKS = {"original48_uniquely_accounted_for", "new33_input_source_scoring_terminal_binding_closed",
    "both_hosts_closed", "original_user_interruptions_identified", "old_missing_evidence_preserved",
    "no_old_request_replay_or_rescore", "no_performance_threshold_or_outcome_selection",
    "cal2_inventory_and_initial_states_prelocked_independently"}
SOURCE_CHECKS = {"source_environment_qualified", "source_partition_bound", "original_test_inventory_preserved",
    "new_initial_inputs_bound", "pws_interface_controls", "formal_fixture_rejection", "pws_formal_sources_identical"}
COMPOUND_CHECKS = {"cal1_scope_explained", "source_environment_qualified", "new_initial_inputs_bound",
    "pws_interface_controls", "native_interface_controls", "shared_runner_controls",
    "authoritative_R_tree_bound", "host_controls", "current_resource_policy_bound"}


def required_checks(value, required):
    return (isinstance(value, dict) and required <= set(value)
            and all(item is True for item in value.values()))


def inventory(value):
    """Read static CAL2 metadata only; no HOLD task material is opened."""
    rows = [copy.deepcopy(row) for row in value["rows"] if row["partition"] == "CAL2"]
    if len(rows) != 18 or len({row["slot_id"] for row in rows}) != 18:
        raise ValueError("Exactly eighteen original CAL2 slots are required")
    tasks = [f"cal2-{repo}-{number}" for repo in ("boltons", "parse", "xmltodict") for number in (1, 2)]
    orders = (("R", "P", "U"), ("P", "U", "R"), ("U", "R", "P"))
    for index, task_id in enumerate(tasks):
        for row, condition in zip(rows[index * 3:index * 3 + 3], orders[index % 3], strict=True):
            if (row["task_id"] != task_id or row["condition"] != condition
                    or row["slot_id"] != "v051-" + task_id + "-" + condition
                    or row["seed"] != 202610170551 + index
                    or row["first_member"] != "member_001"
                    or row["generation_tokens"] != 500000
                    or row["decisions"] != 128 or row["attempts"] != 128
                    or row["project_public_tests"] != (None if condition == "R" else 32)
                    or row["condition_order_for_task"] != list(orders[index % 3])):
                raise ValueError("The original CAL2 task/seed/condition/budget order changed")
    return rows


def gate_records(release, source, admission, *, release_ref, source_ref, policy_ref):
    """Independent source/input/control release, never a score threshold."""
    if (release.get("version") != "v051-cal1-to-cal2-dispatch-release-v1"
            or release.get("next_stage") != "CAL2" or release.get("released") is not True
            or release.get("unresolved_blockers") != []
            or not required_checks(release.get("checks"), CAL1_CHECKS)):
        raise ValueError("An independent complete CAL1-to-CAL2 release is required")
    resources = release.get("resources", {})
    if (resources.get("policy_reference") != policy_ref
            or resources.get("allowed_gpu_indices") != GPU_PREFERENCE
            or resources.get("max_residents") != 4 or resources.get("idle_only_admission") is not False):
        raise ValueError("Bind the explicit 2026-10-18 capacity-sharing resource revision")
    if (source.get("version") != "v051-cal2-source-qualified-v1"
            or source.get("passed") is not True or not required_checks(source.get("checks"), SOURCE_CHECKS)
            or len(source.get("tasks", [])) != 6):
        raise ValueError("Frozen CAL2 source and initial-input qualification is missing")
    if (admission.get("version") != "v051-cal2-compound-admission-v1"
            or admission.get("stage") != "CAL2" or admission.get("released") is not True
            or admission.get("unresolved_blockers") != []
            or admission.get("cal1_release") != release_ref
            or admission.get("source_qualified") != source_ref
            or admission.get("resource_policy") != policy_ref
            or not required_checks(admission.get("checks"), COMPOUND_CHECKS)
            or not admission.get("control_references")):
        raise ValueError("Root-authored compound CAL2 admission is required")
    return True


def _evidence_refs(release, source, admission):
    refs = [release["cal1_report"], *release["cal1_supervisors"], source["adapter_manifest"]]
    refs.extend(source["sources"].values() if isinstance(source["sources"], dict) else source["sources"])
    refs.extend(source.get("tested_formal_modules", {}).values())
    refs.extend(admission["control_references"].values() if isinstance(admission["control_references"], dict)
                else admission["control_references"])
    normalized = []
    for item in refs:
        path = Path(item["path"])
        actual = ref(path if path.is_absolute() else SOURCE / path)
        if any(actual[key] != item[key] for key in ("sha256", "bytes")):
            raise ValueError("Upstream evidence bytes changed: " + str(path))
        normalized.append(actual)
    return normalized


def prepare(root):
    from proworksim.audit import code_identity

    root = Path(root).resolve()
    if root.exists():
        raise FileExistsError("CAL2 requires a fresh independent root")
    identity = code_identity()
    if identity.get("code_dirty") is not False:
        raise ValueError("Commit CAL2 source and gates before freezing its model inventory")
    original = read_json(INVENTORY)
    rows = inventory(original)
    release, source, admission = map(read_json, (RELEASE, SOURCE_QUALIFIED, ADMISSION))
    gate_records(release, source, admission, release_ref=ref(RELEASE),
        source_ref=ref(SOURCE_QUALIFIED), policy_ref=ref(RESOURCE_POLICY))
    upstream_evidence = _evidence_refs(release, source, admission)
    for item in upstream_evidence:
        checked(item)
    state = copy.deepcopy(original["states"]["S_star"])
    for item in (state["checkpoint"], state["state_file_reference_from_original_metadata"]):
        checked(item)
    if state["historical_steps"] != [4, 4]:
        raise ValueError("CAL2 U imports only the original S-star actor4/4")
    root.mkdir(parents=True)
    snapshot, sources = root / "source", {}
    for folder in ("src", "scripts"):
        for path in sorted((SOURCE / folder).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            relative = path.relative_to(SOURCE)
            target = snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            sources[str(relative)] = sha_file(target)
    evidence = []
    for path in (RELEASE, SOURCE_QUALIFIED, ADMISSION, RESOURCE_POLICY, INVENTORY, MINI_MANIFEST,
                 DOCS / "software-calibration-v051-repository-protocol.md",
                 DOCS / "software-calibration-v051-native-execution.md",
                 DOCS / "software-calibration-v051-cal2-host-protocol.md"):
        destination = root / "evidence" / path.name
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(path, destination)
        evidence.append({"original": ref(path), "frozen_copy": ref(destination)})
    plan = sealed({"version": VERSION, "created_at": time.time(), "source_commit": identity,
        "source_root": str(snapshot), "source_files": sources, "rows": rows,
        "inventory": ref(INVENTORY), "source_qualified": ref(SOURCE_QUALIFIED),
        "cal1_release": ref(RELEASE), "compound_admission": ref(ADMISSION),
        "resource_policy_reference": ref(RESOURCE_POLICY), "upstream_evidence": upstream_evidence,
        "repository_source_root": source["source_root"],
        "adapter_manifest": ref(SOURCE / source["adapter_manifest"]["path"]),
        "S_star": state, "mini_manifest": ref(MINI_MANIFEST), "evidence": evidence,
        "model_path": str(MODEL), "model_manifest": ref(MODEL / "proworksim-manifest.json"),
        "native_python": str(PYTHON), "runtime_dependency_path": str(DEPS),
        "resource_modules": [ref(RESOURCE_SOURCE / (name + ".py")) for name in
            ("software_learning_resources_v050r3", "software_learning_resources_v050r5")],
        "contract": CONTRACT, "limits": LIMITS, "gpu_preference": GPU_PREFERENCE,
        "idle_only_admission": False, "fresh_resident_per_slot": True,
        "maximum_slots": 18, "maximum_actual_tokens": 9000000,
        "maximum_decisions": 2304, "maximum_attempts": 2304,
        "maximum_public_project_tests": 384, "maximum_parameter_updates": 0,
        "maximum_backward_calls": 0, "new_qualification_calls": 0,
        "model_retries": False, "pre_model_resource_only_retries": True,
        "hold_material_opened": False, "automatic_successors": False})
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    plan = unseal(read_json(Path(root) / "plan.json"))
    if (plan["version"] != VERSION or plan["contract"] != CONTRACT or plan["limits"] != LIMITS
            or plan["gpu_preference"] != GPU_PREFERENCE or plan["idle_only_admission"] is not False
            or plan["fresh_resident_per_slot"] is not True):
        raise ValueError("Frozen CAL2 source or execution/resource contract changed")
    for name, sha in plan["source_files"].items():
        if sha_file(Path(plan["source_root"]) / name) != sha:
            raise ValueError("CAL2 source snapshot changed: " + name)
    for item in [plan["inventory"], plan["source_qualified"], plan["cal1_release"],
                 plan["compound_admission"], plan["resource_policy_reference"], plan["model_manifest"],
                 plan["mini_manifest"], plan["S_star"]["checkpoint"],
                 plan["S_star"]["state_file_reference_from_original_metadata"],
                 *plan["upstream_evidence"], *[r["frozen_copy"] for r in plan["evidence"]]]:
        checked(item)
    gate_records(read_json(checked(plan["cal1_release"])), read_json(checked(plan["source_qualified"])),
        read_json(checked(plan["compound_admission"])), release_ref=plan["cal1_release"],
        source_ref=plan["source_qualified"], policy_ref=plan["resource_policy_reference"])
    original = read_json(checked(plan["inventory"]))
    if inventory(original) != plan["rows"] or original["states"]["S_star"] != plan["S_star"]:
        raise ValueError("Original eighteen CAL2 rows or S-star identity changed")
    return plan


def phase(output, kind, *, episode_started_at=None, episode_closed_at=None):
    write(Path(output) / "task.json", {"kind": kind, "started_at": time.time(), "pid": os.getpid(),
        "episode_started_at": episode_started_at, "episode_closed_at": episode_closed_at})


def deadline_reason(current, now):
    cap = LIMITS.get(current.get("kind", "") + "_seconds")
    if cap is None or now - current["started_at"] >= cap:
        return "task_deadline"
    if (current.get("episode_started_at") is not None and current.get("episode_closed_at") is None
            and now - current["episode_started_at"] >= LIMITS["episode_seconds"]):
        return "episode_hard_deadline"
    return None


def native_accounting(resident):
    """Count actual native receipts once; unfinished generations retain reservation."""
    calls = Path(resident) / "calls"
    started = {p.name.removesuffix("-started.json"): read_json(p) for p in calls.glob("*-started.json")}
    complete = {p.name.removesuffix("-complete.json"): read_json(p) for p in calls.glob("*-complete.json")}
    prepared = {p.name.removesuffix("-prepared.json"): read_json(p) for p in calls.glob("*-prepared.json")}
    actual = uncertain = 0
    errors, actual_calls = [], []
    for key, item in complete.items():
        before = started.get(key)
        usage = item.get("usage", {})
        if (before is None or key not in prepared or item.get("attempt_id") != key
                or item.get("input") != before.get("native_input")
                or item.get("actor_identity") != before.get("actor_identity")
                or any(type(usage.get(k)) is not int for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
                or usage["prompt_tokens"] != len(item.get("input", {}).get("input_ids", []))
                or usage["completion_tokens"] != len(item.get("output_ids", []))
                or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]
                or not 0 < usage["total_tokens"] <= before.get("reserved_maximum_tokens", 0)):
            errors.append(key + ":incomplete_or_mismatched_actual_native_receipt")
        else:
            actual += usage["total_tokens"]
            actual_calls.append({"attempt_id": key, "usage": usage,
                "native_input_sha256": item["input"].get("sha256"),
                "actor_identity": item["actor_identity"], "online_window_id": before.get("online_window_id")})
    for key, item in started.items():
        preparation = prepared.get(key, {})
        if (key not in prepared or item.get("generation_started") is not True
                or item.get("attempt_id") != key or preparation.get("attempt_id") != key
                or any(item.get(field) != preparation.get(field) for field in
                    ("native_input", "actor_identity", "online_window_id", "reserved_maximum_tokens"))):
            errors.append(key + ":missing_preparation_or_start")
        if key not in complete:
            uncertain += item["reserved_maximum_tokens"]
    return {"prepared_requests": len(prepared), "started_generations": len(started),
        "complete_generations": len(complete), "known_actual_tokens": actual,
        "uncertain_reservation_tokens": uncertain, "ledger_tokens": actual + uncertain,
        "complete_actual_tokens": actual if not uncertain and not errors else None,
        "prepared_without_generation": sorted(set(prepared) - set(started)),
        "integrity_errors": errors, "all_started_settled": not uncertain and not errors,
        "calls_path": str(calls.resolve()), "actual_calls": actual_calls}


def classify_closed(row, *, result, accounting, guard, episode_guard, measurement):
    reasons = []
    if accounting.get("all_started_settled") is not True or accounting.get("integrity_errors"):
        reasons.append("native_generation_or_accounting_unresolved")
    if guard.get("passed") is not True or not all(episode_guard.get(k) is True
            for k in ("learning_unchanged", "rng_restored_exactly")):
        reasons.append("terminal_actor_or_rng_guard_unresolved")
    if type(result.get("R_code")) is not int or result["R_code"] not in (0, 1):
        reasons.append("terminal_code_unknown")
    if row["condition"] != "R" and (type(result.get("R_joint")) is not int or result["R_joint"] not in (0, 1)):
        reasons.append("project_fixed_delivery_unknown")
    if measurement.get("decision") != "continue":
        reasons.append("mechanical_measurement_not_continue")
    if accounting.get("known_actual_tokens", 0) > row["generation_tokens"]:
        reasons.append("slot_generation_budget_exceeded")
    return {"decision": "global_pause" if reasons else "continue", "reasons": reasons,
        "selected_by_reward": False, "terminal_code_unknown_always_pauses": True}


def measure_native(result, *, row, owner_identity, accounting):
    """Read the new native episode's own exact ledger and preexecution proof."""
    from proworksim.software_calibration_runtime_v051 import validate_native_input

    ledger = result["ledger"]
    errors = []
    calls = {item["attempt_id"]: item for item in accounting["actual_calls"]}
    declared = ledger.get("calls", [])
    if (result.get("status") != "bounded_native_episode_closed"
            or result.get("task_id") != row["task_id"] or result.get("seed") != row["seed"]
            or ledger.get("episode_binding", {}).get("task_id") != row["task_id"]
            or ledger.get("episode_binding", {}).get("condition") != "R"
            or ledger.get("episode_binding", {}).get("seed") != row["seed"]
            or ledger.get("episode_binding", {}).get("initial_files_sha256") != result.get("initial_files_sha256")
            or ledger.get("inflight") is not None or ledger.get("reserved_unknown_tokens") != 0
            or ledger.get("attempts") != accounting["started_generations"]
            or ledger.get("complete_responses") != accounting["complete_generations"]
            or ledger.get("known_actual_tokens") != accounting["known_actual_tokens"]
            or not 0 <= ledger.get("decisions", -1) <= 128
            or not 0 <= ledger.get("attempts", -1) <= ledger["decisions"]
            or not 0 <= result.get("actions", -1) <= 128):
        errors.append("native_episode_or_ledger_mismatch")
    if (len(declared) != len(calls)
            or {item.get("native_attempt_id") for item in declared} != set(calls)):
        errors.append("native_call_inventory_mismatch")
    for index, item in enumerate(declared, 1):
        actual = calls.get(item.get("native_attempt_id"), {})
        if (item.get("attempt") != index or actual.get("actor_identity") != owner_identity
                or actual.get("online_window_id") != "v051-cal2-R:" + row["task_id"]
                or any(item.get(key) != actual.get(key) for key in ("usage", "native_input_sha256"))):
            errors.append("native_call_source_or_actual_usage_mismatch")
    if len(ledger.get("preexecution_rejections", [])) > 1:
        errors.append("native_episode_continued_after_preexecution_stop")
    for reference in ledger.get("preexecution_rejections", []):
        path = Path(reference["path"])
        item = read_json(path)
        if sha_file(path) != reference["sha256"]:
            errors.append("native_rejection_source_changed")
        native = item["native_input"]
        fits = validate_native_input(native, CONTRACT)
        reason = item.get("reason")
        valid_reason = ((reason == "full_native_context_preexecution_rejection" and not fits)
            or (reason == "full_request_token_reservation_insufficient" and fits
                and item["P"] + item["O"] > item["remaining_tokens"]))
        if (not valid_reason or item.get("P") != native["prompt_tokens"]
                or item.get("O") != 2048 or item.get("C") != 18432
                or item.get("fits") is not fits or item.get("generation_started") is not False
                or item.get("new_side_effect") is not False or item.get("actor_identity") != owner_identity
                or item.get("actual_tokens") != ledger["known_actual_tokens"]
                or item.get("remaining_tokens") != 500000 - ledger["known_actual_tokens"]
                or item.get("decisions") != ledger["decisions"] or item.get("attempts") != ledger["attempts"]
                or ledger.get("stop_reason") != reason
                or item.get("episode_binding") != ledger["episode_binding"]
                or item["episode_binding"].get("task_id") != row["task_id"]
                or item["episode_binding"].get("seed") != row["seed"]):
            errors.append("native_preexecution_rejection_not_fully_bound")
    return {"version": VERSION, "decision": "global_pause" if errors else "continue",
        "errors": errors, "read_only": True, "new_model_calls": 0,
        "local_preexecution_rejections": len(ledger.get("preexecution_rejections", [])),
        "score_used_for_continuation": False}


def worker(root, slot_id, attempt):
    root, output = Path(root).resolve(), Path(attempt).resolve()
    plan = frozen(root)
    matches = [row for row in plan["rows"] if row["slot_id"] == slot_id]
    if len(matches) != 1 or output.exists():
        raise ValueError("A fresh attempt for one frozen CAL2 slot is required")
    if Path(sys.executable).resolve() != Path(plan["native_python"]).resolve():
        raise ValueError("Use the frozen native interpreter")
    row = matches[0]
    directory = root / "slots" / slot_id
    if directory.exists():
        raise FileExistsError("An entered CAL2 slot is never replayed")
    output.mkdir(parents=True)
    res, startup = resource_modules(plan)
    binding = res.binding_from_env()
    if binding["gpu_index"] not in plan["gpu_preference"]:
        raise ValueError("GPU outside explicit current authorization")
    phase(output, "reservation")
    launch_identity = {"plan": ref(root / "plan.json"), "slot_id": slot_id}
    try:
        startup.acquire_startup_cache(output / "startup", binding, identity=launch_identity)
    except startup.StartupResourceUnavailable:
        write(output / "report.json", {"status": "pre_model_resource_unavailable",
            "model_loader_entered": False, "generation_calls": 0, "slot_id": slot_id,
            "source_plan": ref(root / "plan.json")})
        return 75
    directory.mkdir(parents=True, exist_ok=False)
    write(directory / "started.json", {"row": row, "attempt": str(output),
        "pid": os.getpid(), "at": time.time(), "source_plan": ref(root / "plan.json"),
        "scope": "Slot entered before model load; no model or loader retry after this point"})
    phase(output, "loading")
    try:
        from proworksim.repository_sources_v051 import RepositorySources
        from proworksim.software_calibration_runtime_v051 import load_actor
        from proworksim.software_calibration_repo_tests_v051 import run_repository_tests

        owner = load_actor(plan["model_path"], manifest=plan["model_manifest"]["path"],
            contract=CONTRACT, path="project", output=output / "resident",
            checkpoint=plan["S_star"]["checkpoint"]["path"] if row["condition"] == "U" else None)
        phase(output, "preparation")
        episode_started = None

        def runner(**kwargs):
            phase(output, "scoring", episode_started_at=episode_started)
            try:
                return run_repository_tests(**kwargs)
            finally:
                phase(output, "episode", episode_started_at=episode_started)

        provider = RepositorySources(plan["repository_source_root"], runner=runner,
            expected_manifest_sha256=plan["adapter_manifest"]["sha256"])
        source = provider.build_case(row["task_id"])
        original_generate = owner.generate_native

        def generation(record):
            phase(output, "generation", episode_started_at=episode_started)
            try:
                # This existing resource helper allocates no retained tensors and
                # leaves the original numerical call, arguments and RNG untouched.
                with res.native_cache_context(owner, output / "native-cache", binding):
                    return original_generate(record)
            finally:
                phase(output, "episode", episode_started_at=episode_started)

        owner.generate_native = generation
        if row["condition"] == "R":
            from proworksim.software_calibration_v051_mini import prepare_buggy_worktree, run_native_case
            from proworksim.software_calibration_native_grade_v051 import grade_native_candidate

            receipt = prepare_buggy_worktree(source["files"], directory / "native-worktree",
                receipt_path=directory / "worktree-origin.json")
            task = {**provider.runner_spec(row["task_id"]), "problem_statement": source["root_goal"]}
            episode_started = time.time()
            phase(output, "episode", episode_started_at=episode_started)
            result = run_native_case(owner, task=task, worktree=directory / "native-worktree", seed=row["seed"],
                output=output / "episode", mini_manifest=plan["mini_manifest"]["path"],
                workspace_receipt=receipt, initial_files=source["files"])
            candidate = read_json(Path(result["candidate_files"]))
            grade = grade_native_candidate(provider=provider, task_id=row["task_id"],
                candidate_files=candidate, run_root=output / "terminal-code")
            result.update(R_code=grade["R_code"], Q_task_terminal=grade["Q_task"],
                R_joint=None, project_delivery_endpoint="not_applicable", terminal_code=grade)
        else:
            from proworksim.software_calibration_world_v051 import build_software_collaboration_case
            from proworksim.software_calibration_collector_v051 import collect_episode

            prepared = build_software_collaboration_case(row["task_id"], output / "prepared", provider=provider)
            episode_started = time.time()
            phase(output, "episode", episode_started_at=episode_started)
            result = collect_episode(owner, prepared, output / "episode", sampling_seed=row["seed"],
                slot_id=slot_id, calibration_condition=row["condition"])
        episode_closed = time.time()
        if episode_closed - episode_started >= LIMITS["episode_seconds"]:
            raise TimeoutError("CAL2 episode including final grading exceeded its hard bound")
        phase(output, "measurement", episode_started_at=episode_started, episode_closed_at=episode_closed)
        accounting = native_accounting(output / "resident")
        if row["condition"] == "R":
            measurement = measure_native(result, row=row, owner_identity=owner.freeze_identity(), accounting=accounting)
            write(output / "measurement.json", measurement)
        else:
            from proworksim.software_calibration_measurement_v051 import measure_slot
            measurement = measure_slot(result, output / "measurement.json", provider=provider)
            if result.get("usage", {}).get("total_tokens") != accounting["known_actual_tokens"]:
                measurement = {**measurement, "decision": "global_pause", "native_usage_mismatch": True}
                write(output / "native-usage-mismatch.json", measurement)
        episode_guard = read_json(output / "episode/evaluation-guard.json")
        guard = owner.verify_evaluation_guard()
        verdict = classify_closed(row, result=result, accounting=accounting, guard=guard,
            episode_guard=episode_guard, measurement=measurement)
        report = {"version": VERSION, "status": "closed" if verdict["decision"] == "continue" else "paused",
            "row": row, "source_plan": ref(root / "plan.json"), "result": result,
            "accounting": accounting, "measurement": measurement, "guard": guard,
            "episode_guard": episode_guard, "verdict": verdict,
            "episode_started_at": episode_started, "episode_closed_at": episode_closed,
            "new_backward_calls": 0, "new_parameter_updates": 0}
        write(output / "report.json", report)
        write(directory / "closed.json", {"report": ref(output / "report.json"), "decision": verdict["decision"]})
        return 0
    except BaseException as error:
        write(output / "interruption.json", {"version": VERSION, "row": row,
            "error": {"type": type(error).__name__, "message": str(error)}, "at": time.time(),
            "model_retry_allowed": False, "formal_outcome": None})
        raise


def ledger(root, rows):
    totals = {"known_actual_tokens": 0, "uncertain_reservation_tokens": 0,
        "started_generations": 0, "complete_generations": 0}
    outcomes, errors = [], []
    for row in rows:
        folder = Path(root) / "slots" / row["slot_id"]
        started = folder / "started.json"
        closed = folder / "closed.json"
        outcome = {"slot_id": row["slot_id"], "started": started.exists(),
            "R_code": None, "R_joint": None, "closed": closed.exists()}
        if started.exists():
            attempt = Path(read_json(started)["attempt"])
            usage = native_accounting(attempt / "resident")
            for key in totals:
                totals[key] += usage[key]
            errors.extend(usage["integrity_errors"])
        if closed.exists():
            report = read_json(checked(read_json(closed)["report"]))
            outcome.update({key: report["result"].get(key) for key in ("R_code", "R_joint")})
            outcome["decision"] = report["verdict"]["decision"]
        outcomes.append(outcome)
    return {**totals, "ledger_tokens": totals["known_actual_tokens"] + totals["uncertain_reservation_tokens"],
        "complete_actual_tokens": totals["known_actual_tokens"] if not totals["uncertain_reservation_tokens"] and not errors else None,
        "integrity_errors": errors, "outcomes": outcomes,
        "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_calls": 0}


def worker_completion(row, attempt, report, *, plan_ref, slot_started, cleanup_passed):
    """The only retry is a recorded zero-model startup capacity failure."""
    if (attempt.get("exit_code") == 75 and attempt.get("reason") is None and not slot_started
            and cleanup_passed and report == {"status": "pre_model_resource_unavailable",
                "model_loader_entered": False, "generation_calls": 0, "slot_id": row["slot_id"],
                "source_plan": plan_ref}):
        return "not_started"
    if (attempt.get("exit_code") == 0 and attempt.get("reason") is None and cleanup_passed
            and report.get("status") == "closed" and report.get("row") == row
            and report.get("source_plan") == plan_ref and report.get("verdict", {}).get("decision") == "continue"):
        verdict = classify_closed(row, result=report["result"], accounting=report["accounting"],
            guard=report["guard"], episode_guard=report["episode_guard"], measurement=report["measurement"])
        if verdict["decision"] == "continue":
            return "complete"
    return "stopped"


def supervise(root):
    from proworksim.software_calibration_process_v051 import cleanup_registered_children

    root = Path(root).resolve()
    plan = frozen(root)
    if (root / "supervisor.json").exists():
        raise FileExistsError("A started CAL2 inventory cannot be replayed")
    res, _ = resource_modules(plan)
    states = {row["slot_id"]: {"status": "not_started", "attempts": []} for row in plan["rows"]}
    by_id = {row["slot_id"]: row for row in plan["rows"]}
    summary = {"version": VERSION, "status": "waiting", "started_at": time.time(),
        "observer_pid": os.getpid(), "plan": ref(root / "plan.json"), "states": states}
    active, streams, guards = {}, {}, {}

    def publish():
        summary.update(observed_at=time.time(), ledger=ledger(root, plan["rows"]),
            gpu_worker_seconds=sum(a.get("seconds", time.time() - a["started_at"])
                for state in states.values() for a in state["attempts"]))
        write(root / "supervisor.json", summary)

    def pause(reason, detail):
        if not (root / "pause.json").exists():
            write(root / "pause.json", {"kind": reason, "detail": detail, "at": time.time()})

    def close(name, reason=None):
        process = active[name]
        attempt = states[name]["attempts"][-1]
        output = Path(attempt["output"])
        cleanups = []
        if process.poll() is None:
            write(output / "host-stop.json", {"reason": reason, "at": time.time(),
                "target_pid": process.pid, "identity": worker_identity(process.pid)})
            cleanups.append(cleanup_registered_children(output, process.pid,
                attempt["identity"]["start_ticks"], reason="before_worker_stop:" + str(reason)))
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
        cleanups.append(cleanup_registered_children(output, process.pid,
            attempt["identity"]["start_ticks"], reason="after_worker_exit:" + str(reason)))
        path = output / "report.json"
        report = read_json(path) if path.exists() else {}
        attempt.update(ended_at=time.time(), seconds=time.time() - attempt["started_at"],
            exit_code=process.returncode, reason=reason, report=report, child_cleanup=cleanups)
        streams.pop(name).close()
        active.pop(name)
        guards.pop(name)
        states[name]["status"] = worker_completion(by_id[name], attempt, report,
            plan_ref=ref(root / "plan.json"), slot_started=(root / "slots" / name / "started.json").exists(),
            cleanup_passed=all(item["passed"] for item in cleanups))
        if states[name]["status"] == "stopped":
            pause("execution_or_measurement_pause", {"slot_id": name, "attempt": attempt})

    def receive(signum, _frame):
        raise InterruptedError("CAL2 supervisor received signal " + str(signum))

    signal.signal(signal.SIGTERM, receive)
    signal.signal(signal.SIGINT, receive)
    publish()
    try:
        while True:
            for name, process in list(active.items()):
                if process.poll() is not None:
                    close(name)
            if active:
                with ThreadPoolExecutor(max_workers=len(active)) as pool:
                    futures = {name: pool.submit(target_resources, states[name]["attempts"][-1]["gpu"]["index"],
                        worker_pid=process.pid) for name, process in active.items()}
                    for name, future in futures.items():
                        sample = future.result()
                        process, attempt = active[name], states[name]["attempts"][-1]
                        if process.poll() is not None:
                            close(name)
                            continue
                        verdict = guards[name].observe(sample, time.time(), process.pid,
                            attempt["gpu"]["index"], own_memory_limit_mib=None)
                        write(Path(attempt["output"]).with_suffix(".telemetry.json"), verdict)
                        reason = verdict["stop_reason"]
                        path = Path(attempt["output"]) / "task.json"
                        current = read_json(path) if path.exists() else {"kind": "loading", "started_at": attempt["started_at"]}
                        reason = reason or deadline_reason(current, time.time())
                        if rss(process.pid) > LIMITS["rss_bytes"]:
                            reason = reason or "host_rss_budget"
                        if reason:
                            close(name, reason)
            if artifact_bytes(root) > LIMITS["artifact_bytes"]:
                pause("artifact_budget", {})
                for name in list(active):
                    close(name, "artifact_budget")
            if not (root / "pause.json").exists() and len(active) < LIMITS["max_residents"]:
                if shutil.disk_usage(root).free < LIMITS["minimum_volume_free_bytes"]:
                    pause("volume_reserve", {})
                else:
                    sample = target_resources(",".join(map(str, plan["gpu_preference"])), worker_pid=os.getpid())
                    write(root / "admission-latest.json", sample)
                    cards = res.available_cards(plan, sample,
                        excluded=[states[name]["attempts"][-1]["gpu"]["index"] for name in active])
                    pending = [name for name, state in states.items() if state["status"] == "not_started"]
                    for name, card in zip(pending[:LIMITS["max_residents"] - len(active)], cards):
                        output = root / "workers" / name / f"attempt-{len(states[name]['attempts']) + 1:03d}"
                        output.parent.mkdir(parents=True, exist_ok=True)
                        binding = res.launch_target(card)
                        env = {**os.environ, "CUDA_VISIBLE_DEVICES": str(card["index"]),
                            "TOKENIZERS_PARALLELISM": "false", "OMP_NUM_THREADS": "8", "MKL_NUM_THREADS": "8",
                            "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_OFFLINE": "1",
                            "TRANSFORMERS_OFFLINE": "1", "PYTHONPATH": os.pathsep.join([
                                plan["runtime_dependency_path"], str(Path(plan["source_root"]) / "src"), plan["source_root"]])}
                        env.pop("PROWORKSIM_REPLICA_GPUS", None)
                        env = res.worker_env(env, binding)
                        command = [plan["native_python"], "-m", "scripts.software_calibration_v051_cal2", "worker",
                            "--root", str(root), "--slot", name, "--attempt", str(output)]
                        stream = output.with_suffix(".log").open("wb")
                        launched = time.time()
                        process = subprocess.Popen(command, cwd=plan["source_root"], env=env,
                            stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                        identity = worker_identity(process.pid)
                        attempt = {"started_at": launched, "pid": process.pid, "output": str(output),
                            "gpu": card, "binding": binding, "command": command, "identity": identity}
                        states[name]["attempts"].append(attempt)
                        states[name]["status"] = "running"
                        active[name], streams[name] = process, stream
                        guards[name] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
                        write(output.with_suffix(".launch.json"), attempt)
            if not active and ((root / "pause.json").exists() or all(s["status"] == "complete" for s in states.values())):
                break
            summary["status"] = "running" if active else "waiting"
            publish()
            time.sleep(LIMITS["poll_seconds"])
    except BaseException as error:
        pause("supervisor_interrupted_or_fault", {"type": type(error).__name__, "message": str(error)})
        for name in list(active):
            close(name, "supervisor_interrupted_or_fault")
        raise
    finally:
        summary.update(status="complete" if all(s["status"] == "complete" for s in states.values()) else "paused",
            ended_at=time.time())
        publish()
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "supervise", "worker"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--slot")
    parser.add_argument("--attempt", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.root)
    elif args.command == "supervise":
        supervise(args.root)
    else:
        raise SystemExit(worker(args.root, args.slot, args.attempt))


if __name__ == "__main__":
    main()
