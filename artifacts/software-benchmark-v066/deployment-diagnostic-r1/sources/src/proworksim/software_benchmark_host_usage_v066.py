"""Durable per-slot Qwen forwarding journal and bounded interruption recovery.

This trusted-host layer keeps the frozen v064 wire/model contract. It creates
no service, network listener, container or GPU allocation. Counting is reused
from the actual preceding tokenizer reply; a missing response retains its
original reservation and never becomes fabricated zero usage.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import threading
import time

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_exact_transport_v054 import REF_MODEL, TEMPLATE_KEYS, HTTPFailure, LoopbackHTTP
from .software_benchmark_ref_budget_v064 import validate_condition
from .software_benchmark_full_plan_v064 import group_profiles
from .software_benchmark_model_fifo_v064 import (
    CancellableLoopbackHTTP, PORTS, DEEPSEEK_PORT, MAX_COUNT_REQUESTS,
    MAX_GENERATION_REQUESTS, MAX_REQUESTS, decode_frame, encoded_frame, model_response,
    VERSION as WIRE_VERSION,
)
from .storage import atomic_write, digest, json_bytes

VERSION = "v066-durable-host-qwen-forwarding-r1"


class HostUsageIntegrityError(RuntimeError):
    """Journal/source/provider contradictions cannot be treated as local usage gaps."""


def _durable_new(path, value):
    result = write_new(path, value)
    descriptor = os.open(str(Path(path).parent), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return result


def _load(path):
    value = json.loads(Path(path).read_bytes())
    if not isinstance(value, dict):
        raise HostUsageIntegrityError("A journal entry is not an object")
    return value


def _template(payload):
    return {key: copy.deepcopy(payload[key]) for key in TEMPLATE_KEYS if key in payload}


def read_host_ledger(folder, *, expected_slot_id=None):
    """Recover from immutable dispatch/settlement receipts, not a cached total."""
    folder = Path(folder)
    manifest = _load(folder / "manifest.json")
    profile = group_profiles().get(manifest.get("condition_id"))
    if (manifest.get("version") != VERSION or manifest.get("model_key") != "QWEN"
            or profile is None or profile.get("model_key") != "QWEN"
            or manifest.get("token_limit") != profile["input_plus_output_tokens"]
            or manifest.get("all_model_attempt_limit") != 512 or manifest.get("agent_decision_limit") != 512
            or manifest.get("service_identity_sha256") != digest(json_bytes(manifest.get("service_identity")))
            or expected_slot_id is not None and manifest.get("slot_id") != expected_slot_id):
        raise HostUsageIntegrityError("The journal belongs to another slot or implementation")
    intents = sorted((folder / "dispatches").glob("*.json"))
    settlements = sorted(folder.glob("[0-9][0-9][0-9][0-9].json"))
    if len(intents) > manifest["all_model_attempt_limit"]:
        raise HostUsageIntegrityError("The host journal exceeds its original attempt bound")
    calls, pending, ids, known, decisions = [], [], set(), 0, 0
    for number, path in enumerate(intents, 1):
        item = _load(path)
        if (path.name != f"{number:04d}.json" or item.get("attempt") != number
                or item.get("version") != VERSION or item.get("slot_id") != manifest["slot_id"]
                or item.get("condition_id") != manifest["condition_id"]
                or item.get("service_identity_sha256") != manifest["service_identity_sha256"]
                or item.get("usage_id") not in {"agent", "condenser"}
                or type(item.get("prompt_tokens")) is not int
                or not 0 <= item["prompt_tokens"] <= 98304
                or item.get("maximum_output_tokens") != 32768
                or item.get("reservation") != item["prompt_tokens"] + 32768
                or item.get("written_before_forward") is not True):
            raise HostUsageIntegrityError("The durable forwarding intent is invalid")
        counter = _load(checked(item["exact_count_receipt"]))
        if (counter.get("template_sha256") != item.get("template_sha256")
                or counter.get("count") != item["prompt_tokens"]
                or counter.get("slot_id") != manifest["slot_id"]):
            raise HostUsageIntegrityError("The reserved request lost its exact tokenizer binding")
        decisions += item["usage_id"] == "agent"
        response_path = folder / f"{number:04d}.json"
        if not response_path.exists():
            pending.append({**item, "request": reference(path), "status": "outcome_unresolved",
                            "reservation_is_actual_usage": False})
            continue
        result = _load(response_path)
        usage = result.get("usage", {})
        if (result.get("slot_id") != manifest["slot_id"] or result.get("attempt") != number
                or result.get("dispatch") != reference(path) or result.get("usage_valid") is not True
                or result.get("before_controller_forward") is not True
                or result.get("request_sha256") != item["request_sha256"]
                or result.get("model") != REF_MODEL or not isinstance(result.get("call_id"), str)
                or not result["call_id"] or result["call_id"] in ids
                or any(type(usage.get(k)) is not int for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
                or usage["prompt_tokens"] != item["prompt_tokens"]
                or not 0 < usage["completion_tokens"] <= 32768
                or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]):
            raise HostUsageIntegrityError("The durable model response contradicts its original reservation")
        ids.add(result["call_id"])
        known += usage["total_tokens"]
        calls.append({"attempt": number, "usage_id": item["usage_id"],
            "reservation": item["reservation"], "prompt_tokens": item["prompt_tokens"],
            "request": reference(path), "response": reference(response_path),
            "native_attempt_id": result["call_id"], "usage": copy.deepcopy(usage),
            "finish_reason": result.get("finish_reason")})
    if any(int(path.stem) > len(intents) for path in settlements):
        raise HostUsageIntegrityError("A response exists without a prior durable forwarding intent")
    held = sum(row["reservation"] for row in pending)
    if (len(pending) > 1 or decisions > manifest["agent_decision_limit"]
            or known + held > manifest["token_limit"]):
        raise HostUsageIntegrityError("The local slot has exceeded its frozen bounded accounting")
    fault = _load(folder / "integrity-failure.json") if (folder / "integrity-failure.json").exists() else None
    if fault is not None:
        raise HostUsageIntegrityError("Host usage journal has a retained integrity failure: " + str(fault.get("reason")))
    return {"version": VERSION, "slot_id": manifest["slot_id"],
        "condition_id": manifest["condition_id"], "attempts": len(intents), "decisions": decisions,
        "decisions_scope": "forwarded agent calls only; controller administrative unsent decisions are separate",
        "calls": calls, "known_actual_tokens": known,
        "complete_actual_tokens": None if pending else known,
        "uncertain_reserved_tokens": held, "inflight": pending[0] if pending else None,
        "token_limit": manifest["token_limit"], "all_model_attempt_limit": manifest["all_model_attempt_limit"],
        "agent_decision_limit": manifest["agent_decision_limit"], "local_dollar_cost_estimate": None,
        "automatic_retry": False, "host_accounting_authority": True,
        "manifest": reference(folder / "manifest.json"),
        "bounded_unknown_is_slot_local": True, "unresolved_reservations_are_not_actual_tokens": True}


class HostUsageTransport:
    """Persist each possible generation before sending and actual usage before reply."""
    def __init__(self, delegate, folder, slot_id, *, condition, service_identity):
        limits = validate_condition(condition)
        if condition["model_key"] != "QWEN" or condition["condition_id"] not in slot_id:
            raise ValueError("Host Qwen accounting must bind this exact original condition")
        self.delegate, self.folder, self.slot_id = delegate, Path(folder), slot_id
        self.folder.mkdir(parents=True, exist_ok=False)
        parent_fd = os.open(str(self.folder.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        (self.folder / "counts").mkdir()
        (self.folder / "dispatches").mkdir()
        self.lock, self.counts = threading.RLock(), {}
        self.count_requests, self.blocked_requests = 0, 0
        self.manifest = {"version": VERSION, "slot_id": slot_id, "model_key": "QWEN",
            "condition_id": condition["condition_id"], "token_limit": limits["input_plus_output_tokens"],
            "all_model_attempt_limit": limits["all_model_attempts"], "agent_decision_limit": limits["agent_decisions"],
            "service_identity_sha256": digest(json_bytes(service_identity)),
            "service_identity": copy.deepcopy(service_identity), "automatic_retry": False,
            "source_of_reservation": "original full exact tokenizer count plus original 32768 output ceiling"}
        _durable_new(self.folder / "manifest.json", self.manifest)
        self._save()

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def snapshot(self):
        with self.lock:
            return read_host_ledger(self.folder, expected_slot_id=self.slot_id)

    def _save(self):
        value = self.snapshot()
        atomic_write(self.folder / "ledger.json", json_bytes(value))
        return value

    def _integrity(self, reason, **details):
        target = self.folder / "integrity-failure.json"
        if not target.exists():
            _durable_new(target, {"version": VERSION, "slot_id": self.slot_id,
                                  "reason": reason, **details})
        raise HostUsageIntegrityError(reason)

    def _before_dispatch_reject(self, reason):
        self.blocked_requests += 1
        _durable_new(self.folder / f"predispatch-rejected-{self.blocked_requests:04d}.json", {
            "version": VERSION, "slot_id": self.slot_id, "reason": reason,
            "provider_post_entered": False, "actual_model_calls": 0})
        raise HTTPFailure("Host rejected before forwarding: " + reason)

    def post(self, path, payload):
        if path == "/tokenize":
            response = self.delegate.post(path, payload)
            ids, count = response.get("tokens"), response.get("count")
            if (not isinstance(ids, list) or type(count) is not int or count != len(ids)
                    or response.get("max_model_len") != 131072
                    or payload.get("model") != REF_MODEL):
                self._integrity("Tokenizer response differs from the frozen local model contract")
            with self.lock:
                self.count_requests += 1
                key = digest(json_bytes(payload))
                proof = _durable_new(self.folder / "counts" / f"{self.count_requests:04d}.json", {
                    "version": VERSION, "slot_id": self.slot_id, "template_sha256": key,
                    "count": count, "token_ids_sha256": digest(json_bytes(ids)),
                    "max_model_len": 131072, "generation_attempt": False})
                old = self.counts.get(key)
                if old is not None and old["count"] != count:
                    self._integrity("The same frozen template produced contradictory exact counts")
                self.counts[key] = {"count": count, "proof": proof}
            return response
        if path != "/v1/chat/completions":
            raise ValueError("Only the original local model and tokenizer endpoints are allowed")
        with self.lock:
            state = self.snapshot()
            key = digest(json_bytes(_template(payload)))
            measured = self.counts.get(key)
            if (payload.get("model") != REF_MODEL or payload.get("max_tokens") != 32768
                    or payload.get("stream") is not False or measured is None):
                self._before_dispatch_reject("The generation lacks its original exact count or fixed model ceiling")
            count = measured["count"]
            if not 0 <= count <= 98304:
                self._before_dispatch_reject("The complete input exceeds the original input ceiling")
            purpose = "agent" if payload.get("tools") else "condenser"
            reservation = count + 32768
            if (state["inflight"] is not None or state["attempts"] >= self.manifest["all_model_attempt_limit"]
                    or purpose == "agent" and state["decisions"] >= self.manifest["agent_decision_limit"]
                    or state["known_actual_tokens"] + reservation > self.manifest["token_limit"]):
                self._before_dispatch_reject("The original slot budget cannot reserve another complete response")
            number = state["attempts"] + 1
            intent = {"version": VERSION, "slot_id": self.slot_id,
                "condition_id": self.manifest["condition_id"], "attempt": number, "usage_id": purpose,
                "request_sha256": digest(json_bytes(payload)), "template_sha256": key,
                "service_identity_sha256": self.manifest["service_identity_sha256"],
                "exact_count_receipt": measured["proof"], "prompt_tokens": count,
                "maximum_output_tokens": 32768, "reservation": reservation,
                "written_before_forward": True, "dispatch_intent_is_proof_of_actual_generation": False,
                "created_unix": time.time()}
            intent_ref = _durable_new(self.folder / "dispatches" / f"{number:04d}.json", intent)
            self._save()
        # No forward can precede its durable intent. Any interruption from here
        # keeps that exact reservation unless a complete valid response settles.
        try:
            response = self.delegate.post(path, payload)
        except BaseException as error:
            with self.lock:
                _durable_new(self.folder / f"transport-failure-{number:04d}.json", {
                    "version": VERSION, "slot_id": self.slot_id, "attempt": number,
                    "dispatch": intent_ref, "exception_type": type(error).__name__,
                    "outcome": "unknown_after_forwarding_entry", "reservation_retained": True})
                self._save()
            raise
        with self.lock:
            usage, choices = response.get("usage", {}), response.get("choices", [])
            current = self.snapshot()
            details = usage.get("completion_tokens_details") if isinstance(usage, dict) else None
            reasoning = details.get("reasoning_tokens") if isinstance(details, dict) else None
            valid = (response.get("model") == REF_MODEL and isinstance(response.get("id"), str)
                and bool(response["id"]) and response["id"] not in {c["native_attempt_id"] for c in current["calls"]}
                and isinstance(choices, list) and len(choices) == 1
                and isinstance(choices[0], dict) and choices[0].get("index") == 0
                and isinstance(choices[0].get("message"), dict)
                and choices[0]["message"].get("role") == "assistant"
                and choices[0].get("finish_reason") in {"stop", "length", "tool_calls"}
                and isinstance(usage, dict)
                and all(type(usage.get(k)) is int for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
                and usage["prompt_tokens"] == count and 0 < usage["completion_tokens"] <= 32768
                and usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"])
            valid = valid and (details is None or isinstance(details, dict)) and (
                reasoning is None or type(reasoning) is int and 0 <= reasoning <= usage["completion_tokens"])
            if not valid:
                self._integrity("Model response identity or actual usage violates its exact reservation",
                    attempt=number, response_sha256=digest(json_bytes(response)), reported_usage=usage)
            _durable_new(self.folder / f"{number:04d}.json", {"version": VERSION,
                "slot_id": self.slot_id, "attempt": number, "dispatch": intent_ref,
                "call_id": response["id"], "purpose": purpose, "usage": copy.deepcopy(usage),
                "usage_valid": True, "model": response["model"],
                "finish_reason": choices[0]["finish_reason"], "request_sha256": intent["request_sha256"],
                "response_sha256": digest(json_bytes(response)), "before_controller_forward": True,
                "provider_key_recorded": False})
            self._save()
        return response


def reconcile_host_usage(result, host_ledger):
    """Use retained actual responses even if the controller never received them."""
    old = result.get("ledger")
    if isinstance(old, dict):
        host_by_id = {call["native_attempt_id"]: call for call in host_ledger["calls"]}
        for call in old.get("calls", []):
            actual = host_by_id.get(call.get("native_attempt_id"))
            if actual is None or actual.get("usage") != call.get("usage"):
                raise HostUsageIntegrityError("Controller usage has no identical durable host response")
        if old.get("complete_actual_tokens") is not None and (
                old.get("known_actual_tokens") != host_ledger["known_actual_tokens"]
                or host_ledger["uncertain_reserved_tokens"]):
            raise HostUsageIntegrityError("Complete controller accounting contradicts the host journal")
        result["controller_ledger_before_host_reconciliation"] = copy.deepcopy(old)
    result["ledger"] = copy.deepcopy(host_ledger)
    if isinstance(old, dict) and type(old.get("decisions")) is int:
        if not host_ledger["decisions"] <= old["decisions"] <= host_ledger["agent_decision_limit"]:
            raise HostUsageIntegrityError("Controller decisions cannot contradict forwarded agent attempts")
        result["ledger"]["decisions"] = old["decisions"]
        result["ledger"]["decisions_scope"] = "original controller decisions, including its unsent budget-boundary decisions"
    result["host_possible_forwarded_attempts"] = host_ledger["attempts"]
    # Actual forwarding counts and permission to re-enter a slot are separate.
    # Counting-only RPCs may prove zero generation, while the original entered
    # intent remains true. Only zero_request_recovery supplies the stronger
    # immutable proof used by a separately reviewed continuation inventory.
    result.setdefault("original_model_dispatch_started_before_host_reconciliation",
                      result.get("model_dispatch_started"))
    result["model_calls"] = host_ledger["attempts"]
    result.setdefault("zero_model_generation_proven", False)
    result["host_accounting_recovered"] = not isinstance(old, dict) or old.get("complete_actual_tokens") is None
    result["known_actual_tokens"] = host_ledger["known_actual_tokens"]
    return result


def zero_request_recovery(result, *, bridge, writers, cleanup, host_ledger=None):
    """Return a proof only for a finished, clean channel with literally zero RPCs."""
    if (result.get("model_bridge_thread_finished") is not True or bridge.get("ready") is not True
            or bridge.get("version") != WIRE_VERSION
            or bridge.get("status") not in {"channel_closed", "stopped_after_controller"}
            or any(type(bridge.get(k)) is not int or bridge[k] != 0 for k in
                   ("requests", "failed_requests", "count_requests", "generation_requests", "predispatch_admission_replies"))
            or bridge.get("error") or writers.get("all_quiet") is not True or writers.get("errors") != []
            or writers.get("create_result_unknown_roles") != []
            or cleanup.get("quiescent") is not True or cleanup.get("cleanup_errors") != []
            or cleanup.get("create_result_unknown") is not False or cleanup.get("create_result_unknown_roles", [])):
        return None
    rows = writers.get("writers")
    if (not isinstance(rows, list) or len(rows) != 2 or {r.get("role") for r in rows} != {"actor", "controller"}
            or any(r.get("state", {}).get("Running") is not False or r.get("state", {}).get("Pid") != 0
                   for r in rows)):
        return None
    if host_ledger is not None and any(host_ledger.get(k) != 0 for k in
            ("attempts", "known_actual_tokens", "complete_actual_tokens", "uncertain_reserved_tokens")):
        return None
    return {"version": VERSION, "slot_id": result["slot_id"], "proved_no_model_RPC": True,
        "actual_model_calls": 0, "actual_input_output_tokens": 0,
        "prior_model_calls": result.get("model_calls"),
        "prior_model_dispatch_started": result.get("model_dispatch_started"),
        "dispatch_intent_preserved": True, "bridge": copy.deepcopy(bridge),
        "writers_quiescent": True, "owned_cleanup_quiescent": True,
        "absence_of_usage_files_is_not_the_proof": True}


def serve_model_channel(channel, *, endpoint, key_file, deadline, stop_event, slot_id,
                        on_ready=None, transport=None):
    """Host thread: only this ordinary process sees the resident authentication key.

    channel is the DockerStdioChannel supplied by the owned actor runtime. It
    separates Docker stderr from stdout and enforces its own bounded line size.
    """
    from .software_benchmark_dispatch_v066 import require_v066_allowed
    require_v066_allowed("v066.model.bridge", slot_id=slot_id)
    client = transport or CancellableLoopbackHTTP(endpoint, key_file)
    if client.port not in PORTS or client.timeout_seconds != 1800:
        raise ValueError("The host model route must retain the original admitted port and timeout")
    if client.port != LoopbackHTTP(endpoint).port:
        raise ValueError("Model broker endpoint and admitted service identity differ")
    if client.port == DEEPSEEK_PORT:
        client.validate_identity(slot_id)
    result = {"version": WIRE_VERSION, "ready": False, "requests": 0, "failed_requests": 0,
              "count_requests": 0, "generation_requests": 0, "predispatch_admission_replies": 0,
              "model_key_sent_to_container": False, "host_listener": False, "automatic_retries": 0}
    try:
        ready = decode_frame(channel.readline(deadline=min(deadline, time.monotonic() + 20)))
        if ready != {"type": "model_bridge_ready", "version": WIRE_VERSION}:
            raise ValueError("Controller model FIFO bridge did not initialize")
        result["ready"] = True
        if on_ready is not None:
            on_ready()
        while not stop_event.is_set():
            if time.monotonic() >= deadline:
                raise TimeoutError("Model bridge exceeded episode hard deadline")
            try:
                raw = channel.readline(deadline=min(deadline, time.monotonic() + 1))
            except TimeoutError:
                continue
            except ConnectionResetError as error:
                # This branch is reached only while awaiting the next request,
                # never during the actual model POST or response write. PID1
                # exit may reset its owned exec socket; the controller result
                # must still prove normal completion before the episode counts.
                stdout = getattr(channel, "buffer", None)
                frames = getattr(getattr(channel, "decoder", None), "buffer", None)
                if (not isinstance(stdout, (bytes, bytearray)) or stdout
                        or not isinstance(frames, (bytes, bytearray)) or frames):
                    raise
                result.update(status="channel_closed", requires_controller_exit_classification=True,
                              idle_exec_reset={"type": type(error).__name__, "message": str(error),
                                               "buffered_stdout_bytes": 0, "buffered_frame_bytes": 0})
                return result
            if not raw:
                result.update(status="channel_closed", requires_controller_exit_classification=True)
                return result
            result["requests"] += 1
            if result["requests"] > MAX_REQUESTS:
                raise ValueError("Model bridge request bound exceeded")
            request = decode_frame(raw)
            count_only = request.get("path") in {"/tokenize", "/tokenize-prefix"}
            if count_only:
                result["count_requests"] += 1
                if result["count_requests"] > MAX_COUNT_REQUESTS:
                    raise ValueError("Count-only model RPC limit exceeded")
            elif result["generation_requests"] >= MAX_GENERATION_REQUESTS:
                raise ValueError("Actual model attempt RPC limit exceeded")
            response = model_response(request, client, result["requests"])
            unsent = response.get("provider_failure", {}).get("before_dispatch_proven") is True
            result["predispatch_admission_replies"] += not count_only and unsent
            result["generation_requests"] += not count_only and not unsent
            result["failed_requests"] += response["ok"] is False
            channel.write(encoded_frame(response))
        channel.write(encoded_frame({"op": "stop"}))
        result["status"] = "stopped_after_controller"
    except Exception as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)})
    return result
