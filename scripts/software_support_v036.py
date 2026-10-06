"""One fixed sixteen-slot P2 support window before contribution feedback."""
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
from proworksim.storage import digest, json_bytes, read_json
from scripts import continue_model_selection_v031 as continuation
from scripts import software_model_selection_v030 as original
from scripts import software_model_selection_v031 as dense
from scripts import software_local_feasibility_v034 as selected
from scripts.gpu_occupancy_accounting import GpuInterval, interval_accounting
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, resources, write
from scripts.software_development_v028 import available_cards, task

VERSION = "software-current-policy-support-v0.36"
SOURCE = Path(__file__).resolve().parents[1]
CANDIDATE = "qwen3.5-9b"
CANDIDATES = (CANDIDATE,)
GPU_ORDER = list(selected.GPU_ORDER)
LIMITS = {**copy.deepcopy(selected.LIMITS), "max_parallel_model_instances": 1}
TERMINAL = {"complete", "stopped"}
TEAM_LIMITS = copy.deepcopy(selected.TEAM_LIMITS)
GENERATION_LIMITS = copy.deepcopy(selected.GENERATION_LIMITS)
SUPPORT_M = 16
SUPPORT_WINDOW = "v036-current-policy-support-16"
SUPPORT_SEEDS = tuple(range(202610070101, 202610070117))
DEVELOPMENT_SEEDS = tuple(range(202610070201, 202610070205))
CONFIRMATION_SEEDS = tuple(range(202610070301, 202610070305))
REPORT_PATHS = ["docs/experiments/software-support-v036.md", "docs/experiments/software-support-v036.json"]
AUTOMATIC_SUCCESSORS = ["freeze_actual_support_before_feedback", "shared_B_real_consumption_and_cost",
                        "all_frozen_G_raw_and_I_P_trials", "three_formal_updates_and_independent_panel"]
ROUTING_ADDITION = (
    "    from .experience_allocation_v035 import VERSION as current_version, validate_allocation as current_allocation\n"
    "\n"
    "    if isinstance(composition, dict) and composition.get(\"version\") == current_version:\n"
    "        return current_allocation(entries, prepared, composition)\n"
)
POLICY = {
    "M": 16, "fixed_first_member": "member_a", "min_class_count": 2,
    "member_block_order": ["member_a", "member_b"], "maximum_configured_blocks": 1,
    "stop_rule": "Exactly sixteen slots; no stop-on-success or stop-on-two-classes; technical stops remain unknown",
    "base_denominator": "Original M x active members x original member own output tokens; residuals stay weight one and masks are not renormalized",
    "critic_recipe_changes_with_q": False,
    "M_rationale": "Finite unknown-yield window chosen jointly with full-direction cost; not inferred from mixed P1 success fractions",
    "postcollection_before_contribution_freeze_required": True, "automatic_unfrozen_P3": False,
    "P3_upper_inventory": {"unique_trial_updates": 33, "development_episodes": 528,
                           "formal_updates": 3, "independent_confirmation_episodes": 48},
    "B_trial_contains_probability_and_target_consumption_checks": True,
    "extra_production_diagnostic_updates": 0,
    "development_panel": {"roots": 4, "paired_seeds_per_root": 4, "D": 16},
    "confirmation_panel": {"roots": 4, "seeds_per_root": 4, "per_method": 16},
    "measurement_scope": "Local mechanism panel; D=16 is not precision certification. Report paired outcomes per root; no seed-as-task confidence interval.",
    "conditional_full_online_inventory_upper": 592,
    "conditional_full_window_updates_upper": 36,
    "no_new_rewards_or_learning_rate_or_weight_tuning": True,
    "closed_P3_trace_archival": "Lossless checksum-verified cold archive; all original file bytes remain recoverable; support material stays live for every update",

}
checked = selected.checked


def inventories():
    from proworksim.software_collaboration_v036 import CONTRIBUTION_CASE_IDS, CONFIRMATION_CASE_IDS
    from proworksim.software_runtime_v036 import inventory
    def panel(case_ids, seeds, prefix):
        return [inventory(case_id, seeds=(seed,), first_member="member_a",
                          prefix=f"{prefix}-{seed_index}-{case_index}")[0]
                for seed_index, seed in enumerate(seeds) for case_index, case_id in enumerate(case_ids)]
    return {"support": inventory(seeds=SUPPORT_SEEDS, first_member="member_a", prefix="v036-support"),
            "development": panel(CONTRIBUTION_CASE_IDS, DEVELOPMENT_SEEDS, "v036-development"),
            "confirmation": panel(CONFIRMATION_CASE_IDS, CONFIRMATION_SEEDS, "v036-confirmation")}


def inherited_candidate(data_root):
    """Reuse unchanged numerical binding and preserve the closed v035 result."""
    from scripts.software_support_v035 import inherited_candidate as inherited_v035
    root = Path(data_root).resolve()
    parent = inherited_v035(root)
    prior_path = root / "docs/experiments/software-support-v035.json"
    prior = read_json(prior_path)
    if (prior.get("status") != "complete" or prior.get("known_results") != 16
            or prior.get("optimizer_updates_during_P2") != 0
            or prior.get("worker_trusted_and_common_restored") is not True
            or prior.get("next_stage", {}).get("P3_started") is not False):
        raise ValueError("Keep the completed original v035 window and no historical P3")
    parent.update(closed_v035_report=reference(prior_path),
        old_v035_slots_are_shadow_development_only=True,
        model_and_training_root_reselection=False)
    return parent


def presentation(parent):
    from proworksim.software_collaboration_v036 import PUBLIC_FEEDBACK_VERSION, MEMBER_TEST_VERSION, member_test_specification
    return {"version": "software-information-v0.36", "capacity_and_deduplication": parent["inherited_presentation"],
        "member_test_feedback_version": PUBLIC_FEEDBACK_VERSION, "member_test_completion": MEMBER_TEST_VERSION,
        "member_runner": reference(SOURCE / "src/proworksim/software_collaboration_v036.py"),
        "member_test_specification": member_test_specification(),
        "scope": "The exact v034 input-capacity/deduplication algorithm is unchanged; only the new evidence-backed member-script completion feedback changes Gamma. No historical status is repaired."}


def make_plan(data_root, cpu_qualification):
    from proworksim.software_mapper_v036 import mapping_spec
    from proworksim.software_collaboration_v036 import case_spec
    from scripts.software_allocation_v036 import LIMITS as P3_LIMITS
    root = Path(data_root).resolve()
    parent = inherited_candidate(root)
    previous = read_json(checked(parent["selected_v034_plan"]))
    model_plan = read_json(checked(parent["references"]["plan"]))
    rows = inventories()
    cases = {row["case_id"]: case_spec(row["case_id"], first_member="member_a")
             for group in rows.values() for row in group}
    return {"version": VERSION, "created_at": time.time(), "source": code_identity(), "source_root": str(SOURCE),
        "data_root": str(root), "qualification": reference(cpu_qualification), "candidate_id": CANDIDATE,
        "parent": parent, "presentation": presentation(parent),
        "inventories": rows, "cases": cases, "mapper_specification": mapping_spec(), "policy": copy.deepcopy(POLICY),
        "support_window_id": SUPPORT_WINDOW, "frozen_sampling_slots": SUPPORT_M,
        "future_panels_frozen_before_support": True, "future_panels_executable_during_P2": False,
        "limits": copy.deepcopy(LIMITS), "gpu_preference": list(GPU_ORDER),
        "team_limits": copy.deepcopy(TEAM_LIMITS), "generation_limits": copy.deepcopy(GENERATION_LIMITS),
        "runtime_dependency_path": model_plan["runtime_dependency_path"],
        "prior_artifact_roots": dense._artifact_roots([*previous["prior_artifact_roots"],
            Path(parent["selected_v034_plan"]["path"]).parent, root / "runs/software-support-v035"]),
        "protocol": reference(SOURCE / "docs/experiments/software-support-v036-protocol.md"),
        "audit_reference": reference(SOURCE / "docs/reference/audit-v035-next-v036.md"),
        "optimizer_updates_during_P2": 0, "fresh_technical_quiz_calls": 0, "repeat_near_16k_stress": False,
        "automatic_retries": False, "automatic_successors": list(AUTOMATIC_SUCCESSORS), "automatic_unfrozen_P3": False,
        "automatic_successor_authorization": "User explicitly approved automatic_execution after the approval-review rejection in this v036 session. Conditions and complete frozen inventories remain mandatory.",
        "P3_resource_limits": copy.deepcopy(P3_LIMITS),
        "total_gpu_seconds": None, "worker_gpu_seconds": None, "queue_deadline_at": None, "wall_deadline_at": None,
        "historical_results_reclassified": False, "historical_gpu_costs_included_as_new": False,
        "scope": "One selected 9B owner, original complete 3/3 common and declared v036 member-test feedback Gamma; same training root/new exact window and sixteen seeds. P2 collects support only. Actual n+/K/kernel/directions/steps/trial/fair budget require a later freeze before any contribution feedback."}


def validate_plan(plan, *, check_files=True):
    from proworksim.software_mapper_v036 import mapping_spec
    from proworksim.software_collaboration_v036 import case_spec
    rows = inventories()
    cases = {row["case_id"]: case_spec(row["case_id"], first_member="member_a")
             for group in rows.values() for row in group}
    if (plan.get("version") != VERSION or plan.get("candidate_id") != CANDIDATE
            or plan.get("inventories") != rows or plan.get("cases") != cases
            or plan.get("mapper_specification") != mapping_spec() or plan.get("policy") != POLICY
            or plan.get("support_window_id") != SUPPORT_WINDOW or plan.get("frozen_sampling_slots") != SUPPORT_M
            or plan.get("limits") != LIMITS or plan.get("gpu_preference") != GPU_ORDER
            or plan.get("team_limits") != TEAM_LIMITS or plan.get("generation_limits") != GENERATION_LIMITS
            or plan.get("future_panels_frozen_before_support") is not True
            or plan.get("future_panels_executable_during_P2") is not False
            or plan.get("optimizer_updates_during_P2") != 0 or plan.get("fresh_technical_quiz_calls") != 0
            or plan.get("repeat_near_16k_stress") is not False or plan.get("automatic_retries") is not False
            or plan.get("automatic_successors") != AUTOMATIC_SUCCESSORS or plan.get("automatic_unfrozen_P3") is not False
            or plan.get("historical_results_reclassified") is not False
            or plan.get("historical_gpu_costs_included_as_new") is not False
            or any(plan.get(key) is not None for key in ("total_gpu_seconds", "worker_gpu_seconds", "queue_deadline_at", "wall_deadline_at"))):
        raise ValueError("Use exactly the sixteen-slot P2 window and predeclared future panels")
    if check_files:
        from scripts.software_allocation_v036 import LIMITS as P3_LIMITS
        if plan.get("P3_resource_limits") != P3_LIMITS or not plan.get("automatic_successor_authorization"):
            raise ValueError("Explicitly authorized successors retain all frozen P3 resource protections")
        if (plan["source"] != code_identity() or plan["source"].get("code_dirty") is not False
                or plan["source_root"] != str(SOURCE)):
            raise ValueError("Use the exact clean CPU-qualified v036 source")
        qualification = read_json(checked(plan["qualification"]))
        if (qualification.get("passed") is not True or qualification.get("source") != plan["source"]
                or qualification.get("target_model_calls", qualification.get("model_calls")) != 0
                or qualification.get("gpu_used") is not False):
            raise ValueError("Require current-source CPU controls with no target-model/GPU qualification")
        if inherited_candidate(plan["data_root"]) != plan["parent"] or plan["presentation"] != presentation(plan["parent"]):
            raise ValueError("Selected common, declared routing adaptation or frozen Gamma changed")
        checked(plan["protocol"])
        checked(plan["audit_reference"])
    return plan


def observe_rows(actual, expected):
    rows = read(Path(actual) / "collection/progress.json") or []
    if len(rows) > len(expected) or any(any(row.get(key) != value for key, value in slot.items())
                                     for row, slot in zip(rows, expected)):
        raise ValueError("P2 progress must preserve the sixteen-slot prefix and exact seeds")
    return rows


def retained_inventory(entries, records, declaration, progress):
    """Represent missing slots explicitly; never resample or shrink the denominator."""
    byentry, byrecord = {r["slot_id"]: r for r in entries}, {r["slot_id"]: r for r in records}
    observed = {r["slot_id"]: r for r in progress}
    expected = {row["slot_id"] for row in declaration["slots"]}
    if len(byentry) != len(entries) or len(byrecord) != len(records) or set(byentry) - expected or set(byrecord) - expected:
        raise ValueError("Retained inventory cannot duplicate or introduce a raw slot")
    full_entries, full_records = [], []
    for slot in declaration["slots"]:
        sid = slot["slot_id"]
        full_entries.append(byentry.get(sid, {"slot_id": sid, "active_members": slot["active_members"],
                                             "rollout": None, "reward": None, "training_eligible": True}))
        row = byrecord.get(sid, {"slot_id": sid, "status": "not_started" if sid not in observed else "execution_unknown"})
        if sid in observed and observed[sid].get("status") != "closed":
            row = {"slot_id": sid, "status": "execution_unknown", "original_status": row["status"]}
        full_records.append(row)
    return full_entries, full_records


def current_support_gate(entries, declaration, records):
    """Reject old shadow labels before invoking the unchanged allocation math."""
    from proworksim.experience_allocation_v035 import allocation_gate
    from proworksim.software_mapper_v036 import CLASS_ORDER, MAPPER, mapping_spec
    from proworksim.software_collaboration_v036 import member_test_specification
    gamma = declaration["gamma_identity"]
    spec_sha = digest(json_bytes(mapping_spec()))
    if (declaration["window_id"] != SUPPORT_WINDOW
            or gamma.get("gamma_version") != "software-information-v0.36"
            or gamma.get("mapper_specification") != mapping_spec()
            or gamma.get("member_test_specification") != member_test_specification()
            or any(slot["mapping_spec_id"] != MAPPER for slot in declaration["slots"])):
        raise ValueError("Only the newly declared v036 policy window may supply support")
    for entry in entries:
        rollout = entry.get("rollout")
        if rollout is None:
            continue  # Preserve an interrupted slot in the original denominator.
        mapping = entry["mapping"]
        if (rollout.get("online_scope", {}).get("method_mapper_spec_sha256") != spec_sha
                or mapping.get("mapper_spec_sha256") != spec_sha
                or mapping.get("collection_mapper_binding_matches") is not True
                or mapping.get("shadow_diagnostic_only") is not False
                or mapping.get("class_id") not in {*CLASS_ORDER, None}
                or mapping.get("status") == "mapped" and mapping.get("composition_support_eligible") is not True):
            raise ValueError("Shadow, old-rule or undeclared member-route labels cannot enter current support")
    return allocation_gate(entries, declaration, records)


def run_worker(plan_path, candidate, output):
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.online_training import tensor_tree_digest
    from proworksim.software_learning_v036 import migrate_software_owner, restore_common, validate_training_entries
    from proworksim.software_runtime_v036 import collect, window_spec
    plan = validate_plan(read_json(plan_path))
    if candidate != CANDIDATE or os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, GPU_ORDER)):
        raise ValueError("P2 admits only selected 9B on one assigned GPU")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"version": VERSION, "candidate_id": candidate, "status": "loading", "started_at": time.time(),
        "source_before": code_identity(), "plan": reference(plan_path), "rows": [],
        "new_actor_optimizer_steps": 0, "new_critic_optimizer_steps": 0,
        "fresh_technical_quiz_calls": 0, "P3_started": False}
    owner, common_dir = None, None
    write(output / "report.json", report)
    try:
        task(output, "load-selected-original-9b-common", "loading")
        sample = resources()
        write(output / "preload-resources.json", sample)
        if int(os.environ["CUDA_VISIBLE_DEVICES"]) not in [card["index"] for card in available_cards(plan, sample)]:
            raise RuntimeError("Assigned empty A100 capacity changed before loading")
        refs = plan["parent"]["references"]
        saved = read_json(checked(refs["owner"]))
        old_plan = read_json(checked(refs["plan"]))
        model_plan = read_json(checked(old_plan["prior_model_plan"]))
        owner = DeterministicCandidateActor.from_candidate(model_plan["model"], manifest=checked(model_plan["manifest"]),
            profile=model_plan["runtime_profile"], recipe=saved["recipe"], output=output / "resident")
        write(output / "software-critic-migration.json", migrate_software_owner(owner, expected_steps=None))
        common_dir = checked(refs["common"]).parent
        common = read_json(common_dir / "checkpoint.json")
        restored = restore_common(owner, common_dir)
        if (restored["state_sha256"] != common["state_tensor_digest"]
                or owner.inference_profile != saved["inference_profile"] or owner.base_identity != saved["base_identity"]
                or (owner.actor_steps, owner.critic_steps) != (3, 3)):
            raise ValueError("Require exact original learner/profile/common, never a fresh endpoint")
        report.update(status="collecting", initial_actor_steps=3, initial_critic_steps=3,
                      common_actor_identity=owner.freeze_identity(), execution_binding_passed=True)
        write(output / "initial-common-restore.json", restored)
        write(output / "inherited-common.json", {
            "common": refs["common"], "state_tensor_digest": restored["state_sha256"],
            "training_rng_sha256": restored["rng_sha256"], "actor_identity": restored["actor_identity"],
            "actor_steps": restored["actor_steps"], "critic_steps": restored["critic_steps"],
            "rng_definition": "tensor_tree_digest({rng_cpu: actual_bundle[rng_cpu], rng_cuda: actual_bundle[rng_cuda]})",
            "scope": "Actual full common restoration before P2; this binds RNG tensors, not the checkpoint-file digest",
        })
        def on_slot(event, row, folder):
            if event == "closed":
                report["rows"] = observe_rows(output, plan["inventories"]["support"])
                write(output / "report.json", report)
        entries = collect(owner, window_spec(SUPPORT_WINDOW, plan["inventories"]["support"], "policy_training"),
                          output / "collection", output, common_dir=common_dir, on_slot=on_slot)
        task(output, "bind-current-original-token-material", "boundary")
        declaration = read_json(output / "collection/declaration.json")
        records = read_json(output / "collection/records.json")
        proof = validate_training_entries(owner, entries, declaration,
            request_evidence_root=output / "collection", require_open_window=False)
        write(output / "training-material-binding.json", proof)
        gate = current_support_gate(entries, declaration, records)
        write(output / "support-gate.json", gate)
        report.update(status="complete", support_status=gate["status"],
            training_material_binding=reference(output / "training-material-binding.json"),
            support_gate=reference(output / "support-gate.json"), common_restored_exactly=True)
    except BaseException as error:
        report.update(status="execution_error", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        report["rows"] = observe_rows(output, plan["inventories"]["support"])
        if owner is not None and common_dir is not None and owner.phase == "idle" and not owner.busy:
            task(output, "final-original-complete-common-restore", "boundary")
            restored = restore_common(owner, common_dir)
            write(output / "final-common-restore.json", restored)
            report.update(common_restored_exactly=restored["complete_state_exact"],
                          final_state_tensor_digest=tensor_tree_digest(owner._state_bundle(), owner.torch))
        if owner is not None:
            report.update(actor_steps=owner.actor_steps, critic_steps=owner.critic_steps,
                          final_actor_identity=owner._make_identity())
        declaration_path = output / "collection/declaration.json"
        if declaration_path.exists() and not (output / "support-gate.json").exists():
            declaration = read_json(declaration_path)
            entries = read(output / "collection/entries.json") or []
            records = read(output / "collection/records.json") or []
            full_entries, full_records = retained_inventory(entries, records, declaration, report["rows"])
            write(output / "support-gate.json", current_support_gate(full_entries, declaration, full_records))
            report["support_gate"] = reference(output / "support-gate.json")
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
                        if not waiting or len(active) >= 1:
                            break
                        if now - stable[card["index"]] < LIMITS["gpu_capacity_stability_seconds"]:
                            continue
                        validate_plan(plan)
                        c = waiting.pop(0)
                        folder = root / c
                        folder.mkdir(exist_ok=True)
                        argv = [sys.executable, "-m", "scripts.software_support_v036", "worker", "--plan", str(root / "plan.json"),
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
                    with ThreadPoolExecutor(max_workers=1) as pool:
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





def results(plan, root):
    root = Path(root)
    supervisor = read_json(root / "supervisor.json")
    state = supervisor["states"][CANDIDATE]
    actual = root / CANDIDATE / "actual"
    observed = observe_rows(actual, plan["inventories"]["support"])
    progress = actual / "collection/progress.json"
    progress_ref = reference(progress) if progress.exists() else None
    rows = []
    for index, slot in enumerate(plan["inventories"]["support"]):
        original_row = observed[index] if index < len(observed) else {}
        compact = selected.compact_row(original_row, slot, progress_ref, index)
        compact.update(mapping_status=original_row.get("mapping_status"), method_class=original_row.get("method_class"),
                       training_eligible=original_row.get("training_eligible"))
        rows.append(compact)
    worker = read(actual / "report.json") or {}
    gate = read(actual / "support-gate.json")
    material = read(actual / "training-material-binding.json")
    trusted = (state["status"] == "complete" and worker.get("status") == "complete"
        and worker.get("common_restored_exactly") is True and worker.get("execution_binding_passed") is True
        and worker.get("source_before") == worker.get("source_after") == plan["source"]
        and all(worker.get(key) == 3 for key in ("initial_actor_steps", "initial_critic_steps", "actor_steps", "critic_steps"))
        and worker.get("final_actor_identity") == plan["parent"]["common_actor_identity"]
        and worker.get("new_actor_optimizer_steps") == worker.get("new_critic_optimizer_steps") == 0
        and len(observed) == SUPPORT_M and all(selected.known(row) and selected.usage_known(row) for row in rows)
        and material is not None)
    terminal = state["status"] in TERMINAL
    if not terminal:
        decision = "collecting_fixed_inventory"
    elif not trusted or gate is None or gate.get("status") == "incomplete_keep_original_inventory":
        decision = "technical_unknown_no_support_freeze"
    elif gate["status"] == "ready_for_postcollection_freeze":
        decision = "ready_for_postcollection_freeze"
    else:
        decision = "finite_window_no_configurable_support"
    support = (gate or {}).get("supports_by_xi") or {}
    blocks = {xi: {member: {key: block[key] for key in (
        "M", "n_positive", "v", "n_by_class", "b", "candidate_counts_before_support",
        "eligible_slots", "base_actor_mask", "composition_degrees_of_freedom", "diagnostics")}
        for member, block in value["blocks"].items()} for xi, value in support.items()}
    prospective = None
    if decision == "ready_for_postcollection_freeze":
        xi, member = gate["selected_block"]
        block = blocks[xi][member]
        n, k = block["n_positive"], len(block["b"])
        unique = 1 + 2 * (n - 1) + 2 * (k - 1)
        prospective = {"n_positive": n, "K": k, "unique_trial_updates": unique,
            "development_episodes": unique * len(plan["inventories"]["development"]),
            "formal_updates": 3, "independent_confirmation_episodes": 3 * len(plan["inventories"]["confirmation"]),
            "frozen_or_executed": False, "measured_window_update_seconds": None}
    intervals, cost_rows = [], []
    if state.get("attempted") and state.get("ended_at") is not None:
        intervals.append(GpuInterval(state["gpu"], round(state["started_at"] * 1_000_000), round(state["ended_at"] * 1_000_000)))
        cost_rows.append({"gpu": state["gpu"], "pid": state["pid"], "started_at": state["started_at"],
            "ended_at": state["ended_at"], "worker_gpu_seconds": state["elapsed_gpu_seconds"],
            "controller_to_assignment_seconds": state["started_at"] - supervisor["started_at"]})
    usage = [row for row in rows if selected.usage_known(row)]
    material_keys = ("original_slot_count", "admitted_decisions", "admitted_input_tokens", "admitted_own_output_tokens",
                     "maximum_actual_sequence_tokens", "sum_actual_sequence_tokens", "by_member", "exclusion_counts", "normalization")
    actual_freeze = read(root / "postcollection-freeze.json")
    p3 = read(root / "p3-supervisor.json")
    cost_review = read(root / "shared-B-cost-review.json")
    next_status = decision
    if actual_freeze:
        next_status = "actual_inventory_frozen_waiting_shared_B"
        if prospective:
            prospective["frozen_or_executed"] = True
            prospective["measured_window_update_seconds"] = (cost_review or {}).get("measured_B_complete_material_update_seconds")
    if p3:
        next_status = "P3_" + p3["stage"] + "_" + p3["status"]
    return {"version": VERSION, "generated_at": time.time(), "status": supervisor["status"], "source": plan["source"],
        "plan": reference(root / "plan.json"), "supervisor": reference(root / "supervisor.json"),
        "candidate_id": CANDIDATE, "original_common_steps": 3, "common_is_fresh_base": False,
        "rows": rows, "known_results": sum(selected.known(row) for row in rows),
        "complete_successes": sum(selected.known(row) and row["R"] == 1 for row in rows),
        "submitted": sum(row["submitted"] is True for row in rows), "not_submitted": sum(row["submitted"] is False for row in rows),
        "support_status": (gate or {}).get("status", "not_available"),
        "member_support_states": (gate or {}).get("member_support_states", {}), "support_blocks": blocks,
        "selected_block": (gate or {}).get("selected_block"),
        "support_gate": reference(actual / "support-gate.json") if gate else None,
        "training_material": {key: material[key] for key in material_keys} if material else None,
        "training_material_binding": reference(actual / "training-material-binding.json") if material else None,
        "inherited_common": reference(actual / "inherited-common.json") if (actual / "inherited-common.json").exists() else None,
        "raw_entries": reference(actual / "collection/entries.json") if (actual / "collection/entries.json").exists() else None,
        "declaration": reference(actual / "collection/declaration.json") if (actual / "collection/declaration.json").exists() else None,
        "sampling_usage": {"known_usage_slots": len(usage), **{key: sum(row["recorded_usage"][key] for row in usage)
                          for key in ("decisions", "attempts", "charged_tokens", "test_runs")}},
        "worker_trusted_and_common_restored": trusted,
        "cost": {"current_stage_worker_gpu_seconds": sum(row["worker_gpu_seconds"] for row in cost_rows),
            "current_running_gpu_seconds": supervisor.get("running_gpu_seconds", 0),
            "current_stage_worker_interval_union": interval_accounting(intervals, [])["totals"]["worker_union"],
            "worker_intervals": cost_rows, "historical_costs_added": False,
            "queue_wait_is_GPU_cost": False},
        "next_stage": {"status": next_status, "support_gate_decision": decision,
            "prospective_actual_inventory": prospective,
            "postcollection_freeze_before_contribution_required": True,
            "automatic_execution": bool(actual_freeze and actual_freeze.get("automatic_execution")),
            "actual_postcollection_freeze": reference(root / "postcollection-freeze.json") if actual_freeze else None,
            "common_B_real_consumption_checked": cost_review is not None,
            "gradient_or_update_identifiability_checked": cost_review is not None,
            "P3_started": bool(p3 and any(s.get("attempted") for s in p3["states"].values())),
            "common_B_requires_real_probability_and_full_backward": True},
        "optimizer_updates_during_P2": 0, "scope": plan["scope"],
        "history": "P1 carrier choice and old diagnostic results are inherited without replay or relabeling; no historical development record becomes training material."}


def report(run_root, output_dir):
    root, output = Path(run_root).resolve(), Path(output_dir).resolve()
    value = results(read_json(root / "plan.json"), root)
    output.mkdir(parents=True, exist_ok=True)
    write(output / "software-support-v036.json", value)
    lines = ["# v0.36 P2 固定当前策略支持窗口", "",
        f"状态：`{value['status']}`；支持门：`{value['support_status']}`；源码：`{value['source']['code_commit']}`；原件：`{root}`。", "",
        "仅使用已选9B原完整3/3 common及v036成员自测反馈／Γ（原v034容量与去重算法保持）；这不是fresh base。沿用原训练用途根目标、一个精确情境、固定member_a先手和16个事前seed。每例共同128决定／128尝试／500000 token／32 tests；不采到成功或两类才停止。", "",
        "P2只采集，不执行参数更新、贡献开发或独立确认。新来源与用途隔离，P1／历史开发记录未改标为训练；没有重复GPU资格、16K压力或用完即丢的生产诊断更新。", "",
        "| 槽 | seed | 状态 | 完整R | 提交 | Mapper状态 | 方法 | 实际tokens |",
        "|---|---:|---|---:|---|---|---|---:|"]
    for row in value["rows"]:
        lines.append(f"| {row['slot_id']} | {row['sampling_seed']} | {row['status']} | {row['R']} | {row['submitted']} | {row['mapping_status']} | {row['method_class']} | {row['recorded_usage']['charged_tokens']} |")
    lines += ["", f"完整成功：{value['complete_successes']}/{value['known_results']} 已知；提交 {value['submitted']}，未提交 {value['not_submitted']}。未知／未开始不填零，未提交内容不补验。", "",
        "| 精确情境 | 成员 | 原M | n+ | v | 类频数 | b | 状态 |", "|---|---|---:|---:|---:|---|---|---|"]
    for xi, members in value["support_blocks"].items():
        for member, block in members.items():
            lines.append(f"| {xi} | {member} | {block['M']} | {block['n_positive']} | {block['v']:.6f} | {block['n_by_class']} | {block['b']} | {value['member_support_states'].get(member)} |")
    material = value["training_material"]
    if material:
        lines += ["", f"原始可用训练材料：{material['admitted_decisions']} 条本人决定、{material['admitted_input_tokens']} 输入token、{material['admitted_own_output_tokens']} 本人输出目标token；最大真实序列 {material['maximum_actual_sequence_tokens']} token，总输入＋输出序列规模 {material['sum_actual_sequence_tokens']}。",
            "这只是静态真实材料规模，不是一次完整更新耗时。训练输入必须与原selected请求及原input IDs一致，目标仅为本人原output IDs与行为概率；不补回被公开反馈投影删除的信息。"]
    lines += ["", f"后续状态：`{value['next_stage']['status']}`；首合格成员块：`{value['selected_block']}`。",
        "无支持、只有一类、多类频数不足与形式自由度存在但梯度尚未验证分别记录。全部原16槽保持基础分母，可信失败／unmapped／低频及未选成员维持基础损失，不删样本后重新平均。", "",
        f"按当前n+/K计算的条件化后继规模：`{value['next_stage']['prospective_actual_inventory']}`。",
        "任何贡献反馈前还须另冻类内核、完整探测方向与步长、唯一试训表、共同B复用、正式更新和公平预算。事前面板是4贡献根目标×4seed与另4确认根目标×4seed；P2未执行。真实概率／目标消费及完整反传合并进共同B试训。已有静态分配自由度不等于梯度或配置效果已可辨识。", "",
        "分配接口逐字复用v035绑定及既有logN、历史／覆盖双KL和B/G-raw/I-P求解器；不改数值更新，不把旧G-lift冒称G-raw。", "",
        f"本阶段已闭合worker成本 {value['cost']['current_stage_worker_gpu_seconds']:.6f} GPU秒；运行中 {value['cost']['current_running_gpu_seconds']:.6f}秒。排队等待、旧阶段成本及CPU开发未叠成新采样GPU成本；未据P1采样时长承诺完整P3工时。", "",
        "本P2报告不构成训练收益、分配增量或独立确认结论。用户已明确批准条件自动推进：支持合格后先冻完整实际清单，再共同B核验，随后全方向与正式／确认。未冻结P3不会启动；正式B/G/I从同一完整common出发，试训不得累加。实际后继状态另见software-allocation-v036报告。", ""]
    (output / "software-support-v036.md").write_text("\n".join(lines))
    return value


def finish(plan_path, run_root, report_repo, *, publish=False):
    plan_path, run_root, report_repo = (Path(p).resolve() for p in (plan_path, run_root, report_repo))
    if run_root.exists():
        raise FileExistsError("Do not retry or append a previously started P2 support window")
    path = run_root.parent / (run_root.name + "-finish.json")
    state = {"version": VERSION, "status": "supervising", "started_at": time.time(), "run_root": str(run_root)}
    write(path, state)
    process = subprocess.run([sys.executable, "-m", "scripts.software_support_v036", "supervise", "--plan", str(plan_path),
                              "--run-root", str(run_root)], cwd=SOURCE, check=False)
    state["supervisor_exit_code"] = process.returncode
    if not (run_root / "supervisor.json").exists():
        state.update(status="failed_before_run_archive", ended_at=time.time())
        write(path, state)
        return state
    support_result = report(run_root, report_repo / "docs/experiments")
    state["status"] = "reported"
    write(path, state)
    if publish:
        if subprocess.check_output(["git", "branch", "--show-current"], cwd=report_repo, text=True).strip() != "main":
            state["publish_status"] = "repository_branch_changed"
        else:
            subprocess.run(["git", "add", "--", *REPORT_PATHS], cwd=report_repo, check=True)
            change = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *REPORT_PATHS], cwd=report_repo).returncode
            if change == 1:
                subprocess.run(["git", "commit", "--only", "-m", "docs: archive v036 revised-relation current-policy support window", "--", *REPORT_PATHS], cwd=report_repo, check=True)
            elif change != 0:
                raise RuntimeError("Cannot inspect the fixed v036 report paths")
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
    if support_result["next_stage"]["status"] == "ready_for_postcollection_freeze":
        from scripts.freeze_software_allocation_v036 import freeze
        from scripts.software_allocation_v036 import report as allocation_report, REPORT_PATHS as ALLOCATION_REPORT_PATHS
        p3_exception = None
        try:
            actual = freeze(run_root, run_root / "postcollection-freeze.json")
            state.update(status="conditional_P3_started", postcollection_freeze=reference(run_root / "postcollection-freeze.json"),
                         actual_inventory=actual["actual_inventory"])
            write(path, state)
            allocation_report(run_root, report_repo / "docs/experiments")
            child = subprocess.run([sys.executable, "-m", "scripts.software_allocation_v036", "supervise",
                                    "--run-root", str(run_root)], cwd=SOURCE, check=False)
            state["P3_exit_code"] = child.returncode
        except BaseException as error:
            p3_exception = error
            state.update(status="P3_preparation_or_execution_error", error={"type": type(error).__name__, "message": str(error)})
            raise
        finally:
            try:
                final = allocation_report(run_root, report_repo / "docs/experiments")
                report(run_root, report_repo / "docs/experiments")
                state["P3_status"] = final["status"]
                if p3_exception is None:
                    state["status"] = "reported_P3_terminal"
                if publish:
                    state["P3_publication"] = publish_report_paths(report_repo, [*REPORT_PATHS, *ALLOCATION_REPORT_PATHS],
                        "docs: archive v036 frozen allocation and local confirmation outcome")
            except BaseException as reporting_error:
                state["P3_reporting_error"] = {"type": type(reporting_error).__name__, "message": str(reporting_error)}
                if p3_exception is None:
                    state["status"] = "P3_reporting_error"
            finally:
                state["ended_at"] = time.time()
                write(path, state)
    else:
        state["conditional_P3_not_started_reason"] = support_result["next_stage"]["status"]
    state["ended_at"] = time.time()
    write(path, state)
    return state


def publish_report_paths(repo, paths, message):
    """Publish only this run's explicit report paths under the user's standing authorization."""
    if subprocess.check_output(["git", "branch", "--show-current"], cwd=repo, text=True).strip() != "main":
        return {"status": "repository_branch_changed"}
    subprocess.run(["git", "add", "--", *paths], cwd=repo, check=True)
    change = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *paths], cwd=repo).returncode
    if change == 1:
        subprocess.run(["git", "commit", "--only", "-m", message, "--", *paths], cwd=repo, check=True)
    elif change != 0:
        raise RuntimeError("Cannot inspect declared report paths")
    env = {k: v for k, v in os.environ.items() if k.lower() not in {"http_proxy", "https_proxy", "all_proxy"}}
    attempts = []
    for index in range(3):
        result = subprocess.run(["git", "push", "origin", "main"], cwd=repo, env=env, capture_output=True, text=True, timeout=90)
        attempts.append({"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode == 0:
            break
        if index < 2:
            time.sleep(10)
    return {"status": "pushed" if attempts[-1]["returncode"] == 0 else "push_failed", "attempts": attempts,
            "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()}





def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "worker", "supervise", "report", "finish"])
    for name in ("data-root", "cpu-qualification", "plan", "run-root", "output", "report-repo"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--candidate", choices=CANDIDATES)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    required = {"prepare": ("data_root", "cpu_qualification", "output"), "worker": ("plan", "candidate", "output"),
                "supervise": ("plan", "run_root"), "report": ("run_root", "output"),
                "finish": ("plan", "run_root", "report_repo")}
    if any(getattr(args, key) is None for key in required[args.mode]):
        parser.error(args.mode + " requires " + ", ".join(required[args.mode]))
    def interrupted(signum, frame):
        raise KeyboardInterrupt("P2 support collection received signal " + str(signum))
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
