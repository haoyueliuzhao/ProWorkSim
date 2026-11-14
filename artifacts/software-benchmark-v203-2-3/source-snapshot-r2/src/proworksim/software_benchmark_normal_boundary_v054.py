"""Close known pre-generation limits normally; preserve all uncertain executions as faults."""
from __future__ import annotations

import copy

from .software_benchmark_match_v054 import DispatchStopped
from .software_benchmark_owner_ipc_v054 import OwnerService

NORMAL_REASONS = frozenset({
    "all_model_attempt_limit", "agent_decision_limit", "full_context_preexecution_rejection",
    "full_input_and_output_reservation_insufficient", "soft_deadline_before_generation",
    "soft_deadline_after_exact_count_before_generation", "soft_deadline_before_new_dispatch",
})


class NormalEpisodeBoundary(DispatchStopped):
    """No new generation occurred, and every prior attempt has complete actual usage."""


def unwrap_normal_boundary(error):
    if type(error) is NormalEpisodeBoundary:
        return error if str(error) in NORMAL_REASONS else None
    from openhands.sdk.conversation.exceptions import ConversationRunError
    if (type(error) is ConversationRunError
            and type(error.original_exception) is NormalEpisodeBoundary
            and error.__cause__ is error.original_exception
            and str(error.original_exception) in NORMAL_REASONS):
        return error.original_exception
    return None


def known_boundary(error, ledger):
    if type(error) is not DispatchStopped or str(error) not in NORMAL_REASONS:
        return None
    if (ledger.get("inflight") is not None or ledger.get("uncertain_reserved_tokens", 0)
            or type(ledger.get("complete_actual_tokens")) is not int
            or ledger["complete_actual_tokens"] != ledger["known_actual_tokens"]):
        return None
    return {"reason": str(error), "generation_dispatched_at_boundary": False,
            "all_prior_usage_complete": True, "ledger": copy.deepcopy(ledger),
            "retry_or_resample": False}


class FormalOwnerService(OwnerService):
    """Only RPC close classification changes; original owner and numerical bridge are inherited."""
    def dispatch(self, request):
        try:
            return super().dispatch(request)
        except DispatchStopped as error:
            if request.get("operation") != "match_complete" or self.bridge is None:
                raise
            boundary = known_boundary(error, self.bridge.ledger.snapshot())
            if boundary is None:
                raise
            # MatchBridge already seals further generation. Keep original finish
            # and its RNG/learning guard available; no request is replayed.
            return {"terminal_boundary": boundary, "ledger": boundary["ledger"]}
