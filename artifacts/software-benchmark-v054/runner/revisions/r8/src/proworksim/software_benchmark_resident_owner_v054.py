"""One raw resident owner, independently fenced MATCH/PROJECT evaluation windows."""
from __future__ import annotations

import json
import copy
import argparse
import functools
import os
from pathlib import Path
import re
import socketserver
import threading
import sys
import uuid

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_match_v054 import CONTRACT
from .software_benchmark_normal_boundary_v054 import FormalOwnerService
from . import software_benchmark_owner_ipc_v054 as original
from .software_benchmark_supervision_v054 import process_identity
from .storage import atomic_write, digest, json_bytes

VERSION = "v054-resident-raw-owner-r1"


class ResidentOwner:
    """Sequential leases only; poisoned or unclosed windows cannot be reused."""
    def __init__(self, owner, *, output, codec=None, synthetic=False, smoke=False,
                 max_smoke_requests=2, resource_binding=None, preparation_authorization=None):
        if smoke or codec is None:
            raise ValueError("A persistent MATCH/PROJECT owner requires its codec and no capacity-smoke mode")
        self.owner, self.root, self.codec = owner, Path(output), codec
        self.synthetic, self.resource_binding = synthetic, resource_binding
        self.preparation_authorization = preparation_authorization
        self.root.mkdir(parents=True, exist_ok=True)
        if (self.root / "resident-state.json").exists():
            raise ValueError("A resident process cannot resume old in-memory windows")
        self._owner_identity = owner.freeze_identity()
        self._model_object = getattr(owner, "model", owner)
        self.lock = threading.RLock()
        self.active, self.inflight, self.poisoned = None, None, None
        self.used_claims, self.used_slots, self.sequences = set(), set(), {}
        self.closed, self.stop_event = False, threading.Event()
        self.ordinal = 0
        self.preparation_attempts = {}
        self.socket_root = None
        prototype = FormalOwnerService(owner, output=self.root / "prototype", codec=codec,
            synthetic=synthetic, resource_binding=resource_binding)
        self.identity = {**prototype.identity, "resident": True, "resident_version": VERSION,
                         "resident_id": uuid.uuid4().hex, "supported_arms": ["MATCH", "PROJECT"],
                         "resident_source": reference(__file__),
                         "resident_owner_process": process_identity(os.getpid()),
                         "resident_model_object_id": id(self._model_object),
                         "preparation_authorization": preparation_authorization,
                         "model_loads_at_initialization": 0 if synthetic else 1,
                         "numerical_methods_replaced": False}
        self._assert_owner()
        self._save()

    def _assert_owner(self):
        if (self.owner.freeze_identity() != self._owner_identity or self.owner.contract != CONTRACT
                or self.owner.path != "project" or getattr(self.owner, "model", self.owner) is not self._model_object
                or not self._owner_identity.get("raw_release")
                or self._owner_identity.get("checkpoint") is not None
                or self._owner_identity.get("adapter_sha256") is not None):
            raise ValueError("Resident raw identity, model object or numerical contract changed")
        if not self.synthetic:
            from .software_calibration_runtime_v051 import CalibrationActor
            if (not isinstance(self.owner, CalibrationActor)
                    or self.owner.generate_native.__func__ is not CalibrationActor.generate_native
                    or self.owner.inference_profile["base_storage_dtype"] != "bfloat16_backbone_float32_lm_head"):
                raise ValueError("The original raw CalibrationActor numerical path is required")

    def status(self):
        with self.lock:
            return {"resident": True, "state": "poisoned" if self.poisoned else "busy" if self.active else "idle",
                    "poisoned": self.poisoned, "active_claim": self.active["claim_id"] if self.active else None,
                    "inflight": self.inflight, "completed_or_reserved_windows": self.ordinal,
                    "owner_phase": self.owner.phase, "owner_busy": self.owner.busy,
                    "model_loads": 0 if self.synthetic else 1, "weights_reloaded_between_episodes": False}

    def _save(self):
        atomic_write(self.root / "resident-state.json", json_bytes(self.status()))

    def poison(self, claim_id, reason):
        with self.lock:
            if claim_id is not None and (not self.active or self.active["claim_id"] != claim_id):
                raise ValueError("Poison request belongs to another resident session")
            if self.poisoned is None:
                self.poisoned = {"claim_id": claim_id, "reason": str(reason),
                                 "inflight_at_poison": self.inflight, "automatic_reuse": False,
                                 "GPU_resident_and_lease_retained": True,
                                 "already_submitted_GPU_work_immediately_cancelled": False}
                write_new(self.root / "poisoned.json", self.poisoned)
            self._save()
            return self.status()

    def acquire(self, *, slot, claim_id, authorization, host_process):
        with self.lock:
            if self.poisoned:
                raise RuntimeError("Poisoned owner requires explicit operator intervention")
            if self.active:
                return {"state": "busy", "acquired": False, "active_claim": self.active["claim_id"]}
            if (not re.fullmatch(r"[a-f0-9]{32}", claim_id) or claim_id in self.used_claims
                    or slot["slot_id"] in self.used_slots or slot["arm"] not in {"MATCH", "PROJECT"}
                    or type(slot["seed"]) is not int or not 0 <= slot["seed"] < 2**63):
                raise ValueError("A fresh planned MATCH/PROJECT session is required")
            preparation = False
            permit = None
            if self.synthetic:
                if not slot["slot_id"].startswith("synthetic-"):
                    raise ValueError("Synthetic resident cannot acquire formal work")
            else:
                permit = json.loads(checked(authorization).read_text())
                if permit.get("version") == "v054-resident-session-smoke-v1":
                    preparation = True
                    if (authorization != self.preparation_authorization
                            or permit.get("preparation_generation_authorized") is not True
                            or permit.get("formal_execution_authorized") is not False
                            or permit.get("maximum_generation_requests") != 2
                            or permit.get("maximum_requests_per_session") != 1
                            or len(permit.get("sessions", [])) != 2 or slot not in permit["sessions"]
                            or [row["arm"] for row in permit["sessions"]] != ["MATCH", "PROJECT"]
                            or not all(row["slot_id"].startswith("synthetic-") for row in permit["sessions"])
                            or len({row["slot_id"] for row in permit["sessions"]}) != 2
                            or len({row["seed"] for row in permit["sessions"]}) != 2):
                        raise ValueError("Only two separately authorized synthetic handoff requests are permitted")
                elif (slot["slot_id"].startswith("synthetic-") or not permit.get("execution_authorized")
                        or slot["slot_id"] not in permit.get("slot_ids", [])):
                    raise ValueError("Separate formal slot authorization is required")
            if process_identity(host_process["pid"]) != host_process:
                raise ValueError("Session host identity is no longer alive")
            self._assert_owner()
            if self.owner.phase != "idle" or self.owner.busy:
                raise ValueError("Previous owner window was not completely closed")
            self.ordinal += 1
            folder = self.root / "episodes" / claim_id
            folder.mkdir(parents=True, exist_ok=False)
            owner_output = folder / "owner"
            (owner_output / "calls").mkdir(parents=True)
            self.owner.output = owner_output  # Logging destination only; no model/decoder mutation.
            write_new(owner_output / "resident-routing.json", {
                "resident_identity": self.identity, "slot": slot, "claim_id": claim_id,
                "window_ordinal": self.ordinal, "model_reloaded": False})
            child = FormalOwnerService(self.owner, output=folder, codec=self.codec,
                synthetic=self.synthetic, resource_binding=self.resource_binding)
            child.identity.update(resident=True, resident_id=self.identity["resident_id"],
                                  session_claim_id=claim_id, session_epoch=self.ordinal,
                                  session_nonce=uuid.uuid4().hex, preparation_only=preparation or self.synthetic)
            downstream = authorization
            if preparation:
                # Adapt the old owner's generic execution gate without granting
                # any real task. The external permit is restricted above.
                downstream = write_new(folder / "preparation-owner-permit.json", {
                    "execution_authorized": True, "formal_execution_authorized": False,
                    "slot_ids": [slot["slot_id"]], "scope": "one synthetic preparation request",
                    "source_preparation_authorization": authorization})
            path = self.socket_root / ("s-" + claim_id[:12] + ".sock")
            self.active = {"claim_id": claim_id, "slot": dict(slot), "child": child,
                           "authorization": authorization, "host_process": dict(host_process),
                           "folder": folder, "socket": path, "finish": None,
                           "preparation": preparation, "preparation_requests": 0,
                           "downstream_authorization": downstream}
            self.used_claims.add(claim_id)
            try:
                server = session_server(self, path, claim_id)
            except BaseException as error:
                self.poison(claim_id, "session_socket_creation_failed:" + str(error))
                raise
            self.active["server"] = server
            self.active["thread"] = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
            self.active["thread"].start()
            result = {"state": "acquired", "acquired": True, "claim_id": claim_id, "slot": slot,
                      "session_socket": str(path), "session_identity": child.identity,
                      "session_root": str(folder), "resident_identity": self.identity,
                      "generation_window_entered": False, "model_reloaded": False}
            write_new(folder / "acquired.json", result)
            self._save()
            return result

    def episode_dispatch(self, claim_id, request):
        with self.lock:
            active = self.active
            if self.poisoned or not active or active["claim_id"] != claim_id or active.get("closing"):
                raise ValueError("Stale or poisoned episode socket cannot dispatch")
            if self.inflight is not None:
                raise ValueError("One numerical operation at a time")
            operation = request["operation"]
            if operation not in {"begin", "match_count", "match_complete", "project_complete", "finish"}:
                raise ValueError("Unknown resident episode operation")
            if operation == "begin":
                args = request["arguments"]
                if (args["slot"] != active["slot"] or args["claim_id"] != claim_id
                        or args.get("authorization") != active["authorization"]):
                    raise ValueError("Session begin differs from its reserved exact slot")
                self.used_slots.add(active["slot"]["slot_id"])
                request = copy.deepcopy(request)
                request["arguments"]["authorization"] = active["downstream_authorization"]
            if active["preparation"] and operation in {"match_complete", "project_complete"}:
                key = active["authorization"]["sha256"]
                if active["preparation_requests"] >= 1 or self.preparation_attempts.get(key, 0) >= 2:
                    raise ValueError("Synthetic handoff preparation generation bound is exhausted")
                active["preparation_requests"] += 1
                self.preparation_attempts[key] = self.preparation_attempts.get(key, 0) + 1
            self.inflight = {"claim_id": claim_id, "operation": operation}
            self._save()
        try:
            result = active["child"].dispatch(request)
            if operation == "project_complete" and result.get("http_status") != 200:
                raise RuntimeError("Original owner returned a failed request; resident cannot be reused")
            with self.lock:
                if self.poisoned:
                    raise RuntimeError("Request returned after resident poisoning; usage remains separately evidenced")
                if operation == "finish":
                    active["finish"] = result
                return result
        except BaseException as error:
            self.poison(claim_id, f"{type(error).__name__}:{error}")
            raise
        finally:
            with self.lock:
                self.inflight = None
                self._save()

    def release(self, *, claim_id, finish_receipt=None, cancel_unentered=False):
        with self.lock:
            active = self.active
            if self.poisoned or not active or active["claim_id"] != claim_id or self.inflight is not None:
                raise ValueError("Only an idle exact unpoisoned session can release")
            child = active["child"]
            if cancel_unentered:
                if child.entered or self.owner.phase != "idle" or self.owner.busy:
                    raise ValueError("An entered session cannot cancel its slot")
                guard = None
            else:
                finished = active["finish"]
                if (not finished or finished["receipt"] != finish_receipt or not child.closed
                        or self.owner.phase != "idle" or self.owner.busy
                        or not finished["guard"]["learning_unchanged"]
                        or not finished["guard"]["rng_restored_exactly"]):
                    raise ValueError("Original finish and learning/RNG guard must precede release")
                checked(finish_receipt)
                guard = finished["guard"]
            self._assert_owner()
            if not self.synthetic:
                self.owner.torch.cuda.synchronize()
                if hasattr(self.owner.model, "_cache"):
                    raise ValueError("Per-request model KV survived the original native close")
            # Mark closure before dropping the lock so no late old request enters.
            child.closed = True
            active["closing"] = True
        active["server"].shutdown()
        active["server"].server_close()
        active["thread"].join(timeout=5)
        active["socket"].unlink(missing_ok=True)
        with self.lock:
            quiescence = {"owner_idle": self.owner.phase == "idle", "model_busy": self.owner.busy,
                "active_session": None, "learning_unchanged": bool(guard and guard["learning_unchanged"]),
                "rng_restored_exactly": bool(guard and guard["rng_restored_exactly"]),
                "model_object_retained": True, "weights_reloaded": False,
                "empty_cache_called": False, "old_session_socket_removed": True,
                "cancelled_before_begin": cancel_unentered}
            if not self.synthetic:
                quiescence.update(allocator_reserved_bytes=self.owner.torch.cuda.memory_reserved(),
                                  allocator_allocated_bytes=self.owner.torch.cuda.memory_allocated(),
                                  original_per_request_model_cache_absent=not hasattr(self.owner.model, "_cache"))
            resource_log = active["folder"] / "native-cache/native-cache-resources.jsonl"
            if resource_log.exists():
                quiescence["per_session_resource_evidence"] = reference(resource_log)
            receipt = write_new(active["folder"] / "released.json", {
                "claim_id": claim_id, "slot": active["slot"], "finish_receipt": finish_receipt,
                "quiescence": quiescence, "resident_identity": self.identity})
            self.active = None
            self._save()
            return {"state": "released", "claim_id": claim_id, "quiescence": quiescence, "receipt": receipt}

    def dispatch(self, request):
        with self.lock:
            if (request["version"] != original.VERSION
                    or request["identity_sha256"] != digest(json_bytes(self.identity))
                    or request["sequence"] != self.sequences.get(request["session"], 0) + 1):
                raise ValueError("Resident administrator identity or sequence differs")
            self.sequences[request["session"]] = request["sequence"]
        operation, args = request["operation"], request["arguments"]
        if operation == "status":
            return self.status()
        if operation == "acquire":
            return self.acquire(**args)
        if operation == "release":
            return self.release(**args)
        if operation == "cancel_acquire":
            return self.release(claim_id=args["claim_id"], cancel_unentered=True)
        if operation == "poison":
            return self.poison(**args)
        raise ValueError("Unknown resident administrator operation")


def make_handler(identity, dispatch):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            request = {}
            try:
                self.request.settimeout(30)
                raw = self.rfile.readline(original.MAX_WIRE + 1)
                if len(raw) > original.MAX_WIRE or not raw.endswith(b"\n"):
                    raise ValueError("Incomplete resident wire frame")
                request = json.loads(raw)
                body = {"result": dispatch(request)}
            except BaseException as error:
                body = {"error": {"type": type(error).__name__, "message": str(error)},
                        "actual_usage": None, "automatic_retry": False}
            payload = original.wire_json({"sequence": request.get("sequence"),
                "identity_sha256": digest(json_bytes(identity)), **body})
            if len(payload) > original.MAX_WIRE:
                raise ValueError("Resident response cannot be truncated")
            self.wfile.write(payload)
    return Handler


def session_server(manager, path, claim_id):
    server = socketserver.UnixStreamServer(str(path), make_handler(manager.active["child"].identity,
        lambda request: manager.episode_dispatch(claim_id, request)))
    os.chmod(path, 0o600)
    return server


def serve(service, socket_path, identity_output):
    path = Path(socket_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    service.socket_root = path.parent
    write_new(identity_output, service.identity)
    def watch_host():
        while not service.stop_event.wait(.25):
            with service.lock:
                active = service.active
                identity = dict(active["host_process"]) if active else None
                claim = active["claim_id"] if active else None
            if identity is None or service.poisoned:
                continue
            try:
                alive = process_identity(identity["pid"]) == identity
                raw = Path(f"/proc/{identity['pid']}/stat").read_text()
                alive &= raw[raw.rfind(")") + 2:].split()[0] != "Z"
            except (FileNotFoundError, ProcessLookupError):
                alive = False
            if not alive:
                with service.lock:
                    if service.active and service.active["claim_id"] == claim:
                        service.poison(claim, "session_host_exited_or_changed")
    threading.Thread(target=watch_host, daemon=True).start()
    with socketserver.UnixStreamServer(str(path), make_handler(service.identity, service.dispatch)) as server:
        os.chmod(path, 0o600)
        atomic_write(service.root / "service-ready.json", json_bytes({"version": VERSION,
            "identity": reference(identity_output), "socket": str(path), "pid": os.getpid(),
            "ready": True, "resident": True}))
        try:
            server.serve_forever(poll_interval=.1)
        finally:
            service.stop_event.set()
            path.unlink(missing_ok=True)


def main():
    # Reuse the original loader/CLI/startup cache exactly once; specialize only
    # the service lifecycle. CalibrationActor methods are never substituted.
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--resident-preparation-permit", type=Path)
    args, remaining = parser.parse_known_args()
    authorization = reference(args.resident_preparation_permit) if args.resident_preparation_permit else None
    sys.argv = [sys.argv[0], *remaining]
    original.OwnerService = functools.partial(ResidentOwner, preparation_authorization=authorization)
    original.serve = serve
    original.main()
