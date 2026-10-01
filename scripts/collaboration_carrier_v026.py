"""One frozen resident executes its predeclared v026 carrier development slots.

The original checkpoint source marker is immutable. A separate migration proof
binds its exact complete state to the new world/harness protocol; no training or
probability replay is performed by this worker.
"""

import argparse
from collections import Counter
import copy
import csv
import io
import math
import os
from pathlib import Path
import signal
import subprocess
import time

from proworksim.audit import code_identity
from proworksim.episode import begin_episode, finish_episode
from proworksim.online_collection import run_fragment
from proworksim.storage import digest, json_bytes, read_json
from scripts.evaluate_work_v022 import checked, reference, write

VERSION = "reciprocal-carrier-development-v0.26-r2"
# Original loading attempts consumed 25.742102 / 25.402630 seconds.
# Charge each upward to 26 seconds, retaining the original total 4 GPU-hour cap.
RESOURCE_CAPS = {"worker-0": 7174, "worker-1": 7174}
TASK_CAPS = {"loading": 900, "episode": 1200, "boundary": 600}
INVARIANT_MODULES = tuple(
    "src/proworksim/" + name + ".py"
    for name in (
        "online_training",
        "candidate_runtime_v015",
        "candidate_runtime_v0151",
        "candidate_runtime_v017",
        "candidate_runtime_v020",
        "candidate_runtime_v0201",
        "collaboration_actor_v022",
        "functional_qwen_v022",
        "deterministic_work_v024",
        "local_model_service",
        "model_policy",
        "model_transport",
        "format_diagnostics",
        "training",
        "storage",
        "work_view_v022",
        "staff_runtime",
    )
)
FIXED_LIMITS = {
    "resource_caps": RESOURCE_CAPS,
    "task_caps": TASK_CAPS,
    "internal_gpu_seconds": 14348,
    "max_concurrent_model_instances": 2,
    "per_episode_model_instances": 1,
    "max_new_episodes": 16,
    "max_new_actor_steps": 0,
    "max_new_critic_steps": 0,
    "model_api_calls": 0,
    "automatic_recovery": False,
    "automatic_successors": [],
    "max_wall_seconds": 64800,
    "queue_deadline_at": 1790870400,  # 2026-10-02 00:00 Asia/Shanghai
    "wall_deadline_at": 1790877600,  # Final absolute ceiling, 02:00
    "minimum_free_gpu_mib": 78000,
    "max_idle_gpu_utilization_percent": 5,
    "gpu_idle_stability_seconds": 120,
    "require_unoccupied_gpu": True,
    "host_rss_bytes": 64 * 1024**3,
    "artifact_bytes": 12 * 1024**3,
    "own_gpu_memory_mib": 32768,
    "minimum_temp_free_bytes": 1024**3,
    "gpu_preference": [0, 4, 5, 7],
    "python_hash_seed": "0",
}


def released_gpus(plan, sample, *, excluded=()):
    """Only explicitly allowed, currently unoccupied and idle A100 devices."""
    if any(sample.get(key, {}).get("returncode") != 0 for key in ("gpus", "processes")):
        return []
    occupied = set()
    for row in csv.reader(io.StringIO(sample["processes"]["stdout"])):
        if len(row) != 4:
            return []
        occupied.add(row[0].strip())
    available = set()
    try:
        for row in csv.reader(io.StringIO(sample["gpus"]["stdout"])):
            if len(row) != 6:
                return []
            index, uuid, name, free, total, utilization = (value.strip() for value in row)
            index, free, total, utilization = int(index), float(free), float(total), float(utilization)
            if (index in plan["gpu_preference"] and index not in excluded
                    and uuid not in occupied and "A100" in name
                    and all(math.isfinite(value) for value in (free, total, utilization))
                    and total >= 81920 and free >= plan["minimum_free_gpu_mib"]
                    and 0 <= utilization <= plan["max_idle_gpu_utilization_percent"]):
                available.add(index)
    except ValueError:
        return []
    return [index for index in plan["gpu_preference"] if index in available]


def validate_previous_loading_attempt(plan):
    """Resume only the unchanged sixteen unstarted slots; debit both old attempts."""
    previous = plan["previous_attempt"]
    original = read_json(checked(previous["plan"]))
    summary = read_json(checked(previous["supervisor"]))
    if (original.get("version") != "reciprocal-carrier-development-v0.26"
            or original.get("resource_caps") != {"worker-0": 7200, "worker-1": 7200}
            or original.get("internal_gpu_seconds") != 14400
            or summary.get("status") != "closed_with_incomplete_workers"
            or summary.get("plan") != previous["plan"]
            or summary.get("parameter_updates") != 0
            or set(previous.get("workers", {})) != set(RESOURCE_CAPS)):
        raise ValueError("R1 requires the original terminal loading-only C1 attempt")
    for key in ("checkpoint_marker", "old_worker_source", "invariant_module_sha256",
                "prior_model_plan", "owner_recipe", "catalog", "source_pin", "assets_root", "qualification"):
        if plan.get(key) != original.get(key):
            raise ValueError("R1 must preserve the original model, carrier and qualification: " + key)
    costs = {}
    for name, refs in previous["workers"].items():
        state, report = read_json(checked(refs["state"])), read_json(checked(refs["report"]))
        elapsed = state.get("elapsed_gpu_seconds")
        if (state.get("worker") != name or state.get("status") != "stopped"
                or state.get("stop_reason") != "worker_failed" or state.get("completed_slot_count") != 0
                or state.get("task", {}).get("kind") != "loading"
                or report.get("status") != "interrupted_or_error"
                or report.get("error", {}).get("type") != "OutOfMemoryError"
                or report.get("rows") or report.get("restoration") or report.get("final_actor_identity")
                or report.get("source_unchanged") is not True
                or any(report.get(key) != 0 for key in ("new_actor_steps", "new_critic_steps", "model_api_calls"))
                or not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed)
                or not 0 < elapsed <= 26 or 7200 - math.ceil(elapsed) != RESOURCE_CAPS[name]
                or state.get("slots") != summary["worker_assignments"][name]
                or report.get("slots") != summary["worker_assignments"][name]):
            raise ValueError("Previous worker is not an immutable pre-episode loading failure: " + name)
        costs[name] = elapsed
    if (previous.get("actual_gpu_seconds") != sum(costs.values())
            or previous.get("budget_charge_seconds") != sum(math.ceil(value) for value in costs.values())
            or previous["budget_charge_seconds"] + plan["internal_gpu_seconds"] != 14400):
        raise ValueError("Previous loading cost must remain inside the original four GPU-hour cap")
    return costs


def validate_previous_waiting_queue(plan):
    """A user-requested deadline extension may replace only an unused queue."""
    refs = plan["previous_queue"]
    previous = read_json(checked(refs["plan"]))
    summary = read_json(checked(refs["supervisor"]))
    transition = read_json(checked(refs["transition"]))
    if (previous.get("version") != "reciprocal-carrier-development-v0.26-r1"
            or summary.get("plan") != refs["plan"]
            or summary.get("status") != "supervisor_error"
            or summary.get("error", {}).get("type") != "KeyboardInterrupt"
            or summary.get("terminated_gpu_seconds") != 0
            or summary.get("running_gpu_seconds") != 0
            or transition.get("operation") != "user_requested_wait_extension"
            or transition.get("new_queue_deadline_beijing") != "2026-10-02T00:00:00+08:00"
            or set(refs.get("workers", {})) != set(RESOURCE_CAPS)):
        raise ValueError("Deadline extension requires the archived zero-GPU waiting queue")
    for key, value in previous.items():
        if key not in {"version", "queue_deadline_at", "wall_deadline_at"} and plan.get(key) != value:
            raise ValueError("Deadline extension changed a non-scheduling declaration: " + key)
    for name, ref in refs["workers"].items():
        path = checked(ref)
        state = read_json(path)
        if (state.get("status") != "not_started_supervisor_interrupted"
                or state.get("attempted") is not False or state.get("pid") is not None
                or state.get("gpu") is not None or state.get("elapsed_gpu_seconds") is not None
                or state.get("slots") != summary["worker_assignments"][name]
                or (path.parent / "actual").exists()):
            raise ValueError("A started worker cannot be repeated by a queue-only extension: " + name)
    return {"previous_queue_gpu_seconds": 0, "same_unstarted_slots": True}


def assignments(catalog):
    """Keep every case/seed's conditions on one resident, independent of outcomes."""
    cases, slots = catalog["cases"], catalog["slots"]
    ids = [case["case_id"] for case in cases]
    if len(ids) != 4 or len(set(ids)) != 4 or len(slots) != 16:
        raise ValueError("C1 requires four distinct cases and sixteen fixed slots")
    if len({slot["slot_id"] for slot in slots}) != 16:
        raise ValueError("C1 slot identities must be unique")
    expected = {
        (case, condition, repeat)
        for case in ids
        for condition in ("normal", "single_pass")
        for repeat in range(2)
    }
    actual = {(slot["case_id"], slot["condition"], slot["repeat_index"]) for slot in slots}
    if actual != expected:
        raise ValueError(
            "All four cases, both communication conditions and both repeats are required"
        )
    seeds = {}
    for slot in slots:
        seed = slot["sampling_seed"]
        if type(seed) is not int or not 0 <= seed < 2**63 or slot["seed"] != seed:
            raise ValueError("Each slot needs one explicit finite unchanged sampling seed")
        key = slot["case_id"], slot["repeat_index"]
        if key in seeds and seeds[key] != seed:
            raise ValueError("Paired communication conditions must use the same seed")
        seeds[key] = seed
    if any(seeds[(case, 0)] == seeds[(case, 1)] for case in ids):
        raise ValueError("The two repeats must have different fixed seeds")
    return {
        f"worker-{worker}": [
            copy.deepcopy(slot) for slot in slots if ids.index(slot["case_id"]) % 2 == worker
        ]
        for worker in range(2)
    }


def verify_invariant_source(plan, source_root=None):
    """Check the actual old commit and current files; never trust declared hashes alone."""
    root = Path(source_root or Path(__file__).resolve().parents[1])
    expected = plan["invariant_module_sha256"]
    if set(expected) != set(INVARIANT_MODULES):
        raise ValueError("The full frozen numerical actor and policy module set is required")
    commit = plan["old_worker_source"]["code_commit"]
    if (
        not isinstance(commit, str)
        or len(commit) != 40
        or any(c not in "0123456789abcdef" for c in commit)
    ):
        raise ValueError("Old actor source must be an exact Git commit")
    observed = {}
    for relative in INVARIANT_MODULES:
        old = subprocess.check_output(["git", "show", commit + ":" + relative], cwd=root)
        current = (root / relative).read_bytes()
        if digest(old) != expected[relative] or digest(current) != expected[relative]:
            raise ValueError("Frozen actor execution changed across source migration: " + relative)
        observed[relative] = {"old_sha256": digest(old), "new_sha256": digest(current)}
    return observed


QUALIFICATION_VERSION = "reciprocal-carrier-cpu-controls-v0.26"
QUALIFICATION_SOURCE_MODULES = (
    "scripts/reciprocal_carrier_controls_v026.py",
    "scripts/retail_work_controls_v025.py",
    "src/proworksim/templates/reciprocal_data_v026.py",
    "src/proworksim/reciprocal_runtime_v026.py",
    "src/proworksim/reciprocal_interface_v026.py",
    "src/proworksim/work_interface.py",
    "src/proworksim/world_core.py",
    "src/proworksim/presentations.py",
)
QUALIFICATION_LIMITS = {
    "max_context_tokens": 16384,
    "max_output_tokens": 2048,
    "role_decision_limits": {"maintainer": 24, "consumer": 24},
}


def validate_cpu_qualification(plan, catalog, *, source_root=None, current_source=None):
    """Admit only the final complete CPU/tokenizer qualification of this exact Γ.

    Git commit/dirty flags may change when completed results are committed. The
    actual src tree, critical script bytes, catalog, tokenizer and budgets may
    not change. No SQL execution, tokenizer replay or model loading occurs here.
    """
    if not isinstance(plan.get("qualification"), dict):
        raise ValueError(
            "A passed frozen CPU qualification reference is required before GPU execution"
        )
    report = read_json(checked(plan["qualification"]))
    root = Path(source_root or Path(__file__).resolve().parents[1])
    current = current_source or code_identity()
    if (
        report.get("version") != QUALIFICATION_VERSION
        or report.get("passed") is not True
        or report.get("gpu_launch_qualified") is not True
        or report.get("code_unchanged_during_qualification") is not True
        or report.get("source_tree_unchanged_during_qualification") is not True
        or report.get("source_tree_sha256") != current["source_tree_sha256"]
        or report.get("negative_controls_passed") is not True
        or any(report.get(key) != 0 for key in ("model_calls", "gpu_calls", "parameter_updates"))
        or report.get("model_training_eligible") is not False
    ):
        raise ValueError(
            "CPU qualification is incomplete, failed or belongs to another source tree"
        )
    hashes = report.get("code_identity", {})
    if set(hashes) != set(QUALIFICATION_SOURCE_MODULES):
        raise ValueError("Qualification must bind the complete frozen carrier/harness script set")
    for relative, sha in hashes.items():
        if digest((root / relative).read_bytes()) != sha:
            raise ValueError("Qualified carrier/harness source bytes changed: " + relative)
    qualified_catalog = read_json(checked(report["catalog_reference"]))
    planned_catalog = read_json(checked(plan["catalog"]))
    prior = read_json(checked(plan["prior_model_plan"]))
    checked(plan["source_pin"])
    if (
        qualified_catalog != catalog
        or planned_catalog != catalog
        or report.get("catalog_sha256") != digest(json_bytes(catalog))
        or report.get("source_manifest_sha256") != plan["source_pin"]["sha256"]
        or report.get("limits") != QUALIFICATION_LIMITS
        or prior["runtime_profile"]["max_context_tokens"]
        != QUALIFICATION_LIMITS["max_context_tokens"]
        or prior["runtime_profile"]["max_output_tokens"]
        != QUALIFICATION_LIMITS["max_output_tokens"]
        or Path(report.get("tokenizer_path", "")).resolve() != Path(prior["model"]).resolve()
        or any(
            case.get("role_decision_limits") != QUALIFICATION_LIMITS["role_decision_limits"]
            for case in catalog["cases"]
        )
    ):
        raise ValueError(
            "Qualified catalog, source material, tokenizer or unchanged resource limits differ"
        )
    cases = [case["case_id"] for case in catalog["cases"]]
    choices = (
        ("normal", "constraint_first"),
        ("normal", "query_first"),
        ("single_pass", "constraint_first"),
    )
    controls = report.get("controls", [])
    positives = [row for row in controls if row.get("negative_control") is None]
    negatives = [row for row in controls if row.get("negative_control") is not None]
    expected = {(case, condition, route) for case in cases for condition, route in choices}
    if (
        len(positives) != 12
        or {(row.get("case_id"), row.get("condition"), row.get("route")) for row in positives}
        != expected
        or len(negatives) != 2
        or {
            (
                row.get("case_id"),
                row.get("condition"),
                row.get("route"),
                row.get("negative_control"),
            )
            for row in negatives
        }
        != {
            (cases[1], "normal", "constraint_first", "ignore_demand_distinction"),
            (cases[2], "single_pass", "constraint_first", "ignore_unit_distinction"),
        }
    ):
        raise ValueError(
            "Qualification must retain all twelve positive routes and both fixed negatives"
        )
    for row in controls:
        counts, tokens = row.get("program_requests", {}), row.get("tokens", [])
        positive = row.get("negative_control") is None
        assessment = row.get("assessment", {})
        if (
            row.get("passed") is not positive
            or assessment.get("eligible") is not True
            or assessment.get("completed") is not positive
            or row.get("tokenizer_checked") is not True
            or row.get("within_role_budgets") is not True
            or row.get("role_limits") != QUALIFICATION_LIMITS["role_decision_limits"]
            or row.get("context_limit") != 16384
            or row.get("reserved_output") != 2048
            or row.get("token_failures") != []
            or row.get("tool_refusals") != []
            or row.get("model_calls") != 0
            or row.get("parameter_updates") != 0
            or set(counts) != {"maintainer", "consumer"}
            or any(type(count) is not int or not 0 < count <= 24 for count in counts.values())
            or len(tokens) != sum(counts.values())
            or any(
                token.get("fits_prompt_and_reserved_output") is not True
                or token.get("program_output_within_limit") is not True
                or type(token.get("prompt_tokens")) is not int
                or not 0 < token["prompt_tokens"] <= 16384 - 2048
                or type(token.get("program_output_tokens")) is not int
                or not 0 < token["program_output_tokens"] <= 2048
                for token in tokens
            )
        ):
            raise ValueError(
                "Qualification contains an incomplete route, failed negative or exceeded native budget"
            )
        # Read-only existence/byte binding, not a second world or token replay.
        checked(row["episode_manifest"])
        checked(row["requests_reference"])
    pairs = report.get("counterfactual_checks", [])
    expected_pairs = {
        (indices, condition, route) for indices in ((0, 1), (2, 3)) for condition, route in choices
    }
    if (
        len(pairs) != 6
        or {
            (tuple(row.get("case_indices", [])), row.get("condition"), row.get("route"))
            for row in pairs
        }
        != expected_pairs
        or any(
            row.get("passed") is not True
            or row.get("first_request_bytes_identical") is not True
            or len(row.get("first_request_sha256", [])) != 2
            or row["first_request_sha256"][0] != row["first_request_sha256"][1]
            for row in pairs
        )
    ):
        raise ValueError("All six raw-input counterfactual qualification pairs must pass")
    fairness = report.get("fairness_checks", [])
    if (
        len(fairness) != 4
        or {row.get("case_index") for row in fairness} != set(range(4))
        or any(
            any(
                row.get(key) is not True
                for key in (
                    "passed",
                    "business_tool_definitions_equal",
                    "same_decision_context_output_budgets",
                    "exactly_one_legal_demand_forward",
                    "both_conditions_reachable",
                )
            )
            for row in fairness
        )
    ):
        raise ValueError("The four business-tool/budget/single-pass fairness controls must pass")
    return {
        "qualification": plan["qualification"],
        "version": QUALIFICATION_VERSION,
        "source_tree_sha256": current["source_tree_sha256"],
        "code_identity": hashes,
        "catalog_sha256": report["catalog_sha256"],
        "source_manifest_sha256": report["source_manifest_sha256"],
        "limits": report["limits"],
        "positive_routes": len(positives),
        "negative_controls": len(negatives),
        "counterfactual_pairs": len(pairs),
        "fairness_cases": len(fairness),
        "passed": True,
        "scope": "Archived CPU/tokenizer qualification matched before model loading; no production-model support or learning claim.",
    }


def validate_plan(plan, *, verify_source=True):
    if plan.get("version") != VERSION or any(
        plan.get(key) != value for key, value in FIXED_LIMITS.items()
    ):
        raise ValueError(
            "Only the frozen sixteen-slot zero-update C1 and its finite caps are allowed"
        )
    if not isinstance(plan.get("qualification"), dict):
        raise ValueError(
            "A passed frozen CPU qualification reference is required before GPU execution"
        )
    from proworksim.templates.reciprocal_data_v026 import registry

    catalog = read_json(checked(plan["catalog"]))
    if catalog != registry():
        raise ValueError("The frozen carrier catalog differs from current implementation")
    assigned = assignments(catalog)
    validate_cpu_qualification(plan, catalog)
    checked(plan["source_pin"])
    prior = read_json(checked(plan["prior_model_plan"]))
    recipe = read_json(checked(plan["owner_recipe"]))["recipe"]
    if (
        prior["runtime_profile"]["version"] != "candidate-runtime-v0.20.1"
        or prior["runtime_profile"]["candidate_id"] != "qwen3.5-9b"
        or prior["runtime_profile"]["devices"] != 1
        or recipe["credit_assignment"] != "terminal_mc"
        or recipe["members"] != ["provider", "implementer", "reviewer"]
    ):
        raise ValueError(
            "Use the existing single-card 9B numerical profile and exact original recipe"
        )
    marker = read_json(checked(plan["checkpoint_marker"]))
    saved = read_json(checked(marker["checkpoint"]))
    state_path = Path(saved["state"]["path"])
    if (
        marker["source"] != plan["old_worker_source"]
        or marker["source"]["code_dirty"] is not False
        or marker["label"] != "base"
        or marker["credit_assignment"] != "terminal_mc"
        or marker["actor_identity"] != saved["actor_identity"]
        or saved["actor_steps"] != 3
        or saved["critic_steps"] != 3
        or saved["serialized_reload_exact"] is not True
        or Path(marker["directory"]).resolve() != checked(marker["checkpoint"]).parent
        or state_path.resolve() != Path(marker["directory"]).resolve() / "shared-state.pt"
        or digest(state_path.read_bytes()) != saved["state"]["sha256"]
        or state_path.stat().st_size != saved["state"]["bytes"]
    ):
        raise ValueError("The immutable original 3/3 complete endpoint or its source changed")
    if verify_source:
        verify_invariant_source(plan)
    validate_previous_loading_attempt(plan)
    validate_previous_waiting_queue(plan)
    return catalog, assigned


def restore_original_endpoint(owner, plan, output):
    """Explicit cross-source authorization, followed by unchanged strict tensor restore."""
    from proworksim.online_training import tensor_tree_digest

    source = code_identity()
    if source["code_dirty"]:
        raise ValueError("Cross-source restore requires a committed new protocol")
    modules = verify_invariant_source(plan)
    marker_path = checked(plan["checkpoint_marker"])
    original_bytes = marker_path.read_bytes()
    marker = read_json(marker_path)
    if marker["source"] != plan["old_worker_source"]:
        raise ValueError("Original endpoint source differs from migration declaration")
    saved = read_json(checked(marker["checkpoint"]))
    restored = owner.restore_checkpoint(marker["directory"])
    actual_digest = tensor_tree_digest(owner._state_bundle(), owner.torch)
    if (
        restored != saved
        or actual_digest != saved["state_tensor_digest"]
        or owner.freeze_identity() != marker["actor_identity"]
        or owner.actor_steps != 3
        or owner.critic_steps != 3
        or marker_path.read_bytes() != original_bytes
    ):
        raise ValueError(
            "Exact actor/critic/optimizer/RNG restoration or original marker preservation failed"
        )
    proof = {
        "version": VERSION,
        "old_worker_source": marker["source"],
        "new_worker_source": source,
        "checkpoint_marker": plan["checkpoint_marker"],
        "checkpoint": marker["checkpoint"],
        "state": saved["state"],
        "invariant_modules": modules,
        "old_marker_bytes_unchanged": True,
        "strict_restore_executed": True,
        "state_tensor_digest": saved["state_tensor_digest"],
        "restored_state_tensor_digest": actual_digest,
        "actor_identity": owner.freeze_identity(),
        "actor_steps": owner.actor_steps,
        "critic_steps": owner.critic_steps,
        "new_parameter_updates": 0,
        "scope": "Exact old complete learning state under a newly frozen carrier/harness protocol. The old marker/source are never relabeled; this is not a replay of old world evaluation.",
    }
    write(Path(output) / "cross-source-restore-proof.json", proof)
    return proof


def task(output, name, kind):
    write(
        Path(output) / "task.json",
        {"task": name, "kind": kind, "started_at": time.time(), "pid": os.getpid()},
    )


def event_counts(events):
    return {
        "events": len(events),
        "kinds": dict(Counter(event["kind"] for event in events)),
        "model_requests": sum(
            event["kind"] == "model_call" and event["payload"].get("stage") == "started"
            for event in events
        ),
        "model_responses": sum(event["kind"] == "model_response" for event in events),
        "world_actions": sum(event["kind"] == "tool_call" for event in events),
    }


def collect(owner, plan, slots, output):
    from proworksim.reciprocal_runtime_v026 import runtime as make_runtime
    from proworksim.templates.reciprocal_data_v026 import assess_episode, build_case

    rows, identity = [], owner.freeze_identity()
    for slot in slots:
        task(output, slot["slot_id"], "episode")
        folder = Path(output) / slot["slot_id"]
        prepared = build_case(slot["case_id"], folder, assets_root=plan["assets_root"])
        if prepared.deployment.status != "ready" or prepared.case["role_decision_limits"] != {
            "maintainer": 24,
            "consumer": 24,
        }:
            raise ValueError("Carrier must be ready with identical 24-decision role budgets")
        snapshot = owner.capture_evaluation_state()
        current = owner.begin_window("v026-" + slot["slot_id"])
        if current != identity:
            raise ValueError("Frozen actor changed across carrier episodes")
        owner.reseed(slot["sampling_seed"], label=slot["slot_id"])
        runtime, captured, _ = make_runtime(
            owner, prepared, folder, slot["condition"], episode_key=str(slot["sampling_seed"])
        )
        scenario = copy.deepcopy(prepared.scenario)
        scenario.setdefault("variation", {})["carrier_development"] = {
            "version": VERSION,
            "slot": slot,
            "training_projection": False,
            "parameter_updates": 0,
            "host_only_metadata": True,
        }
        work_nodes = getattr(prepared, "work_nodes", None) or prepared.case.get("work_nodes")
        if work_nodes is None:
            work_nodes = sorted(
                {work["node_id"] for work in prepared.world.state["work_items"].values()}
            )
        episode = folder / "episode"
        row = {
            **copy.deepcopy(slot),
            "status": "started",
            "started_at": time.time(),
            "actor_identity": identity,
        }
        rows.append(row)
        write(Path(output) / "progress.json", rows)
        try:
            begin_episode(
                prepared.world,
                episode,
                experience=runtime.recorder.snapshot(),
                work_nodes=work_nodes,
                work_ids=[],
                scenario=scenario,
                policies=runtime.policy_identities,
            )
            boundary = run_fragment(prepared, runtime, external_tick_per_sweep=1)
            finish_episode(
                prepared.world,
                episode,
                experience=runtime.recorder.snapshot(),
                termination=boundary,
            )
            assessment = assess_episode(episode)
            write(folder / "assessment.json", assessment)
            row.update(
                status="closed",
                boundary=boundary,
                assessment=assessment,
                assessment_ref=reference(folder / "assessment.json"),
                ended_at=time.time(),
            )
            owner.finish_evaluation(
                [
                    {
                        "slot_id": slot["slot_id"],
                        "active_members": prepared.active_roles,
                        "reward": assessment,
                    }
                ],
                folder / "frozen-evaluation",
            )
            guard = owner.finish_evaluation_guard(snapshot)
            write(folder / "evaluation-guard.json", guard)
            row["evaluation_guard"] = guard
            if not guard["learning_unchanged"] or not guard["rng_restored_exactly"]:
                raise ValueError("Frozen learning or RNG state guard failed")
            if assessment.get("eligible") is not True:
                row["status"] = "unassessable"
            errors = {
                "model_service_error",
                "environment_error",
                "binding_mismatch",
                "policy_error",
            }
            if (
                errors & set(boundary.get("role_stops", {}).values())
                or boundary.get("status") == "environment_error"
            ):
                row["status"] = "execution_unknown"
        except BaseException as error:
            row.update(
                status="interrupted_or_unassessed",
                ended_at=time.time(),
                error={"type": type(error).__name__, "message": str(error)},
            )
            raise
        finally:
            write(folder / "public-capture.json", captured)
            write(folder / "runtime.json", runtime.snapshot())
            experience = runtime.recorder.snapshot()
            write(
                folder / "joint-experience.json",
                {
                    "version": VERSION,
                    "slot": slot,
                    "actor_identity": identity,
                    "training_projection": False,
                    "experience": experience,
                    "scope": "Original chronological two-member runtime events, including actual role inputs/responses and refused actions; not method-support admission.",
                },
            )
            row["event_counts"] = event_counts(experience["events"])
            write(Path(output) / "progress.json", rows)
        print(
            {
                "slot": slot["slot_id"],
                "status": row["status"],
                "completed": assessment.get("completed"),
            },
            flush=True,
        )
        if row["status"] != "closed":
            return {"status": "stopped_unknown", "rows": rows, "not_started": slots[len(rows) :]}
    return {"status": "complete", "rows": rows, "not_started": []}


def run(plan_path, output, worker):
    plan = read_json(plan_path)
    _, assigned = validate_plan(plan)
    source = code_identity()
    if source["code_dirty"] or os.environ.get("CUDA_VISIBLE_DEVICES") not in set(
        map(str, plan["gpu_preference"])
    ):
        raise ValueError(
            "C1 must run committed source on exactly one declared physical GPU per worker"
        )
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "version": VERSION,
        "worker": worker,
        "status": "loading",
        "source_before": source,
        "plan": reference(plan_path),
        "qualification": plan["qualification"],
        "cpu_qualification_passed_before_model_loading": True,
        "slots": assigned[worker],
        "started_at": time.time(),
        "model_api_calls": 0,
        "new_actor_steps": 0,
        "new_critic_steps": 0,
        "learning_probability_recomputation": False,
        "automatic_successors": [],
    }
    write(output / "report.json", report)
    owner = None
    try:
        from proworksim.deterministic_work_v024 import DeterministicCandidateActor

        prior = read_json(checked(plan["prior_model_plan"]))
        recipe = read_json(checked(plan["owner_recipe"]))["recipe"]
        task(output, "load-existing-9b", "loading")
        from scripts.run_ne_v021 import resources

        loading_resources = resources()
        write(output / "preload-resources.json", loading_resources)
        if int(os.environ["CUDA_VISIBLE_DEVICES"]) not in released_gpus(plan, loading_resources):
            raise RuntimeError("Selected GPU lost its released capacity before model loading")
        owner = DeterministicCandidateActor.from_candidate(
            prior["model"],
            manifest=checked(prior["manifest"]),
            profile=prior["runtime_profile"],
            recipe=recipe,
            output=output / "resident",
        )
        task(output, "restore-exact-old-state-under-new-protocol", "boundary")
        report["restoration"] = restore_original_endpoint(owner, plan, output)
        report.update(status="running")
        write(output / "report.json", report)
        report.update(collect(owner, plan, assigned[worker], output))
    except BaseException as error:
        report.update(
            status="interrupted_or_error",
            error={"type": type(error).__name__, "message": str(error)},
        )
        raise
    finally:
        if owner is not None:
            report.update(
                final_actor_identity=owner._make_identity(),
                actor_steps=owner.actor_steps,
                critic_steps=owner.critic_steps,
            )
        report.update(ended_at=time.time(), source_after=code_identity())
        report["source_unchanged"] = source == report["source_after"]
        progress = output / "progress.json"
        if progress.exists():
            report["rows"] = read_json(progress)
            report["not_started"] = assigned[worker][len(report["rows"]) :]
        write(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", choices=list(RESOURCE_CAPS), required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    result = run(args.plan.resolve(), args.output.resolve(), args.worker)
    raise SystemExit(0 if result["status"] == "complete" else 2)
