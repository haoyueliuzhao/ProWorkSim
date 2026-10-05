"""A frozen four-slot T feasibility window for new v034 roots.

The established shared-team budget, scheduler closure rules, durable archival,
permission gates and exact learning/RNG restore remain in force. New source
material and exact-contract presentation have separately frozen identities.
"""
import copy
from pathlib import Path
import time

from .audit import code_identity
from .episode import begin_episode, finish_episode
from .experience import capture_port
from .harness_port import HarnessPort
from .harness_runtime import SDKStaffRuntime
from .online_collection import _config
from .online_support import declare_window
from .scenarios import ScenarioController
from .software_collaboration_v034 import (
    CASE_IDS, INTERFACE_REVISION, PURPOSE, SCHEDULER, TEAM_LIMITS, PUBLIC_FEEDBACK_VERSION,
    VERSION as INTERFACE_VERSION, SoftwareCollaborationPort,
    assess_software_collaboration, build_software_collaboration_case,
    case_spec, prove_initial_team, validate_case,
)
from .software_context_v034 import CAPACITY_ERROR, VERSION as CONTEXT_VERSION
from .software_runtime_v033 import (
    TERMINAL, TECHNICAL_FAILURES, SDK_CONTEXT_SELECTION,
    _append, _StreamList, _StreamRecorder, _decisions, _capture_slot_guard,
    budget_snapshot, availability, close_runtime, _new_events, _terminal_detail,
)
from .storage import atomic_write, digest, json_bytes
from .team_budget_v033 import SharedTeamBudget

VERSION = "software-runtime-v0.34"
DIAGNOSTICS = "new-root-development-process-diagnostics-v0.34"
MODE = "frozen_new_root_feasibility"
SAMPLING_SEEDS = (202610060701, 202610060702)


def situation_id(case):
    return case["case_id"] + "::condition=T::active=" + ",".join(case["active_roles"]) + "::first=" + case["first_member"]


def build_runtime(owner, prepared, folder, harness="openhands_v16"):
    """Existing SDK construction with durable event/capture sinks, no sampling."""
    if harness != "openhands_v16":
        raise ValueError("The software protocol fixes the existing OpenHands SDK harness")
    validate_case(prepared.case)
    if tuple(owner.recipe.get("members", ())) != ("member_a", "member_b", "software_inactive"):
        raise ValueError("Screening owners must use the frozen software member/critic coordinate binding")
    from .harness_sdk import HarnessWorker

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    before = prepared.world.store.load()
    recorder = _StreamRecorder(folder / "experience.jsonl")
    captured, policies, ports, interfaces, holder = {}, {}, {}, {}, {}
    team_budget = SharedTeamBudget(members=prepared.case["active_roles"], team_id=owner.window_id,
        **{key: TEAM_LIMITS[key] for key in ("max_decisions", "max_attempts", "max_total_tokens")})
    prepared.world.model_budget_snapshot = team_budget.snapshot
    for role in prepared.scenario["roles"]:
        member = role["role_id"]
        interface = SoftwareCollaborationPort(prepared.world.session(role["actor"], role["project"]), member)
        interfaces[member] = interface
        rows = _StreamList(folder / "public-capture" / (member + ".jsonl"))
        captured[member] = rows
        base = capture_port(interface, rows)
        config = _config(owner, member, role["config"]["task"], prepared.case["role_decision_limits"])
        config["context_policy"] = "full_history"
        config["format_error_policy"] = "format_feedback_budgeted_v033"
        ports[member] = HarnessPort(base, member, project_id=role["project"],
            public_sink=lambda kind, value, member=member: recorder.record(kind, value, worker_id=member),
            world_sink=lambda payload, association, member=member: holder["runtime"].record_world_call(member, payload, association),
            harness_sink=lambda payload, association, member=member: holder["runtime"].record_harness_call(member, payload, association))
        policies[member] = HarnessWorker(member, ports[member].tools(), config,
            transport=owner.transport, team_budget=team_budget,
            execute=lambda name, arguments, association, member=member: holder["runtime"].execute(member, name, arguments, association),
            event_sink=lambda kind, value, member=member: recorder.record(kind, value, worker_id=member),
            directory=folder / "sdk-conversations" / member, context_selection=SDK_CONTEXT_SELECTION)
        role.update(policy="model", config=copy.deepcopy(policies[member].config))
    runtime = SDKStaffRuntime(ports, policies, recorder=recorder)
    runtime.team_budget = team_budget
    holder["runtime"] = runtime
    # Keep member identity/order fixed; the cursor selects the declared first turn.
    runtime.cursor = list(prepared.case["active_roles"]).index(prepared.case["first_member"])
    prepared.world.runtime_availability = lambda: availability(runtime, prepared.case)
    if (any(event["kind"] in {"model_call", "tool_call"} for event in recorder.events)
            or prepared.world.store.load() != before):
        close_runtime(runtime)
        raise ValueError("SDK construction must not sample or change the software world")
    recorder.events.clear()
    recorder.enabled = True
    for rows in captured.values():
        rows.clear()
        rows.enabled = True
    return runtime, captured, interfaces


def run_fragment(prepared, runtime, *, on_opportunity=None):
    """Fair opportunities among runnable roles; one shared pool, no 64/64 split."""
    case = validate_case(prepared.case)
    controller = ScenarioController(prepared.deployment, recorder=runtime.recorder)
    controller.record_environment()
    waiting, stopped, outcomes, details = {}, {}, [], {}
    runtime.cursor = list(runtime.labels).index(case["first_member"])
    prepared.world.runtime_availability = lambda: availability(runtime, case)
    integrity_failure = None
    while True:
        snapshot = runtime.team_budget.snapshot()
        if snapshot.get("integrity_failure"):
            integrity_failure = snapshot["integrity_failure"]
            break
        exhausted = [key for key in ("remaining_decisions", "remaining_attempts", "available_tokens") if snapshot[key] <= 0]
        if exhausted:
            for member in set(case["active_roles"]) - set(stopped):
                stopped[member] = "team_budget_exhausted"
                details[member] = {"status": "team_budget_exhausted", "cause": "shared_team_pool_exhausted",
                                   "limits": exhausted, "member_decisions": _decisions(runtime, member)}
                runtime.roles[member].update(status="team_budget_exhausted", software_retired=True)
            waiting.clear()
            break
        for member in list(waiting):
            events = _new_events(prepared, member, waiting[member])
            if events:
                del waiting[member]
                runtime.roles[member].update(status="ready", reason="New reachable work event")
                runtime.recorder.record("role_reactivated", {"event_sequences": [event["sequence"] for event in events],
                    "decisions_already_consumed": _decisions(runtime, member),
                    "shared_remaining_decisions": snapshot["remaining_decisions"], "budget_reset": False}, worker_id=member)
        runnable = set(case["active_roles"]) - set(stopped) - set(waiting)
        if not runnable:
            break
        member = runtime.labels[runtime.cursor % len(runtime.labels)]
        if member not in runnable:
            runtime.cursor += 1
            continue
        first_event = len(runtime.recorder.events)
        result = runtime.step()
        if result["status"] == "model_service_error" and not result.get("action_performed"):
            attempts = [event for event in runtime.recorder.events[first_event:] if event["kind"] == "model_attempt"
                        and event.get("worker_id") == member and event["payload"].get("stage") == "finished"]
            last = attempts[-1] if attempts else None
            body = last["payload"].get("response", {}).get("body", {}) if last else {}
            if (isinstance(body, dict) and body.get("transport_kind") == CONTEXT_VERSION
                    and body.get("generation_started") is False and body.get("error", {}).get("code") == CAPACITY_ERROR):
                result = {**result, "original_status": result["status"], "status": "model_budget_exhausted", "budget_kind": "context_capacity"}
                runtime.roles[member].update(status="model_budget_exhausted", reason="Declared context capacity exhausted before generation")
                runtime.recorder.record("software_context_capacity_boundary", {
                    "source_attempt_sequence": last["sequence"], "error": body["error"],
                    "raw_sdk_status": "model_service_error", "status": "model_budget_exhausted",
                    "model_generation_started": False, "context_projection": body["context_projection"]}, worker_id=member)
        outcomes.append(result)
        controller.record_environment()
        status = result["status"]
        rejection_code = (result.get("response") or {}).get("error", {}).get("rejection", {}).get("code")
        if rejection_code in {"world_power_denied", "project_power_denied", "trusted_context_override"}:
            result = {**result, "original_status": status, "status": "model_permission_error",
                      "reason": "Trusted WorldCore permission/context boundary: " + rejection_code}
            outcomes[-1] = result
            status = result["status"]
            runtime.roles[member]["status"] = status
            runtime.recorder.record("critical_permission_boundary", {"code": rejection_code,
                "original_status": result["original_status"], "status": status}, worker_id=member)
        fatal = status in TECHNICAL_FAILURES and not (status == "policy_error" and result.get("action_performed"))
        if fatal:
            stopped[member] = status
            details[member] = _terminal_detail(member, result, runtime, runtime.recorder.events[first_event:])
            runtime.roles[member]["software_retired"] = True
            integrity_failure = {"member": member, "status": status, "reason": result.get("reason")}
        elif status in TERMINAL - {"policy_error", "model_format_error"}:
            stopped[member] = status
            details[member] = _terminal_detail(member, result, runtime, runtime.recorder.events[first_event:])
            runtime.roles[member]["software_retired"] = True
        elif status in {"worker_waiting", "world_blocked"}:
            events = prepared.world.store.load().get("software_events", [])
            waiting[member] = events[-1]["sequence"] if events else 0
            runtime.recorder.record("role_suspended", {"after_event_sequence": waiting[member],
                "decisions_already_consumed": _decisions(runtime, member)}, worker_id=member)
        if on_opportunity:
            on_opportunity(result)
        if integrity_failure is not None:
            break
    for member, sequence in waiting.items():
        details[member] = {"status": runtime.roles[member]["status"], "cause": "no_reachable_wake_event",
            "reason": runtime.roles[member].get("reason"), "waiting_after_event_sequence": sequence,
            "member_decisions": _decisions(runtime, member)}
    status = ("execution_integrity_blocked" if integrity_failure is not None else "blocked_no_reachable_events" if waiting
              else "workers_done" if stopped and all(value == "completed" for value in stopped.values())
              else "bounded_work_closed")
    boundary = {"status": status, "kind": "same_root_diagnostic_terminal", "scheduling_protocol": SCHEDULER,
        "first_member": case["first_member"], "role_stops": stopped, "waiting_members": copy.deepcopy(waiting),
        "outcomes": outcomes, "terminal_details": details, "closure_reason": "execution_integrity_failure" if integrity_failure else "no_runnable_members",
        "execution_integrity_failure": integrity_failure, "opportunities": runtime.opportunities,
        "actions": runtime.actions, "team_budget": budget_snapshot(runtime, prepared), "continuation": False, "bootstrap": 0,
        "scope": "No extra per-member 64-decision or ordinary format-error retirement cap; all real attempts share the declared episode pool. Closure does not imply delivery success."}
    runtime.recorder.record("run_boundary", boundary)
    return boundary


def inventory():
    rows = []
    for index, seed in enumerate(SAMPLING_SEEDS):
        cases = CASE_IDS if index == 0 else tuple(reversed(CASE_IDS))
        for case_id in cases:
            label = "directory" if case_id == CASE_IDS[0] else "names"
            first = "member_a" if index == 0 else "member_b"
            case = case_spec(case_id, first_member=first)
            rows.append({"slot_id": f"p1-{index}-{label}-T", "case_id": case_id, "condition": "T",
                "sampling_seed": seed, "first_member": first,
                "role_decision_limits": case["role_decision_limits"], "team_limits": copy.deepcopy(TEAM_LIMITS)})
    return rows


def window_spec(window_id, rows=None):
    selected = inventory() if rows is None else copy.deepcopy(rows)
    return {"window_id": window_id, "harness": "openhands_v16", "usage": PURPOSE, "mode": MODE,
            "min_class_count": 2, "slots": selected,
            "budget": {"max_slots": len(selected), "max_model_calls": len(selected) * TEAM_LIMITS["max_attempts"]}}


def _validate_window(spec):
    if (not isinstance(spec, dict) or not isinstance(spec.get("window_id"), str) or not spec["window_id"]
            or spec != window_spec(spec["window_id"])):
        raise ValueError("Freeze exactly the four new T slots, order, seeds, first members and shared limits")
    return spec["slots"]


def collect_software_window(owner, window_spec, output_dir, *, on_slot=None):
    """Freeze a complete declared purpose-specific window; export every attempt."""
    rows = _validate_window(window_spec)
    if owner.window_id != window_spec["window_id"]:
        raise ValueError("Current owner must enter this exact software window before collection")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    atomic_write(output / "window-spec.json", json_bytes(window_spec))
    identity, items = owner.freeze_identity(), []
    try:
        for index, row in enumerate(rows):
            folder = output / f"slot-{index}"
            prepared = build_software_collaboration_case(case_spec(row["case_id"],
                condition=row["condition"], first_member=row["first_member"],
                role_decision_limits=row["role_decision_limits"]), folder)
            runtime, captured, interfaces = build_runtime(owner, prepared, folder)
            runtime.slot_id = row["slot_id"]
            scenario = copy.deepcopy(prepared.scenario)
            scenario.setdefault("variation", {})["software_case"] = copy.deepcopy(prepared.case)
            scenario["variation"]["software_runtime"] = {
                "version": VERSION, "harness": "openhands_v16", "source_usage": window_spec["usage"],
                "collection_mode": window_spec["mode"],
                "interface_revision": INTERFACE_REVISION, "sdk_context_selection": SDK_CONTEXT_SELECTION,
                "context_policy": getattr(owner, "software_context_policy", "latest_observation_last4_tool_rounds"),
                "presentation_version": CONTEXT_VERSION, "public_test_feedback_version": PUBLIC_FEEDBACK_VERSION,
                "profile_bindings": {member: interface.profile for member, interface in interfaces.items()},
                "external_tick_per_sweep": 0, "first_member": prepared.case["first_member"],
                "scheduling_protocol": SCHEDULER,
                "role_decision_limits": copy.deepcopy(prepared.case["role_decision_limits"]),
                "condition": prepared.case["condition"], "team_limits": copy.deepcopy(TEAM_LIMITS),
                "active_roles": list(prepared.case["active_roles"]), "category": prepared.case["category"]}
            initial = {"case": prepared.case, "reward_spec": prepared.reward_spec,
                       "initial_business_sha256": prepared.prefix["prepared_business_state_sha256"]}
            spec = {"slot_id": row["slot_id"], "xi_id": situation_id(prepared.case),
                    "xi_fingerprint": digest(json_bytes(initial)), "active_members": list(prepared.case["active_roles"]),
                    "policies": runtime.policy_identities, "mapping_spec_id": DIAGNOSTICS}
            items.append({"row": row, "folder": folder, "prepared": prepared, "runtime": runtime,
                          "captured": captured, "scenario": scenario, "slot_spec": spec, "closed": False})
            atomic_write(folder / "model-scenario.json", json_bytes(scenario))
        proofs = [{"slot_id": item["row"]["slot_id"], **prove_initial_team(item["prepared"])} for item in items]
        atomic_write(output / "initial-team-proofs.json", json_bytes(proofs))
        executing = items
        execution_budget = copy.deepcopy(window_spec["budget"])
        gamma = {"collection_version": VERSION, "harness": "openhands_v16", "interface": INTERFACE_VERSION,
                 "source": code_identity(), "source_usage": window_spec["usage"],
                 "collection_mode": window_spec["mode"], "recipe": copy.deepcopy(owner.recipe),
                 "interface_revision": INTERFACE_REVISION, "sdk_context_selection": SDK_CONTEXT_SELECTION,
                 "presentation_version": CONTEXT_VERSION, "public_test_feedback_version": PUBLIC_FEEDBACK_VERSION,
                 "context_projection": getattr(owner, "software_context_policy", "latest_observation_last4_tool_rounds"),
                 "external_tick_per_sweep": 0,
                 "scheduling_protocol": SCHEDULER, "budget": execution_budget,
                 "slot_sampling_seeds": {item["row"]["slot_id"]: item["row"]["sampling_seed"] for item in executing},
                 "fixed_slot_cases": [item["slot_spec"]["xi_fingerprint"] for item in executing],
                 "optimizer_update_allowed": False, "method_classification_performed": False,
                 "support_computation_performed": False, "min_class_count_has_research_meaning": False}
        declaration = declare_window(window_spec["window_id"], actor_identity=identity, gamma_identity=gamma,
                                     slot_specs=[item["slot_spec"] for item in executing], min_class_count=window_spec["min_class_count"])
        atomic_write(output / "declaration.json", json_bytes(declaration))
        entries, summaries, records = [], [], []
        for item in executing:
            row, prepared, folder = item["row"], item["prepared"], item["folder"]
            runtime, captured = item["runtime"], item["captured"]
            if owner.freeze_identity() != identity:
                raise ValueError("Frozen software window cannot change the actor between slots")
            if on_slot:
                on_slot("started", row, folder)
            slot_guard_before = _capture_slot_guard(owner)
            slot_binding = {key: copy.deepcopy(getattr(owner, key)) for key in ("recipe", "inference_profile", "base_identity", "software_learning_binding")}
            slot_guard_closed = False
            owner.reseed(row["sampling_seed"], label=row["slot_id"])
            episode = folder / "episode"
            begin_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), work_ids=[],
                          scenario=item["scenario"], policies=runtime.policy_identities)
            started, episode_closed = time.time(), False
            try:
                def checkpoint(result):
                    _append(folder / "runtime-opportunities.jsonl", result)
                    atomic_write(folder / "runtime-state.json", json_bytes({
                        "opportunities": runtime.opportunities, "actions": runtime.actions,
                        "cursor": runtime.cursor, "availability": availability(runtime, prepared.case),
                        "team_budget": budget_snapshot(runtime, prepared)}))
                    atomic_write(folder / "team-budget.json", json_bytes(budget_snapshot(runtime, prepared)))

                boundary = run_fragment(prepared, runtime, on_opportunity=checkpoint)
                finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination=boundary)
                episode_closed = True
                close_runtime(runtime)
                item["closed"] = True
                assessment = assess_software_collaboration(prepared, run_root=folder / "private-assessment")
                atomic_write(folder / "raw-independent-assessment.json", json_bytes(assessment))
                failures = {member: status for member, status in boundary["role_stops"].items()
                            if status in TECHNICAL_FAILURES}
                if failures or boundary.get("execution_integrity_failure"):
                    # A known file-test result is still useful diagnostic
                    # evidence, but cannot turn a failed execution boundary
                    # into an ordinary evaluable model-work failure/success.
                    assessment.update(status="unknown", R=None, content_correct=None,
                        required_process_satisfied=None, process_observation_complete=None, complete_delivery=None,
                        execution_failure={"role_stops": failures,
                            "reason": "Technical execution failed before normal bounded work closure",
                            "raw_independent_assessment_path": "raw-independent-assessment.json"})
                atomic_write(folder / "assessment.json", json_bytes(assessment))
                from .software_training_v034 import export_software_episode
                entry, evidence = export_software_episode(prepared, episode, assessment,
                    declaration=declaration, slot_id=row["slot_id"], captured=captured)
                atomic_write(folder / "software-evidence.json", json_bytes(evidence))
                atomic_write(folder / "entry.json", json_bytes(entry))
                atomic_write(folder / "team-rollout.json", json_bytes(entry["rollout"]))
                atomic_write(folder / "process-diagnostics.json", json_bytes(entry["process_diagnostics"]))
                entries.append(entry)
                if entry["reward"]["eligible"]:
                    record = {"slot_id": row["slot_id"], "status": "closed",
                              "rollout": entry["rollout"], "training_eligible": False,
                              "process_diagnostics": entry["process_diagnostics"]}
                else:
                    record = {"slot_id": row["slot_id"], "status": "closed_unassessed",
                              "episode": str(episode.resolve()),
                              "manifest_sha256": digest((episode / "manifest.json").read_bytes())}
                records.append(record)
                atomic_write(output / "entries.json", json_bytes(entries))
                atomic_write(output / "records.json", json_bytes(records))
                slot_guard = owner.finish_evaluation_guard(slot_guard_before)
                slot_guard.update(software_binding_unchanged=all(getattr(owner, key) == value for key, value in slot_binding.items()),
                                  actor_identity_unchanged=owner.freeze_identity() == identity)
                slot_guard_closed = True
                atomic_write(folder / "evaluation-guard.json", json_bytes(slot_guard))
                if not all(slot_guard[key] for key in ("learning_unchanged", "rng_restored_exactly", "software_binding_unchanged", "actor_identity_unchanged")):
                    raise ValueError("A diagnostic episode changed the frozen learner, identity, binding or RNG restoration")
                atomic_write(folder / "team-budget.json", json_bytes(budget_snapshot(runtime, prepared)))
                from scripts.run_ne_v021 import reference
                summary = {**copy.deepcopy(row),
                           "status": "closed" if assessment["status"] == "evaluable" else "execution_unknown",
                           "first_member": row["first_member"], "boundary": boundary,
                           "R": assessment["R"], "started_at": started,
                           "ended_at": time.time(), "training_eligible": False,
                           "active_members": list(prepared.case["active_roles"]), "category": prepared.case["category"],
                           "process_diagnostics": entry["process_diagnostics"],
                           "content_correct": assessment.get("content_correct"),
                           "required_process_satisfied": assessment.get("required_process_satisfied"),
                           "process_observation_complete": assessment.get("process_observation_complete"),
                           "complete_delivery": assessment.get("complete_delivery"), "submitted": assessment.get("submitted"),
                           "record_validity": entry["rollout"]["work_validity"]["components"]["record"]["value"],
                           "entry": reference(folder / "entry.json"), "assessment": reference(folder / "assessment.json"),
                           "evaluation_guard": reference(folder / "evaluation-guard.json"),
                           "team_budget": budget_snapshot(runtime, prepared)}
                summaries.append(summary)
                atomic_write(output / "progress.json", json_bytes(summaries))
                if on_slot:
                    on_slot("closed", row, folder)
                if failures or boundary.get("execution_integrity_failure") or summary["record_validity"] is not True:
                    raise ValueError("Critical execution/permission/record failure blocks the remaining diagnostic window")
            except BaseException as error:
                detail = {"type": type(error).__name__, "message": str(error),
                          "episode_closed_before_error": episode_closed, "runtime_closed": item["closed"]}
                atomic_write(folder / "interruption.json", json_bytes(detail))
                if not episode_closed:
                    finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination={
                        "status": "interrupted", "kind": "external_or_collector_failure", "error": detail,
                        "business_result": None, "continuation": False})
                if summaries and summaries[-1]["slot_id"] == row["slot_id"]:
                    summaries[-1].update(status="execution_unknown", R=None, complete_delivery=None,
                                          content_correct=None, required_process_satisfied=None, process_observation_complete=None, error=detail)
                    partial = summaries
                else:
                    partial = [*summaries, {**copy.deepcopy(row), "status": "interrupted", "R": None,
                                           "complete_delivery": None, "error": detail}]
                atomic_write(output / "progress.json", json_bytes(partial))
                raise
            finally:
                if not slot_guard_closed:
                    slot_guard = owner.finish_evaluation_guard(slot_guard_before)
                    slot_guard.update(software_binding_unchanged=all(getattr(owner, key) == value for key, value in slot_binding.items()),
                                      actor_identity_unchanged=owner.freeze_identity() == identity)
                    atomic_write(folder / "evaluation-guard.json", json_bytes(slot_guard))
                atomic_write(folder / "team-budget.json", json_bytes(budget_snapshot(runtime, prepared)))
                atomic_write(folder / "public-capture.json", json_bytes(captured))
                atomic_write(folder / "runtime.json", json_bytes(runtime.snapshot()))
        if owner.freeze_identity() != identity:
            raise ValueError("Software development collection changed the actor identity")
        atomic_write(output / "summary.json", json_bytes({"version": VERSION, "usage": window_spec["usage"],
                     "actor_identity": identity, "slots": summaries,
                     "new_episode_count": len(summaries),
                     "training_eligible": False, "optimizer_update_allowed": False,
                     "method_classification_performed": False, "support_computation_performed": False,
                     "scope": "Frozen model/interface screening only. Original member records are archived; no development record is optimizer material."}))
        atomic_write(output / "entries.json", json_bytes(entries))
        return entries
    finally:
        for item in items:
            if not item["closed"]:
                close_runtime(item["runtime"])
                item["closed"] = True


def collect(owner, spec, output, worker_output, *, common_dir=None, on_slot=None):
    """Execute the exact new four-slot inventory; restore the original common exactly."""
    from scripts.software_model_selection_v030 import CollectionOwner
    from scripts.software_development_v028 import DurableTransport, task
    from .software_context_v034 import SoftwareContextTransport
    from .online_training import tensor_tree_digest
    from .storage import read_json

    output = Path(output)
    before = owner.capture_evaluation_state()
    identity = owner.freeze_identity()
    binding = {key: copy.deepcopy(getattr(owner, key)) for key in ("recipe", "inference_profile", "base_identity", "software_learning_binding")}
    facade = CollectionOwner(owner)
    owner.begin_window(spec["window_id"])
    entries = []
    def boundary(event, row, folder):
        if event == "started":
            task(worker_output, row["slot_id"], "episode")
            directory = folder / "raw-transport"
            facade.transport.inner = DurableTransport(SoftwareContextTransport(owner, directory / "context-projections"), directory, owner.window_id)
        else:
            task(worker_output, "close-" + row["slot_id"], "boundary")
            facade.transport.inner = None
        if on_slot:
            on_slot(event, row, folder)
    try:
        entries = collect_software_window(facade, spec, output, on_slot=boundary)
        owner.finish_evaluation(entries, output / "frozen-collection-close")
    finally:
        facade.transport.inner = None
        if owner.phase == "collecting" and not owner.busy:
            owner.finish_evaluation(entries, output / "interrupted-collection-close")
        guard = owner.finish_evaluation_guard(before)
        guard.update(software_binding_unchanged=all(getattr(owner, key) == value for key, value in binding.items()),
                     actor_identity_unchanged=owner.freeze_identity() == identity)
        atomic_write(output / "evaluation-guard.json", json_bytes(guard))
        if common_dir is not None:
            task(worker_output, "restore-original-common-after-new-root-feasibility", "boundary")
            common_dir = Path(common_dir)
            common = read_json(common_dir / "checkpoint.json")
            if owner.busy or owner.phase != "idle":
                raise ValueError("A nonidle owner cannot restore the original common")
            owner.restore_checkpoint(common_dir)
            exact = tensor_tree_digest(owner._state_bundle(), owner.torch) == common["state_tensor_digest"]
            atomic_write(output / "common-restore.json", json_bytes({"checkpoint": str(common_dir / "checkpoint.json"),
                "common_restored_exactly": exact, "actor_identity": owner.freeze_identity(), "optimizer_updates": 0}))
            if not exact or owner.freeze_identity() != common["actor_identity"]:
                raise ValueError("The complete original learner/common did not restore exactly")
        if not all(guard[key] for key in ("learning_unchanged", "rng_restored_exactly", "software_binding_unchanged", "actor_identity_unchanged")):
            raise ValueError("The paired diagnostic changed learning/binding/identity or failed RNG restoration")
    return entries
