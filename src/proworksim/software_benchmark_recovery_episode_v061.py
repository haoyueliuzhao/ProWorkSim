"""Fresh, separately labelled native REF recovery episodes in owned Docker pairs.

The old thirteen interrupted episodes are never edited or resumed. A new pair
uses the same task, seed and budget, keeps the actual public checkout shared RO
to its trusted SDK controller, and fixes one terminal snapshot after all writers
have stopped. No host mount, namespace or shared service operation occurs here.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import threading
import time
import traceback

from . import software_benchmark_dispatch_v061 as policy
from . import software_benchmark_sdk_bundle_v061 as runtime
from .repository_sources_v054 import normalize_policy, validate_path
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_docker_actor_v061 import (
    DockerStdioChannel, OwnedActorPair, StdioBridge, validate_actor_ready,
)
from .software_benchmark_model_fifo_v061 import serve_model_channel
from .software_benchmark_native_artifact_v054 import PROTOCOL, native_tree_manifest, validate_native_tree
from .software_benchmark_native_rootfs_v054 import image_environment
from .software_benchmark_ref_budget_v056 import validate_condition
from .software_benchmark_snapshot_recovery_v061 import export_utf8_patch
from .storage import json_bytes

ROOT, BATCH = policy.ROOT, policy.BATCH_ROOT
VERSION = "v061-private-native-recovery-episode-r1"
PRIVATE_ROOTS = ["/opt/pws-runtime/" + name for name in ("site", "overlay", "upstream-tools", "project")]
GIB = 1024**3


def load(ref):
    return json.loads(checked(ref).read_bytes())


def capacity():
    memory = next(int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()
                  if line.startswith("MemAvailable:"))
    disk, load1 = shutil.disk_usage(ROOT).free, os.getloadavg()[0]
    return {"admit": memory >= 200 * GIB and disk >= 256 * GIB and load1 < 140,
            "memory_available_bytes": memory, "disk_free_bytes": disk, "load_1m": load1,
            "memory_floor_with_two_pairs_and_two_graders": 200 * GIB,
            "disk_floor_with_two_actor_reservations": 256 * GIB}


def wait_capacity(stop_event=None):
    while True:
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("Recovery cancelled before resource admission")
        policy.require_v061_allowed("v061.run")
        result = capacity()
        if result["admit"]:
            return result
        if stop_event is None:
            time.sleep(30)
        else:
            stop_event.wait(30)


def public_environment(config):
    mapping = load(config["scorer_request_base"]["baseline_mapping"])
    blob = Path(mapping["actor_config_blob"])
    public = image_environment(blob.read_bytes(), image_id=mapping["actor_image_id"],
                               public_python=mapping["public_python"])
    return mapping, public


def archive_bundle(path, *, gitlinks=()):
    """Decode a complete stopped worktree without following candidate symlinks."""
    files, metadata, pending = {}, {}, []
    limits, total = normalize_policy(), 0
    with tarfile.open(path, "r|*") as archive:
        for member in archive:
            name = PurePosixPath(member.name.removeprefix("./"))
            if name.is_absolute() or ".." in name.parts or not name.parts or name.parts[0] != "testbed":
                raise ValueError("Docker worktree archive escapes its declared root")
            relative = "/".join(name.parts[1:])
            if not relative or ".git" in name.parts or member.isdir():
                continue
            validate_path(relative)
            if relative in files or any(item[0] == relative for item in pending):
                raise ValueError("Duplicated worktree archive entry")
            if member.islnk():
                target = PurePosixPath(member.linkname.removeprefix("./"))
                if target.is_absolute() or ".." in target.parts or target.parts[:1] != ("testbed",):
                    raise ValueError("Repository hardlink target escapes the task archive")
                pending.append((relative, "/".join(target.parts[1:]), member.mode))
                continue
            if member.issym():
                raw = member.linkname.encode("utf-8", "surrogateescape")
                try:
                    value, encoding = raw.decode("utf-8"), "symlink-target"
                except UnicodeDecodeError:
                    value, encoding = base64.b64encode(raw).decode("ascii"), "base64-symlink-target"
                item = {"kind": "symlink", "encoding": encoding, "mode": "120000"}
            elif member.isfile():
                if member.size > limits["max_file_bytes"] or total + member.size > limits["max_source_bytes"]:
                    raise ValueError("Original full-tree deployment limit exceeded; no truncation")
                raw = archive.extractfile(member).read()
                try:
                    value = raw.decode("utf-8")
                    if b"\0" in raw:
                        raise UnicodeError
                    encoding = "utf-8"
                except UnicodeError:
                    value, encoding = base64.b64encode(raw).decode("ascii"), "base64"
                item = {"kind": "file", "encoding": encoding, "mode": "100755" if member.mode & 0o111 else "100644"}
            else:
                raise ValueError("Repository archive contains an unsupported special file")
            total += len(raw)
            if total > limits["max_source_bytes"]:
                raise ValueError("Original full-tree deployment limit exceeded; no truncation")
            files[relative], metadata[relative] = value, item
    while pending:
        resolved = []
        for name, target, mode in pending:
            if target in files:
                if metadata[target]["kind"] != "file":
                    raise ValueError("A repository hardlink must identify a regular file")
                files[name], metadata[name] = files[target], {**metadata[target], "mode": "100755" if mode & 0o111 else "100644"}
                resolved.append((name, target, mode))
        if not resolved:
            raise ValueError("Unresolved or out-of-tree hardlink in task archive")
        pending = [item for item in pending if item not in resolved]
    validate_native_tree(files, metadata, limits)
    return {"files": dict(sorted(files.items())), "entry_metadata": dict(sorted(metadata.items())),
            "tree": native_tree_manifest(files, metadata), "file_policy": limits, "truncated": False,
            "capture_scope": "complete_owned_Docker_named_volume_after_writer_boundary",
            "native_artifact_protocol": PROTOCOL, "symlink_targets_followed": False,
            "excluded_control_metadata": [".git at every repository depth"], "gitlinks": list(gitlinks)}


def extract_controller_output(archive_path, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    seen, total = set(), 0
    with tarfile.open(archive_path, "r|*") as archive:
        for member in archive:
            name = PurePosixPath(member.name.removeprefix("./"))
            if name.is_absolute() or ".." in name.parts or name.parts[:1] != ("output",):
                raise ValueError("Controller output archive escapes its private output root")
            relative = Path(*name.parts[1:])
            if str(relative) == ".":
                if not member.isdir():
                    raise ValueError("Controller output root is not a directory")
                continue
            if relative in seen:
                raise ValueError("Duplicate controller output archive entry")
            seen.add(relative)
            target = destination / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile() or member.size > 512 * 1024**2:
                raise ValueError("Controller output contains a link/special/oversized file")
            total += member.size
            if total > 2 * GIB:
                raise ValueError("Controller output exceeds its bounded evidence capacity")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                shutil.copyfileobj(archive.extractfile(member), output, length=1024**2)
    return {"container_prefix": "/pws/output", "host_prefix": str(destination.resolve()),
            "bytes": total, "entries": len(seen), "raw_json_references_rewritten": False,
            "interpretation": "Container-absolute evidence references resolve through this mapping"}


def read_container_json(container, path):
    chunks, _ = container.get_archive(path)
    data = bytearray()
    for chunk in chunks:
        data.extend(chunk)
        if len(data) > 2 * 1024**2:
            raise ValueError("Small controller status artifact exceeds its bound")
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        files = [member for member in archive if member.isfile()]
        if len(files) != 1 or PurePosixPath(files[0].name).name != Path(path).name:
            raise ValueError("Unexpected controller status archive")
        return json.load(archive.extractfile(files[0]))


def wait_controller_ready(container, *, timeout=120):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        container.reload()
        if not container.attrs["State"]["Running"]:
            raise RuntimeError("Private SDK controller exited before initialization")
        try:
            value = read_container_json(container, "/pws/output/controller-ready.json")
        except Exception as error:
            if type(error).__name__ != "NotFound":
                raise
        else:
            if value.get("trusted_SDK_imports_complete") is not True or value.get("model_calls") != 0:
                raise ValueError("Controller initialization already entered a model")
            return value
        time.sleep(.5)
    raise TimeoutError("Private SDK controller initialization deadline exceeded")


def snapshot(pair, folder, *, name, gitlinks):
    archive_path = folder / (name + ".tar")
    exported = pair.download_archive("actor", "/testbed", archive_path)
    bundle = archive_bundle(archive_path, gitlinks=gitlinks)
    ref = write_new(folder / (name + ".json"), bundle)
    write_new(folder / (name + "-provenance.json"), {"archive": exported, "snapshot": ref,
        "model_or_grader_calls": 0, "source": "fresh_owned_actor_named_volume"})
    return bundle, ref


def _row_and_config(original_row, diagnostic):
    auth = policy.require_v061_allowed("v061.run")
    plan = load(auth["plan"])
    rows = [row for row in plan["rows"] if row["slot_index"] == original_row["slot_index"]]
    if rows != [original_row] or original_row["measurement_kind"] != "fresh_generation_recovery":
        raise ValueError("Only one of the thirteen fixed new-generation recovery rows may enter")
    if diagnostic and original_row["slot_index"] != min(r["slot_index"] for r in plan["rows"]):
        raise ValueError("Deployment control must use the predeclared first task")
    config = load(original_row["original_config"])
    condition = load(config["configuration"])
    limits = validate_condition(condition)
    if limits["input_plus_output_tokens"] != original_row["input_plus_output_tokens"] or config.get("seed") != original_row["seed"]:
        raise ValueError("Original seed or cumulative budget changed")
    return config, condition, limits


def _run(original_row, resident, *, diagnostic=False, diagnostic_index=1, stop_event=None):
    config, condition, limits = _row_and_config(original_row, diagnostic)
    index = original_row["slot_index"]
    output = BATCH / ("diagnostic-" + str(diagnostic_index) if diagnostic else "episodes/" + str(index))
    if (output / "result.json").exists():
        return reference(output / "result.json")
    if output.exists():
        raise ValueError("An entered or partially prepared recovery is not automatically replayed")
    admission = wait_capacity(stop_event)
    output.mkdir(parents=True, mode=0o700)
    result = {"version": VERSION, "status": "technical_unknown", "original_slot_id": original_row["slot_id"],
        "slot_id": original_row["recovery_slot_id"], "measurement_kind": "zero_model_diagnostic" if diagnostic else "fresh_generation_recovery",
        "original_config": original_row["original_config"], "condition_id": original_row["condition_id"],
        "instance_id": original_row["instance_id"], "seed": original_row["seed"],
        "original_unknown_preserved": True, "automatic_replay": False, "capacity_admission": admission,
        "candidate_lock": None, "model_calls": 0 if diagnostic else None}
    write_new(output / "execution-intent.json", result)
    pair = client = bridge = model_channel = model_thread = model_transport = watchdog = None
    model_result, handles = {}, []
    model_stop = threading.Event()
    lifecycle_expired = threading.Event()
    watchdog_errors = []
    controller = None
    terminal_ref = None
    try:
        bundle = runtime.prepare_bundle()
        mapping, public = public_environment(config)
        if len(os.sched_getaffinity(0)) < (4 if diagnostic else 12):
            raise RuntimeError("Native actor/controller lanes exceed the available CPU affinity")
        import docker
        socket = Path(config["scorer_request_base"]["docker_socket"]).resolve()
        if not socket.is_socket():
            raise ValueError("The existing project Docker API is unavailable")
        client = docker.DockerClient(base_url="unix://" + str(socket), timeout=120)
        lifecycle_deadline = time.monotonic() + (180 if diagnostic else limits["hard_seconds"] + 600)
        pair = OwnedActorPair(client, slot_index=index, original_slot_id=original_row["slot_id"],
            instance_id=original_row["instance_id"], diagnostic=diagnostic, diagnostic_index=diagnostic_index,
            deadline=lifecycle_deadline)
        def expire_owned_pair():
            lifecycle_expired.set()
            model_stop.set()
            try:
                if model_transport is not None:
                    model_transport.abort()
                pair.stop_writers()
            except Exception as error:
                watchdog_errors.append({"type": type(error).__name__, "message": str(error)})
        watchdog = threading.Timer(max(.01, lifecycle_deadline - time.monotonic()), expire_owned_pair)
        watchdog.daemon = True
        watchdog.start()
        pair.create_volume()
        gitlinks = [{"path": row["path"], "oid": row["official_commit"]} for row in mapping.get("submodules", [])]
        write_new(output / "public-environment.json", public)
        public_raw = (output / "public-environment.json").read_bytes()
        actor_config = {"version": "v061-private-docker-native-worker-r1", "private_roots": PRIVATE_ROOTS,
            "stdlib": "/opt/pws-runtime/sysroot/usr/lib/python3.12", "vision_enabled": False,
            "public_environment": public, "public_environment_sha256": hashlib.sha256(public_raw).hexdigest(),
            "instance_id": original_row["instance_id"], "actor_image_id": mapping["actor_image_id"],
            "baseline_head": mapping["actor_head"], "baseline_tree": mapping["actor_tree"], "official_task_admitted": True,
            "lifecycle_deadline": lifecycle_deadline, "maximum_lifecycle_seconds": 180 if diagnostic else 24000}
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("Recovery cancelled before actor creation")
        actor_obj = pair.create_container("actor", runtime.python_argv([
            "/opt/pws-runtime/project/tools/run_native_worker_docker_v061.py", "--config", "/pws/control/actor-config.json"]),
            environment=runtime.runtime_environment())
        pair.upload_archive("actor", bundle["archive"])
        pair.upload_file("actor", "/pws/control/actor-config.json", json_bytes(actor_config))
        pair.upload_file("actor", "/pws/control/public-environment.json", public_raw)
        actor_stderr = (output / "actor.stderr").open("xb")
        handles.append(actor_stderr)
        actor_channel = pair.attach("actor", actor_stderr)
        pair.start("actor")
        ready = json.loads(actor_channel.readline(min(lifecycle_deadline, time.monotonic() + 120)))
        write_new(output / "actor-ready.json", ready)
        write_new(output / "actor-isolation.json", validate_actor_ready(ready, public_environment_sha256=actor_config["public_environment_sha256"]))
        if ready.get("baseline") != {"head": mapping["actor_head"], "tree": mapping["actor_tree"], "working_tree_clean": True}:
            raise ValueError("Actual live volume baseline differs from the original task")
        baseline, baseline_ref = snapshot(pair, output, name="baseline-snapshot", gitlinks=gitlinks)
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("Recovery cancelled before controller creation")
        controller = pair.create_container("controller", runtime.python_argv([
            "/opt/pws-runtime/project/tools/run_ref_budget_controller_v061.py", "--config", "/pws/control/controller-config.json"]),
            environment=runtime.runtime_environment())
        pair.upload_archive("controller", bundle["archive"])
        controller_inputs = runtime.controller_inputs(config, original_row["recovery_slot_id"], ready,
            {} if diagnostic else resident["identity_value"], "http://127.0.0.1:18161" if diagnostic else resident["endpoint"], diagnostic=diagnostic)
        control_config = json.loads(controller_inputs["controller-config.json"])
        control_config.update(lifecycle_deadline=lifecycle_deadline,
                              maximum_lifecycle_seconds=180 if diagnostic else 24000)
        controller_inputs["controller-config.json"] = json_bytes(control_config)
        for filename, payload in controller_inputs.items():
            pair.upload_file("controller", "/pws/control/" + filename, payload)
        controller_stderr = (output / "controller.stderr").open("xb")
        handles.append(controller_stderr)
        controller_channel = pair.attach("controller", controller_stderr)
        pair.start("controller")
        write_new(output / "controller-ready.json", wait_controller_ready(controller,
            timeout=max(.01, min(120, lifecycle_deadline - time.monotonic()))))
        duration = 180 if diagnostic else limits["hard_seconds"]
        started = time.monotonic()
        deadline = min(lifecycle_deadline, started + duration)
        bridge = StdioBridge(actor_channel, controller_channel, deadline=deadline).start()
        if not diagnostic:
            from .software_benchmark_model_fifo_v061 import CancellableLoopbackHTTP
            model_transport = CancellableLoopbackHTTP(resident["endpoint"], resident["api_key_file"])
            exec_id = client.api.exec_create(controller.id, runtime.python_argv([
                "/opt/pws-runtime/project/tools/bridge_ref_model_fifo_v061.py"]), stdin=True, stdout=True, stderr=True, tty=False)["Id"]
            stream = client.api.exec_start(exec_id, socket=True, tty=False)
            model_stderr = (output / "model-bridge.stderr").open("xb")
            handles.append(model_stderr)
            model_channel = DockerStdioChannel(stream, model_stderr, max_line=32 * 1024**2 + 1)
            model_ready = threading.Event()
            def model_loop():
                model_result.update(serve_model_channel(model_channel, endpoint=resident["endpoint"],
                    key_file=resident["api_key_file"], deadline=deadline, stop_event=model_stop,
                    original_slot_id=original_row["slot_id"], on_ready=model_ready.set, transport=model_transport))
            model_thread = threading.Thread(target=model_loop, daemon=True, name="v061-model-fifo")
            model_thread.start()
            if not model_ready.wait(20):
                raise RuntimeError("Trusted model FIFO bridge did not initialize")
        start = {"started": started, "soft_at": started + (150 if diagnostic else limits["soft_seconds"]),
                 "hard_at": deadline, "guard_path": "/pws/output/guard.json"}
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("Recovery cancelled before model entry")
        pair.upload_file("controller", "/pws/output/guard.json", json_bytes({"stop_requested": False, "request_deadline": None}))
        pair.upload_file("controller", "/pws/control/start.json", json_bytes(start))
        write_new(output / "entered.json", {**start, "diagnostic": diagnostic,
            "resident_identity": None if diagnostic else resident["identity"], "runtime_bundle": reference(runtime.OUTPUT / "manifest.json")})
        while time.monotonic() < deadline:
            if stop_event is not None and stop_event.is_set():
                raise InterruptedError("Recovery coordinator requested owned-episode cancellation")
            controller.reload()
            if not controller.attrs["State"]["Running"]:
                break
            if bridge.errors or (model_result and model_result.get("status") == "technical_unknown"):
                raise RuntimeError("Native/model transport failed; preserve original attempt without replay")
            time.sleep(.5)
        else:
            raise TimeoutError("Recovery episode reached its original hard lifetime")
        controller_exit = controller.attrs["State"].get("ExitCode")
        actor_obj.reload()
        end_grace = time.monotonic() + 10
        while actor_obj.attrs["State"]["Running"] and time.monotonic() < end_grace:
            time.sleep(.1)
            actor_obj.reload()
        writer_proof = pair.stop_writers()
        writer_ref = write_new(output / "writer-quiescence.json", writer_proof)
        result["writer_quiescence"] = writer_ref
        transfer = pair.download_archive("controller", "/pws/output", output / "controller-output.tar", maximum_bytes=2 * GIB)
        relocation = extract_controller_output(output / "controller-output.tar", output / "controller-output")
        write_new(output / "controller-output-transfer.json", {"transfer": transfer, "relocation": relocation})
        child_path = output / "controller-output/controller-result.json"
        child = json.loads(child_path.read_bytes())
        result.update(controller_result=reference(child_path), controller_exit_code=controller_exit,
                      controller_status=child.get("status"), ledger=child.get("ledger"))
        if (controller_exit != 0 or child.get("status") != "closed" or writer_proof.get("all_quiet") is not True
                or lifecycle_expired.is_set()):
            raise RuntimeError("The native controller did not produce a trusted closed episode")
        bridge_proof = bridge.join(5)
        write_new(output / "native-bridge.json", bridge_proof)
        if not bridge_proof["threads_finished"] or bridge_proof["errors"]:
            raise RuntimeError("Native RPC bridge did not close without ambiguity")
        if model_thread is not None:
            model_thread.join(2)
            if model_thread.is_alive():
                raise RuntimeError("Model transport retained an in-flight request after controller closure")
            if model_result.get("status") not in {"channel_closed", "stopped_after_controller"}:
                raise RuntimeError("Model bridge did not finish with its closed controller")
        write_new(output / "candidate-claim.json", {"version": VERSION, "writer_quiescence": writer_ref,
            "slot_id": original_row["recovery_slot_id"], "selection": "single_final_worktree_after_generation"})
        terminal, terminal_ref = snapshot(pair, output, name="terminal-snapshot", gitlinks=gitlinks)
        if diagnostic:
            if not child.get("diagnostic_passed") or terminal["tree"] != baseline["tree"]:
                raise ValueError("Deployment control changed public source or did not pass every check")
            result.update(status="closed", diagnostic_passed=True, checks=child["checks"], model_calls=0)
        else:
            slot = {key: original_row[key] for key in ("slot_index", "task_index", "instance_id", "repo", "arm", "condition_id", "seed", "input_plus_output_tokens")}
            slot["slot_id"] = original_row["recovery_slot_id"]
            patch = export_utf8_patch(baseline, terminal, output / "candidate.patch", policy=terminal["file_policy"])
            lock = write_new(output / "candidate-lock.json", {"version": "software-benchmark-native-closure-v054",
                "implementation": VERSION, "claim_id": pair.claims["actor"]["sha256"], "slot": slot,
                "original_slot_id": original_row["slot_id"], "measurement_kind": "fresh_generation_recovery",
                "endpoint": "terminal_code", "quiescence": writer_ref, "baseline": baseline_ref,
                "candidate": terminal_ref, "patch_receipt": patch, "tree_sha256": patch["candidate_tree_sha256"],
                "delivery": None, "lock_before_grading": True, "model_calls": 0, "grading_calls": 0})
            result.update(status="closed", candidate_lock=lock, model_calls=child["ledger"]["attempts"],
                          known_actual_tokens=child["ledger"]["known_actual_tokens"])
    except Exception as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)},
                      traceback=traceback.format_exc())
    finally:
        cleanup_errors = []
        def cleanup_step(name, action):
            try:
                return action()
            except Exception as error:
                cleanup_errors.append({"step": name, "type": type(error).__name__, "message": str(error)})
                return None
        model_stop.set()
        if watchdog is not None:
            watchdog.cancel()
            watchdog.join(130)
            if watchdog.is_alive():
                cleanup_errors.append({"step": "lifecycle_watchdog", "message": "Owned-only watchdog remains alive"})
        result["lifecycle_deadline_reached"] = lifecycle_expired.is_set()
        cleanup_errors.extend({"step": "lifecycle_watchdog", **error} for error in watchdog_errors)
        if model_transport is not None:
            cleanup_step("model_abort", model_transport.abort)
        if model_channel is not None:
            cleanup_step("model_channel_close", model_channel.close)
        if model_thread is not None:
            model_thread.join(10)
            result["model_bridge_thread_finished"] = not model_thread.is_alive()
            if model_thread.is_alive():
                cleanup_errors.append({"step": "model_thread", "message": "Host model bridge is still alive"})
        if model_result:
            result["model_transport"] = cleanup_step("model_transport_receipt",
                lambda: write_new(output / "model-transport.json", model_result))
        if bridge is not None:
            bridge_cleanup = cleanup_step("native_bridge_close", bridge.close)
            if bridge_cleanup is not None and not bridge_cleanup["threads_finished"]:
                cleanup_errors.append({"step": "native_bridge_threads", "message": "Native bridge thread remains alive"})
        cleanup = {"version": VERSION, "quiescent": True, "cleanup_errors": [], "create_result_unknown": False,
                   "removed_roles": [], "create_result_unknown_roles": [], "retained_objects": [],
                   "all_owned_objects_removed": True}
        if pair is not None:
            preserve_worktree = False
            # On an abnormal path retain the private SDK evidence before removing its own container.
            if controller is not None and not (output / "controller-output").exists():
                try:
                    pair.stop_writers()
                    transfer_path = output / "controller-output-failure.tar"
                    pair.download_archive("controller", "/pws/output", transfer_path, maximum_bytes=2 * GIB)
                    relocation = extract_controller_output(transfer_path, output / "controller-output")
                    write_new(output / "controller-failure-output-relocation.json", relocation)
                except Exception as error:
                    result["evidence_retention_error"] = {"type": type(error).__name__, "message": str(error)}
            if "actor" in pair.objects and terminal_ref is None:
                try:
                    interrupted_quiet = pair.stop_writers()
                    if not interrupted_quiet["all_quiet"]:
                        raise RuntimeError("Cannot archive an interrupted worktree with uncertain writers")
                    archive = pair.download_archive("actor", "/testbed", output / "interrupted-worktree.tar")
                    result["interrupted_worktree"] = write_new(output / "interrupted-worktree.json", {
                        "archive": archive, "writer_quiescence": interrupted_quiet,
                        "official_final_candidate": False, "scoring_authorized_by_this_record": False,
                        "interpretation": "Stopped intermediate code retained only for failure diagnosis"})
                except Exception as error:
                    preserve_worktree = True
                    result["interrupted_worktree_retention_error"] = {"type": type(error).__name__, "message": str(error)}
            observed_cleanup = cleanup_step("owned_pair_cleanup", lambda: pair.cleanup(preserve_worktree=preserve_worktree))
            if observed_cleanup is not None:
                cleanup = observed_cleanup
            else:
                cleanup.update(quiescent=False, create_result_unknown=True)
        if client is not None:
            cleanup_step("docker_client_close", client.close)
        for handle in handles:
            cleanup_step("log_close", handle.close)
        cleanup["cleanup_errors"].extend(cleanup_errors)
        cleanup["quiescent"] = cleanup["quiescent"] and not cleanup_errors
        result["quiescence"] = write_new(output / "quiescence.json", cleanup)
        result["retained_objects"] = cleanup.get("retained_objects", [])
        if not cleanup["quiescent"]:
            result["status"] = "technical_unknown"
    if diagnostic:
        result["passed"] = result["status"] == "closed" and cleanup["quiescent"] is True
    return write_new(output / "result.json", result)


def run_episode(original_row, resident, *, stop_event=None):
    return _run(original_row, resident, stop_event=stop_event)


def run_diagnostic(index=1, *, stop_event=None):
    auth = policy.require_v061_allowed("v061.run")
    plan = load(auth["plan"])
    row = min(plan["rows"], key=lambda item: item["slot_index"])
    return _run(row, None, diagnostic=True, diagnostic_index=index, stop_event=stop_event)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot-index", type=int)
    parser.add_argument("--resident", type=Path)
    parser.add_argument("--diagnostic-index", type=int)
    args = parser.parse_args()
    if args.diagnostic_index:
        ref = run_diagnostic(args.diagnostic_index)
    else:
        plan = load(reference(policy.PLAN_FILE))
        row = next(item for item in plan["rows"] if item["slot_index"] == args.slot_index)
        ref = run_episode(row, json.loads(args.resident.read_bytes()))
    print(json.dumps(ref))


if __name__ == "__main__":
    main()
