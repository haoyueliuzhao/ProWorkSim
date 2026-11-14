"""One native agent with bounded, fully accounted public verification turns.

Only the SDK's public send_message/run interface changes conversation status.
The v057 response factory, native tools, detector and complete history remain
in place. This module never starts workers, scores candidates or retries calls.
"""
from __future__ import annotations

import copy
import importlib.metadata
import math
from pathlib import Path

from .software_benchmark_exact_transport_v057 import (
    assert_response_projection_healthy,
    build_llm,
)
from .software_benchmark_native_execution_v057 import recovery_admission
from .storage import digest

VERSION = "v062-single-agent-bounded-verification-r1"
SDK_VERSION = "1.49.6"
MAX_STUCK_CORRECTIONS = 2
MAX_FINISH_REVIEWS = 1

WORKFLOW_GUIDANCE = """Repair and verification workflow:
- Derive a short checklist from the issue's requested behaviors, public interfaces and edge cases. Check each separately against the implementation; one working path does not establish that other requested paths work.
- Read the public repository documentation and tests to identify the appropriate test frontend and focused reproductions. Use the supplied public execution context when present.
- Derive expected behavior from the issue and public API contract independently of the current patch. A new test that merely reproduces the patch's output does not establish that the requirement is satisfied.
- Use the native terminal schema and its documented continuation operation for a command that is still running. Investigate command failures, collection errors, and missing dependencies; none is a passing test.
- Before finishing, compare the patch and focused test coverage against the checklist, inspect relevant regressions, and state what actually ran and what remains unverified. Prefer evidence-producing actions over repeating the same reasoning or command without new information.
All work and verification share this task's original token, attempt, decision and time limits."""

STUCK_CORRECTION = """Execution feedback: the native SDK detected repeated or non-actionable behavior. A bounded continuation is available in this same conversation and workspace, under the original cumulative budget and deadlines.
Review the latest action and its actual feedback. Choose a different evidence-producing action for an uncovered requirement or the concrete error. Do not repeat an identical read, reasoning step, failed command or wait without a specific reason it can produce new information. If the previous replies contained only reasoning, keep the next reasoning brief and emit a valid tool action or an honest finish report. Report unexecuted or failed tests accurately.
No extra budget or new independent attempt is available. If further progress is not possible, finish and identify the remaining limitation."""

FINISH_REVIEW = """A single final self-review opportunity is available in this same conversation and workspace, within the remaining original budget and deadlines.
Re-read the issue's requested behavior independently of your previous success claim. Compare each requested public interface and edge case with the current patch and the evidence actually produced. Check that your expected test results follow from the issue and public contract, rather than from the patch itself. If a concrete gap remains, perform a focused public reproduction or regression check and repair it if warranted. Existing sufficient evidence can be cited without rerunning the same tests.
Finish with the actual verification results and any unresolved limitations. This is the only final self-review opportunity; it does not reset the task, create another agent or increase any limit."""


def initial_message(problem_statement, *, public_context=""):
    """Append fixed guidance and separately admitted public context verbatim.

    The caller is responsible for admitting public_context. This function never
    reads task mappings, reference patches, scorer files or evaluation feedback.
    """
    if not isinstance(problem_statement, str) or not problem_statement.strip():
        raise ValueError("The unchanged public problem statement is required")
    if not isinstance(public_context, str):
        raise TypeError("Public execution context must already be admitted text")
    parts = [problem_statement, WORKFLOW_GUIDANCE]
    if public_context:
        parts.append(public_context)
    return "\n\n".join(parts)


def create_conversation(adapter, rpc, output, limits, *, workspace="/testbed"):
    """Use the frozen five-tool factory and the complete v057 projection guard."""
    if importlib.metadata.version("openhands-sdk") != SDK_VERSION:
        raise ValueError("The v062 protocol requires the pinned OpenHands SDK 1.49.6")
    from openhands.sdk import Conversation

    from .software_benchmark_native_binding_v054 import build_isolated_agent

    output = Path(output)
    llm = build_llm(adapter, normalization_folder=output / "sdk-response-projections")
    return Conversation(
        agent=build_isolated_agent(llm, rpc=rpc), workspace=workspace,
        persistence_dir=output / "native-conversation", plugins=[],
        max_iteration_per_run=limits["agent_decisions"], stuck_detection=True,
        visualizer=None, delete_on_close=False)


def _status(conversation):
    value = conversation.state.execution_status
    return getattr(value, "value", str(value))


def _known_usage(snapshot):
    if (snapshot.get("complete_actual_tokens") is None
            or snapshot.get("complete_actual_tokens") != snapshot.get("known_actual_tokens")
            or snapshot.get("inflight") is not None
            or snapshot.get("uncertain_reserved_tokens", 0)):
        raise RuntimeError("A continuation or closure cannot conceal uncertain model usage")


def _validate_deadlines(started, limits):
    for key in ("started", "soft_at", "hard_at"):
        value = started.get(key)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Finite original absolute episode deadlines are required")
    if not started["started"] < started["soft_at"] <= started["hard_at"]:
        raise ValueError("Episode deadlines are not ordered")
    for key, maximum in (("soft_at", "soft_seconds"), ("hard_at", "hard_seconds")):
        if started[key] - started["started"] > limits[maximum]:
            raise ValueError("Continuation cannot extend the original episode deadlines")


def run_controlled_conversation(conversation, *, adapter, started, limits, event_sink=None):
    """Run once, plus at most two stuck corrections and one final self-review.

    Every continuation is a normal public user message in the same conversation;
    its next model request includes and charges that message normally. The exact
    original adapter still admits each full request. No exception, ERROR, pause,
    uncertain charge, or projection fault is automatically recovered. The caller
    must retain its independent wall-clock/worker deadline enforcement and check
    projection health again before accepting the final candidate.
    """
    _validate_deadlines(started, limits)
    assert_response_projection_healthy(adapter)
    ledger = adapter.ledger
    initial = ledger.snapshot()
    _known_usage(initial)
    if (getattr(conversation, "_v062_execution_policy_started", False)
            or _status(conversation) != "idle"
            or any(initial[key] != 0 for key in ("attempts", "decisions", "known_actual_tokens"))):
        raise ValueError("Execution policy requires one fresh idle, unconsumed conversation")
    if conversation.stuck_detector is None:
        raise ValueError("The original native stuck detector must remain enabled")
    guard = adapter._v057_projection_guard
    if conversation.agent.llm._adapter is not guard:
        raise ValueError("The native agent must use the same guarded model adapter")
    condenser = getattr(conversation.agent, "condenser", None)
    if condenser is not None and condenser.llm._adapter is not guard:
        raise ValueError("The native condenser must share the agent's guarded model adapter")
    object.__setattr__(conversation, "_v062_execution_policy_started", True)
    agent, detector, state = conversation.agent, conversation.stuck_detector, conversation.state
    original_started, original_limits = copy.deepcopy(started), copy.deepcopy(limits)
    events, corrections, reviews, runs = [], 0, 0, 0
    phase = "initial"

    def emit(kind, **values):
        event = {"version": VERSION, "kind": kind, **values}
        events.append(event)
        if event_sink is not None:
            event_sink(copy.deepcopy(event))

    def assert_invariants():
        assert_response_projection_healthy(adapter)
        if (adapter.ledger is not ledger or conversation.agent is not agent
                or conversation.stuck_detector is not detector or conversation.state is not state
                or started != original_started or limits != original_limits):
            raise RuntimeError("The agent, detector, state, ledger, limits and deadlines must remain bound")

    def snapshot_checked(previous):
        assert_invariants()
        snapshot = ledger.snapshot()
        _known_usage(snapshot)
        for key in ("attempts", "decisions", "known_actual_tokens"):
            if snapshot[key] < previous[key]:
                raise RuntimeError("Cumulative usage cannot decrease between conversation segments")
        return snapshot

    before = initial
    while True:
        assert_invariants()
        reason = recovery_admission(before, started=started, limits=limits)
        if reason:
            emit("run_not_started", reason=reason, phase=phase, status=_status(conversation))
            break
        remaining = limits["agent_decisions"] - before["decisions"]
        conversation.max_iteration_per_run = remaining
        runs += 1
        emit("sdk_run_started", run_index=runs, phase=phase,
             segment_max_iterations=remaining, attempts_before=before["attempts"],
             decisions_before=before["decisions"], tokens_before=before["known_actual_tokens"])
        try:
            conversation.run()
        except BaseException as error:
            emit("sdk_run_raised", run_index=runs, phase=phase, status=_status(conversation),
                 error_type=type(error).__name__, automatic_retry=False)
            raise
        after = snapshot_checked(before)
        status = _status(conversation)
        emit("sdk_run_returned", run_index=runs, phase=phase, status=status,
             segment_max_iterations=remaining, attempts_before=before["attempts"],
             attempts_after=after["attempts"], decisions_before=before["decisions"],
             decisions_after=after["decisions"], tokens_before=before["known_actual_tokens"],
             tokens_after=after["known_actual_tokens"])
        if status == "stuck":
            phase, message, used, maximum = "stuck_correction", STUCK_CORRECTION, corrections, MAX_STUCK_CORRECTIONS
        elif status == "finished":
            phase, message, used, maximum = "finish_review", FINISH_REVIEW, reviews, MAX_FINISH_REVIEWS
        else:
            emit("continuation_not_sent", reason="sdk_status_not_resumable", status=status)
            break
        reason = "opportunity_limit" if used >= maximum else recovery_admission(
            after, started=started, limits=limits)
        if reason:
            emit("continuation_not_sent", reason=reason, phase=phase, status=status, opportunities_used=used)
            break
        emit("policy_message_prepared", phase=phase, opportunity_index=used + 1,
             message=message, message_sha256=digest(message.encode()), status_before=status,
             ledger_reset=False, additional_budget=0, additional_agents=0)
        conversation.send_message(message, sender="v062-execution-policy")
        if _status(conversation) != "idle":
            raise RuntimeError("SDK send_message did not publicly transition the terminal state to idle")
        after_message = snapshot_checked(after)
        if after_message != after:
            raise RuntimeError("Sending a policy message unexpectedly changed model accounting")
        if phase == "stuck_correction":
            corrections += 1
        else:
            reviews += 1
        emit("policy_message_sent", phase=phase, opportunity_index=used + 1,
             status_before=status, status_after="idle", charged_in_next_request=True)
        before = after_message
    assert_invariants()
    _known_usage(ledger.snapshot())
    return {"version": VERSION, "sdk_runs": runs, "stuck_corrections": corrections,
            "finish_reviews": reviews, "final_sdk_status": _status(conversation), "events": events,
            "ledger_reset": False, "additional_agents": 0, "additional_budget": 0,
            "original_stuck_detector_retained": True, "automatic_model_retry": False,
            "candidate_selection": "last production workspace only; no intermediate scoring or selection"}
