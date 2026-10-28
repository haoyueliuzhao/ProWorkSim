"""Only trusted managed-tree/public-test RPC inside one owned private actor."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from proworksim import software_benchmark_managed_actor_v064 as managed
from proworksim.repository_sources_v054 import normalize_policy, snapshot_repository
from proworksim.storage import digest, json_bytes

IMPLEMENTATION = "v064-private-docker-managed-worker-r1"


def native_isolation_module():
    path = Path(__file__).resolve().with_name("worker.py")
    if path != Path("/opt/pws-runtime/worker.py") or not path.is_file():
        raise ValueError("Managed actor requires the same copied private isolation implementation")
    spec = importlib.util.spec_from_file_location("pws_v064_native_isolation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def emit(value):
    text = json.dumps(value, ensure_ascii=False) + "\n"
    if len(text.encode("utf-8")) > managed.MAX_RPC_BYTES:
        raise managed.ManagedInterfaceLimit("Managed response exceeds its exact serialized RPC bound")
    sys.stdout.write(text)
    sys.stdout.flush()


def serve(config):
    if config.get("version") != IMPLEMENTATION:
        raise ValueError("Wrong managed actor implementation")
    counters = {"network_attempts": 0, "weight_files_opened": 0, "gpu_device_opens": 0}
    phase = [True]
    def audit(event, args):
        if not phase[0]:
            return
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            counters["network_attempts"] += 1
            raise RuntimeError("No network in trusted managed actor preload")
        if event == "open" and args and isinstance(args[0], (str, bytes)):
            name = os.fsdecode(args[0])
            if name.endswith((".safetensors", ".gguf")) or "pytorch_model" in name:
                counters["weight_files_opened"] += 1
                raise RuntimeError("No model weights in the managed actor")
            if name.startswith(("/dev/nvidia", "/dev/dri/")):
                counters["gpu_device_opens"] += 1
                raise RuntimeError("No GPU in the managed actor")
    sys.addaudithook(audit)
    native = native_isolation_module()
    native.install_lifecycle_deadline(config)
    public = native.validate_config({**config, "version": native.IMPLEMENTATION})
    raw_public = Path("/pws/control/public-environment.json").read_bytes()
    if hashlib.sha256(raw_public).hexdigest() != config["public_environment_sha256"] or json.loads(raw_public) != public:
        raise ValueError("Copied public environment identity changed")
    entry = managed.validate_public_entry(config["public_test_entry"],
        instance_id=config["instance_id"], public_python=public["public_python"])
    policy = normalize_policy(config.get("file_policy"))
    links = managed.checked_gitlinks(config.get("gitlinks", []))
    identity = subprocess.run(["/usr/bin/git", "-c", "safe.directory=/testbed", "-C", "/testbed",
                              "rev-parse", "HEAD", "HEAD^{tree}"], env=public["environment"],
                             capture_output=True, timeout=30, check=True).stdout.decode().splitlines()
    dirty = subprocess.run(["/usr/bin/git", "-c", "safe.directory=/testbed", "-C", "/testbed",
                           "status", "--porcelain"], env=public["environment"],
                          capture_output=True, timeout=30, check=True).stdout
    if identity != [config["baseline_head"], config["baseline_tree"]] or dirty:
        raise ValueError("The managed actor needs its exact admitted clean baseline")
    baseline = snapshot_repository("/testbed", file_policy=policy, gitlinks=links)
    isolation = native.seal_actor(public)
    phase[0] = False
    uploads = managed.ManagedUploadReceiver("/home/actor/managed-uploads", hard_at=config["lifecycle_deadline"])
    emit({"type": "ready", "version": managed.VERSION, "implementation": IMPLEMENTATION,
          "isolation": isolation, "managed_operations": ["managed_public_test", "sync_terminal"],
          "managed_upload_protocol": managed.upload_protocol(),
          "public_environment_sha256": config["public_environment_sha256"],
          "public_environment_kind": public["kind"], "public_python": public["public_python"],
          "public_test_entry_sha256": digest(json_bytes(entry)),
          "file_policy": policy, "initial_tree_sha256": baseline["tree"]["tree_sha256"],
          "baseline": {"head": identity[0], "tree": identity[1], "working_tree_clean": True},
          "rootfs_binding": {"official_task_admitted": True, "kind": "official_image",
              "instance_id": config["instance_id"], "image_id": config["actor_image_id"],
              "admission_source": "host_verified_original_sanitized_actor_image"},
          "vision_enabled": False, "model_calls": 0, "unmanaged_model_tool": False,
          "trusted_preload_counters": counters,
          "trusted_preload_scope": "isolation-helper import, public baseline capture and actor seal"})
    sequence, test_calls, terminal_locked = 0, 0, False
    while True:
        line = sys.stdin.buffer.readline(managed.MAX_RPC_BYTES + 1)
        if not line:
            if uploads.pending is not None:
                uploads.abort()
                raise managed.ManagedTransferError("Controller ended before its full upload committed")
            return
        if len(line) > managed.MAX_RPC_BYTES or not line.endswith(b"\n"):
            raise managed.ManagedInterfaceLimit("Actor RPC frame exceeds its declared exact bound")
        request = json.loads(line)
        sequence += 1
        if request.get("id") != sequence:
            raise ValueError("Managed actor RPC identity was replayed or reordered")
        if set(request) == {"id", "op"} and request["op"] == "close":
            if uploads.pending is not None:
                uploads.abort()
                error = managed.ManagedTransferError("Cannot close with an incomplete managed upload")
                emit({"type": "error", "id": sequence, "error_type": type(error).__name__,
                      "error": str(error), "classification": error.classification})
                raise error
            managed._reap_private_children()
            emit({"type": "closed", "id": sequence, "model_calls": 0,
                  "managed_public_test_calls": test_calls, "terminal_synchronized": terminal_locked,
                  "owned_children_quiescent": True, "process_tree_quiescence_proven": False})
            return
        try:
            if (set(request) != {"id", "tool", "action"}
                    or request["tool"] not in {managed.UPLOAD_BEGIN, managed.UPLOAD_CHUNK, managed.UPLOAD_COMMIT}
                    or terminal_locked):
                raise managed.ManagedTransferError("Only the bounded trusted upload protocol before terminal lock is allowed")
            if request["tool"] in {managed.UPLOAD_BEGIN, managed.UPLOAD_CHUNK}:
                method = uploads.begin if request["tool"] == managed.UPLOAD_BEGIN else uploads.chunk
                ack = method(request["action"])
                emit({"type": "observation", "id": sequence, "tool": request["tool"], "result": ack})
                continue
            operation, payload, upload_receipt = uploads.commit(request["action"])
            provenance = payload["request"]
            if (provenance.get("instance_id") != config["instance_id"]
                    or not isinstance(provenance.get("source_reference"), dict)
                    or set(provenance["source_reference"]) != {"object_id", "version_id"}
                    or provenance.get("hidden_evaluation") is not False
                    or provenance.get("arbitrary_command") is not False
                    or type(provenance.get("hard_deadline_monotonic")) not in (int, float)
                    or not time.monotonic() < provenance["hard_deadline_monotonic"] <= config["lifecycle_deadline"]):
                raise ValueError("Managed operation lost task, version, deadline or public-only provenance")
            candidate = managed.reconstruct_delta(baseline, payload, gitlinks=links)
            synchronized = managed.synchronize_tree("/testbed", candidate, gitlinks=links)
            if operation == "managed_public_test":
                if provenance.get("call_index") != test_calls + 1 or test_calls >= 512:
                    raise ValueError("One numbered public test per accepted managed operation")
                test_calls += 1
                result = managed.run_public_entry(entry, root="/testbed", environment=public["environment"],
                    request=provenance, candidate_tree_sha256=candidate["tree_sha256"])
            else:
                terminal_locked = True
                result = {**synchronized, "source_reference": provenance["source_reference"],
                          "terminal_locked": True, "model_can_resume": False}
            emit({"type": "observation", "id": sequence, "tool": operation, "result": result,
                  "upload_receipt": {**upload_receipt, "operation_executed": True}})
        except Exception as error:
            uploads.abort()
            emit({"type": "error", "id": sequence, "tool": request.get("tool"),
                  "error_type": type(error).__name__, "error": str(error),
                  "classification": getattr(error, "classification", "technical_unknown")})
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    serve(json.loads(parser.parse_args().config.read_bytes()))
