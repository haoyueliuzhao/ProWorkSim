"""Explicit future PROJECT protocol: spend only an affordable output reservation.

The ceiling remains 32768, but a final request can reserve less when its unchanged
input fits the remaining episode budget. No action, test, fix or submission is
created here. Historical protocols and cash reservations remain untouched.
"""
from __future__ import annotations

import copy
import time

from . import software_benchmark_managed_v064 as original
from . import software_benchmark_deepseek_adapter_v064 as remote
from .model_policy import ModelPolicy
from .software_benchmark_candidates_v054 import write_new
from .storage import digest, json_bytes

VERSION = "v103-remaining-budget-output-r1"
PREPARATION_VERSION = "v103-managed-budget-preparation-r1"


def affordable_output_cap(prompt_tokens, available_tokens):
    """Return a positive reduced cap, or retain normal refusal if input cannot fit."""
    if any(type(value) is not int or value < 0 for value in (prompt_tokens, available_tokens)):
        raise ValueError("Token bounds must be nonnegative integers")
    room = available_tokens - prompt_tokens
    return min(original.MAX_OUTPUT_TOKENS, room) if room > 0 else original.MAX_OUTPUT_TOKENS


class RemainingBudgetContextTransport(original.ManagedContextTransport):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._budget_sources_v103 = {}

    def bind_budget_sources(self, member, *, meter, team_budget, local_limit):
        if member in self._budget_sources_v103 or type(local_limit) is not int or local_limit <= 0:
            raise ValueError("Bind each real member budget exactly once")
        self._budget_sources_v103[member] = (meter, team_budget, local_limit)

    def prepare_for_budget(self, request):
        measure = super().prepare_for_budget(request)
        adapter = self.owner.adapter
        if not getattr(adapter, "remaining_budget_output_v103", False):
            return measure  # Qwen and old explicit fixtures retain their frozen cap.
        try:
            member = self._turn["member_id"]
            meter, team, local_limit = self._budget_sources_v103[member]
            state = team.snapshot()
            if state.get("integrity_failure") or adapter.ledger.inflight is not None:
                raise ValueError("Unsettled or untrusted usage cannot acquire extra headroom")
            values = {
                "local_available_tokens": local_limit - meter["budget_accounted_tokens"],
                "team_available_tokens": state["available_tokens"],
                "adapter_available_tokens": adapter.ledger.token_budget - adapter.ledger.actual,
            }
            if any(type(value) is not int or value < 0 for value in values.values()):
                raise ValueError("Budget sources lack a trustworthy nonnegative remainder")
            available = min(values.values())
            cap = affordable_output_cap(measure["prompt_tokens"], available)
            pending = self._prepared
            wire = copy.deepcopy(pending["wire"])
            wire["max_tokens"] = cap
            if cap != original.MAX_OUTPUT_TOKENS:
                counted = adapter.count(wire)
                if (counted["prompt_tokens"] != measure["prompt_tokens"]
                        or counted.get("request_sha256") != digest(json_bytes(wire))):
                    raise ValueError("Changing only output cap unexpectedly changed the counted prompt")
                pending["projection"]["measurement"] = counted
            adjustment = {"version": VERSION, **values, "available_tokens": available,
                "team_state_sha256": state["state_sha256"],
                "maximum_output_tokens": original.MAX_OUTPUT_TOKENS,
                "actual_output_cap": cap, "reduced": cap != original.MAX_OUTPUT_TOKENS,
                "input_and_history_unchanged": True, "automatic_submission": False,
                "no_positive_output_room": available <= measure["prompt_tokens"]}
            measure.update(version=PREPARATION_VERSION, reserved_output_tokens=cap,
                wire_request_sha256=digest(json_bytes(wire)), output_budget_adjustment=adjustment)
            measure["preparation_sha256"] = digest(json_bytes(
                {key: value for key, value in measure.items() if key != "preparation_sha256"}))
            pending["wire"], pending["measurement"] = wire, copy.deepcopy(measure)
            pending["projection"].update(reserved_output_tokens=cap,
                wire_request_sha256=measure["wire_request_sha256"], output_budget_adjustment=adjustment)
            return copy.deepcopy(measure)
        except BaseException:
            self.discard_prepared_request(request)
            raise


def model_reservation(request, prepared):
    if not prepared or prepared.get("version") != PREPARATION_VERSION:
        return original.model_reservation(request, prepared)
    unsealed = {key: value for key, value in prepared.items() if key != "preparation_sha256"}
    prompt, output = prepared.get("prompt_tokens"), prepared.get("reserved_output_tokens")
    adjustment = prepared.get("output_budget_adjustment", {})
    if (prepared.get("preparation_sha256") != digest(json_bytes(unsealed))
            or prepared.get("original_request_sha256") != digest(json_bytes(request))
            or prepared.get("context_limit") != original.CONTEXT_LIMIT
            or type(prompt) is not int or prompt < 0
            or type(output) is not int or not 0 < output <= original.MAX_OUTPUT_TOKENS
            or adjustment.get("version") != VERSION
            or adjustment.get("actual_output_cap") != output
            or output != affordable_output_cap(prompt, adjustment.get("available_tokens"))):
        raise ValueError("Adaptive output reservation lacks its exact measured preparation")
    # Reuse the original fixed input/context validation without changing that contract.
    fixed = copy.deepcopy(prepared)
    fixed.update(version="v064-managed-budget-preparation-r1",
                 reserved_output_tokens=original.MAX_OUTPUT_TOKENS)
    fixed["preparation_sha256"] = digest(json_bytes(
        {key: value for key, value in fixed.items() if key != "preparation_sha256"}))
    result = original.model_reservation(request, fixed)
    result.update(output_token_reservation=output, token_reservation=prompt + output,
                  preparation=copy.deepcopy(prepared))
    return result


class RemainingBudgetAccountant(ModelPolicy):
    def _reserve(self, request, *, prepared=None, actor_identity=None):
        return model_reservation(request, prepared)


def install_worker_budget(worker):
    """Install on a new worker only; standalone constructor fixtures need no ledger."""
    worker._accountant = RemainingBudgetAccountant(worker.config, transport=worker.transport)
    worker._accountant.bind_event_sink(worker._emit)
    if isinstance(worker.transport, RemainingBudgetContextTransport):
        worker.transport.bind_budget_sources(worker.role_id, meter=worker.meter,
            team_budget=worker.team_budget, local_limit=worker.config["budget"]["max_total_tokens"])


class RemainingBudgetDeepSeekAdapter(remote.DeepSeekEpisodeAdapter):
    """The same episode/host/cash accounting with actual per-request max_tokens."""
    remaining_budget_output_v103 = True

    def complete(self, request, usage_id="agent"):
        if usage_id not in {"agent", "condenser"}:
            raise ValueError("Only the one agent and its condenser may generate")
        with self.lock:
            if self.halted or self.ledger.inflight:
                raise remote.RemoteEpisodeBoundary("episode_closed_or_uncertain_usage")
            if self.soft_at is not None and time.monotonic() >= self.soft_at:
                raise remote.RemoteEpisodeBoundary("soft_deadline_before_dispatch")
            cap = request.get("max_tokens")
            if type(cap) is not int or not 0 < cap <= self.maximum_output_tokens:
                raise ValueError("Requested output must remain within the fixed maximum")
            expected = self.request(request["messages"], request.get("tools"))
            expected["max_tokens"] = cap
            if request != expected:
                raise ValueError("Request differs from the fixed provider configuration")
            if usage_id == "condenser" and request.get("tools"):
                raise ValueError("The original condenser cannot acquire tools")
            if self.arm == "REF" and usage_id == "agent":
                if {tool["function"]["name"] for tool in request.get("tools", [])} != remote.NATIVE_TOOLS:
                    raise ValueError("Native REF must retain its exact five local tools")
            measured = self.count(request)
            reservation = measured["prompt_tokens"] + cap
            if measured["prompt_tokens"] > self.maximum_input_tokens:
                raise remote.RemoteEpisodeBoundary("conservative_context_reservation_exhausted")
            if self.ledger.attempts >= 512 or (usage_id == "agent" and self.ledger.decisions >= 512):
                raise remote.RemoteEpisodeBoundary("episode_call_limit")
            if self.ledger.actual + reservation > self.ledger.token_budget:
                raise remote.RemoteEpisodeBoundary("episode_token_reservation_exhausted")
            index = self.ledger.attempts + 1
            ref = write_new(self.folder / f"request-{index:04d}.json", {
                "request": request, "measurement": measured, "usage_id": usage_id,
                "output_budget_policy": VERSION, "actual_output_cap": cap})
            inflight = {"attempt": index, "usage_id": usage_id, "reservation": reservation,
                "request": ref, "request_id": self.slot_id + f":{index:04d}", "max_output_tokens": cap}
            self.ledger.inflight = inflight
            self.ledger.attempts += 1
            self.ledger.decisions += usage_id == "agent"
            self.save()

            def unstarted(reason):
                self.ledger.inflight = None
                self.ledger.attempts -= 1
                self.ledger.decisions -= usage_id == "agent"
                self.halted = reason
                self.save()
                raise remote.RemoteEpisodeBoundary(reason)

            try:
                while True:
                    if self.soft_at is not None and time.monotonic() >= self.soft_at:
                        unstarted("soft_deadline_during_provider_admission_wait")
                    try:
                        body = self.post("/chat/completions", {
                            "wire": request, "request_id": inflight["request_id"],
                            "slot_id": self.slot_id, "condition": self.condition_id,
                            "usage_id": usage_id, "prompt_upper_bound": measured["prompt_tokens"]})
                        break
                    except remote.api.PreDispatchConcurrencyBusy:
                        time.sleep(0.5)
            except remote.api.PreDispatchBudgetStopped as error:
                unstarted(str(error))
            except remote.api.ProviderOutputBoundViolation as error:
                if error.authoritative_response is not None:
                    self._record(inflight, error.authoritative_response)
                self.halted = str(error)
                self.save()
                raise
            except BaseException as error:
                self.halted = type(error).__name__
                self.save()
                raise
            try:
                normalized = self._record(inflight, body)
                if (normalized["input_tokens"] > measured["prompt_tokens"]
                        or normalized["output_tokens"] > cap):
                    raise remote.api.ProviderOutputBoundViolation(
                        "actual_usage_exceeded_engineering_reservation", body=body)
                message = body["choices"][0]["message"]
                if request.get("tools") and not isinstance(message.get("reasoning_content"), str):
                    raise remote.api.ProviderOutputBoundViolation("missing_original_thinking_response", body=body)
                self.history.remember(message)
                self.save()
                return body
            except BaseException as error:
                self.halted = type(error).__name__
                self.save()
                raise
