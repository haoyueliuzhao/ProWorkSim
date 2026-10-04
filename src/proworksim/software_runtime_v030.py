"""Frozen model/interface screening with dynamic active startup members.

Only the existing managed SDK executes member decisions. The controller chooses
opportunities, never tasks, edits, messages or repairs. Every raw input/output
event is appended before the next decision; committed WorldCore versions remain
in the live world and are copied into each completed/interrupted episode.
"""

import copy
import json
import os
from pathlib import Path
import time

from .audit import code_identity
from .episode import begin_episode, finish_episode
from .experience import ExperienceRecorder, capture_port
from .harness_port import HarnessPort
from .harness_runtime import SDKStaffRuntime
from .online_collection import _config
from .online_support import declare_window
from .scenarios import ScenarioController
from .software_collaboration_v030 import (
    INTERFACE_REVISION, PURPOSE, SCHEDULER, VERSION as INTERFACE_VERSION, SoftwareCollaborationPort,
    assess_software_collaboration, build_software_collaboration_case, case_spec, validate_case,
)
from .software_context_v028 import CAPACITY_ERROR, VERSION as CONTEXT_VERSION
from .storage import atomic_write, digest, json_bytes

VERSION = "software-runtime-v0.30"
DIAGNOSTICS = "software-development-process-diagnostics-v0.30"
MODE = "frozen_screening"
SDK_CONTEXT_SELECTION = "first_and_latest_observation_last4_tool_rounds"
TERMINAL = frozenset({"completed", "model_budget_exhausted", "model_service_error",
                      "model_format_error", "model_usage_missing", "binding_mismatch",
                      "environment_error", "policy_error"})
TECHNICAL_FAILURES = frozenset({"model_service_error", "model_usage_missing",
                                "binding_mismatch", "environment_error", "policy_error"})


def _append(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


class _StreamList(list):
    def __init__(self, path):
        super().__init__()
        self.path, self.enabled = path, False

    def append(self, value):
        if self.enabled:
            _append(self.path, value)
        super().append(value)

    def __deepcopy__(self, memo):
        # Evidence consumers may copy capture data; copying must never append a
        # second fabricated event to the original durable stream.
        return copy.deepcopy(list(self), memo)


class _StreamRecorder(ExperienceRecorder):
    def __init__(self, path):
        super().__init__()
        self.path, self.enabled = path, False

    def record(self, kind, payload, worker_id=None):
        event = super().record(kind, payload, worker_id)
        if self.enabled:
            _append(self.path, event)
        return event


def situation_id(case):
    """A different first opportunity is a different exact protocol situation."""
    return case["case_id"] + "::active=" + ",".join(case["active_roles"]) + "::first=" + case["first_member"]


def _decisions(runtime, member):
    worker = runtime.policies[member]
    return getattr(worker, "meter", {}).get("decisions", runtime.roles[member]["opportunities"])


def availability(runtime, case):
    result = {}
    for member in case["active_roles"]:
        status = runtime.roles[member]["status"]
        remaining = max(0, case["role_decision_limits"][member] - _decisions(runtime, member))
        retired = (runtime.roles[member].get("software_retired", False)
                   or status in TERMINAL - {"policy_error"})
        result[member] = {"status": status, "remaining_decisions": remaining,
                          "can_receive_work": not retired and remaining > 0}
    return result


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
    for role in prepared.scenario["roles"]:
        member = role["role_id"]
        interface = SoftwareCollaborationPort(prepared.world.session(role["actor"], role["project"]), member)
        interfaces[member] = interface
        rows = _StreamList(folder / "public-capture" / (member + ".jsonl"))
        captured[member] = rows
        base = capture_port(interface, rows)
        config = _config(owner, member, role["config"]["task"], prepared.case["role_decision_limits"])
        config["context_policy"] = "full_history"
        ports[member] = HarnessPort(base, member, project_id=role["project"],
            public_sink=lambda kind, value, member=member: recorder.record(kind, value, worker_id=member),
            world_sink=lambda payload, association, member=member: holder["runtime"].record_world_call(member, payload, association),
            harness_sink=lambda payload, association, member=member: holder["runtime"].record_harness_call(member, payload, association))
        policies[member] = HarnessWorker(member, ports[member].tools(), config,
            transport=owner.transport,
            execute=lambda name, arguments, association, member=member: holder["runtime"].execute(member, name, arguments, association),
            event_sink=lambda kind, value, member=member: recorder.record(kind, value, worker_id=member),
            directory=folder / "sdk-conversations" / member, context_selection=SDK_CONTEXT_SELECTION)
        role.update(policy="model", config=copy.deepcopy(policies[member].config))
    runtime = SDKStaffRuntime(ports, policies, recorder=recorder)
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


def close_runtime(runtime):
    for worker in runtime.policies.values():
        worker.close()


def _new_events(prepared, member, after):
    state = prepared.world.store.load()
    return [event for event in state.get("software_events", []) if event["sequence"] > after and (
        (event["kind"] in {"work_message", "handoff", "delegate", "task_returned"}
         and event.get("recipient") == member)
        or (event["kind"] == "patch_fixed" and event["actor_id"] != member))]


def run_fragment(prepared, runtime, *, on_opportunity=None):
    """Round robin; wait suspends, new work wakes, exhausted/done never revive."""
    case = validate_case(prepared.case)
    controller = ScenarioController(prepared.deployment, recorder=runtime.recorder)
    controller.record_environment()
    waiting, stopped, outcomes = {}, {}, []
    runtime.cursor = list(runtime.labels).index(case["first_member"])
    prepared.world.runtime_availability = lambda: availability(runtime, case)

    def refresh():
        for member in case["active_roles"]:
            role = runtime.roles[member]
            if member in stopped:
                continue
            if _decisions(runtime, member) >= case["role_decision_limits"][member]:
                role.update(status="model_budget_exhausted", reason="Frozen member decision cap reached")
                stopped[member] = "model_budget_exhausted"
                waiting.pop(member, None)
                runtime.recorder.record("role_retired", {"reason": stopped[member],
                    "decisions": _decisions(runtime, member)}, worker_id=member)
            elif member in waiting:
                events = _new_events(prepared, member, waiting[member])
                if events:
                    del waiting[member]
                    role.update(status="ready", reason="New reachable work event")
                    runtime.recorder.record("role_reactivated", {
                        "event_sequences": [event["sequence"] for event in events],
                        "decisions_already_consumed": _decisions(runtime, member),
                        "remaining_decisions": case["role_decision_limits"][member] - _decisions(runtime, member),
                        "budget_reset": False}, worker_id=member)

    while True:
        refresh()
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
            # The SDK records the original non-200 envelope as a service error.
            # Our explicitly identified pre-generation capacity boundary is a
            # finite context limit, not an inference/adapter outage. Keep that
            # original event and append the exact interpretation separately.
            attempts = [event for event in runtime.recorder.events[first_event:]
                        if event["kind"] == "model_attempt" and event.get("worker_id") == member
                        and event["payload"].get("stage") == "finished"]
            last = attempts[-1] if attempts else None
            body = last["payload"].get("response", {}).get("body", {}) if last else {}
            if (isinstance(body, dict) and body.get("transport_kind") == CONTEXT_VERSION
                    and body.get("generation_started") is False
                    and body.get("error", {}).get("code") == CAPACITY_ERROR):
                result = {**result, "original_status": result["status"],
                          "status": "model_budget_exhausted", "budget_kind": "context_capacity"}
                runtime.roles[member].update(status="model_budget_exhausted",
                    reason="Declared context capacity exhausted before generation")
                runtime.recorder.record("software_context_capacity_boundary", {
                    "source_attempt_sequence": last["sequence"], "error": body["error"],
                    "raw_sdk_status": "model_service_error", "status": "model_budget_exhausted",
                    "model_generation_started": False, "context_projection": body["context_projection"],
                }, worker_id=member)
        outcomes.append(result)
        controller.record_environment()
        status = result["status"]
        if status in TERMINAL and not (status == "policy_error" and result.get("action_performed")):
            stopped[member] = status
            runtime.roles[member]["software_retired"] = True
        elif status in {"worker_waiting", "world_blocked"}:
            events = prepared.world.store.load().get("software_events", [])
            waiting[member] = events[-1]["sequence"] if events else 0
            runtime.recorder.record("role_suspended", {"after_event_sequence": waiting[member],
                "decisions_already_consumed": _decisions(runtime, member)}, worker_id=member)
        if on_opportunity:
            on_opportunity(result)
    boundary = {
        "status": ("blocked_no_reachable_events" if waiting else "workers_done"
                   if all(value == "completed" for value in stopped.values()) else "finite_task_deadline"),
        "kind": "finite_horizon_task_terminal", "scheduling_protocol": SCHEDULER,
        "first_member": case["first_member"], "role_stops": stopped,
        "waiting_members": copy.deepcopy(waiting), "outcomes": outcomes,
        "opportunities": runtime.opportunities, "actions": runtime.actions,
        "continuation": False, "bootstrap": 0,
        "scope": "No asynchronous work or external producer exists; no runnable member means no future wake event. This terminal does not imply business success.",
    }
    runtime.recorder.record("run_boundary", boundary)
    return boundary


def _validate_window(spec):
    if not isinstance(spec, dict) or spec.get("harness") != "openhands_v16":
        raise ValueError("Declare the software SDK harness explicitly")
    if not isinstance(spec.get("window_id"), str) or not spec["window_id"]:
        raise ValueError("Declare a new software window identity")
    if set(spec) != {"window_id", "harness", "usage", "mode", "min_class_count", "budget", "slots"}:
        raise ValueError("Freeze exactly the v0.30 screening window fields")
    if spec.get("usage") != PURPOSE or spec.get("mode") != MODE:
        raise ValueError("Only model_interface_development with frozen_screening is admitted")
    slots = spec.get("slots")
    if not isinstance(slots, list) or not slots:
        raise ValueError("Predeclare every finite software slot")
    seen, calls = set(), 0
    for row in slots:
        if not isinstance(row, dict) or set(row) != {
                "slot_id", "case_id", "sampling_seed", "first_member", "role_decision_limits"}:
            raise ValueError("Each slot needs identity, case, seed, first member and exact decision limits")
        if not isinstance(row["slot_id"], str) or not row["slot_id"] or row["slot_id"] in seen:
            raise ValueError("Slot IDs must be nonempty and unique")
        seen.add(row["slot_id"])
        if type(row["sampling_seed"]) is not int or row["sampling_seed"] < 0:
            raise ValueError("Predeclare an integer sampling seed per software slot")
        case = case_spec(row["case_id"], first_member=row["first_member"], role_decision_limits=row["role_decision_limits"])
        if case["purpose"] != spec["usage"]:
            raise ValueError("Source partition purpose cannot be relabeled by the caller")
        calls += sum(case["role_decision_limits"].values())
    budget = spec.get("budget")
    if (not isinstance(budget, dict) or set(budget) != {"max_slots", "max_model_calls"}
            or type(budget["max_slots"]) is not int or type(budget["max_model_calls"]) is not int
            or budget != {"max_slots": len(slots), "max_model_calls": calls}):
        raise ValueError("Declare exact finite slot and model-call caps; old resource budgets are not inherited")
    if type(spec.get("min_class_count")) is not int or spec["min_class_count"] != 2:
        raise ValueError("min_class_count is fixed at 2 solely for declaration compatibility; no support is computed")
    return slots


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
                first_member=row["first_member"], role_decision_limits=row["role_decision_limits"]), folder)
            runtime, captured, interfaces = build_runtime(owner, prepared, folder)
            scenario = copy.deepcopy(prepared.scenario)
            scenario.setdefault("variation", {})["software_case"] = copy.deepcopy(prepared.case)
            scenario["variation"]["software_runtime"] = {
                "version": VERSION, "harness": "openhands_v16", "source_usage": window_spec["usage"],
                "collection_mode": window_spec["mode"],
                "interface_revision": INTERFACE_REVISION, "sdk_context_selection": SDK_CONTEXT_SELECTION,
                "context_policy": getattr(owner, "software_context_policy", "latest_observation_last4_tool_rounds"),
                "profile_bindings": {member: interface.profile for member, interface in interfaces.items()},
                "external_tick_per_sweep": 0, "first_member": prepared.case["first_member"],
                "scheduling_protocol": SCHEDULER,
                "role_decision_limits": copy.deepcopy(prepared.case["role_decision_limits"]),
                "active_roles": list(prepared.case["active_roles"]), "category": prepared.case["category"]}
            initial = {"case": prepared.case, "reward_spec": prepared.reward_spec,
                       "initial_business_sha256": prepared.prefix["prepared_business_state_sha256"]}
            spec = {"slot_id": row["slot_id"], "xi_id": situation_id(prepared.case),
                    "xi_fingerprint": digest(json_bytes(initial)), "active_members": list(prepared.case["active_roles"]),
                    "policies": runtime.policy_identities, "mapping_spec_id": DIAGNOSTICS}
            items.append({"row": row, "folder": folder, "prepared": prepared, "runtime": runtime,
                          "captured": captured, "scenario": scenario, "slot_spec": spec, "closed": False})
            atomic_write(folder / "model-scenario.json", json_bytes(scenario))
        gamma = {"collection_version": VERSION, "harness": "openhands_v16", "interface": INTERFACE_VERSION,
                 "source": code_identity(), "source_usage": window_spec["usage"],
                 "collection_mode": window_spec["mode"], "recipe": copy.deepcopy(owner.recipe),
                 "interface_revision": INTERFACE_REVISION, "sdk_context_selection": SDK_CONTEXT_SELECTION,
                 "context_projection": getattr(owner, "software_context_policy", "latest_observation_last4_tool_rounds"),
                 "external_tick_per_sweep": 0,
                 "scheduling_protocol": SCHEDULER, "budget": copy.deepcopy(window_spec["budget"]),
                 "slot_sampling_seeds": {row["slot_id"]: row["sampling_seed"] for row in rows},
                 "fixed_slot_cases": [item["slot_spec"]["xi_fingerprint"] for item in items],
                 "optimizer_update_allowed": False, "method_classification_performed": False,
                 "support_computation_performed": False, "min_class_count_has_research_meaning": False}
        declaration = declare_window(window_spec["window_id"], actor_identity=identity, gamma_identity=gamma,
                                     slot_specs=[item["slot_spec"] for item in items], min_class_count=window_spec["min_class_count"])
        atomic_write(output / "declaration.json", json_bytes(declaration))
        entries, summaries, records = [], [], []
        for item in items:
            row, prepared, folder = item["row"], item["prepared"], item["folder"]
            runtime, captured = item["runtime"], item["captured"]
            if owner.freeze_identity() != identity:
                raise ValueError("Frozen software window cannot change the actor between slots")
            if on_slot:
                on_slot("started", row, folder)
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
                        "cursor": runtime.cursor, "availability": availability(runtime, prepared.case)}))

                boundary = run_fragment(prepared, runtime, on_opportunity=checkpoint)
                finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination=boundary)
                episode_closed = True
                close_runtime(runtime)
                item["closed"] = True
                assessment = assess_software_collaboration(prepared, run_root=folder / "private-assessment")
                atomic_write(folder / "raw-independent-assessment.json", json_bytes(assessment))
                failures = {member: status for member, status in boundary["role_stops"].items()
                            if status in TECHNICAL_FAILURES}
                if failures:
                    # A known file-test result is still useful diagnostic
                    # evidence, but cannot turn a failed execution boundary
                    # into an ordinary evaluable model-work failure/success.
                    assessment.update(status="unknown", R=None,
                        execution_failure={"role_stops": failures,
                            "reason": "Technical execution failed before normal bounded work closure",
                            "raw_independent_assessment_path": "raw-independent-assessment.json"})
                atomic_write(folder / "assessment.json", json_bytes(assessment))
                from .software_training_v030 import export_software_episode
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
                if on_slot:
                    on_slot("closed", row, folder)
                summary = {"slot_id": row["slot_id"], "case_id": row["case_id"],
                           "status": "closed" if assessment["status"] == "evaluable" else "execution_unknown",
                           "first_member": row["first_member"], "boundary": boundary,
                           "R": assessment["R"], "started_at": started,
                           "ended_at": time.time(), "training_eligible": False,
                           "active_members": list(prepared.case["active_roles"]), "category": prepared.case["category"],
                           "process_diagnostics": entry["process_diagnostics"]}
                summaries.append(summary)
                atomic_write(output / "progress.json", json_bytes(summaries))
            except BaseException as error:
                detail = {"type": type(error).__name__, "message": str(error),
                          "episode_closed_before_error": episode_closed, "runtime_closed": item["closed"]}
                atomic_write(folder / "interruption.json", json_bytes(detail))
                if not episode_closed:
                    finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination={
                        "status": "interrupted", "kind": "external_or_collector_failure", "error": detail,
                        "business_result": None, "continuation": False})
                atomic_write(output / "progress.json", json_bytes([*summaries, {
                    "slot_id": row["slot_id"], "status": "interrupted", "R": None, "error": detail}]))
                raise
            finally:
                atomic_write(folder / "public-capture.json", json_bytes(captured))
                atomic_write(folder / "runtime.json", json_bytes(runtime.snapshot()))
        if owner.freeze_identity() != identity:
            raise ValueError("Software development collection changed the actor identity")
        atomic_write(output / "summary.json", json_bytes({"version": VERSION, "usage": window_spec["usage"],
                     "actor_identity": identity, "slots": summaries,
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
