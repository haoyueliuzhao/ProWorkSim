"""Host admission for two independent MP sessions; no model/numerical changes."""
from __future__ import annotations

import copy
from contextlib import contextmanager
import json
import time

from .software_benchmark_interleaved_owner_v054 import (
    InterleavedOwnerClient, InterleaveNotDispatched,
)
from .software_benchmark_owner_ipc_v054 import OwnerClient
from .software_benchmark_runner_transport_v054 import HostDeadline, RemoteMatchAdapter, RemoteProjectOwner
from .software_benchmark_normal_boundary_v054 import NormalEpisodeBoundary, known_boundary
from .software_benchmark_match_v054 import DispatchStopped
from .software_organization_runtime_v047 import (
    AdministrativeSoftDeadline, NativeDispatchGate,
)
from .software_calibration_collector_v051 import _CollectionOwner, SoftwareContextTransport
from .storage import atomic_write, json_bytes

PROTOCOL = "mp-interleave-v1"
BOUNDARY = "interleaved_request_queue_deadline_before_dispatch"


class InterleavedHostDeadline(HostDeadline):
    @contextmanager
    def request(self, arm):
        if arm not in {"MATCH", "PROJECT"}:
            raise ValueError("Interleaving does not change REF deadlines")
        if time.monotonic() >= self.start["soft_at"]:
            raise NormalEpisodeBoundary("soft_deadline_before_new_dispatch")
        guard = json.loads(self.path.read_text())
        if guard["stop_requested"]:
            raise DispatchStopped("host_closed_dispatch")
        guard["request_deadline"] = min(self.start["hard_at"], time.monotonic() + 660)
        atomic_write(self.path, json_bytes(guard))
        try:
            yield
        except (NormalEpisodeBoundary, AdministrativeSoftDeadline,
                InterleaveNotDispatched, InterleaveEpisodeBoundary):
            # Undispatched proof is validated by the caller before normal close.
            # The independent hard/request clock remains armed throughout.
            raise
        except BaseException:
            guard["stop_requested"] = True
            atomic_write(self.path, json_bytes(guard))
            raise
        finally:
            guard["stop_requested"] |= (time.monotonic() >= guard["request_deadline"]
                                        or json.loads(self.path.read_text())["stop_requested"])
            guard["request_deadline"] = None
            atomic_write(self.path, json_bytes(guard))


def interleaved(identity):
    return identity.get("session_protocol") == PROTOCOL and identity.get("maximum_sessions") == 2


def owner_client(socket_path, identity, *, guard_path=None, hard_deadline=None):
    if interleaved(identity):
        return InterleavedOwnerClient(socket_path, identity, guard_path=guard_path,
                                      hard_deadline=hard_deadline)
    return OwnerClient(socket_path, identity)


def cancellation(error, client, operation):
    """Only a server-confirmed, exactly bound uncommitted ticket has zero usage."""
    proof = copy.deepcopy(error.receipt)
    if (type(error) is not InterleaveNotDispatched
            or proof.get("dispatched") is not False
            or proof.get("generation_calls") != 0
            or proof.get("original_operation") != operation
            or proof.get("session_claim") != client.identity.get("session_claim_id")
            or not proof.get("request_id")
            or proof.get("usage_unknown") is not False):
        raise ValueError("No exact server proof of an undispatched request")
    return {"reason": BOUNDARY, "server_reason": error.reason,
            "receipt": proof, "receipt_reference": error.receipt_reference,
            "generation_retried": False, "model_failure": False}


class InterleaveEpisodeBoundary(BaseException):
    def __init__(self, evidence):
        super().__init__(BOUNDARY)
        self.evidence = evidence


def unwrap_interleave_boundary(error):
    if type(error) is InterleaveEpisodeBoundary:
        return error
    # SDK versions may wrap BaseException during conversation shutdown.
    from openhands.sdk.conversation.exceptions import ConversationRunError
    if (type(error) is ConversationRunError
            and type(error.original_exception) is InterleaveEpisodeBoundary
            and error.__cause__ is error.original_exception):
        return error.original_exception
    return None


class InterleavedMatchAdapter(RemoteMatchAdapter):
    def _cancel(self, error, operation):
        proof = cancellation(error, self.client, operation)
        ledger = error.receipt.get("ledger")
        if (not isinstance(ledger, dict) or ledger.get("inflight") is not None
                or ledger.get("uncertain_reserved_tokens", 0)
                or type(ledger.get("complete_actual_tokens")) is not int
                or ledger["complete_actual_tokens"] != ledger.get("known_actual_tokens")):
            raise ValueError("Undispatched MATCH boundary lacks the authoritative complete ledger")
        self.ledger.update(ledger)
        atomic_write(self.ledger.directory / "interleaved-queue-boundary.json", json_bytes(proof))
        raise InterleaveEpisodeBoundary(proof)

    def count(self, request):
        with self.gate.request("MATCH"):
            try:
                return self.client.call("match_count", request=request)
            except InterleaveNotDispatched as error:
                self._cancel(error, "match_count")

    def complete(self, request, usage_id):
        with self.gate.request("MATCH"):
            try:
                result = self.client.call("match_complete", request=request, usage_id=usage_id)
            except InterleaveNotDispatched as error:
                self._cancel(error, "match_complete")
            except BaseException:
                atomic_write(self.ledger.directory / "transport-unknown.json", json_bytes({
                    "actual_usage": None, "authoritative_ledger": "model-service/match-ledger/ledger.json",
                    "automatic_retry": False}))
                raise
            self.ledger.update(result["ledger"])
            if result.get("terminal_boundary"):
                boundary = result["terminal_boundary"]
                if known_boundary(DispatchStopped(boundary["reason"]), result["ledger"]) != boundary:
                    raise RuntimeError("Original numerical terminal boundary is not fully accounted")
                raise NormalEpisodeBoundary(boundary["reason"])
            return result["body"]


class InterleavedProjectOwner(RemoteProjectOwner):
    def complete(self, request, *, timeout_seconds):
        if timeout_seconds != 600 or not getattr(self, "_admitted_turn", False):
            raise ValueError("PROJECT requires its original timeout and a separately admitted turn")
        # The outer gate spans queue admission and execution: never reset its
        # original 660-second deadline after waiting for the GPU.
        return self.client.call("project_complete", request=request)


class InterleavedProjectDispatchGate(NativeDispatchGate):
    def __init__(self, transport, deadline):
        super().__init__(transport, deadline)
        self.scheduler_boundaries = []

    def complete(self, request, **kwargs):
        owner = self.transport
        turn = self.context._turn if self.context is not None else None
        if not turn or self.runtime is None:
            raise ValueError("Interleaved PROJECT needs its exact original worker/call scope")
        member, call_id = turn["member_id"], turn["association"]["call_id"]
        try:
            with owner.gate.request("PROJECT"):
                try:
                    with owner.client.turn("project_complete", request=request):
                        owner._admitted_turn = True
                        try:
                            # The original trusted dispatch marker is after a
                            # nonexecuting FIFO grant; call() then commits it.
                            return super().complete(request, **kwargs)
                        finally:
                            owner._admitted_turn = False
                except InterleaveNotDispatched as error:
                    proof = cancellation(error, owner.client, "project_complete")
                    if call_id in self.deadline.dispatches:
                        # Preserve the actual host commitment and held cost;
                        # this exception is inside the host guard so it stops
                        # this episode's writer scopes immediately.
                        raise RuntimeError("FIFO admission expired after trusted dispatch commitment") from error
                    self.deadline.now()
                    proof.update(member_id=member, call_id=call_id)
                    self.deadline.cancel(member, call_id, self.runtime.team_budget, reason=BOUNDARY)
                    self.runtime.policies[member].cancel_pending_dispatch(call_id)
                    self.deadline.prevented_work = True
                    self.scheduler_boundaries.append(proof)
                    self.runtime.recorder.record("interleaved_request_cancelled_before_dispatch", proof,
                                                 worker_id=member)
                    raise AdministrativeSoftDeadline(BOUNDARY)
        except NormalEpisodeBoundary as error:
            if str(error) != "soft_deadline_before_new_dispatch" or call_id in self.deadline.dispatches:
                raise
            self.deadline.now()
            self.deadline.cancel(member, call_id, self.runtime.team_budget,
                                 reason="soft_deadline_before_dispatch")
            self.runtime.policies[member].cancel_pending_dispatch(call_id)
            self.deadline.soft_triggered = self.deadline.prevented_work = True
            raise AdministrativeSoftDeadline("Original soft cutoff before FIFO admission") from error


def context_transport(owner, directory, deadline):
    gate = InterleavedProjectDispatchGate(owner.transport, deadline)
    context = SoftwareContextTransport(_CollectionOwner(owner, gate), directory)
    gate.context = context
    context.native_dispatch_gate = gate
    return context
