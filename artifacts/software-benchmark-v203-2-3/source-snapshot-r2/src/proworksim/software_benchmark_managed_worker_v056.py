"""Managed-only handling of SDK tool exceptions at the one-opportunity boundary."""
from __future__ import annotations

import copy
from functools import cache

VERSION = "v056-managed-execution-error-boundary-r1"


class _ExecutionFailureBoundaryMixin:
    """Retain the first tool failure instead of letting SDK resample after it."""

    def _on_sdk_event(self, event):
        from openhands.sdk.event import AgentErrorEvent

        # Preserve original SDK event provenance and normal ObservationEvent pause.
        super()._on_sdk_event(event)
        if not isinstance(event, AgentErrorEvent):
            return
        pending = self._pending
        matched = (self._in_step and self._completions == 1 and pending is not None
                   and event.tool_name == pending["name"]
                   and event.tool_call_id == pending["tool_call_id"])
        record = {
            "version": VERSION, "model_call_id": self._association.get("call_id"),
            "opportunity_id": self._association.get("opportunity_id"),
            "original_sdk_error": event.model_dump(mode="json"),
            "matches_admitted_action": matched,
            "gateway_invocations": self._executions,
            "world_result_known": self._result is not None,
            "automatic_retry": False,
        }
        self._execution_failure_v056 = copy.deepcopy(record)
        self.conversation.pause()
        self._emit("managed_execution_error_v056", record)
        reason = ("Managed tool execution failed; original SDK error retained and replay forbidden: "
                  + event.error if matched else
                  "SDK tool error does not match this opportunity's admitted action")
        # A tool may already have changed the world before raising. Never turn
        # this into correctable model format feedback or a successful tool result.
        self._fail("execution_integrity_error", reason, managed_execution_failure=record)

    def step(self, *args, **kwargs):
        failure = getattr(self, "_execution_failure_v056", None)
        if failure is not None:
            self._fail("execution_integrity_error",
                       "Prior managed execution outcome is unresolved; worker reuse is forbidden",
                       managed_execution_failure=copy.deepcopy(failure))
        return super().step(*args, **kwargs)

    def snapshot(self):
        result = super().snapshot()
        result["managed_worker_revision"] = VERSION
        result["managed_execution_failure"] = copy.deepcopy(
            getattr(self, "_execution_failure_v056", None))
        return result


@cache
def worker_type():
    from .software_calibration_collector_v051 import worker_type as existing_worker_type

    class ManagedExecutionBoundaryWorker(_ExecutionFailureBoundaryMixin, existing_worker_type()):
        pass

    return ManagedExecutionBoundaryWorker
