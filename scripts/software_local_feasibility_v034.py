"""One frozen eight-slot T-only local-feasibility batch; no automatic training."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.storage import digest, read_json
from scripts import continue_model_selection_v031 as continuation
from scripts import software_model_selection_v030 as original
from scripts import software_model_selection_v031 as dense
from scripts import software_paired_o1_v033 as prior
from scripts.gpu_occupancy_accounting import GpuInterval, interval_accounting
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, resources, write
from scripts.software_development_v028 import available_cards, task

VERSION = "software-local-feasibility-v0.34"
SOURCE = Path(__file__).resolve().parents[1]
CANDIDATES = prior.CANDIDATES
GPU_ORDER = list(prior.GPU_ORDER)
LIMITS = copy.deepcopy(prior.LIMITS)
TERMINAL = prior.TERMINAL
REPORT_PATHS = ["docs/experiments/software-local-feasibility-v034.md",
                "docs/experiments/software-local-feasibility-v034.json"]
TEAM_LIMITS = {"max_decisions": 128, "max_attempts": 128,
               "max_total_tokens": 500000, "max_test_runs": 32}
GENERATION_LIMITS = {"context_tokens": 16384, "max_output_tokens": 2048,
                     "native_profile_precision_and_sampling": "unchanged original candidate profile"}
NEXT_STAGE_RULE = {
    "purpose": "Choose one local carrier for separately frozen P2 training-source support planning",
    "require_all_four_valid_known": True, "require_full_common_restore": True,
    "minimum_complete_successes": 1,
    "rank_order": ["complete_success_count_desc", "distinct_roots_with_success_desc",
                   "total_actual_tokens_all_four_slots_asc", "fixed_candidate_order"],
    "one_success_means": "Finite local feasibility only; neither stable ability nor allocation support",
    "development_records_may_become_training": False,
    "old_selection_reclassified": False, "automatic_model_search": False,
    "all_business_failed": "Close this frozen batch; do not retune prompts and rerun these slots",
    "technical_unknown": "Keep unknown; never fill it with zero or treat it as all-business-failed",
}
PHASES = {
    "P0": {"status": "executable_cpu_only", "purpose": "New-root dependency witnesses and one presentation audit"},
    "P1": {"status": "executable_after_cpu_qualification", "purpose": "One eight-slot T-only development batch",
           "episodes": 8, "optimizer_updates": 0},
    "P2": {"status": "awaiting_actual_support_specification", "purpose": "Fresh purpose-isolated training sources and current-policy collection",
           "development_records_are_training_support": False,
           "repetition_planning": "Use overall valid-output yield and estimation precision, not success-pool class proportions",
           "must_freeze": ["fresh_training_source", "current_strategy_window", "repetition_count_and_precision",
                           "M", "n_xi_i_z", "n_positive_xi_i", "v_xi_i", "b_xi_i_z"]},
    "P3": {"status": "awaiting_actual_support_and_fair_probe_budget", "methods": ["B", "G-raw", "I-P"],
           "must_freeze": ["actual_n_positive_and_K", "complete_probe_directions", "shared_B_once",
                           "formal_updates_from_common", "independent_confirmation", "fair_total_resource_policy"],
           "raw_member_branches_may_be_dropped_to_reduce_cost": False,
           "G_lift_is_auxiliary_not_G_raw": True},
}
checked = prior.checked


def inventory():
    from proworksim.software_runtime_v034 import inventory as current_inventory
    return current_inventory()


def validate_inventory(rows):
    if (len(rows) != 4 or len({row["slot_id"] for row in rows}) != 4
            or len({row["case_id"] for row in rows}) != 2
            or len({row["sampling_seed"] for row in rows}) != 2
            or len({(row["case_id"], row["sampling_seed"]) for row in rows}) != 4
            or any(row.get("condition") != "T" or row.get("team_limits") != TEAM_LIMITS
                   or row.get("role_decision_limits") != {"member_a": 128, "member_b": 128}
                   for row in rows)
            or {row["case_id"] for row in rows} & {row["case_id"] for row in prior.inventory()}):
        raise ValueError("P1 requires two new O1 roots x two fixed seeds, four T slots per model")
    return rows



def reference_route_budget(data_root):
    """Fail closed on the final conditional native cost witness, without rerunning it."""
    from proworksim.software_context_v034 import VERSION as presentation_version
    path = Path(data_root) / "runs/v034-controls/presentation/reference-route-budget-final.json"
    proof = read_json(path)
    expected_limits = {"context": 16384, "max_output_per_call": 2048, "episode_tokens": 500000,
                       "decisions": 128, "attempts": 128, "test_runs": 32}
    if (proof.get("version") != "reference-route-native-budget-v0.34"
            or proof.get("presentation_version") != presentation_version
            or proof.get("passed") is not True or proof.get("model_calls") != 0
            or proof.get("gpu_used") is not False or proof.get("weights_loaded") is not False
            or proof.get("public_feedback_projection_applied") is not True
            or proof.get("limits") != expected_limits or proof.get("reference_routes") != 4):
        raise ValueError("Require the passing final zero-model native route-budget witness under the feedback Gamma")
    source_refs = proof.get("source_refs", {})
    helper_name = "src/proworksim/software_tasks_v034.py"
    required_sources = {helper_name, "scripts/measure_software_reference_routes_v034.py",
                        "src/proworksim/software_context_v034.py", "src/proworksim/software_context_v028.py",
                        "src/proworksim/candidate_runtime_v015.py", "src/proworksim/candidate_runtime_v030.py",
                        "src/proworksim/native_codecs_v031.py"}
    if not required_sources <= set(source_refs):
        raise ValueError("The final route-budget witness must bind its helper and native measurement sources")
    for name, item in source_refs.items():
        current = (SOURCE / name).resolve()
        if not current.is_relative_to(SOURCE) or digest(current.read_bytes()) != item.get("file_sha256"):
            raise ValueError("A final route-budget implementation changed: " + name)
    if proof.get("public_feedback_projection_source", {}).get("file_sha256") != source_refs[helper_name]["file_sha256"]:
        raise ValueError("The public-feedback helper is not the measured implementation")
    expected = {(candidate, row["slot_id"]): row for candidate in CANDIDATES for row in inventory()}
    rows = proof.get("rows", [])
    if len(rows) != 8 or {(row.get("model"), row.get("slot_id")) for row in rows} != set(expected):
        raise ValueError("The route-budget witness must cover both native formats and all four fixed routes")
    for row in rows:
        slot = expected[(row["model"], row["slot_id"])]
        steps = row.get("steps", [])
        if (row.get("case_id") != slot["case_id"] or not steps
                or row.get("scripted_calls") != len(steps) or len(steps) > TEAM_LIMITS["max_attempts"]
                or any(row.get(key) is not True for key in (
                    "all_steps_fit_context", "all_constructed_outputs_fit_output_limit", "episode_budget_fits"))
                or any(type(row.get(key)) is not int or row[key] < 0 for key in (
                    "decision_margin", "attempt_margin", "test_margin", "episode_token_margin"))):
            raise ValueError("A final reference route did not pass every fixed budget gate")
        for step in steps:
            output = step.get("canonical_reference_output", {})
            if (type(step.get("prompt_tokens")) is not int or step["prompt_tokens"] < 0
                    or step.get("reserved_output_tokens") != 2048
                    or step.get("context_upper_bound_tokens") != step["prompt_tokens"] + 2048
                    or step["context_upper_bound_tokens"] > 16384 or step.get("context_fits") is not True
                    or output.get("within_2048") is not True or output.get("native_parser_roundtrip_equal") is not True
                    or type(output.get("tokens_including_native_stop")) is not int
                    or not 0 < output["tokens_including_native_stop"] <= 2048):
                raise ValueError("A final reference request/output exceeds the original native limits")
        total = sum(step["context_upper_bound_tokens"] for step in steps)
        if row.get("episode_token_upper_bound") != total or total > 500000:
            raise ValueError("The final route upper bound does not fit the unchanged episode budget")
    if proof.get("native_request_measurements") != sum(len(row["steps"]) for row in rows):
        raise ValueError("Final route measurement count differs from its step records")
    return reference(path)


def presentation_binding(data_root):
    from proworksim.software_context_v034 import VERSION as presentation_version
    from proworksim.software_tasks_v034 import PUBLIC_FEEDBACK_VERSION
    root = Path(data_root) / "runs/v034-controls/presentation"
    route_budget = reference_route_budget(data_root)
    return {"version": presentation_version,
            "implementation": reference(SOURCE / "src/proworksim/software_context_v034.py"),
            "audit_report": reference(root / "report.json"), "cpu_controls": reference(root / "controls.json"),
            "reference_route_budget": route_budget,
            "reference_route_budget_scope": "Conditional CPU/native-tokenizer witness for declared derived scripted requests; not sampled model feasibility, current support or exact replay of all fresh runtime requests",
            "public_test_feedback": {
                "version": PUBLIC_FEEDBACK_VERSION,
                "helper": "proworksim.software_tasks_v034.project_public_test_feedback",
                "implementation": reference(SOURCE / "src/proworksim/software_tasks_v034.py"),
                "world_implementation": reference(SOURCE / "src/proworksim/software_collaboration_v034.py"),
                "lossless_projection": False,
                "passed_public_test_fields": ["test_id", "requirement_group", "status"],
                "failed_business_diagnostics_preserved": True,
                "member_authored_test_feedback_preserved": True,
                "raw_public_stdout_and_detailed_api_trace_actor_visible": False,
                "raw_test_event_retained_for_audit": True,
                "public_execution_actor_view": "Execution status and original stdout digest/size only; no duplicate full public result",
            },
            "behavior_distribution_preserved": False,
            "behavior_distribution_unchanged_claimed": False,
            "latest_public_feedback_preserved_byte_for_byte": False,
            "contract_and_tool_schema_preserved": True}


def make_plan(data_root, cpu_qualification):
    root = Path(data_root).resolve()
    parents = {c: prior.inherited_candidate(root, c) for c in CANDIDATES}
    old_model_plan = read_json(checked(parents[CANDIDATES[0]]["references"]["plan"]))
    previous = root / "runs/software-paired-o1-v033-recovery/plan.json"
    previous_plan = read_json(previous)
    slots = validate_inventory(inventory())
    return {
        "version": VERSION, "created_at": time.time(), "source": code_identity(), "source_root": str(SOURCE),
        "data_root": str(root), "qualification": reference(cpu_qualification), "parents": parents,
        "presentation": presentation_binding(root), "candidates": list(CANDIDATES),
        "inventories": {c: copy.deepcopy(slots) for c in CANDIDATES},
        "limits": copy.deepcopy(LIMITS), "gpu_preference": list(GPU_ORDER),
        "team_limits": copy.deepcopy(TEAM_LIMITS), "generation_limits": copy.deepcopy(GENERATION_LIMITS),
        "runtime_dependency_path": old_model_plan["runtime_dependency_path"],
        "prior_artifact_roots": dense._artifact_roots([
            *previous_plan["prior_artifact_roots"], previous.parent]),
        "closed_v033_report": reference(root / "docs/experiments/software-paired-o1-v033-recovery.json"),
        "protocol": reference(SOURCE / "docs/experiments/software-local-feasibility-v034-protocol.md"),
        "frozen_development_episodes": 8, "episodes_per_model": 4, "conditions": ["T"],
        "phases": copy.deepcopy(PHASES), "next_stage_rule": copy.deepcopy(NEXT_STAGE_RULE),
        "optimizer_updates_allowed": False, "fresh_technical_quiz_calls": 0, "repeat_near_16k_stress": False,
        "automatic_retries": False, "automatic_successors": [], "automatic_unfrozen_successors": False,
        "automatic_model_replacement": False, "resample_v033_slots": False, "repeat_S_conditions": False,
        "historical_results_reclassified": False, "old_selected_candidate": None,
        "swe_rerun": False, "new_model_downloads": False,
        "total_gpu_seconds": None, "worker_gpu_seconds": None, "queue_deadline_at": None, "wall_deadline_at": None,
        "historical_gpu_costs_included_as_new": False,
        "authorization": "User requested revisions and subsequent experiments following the v034 audit",
        "scope": "P0 CPU preparation and one P1 batch: two existing models x two new O1 roots x two fixed seeds, T only. Original common and native profile, new fixed presentation Gamma, unchanged joint budgets. P2/P3 require new actual-support and fair-probe specifications and are not launched automatically.",
    }


def validate_plan(plan, *, check_files=True):
    slots = validate_inventory(inventory())
    if (plan.get("version") != VERSION or plan.get("candidates") != list(CANDIDATES)
            or plan.get("inventories") != {c: slots for c in CANDIDATES}
            or plan.get("limits") != LIMITS or plan.get("gpu_preference") != GPU_ORDER
            or plan.get("team_limits") != TEAM_LIMITS or plan.get("generation_limits") != GENERATION_LIMITS
            or plan.get("frozen_development_episodes") != 8 or plan.get("episodes_per_model") != 4
            or plan.get("conditions") != ["T"] or plan.get("phases") != PHASES
            or plan.get("next_stage_rule") != NEXT_STAGE_RULE
            or plan.get("optimizer_updates_allowed") is not False
            or plan.get("fresh_technical_quiz_calls") != 0 or plan.get("repeat_near_16k_stress") is not False
            or plan.get("automatic_retries") is not False or plan.get("automatic_successors") != []
            or plan.get("automatic_unfrozen_successors") is not False or plan.get("automatic_model_replacement") is not False
            or plan.get("resample_v033_slots") is not False or plan.get("repeat_S_conditions") is not False
            or plan.get("historical_results_reclassified") is not False or plan.get("old_selected_candidate") is not None
            or plan.get("historical_gpu_costs_included_as_new") is not False
            or plan.get("swe_rerun") is not False or plan.get("new_model_downloads") is not False
            or any(plan.get(key) is not None for key in ("total_gpu_seconds", "worker_gpu_seconds", "queue_deadline_at", "wall_deadline_at"))):
        raise ValueError("Use exactly the frozen eight-slot T-only P1 batch; P2/P3 are not executable successors")
    if check_files:
        if (plan["source"] != code_identity() or plan["source"].get("code_dirty") is not False
                or plan["source_root"] != str(SOURCE)):
            raise ValueError("Use the exact clean CPU-qualified v034 execution checkout")
        cpu = read_json(checked(plan["qualification"]))
        if (cpu.get("passed") is not True or cpu.get("source") != plan["source"]
                or cpu.get("model_calls") != 0 or cpu.get("gpu_used") is not False):
            raise ValueError("Require passing same-source zero-model zero-GPU P0 controls")
        if presentation_binding(plan["data_root"]) != plan["presentation"]:
            raise ValueError("The frozen presentation Gamma or its P0 evidence changed")
        for c in CANDIDATES:
            if prior.inherited_candidate(plan["data_root"], c) != plan["parents"][c]:
                raise ValueError("Original common, native profile or numerical implementation changed")
        historical = read_json(checked(plan["closed_v033_report"]))
        if historical.get("status") != "complete":
            raise ValueError("The previous v033 queue must already be closed")
        checked(plan["protocol"])
    return plan


def observe_rows(actual, expected):
    rows = read(Path(actual) / "diagnostics/progress.json") or []
    if len(rows) > len(expected) or any(
        any(row.get(key) != value for key, value in slot.items())
        for row, slot in zip(rows, expected)
    ):
        raise ValueError("P1 progress must be a prefix of the four frozen new T slots")
    return rows


def run_worker(plan_path, candidate, output):
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.online_training import tensor_tree_digest
    from proworksim.software_learning_v029 import migrate_software_owner
    from proworksim.software_runtime_v034 import collect, window_spec

    plan = validate_plan(read_json(plan_path))
    if candidate not in CANDIDATES or os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, GPU_ORDER)):
        raise ValueError("One declared candidate per assigned physical GPU")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"version": VERSION, "candidate_id": candidate, "status": "loading", "started_at": time.time(),
        "source_before": code_identity(), "rows": [], "plan": reference(plan_path),
        "fresh_technical_quiz_calls": 0, "diagnostic_optimizer_steps": 0, "screening_optimizer_steps": 0,
        "historical_results_reclassified": False, "learning_evidence_inherited": True,
        "new_sampling_episodes": 4, "presentation": plan["presentation"]}
    owner = None
    write(output / "report.json", report)
    try:
        task(output, "load-original-common-" + candidate, "loading")
        sample = resources()
        write(output / "preload-resources.json", sample)
        if int(os.environ["CUDA_VISIBLE_DEVICES"]) not in [card["index"] for card in available_cards(plan, sample)]:
            raise RuntimeError("Assigned empty A100 capacity changed before loading")
        parent = plan["parents"][candidate]
        refs = parent["references"]
        saved_owner = read_json(checked(refs["owner"]))
        old_plan = read_json(checked(refs["plan"]))
        if candidate == CANDIDATES[0]:
            loading = read_json(checked(old_plan["prior_model_plan"]))
            owner = DeterministicCandidateActor.from_candidate(loading["model"], manifest=checked(loading["manifest"]),
                profile=loading["runtime_profile"], recipe=saved_owner["recipe"], output=output / "resident")
        else:
            profile = old_plan["candidate_profiles"][candidate]
            owner = dense.load_owner(saved_owner["base_identity"]["path"], manifest=checked(refs["base_manifest"]),
                profile=profile, recipe=saved_owner["recipe"], output=output / "resident")
        write(output / "software-critic-migration.json", migrate_software_owner(owner, expected_steps=None))
        if owner.inference_profile != saved_owner["inference_profile"] or owner.base_identity != saved_owner["base_identity"]:
            raise ValueError("Actual native runtime/base identity differs from inherited numerical evidence")
        task(output, "restore-full-original-common", "boundary")
        common_dir = checked(refs["common"]).parent
        common = read_json(common_dir / "checkpoint.json")
        if owner.restore_checkpoint(common_dir) != common:
            raise ValueError("Restore must return the exact original common checkpoint")
        def verify_common():
            if (tensor_tree_digest(owner._state_bundle(), owner.torch) != common["state_tensor_digest"]
                    or owner.freeze_identity() != common["actor_identity"]
                    or (owner.actor_steps, owner.critic_steps) != (parent["common_steps"], parent["common_steps"])):
                raise ValueError("Actor/critic/optimizers/RNG identity is not the original common")
        verify_common()
        report.update(status="collecting", common_actor_identity=owner.freeze_identity(),
                      initial_actor_steps=owner.actor_steps, initial_critic_steps=owner.critic_steps,
                      inherited_learning_evidence=parent, execution_binding_passed=True)
        write(output / "inherited-common.json", {"restored_exactly": True, "common": refs["common"],
              "state_tensor_digest": common["state_tensor_digest"], "actor_identity": owner.freeze_identity(),
              "no_new_learning_or_capacity_probe": True})
        write(output / "report.json", report)
        def on_slot(event, row, folder):
            if event == "closed":
                report["rows"] = observe_rows(output, plan["inventories"][candidate])
                write(output / "report.json", report)
        entries = collect(owner, window_spec("v034-" + candidate), output / "diagnostics", output,
                          common_dir=common_dir, on_slot=on_slot)
        verify_common()
        report["rows"] = observe_rows(output, plan["inventories"][candidate])
        if len(entries) != 4 or len(report["rows"]) != 4:
            raise ValueError("P1 must retain exactly the four frozen new T slots")
        report.update(status="complete", common_restored_exactly=True)
    except BaseException as error:
        report.update(status="execution_error", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        report["rows"] = observe_rows(output, plan["inventories"][candidate])
        if owner is not None:
            report.update(actor_steps=owner.actor_steps, critic_steps=owner.critic_steps,
                          final_actor_identity=owner._make_identity())
        report.update(ended_at=time.time(), source_after=code_identity())
        write(output / "report.json", report)
    return report




def supervise(plan_path, run_root):
    plan = validate_plan(read_json(plan_path))
    root = Path(run_root).resolve()
    if any(root == Path(old) or root.is_relative_to(Path(old)) or Path(old).is_relative_to(root) for old in plan["prior_artifact_roots"]):
        raise ValueError("Use a new run outside every previous immutable artifact root")
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    states = {c: {"candidate_id": c, "status": "not_started", "attempted": False} for c in CANDIDATES}
    summary = {"version": VERSION, "status": "waiting", "started_at": time.time(), "observer_pid": os.getpid(),
               "source": plan["source"], "states": states}
    active, logs, guards, stable = {}, {}, {}, {}
    def publish():
        summary.update(observed_at=time.time(), worker_gpu_seconds=sum(x.get("elapsed_gpu_seconds", 0) for x in states.values()),
                       running_gpu_seconds=sum(time.time() - states[c]["started_at"] for c in active))
        write(root / "supervisor.json", summary)
        for c, state in states.items():
            write(root / c / "state.json", state)
    def finish(candidate, reason):
        process = active.pop(candidate)
        state = states[candidate]
        if process.poll() is None:
            continuation._stop_worker(process, state)
        process.wait(timeout=15)
        worker = read(root / candidate / "actual/report.json") or {}
        okay = (process.returncode == 0 and reason is None and worker.get("status") == "complete"
                and worker.get("source_before") == plan["source"] and worker.get("source_after") == plan["source"])
        ended = time.time()
        state.update(status="complete" if okay else "stopped", ended_at=ended, exit_code=process.returncode,
                     stop_reason=reason if reason is not None or okay else "worker_not_complete_same_source",
                     elapsed_gpu_seconds=max(0, ended - state["started_at"]))
        logs.pop(candidate).close()
        publish()
    with lock(root):
        try:
            while not all(s["status"] in TERMINAL for s in states.values()):
                for c, process in list(active.items()):
                    if process.poll() is not None:
                        finish(c, None if process.returncode == 0 else "worker_exit_error")
                size = sum(artifact_bytes(Path(path)) for path in dense._artifact_roots([*plan["prior_artifact_roots"], root]))
                free = shutil.disk_usage(root).free
                if size > LIMITS["artifact_bytes"] or free < LIMITS["minimum_volume_free_bytes"]:
                    for c in list(active):
                        finish(c, "trajectory_storage_reserve")
                    for c, state in states.items():
                        if state["status"] == "not_started":
                            state.update(status="stopped", stop_reason="trajectory_storage_reserve", ended_at=time.time(), elapsed_gpu_seconds=0)
                    break
                waiting = [c for c in CANDIDATES if states[c]["status"] == "not_started"]
                if waiting:
                    sample = resources()
                    with (root / "waiting-resources.jsonl").open("a") as stream:
                        stream.write(json.dumps(sample) + "\n")
                    cards = available_cards(plan, sample, [states[c]["gpu"] for c in active])
                    now = time.time()
                    stable = {card["index"]: stable.get(card["index"], now) for card in cards}
                    for card in cards:
                        if not waiting or len(active) >= 2:
                            break
                        if now - stable[card["index"]] < LIMITS["gpu_capacity_stability_seconds"]:
                            continue
                        validate_plan(plan)
                        c = waiting.pop(0)
                        folder = root / c
                        folder.mkdir(exist_ok=True)
                        argv = [sys.executable, "-m", "scripts.software_local_feasibility_v034", "worker", "--plan", str(root / "plan.json"),
                                "--candidate", c, "--output", str(folder / "actual")]
                        logs[c] = (folder / "worker.log").open("x")
                        started = time.time()
                        process = subprocess.Popen(argv, cwd=SOURCE, env=original.worker_env(plan, root, c, card["index"]),
                            stdin=subprocess.DEVNULL, stdout=logs[c], stderr=subprocess.STDOUT, start_new_session=True)
                        identity = worker_identity(process.pid)
                        states[c].update(status="running", attempted=True, started_at=started, gpu=card["index"], gpu_uuid=card["uuid"],
                                         pid=process.pid, process_identity=identity, command=argv)
                        active[c] = process
                        guards[c] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
                        publish()
                else:
                    stable = {}
                if active:
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = {c: pool.submit(target_resources, states[c]["gpu"], worker_pid=p.pid) for c, p in active.items()}
                        samples = {c: f.result() for c, f in futures.items()}
                    for c, process in list(active.items()):
                        if process.poll() is not None:
                            finish(c, None if process.returncode == 0 else "worker_exit_error")
                            continue
                        state = states[c]
                        observation = guards[c].observe(samples[c], time.time(), process.pid, state["gpu"], own_memory_limit_mib=LIMITS["own_gpu_memory_mib"])
                        current = read(root / c / "actual/task.json") or {"kind": "loading", "started_at": state["started_at"]}
                        own_rss, reason = rss(process.pid), observation.get("stop_reason")
                        cap = LIMITS["task_seconds"].get(current.get("kind"))
                        if current.get("kind") not in LIMITS["task_seconds"]:
                            reason = reason or "unknown_task_kind"
                        elif cap is not None and time.time() - current["started_at"] >= cap:
                            reason = reason or "single_task_budget"
                        elif own_rss > LIMITS["host_rss_per_worker_bytes"]:
                            reason = reason or "host_memory_budget"
                        with (root / c / "resources.jsonl").open("a") as stream:
                            stream.write(json.dumps({"sample": samples[c], "guard": observation, "task": current,
                                                     "rss_bytes": own_rss, "artifact_bytes": size, "volume_free_bytes": free}) + "\n")
                        if reason:
                            finish(c, reason)
                summary["status"] = "running" if active else "waiting"
                publish()
                if not all(s["status"] in TERMINAL for s in states.values()):
                    time.sleep(LIMITS["poll_seconds"])
            summary["status"] = "complete" if all(s["status"] == "complete" for s in states.values()) else "ended_with_execution_stop"
        except BaseException as error:
            summary["error"] = {"type": type(error).__name__, "message": str(error)}
            for c in list(active):
                finish(c, "supervisor_interrupted")
            for state in states.values():
                if state["status"] == "not_started":
                    state.update(status="stopped", stop_reason="supervisor_interrupted",
                                 ended_at=time.time(), elapsed_gpu_seconds=0)
            summary["status"] = "interrupted"
            raise
        finally:
            summary["ended_at"] = time.time()
            publish()
    write(root / "next-stage-decision.json", results(plan, root)["next_stage"])
    return summary




def compact_row(row, slot, progress_ref, index):
    model = row.get("team_budget", {}).get("model", {})
    tests = row.get("team_budget", {}).get("tests", {})
    result = {**copy.deepcopy(slot), "status": row.get("status", "not_started"),
              "record_validity": row.get("record_validity"),
              **{key: row.get(key) for key in (
                  "R", "submitted", "complete_delivery", "content_correct",
                  "required_process_satisfied", "process_observation_complete")},
              "training_eligible": False,
              "recorded_usage": {**{key: model.get(key) for key in (
                  "decisions", "attempts", "charged_tokens", "held_tokens")}, "test_runs": tests.get("used")},
              "started_at": row.get("started_at"), "ended_at": row.get("ended_at"),
              "evidence": {"progress": progress_ref if row else None,
                           "progress_index": index if row else None,
                           **{key: row[key] for key in ("entry", "assessment", "evaluation_guard") if key in row}}}
    return result


def known(row):
    return (row.get("status") == "closed" and row.get("record_validity") is True
            and type(row.get("R")) is int and row["R"] in (0, 1)
            and type(row.get("complete_delivery")) is bool
            and row["R"] == int(row["complete_delivery"]))


def usage_known(row):
    usage = row["recorded_usage"]
    limits = {"decisions": TEAM_LIMITS["max_decisions"], "attempts": TEAM_LIMITS["max_attempts"],
              "charged_tokens": TEAM_LIMITS["max_total_tokens"], "test_runs": TEAM_LIMITS["max_test_runs"]}
    return (all(type(usage[key]) is int and 0 <= usage[key] <= cap for key, cap in limits.items())
            and type(usage["held_tokens"]) is int and usage["held_tokens"] == 0)


def candidate_summary(rows, worker, state, plan, candidate):
    full = [row for row in rows if known(row) and row["R"] == 1]
    all_known = len(rows) == 4 and all(known(row) for row in rows)
    all_usage = len(rows) == 4 and all(usage_known(row) for row in rows)
    parent = plan["parents"][candidate]
    trusted = (state["status"] == "complete" and worker.get("status") == "complete"
        and worker.get("execution_binding_passed") is True and worker.get("common_restored_exactly") is True
        and worker.get("source_before") == plan["source"] and worker.get("source_after") == plan["source"]
        and worker.get("common_actor_identity") == parent["common_actor_identity"]
        and worker.get("final_actor_identity") == parent["common_actor_identity"]
        and all(worker.get(key) == parent["common_steps"] for key in (
            "initial_actor_steps", "initial_critic_steps", "actor_steps", "critic_steps"))
        and all(worker.get(key) == 0 for key in (
            "screening_optimizer_steps", "diagnostic_optimizer_steps", "fresh_technical_quiz_calls")))
    return {
        "expected": 4, "known": sum(known(row) for row in rows), "all_four_known_valid": all_known,
        "all_four_usage_known_within_budget": all_usage, "worker_trusted_and_common_restored": trusted,
        "complete_success_count": len(full), "distinct_roots_with_success": len({row["case_id"] for row in full}),
        "total_actual_tokens_all_four_slots": sum(row["recorded_usage"]["charged_tokens"] for row in rows) if all_usage else None,
        "eligible_local_carrier": all_known and all_usage and trusted and len(full) >= 1,
        "submitted": sum(row["submitted"] is True for row in rows),
        "not_submitted": sum(row["submitted"] is False for row in rows),
        "not_started": sum(row["status"] == "not_started" for row in rows),
        "technical_unknown": sum(row["status"] != "not_started" and not known(row) for row in rows),
        "content_known": sum(type(row["content_correct"]) is bool for row in rows),
        "content_correct": sum(row["content_correct"] is True for row in rows),
        "process_known": sum(type(row["required_process_satisfied"]) is bool for row in rows),
        "process_satisfied": sum(row["required_process_satisfied"] is True for row in rows),
        "process_observation_known": sum(type(row["process_observation_complete"]) is bool for row in rows),
        "process_observation_complete": sum(row["process_observation_complete"] is True for row in rows),
        "process_observation_incomplete": sum(row["process_observation_complete"] is False for row in rows),
        "process_observation_unknown": sum(row["process_observation_complete"] is None for row in rows),
        "state_status": state["status"], "state_stop_reason": state.get("stop_reason"),
        "worker_status": worker.get("status"),
    }


def next_stage_decision(candidate_results, terminal):
    eligible = [c for c in CANDIDATES if candidate_results[c]["eligible_local_carrier"]] if terminal else []
    eligible.sort(key=lambda c: (-candidate_results[c]["complete_success_count"],
        -candidate_results[c]["distinct_roots_with_success"],
        candidate_results[c]["total_actual_tokens_all_four_slots"], CANDIDATES.index(c)))
    unresolved = any(not result["all_four_known_valid"] or not result["all_four_usage_known_within_budget"]
                     or not result["worker_trusted_and_common_restored"] for result in candidate_results.values())
    if not terminal:
        status, next_work = "pending", "Finish only the remaining slots of this frozen P1 batch"
    elif eligible:
        status = "local_carrier_identified_for_p2_design"
        next_work = "Freeze fresh purpose-isolated training sources, overall-yield/precision-based repetition and current-strategy support; then freeze affordable fair B/G-raw/I-P trial dimensions using actual n+ and K"
    elif unresolved:
        status = "technical_unknown_no_carrier_decision"
        next_work = "Retain technical unknowns separately; do not relabel them as business zeros"
    else:
        status = "finite_p1_all_business_failed"
        next_work = "Close this batch with its observed results; no prompt retuning or automatic rerun of these same slots"
    return {"status": status, "local_carrier_for_p2_design": eligible[0] if eligible else None,
            "ranked_eligible_candidates": eligible, "rule": NEXT_STAGE_RULE,
            "all_business_failed_branch_applied": status == "finite_p1_all_business_failed",
            "one_success_is_stable_ability_or_allocation_support": False,
            "old_selection_reclassified": False, "prior_selected_candidate": None,
            "development_records_are_training_support": False, "automatic_execution": False,
            "P2_frozen_and_started": False, "P3_frozen_and_started": False,
            "required_next_freeze": next_work}


def cost_summary(supervisor):
    intervals, records = [], []
    for candidate in CANDIDATES:
        state = supervisor["states"][candidate]
        if not state.get("attempted") or state.get("ended_at") is None:
            continue
        start, end = state["started_at"], state["ended_at"]
        intervals.append(GpuInterval(state["gpu"], round(start * 1_000_000), round(end * 1_000_000)))
        records.append({"candidate_id": candidate, "gpu": state["gpu"], "pid": state.get("pid"),
                        "started_at": start, "ended_at": end,
                        "recorded_worker_seconds": state["elapsed_gpu_seconds"],
                        "controller_to_assignment_seconds": start - supervisor["started_at"]})
    union = interval_accounting(intervals, [])
    return {"new_distinct_worker_gpu_seconds": sum(row["recorded_worker_seconds"] for row in records),
            "new_running_gpu_seconds": supervisor.get("running_gpu_seconds", 0),
            "worker_interval_union": union["totals"]["worker_union"],
            "per_gpu": [{"gpu": row["gpu"], **row["worker_union"]} for row in union["per_gpu"]],
            "recorded_worker_intervals": records, "historical_gpu_costs_included": False,
            "scope": "This P1 stage only: terminal assigned-to-ended single-GPU worker intervals, merged per GPU. Queue waits are wall delays, not GPU occupancy; P0 CPU work and historical runs are excluded."}


def results(plan, root):
    root = Path(root)
    supervisor = read_json(root / "supervisor.json")
    outcomes, candidates = {}, {}
    for candidate in CANDIDATES:
        actual = root / candidate / "actual"
        observed = observe_rows(actual, plan["inventories"][candidate])
        progress = actual / "diagnostics/progress.json"
        progress_ref = reference(progress) if progress.exists() else None
        rows = [compact_row(observed[index] if index < len(observed) else {}, slot, progress_ref, index)
                for index, slot in enumerate(plan["inventories"][candidate])]
        worker = read(actual / "report.json") or {}
        outcomes[candidate] = rows
        candidates[candidate] = candidate_summary(rows, worker, supervisor["states"][candidate], plan, candidate)
        candidates[candidate]["worker_report"] = reference(actual / "report.json") if (actual / "report.json").exists() else None
    terminal = all(supervisor["states"][c]["status"] in TERMINAL for c in CANDIDATES)
    rows = [row for group in outcomes.values() for row in group]
    observed_usage = [row for row in rows if usage_known(row)]
    return {
        "version": VERSION, "generated_at": time.time(), "status": supervisor["status"],
        "source": plan["source"], "plan": reference(root / "plan.json"),
        "supervisor": reference(root / "supervisor.json"), "qualification": plan["qualification"],
        "presentation": plan["presentation"], "phases": PHASES,
        "outcomes": outcomes, "candidate_results": candidates,
        "next_stage": next_stage_decision(candidates, terminal), "selected_candidate": None,
        "logical_inventory_count": 8, "conditions": ["T"], "old_v033_slots_added_to_denominator": 0,
        "sampling_summary": {"rows_observed": sum(row["status"] != "not_started" for row in rows),
            "rows_with_known_usage": len(observed_usage),
            **{key: sum(row["recorded_usage"][key] for row in observed_usage)
               for key in ("decisions", "attempts", "charged_tokens", "test_runs")}},
        "complete_deliveries": sum(known(row) and row["R"] == 1 for row in rows),
        "known_work_results": sum(known(row) for row in rows),
        "optimizer_steps": 0, "fresh_technical_quiz_calls": 0, "repeat_near_16k_stress": False,
        "allocation_experiment_started": False, "training_support_collected": False,
        "cost": cost_summary(supervisor), "scope": plan["scope"],
        "detail_storage": "Only compact slot fields and immutable source references are published. Full team ledgers, traces, contexts and boundaries remain in runs artifacts.",
    }


def report(run_root, output_dir):
    root, output = Path(run_root).resolve(), Path(output_dir).resolve()
    value = results(read_json(root / "plan.json"), root)
    output.mkdir(parents=True, exist_ok=True)
    write(output / "software-local-feasibility-v034.json", value)
    lines = ["# v0.34 P1 新根目标的有限团队可行性批次", "",
        f"状态：`{value['status']}`；源码：`{value['source']['code_commit']}`；原件：`{root}`。", "",
        "本阶段仅有现有 9B 与 Devstral、两个新 O1 根目标、两个固定 seed，共八条 T 经历。旧 v033 的十六槽不重跑，也不合入本轮分母；本轮没有 S 条件、新模型下载或 SWE 重测。", "",
        "P0 继承原 common 与真实数值接入证据，只执行新目标与呈现的 CPU 核查。新的 presentation Γ包含已证实的合同去重及额外有损公开测试反馈投影：通过项仅标识／分组／状态和汇总，失败业务诊断与成员自测反馈保留，完整公开 stdout/API 细迹仅存审计原件。它可能改变实际行为分布，不能称为完整最新反馈的无损保留；离线输入计数差和条件化脚本路线预算旁证都不是新策略的实测收益。原 native profile、16K 上下文、2048 输出上限不变。", "",
        "每条 T 共享总预算 128 次决定、128 次尝试、500000 token、32 次 run_tests；不按成员翻倍。没有新增资格题、16K 压力或优化步骤。", "",
        "| 模型 | 根目标 | seed | 先手 | 完整 R | 提交 | 内容正确 | 规定过程满足 | 过程观测完整 | 状态 |",
        "|---|---|---:|---|---:|---|---|---|---|---|"]
    for candidate, rows in value["outcomes"].items():
        for row in rows:
            def show(key):
                return "未知/未开始" if row[key] is None else str(row[key])
            lines.append(f"| {candidate} | {row['case_id']} | {row['sampling_seed']} | {row['first_member']} | {show('R')} | {show('submitted')} | {show('content_correct')} | {show('required_process_satisfied')} | {show('process_observation_complete')} | {row['status']} |")
    lines += ["", "过程要求满足与过程观测完整分列：未证明满足不等于已证明完全没有调用 API。未知和未开始不补零；未提交的工作区不另行补验后替换原结果。", "",
        "| 模型 | 完整成功／已知 | 成功根目标数 | 四槽全量实际 token | 已提交 | common／执行可信 |",
        "|---|---:|---:|---:|---:|---|"]
    for candidate, result in value["candidate_results"].items():
        lines.append(f"| {candidate} | {result['complete_success_count']}/{result['known']} | {result['distinct_roots_with_success']} | {result['total_actual_tokens_all_four_slots']} | {result['submitted']} | {result['worker_trusted_and_common_restored']} |")
    next_stage, cost = value["next_stage"], value["cost"]
    lines += ["", f"局部载体决策：`{next_stage['status']}`；候选：`{next_stage['local_carrier_for_p2_design']}`。",
        "入选须同模型四槽全部已知可信、预算用量完整、原 common 完整恢复且至少一条完整 R=1。多候选依次比较完整成功数、成功根目标覆盖数、全部四槽实际 token 总量，最后用固定 9B→Devstral 顺序。没有只统计成功子集的成本。", "",
        "一条成功仅提供本地有限可行性，不是稳定能力认证、旧选型赢家或当前训练支持。全部业务失败则关闭固定批次，不围绕这些槽逐句改提示重跑；无候选且有技术未知时保留独立未知状态。", "",
        "P2 仍须冻结用途隔离的新训练来源、当前策略窗口及依据全体有效产出率与精度确定的重复数，不能把本批开发轨迹改标为训练。P3 须按真实 n+、K 和贡献开发成本另冻公平的 B／G-raw／I-P 预算，共享 B 一次且不临时删除原始分支探测方向；G-lift 只作辅助对照。没有自动启动未冻结训练或试训，也没有预承诺固定训练重复数。", "",
        f"本阶段新 worker 成本：{cost['new_distinct_worker_gpu_seconds']:.9f} GPU 秒；逐卡区间并集：{cost['worker_interval_union']['gpu_seconds']:.6f} 秒（{cost['worker_interval_union']['gpu_hours']:.9f} GPU 小时）；当前运行中：{cost['new_running_gpu_seconds']:.6f} 秒。",
        "上述只计本阶段已分配单卡 worker 墙钟，排队等待、P0 CPU 工作和旧实验 GPU 成本未混入。累计 GPU／worker／统一墙钟上限仍为空，单任务与内存、产物保护门保留。", "",
        "本轮没有参数训练或 ID-VTDO 分配效果结论；新小任务高于旧任务也只说明载体与呈现改变，不能替代同一载体上的独立 B/G/I 学习增量。", ""]
    (output / "software-local-feasibility-v034.md").write_text("\n".join(lines))
    return value


def finish(plan_path, run_root, report_repo, *, publish=False):
    plan_path, run_root, report_repo = (Path(p).resolve() for p in (plan_path, run_root, report_repo))
    if run_root.exists():
        raise FileExistsError("Do not retry or append a previously started P1 feasibility batch")
    path = run_root.parent / (run_root.name + "-finish.json")
    state = {"version": VERSION, "status": "supervising", "started_at": time.time(), "run_root": str(run_root)}
    write(path, state)
    process = subprocess.run([sys.executable, "-m", "scripts.software_local_feasibility_v034", "supervise", "--plan", str(plan_path),
                              "--run-root", str(run_root)], cwd=SOURCE, check=False)
    state["supervisor_exit_code"] = process.returncode
    if not (run_root / "supervisor.json").exists():
        state.update(status="failed_before_run_archive", ended_at=time.time())
        write(path, state)
        return state
    report(run_root, report_repo / "docs/experiments")
    state["status"] = "reported"
    write(path, state)
    if publish:
        if subprocess.check_output(["git", "branch", "--show-current"], cwd=report_repo, text=True).strip() != "main":
            state["publish_status"] = "repository_branch_changed"
        else:
            subprocess.run(["git", "add", "--", *REPORT_PATHS], cwd=report_repo, check=True)
            change = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *REPORT_PATHS], cwd=report_repo).returncode
            if change == 1:
                subprocess.run(["git", "commit", "--only", "-m", "docs: archive v034 finite local team feasibility batch", "--", *REPORT_PATHS], cwd=report_repo, check=True)
            elif change != 0:
                raise RuntimeError("Cannot inspect the fixed v034 report paths")
            state["report_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=report_repo, text=True).strip()
            env = {key: value for key, value in os.environ.items() if key.lower() not in {"http_proxy", "https_proxy", "all_proxy"}}
            attempts = []
            for index in range(3):
                result = subprocess.run(["git", "push", "origin", "main"], cwd=report_repo, env=env, capture_output=True, text=True, timeout=90)
                attempts.append({"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
                if result.returncode == 0:
                    break
                if index < 2:
                    time.sleep(10)
            state.update(publish_status="pushed" if attempts[-1]["returncode"] == 0 else "push_failed", push_attempts=attempts)
    state["ended_at"] = time.time()
    write(path, state)
    return state




def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "worker", "supervise", "report", "finish"])
    for name in ("data-root", "cpu-qualification", "plan", "run-root", "output", "report-repo"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--candidate", choices=CANDIDATES)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    required = {"prepare": ("data_root", "cpu_qualification", "output"),
                "worker": ("plan", "candidate", "output"), "supervise": ("plan", "run_root"),
                "report": ("run_root", "output"), "finish": ("plan", "run_root", "report_repo")}
    if any(getattr(args, key) is None for key in required[args.mode]):
        parser.error(args.mode + " requires " + ", ".join(required[args.mode]))
    def interrupted(signum, frame):
        raise KeyboardInterrupt("P1 local feasibility received signal " + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    if args.mode == "prepare":
        value = validate_plan(make_plan(args.data_root, args.cpu_qualification))
        write(args.output, value)
    elif args.mode == "worker":
        value = run_worker(args.plan, args.candidate, args.output)
    elif args.mode == "supervise":
        value = supervise(args.plan, args.run_root)
    elif args.mode == "report":
        value = report(args.run_root, args.output)
    else:
        value = finish(args.plan, args.run_root, args.report_repo, publish=args.publish)
    print(json.dumps({"version": VERSION, "status": value.get("status", "written")}))


if __name__ == "__main__":
    main()
