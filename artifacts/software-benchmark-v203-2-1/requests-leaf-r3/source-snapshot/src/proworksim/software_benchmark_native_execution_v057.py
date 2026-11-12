"""Versioned public guidance and one bounded native-SDK stuck correction.

This is a new execution condition. It does not alter native tool semantics,
remove the SDK detector, create another agent, or reset model accounting.
"""
from __future__ import annotations

import copy
import json
import math
import shlex
import time

from .software_benchmark_candidates_v054 import checked, reference

VERSION = "v057-public-guidance-and-one-stuck-correction-r1"
MAX_STUCK_CORRECTIONS = 1
OUTPUT_RESERVATION = 32768

WORKFLOW_GUIDANCE = """Execution guidance for this independent repair task:
- Identify each distinct behavior and public interface requested by the issue. Keep a short coverage checklist; a fix for one path does not establish that another path is fixed.
- Inspect public repository documentation and tests. Use the repository's own test frontend below; do not assume that pytest is installed or that every repository uses the same test labels or settings.
- For terminal commands, follow the native tool's schema. Express one command invocation; explicitly join dependent commands with && or put a deliberate sequence in a script. Do not submit multiple unrelated bare command lines. If a prior command is still running, use the documented continuation/interrupt operation before starting another.
- Treat a failed command, collection error, missing dependency, or unexecuted test as a limitation to investigate, not as a passing test. Preserve the real output.
- Before finish, check the issue's distinct behaviors, a focused public reproduction or test, and relevant existing regressions. State what was actually tested and what remains unverified. A large passing test count alone does not prove the new requirement is covered.
These instructions contain only general workflow and public environment facts. Hidden evaluation tests and reference fixes are not available to the agent."""

STUCK_CORRECTION = """Execution feedback: the native SDK detected repeated or non-actionable behavior. One bounded corrective continuation is available within the same task, workspace, model, token budget and time limits.
Review the most recent action and its actual feedback. Do not repeat an identical read, think step, failing command, or waiting operation without a concrete reason it can yield new information. Choose a different evidence-producing action that addresses the error or an uncovered requirement. If recent responses contained only internal reasoning, keep the next reasoning brief and emit a valid tool action or an honest finish report. Do not claim that an unexecuted or failed test passed.
No additional token allowance, model retry, hidden test information, or new agent has been granted. If you cannot make further progress, finish with the specific remaining limitation."""


def prepare_public_guidance(public_task, *, registry_reference, baseline_mapping_reference):
    """Project only admitted repository-wide public facts, never scorer material."""
    registry = json.loads(checked(registry_reference).read_bytes())
    mapping = json.loads(checked(baseline_mapping_reference).read_bytes())
    entries = [entry for entry in registry.get("entries", [])
               if entry.get("instance_id") == public_task.get("instance_id")]
    if len(entries) != 1:
        raise ValueError("Public guidance requires one admitted task entry")
    entry = entries[0]
    if (registry.get("planned_tasks") != 500 or entry.get("admitted") is not True
            or entry.get("source") != "public_repository"
            or entry.get("hidden_material_used") is not False
            or entry.get("selection") != "repository-wide public default; no answer-derived files or task-result selection"
            or entry.get("repo") != public_task.get("repo")
            or entry.get("baseline_mapping") != baseline_mapping_reference
            or mapping.get("instance_id") != public_task.get("instance_id")
            or entry.get("cwd") != "/testbed"):
        raise ValueError("Guidance cannot use hidden tests, answer-selected paths or another task")
    argv = entry.get("argv")
    interpreter = entry.get("public_python")
    if (not isinstance(argv, list) or not argv or len(argv) > 20
            or any(not isinstance(arg, str) or not arg or "\x00" in arg or "\n" in arg for arg in argv)
            or not isinstance(interpreter, str) or argv[0] != interpreter
            or mapping.get("public_python") != interpreter):
        raise ValueError("Public interpreter and repository test frontend differ")
    # No mapping paths, admission notes, task-selected files, commands derived
    # from FAIL_TO_PASS/PASS_TO_PASS, source digests or grader output go to the LLM.
    facts = {"cwd": "/testbed", "python": interpreter, "public_test_frontend": argv}
    text = (WORKFLOW_GUIDANCE + "\n\nPublic execution facts:\n"
            + "Working directory: /testbed\nInterpreter: " + interpreter
            + "\nRepository-wide public test frontend: " + shlex.join(argv)
            + "\nThis is an entry point, not a claim the complete suite has passed. "
              "Choose focused test targets from the issue and public repository only.")
    return {"version": VERSION, "visible_text": text, "visible_facts": facts,
            "sources": {"registry": registry_reference, "baseline_mapping": baseline_mapping_reference,
                        "adapter": reference(__file__)},
            "instance_id": public_task["instance_id"], "repo": public_task["repo"],
            "hidden_material_used": False, "source_entry_selection": entry["selection"],
            "original_problem_statement_changed": False, "model_calls": 0}


def _status(conversation):
    value = conversation.state.execution_status
    return getattr(value, "value", str(value))


def recovery_admission(snapshot, *, started, limits, now=None):
    """A coarse no-reset guard; the original exact counter still admits input."""
    now = time.monotonic() if now is None else now
    for key in ("started", "soft_at", "hard_at"):
        if not isinstance(started.get(key), (int, float)) or not math.isfinite(started[key]):
            raise ValueError("A bound episode deadline is required")
    if (snapshot["token_limit"] != limits["input_plus_output_tokens"]
            or snapshot["all_model_attempt_limit"] != limits["all_model_attempts"]
            or snapshot["agent_decision_limit"] != limits["agent_decisions"]):
        raise ValueError("Correction must retain the original episode limits")
    if (snapshot.get("complete_actual_tokens") is None or snapshot.get("inflight") is not None
            or snapshot.get("uncertain_reserved_tokens", 0)):
        return "uncertain_model_usage"
    if now >= started["soft_at"] or now >= started["hard_at"]:
        return "episode_deadline"
    if snapshot["attempts"] >= limits["all_model_attempts"]:
        return "model_attempt_limit"
    if snapshot["decisions"] >= limits["agent_decisions"]:
        return "agent_decision_limit"
    if limits["input_plus_output_tokens"] - snapshot["known_actual_tokens"] <= OUTPUT_RESERVATION:
        return "no_room_for_complete_output_reservation"
    return None


def run_conversation_once_or_recover(conversation, *, ledger, started, limits, event_sink=None):
    """Run one live conversation, with at most one explicit STUCK correction.

    Exceptions, ERROR, FINISHED and other boundaries are never automatically
    resumed. The same ledger, agent and conversation survive the one correction;
    a subsequent model call counts the new input normally, including this text.
    """
    if conversation.stuck_detector is None:
        raise ValueError("The native stuck detector must remain enabled")
    if (getattr(conversation, "_v057_execution_policy_started", False)
            or _status(conversation) != "idle"):
        raise ValueError("Execution policy may enter one fresh idle conversation only")
    object.__setattr__(conversation, "_v057_execution_policy_started", True)
    events, corrections = [], 0

    def emit(kind, **values):
        event = {"version": VERSION, "kind": kind, **values}
        events.append(event)
        if event_sink is not None:
            event_sink(copy.deepcopy(event))

    while True:
        before = ledger.snapshot()
        remaining = limits["agent_decisions"] - before["decisions"]
        if remaining <= 0:
            emit("run_not_resumed", reason="agent_decision_limit", status=_status(conversation))
            break
        conversation.max_iteration_per_run = remaining
        conversation.run()  # Deliberately let real boundaries/exceptions reach the caller.
        after = ledger.snapshot()
        emit("sdk_run_returned", run_index=corrections + 1, status=_status(conversation),
             segment_max_iterations=remaining, attempts_before=before["attempts"],
             attempts_after=after["attempts"], decisions_before=before["decisions"],
             decisions_after=after["decisions"], known_actual_tokens=after["known_actual_tokens"])
        if _status(conversation) != "stuck":
            break
        if corrections >= MAX_STUCK_CORRECTIONS:
            emit("stuck_correction_not_sent", reason="one_correction_exhausted")
            break
        reason = recovery_admission(after, started=started, limits=limits)
        if reason:
            emit("stuck_correction_not_sent", reason=reason)
            break
        corrections += 1
        emit("stuck_correction_sent", correction_index=corrections,
             source="v057-execution-policy", message=STUCK_CORRECTION,
             ledger_reset=False, additional_budget=0, model_retry=False)
        conversation.send_message(STUCK_CORRECTION, sender="v057-execution-policy")
    return {"version": VERSION, "stuck_corrections": corrections,
            "final_sdk_status": _status(conversation), "events": events,
            "ledger_reset": False, "additional_agents": 0,
            "original_stuck_detector_retained": True, "automatic_model_retry": False}
