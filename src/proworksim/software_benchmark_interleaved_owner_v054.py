"""Two raw owner facades, one FIFO executor, private Torch RNG and bounded tickets.

Only the orchestration is new. Every numerical operation invokes the original
FormalOwnerService and unchanged CalibrationActor.generate_native method.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import functools
import json
import math
import os
from pathlib import Path
import re
import socketserver
import sys
import threading
import time
import uuid

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_match_v054 import CONTRACT
from .software_benchmark_normal_boundary_v054 import FormalOwnerService
from . import software_benchmark_owner_ipc_v054 as original
from .software_benchmark_resident_owner_v054 import make_handler
from .software_benchmark_supervision_v054 import process_identity
from .storage import atomic_write, digest, json_bytes

PROTOCOL = "mp-interleave-v1"
VERSION = "v054-interleaved-raw-owner-r1"
OPERATIONS = {"begin", "match_count", "match_complete", "project_complete", "finish"}
GENERATIONS = {"match_complete", "project_complete"}


class InterleaveNotDispatched(BaseException):
    def __init__(self, body, receipt_reference):
        self.reason, self.receipt, self.receipt_reference = body["reason"], body, receipt_reference
        super().__init__(self.reason)


class InterleavedOwnerClient:
    """Queue before dispatch; no retries, deadline extension or ambiguous zero usage."""
    def __init__(self, socket_path, identity, *, timeout=660, guard_path=None, hard_deadline=None):
        if identity.get("session_protocol") != PROTOCOL or identity.get("maximum_sessions") != 2:
            raise ValueError("An explicitly admitted interleaved session identity is required")
        self.identity, self.path = copy.deepcopy(identity), str(socket_path)
        self.timeout, self.guard_path, self.hard_deadline = timeout, guard_path, hard_deadline
        self.control = original.OwnerClient(socket_path, identity, timeout=5)
        self.execution = original.OwnerClient(socket_path, identity, timeout=timeout)
        self.current = None
        self.last_evidence = None
        self.lock = threading.RLock()

    def _deadline(self):
        limits = [time.monotonic() + min(660, self.timeout)]
        if self.hard_deadline is not None:
            limits.append(self.hard_deadline)
        if self.guard_path is not None:
            guard = json.loads(Path(self.guard_path).read_text())
            if guard.get("stop_requested"):
                limits.append(time.monotonic())
            if guard.get("request_deadline") is not None:
                limits.append(guard["request_deadline"])
        return min(limits)

    def _bound_response(self, value, ticket):
        if (not re.fullmatch(r"[a-f0-9]{32}", value.get("ticket_id", ""))
                or (ticket.get("ticket_id") is not None and value["ticket_id"] != ticket["ticket_id"])
                or value.get("request_id") != ticket["request_id"]
                or value.get("original_operation") != ticket["original_operation"]
                or value.get("session_claim") != self.identity["session_claim_id"]):
            raise ValueError("Response belongs to a different ticket, request, operation or session")
        if value.get("state") == "cancelled":
            body, ref = value["receipt"], value["receipt_reference"]
            encoded = json_bytes(body)
            if (body.get("ticket_id") != value["ticket_id"] or body.get("request_id") != ticket["request_id"]
                    or body.get("original_operation") != ticket["original_operation"]
                    or body.get("session_claim") != self.identity["session_claim_id"]
                    or body.get("dispatched") is not False or body.get("generation_calls") != 0
                    or body.get("usage_unknown") is not False
                    or ref.get("sha256") != digest(encoded) or ref.get("bytes") != len(encoded)
                    or Path(ref.get("path", "")).name != value["ticket_id"] + "-not-dispatched.json"):
                raise ValueError("No exact bound immutable no-dispatch receipt")

    def _cancelled(self, value, ticket):
        self._bound_response(value, ticket)
        if value["state"] == "cancelled":
            raise InterleaveNotDispatched(value["receipt"], value["receipt_reference"])
        if value["state"] == "failed":
            raise RuntimeError("Interleaved execution failed; no automatic replay: " + json.dumps(value["error"]))

    @contextmanager
    def turn(self, operation, **arguments):
        with self.lock:
            if self.current is not None or operation not in OPERATIONS:
                raise ValueError("At most one pending operation per client/session")
            deadline = self._deadline()
            ticket = {"ticket_id": None, "request_id": uuid.uuid4().hex,
                      "original_operation": operation, "original_arguments": copy.deepcopy(arguments),
                      "deadline": deadline, "committed": False}
            submitted = self.control.call("reserve_turn", original_operation=operation,
                original_arguments=arguments, request_id=ticket["request_id"],
                dispatch_deadline=deadline)
            self._bound_response(submitted, ticket)
            ticket["ticket_id"] = submitted["ticket_id"]
            try:
                value = submitted
                while value["state"] != "granted":
                    self._cancelled(value, ticket)
                    if time.monotonic() >= deadline:
                        value = self.control.call("cancel_ticket", ticket_id=ticket["ticket_id"],
                                                  reason="original_client_deadline")
                        self._cancelled(value, ticket)
                        raise RuntimeError("Deadline passed after dispatch; usage cannot be zeroed")
                    time.sleep(min(.05, max(0, deadline - time.monotonic())))
                    value = self.control.call("ticket_status", ticket_id=ticket["ticket_id"])
                    self._bound_response(value, ticket)
                ticket["grant"] = value
                self.current = ticket
                yield ticket
            finally:
                self.current = None
                if not ticket["committed"]:
                    value = self.control.call("cancel_ticket", ticket_id=ticket["ticket_id"],
                                              reason="client_left_uncommitted_turn")
                    self._bound_response(value, ticket)
                    if value["state"] not in {"cancelled"}:
                        raise RuntimeError("Uncommitted turn did not return a no-dispatch proof")

    def call(self, operation, **arguments):
        if operation == "begin" and arguments.get("started") is not None:
            hard = arguments["started"] + 6000
            self.hard_deadline = min(self.hard_deadline, hard) if self.hard_deadline else hard
        with self.lock:
            if self.current is None:
                with self.turn(operation, **arguments):
                    return self.call(operation, **arguments)
            ticket = self.current
            if ticket["original_operation"] != operation or ticket["original_arguments"] != arguments:
                raise ValueError("Commit differs from the immutable preflight request")
            # Mark the client uncertain before sending. A transport failure can
            # never be reclassified as a successful local cancellation.
            ticket["committed"] = True
            self.execution.timeout = max(.001, ticket["deadline"] - time.monotonic())
            value = self.execution.call("dispatch_ticket", ticket_id=ticket["ticket_id"])
            self._cancelled(value, ticket)
            if value["state"] != "complete":
                raise RuntimeError("Dispatch returned without complete execution evidence")
            self.last_evidence = value.get("interleave_evidence")
            return value["result"]


class TorchRNG:
    def __init__(self, owner):
        self.torch = owner.torch

    def read(self):
        return {"cpu": self.torch.get_rng_state().clone(),
                "cuda": [value.clone() for value in self.torch.cuda.get_rng_state_all()]}

    def write(self, value):
        self.torch.set_rng_state(value["cpu"].cpu())
        self.torch.cuda.set_rng_state_all([item.cpu() for item in value["cuda"]])

    def fingerprint(self, value):
        from .online_training import tensor_tree_digest
        return tensor_tree_digest(value, self.torch)

    def synchronize(self):
        self.torch.cuda.synchronize()


class _Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


class InterleavedOwner:
    def __init__(self, owner, *, output, codec=None, synthetic=False, smoke=False,
                 max_smoke_requests=2, resource_binding=None, preparation_authorization=None,
                 maximum_sessions=2, facade_factory=None, rng_backend=None):
        if smoke or codec is None or maximum_sessions != 2:
            raise ValueError("Interleaving requires two sessions and the original codec, not capacity smoke")
        if not synthetic and (facade_factory is not None or rng_backend is not None):
            raise ValueError("Programmed facade/RNG hooks are only allowed in explicit CPU controls")
        self.owner, self.model, self.codec = owner, getattr(owner, "model", owner), codec
        self.synthetic, self.resource_binding = synthetic, resource_binding
        self.preparation_authorization = preparation_authorization
        self.root = Path(output)
        self.root.mkdir(parents=True, exist_ok=True)
        if (self.root / "resident-state.json").exists():
            raise ValueError("A new process cannot resume old in-memory sessions")
        self.rng = rng_backend or TorchRNG(owner)
        self.parked = self.rng.read()
        self.parked_hash = self.rng.fingerprint(self.parked)
        self.owner_identity = owner.freeze_identity()
        self.facades = [self._facade(index, facade_factory) for index in range(2)]
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.sessions, self.tickets, self.sequences = {}, {}, {}
        self.queue, self.used_claims, self.used_slots = [], set(), set()
        self.used_request_ids, self.abort_results, self.closed_claims = set(), {}, {}
        self.current_ticket, self.inflight, self.poisoned = None, None, None
        self.ordinal, self.preparation_calls = 0, 0
        self.socket_root = None
        self.stop_event = threading.Event()
        prototype = FormalOwnerService(self.facades[0], output=self.root / "prototype", codec=codec,
            synthetic=synthetic, resource_binding=resource_binding)
        self.identity = {**prototype.identity, "resident": True, "resident_version": VERSION,
            "resident_id": uuid.uuid4().hex, "session_protocol": PROTOCOL, "maximum_sessions": 2,
            "supported_arms": ["MATCH", "PROJECT"], "resident_source": reference(__file__),
            "resident_owner_process": process_identity(os.getpid()), "resident_model_object_id": id(self.model),
            "model_loads_at_initialization": 0 if synthetic else 1,
            "numerical_methods_replaced": False, "preparation_authorization": preparation_authorization}
        self.executor = threading.Thread(target=self._execute, daemon=True, name="v054-single-native-executor")
        self.executor.start()
        self._save()

    def _facade(self, index, fixture):
        output = self.root / "facades" / str(index)
        output.parent.mkdir(parents=True, exist_ok=True)
        if self.synthetic:
            if fixture is None:
                raise ValueError("CPU control must explicitly provide its non-model facade factory")
            actor = fixture(output)
        else:
            from .software_calibration_runtime_v051 import CalibrationActor
            names = ("base_manifest", "base_revision", "model_path", "raw_release",
                     "trained_adapter_loaded", "checkpoint", "adapter_sha256")
            identity = {key: copy.deepcopy(self.owner_identity[key]) for key in names}
            if (not identity["raw_release"] or identity["trained_adapter_loaded"]
                    or identity["checkpoint"] is not None or identity["adapter_sha256"] is not None):
                raise ValueError("Only the unchanged original raw owner may share weights")
            actor = CalibrationActor(self.owner.model, self.owner.tokenizer, contract=self.owner.contract,
                path="project", output=output, identity=identity, torch_module=self.owner.torch,
                head_execution=self.owner.head_execution,
                historical_steps=(self.owner.actor_steps, self.owner.critic_steps))
            if (actor.model is not self.model or actor.generate_native.__func__ is not CalibrationActor.generate_native
                    or actor.inference_profile != self.owner.inference_profile):
                raise ValueError("Facade altered the real numerical owner")
        if actor.freeze_identity() != self.owner_identity or actor.contract != CONTRACT:
            raise ValueError("A facade changed the original actor identity or contract")
        return actor

    def status(self):
        with self.lock:
            sessions = {claim: {"session_slot": item["session_slot"], "phase": item["phase"],
                "queued": item.get("queued") or False, "dispatched": item.get("dispatched") or False}
                for claim, item in self.sessions.items()}
            slots = {item["session_slot"] for item in sessions.values()}
            return {"resident": True, "state": "poisoned" if self.poisoned else "busy" if sessions else "idle",
                "poisoned": self.poisoned, "active_claims": list(sessions), "sessions": sessions,
                "inflight": self.inflight, "available_session_slots": sorted({0, 1} - slots),
                "session_protocol": PROTOCOL, "maximum_sessions": 2,
                "model_loads": 0 if self.synthetic else 1, "weights_reloaded_between_episodes": False}

    def _save(self):
        atomic_write(self.root / "resident-state.json", json_bytes(self.status()))

    def _permit(self, slot, authorization):
        if self.synthetic:
            if not slot["slot_id"].startswith("synthetic-"):
                raise ValueError("Programmed fixture cannot enter formal work")
            return None
        permit = json.loads(checked(authorization).read_text())
        if permit.get("version") == "v054-resident-interleave-control-v1":
            rows = permit.get("sessions", [])
            modes = {arm: [row for row in rows if row["arm"] == arm] for arm in ("MATCH", "PROJECT")}
            if (authorization != self.preparation_authorization
                    or permit.get("preparation_generation_authorized") is not True
                    or permit.get("formal_execution_authorized") is not False
                    or permit.get("maximum_generation_requests") != 6 or len(rows) != 4
                    or permit.get("maximum_prompt_tokens") != 8192
                    or permit.get("maximum_output_tokens") != 2048
                    or permit.get("maximum_total_tokens") != 61440
                    or slot not in rows or not all(row["slot_id"].startswith("synthetic-") for row in rows)
                    or any(len(value) != 2 or len({row["seed"] for row in value}) != 1 for value in modes.values())
                    or modes["MATCH"][0]["seed"] == modes["PROJECT"][0]["seed"]):
                raise ValueError("Interleaving control requires its exact four-session/six-call permit")
            return permit
        if (not permit.get("execution_authorized") or slot["slot_id"].startswith("synthetic-")
                or slot["slot_id"] not in permit.get("slot_ids", [])):
            raise ValueError("Formal work requires its separate original slot authorization")
        return None

    def acquire(self, *, slot, claim_id, authorization, host_process, session_slot):
        with self.lock:
            if self.poisoned:
                raise RuntimeError("Shared resident is poisoned; no reuse")
            if type(session_slot) is not int or session_slot not in (0, 1):
                raise ValueError("Select one of the two independently locked session slots")
            if session_slot not in self.status()["available_session_slots"]:
                return {"state": "busy", "acquired": False, "session_slot": session_slot}
            if (not re.fullmatch(r"[a-f0-9]{32}", claim_id) or claim_id in self.used_claims
                    or slot["slot_id"] in self.used_slots or slot["arm"] not in {"MATCH", "PROJECT"}
                    or type(slot["seed"]) is not int or not 0 <= slot["seed"] < 2**63
                    or process_identity(host_process["pid"]) != host_process):
                raise ValueError("A fresh exact session/host/seed identity is required")
            permit = self._permit(slot, authorization)
            actor = self.facades[session_slot]
            if actor.phase != "idle" or actor.busy:
                raise ValueError("Session facade has not closed its prior window")
            folder = self.root / "episodes" / claim_id
            (folder / "owner/calls").mkdir(parents=True, exist_ok=False)
            actor.output = folder / "owner"
            child = FormalOwnerService(actor, output=folder, codec=self.codec,
                synthetic=self.synthetic, resource_binding=self.resource_binding)
            child.identity.update(resident=True, resident_id=self.identity["resident_id"],
                session_protocol=PROTOCOL, maximum_sessions=2, session_slot=session_slot,
                session_claim_id=claim_id, session_nonce=uuid.uuid4().hex,
                preparation_only=bool(permit) or self.synthetic)
            downstream = authorization
            if permit:
                downstream = write_new(folder / "preparation-owner-permit.json", {
                    "execution_authorized": True, "formal_execution_authorized": False,
                    "slot_ids": [slot["slot_id"]], "source_preparation_authorization": authorization})
            path = self.socket_root / ("s-" + claim_id[:12] + ".sock")
            context = {"claim_id": claim_id, "slot": copy.deepcopy(slot), "session_slot": session_slot,
                "phase": "acquired", "actor": actor, "child": child, "folder": folder,
                "authorization": authorization, "downstream_authorization": downstream,
                "host_process": host_process, "rng": None, "queued": None, "dispatched": None,
                "finish": None, "socket": path, "sequences": {}, "compute_sequence": 0,
                "permit": permit, "preparation_calls": 0}
            self.sessions[claim_id] = context
            self.used_claims.add(claim_id)
            try:
                server = _Server(str(path), make_handler(child.identity,
                    lambda request: self.session_dispatch(claim_id, request)))
            except BaseException as error:
                self.sessions.pop(claim_id)
                write_new(folder / "acquire-failed.json", {"generation_window_entered": False,
                    "model_calls": 0, "error": {"type": type(error).__name__, "message": str(error)}})
                self._save()
                raise
            os.chmod(path, 0o600)
            context["server"] = server
            context["thread"] = threading.Thread(target=server.serve_forever,
                kwargs={"poll_interval": .05}, daemon=True)
            context["thread"].start()
            result = {"state": "acquired", "acquired": True, "claim_id": claim_id, "slot": slot,
                "session_slot": session_slot, "session_protocol": PROTOCOL, "maximum_sessions": 2,
                "session_socket": str(path), "session_identity": child.identity,
                "session_root": str(folder), "resident_identity": self.identity,
                "generation_window_entered": False, "model_reloaded": False}
            write_new(folder / "acquired.json", result)
            self._save()
            return result

    def _snapshot(self, ticket):
        result = {key: ticket[key] for key in ("ticket_id", "request_id", "state", "original_operation")}
        result["session_claim"] = ticket["claim_id"]
        for key in ("grant_deadline", "receipt", "receipt_reference", "result", "error", "interleave_evidence"):
            if key in ticket:
                result[key] = ticket[key]
        return result

    def _cancel(self, ticket, reason):
        if ticket["state"] in {"cancelled", "complete", "failed", "running"}:
            return self._snapshot(ticket)
        context = self.sessions[ticket["claim_id"]]
        bridge = context["child"].bridge
        body = {"reason": reason, "dispatched": False, "generation_calls": 0,
            "usage_unknown": False, "original_operation": ticket["original_operation"],
            "request_id": ticket["request_id"], "session_claim": ticket["claim_id"],
            "ticket_id": ticket["ticket_id"], "queued_seconds": time.monotonic() - ticket["enqueued"],
            "original_deadline": ticket["deadline"], "ledger": bridge.ledger.snapshot() if bridge else None,
            "automatic_retry": False}
        ticket.update(state="cancelled", receipt=body,
            receipt_reference=write_new(context["folder"] / (ticket["ticket_id"] + "-not-dispatched.json"), body))
        context["queued"] = None
        ticket["done"].set()
        self.condition.notify_all()
        return self._snapshot(ticket)

    def reserve_turn(self, context, *, original_operation, original_arguments, request_id, dispatch_deadline):
        if (original_operation not in OPERATIONS or not re.fullmatch(r"[a-f0-9]{32}", request_id)
                or not isinstance(dispatch_deadline, (float, int)) or not math.isfinite(dispatch_deadline)
                or dispatch_deadline > time.monotonic() + 661
                or context["phase"] == "closing" or context["child"].closed
                or context["queued"] or context["dispatched"]):
            raise ValueError("Invalid bounded preflight or another session operation is pending")
        if request_id in self.used_request_ids:
            raise ValueError("A request identity may never be replayed")
        if original_operation == "begin":
            args = original_arguments
            if (args["slot"] != context["slot"] or args["claim_id"] != context["claim_id"]
                    or args.get("authorization") != context["authorization"]):
                raise ValueError("Begin differs from the exact acquired session")
        now = time.monotonic()
        self.ordinal += 1
        ticket = {"ticket_id": uuid.uuid4().hex, "request_id": request_id,
            "ordinal": self.ordinal, "claim_id": context["claim_id"],
            "original_operation": original_operation, "arguments": copy.deepcopy(original_arguments),
            "request_sha256": digest(json_bytes([original_operation, original_arguments])),
            "deadline": dispatch_deadline, "enqueued": now, "state": "queued", "done": threading.Event()}
        ticket["queue_deadline"] = (min(dispatch_deadline - 615, now + 45)
                                     if original_operation in GENERATIONS else dispatch_deadline - 1)
        self.tickets[ticket["ticket_id"]] = ticket
        self.used_request_ids.add(request_id)
        context["queued"] = ticket["ticket_id"]
        write_new(context["folder"] / (ticket["ticket_id"] + "-preflight.json"),
                  {key: value for key, value in ticket.items() if key != "done"})
        if now >= ticket["queue_deadline"]:
            return self._cancel(ticket, "interleave_queue_deadline_before_dispatch")
        self.queue.append(ticket["ticket_id"])
        self.condition.notify_all()
        self._save()
        return self._snapshot(ticket)

    def session_dispatch(self, claim_id, request):
        with self.condition:
            context = self.sessions.get(claim_id)
            if self.poisoned or context is None or context["phase"] == "closing":
                raise ValueError("Stale, closing or poisoned session")
            if (request["version"] != original.VERSION
                    or request["identity_sha256"] != digest(json_bytes(context["child"].identity))
                    or request["sequence"] != context["sequences"].get(request["session"], 0) + 1):
                raise ValueError("Session wire identity/sequence changed")
            context["sequences"][request["session"]] = request["sequence"]
            op, args = request["operation"], request["arguments"]
            if op == "reserve_turn":
                return self.reserve_turn(context, **args)
            ticket = self.tickets[args["ticket_id"]]
            if ticket["claim_id"] != claim_id:
                raise ValueError("Another session cannot inspect or commit this ticket")
            if op == "cancel_ticket":
                return self._cancel(ticket, args["reason"])
            if op == "ticket_status":
                if ticket["state"] in {"queued", "granted"} and time.monotonic() >= min(
                        ticket["queue_deadline"], ticket.get("grant_deadline", float("inf"))):
                    self._cancel(ticket, "interleave_queue_deadline_before_dispatch")
                return self._snapshot(ticket)
            if op != "dispatch_ticket":
                raise ValueError("Unknown interleaved session operation")
            if ticket["state"] == "cancelled":
                return self._snapshot(ticket)
            if ticket["state"] != "granted":
                raise ValueError("Only a granted, uncommitted FIFO turn may dispatch once")
            if time.monotonic() >= min(ticket["queue_deadline"], ticket["grant_deadline"]):
                return self._cancel(ticket, "interleave_grant_expired_before_dispatch")
            ticket["state"] = "committed"
            self.condition.notify_all()
        # The client only waits for this operation. Metadata cancellation and
        # host liveness never depend on a held numerical lock.
        ticket["done"].wait(max(0, ticket["deadline"] - time.monotonic()))
        with self.condition:
            if ticket["state"] not in {"complete", "cancelled", "failed"}:
                self.poison_shared("dispatched_ticket_exceeded_original_deadline")
                raise RuntimeError("Dispatched operation did not close within its original deadline")
            return self._snapshot(ticket)

    def _execute(self):
        while not self.stop_event.is_set():
            with self.condition:
                while not self.queue and not self.stop_event.is_set():
                    self.condition.wait(.1)
                if self.stop_event.is_set():
                    return
                ticket = self.tickets[self.queue.pop(0)]
                if ticket["state"] != "queued":
                    continue
                if self.poisoned:
                    self._cancel(ticket, "shared_resident_poisoned_before_dispatch")
                    continue
                context = self.sessions[ticket["claim_id"]]
                if time.monotonic() >= ticket["queue_deadline"]:
                    self._cancel(ticket, "interleave_queue_deadline_before_dispatch")
                    continue
                self.current_ticket = ticket["ticket_id"]
                if ticket.get("trusted_cleanup"):
                    ticket["state"] = "committed"
                else:
                    ticket.update(state="granted", grant_deadline=min(ticket["queue_deadline"], time.monotonic() + 5))
                    self.condition.notify_all()
                    while ticket["state"] == "granted" and time.monotonic() < ticket["grant_deadline"]:
                        self.condition.wait(min(.05, max(0, ticket["grant_deadline"] - time.monotonic())))
                    if ticket["state"] == "granted":
                        self._cancel(ticket, "interleave_grant_expired_before_dispatch")
                if ticket["state"] == "committed" and time.monotonic() >= ticket["queue_deadline"]:
                    self._cancel(ticket, "interleave_queue_deadline_before_dispatch")
                if ticket["state"] != "committed":
                    self.current_ticket = None
                    continue
                ticket["state"] = "running"
                context["queued"], context["dispatched"] = None, ticket["ticket_id"]
                self.inflight = {"claim_id": context["claim_id"], "ticket_id": ticket["ticket_id"],
                                 "operation": ticket["original_operation"]}
                self._save()
            try:
                result = self._perform(context, ticket)
                with self.condition:
                    if self.poisoned:
                        raise RuntimeError("Operation completed after shared poisoning; retain evidence, no reuse")
                    ticket.update(state="complete", result=result)
            except BaseException as error:
                with self.condition:
                    ticket.update(state="failed", error={"type": type(error).__name__, "message": str(error)})
                    self.poison_shared("original_dispatch_or_rng_failure:" + str(error))
            finally:
                with self.condition:
                    context["dispatched"] = None
                    self.inflight, self.current_ticket = None, None
                    if ticket.get("trusted_cleanup") and ticket["state"] == "complete":
                        self.sessions.pop(context["claim_id"], None)
                        self.closed_claims[context["claim_id"]] = {"aborted": True,
                            "receipt": reference(context["folder"] / "aborted.json")}
                        self._purge_claim(context["claim_id"])
                    ticket["done"].set()
                    self.condition.notify_all()
                    self._save()

    def _perform(self, context, ticket):
        started = time.monotonic()
        if self.rng.fingerprint(self.rng.read()) != self.parked_hash:
            raise ValueError("Torch RNG changed outside the single numerical executor")
        child = context["child"]
        operation, args = ticket["original_operation"], copy.deepcopy(ticket["arguments"])
        before = context["rng"] if context["rng"] is not None else self.parked
        self.rng.write(before)
        result, after, error = None, None, None
        try:
            if operation == "begin":
                args["authorization"] = context["downstream_authorization"]
                self.used_slots.add(context["slot"]["slot_id"])
            if operation in GENERATIONS and context["permit"]:
                permit = context["permit"]
                labels = permit["session_requests"][context["slot"]["slot_id"]]
                index = context["preparation_calls"]
                if (index >= len(labels) or self.preparation_calls >= 6
                        or args["request"] != permit["requests"][labels[index]]
                        or args.get("usage_id") != permit["usage_ids"][labels[index]]):
                    raise ValueError("Synthetic request differs from its bounded predeclared request plan")
                if operation == "match_complete":
                    from .software_benchmark_match_v054 import prepare_native_input
                    native = prepare_native_input(context["actor"].tokenizer, args["request"], CONTRACT)
                else:
                    native = context["actor"].prepare_request(args["request"])[2]
                if native["prompt_tokens"] > permit["maximum_prompt_tokens"]:
                    raise ValueError("Synthetic preparation prompt exceeds its separate authorization")
                context["preparation_calls"] += 1
                self.preparation_calls += 1
            context["compute_sequence"] += 1
            result = child.dispatch({"version": original.VERSION, "session": "single-compute-thread",
                "sequence": context["compute_sequence"], "identity_sha256": digest(json_bytes(child.identity)),
                "operation": operation, "arguments": args})
            if operation == "project_complete" and result.get("http_status") != 200:
                raise RuntimeError("Original PROJECT request failed; no fabricated zero usage")
            self.rng.synchronize()
            after = self.rng.read()
            if operation == "begin":
                context["phase"] = "collecting"
            if operation == "finish":
                if (not result["guard"]["learning_unchanged"] or not result["guard"]["rng_restored_exactly"]
                        or self.rng.fingerprint(after) != self.parked_hash):
                    raise ValueError("Original session guard did not restore its parked RNG")
                context["finish"] = result
            else:
                context["rng"] = after
            if hasattr(self.model, "_cache"):
                raise ValueError("Original request left shared model KV state")
            return result
        except BaseException as caught:
            error = {"type": type(caught).__name__, "message": str(caught)}
            raise
        finally:
            try:
                self.rng.synchronize()
                if after is None:
                    after = self.rng.read()
                self.rng.write(self.parked)
                restored = self.rng.fingerprint(self.rng.read()) == self.parked_hash
            except BaseException:
                restored = False
            evidence = {"ordinal": ticket["ordinal"], "ticket_id": ticket["ticket_id"],
                "original_operation": operation, "claim_id": context["claim_id"],
                "session_slot": context["session_slot"], "request_id": ticket["request_id"],
                "started_monotonic": started, "finished_monotonic": time.monotonic(),
                "queued_seconds": started - ticket["enqueued"], "original_deadline": ticket["deadline"],
                "rng_before_sha256": self.rng.fingerprint(before),
                "rng_after_sha256": self.rng.fingerprint(after) if after is not None else None,
                "shared_parked_rng_restored": restored, "parked_rng_sha256": self.parked_hash,
                "model_object_id": id(self.model), "owner_model_object_id": id(self.model),
                "cache_absent": not hasattr(self.model, "_cache"),
                "error": error, "generator_replaced": False}
            turn = write_new(context["folder"] / (ticket["ticket_id"] + "-turn.json"), evidence)
            ticket["interleave_evidence"] = {"turn": turn, **evidence}
            # exact_measure has its own whole-object SHA; preserve the exact
            # count object, placing extra lifecycle evidence on its RPC envelope.
            if result is not None and operation != "match_count":
                result["interleave_evidence"] = {"turn": turn, **evidence}
            if not restored:
                raise RuntimeError("Shared parked RNG restoration could not be proven")

    def poison_shared(self, reason):
        with self.condition:
            if self.poisoned is None:
                self.poisoned = {"reason": reason, "inflight": copy.deepcopy(self.inflight),
                    "automatic_reuse": False, "GPU_resident_and_lease_retained": True,
                    "already_submitted_GPU_work_immediately_cancelled": False}
                write_new(self.root / "poisoned.json", self.poisoned)
            self.condition.notify_all()
            self._save()
            return {"shared_poisoned": True, "inflight": self.inflight, "poisoned": self.poisoned}

    def _close_socket(self, context):
        context["server"].shutdown()
        context["server"].server_close()
        context["thread"].join(timeout=5)
        context["socket"].unlink(missing_ok=True)

    def _purge_claim(self, claim_id):
        """Keep anti-replay IDs and immutable disk receipts, not prompt/trace payloads."""
        identities = {key for key, ticket in self.tickets.items() if ticket["claim_id"] == claim_id}
        if any(self.tickets[key]["state"] not in {"complete", "cancelled", "failed"} for key in identities):
            raise ValueError("Cannot drop live or queued per-session execution evidence")
        self.queue[:] = [key for key in self.queue if key not in identities]
        for key in identities:
            del self.tickets[key]

    def release(self, *, claim_id, finish_receipt=None, cancel_unentered=False):
        with self.condition:
            context = self.sessions[claim_id]
            actor, child = context["actor"], context["child"]
            if self.poisoned or context["queued"] or context["dispatched"]:
                raise ValueError("This session still has pending or uncertain work")
            finished = context["finish"]
            if cancel_unentered:
                if child.entered or actor.phase != "idle":
                    raise ValueError("An entered session cannot cancel acquisition")
            elif (not finished or finished["receipt"] != finish_receipt or not child.closed
                  or actor.phase != "idle" or actor.busy):
                raise ValueError("This session must finish its original guard before release")
            context["phase"] = "closing"
            context["closing_action"] = "release"
        self._close_socket(context)
        with self.condition:
            guard = finished["guard"] if finished else {}
            proof = {"session_quiescent": True, "own_inflight": 0, "queued_removed": True,
                "learning_unchanged": bool(guard.get("learning_unchanged")),
                "rng_restored_exactly": bool(guard.get("rng_restored_exactly")),
                "session_rng_closed": not cancel_unentered, "weights_reloaded": False,
                "model_object_retained": True, "old_session_socket_removed": True,
                "resident_still_loaded": True, "other_active_claims": [c for c in self.sessions if c != claim_id],
                "resident_generator_active": self.inflight["claim_id"] if self.inflight else None,
                "cancelled_before_begin": cancel_unentered}
            receipt = write_new(context["folder"] / "released.json", {"claim_id": claim_id,
                "slot": context["slot"], "finish_receipt": finish_receipt, "quiescence": proof,
                "resident_identity": self.identity})
            self.sessions.pop(claim_id)
            self.closed_claims[claim_id] = {"aborted": False, "receipt": receipt}
            self._purge_claim(claim_id)
            self._save()
            return {"state": "released", "claim_id": claim_id, "quiescence": proof, "receipt": receipt}

    def abort_session(self, *, claim_id, reason):
        with self.condition:
            if claim_id in self.abort_results:
                return copy.deepcopy(self.abort_results[claim_id])
            if claim_id in self.closed_claims:
                return {"claim_id": claim_id, "session_aborted": True, "already_closed": True,
                    "shared_poisoned": False, "own_dispatched": False, "not_dispatched_receipts": [],
                    "resident_still_loaded": True, "cleanup_pending": False,
                    "closure": self.closed_claims[claim_id]["receipt"]}
            context = self.sessions.get(claim_id)
            if context is None:
                raise ValueError("Unknown or already closed session")
            if context.get("closing_action") == "release" and context["finish"]:
                result = {"claim_id": claim_id, "session_aborted": True, "already_closed": True,
                    "shared_poisoned": False, "own_dispatched": False, "not_dispatched_receipts": [],
                    "resident_still_loaded": True, "cleanup_pending": False,
                    "release_in_progress": True, "closure": context["finish"]["receipt"]}
                self.abort_results[claim_id] = copy.deepcopy(result)
                return result
            if context["dispatched"]:
                result = {"claim_id": claim_id, "session_aborted": False, "own_dispatched": True,
                          **self.poison_shared("session_failed_during_dispatch:" + reason)}
                self.abort_results[claim_id] = copy.deepcopy(result)
                return result
            cancelled = []
            if context["queued"]:
                value = self._cancel(self.tickets[context["queued"]], "session_aborted_before_dispatch")
                cancelled.append(value["receipt_reference"])
            context["phase"] = "closing"
            cleanup_pending = context["child"].entered and not context["child"].closed
            result = {"claim_id": claim_id, "session_aborted": True, "own_dispatched": False,
                "shared_poisoned": False, "not_dispatched_receipts": cancelled,
                "resident_still_loaded": True, "cleanup_pending": cleanup_pending, "reason": reason}
            receipt = write_new(context["folder"] / "aborted.json", result)
            result["receipt"] = receipt
            self.abort_results[claim_id] = copy.deepcopy(result)
            # No session can write through its socket after this flag. Cleanup
            # uses the original finish/guard only after the other compute turn.
        self._close_socket(context)
        with self.condition:
            if not context["child"].entered or context["child"].closed:
                self.sessions.pop(claim_id)
                self.closed_claims[claim_id] = {"aborted": True, "receipt": receipt}
                self._purge_claim(claim_id)
            else:
                self.ordinal += 1
                cleanup = {"ticket_id": uuid.uuid4().hex, "request_id": uuid.uuid4().hex,
                    "ordinal": self.ordinal, "claim_id": claim_id, "original_operation": "finish",
                    "arguments": {"entries": []}, "deadline": time.monotonic() + 690,
                    "queue_deadline": time.monotonic() + 660, "enqueued": time.monotonic(),
                    "state": "queued", "done": threading.Event(), "trusted_cleanup": True}
                self.tickets[cleanup["ticket_id"]] = cleanup
                self.used_request_ids.add(cleanup["request_id"])
                context["queued"] = cleanup["ticket_id"]
                self.queue.append(cleanup["ticket_id"])
                self.condition.notify_all()
        self._save()
        return result

    def dispatch(self, request):
        with self.lock:
            if (request["version"] != original.VERSION
                    or request["identity_sha256"] != digest(json_bytes(self.identity))
                    or request["sequence"] != self.sequences.get(request["session"], 0) + 1):
                raise ValueError("Resident administrator identity/sequence differs")
            self.sequences[request["session"]] = request["sequence"]
        op, args = request["operation"], request["arguments"]
        if op == "status":
            return self.status()
        if op == "acquire":
            return self.acquire(**args)
        if op == "release":
            return self.release(**args)
        if op == "cancel_acquire":
            return self.release(claim_id=args["claim_id"], cancel_unentered=True)
        if op in {"abort_session", "poison"}:
            return self.abort_session(**args)
        if op == "poison_shared":
            return self.poison_shared(**args)
        raise ValueError("Unknown resident administration operation")


def serve(service, socket_path, identity_output):
    path = Path(socket_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    service.socket_root = path.parent
    write_new(identity_output, service.identity)

    def watch_hosts():
        while not service.stop_event.wait(.25):
            with service.lock:
                values = [(claim, row["host_process"]) for claim, row in service.sessions.items()
                          if row["phase"] != "closing"]
            for claim, expected in values:
                try:
                    alive = process_identity(expected["pid"]) == expected
                    raw = Path(f"/proc/{expected['pid']}/stat").read_text()
                    alive &= raw[raw.rfind(")") + 2:].split()[0] != "Z"
                except (FileNotFoundError, ProcessLookupError):
                    alive = False
                if not alive:
                    try:
                        service.abort_session(claim_id=claim, reason="host_disappeared")
                    except (KeyError, ValueError):
                        pass
    threading.Thread(target=watch_hosts, daemon=True).start()
    with _Server(str(path), make_handler(service.identity, service.dispatch)) as server:
        os.chmod(path, 0o600)
        atomic_write(service.root / "service-ready.json", json_bytes({"version": VERSION,
            "identity": reference(identity_output), "socket": str(path), "pid": os.getpid(),
            "ready": True, "resident": True, "session_protocol": PROTOCOL, "maximum_sessions": 2}))
        try:
            server.serve_forever(poll_interval=.1)
        finally:
            service.stop_event.set()
            with service.condition:
                service.condition.notify_all()
            path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--max-sessions", type=int, required=True)
    parser.add_argument("--resident-preparation-permit", type=Path)
    args, remaining = parser.parse_known_args()
    authorization = reference(args.resident_preparation_permit) if args.resident_preparation_permit else None
    sys.argv = [sys.argv[0], *remaining]
    original.OwnerService = functools.partial(InterleavedOwner,
        preparation_authorization=authorization, maximum_sessions=args.max_sessions)
    original.serve = serve
    original.main()
