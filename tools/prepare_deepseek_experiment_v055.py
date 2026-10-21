"""Prepare/freeze the independent 500-task, six-condition, CNY 2000 API study.

This builder never invokes a model, grader, queue, GPU, shell test or downloader.
Preparation writes the immutable panel and conditions. Final freezing requires
all six original neutral API qualifications, offline-network admission and the
official local-counter artifacts to have passed their separate controls.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new  # noqa: E402
from proworksim.software_benchmark_deepseek_api_v055 import POLICY, VERSION as API_VERSION  # noqa: E402
from proworksim.software_benchmark_queue_v055 import VERSION as QUEUE_VERSION, validate_plan  # noqa: E402

RUN = ROOT / "runs/software-benchmark-v055"
ARTIFACTS = ROOT / "artifacts/software-benchmark-v055/manifests"
ORIGINAL_SLOTS = ROOT / "artifacts/software-benchmark-v054/manifests/slots.json"
ORIGINAL_SOURCE = ROOT / "artifacts/software-benchmark-v054/runner/source-manifest.json"
ASSET_SEED = RUN / "template-existing-assets-r1.json"
NETWORK_ADMISSION = RUN / "network-resource-admission-r2.json"
SCORER_ROOT = RUN / "scorer-preflight-r1"
TOKENIZER_MANIFEST = RUN / "tokenizer-r1/manifest.json"
NEUTRAL_PLAN = RUN / "neutral-qualification-plan-r1.json"
LEDGER = RUN / "budget-r1/ledger.sqlite3"
CONDITIONS = tuple(arm + "-" + mode for arm in ("REF", "MATCH", "PROJECT")
                   for mode in ("nonthinking", "thinking"))
VERSION = "v055-deepseek-experiment-builder-r1"


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_bytes())


def load_ref(value):
    return load(checked(value))


def plain_ref(value):
    """Source URLs/provenance metadata are not part of the byte-reference schema."""
    return {key: value[key] for key in ("path", "sha256", "bytes")}


def emit(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return write_new(path, value)


def create_slots():
    original = load(ORIGINAL_SLOTS)
    tasks = {}
    for row in original["slots"]:
        item = tasks.setdefault(row["instance_id"], {"seed": row["seed"],
            "task_order_index": row["task_order_index"], "arms": set()})
        if item["seed"] != row["seed"] or item["task_order_index"] != row["task_order_index"]:
            raise ValueError("Original task ordering/seed is inconsistent between arms")
        item["arms"].add(row["arm"])
    if len(tasks) != 500 or any(row["arms"] != {"REF", "MATCH", "PROJECT"} for row in tasks.values()):
        raise ValueError("Original complete 500-task, three-arm identity is required")
    ordered = sorted(tasks, key=lambda name: tasks[name]["task_order_index"])
    slots = []
    for index, instance_id in enumerate(ordered):
        offset = index % len(CONDITIONS)
        for position, condition in enumerate(CONDITIONS[offset:] + CONDITIONS[:offset]):
            arm, mode = condition.split("-", 1)
            slots.append({"slot_id": "v055-" + condition + "-" + instance_id,
                "slot_index": len(slots) + 1, "instance_id": instance_id,
                "task_order_index": index + 1, "condition_order_within_task": position + 1,
                "condition_id": condition, "arm": arm, "thinking": mode == "thinking",
                "seed": tasks[instance_id]["seed"],
                "seed_role": "historical_task_identity_only_not_transmitted_to_API",
                "provider_seed_supported": False, "authorization_required": True,
                "automatic_generation_replay": False})
    counts = {condition: [sum(row["condition_id"] == condition
              and row["condition_order_within_task"] == position for row in slots)
              for position in range(1, 7)] for condition in CONDITIONS}
    if any(max(values) - min(values) > 1 for values in counts.values()):
        raise ValueError("Six-condition order failed its predetermined balance requirement")
    return {"version": "v055-six-condition-slots-r1", "source": original["source"],
        "original_slots": reference(ORIGINAL_SLOTS), "distinct_task_count": 500,
        "planned_slot_count": 3000, "conditions": list(CONDITIONS),
        "task_order": "unchanged_original_v054_task_order_index",
        "within_task_order": "left_rotate_declared_six_conditions_by_zero_based_task_index_modulo_6",
        "condition_position_counts": counts, "provider_seed_parameter_used": False,
        "original_seed_formula": original["seed_formula"],
        "new_model_training": False, "automatic_start": False,
        "budget_limited_completion_not_guaranteed": True, "slots": slots}


def condition_spec(condition_id):
    arm, mode = condition_id.split("-", 1)
    thinking = mode == "thinking"
    context, output = (131072, 32768) if arm == "REF" else (18432, 2048)
    fields = {"model": "deepseek-flash", "thinking": {"type": "enabled" if thinking else "disabled"},
              "max_tokens": output, "stream": False}
    if thinking:
        fields["reasoning_effort"] = "high"
    else:
        fields["temperature"] = 0.6 if arm == "REF" else 0.7
    return {"version": "v055-deepseek-condition-r1", "condition_id": condition_id,
        "arm": arm, "thinking": thinking, "model": "deepseek-flash",
        "documented_model_version": "DeepSeek-V4.1-Flash-1017",
        "provider_alias_is_not_immutable_weight_pin": True,
        "single_actual_agent": True, "project_training_adapter": None, "training": False,
        "source_condition_v054": reference(ROOT / ("config/v054-condition-" + arm + ".json")),
        "interface": "actual_managed_S1" if arm == "PROJECT" else "native_OpenHands_1.49.6",
        "inference": {"context_limit": context, "maximum_output_tokens": output,
            "maximum_input_reservation_tokens": context - output,
            "output_includes_reasoning_tokens": True, "fixed_api_fields": fields,
            "top_p": "omitted", "top_k": "omitted_unsupported", "seed": "omitted_unsupported",
            "temperature": "omitted_in_thinking" if thinking else fields["temperature"],
            "thinking_history": "preserve_original_provider_reasoning_content_for_tool_continuations"},
        "episode_limits": {"input_plus_output_tokens": 500000, "all_model_attempts": 128,
            "agent_decisions": 128, "soft_seconds": 5400, "hard_seconds": 6000,
            "input_usage": "official_provider_usage_authoritative",
            "uncertain_usage": "retain_monetary_reservation_and_do_not_replay"},
        "actor_resources": {"aggregate_cpu": 4, "memory_bytes": 16 * 1024**3,
            "pids": 16384, "network": "private_namespace_loopback_only"},
        "network": {"model": "direct_verified_TLS_api.deepseek.com:443", "proxy": False,
            "reverse_proxy": False, "web_search_tool": False, "actor_external_network": False},
        "candidate": {"code": "unique_final_complete_worktree_locked_after_writer_quiescence",
            "delivery": "last_legal_project_submission" if arm == "PROJECT" else None,
            "score_feedback_to_model": False, "reselection_after_score": False},
        "execution_requires_separate_frozen_authorization": True}


def prepare():
    slots = emit(ARTIFACTS / "slots.json", create_slots())
    conditions = {name: emit(ROOT / ("config/v055-condition-" + name + ".json"), condition_spec(name))
                  for name in CONDITIONS}
    draft = {"version": VERSION, "created_utc": now(), "phase": "prepared_not_qualified",
        "slots": slots, "conditions": conditions, "asset_seed": reference(ASSET_SEED),
        "original_source_manifest": reference(ORIGINAL_SOURCE),
        "formal_execution_enabled": False, "planned_episode_count": 3000,
        "global_budget_cny": 2000, "neutral_preparation_maximum_requests": 12,
        "preparation_costs_count_toward_same_budget": True, "ledger_path": str(LEDGER),
        "model_calls_by_builder": 0, "grading_calls_by_builder": 0,
        "generation_concurrency": 24, "scoring_concurrency": 4, "maximum_api_concurrency": 64,
        "requires": ["six_original_neutral_conditions_passed", "independent_network_r2_admitted",
                     "official_tokenizer_counter_bound", "official_scorer_paths_admitted"]}
    ref = emit(ARTIFACTS / "draft.json", draft)
    return {"phase": draft["phase"], "draft": ref, "slots": slots, "model_calls": 0}


def neutral_admission(plan_path, counter_ref):
    plan_ref, plan = reference(plan_path), load(plan_path)
    counter = plan["context_counter"]
    if (plan.get("version") != "v055-deepseek-neutral-qualification-plan-r1"
            or plan.get("maximum_requests_all_conditions") != 12
            or plan.get("maximum_requests_per_condition") != 2
            or plan.get("no_retries_or_replacements") is not True
            or plan.get("formal_tasks") != 0 or plan.get("ledger_path") != str(LEDGER)
            or plan.get("max_api_concurrency") != 64
            or counter.get("module") != "proworksim.software_benchmark_deepseek_tokenizer_v055"
            or counter.get("manifest_path") != counter_ref["path"]
            or counter.get("manifest_sha256") != counter_ref["sha256"]
            or counter.get("reservation_margin_tokens") != 128):
        raise ValueError("Neutral API plan/counter/shared ledger differs from the original preparation")
    receipts, request_ids = {}, []
    if len(plan["conditions"]) != 6:
        raise ValueError("Exactly six neutral conditions must have been predeclared")
    for row in plan["conditions"]:
        canonical = row["arm"] + ("-thinking" if row["thinking"] else "-nonthinking")
        if canonical not in CONDITIONS or canonical in receipts or type(row["thinking"]) is not bool:
            raise ValueError("Neutral qualification lacks a unique arm/thinking identity")
        folder = Path(plan["output_root"]) / row["condition_id"]
        receipt = load(folder / "receipt.json")
        intent = load(folder / "intent.json")
        ledger = receipt.get("ledger", {})
        if (receipt.get("passed") is not True or receipt.get("condition") != row
                or receipt.get("formal_task") is not False or receipt.get("actual_requests") != 2
                or receipt.get("official_grader_calls") != 0 or receipt.get("GPU_loads") != 0
                or receipt.get("automatic_retry") is not False
                or receipt.get("selected_after_outcome") is not False
                or receipt.get("reasoning_content_original_continuation") is not True
                or ledger.get("attempts") != 2 or ledger.get("inflight") is not None
                or len(ledger.get("calls", [])) != 2 or len(receipt.get("comparisons", [])) != 2
                or intent.get("plan") != plan_ref or intent.get("condition") != row
                or intent.get("new_formal_slots_claimed") != 0):
            raise ValueError("Original neutral qualification has not passed: " + canonical)
        for call, comparison in zip(ledger["calls"], receipt["comparisons"]):
            request = load_ref(call["request"])
            measurement = request["measurement"]
            if (measurement.get("tokenizer_manifest_sha256") != counter_ref["sha256"]
                    or measurement.get("reservation_margin_tokens") != 128
                    or comparison["request"] != call["request"]
                    or comparison["response"] != call["response"]
                    or comparison["actual_provider_prompt_tokens"] > comparison["prompt_reservation"]):
                raise ValueError("Neutral counter/usage evidence differs from the frozen reservation")
            checked(call["response"])
            request_ids.append(call["request_id"])
        receipts[canonical] = reference(folder / "receipt.json")
    if set(receipts) != set(CONDITIONS) or len(set(request_ids)) != 12:
        raise ValueError("Incomplete or duplicated neutral qualification requests")
    return {"plan": plan_ref, "conditions": receipts, "request_ids": request_ids,
            "context_counter": counter, "actual_neutral_requests": 12}


def budget_admission(request_ids):
    if not LEDGER.is_file():
        raise ValueError("The paid neutral requests must already have settled in the shared ledger")
    # Read-only access cannot initialize a new ledger, change its cap or erase a failure.
    with sqlite3.connect(LEDGER.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        metadata = dict(db.execute("SELECT name,value FROM metadata"))
        if json.loads(metadata["policy"]) != {**POLICY, "max_concurrency": 64}:
            raise ValueError("Global ledger does not use the current frozen CNY 2000 policy")
        if metadata.get("halted"):
            raise ValueError("Global API/accounting gate is halted; formal dispatch cannot be frozen")
        rows = [dict(row) for row in db.execute("SELECT * FROM requests")]
    by_id = {row["request_id"]: row for row in rows}
    if any(name not in by_id or by_id[name]["status"] != "settled" for name in request_ids):
        raise ValueError("Not all twelve qualification requests have authoritative settlement")
    if any(row["status"] == "reserved" for row in rows):
        raise ValueError("Wait for preparation calls to settle before final source freeze")
    committed = sum(row["settled_nanoyuan"] if row["status"] == "settled" else row["reserved_nanoyuan"]
                    for row in rows)
    if committed > POLICY["cap_nanoyuan"]:
        raise ValueError("Shared ledger already exceeds the authorized ceiling")
    return {"ledger_path": str(LEDGER), "policy_version": API_VERSION,
        "cap_nanoyuan": POLICY["cap_nanoyuan"], "preparation_requests_in_same_ledger": len(rows),
        "verified_neutral_requests": len(request_ids), "committed_upper_nanoyuan": committed,
        "remaining_upper_budget_nanoyuan": POLICY["cap_nanoyuan"] - committed,
        "ledger_read_only": True, "model_calls_by_builder": 0}


def freeze_sources(counter_ref, additional_refs):
    original = load(ORIGINAL_SOURCE)
    files = {item["path"]: plain_ref(item) for item in original["files"]}
    for item in files.values():
        checked(item)
    extras = [reference(ORIGINAL_SOURCE), counter_ref, *additional_refs,
              reference(RUN / "network/ca-bundle.pem")]
    for directory in (ROOT / "src/proworksim", ROOT / "tools"):
        extras.extend(reference(path) for path in sorted(directory.glob("*v055*"))
                      if path.is_file() and path.suffix in {".py", ".sh"})
    tokenizer = load_ref(counter_ref)
    extras.extend(plain_ref(item) for item in tokenizer["installed_files"] + tokenizer["tokenizer_files"])
    for item in extras:
        checked(item)
        prior = files.get(item["path"])
        if prior is not None and prior != item:
            raise ValueError("New experiment cannot replace an original frozen dependency")
        files[item["path"]] = item
    manifest = {"version": "v055-independent-source-manifest-r1", "created_utc": now(),
        "original_source_manifest": reference(ORIGINAL_SOURCE),
        "original_frozen_dependency_count": len(original["files"]),
        "scope": "original_v054_dependency_bytes_plus_new_v055_sources_counter_and_CA",
        "original_dependency_bytes_modified": False, "large_model_or_image_payloads_rehashed": False,
        "files": [files[name] for name in sorted(files)], "model_calls": 0}
    return emit(ARTIFACTS / "source-manifest.json", manifest), manifest["files"]


def freeze(neutral_plan_path, network_path, counter_path, lifecycle_path):
    draft = load(ARTIFACTS / "draft.json")
    slots, assets = load_ref(draft["slots"]), load_ref(draft["asset_seed"])
    if slots["planned_slot_count"] != 3000:
        raise ValueError("Prepared six-condition panel changed")
    for name, item in draft["conditions"].items():
        if load_ref(item) != condition_spec(name):
            raise ValueError("Prepared condition changed before admission")
    counter_ref = reference(counter_path)
    counter = load_ref(counter_ref)
    if (counter.get("version") != "software-benchmark-v055-official-tokenizer-preparation-r1"
            or counter.get("recipe_version") != "0.2.0"
            or counter.get("tokenizer_model") != "deepseek-ai/DeepSeek-V4.1-Flash-1017"):
        raise ValueError("The official local recipe/tokenizer identity is required")
    network_ref, network = reference(network_path), load(network_path)
    if (network.get("version") != "v055-network-resource-admission-r2" or network.get("admitted") is not True
            or network.get("actor_offline_control_passed") is not True
            or network.get("private_sdk_models_GET_with_verified_CA_passed") is not True
            or network.get("scorer_paths_passed") is not True):
        raise ValueError("Independent actor/API/scorer network admission is incomplete")
    for item in network["evidence"].values():
        checked(item)
    scorer_manifest = reference(SCORER_ROOT / "installation-manifest.json")
    scorer = load_ref(scorer_manifest)
    if (scorer.get("version") != "software-benchmark-scorer-v055-r1"
            or scorer.get("official_version") != "5.0.2"
            or scorer.get("mapped_adapter") != reference(ROOT / "src/proworksim/software_benchmark_scorer_v055.py")
            or load(SCORER_ROOT / "receipt.json").get("passed") is not True):
        raise ValueError("Scorer installation/source or actual-runtime path admission changed")
    neutral = neutral_admission(neutral_plan_path, counter_ref)
    budget = budget_admission(neutral["request_ids"])
    lifecycle_ref, lifecycle = reference(lifecycle_path), load(lifecycle_path)
    if (lifecycle.get("version") != "v055-programmed-full-host-lifecycle-r1"
            or lifecycle.get("passed") is not True or lifecycle.get("real_model_calls") != 0
            or lifecycle.get("official_grader_calls") != 0 or lifecycle.get("formal_3000_slot_claims") != 0
            or {item["arm"] for item in lifecycle.get("cases", [])} != {"MATCH", "PROJECT"}
            or any(item.get("passed") is not True for item in lifecycle["cases"])):
        raise ValueError("Both programmed full host lifecycle paths must have passed")
    capacity_ref = reference(RUN / "dynamic-concurrency-control-r2.json")
    capacity = load_ref(capacity_ref)
    if (capacity.get("passed") is not True or capacity.get("model_calls") != 0
            or capacity.get("source") != reference(ROOT / "src/proworksim/software_benchmark_network_v055.py")):
        raise ValueError("Dynamic CPU/RAM/API concurrency boundaries lack their current CPU control")
    environment_control_ref = reference(RUN / "environment-queue-control-r2.json")
    environment_control = load_ref(environment_control_ref)
    if (environment_control.get("passed") is not True or environment_control.get("model_calls") != 0
            or environment_control.get("source") != reference(ROOT / "src/proworksim/software_benchmark_queue_v055.py")):
        raise ValueError("Current cache readiness/deferred queue paths require their one CPU control")
    # Validate the existing panel projections once, without image/test execution.
    public_tasks = load_ref(assets["public_tasks"])
    registry = load_ref(assets["public_test_registry"])
    image_ref = reference(assets["image_inventory_path"])
    images = load_ref(image_ref)["images"]
    expected = {row["instance_id"] for row in slots["slots"]}
    if (len(public_tasks) != 500 or {row["instance_id"] for row in public_tasks} != expected
            or len(registry["entries"]) != 500 or {row["instance_id"] for row in registry["entries"]} != expected
            or any(row.get("admitted") is not True for row in registry["entries"])
            or len(images) != 500 or {row["instance_id"] for row in images} != expected
            or any(row.get("status") != "loaded" for row in images)):
        raise ValueError("Data/image/public interface coverage does not preserve all 500 planned tasks")
    from collections import Counter
    from proworksim.software_benchmark_prewarm_v054 import preparation_state
    cache_states = [preparation_state(row["instance_id"], mapping_reference=row["baseline_mapping"],
        cache_root=Path(assets["lazy_native_preparation"]["cache_root"])) for row in registry["entries"]]
    environment_coverage = emit(ARTIFACTS / "initial-environment-coverage.json", {
        "planned_tasks": 500, "observed_utc": now(), "counts": dict(Counter(row["status"] for row in cache_states)),
        "tasks": cache_states, "model_calls": 0, "slots_claimed": 0,
        "pending_is_not_a_model_failure": True, "preparation_workers_maximum": 2,
        "failed_templates_deferred_without_automatic_repair": True})
    admission = emit(ARTIFACTS / "admission.json", {"version": "v055-six-condition-admission-r1",
        "passed": True, "network": network_ref, "neutral": neutral, "budget": budget,
        "scorer_manifest": scorer_manifest, "counter_manifest": counter_ref,
        "programmed_full_host_lifecycle": lifecycle_ref, "dynamic_concurrency": capacity_ref,
        "environment_queue_control": environment_control_ref, "initial_environment_coverage": environment_coverage,
        "model_calls_by_builder": 0, "grading_calls_by_builder": 0,
        "all_solver_admissions_passed": True})
    source_ref, sources = freeze_sources(counter_ref, [admission, scorer_manifest, network_ref,
        draft["slots"], *draft["conditions"].values(), assets["public_tasks"],
        assets["public_test_registry"], image_ref, assets["scorer_request_base"]["dataset"],
        neutral["plan"], *neutral["conditions"].values(), lifecycle_ref, capacity_ref,
        environment_control_ref, environment_coverage])
    authorization = emit(ROOT / "config/v055-formal-authorization-r1.json", {
        "version": "v055-user-authorized-API-experiment-r1", "created_utc": now(),
        "execution_authorized": True, "slots_sha256": draft["slots"]["sha256"],
        "slot_ids": [row["slot_id"] for row in slots["slots"]], "maximum_formal_episodes": 3000,
        "authorization_source": "user_requested_six_DeepSeek_controls_under_total_CNY_2000",
        "budget_cny": 2000, "ledger_path": str(LEDGER), "budget_policy_version": API_VERSION,
        "neutral_preparation_request_limit": 12, "preparation_cost_included": True,
        "no_new_model_budget_beyond_total_cap": True, "complete_3000_not_guaranteed": True,
        "single_agent": True, "training": False, "GPU_use": False,
        "automatic_generation_retry": False, "repeat_entered_task": False,
        "task_selection_by_model_result": False, "admission": admission, "source_manifest": source_ref})
    template = {key: assets[key] for key in ("public_tasks", "public_test_registry", "stdlib",
                "sdk_runtime", "lazy_native_preparation", "dataset_revision")}
    template.update(model="deepseek-flash", image_inventory=image_ref, authorization=authorization,
        ledger_path=str(LEDGER), api_key_file=str(ROOT / ".env"), max_api_concurrency=64,
        context_counter=neutral["context_counter"], all_solver_admissions_passed=True,
        admission=admission, source_manifest=source_ref,
        scorer_request_base={**assets["scorer_request_base"], "scorer_manifest": scorer_manifest})
    template_ref = emit(ARTIFACTS / "template.json", template)
    plan = {"version": QUEUE_VERSION, "created_utc": now(), "execution_authorized": True,
        "conditions": draft["conditions"], "slots": draft["slots"],
        "frozen_sources": [*sources, source_ref], "template": template_ref,
        "queue_root": str(RUN / "queue-r1"), "ledger_path": str(LEDGER),
        "budget_cny": 2000, "maximum_api_concurrency": 64,
        "generation_concurrency": 32, "scoring_concurrency": 4,
        "preparation_concurrency": 2,
        "native_cache_policy": {"qualified_before_formal_claim": True,
            "unprepared_tasks_remain_pending": True, "deferred_failed_templates_not_retried": True,
            "minimum_disk_free_bytes_for_preparation": 128 * 1024**3,
            "initial_coverage": environment_coverage, "shared_exact_key_flock": True,
            "already_qualified_templates_modified": False},
        "dynamic_resource_admission": {
            "generation_maximum": 32, "per_worker_cpu": 4, "per_worker_memory_bytes": 16 * 1024**3,
            "reserved_host_and_GPU_owner_cpu": 24, "reserved_scoring_CPU": 16,
            "legacy_v054_active_generation_and_scoring_counted": True,
            "minimum_available_memory_reserve_bytes": 128 * 1024**3,
            "minimum_disk_free_for_new_generation_bytes": 100 * 1024**3,
            "maximum_host_load_1m": 140, "API_request_cap": 64,
            "capacity_drop_terminates_existing_workers": False},
        "authorization": authorization, "admission": admission,
        "planned_denominator_per_condition": 500, "planned_formal_episodes": 3000,
        "budget_truncation_is_administrative_censoring": True,
        "fixed_per_task_six_condition_round_robin": True, "automatic_start": False}
    validate_plan(plan)
    plan_ref = emit(ARTIFACTS / "queue-plan.json", plan)
    return {"phase": "frozen_qualified_not_started", "plan": plan_ref,
        "authorization": authorization, "admission": admission, "model_calls_by_builder": 0,
        "launch_argv": [str(ROOT / ".venv/bin/python"), "-m", "proworksim.software_benchmark_queue_v055",
                        "run", "--plan", plan_ref["path"], "--sha256", plan_ref["sha256"]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--freeze", action="store_true")
    parser.add_argument("--neutral-plan", type=Path, default=NEUTRAL_PLAN)
    parser.add_argument("--network-admission", type=Path, default=NETWORK_ADMISSION)
    parser.add_argument("--counter-manifest", type=Path, default=TOKENIZER_MANIFEST)
    parser.add_argument("--host-lifecycle", type=Path, default=RUN / "host-lifecycle-r2/receipt.json")
    args = parser.parse_args()
    result = prepare() if args.prepare else freeze(
        args.neutral_plan, args.network_admission, args.counter_manifest, args.host_lifecycle)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
