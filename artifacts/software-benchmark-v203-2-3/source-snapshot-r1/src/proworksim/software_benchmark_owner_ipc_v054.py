"""Exclusive local owner IPC; the real CalibrationActor and MATCH ledger stay server-side."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import copy
import json
import os
from pathlib import Path
import socket
import socketserver
import struct
import threading
import uuid

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_match_v054 import CONTRACT, MatchBridge
from .storage import atomic_write, digest, json_bytes

VERSION = "software-benchmark-owner-ipc-v054"
MAX_WIRE = 32 * 1024**2


def wire_json(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


class OwnerClient:
    """Exactly one attempt per operation, no retries/reconnect of failed operations."""
    def __init__(self, socket_path, identity, *, timeout=660):
        self.path, self.identity, self.timeout = str(socket_path), copy.deepcopy(identity), timeout
        self.sequence, self.failed = 0, False
        self.lock = threading.Lock()
        self.session = uuid.uuid4().hex

    def call(self, operation, **arguments):
        with self.lock:
            if self.failed:
                raise RuntimeError("A failed owner connection cannot replay an operation")
            self.sequence += 1
            request = {"version": VERSION, "session": self.session, "sequence": self.sequence,
                       "identity_sha256": digest(json_bytes(self.identity)),
                       "operation": operation, "arguments": arguments}
            payload = wire_json(request)
            if len(payload) > MAX_WIRE:
                raise ValueError("Owner request exceeds frozen wire bound")
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
                    stream.settimeout(self.timeout)
                    stream.connect(self.path)
                    peer_pid, peer_uid, _ = struct.unpack(
                        "3i", stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                    if peer_uid != os.getuid() or peer_pid <= 0:
                        raise ValueError("Owner socket peer identity differs")
                    stream.sendall(payload)
                    with stream.makefile("rb") as reader:
                        wire = reader.readline(MAX_WIRE + 1)
                if len(wire) > MAX_WIRE or not wire.endswith(b"\n"):
                    raise ValueError("Incomplete owner response; usage is unknown")
                response = json.loads(wire)
                if (response.get("sequence") != self.sequence
                        or response.get("identity_sha256") != request["identity_sha256"]):
                    raise ValueError("Owner response identity or sequence changed")
                if response.get("error"):
                    raise RuntimeError("Owner operation failed: " + json.dumps(response["error"]))
                return response["result"]
            except BaseException:
                self.failed = True
                raise


class ScriptedOwner:
    """Explicit CPU fixture using real tokenizer IDs and programmed responses, never a model."""
    programmed_fixture = True
    path = "project"
    actor_steps = critic_steps = 0

    def __init__(self, tokenizer, output, responses):
        self.tokenizer, self.output, self.responses = tokenizer, Path(output), responses
        self.output.mkdir(parents=True, exist_ok=False)
        (self.output / "calls").mkdir()
        self.contract = copy.deepcopy(CONTRACT)
        self.recipe = {"max_length": 18432, "max_output_tokens": 2048, "temperature": 0.7}
        self.inference_profile = {"path": "project", "contract": self.contract,
                                  "programmed_fixture_only": True}
        self.inference_profile_sha256 = digest(json_bytes(self.inference_profile))
        self.phase, self.window_id, self.used_window_ids, self.calls = "idle", None, [], 0
        self._identity = {"raw_release": True, "checkpoint": None, "adapter_sha256": None,
                          "policy_version": "synthetic-v054-owner", "programmed_fixture_only": True}
        self.busy = False

    def freeze_identity(self):
        return copy.deepcopy(self._identity)

    def capture_evaluation_state(self):
        if self.phase != "idle":
            raise ValueError("Fixture owner is not idle")
        return {"synthetic": True}

    def begin_window(self, window_id):
        if self.phase != "idle" or window_id in self.used_window_ids:
            raise ValueError("Cannot reuse a fixture window")
        self.phase, self.window_id = "collecting", window_id
        self.used_window_ids.append(window_id)

    def reseed(self, seed, *, label):
        return {"seed": seed, "label": label, "programmed_fixture_only": True}

    def generate_native(self, native):
        from .software_calibration_runtime_v051 import validate_native_input
        if self.phase != "collecting" or not validate_native_input(native, self.contract):
            raise ValueError("Fixture must retain the actual input contract")
        if self.calls >= len(self.responses):
            raise RuntimeError("Programmed fixture responses exhausted; no retry")
        raw = self.responses[self.calls]
        self.calls += 1
        ids = self.tokenizer.encode(raw, add_special_tokens=False) + [248044]
        result = {"attempt_id": "programmed-" + str(self.calls), "actor_identity": self.freeze_identity(),
                  "input": native, "output_ids": ids, "raw_generated_text": raw,
                  "finish_reason": "stop", "behavior_logprobs": [0.0] * len(ids),
                  "usage": {"prompt_tokens": native["prompt_tokens"], "completion_tokens": len(ids),
                            "total_tokens": native["prompt_tokens"] + len(ids)},
                  "seconds": 0.0, "effective_generation": {"programmed_fixture_only": True},
                  "execution_metadata": {"programmed_fixture_only": True, "model_calls": 0}}
        write_new(self.output / "calls" / (result["attempt_id"] + ".json"), result)
        return result

    def prepare_request(self, request):
        from .software_calibration_runtime_v051 import CalibrationActor
        return CalibrationActor.prepare_request(self, request)

    def complete(self, request, *, timeout_seconds):
        from .software_calibration_runtime_v051 import CalibrationActor
        return CalibrationActor.complete(self, request, timeout_seconds=timeout_seconds)

    def finish_evaluation(self, entries, output):
        self.phase = "idle"
        Path(output).mkdir(parents=True, exist_ok=False)
        return {"programmed_fixture_only": True, "entries": entries}

    def finish_evaluation_guard(self, snapshot):
        return {"learning_unchanged": True, "rng_restored_exactly": True,
                "programmed_fixture_only": True, "actual_model_rng_checked": False}


class ScriptedCodec:
    def decode(self, *, request, result):
        from .candidate_runtime_v017 import parse_candidate_generated
        message, error = parse_candidate_generated(result["raw_generated_text"], request)
        if error:
            raise ValueError(error)
        return {"message": message, "programmed_fixture_only": True}


class OwnerService:
    def __init__(self, owner, *, output, codec=None, synthetic=False, smoke=False,
                 max_smoke_requests=2, resource_binding=None):
        from .software_calibration_runtime_v051 import CalibrationActor
        self.owner, self.root, self.codec = owner, Path(output), codec
        self.synthetic, self.smoke = synthetic, smoke
        self.resource_binding = resource_binding
        self.max_smoke_requests, self.smoke_requests = max_smoke_requests, 0
        self.root.mkdir(parents=True, exist_ok=True)
        self.entered, self.closed, self.snapshot, self.bridge = False, False, None, None
        self.sequences, self.arm = {}, None
        self.identity = {
            "version": VERSION, "actor_identity": owner.freeze_identity(), "contract": owner.contract,
            "recipe": owner.recipe, "inference_profile": owner.inference_profile,
            "path": owner.path, "owner_class": type(owner).__module__ + "." + type(owner).__name__,
            "actual_CalibrationActor": isinstance(owner, CalibrationActor),
            "original_generate_native": (not synthetic and
                owner.generate_native.__func__ is CalibrationActor.generate_native),
            "programmed_fixture_only": synthetic, "capacity_smoke_only": smoke,
            "max_smoke_requests": max_smoke_requests if smoke else 0,
            "formal_episode_authorized": False,
            "resource_protocol": "v053-r3-r5-reusable-cache" if resource_binding else "synthetic-no-GPU",
            "resource_binding": resource_binding,
            "source": reference(__file__),
        }

    def generation_context(self):
        if self.synthetic:
            return nullcontext()
        from .software_panel_resources_v053 import native_context
        return native_context(self.owner, self.root / "native-cache", self.resource_binding)

    def dispatch(self, request):
        if (request["version"] != VERSION
                or request["identity_sha256"] != digest(json_bytes(self.identity))
                or request["sequence"] != self.sequences.get(request["session"], 0) + 1):
            raise ValueError("Owner IPC session, sequence or identity differs")
        self.sequences[request["session"]] = request["sequence"]
        operation, arguments = request["operation"], request["arguments"]
        if operation == "begin":
            if self.entered or self.closed:
                raise ValueError("Each resident service accepts one independent episode only")
            slot, claim = arguments["slot"], arguments["claim_id"]
            if self.synthetic or self.smoke:
                if not slot["slot_id"].startswith("synthetic-"):
                    raise ValueError("Preparation service cannot enter a formal slot")
            else:
                permit = json.loads(checked(arguments["authorization"]).read_text())
                if (permit.get("execution_authorized") is not True
                        or slot["slot_id"] not in permit.get("slot_ids", [])):
                    raise ValueError("Formal owner work needs its separate slot authorization")
            self.entered, self.arm = True, slot["arm"]
            write_new(self.root / "entered.json", {"slot": slot, "claim_id": claim})
            self.snapshot = self.owner.capture_evaluation_state()
            self.owner.begin_window(slot["slot_id"] + ":" + claim)
            seeded = self.owner.reseed(slot["seed"], label=slot["slot_id"])
            if self.arm == "MATCH" and not self.smoke:
                self.bridge = MatchBridge(
                    self.owner, codec=self.codec, folder=self.root / "match-ledger",
                    slot_id=slot["slot_id"], execution_authorized=not self.synthetic,
                    allow_programmed_fixture=self.synthetic)
                self.bridge.started = arguments["started"]
            return {"seed": seeded, "window_id": self.owner.window_id,
                    "owner_identity": self.identity, "slot": slot}
        if not self.entered or self.closed:
            raise ValueError("Owner generation requires one entered, open episode")
        if operation == "match_count":
            from .software_benchmark_exact_transport_v054 import ProjectExactCounter
            return ProjectExactCounter(self.bridge).measure(arguments["request"])
        if operation == "match_complete":
            with self.generation_context():
                body = self.bridge.complete_request(arguments["request"], usage_id=arguments["usage_id"])
            return {"body": body, "ledger": self.bridge.ledger.snapshot()}
        if operation == "project_complete":
            if self.arm != "PROJECT" or self.smoke:
                raise ValueError("Wrong numerical endpoint")
            with self.generation_context():
                return self.owner.complete(arguments["request"], timeout_seconds=600)
        if operation == "smoke_count":
            if not self.smoke:
                raise ValueError("Smoke counting is not a formal episode endpoint")
            from .software_benchmark_match_v054 import prepare_native_input
            return prepare_native_input(self.owner.tokenizer, arguments["request"], self.owner.contract)
        if operation == "smoke_generate":
            if not self.smoke or self.smoke_requests >= self.max_smoke_requests:
                raise ValueError("No additional capacity smoke requests authorized")
            self.smoke_requests += 1
            from .software_benchmark_match_v054 import prepare_native_input
            native = prepare_native_input(self.owner.tokenizer, arguments["request"], self.owner.contract)
            with self.generation_context():
                return self.owner.generate_native(native)
        if operation == "finish":
            self.owner.finish_evaluation(arguments.get("entries", []), self.root / "owner-evaluation")
            guard = self.owner.finish_evaluation_guard(self.snapshot)
            if not guard["learning_unchanged"] or not guard["rng_restored_exactly"]:
                raise ValueError("Owner guard failed")
            self.closed = True
            return {"guard": guard, "receipt": write_new(self.root / "owner-close.json", guard),
                    "ledger": self.bridge.ledger.snapshot() if self.bridge else None}
        raise ValueError("Unknown owner operation")


def serve(service, socket_path, identity_output):
    socket_path = Path(socket_path)
    if socket_path.exists():
        raise FileExistsError("Cannot replace an owner socket")
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    write_new(identity_output, service.identity)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            request = {}
            try:
                raw = self.rfile.readline(MAX_WIRE + 1)
                if len(raw) > MAX_WIRE or not raw.endswith(b"\n"):
                    raise ValueError("Incomplete owner request")
                request = json.loads(raw)
                result = {"result": service.dispatch(request)}
            except BaseException as error:
                service.closed = True
                result = {"error": {"type": type(error).__name__, "message": str(error)},
                          "actual_usage": None, "automatic_retry": False}
            response = {"sequence": request.get("sequence"),
                        "identity_sha256": digest(json_bytes(service.identity)), **result}
            payload = wire_json(response)
            if len(payload) > MAX_WIRE:
                service.closed = True
                raise ValueError("Owner response cannot be truncated")
            self.wfile.write(payload)

    try:
        with socketserver.UnixStreamServer(str(socket_path), Handler) as server:
            os.chmod(socket_path, 0o600)
            atomic_write(service.root / "service-ready.json", json_bytes({
                "version": VERSION, "identity": reference(identity_output),
                "socket": str(socket_path), "pid": os.getpid(), "ready": True}))
            server.serve_forever(poll_interval=0.1)
    finally:
        socket_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--model-local", type=Path, required=True)
    parser.add_argument("--model-manifest", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--identity-output", type=Path, required=True)
    parser.add_argument("--verified-source-receipt", type=Path)
    parser.add_argument("--allow-gpu-load", action="store_true")
    parser.add_argument("--load-admission", type=Path)
    parser.add_argument("--capacity-smoke-only", action="store_true")
    parser.add_argument("--max-smoke-requests", type=int, default=2)
    parser.add_argument("--scripted-responses", type=Path)
    parser.add_argument("--codec-socket", type=Path)
    parser.add_argument("--codec-identity", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text())
    synthetic = args.scripted_responses is not None
    resource_binding = None
    if synthetic:
        if args.allow_gpu_load or args.capacity_smoke_only or contract != CONTRACT:
            raise ValueError("Programmed CPU fixture cannot authorize GPU or change contract")
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(args.model_local, local_files_only=True)
        owner = ScriptedOwner(tokenizer, args.output / "owner", json.loads(args.scripted_responses.read_text()))
        codec = ScriptedCodec()
    else:
        if not args.allow_gpu_load or args.load_admission is None:
            raise ValueError("GPU model load requires explicit admission and CLI switch")
        admission = json.loads(args.load_admission.read_text())
        if (admission.get("model_loading_authorized") is not True
                or admission.get("model_manifest") != reference(args.model_manifest)
                or admission.get("contract_sha256") != digest(json_bytes(contract))):
            raise ValueError("GPU admission differs from the fixed model/contract")
        if not args.capacity_smoke_only and contract != CONTRACT:
            raise ValueError("Formal MATCH/PROJECT contract cannot change")
        if not 1 <= args.max_smoke_requests <= 2:
            raise ValueError("Capacity smoke permits at most two requests")
        from .software_calibration_runtime_v051 import load_actor
        from . import software_panel_resources_v053 as resources
        resource_binding = resources.binding_from_environment()
        resources.acquire_startup(args.output / "startup", resource_binding, identity={
            "load_admission": reference(args.load_admission), "capacity_smoke_only": args.capacity_smoke_only,
            "formal_execution_authorized": False})
        owner = load_actor(
            args.model_local, manifest=args.model_manifest, contract=contract, path="project",
            output=args.output / "owner", checkpoint=None,
            verified_source_receipt=(reference(args.verified_source_receipt)
                                     if args.verified_source_receipt else None))
        codec = None
        if args.codec_socket and args.codec_identity:
            from .software_benchmark_codec_v054 import UnixSocketCodec
            codec = UnixSocketCodec(args.codec_socket, json.loads(args.codec_identity.read_text()))
    serve(OwnerService(owner, output=args.output, codec=codec, synthetic=synthetic,
                       smoke=args.capacity_smoke_only, max_smoke_requests=args.max_smoke_requests,
                       resource_binding=resource_binding),
          args.socket, args.identity_output)


if __name__ == "__main__":
    main()
