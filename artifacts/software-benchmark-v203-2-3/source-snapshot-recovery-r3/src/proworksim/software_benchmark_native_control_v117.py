"""Native control with an explicit, unchanged-identity aligned history chain.

Only the exact v117 history wrapper is admitted around the original projection
and raw model adapter. No proxy is relabelled as a projection guard, and no
health, cumulative-accounting, SDK state or deadline check is removed.
"""
from __future__ import annotations

import copy

from .software_benchmark_alignment_contract_v117 import (
    CONDENSER_PARAMETERS, initial_message,  # noqa: F401
)
from .software_benchmark_exact_transport_v057 import (
    ProjectionGuard, assert_response_projection_healthy,
)
from .software_benchmark_finish_review_v117 import FINISH_REVIEW, MAX_FINISH_REVIEWS, policy_manifest
from .software_benchmark_history_v110 import VERSION as HISTORY_VERSION, condenser_type
from .software_benchmark_history_budget_v110 import RefSummaryGuard, SummaryTrace
from .software_benchmark_native_control_v062 import (
    MAX_STUCK_CORRECTIONS, STUCK_CORRECTION, _known_usage, _status, _validate_deadlines,
)
from .software_benchmark_native_execution_v057 import recovery_admission
from .storage import digest

VERSION = 'v117-native-shared-history-and-final-review-r1'


def validate_ref_binding(conversation, adapter, *, expected=None):
    """Validate exactly one declared wrapper and its shared actual condenser.

    The returned object references are an internal boundary token. Subsequent
    calls require identical references, not equality or a duck-typed delegate.
    This function only inspects bindings and health; it never invokes a model.
    """
    agent = conversation.agent
    llm = agent.llm
    wrapper = getattr(llm, '_adapter', None)
    projection = getattr(adapter, '_v057_projection_guard', None)
    condenser = getattr(agent, 'condenser', None)
    if (type(wrapper) is not RefSummaryGuard or type(projection) is not ProjectionGuard
            or wrapper.delegate is not projection or projection.delegate is not adapter
            or type(wrapper.trace) is not SummaryTrace
            or wrapper.trace.owner_id != 'REF-single-agent'
            or wrapper.trace.conversation is not conversation
            or wrapper.trace.event_provider is None
            or type(condenser) is not condenser_type()
            or condenser.llm._adapter is not wrapper or condenser._trace is not wrapper.trace
            or llm.usage_id != 'agent' or condenser.llm.usage_id != 'condenser'):
        raise ValueError('Native agent and condenser must share the exact v117 history -> projection -> model chain')
    values = {key: getattr(condenser, key) for key in ('max_size', 'keep_first', 'max_tokens')}
    values['hard_reset_retries'] = condenser.hard_context_reset_max_retries
    if values != CONDENSER_PARAMETERS:
        raise ValueError('The aligned native condenser strategy changed')
    binding = {'agent_llm': llm, 'condenser': condenser, 'condenser_llm': condenser.llm,
               'history_guard': wrapper, 'projection_guard': projection,
               'history_trace': wrapper.trace, 'adapter': adapter, 'ledger': adapter.ledger,
               'source_provider': wrapper.trace.event_provider,
               'source_conversation': wrapper.trace.conversation,
               'source_state': conversation.state}
    if expected is not None and (set(expected) != set(binding)
            or any(binding[key] is not expected[key] for key in binding)):
        raise RuntimeError('The live native history, projection, model or ledger binding changed')
    wrapper.trace.assert_bound_to(conversation)
    assert_response_projection_healthy(adapter)
    wrapper.assert_healthy()
    if wrapper.trace.pending is not None:
        raise RuntimeError('A controller boundary cannot conceal an unfinished history summary')
    return binding


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
    if (any(getattr(conversation, name, False) for name in (
                    "_v117_native_execution_policy_started", "_v062_execution_policy_started",
                    "_v057_execution_policy_started"))
            or _status(conversation) != "idle"
            or any(initial[key] != 0 for key in ("attempts", "decisions", "known_actual_tokens"))):
        raise ValueError("Execution policy requires one fresh idle, unconsumed conversation")
    if conversation.stuck_detector is None:
        raise ValueError("The original native stuck detector must remain enabled")
    binding = validate_ref_binding(conversation, adapter)
    if binding['history_trace'].counter != 0:
        raise ValueError('The aligned execution policy requires fresh unsummarized history')
    object.__setattr__(conversation, "_v117_native_execution_policy_started", True)
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
        validate_ref_binding(conversation, adapter, expected=binding)
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
    return {"version": VERSION, "final_review_policy": policy_manifest(),
            "aligned_history_version": HISTORY_VERSION, "sdk_runs": runs, "stuck_corrections": corrections,
            "finish_reviews": reviews, "final_sdk_status": _status(conversation), "events": events,
            "ledger_reset": False, "additional_agents": 0, "additional_budget": 0,
            "original_stuck_detector_retained": True, "automatic_model_retry": False,
            "candidate_selection": "last production workspace only; no intermediate scoring or selection"}
