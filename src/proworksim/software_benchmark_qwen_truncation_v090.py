"""Local stop for settled Qwen reasoning-only output truncation.

This is a separately identified execution policy, not a provider retry or a
model-template change. The delegate archives and settles the original response
first. No reasoning is copied into future prompts and no finish is fabricated.
"""
from __future__ import annotations

import copy
from pathlib import Path
import threading

from .software_benchmark_candidates_v054 import checked, write_new
from .software_benchmark_exact_transport_v057 import normalize_response
from .storage import digest, json_bytes

VERSION = "v090-qwen-ref-settled-reasoning-truncation-r1"
REASON = "qwen_reasoning_output_limit_without_action"


class TruncationProtocolFault(RuntimeError):
    """Usage, response, progress or evidence is not sufficient for local closure."""


class SettledReasoningTruncation(RuntimeError):
    """A real, fully charged response hit its output limit without an action."""


def classify_response(body):
    """Inspect the original response without altering its content or reasoning."""
    try:
        projection, _ = normalize_response(body)
    except (TypeError, ValueError) as error:
        raise TruncationProtocolFault("Ambiguous Qwen response fields") from error
    choice = projection["choices"][0]
    message = choice["message"]
    content, calls = message.get("content"), message.get("tool_calls")
    if (choice.get("finish_reason") not in {"stop", "length", "tool_calls"}
            or content is not None and not isinstance(content, str)
            or calls is not None and not isinstance(calls, list)):
        raise TruncationProtocolFault("Unrecognized Qwen response shape")
    reasoning = message.get("reasoning_content") or ""
    if calls:
        kind = "tool_calls"
    elif content and content.strip():
        kind = "visible_content"
    elif reasoning.strip():
        kind = "reasoning_only"
    else:
        kind = "empty"
    return {
        "kind": kind, "finish_reason": choice["finish_reason"],
        "reasoning_characters": len(reasoning),
        "reasoning_sha256": digest(reasoning.encode()) if reasoning else None,
        "requires_local_stop": kind == "reasoning_only" and choice["finish_reason"] == "length",
    }


def _known(snapshot):
    if (type(snapshot.get("complete_actual_tokens")) is not int
            or snapshot["complete_actual_tokens"] != snapshot.get("known_actual_tokens")
            or snapshot.get("inflight") is not None
            or snapshot.get("uncertain_reserved_tokens", 0)):
        raise TruncationProtocolFault("An output boundary cannot conceal unknown usage")


class ReasoningTruncationAdapter:
    """Fresh REF adapter with one sticky, post-settlement local stop.

    ``progress_snapshot`` reports observed completed tool RPCs, not an asserted
    Git tree identity: a previously launched process could still modify files.
    The controller must retain its existing quiescence and candidate export.
    """

    def __init__(self, delegate, *, folder, workspace_id, progress_snapshot):
        condition = getattr(delegate, "condition", {})
        before = delegate.ledger.snapshot()
        _known(before)
        if (condition.get("model_key") != "QWEN" or condition.get("arm") != "REF"
                or workspace_id != getattr(delegate, "slot_id", None)
                or not isinstance(workspace_id, str) or not workspace_id
                or not callable(progress_snapshot)
                or any(before.get(k) != 0 for k in ("attempts", "decisions", "known_actual_tokens"))
                or getattr(delegate, "_v090_truncation_guard", None) is not None):
            raise ValueError("Bind this policy once to a fresh, identified Qwen REF workspace")
        self.delegate, self.workspace_id = delegate, workspace_id
        self._lock = threading.RLock()
        self.progress_snapshot = progress_snapshot
        self._boundary = self._fault = None
        self._boundary_ledger_sha256 = self._boundary_ref = self._receipt = None
        self.observed_responses = {}
        self.folder = Path(folder)
        self._progress()
        self.folder.mkdir(parents=True, exist_ok=False)
        self.policy_reference = write_new(self.folder / "policy.json", {
            "version": VERSION, "workspace_id": workspace_id,
            "stop_at_first_confirmed_reasoning_only_length": True,
            "additional_model_calls": 0, "reasoning_replayed": False,
            "inference_recipe_modified": False, "tools_modified": False,
            "normal_empty_response_policy_modified": False,
            "candidate_and_scoring_rules_modified": False,
            "claimed_equivalent_to_original_REF": False,
        })
        delegate._v090_truncation_guard = self

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def _progress(self):
        value = self.progress_snapshot()
        if (not isinstance(value, dict) or set(value) != {"tool_rpc_count"}
                or type(value["tool_rpc_count"]) is not int or value["tool_rpc_count"] < 0):
            raise TruncationProtocolFault("Expected a nonnegative observed tool RPC count")
        return copy.deepcopy(value)

    def _open(self):
        if self._fault is not None:
            raise self._fault
        if self._boundary is not None:
            raise self._boundary

    def count(self, request):
        with self._lock:
            self._open()
            return self.delegate.count(request)

    def complete(self, request, usage_id):
        with self._lock:
            return self._complete(request, usage_id)

    def _complete(self, request, usage_id):
        self._open()
        before = self.ledger.snapshot()
        try:
            _known(before)
            progress_before = self._progress()
        except TruncationProtocolFault as error:
            self._fault = error
            raise
        body = self.delegate.complete(request, usage_id)
        # Condenser behavior remains unchanged; this policy concerns agent actions.
        if usage_id != "agent":
            return body
        try:
            classification = classify_response(body)
            key = classification["kind"] + ":" + classification["finish_reason"]
            self.observed_responses[key] = self.observed_responses.get(key, 0) + 1
            if not classification["requires_local_stop"]:
                return body
            after = self.ledger.snapshot()
            _known(after)
            usage = body.get("usage", {})
            calls = after.get("calls", [])
            last = calls[-1] if calls else {}
            if (request.get("max_tokens") != 32768
                    or usage.get("completion_tokens") != request["max_tokens"]
                    or after.get("attempts") != before["attempts"] + 1
                    or after.get("decisions") != before["decisions"] + 1
                    or len(calls) != after["attempts"]
                    or after["complete_actual_tokens"] - before["complete_actual_tokens"] != usage.get("total_tokens")
                    or last.get("native_attempt_id") != body.get("id")
                    or last.get("usage_id") != "agent" or last.get("usage") != usage
                    or last.get("finish_reason") != "length"
                    or last.get("response", {}).get("sha256") != digest(json_bytes(body))):
                raise TruncationProtocolFault("Truncation does not bind one fully settled original response")
            progress_after = self._progress()
            if progress_after["tool_rpc_count"] < progress_before["tool_rpc_count"]:
                raise TruncationProtocolFault("Observed workspace progress moved backwards")
            ledger_sha = digest(json_bytes(after))
            receipt = {
                "version": VERSION, "reason": REASON, "workspace_id": self.workspace_id,
                "classification": classification, "response_id": body["id"],
                "wire_response": copy.deepcopy(last["response"]),
                "request": copy.deepcopy(last["request"]),
                "request_payload_sha256": digest(json_bytes(request)),
                "usage": copy.deepcopy(usage), "ledger_sha256": ledger_sha,
                "attempt": after["attempts"], "known_usage": True,
                "generation_dispatched_at_boundary": True,
                "progress_before": progress_before, "progress_after": progress_after,
                "observed_tool_progress_unchanged": progress_before == progress_after,
                "filesystem_unchanged_claimed": False,
                "reasoning_only_truncated_responses_before_stop": 1,
                "further_model_calls_on_this_workspace": 0,
                "generic_sdk_nudge_emitted_for_this_response": False,
                "native_finish_fabricated": False, "automatic_retry": False,
                "reasoning_replayed": False, "raw_response_overwritten": False,
                "candidate_rule": "unchanged; export only after existing trusted quiescence",
            }
            self._boundary_ref = write_new(self.folder / "output-truncation.json", receipt)
            self._receipt, self._boundary_ledger_sha256 = receipt, ledger_sha
            self._boundary = SettledReasoningTruncation(REASON)
        except Exception as error:
            self._fault = error if isinstance(error, TruncationProtocolFault) else TruncationProtocolFault(
                "Could not persist a trustworthy truncation boundary")
            if self._fault is error:
                raise
            raise self._fault from error
        raise self._boundary

    def truncation_snapshot(self):
        return {"version": VERSION, "workspace_id": self.workspace_id,
                "observed_responses": copy.deepcopy(self.observed_responses),
                "policy": copy.deepcopy(self.policy_reference),
                "boundary": copy.deepcopy(self._boundary_ref),
                "fault": None if self._fault is None else {
                    "type": type(self._fault).__name__, "message": str(self._fault)}}


def unwrap_local_boundary(error, adapter):
    """Accept only this guard's actual settled stop, including the SDK wrapper."""
    if not isinstance(adapter, ReasoningTruncationAdapter):
        return None
    candidate = error
    if type(candidate) is not SettledReasoningTruncation:
        try:
            from openhands.sdk.conversation.exceptions import ConversationRunError
        except ImportError:
            return None
        if type(error) is not ConversationRunError or error.__cause__ is not error.original_exception:
            return None
        candidate = error.original_exception
    if (type(candidate) is not SettledReasoningTruncation or candidate is not adapter._boundary
            or adapter._fault is not None or adapter._boundary_ref is None):
        return None
    snapshot = adapter.ledger.snapshot()
    _known(snapshot)
    if digest(json_bytes(snapshot)) != adapter._boundary_ledger_sha256:
        raise TruncationProtocolFault("Ledger changed after the settled local stop")
    try:
        checked(adapter._boundary_ref)
    except (OSError, ValueError) as error:
        raise TruncationProtocolFault("The original truncation evidence is unavailable or changed") from error
    return {"reason": REASON, "kind": "settled_output_truncation",
            "known_usage": True, "generation_dispatched_at_boundary": True,
            "native_finished": False, "automatic_retry": False,
            "policy_version": VERSION, "evidence": copy.deepcopy(adapter._boundary_ref)}
