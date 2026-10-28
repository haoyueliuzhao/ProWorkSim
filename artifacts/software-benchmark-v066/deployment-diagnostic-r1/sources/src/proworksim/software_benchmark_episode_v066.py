"""v066 continuation host around frozen v064 model-visible code and configs.

Original task/condition/seed identities remain fixed. This new host journals
local requests before forwarding and retains recoverable zero-request proofs.
No historical evidence or v064 source is overwritten.
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

from . import software_benchmark_dispatch_v066 as policy
from . import software_benchmark_sdk_bundle_v064 as runtime
from .repository_sources_v054 import normalize_policy, validate_path
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_docker_actor_v066 import (
    DockerStdioChannel, OwnedActorPair, StdioBridge, validate_actor_ready,
)
from .software_benchmark_host_usage_v066 import (
    HostUsageTransport, serve_model_channel, reconcile_host_usage, zero_request_recovery,
)
from .software_benchmark_native_artifact_v054 import PROTOCOL, native_tree_manifest, validate_native_tree
from .software_benchmark_native_rootfs_v054 import image_environment
from .software_benchmark_ref_budget_v064 import validate_condition
from .software_benchmark_archive_storage_v064 import compress_transport_archive, retain_baseline, open_verified_archive
from .software_benchmark_snapshot_recovery_v061 import export_utf8_patch
from .software_benchmark_public_context_v062 import prepare_public_context
from .storage import json_bytes

ROOT, BATCH = policy.ROOT, policy.BATCH_ROOT
VERSION = "v066-private-native-continuation-episode-r1"
PRIVATE_ROOTS = ["/opt/pws-runtime/" + name for name in ("site", "overlay", "upstream-tools", "project")]
GIB = 1024**3


class TaskCandidateExportFailure(RuntimeError):
    """A settled task produced a terminal artifact the patch exporter rejects."""


def controller_ref(value, folder):
    """Resolve an unchanged container JSON reference through its explicit mapping."""
    if not isinstance(value, dict) or set(value) != {'path', 'sha256', 'bytes'}:
        raise ValueError('Controller evidence requires an exact immutable file reference')
    path = PurePosixPath(value.get('path', ''))
    if (not path.is_absolute() or '..' in path.parts or len(path.parts) < 4
            or path.parts[:3] != ('/', 'pws', 'output')):
        raise ValueError('Controller evidence must remain under its original private output')
    root = Path(folder).resolve()
    target = (root / Path(*path.parts[3:])).resolve()
    if not target.is_relative_to(root):
        raise ValueError('Controller evidence relocation cannot follow a link outside its output')
    result = {**value, 'path': str(target)}
    checked(result)
    return result


def controller_identity_matches(child, row):
    return isinstance(child, dict) and all(child.get(key) == row[key]
        for key in ('slot_id', 'condition_id', 'arm', 'model_key'))


def validate_closed_usage(ledger, limits):
    """Known final usage must reconcile; an unspent final decision is not a call."""
    if (not isinstance(ledger, dict)
            or any(type(ledger.get(key)) is not int or ledger[key] < 0
                   for key in ('attempts', 'decisions', 'known_actual_tokens', 'complete_actual_tokens'))
            or ledger['attempts'] > limits['all_model_attempts']
            or ledger['decisions'] > limits['agent_decisions']
            or ledger['known_actual_tokens'] > limits['input_plus_output_tokens']
            or ledger['complete_actual_tokens'] != ledger['known_actual_tokens']
            or ledger.get('token_limit') != limits['input_plus_output_tokens']
            or ledger.get('all_model_attempt_limit') != limits['all_model_attempts']
            or ledger.get('agent_decision_limit') != limits['agent_decisions']
            or 'inflight' not in ledger or ledger['inflight'] is not None
            or type(ledger.get('uncertain_reserved_tokens')) is not int or ledger['uncertain_reserved_tokens'] != 0
            or not isinstance(ledger.get('calls'), list) or len(ledger['calls']) != ledger['attempts']):
        raise ValueError('A closed controller requires reconciled actual usage without unknown reservations')
    actual = 0
    for call in ledger['calls']:
        usage = call.get('usage', {})
        if (any(type(usage.get(key)) is not int or usage[key] < 0
                for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
                or usage['total_tokens'] != usage['prompt_tokens'] + usage['completion_tokens']):
            raise ValueError('Closed per-call usage is missing or internally inconsistent')
        actual += usage['total_tokens']
    if actual != ledger['known_actual_tokens']:
        raise ValueError('Closed aggregate tokens do not equal the retained actual per-call usage')
    return ledger


def classify_failure_scope(result, cleanup):
    """Permit a proven independent task failure; never classify by error text."""
    if (result.get('shared_integrity_fault') or cleanup.get('quiescent') is not True
            or cleanup.get('cleanup_errors') or cleanup.get('create_result_unknown') is not False):
        return 'global'
    # The coordinator still verifies the ledger/conservative reservation. Quiet
    # independent failures alone do not cancel unrelated tasks.
    return 'local'


def load(ref):
    return json.loads(checked(ref).read_bytes())


def capacity():
    memory = next(int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()
                  if line.startswith("MemAvailable:"))
    disk, load1 = shutil.disk_usage(ROOT).free, os.getloadavg()[0]
    memory_floor = (policy.CONSTRAINTS['memory_minimum_free_bytes']
                    + 2 * policy.CONSTRAINTS['generation_pair_reserved_memory_bytes']
                    + 2 * policy.CONSTRAINTS['grader_memory_bytes'])
    return {"admit": memory >= memory_floor and disk >= 256 * GIB and load1 < 140,
            "memory_available_bytes": memory, "disk_free_bytes": disk, "load_1m": load1,
            "memory_floor_with_two_pairs_and_two_graders": memory_floor,
            "disk_floor_with_two_actor_reservations": 256 * GIB}


def wait_capacity(stop_event=None):
    while True:
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("Capability probe cancelled before resource admission")
        policy.require_v066_allowed("v066.run")
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


def extract_controller_output(archive_path, destination, *, archive_storage=None, arm='REF'):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    seen, total, archived_only_bytes, archived_only_entries = set(), 0, 0, 0
    from contextlib import ExitStack
    with ExitStack() as stack:
        if archive_storage is not None:
            source = stack.enter_context(open_verified_archive(archive_storage))
            archive = stack.enter_context(tarfile.open(fileobj=source, mode='r|'))
        else:
            archive = stack.enter_context(tarfile.open(archive_path, 'r|*'))
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
            archive_only = arm == 'PROJECT' and relative.parts[0] in {'managed-world', 'managed-runtime'}
            if archive_only:
                if not member.isdir() and not member.isfile():
                    raise ValueError('Archived private history contains a link or special file')
                archived_only_bytes += member.size
                archived_only_entries += 1
                continue
            target = destination / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile() or member.size > 2 * GIB:
                raise ValueError("Controller output contains a link/special/oversized file")
            total += member.size
            if total > 8 * GIB:
                raise ValueError("Controller output exceeds its bounded evidence capacity")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                shutil.copyfileobj(archive.extractfile(member), output, length=1024**2)
    return {"container_prefix": "/pws/output", "host_prefix": str(destination.resolve()),
            "bytes": total, "entries": len(seen), "raw_json_references_rewritten": False,
            "archive_only_bytes": archived_only_bytes, "archive_only_entries": archived_only_entries,
            "archive_only_prefixes": ['managed-world', 'managed-runtime'] if arm == 'PROJECT' else [],
            "complete_archive_roundtrip_verified": archive_storage is not None,
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
    ref = (retain_baseline(bundle, folder / (name + ".json"), BATCH / "content/baselines")
           if name == "baseline-snapshot" else write_new(folder / (name + ".json"), bundle))
    storage = compress_transport_archive(archive_path, exported["archive"], allowed_root=BATCH)
    write_new(folder / (name + "-provenance.json"), {"archive": exported, "snapshot": ref,
        "archive_storage": storage, "model_or_grader_calls": 0, "source": "fresh_owned_actor_named_volume"})
    return bundle, ref


def _row_and_config(row, diagnostic):
    auth = policy.require_v066_allowed("v066.run", slot_id=row["slot_id"],
                                       instance_id=row["instance_id"])
    plan = load(auth["plan"])
    rows = [item for item in plan["rows"] if item["slot_index"] == row["slot_index"]]
    if rows != [row] or row["measurement_kind"] != "full_verified_comparison":
        raise ValueError("Only one exact new capability-probe row may enter")
    if diagnostic and (row["execution_arm"] not in {"REF", "PROJECT"} or row["model_key"] != "QWEN"
            or not any(spec.get("diagnostic") is True and spec.get("role") == "actor"
                       and spec.get("slot_id") == row["slot_id"]
                       for spec in plan["resources"].values())):
        raise ValueError("Deployment control must use its explicitly planned task and condition")
    config = load(row["configuration"])
    condition = load(config["configuration"])
    limits = validate_condition(condition)
    if (limits["input_plus_output_tokens"] != row["generation_token_upper_bound"]
            or any(config.get(key) != row[key] for key in
                   ("slot_id", "slot_index", "seed", "execution_arm", "source_slot_id", "replicate"))
            or condition["condition_id"] != row["condition_id"]
            or config["public_task"]["instance_id"] != row["instance_id"]
            or config["public_task"]["repo"] != row["repo"]):
        raise ValueError("New slot identity, seed, execution arm or cumulative budget changed")
    return config, condition, limits


def _run(row, resident, *, diagnostic=False, diagnostic_index=1, stop_event=None, api_transport_factory=None):
    config, condition, limits = _row_and_config(row, diagnostic)
    index = row["slot_index"]
    output = BATCH / ("diagnostic-" + str(diagnostic_index) if diagnostic else "episodes/" + str(index))
    if (output / "result.json").exists():
        return reference(output / "result.json")
    if output.exists():
        raise ValueError("An entered or partially prepared capability slot is not automatically replayed")
    admission = wait_capacity(stop_event)
    actor_key = f"diagnostic-{diagnostic_index}-actor" if diagnostic else f"actor-{index}"
    while True:
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("Cancelled before any task resource was claimed")
        try:
            actor_reservation = policy.claim_resource(actor_key)
            break
        except policy.ResourceBusy:
            if stop_event is None:
                time.sleep(5)
            else:
                stop_event.wait(5)
    result = {"version": VERSION, "status": "technical_unknown", "source_slot_id": row["source_slot_id"],
        "slot_id": row["slot_id"], "measurement_kind": "zero_model_diagnostic" if diagnostic else "full_verified_comparison",
        "execution_arm": row["execution_arm"], "replicate": row["replicate"],
        "arm": row["arm"], "model_key": row["model_key"], "group_id": row["group_id"],
        "configuration": row["configuration"], "condition_id": row["condition_id"],
        "instance_id": row["instance_id"], "seed": row["seed"],
        "automatic_replay": False, "capacity_admission": admission,
        "candidate_lock": None, "model_calls": 0, "model_dispatch_started": False}
    try:
        output.mkdir(parents=True, mode=0o700)
        write_new(output / "execution-intent.json", result)
    except BaseException:
        # The pair does not exist yet and no Docker operation was attempted.
        # Keep the consumed claim as history, releasing only its capacity lease.
        policy.release_resource(actor_reservation, quiescent=True)
        raise
    pair = client = bridge = model_channel = model_thread = model_transport = watchdog = None
    model_result, handles, writer_proof = {}, [], {}
    model_stop = threading.Event()
    lifecycle_expired = threading.Event()
    watchdog_errors = []
    controller = None
    terminal_ref = None
    try:
        bundle = runtime.prepare_bundle()
        mapping, public = public_environment(config)
        context = None
        if row["execution_arm"] in {"REF", "PROJECT"}:
            context = prepare_public_context(config["public_task"],
                registry_reference=config["public_test_registry"],
                baseline_mapping_reference=config["public_test_entry"]["baseline_mapping"],
                public_environment=public)
            write_new(output / "public-context-provenance.json", context)
        if diagnostic:
            if len(os.sched_getaffinity(0)) < 4:
                raise RuntimeError("The deployment control requires four visible CPUs")
        elif len(policy.host_cpu_pool()) < 176:
            raise RuntimeError("The fixed host CPU pool does not cover the reviewed runtime slices")
        import docker
        socket = Path(config["scorer_request_base"]["docker_socket"]).resolve()
        if not socket.is_socket():
            raise ValueError("The existing project Docker API is unavailable")
        client = docker.DockerClient(base_url="unix://" + str(socket), timeout=120)
        lifecycle_deadline = time.monotonic() + (180 if diagnostic else limits["hard_seconds"] + 600)
        pair = OwnedActorPair(client, slot_index=index, slot_id=row["slot_id"],
            instance_id=row["instance_id"], diagnostic=diagnostic, diagnostic_index=diagnostic_index,
            deadline=lifecycle_deadline, actor_reservation=actor_reservation)
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
        actor_config = {"version": "v064-private-docker-native-worker-r1" if row['arm'] == 'REF' else "v064-private-docker-managed-worker-r1", "private_roots": PRIVATE_ROOTS,
            "stdlib": "/opt/pws-runtime/sysroot/usr/lib/python3.12", "vision_enabled": False,
            "public_environment": public, "public_environment_sha256": hashlib.sha256(public_raw).hexdigest(),
            "instance_id": row["instance_id"], "actor_image_id": mapping["actor_image_id"],
            "baseline_head": mapping["actor_head"], "baseline_tree": mapping["actor_tree"], "official_task_admitted": True,
            "lifecycle_deadline": lifecycle_deadline, "maximum_lifecycle_seconds": 180 if diagnostic else 24000}
        public_entry = {'version': 'v064-repository-public-test-entry-r1',
                        'instance_id': row['instance_id'], 'argv': config['public_test_entry']['argv'],
                        'cwd': '/testbed', 'timeout_seconds': 1800, 'hidden_material_used': False}
        if row['arm'] == 'PROJECT':
            actor_config.update(public_test_entry=public_entry, file_policy=normalize_policy(), gitlinks=gitlinks)
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("Capability probe cancelled before actor creation")
        actor_tool = 'worker.py' if row['arm'] == 'REF' else 'managed-worker.py'
        actor_obj = pair.create_container("actor", runtime.python_argv([
            "/opt/pws-runtime/" + actor_tool, "--config", "/pws/control/actor-config.json"]),
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
        try:
            isolation_proof = validate_actor_ready(ready, public_environment_sha256=actor_config["public_environment_sha256"], arm=row['arm'])
        except Exception:
            result['shared_integrity_fault'] = 'actor_isolation_attestation_failed'
            raise
        write_new(output / "actor-isolation.json", isolation_proof)
        if ready.get("baseline") != {"head": mapping["actor_head"], "tree": mapping["actor_tree"], "working_tree_clean": True}:
            result['shared_integrity_fault'] = 'initial_baseline_identity_mismatch'
            raise ValueError("Actual live volume baseline differs from the original task")
        baseline, baseline_ref = snapshot(pair, output, name="baseline-snapshot", gitlinks=gitlinks)
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("Capability probe cancelled before controller creation")
        controller_tool = 'controller.py' if row['arm'] == 'REF' else 'project-controller.py'
        controller = pair.create_container("controller", runtime.python_argv([
            "/opt/pws-runtime/" + controller_tool, "--config", "/pws/control/controller-config.json"]),
            environment=runtime.runtime_environment())
        pair.upload_archive("controller", bundle["archive"])
        runtime_config = {**config, 'dataset_revision': condition['dataset_revision']}
        controller_inputs = runtime.controller_inputs(runtime_config, row, ready,
            {} if diagnostic else resident["identity_value"],
            "http://127.0.0.1:18210" if diagnostic else resident["endpoint"],
            diagnostic=diagnostic, public_context=context, public_environment=public,
            public_test_entry=public_entry, file_policy=baseline['file_policy'], gitlinks=gitlinks)
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
            from .software_benchmark_model_fifo_v064 import CancellableLoopbackHTTP
            if row['model_key'] == 'QWEN':
                model_transport = HostUsageTransport(
                    CancellableLoopbackHTTP(resident["endpoint"], resident["api_key_file"]),
                    output / 'host-model-usage', row['slot_id'], condition=condition,
                    service_identity=resident['identity_value'])
            else:
                if api_transport_factory is None:
                    raise ValueError('DeepSeek requires this slot-bound trusted-host API broker')
                model_transport = api_transport_factory(row, output)
            exec_id = client.api.exec_create(controller.id, runtime.python_argv([
                "/opt/pws-runtime/project/tools/bridge_ref_model_fifo_v064.py"]), stdin=True, stdout=True, stderr=True, tty=False)["Id"]
            stream = client.api.exec_start(exec_id, socket=True, tty=False)
            model_stderr = (output / "model-bridge.stderr").open("xb")
            handles.append(model_stderr)
            model_channel = DockerStdioChannel(stream, model_stderr, max_line=32 * 1024**2 + 1)
            model_ready = threading.Event()
            def model_loop():
                model_result.update(serve_model_channel(model_channel, endpoint=resident["endpoint"],
                    key_file=resident["api_key_file"], deadline=deadline, stop_event=model_stop,
                    slot_id=row["slot_id"], on_ready=model_ready.set, transport=model_transport))
            model_thread = threading.Thread(target=model_loop, daemon=True, name="v066-model-fifo")
            model_thread.start()
            if not model_ready.wait(20):
                result['shared_integrity_fault'] = 'trusted_model_bridge_initialization_failed'
                raise RuntimeError("Trusted model FIFO bridge did not initialize")
        start = {"started": started, "soft_at": started + (150 if diagnostic else limits["soft_seconds"]),
                 "hard_at": deadline, "guard_path": "/pws/output/guard.json"}
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("Capability probe cancelled before model entry")
        pair.upload_file("controller", "/pws/output/guard.json", json_bytes({"stop_requested": False, "request_deadline": None}))
        if not diagnostic:
            result.update(model_dispatch_started=True, model_calls=None)
            write_new(output / 'model-dispatch-intent.json', {'slot_id': row['slot_id'], 'start': start})
        pair.upload_file("controller", "/pws/control/start.json", json_bytes(start))
        write_new(output / "entered.json", {**start, "diagnostic": diagnostic,
            "resident_identity": None if diagnostic else resident["identity"], "runtime_bundle": reference(runtime.OUTPUT / "manifest.json")})
        while time.monotonic() < deadline:
            if stop_event is not None and stop_event.is_set():
                raise InterruptedError("Capability coordinator requested owned-episode cancellation")
            controller.reload()
            if not controller.attrs["State"]["Running"]:
                break
            if bridge.errors or (model_result and model_result.get("status") == "technical_unknown"):
                raise RuntimeError("Native/model transport failed; preserve original attempt without replay")
            time.sleep(.5)
        else:
            raise TimeoutError("Capability episode reached its original hard lifetime")
        controller_exit = controller.attrs["State"].get("ExitCode")
        actor_obj.reload()
        end_grace = time.monotonic() + 10
        while actor_obj.attrs["State"]["Running"] and time.monotonic() < end_grace:
            time.sleep(.1)
            actor_obj.reload()
        writer_proof = pair.stop_writers()
        writer_ref = write_new(output / "writer-quiescence.json", writer_proof)
        result["writer_quiescence"] = writer_ref
        transfer = pair.download_compressed_archive('controller', '/pws/output', output / 'controller-output.tar.zst')
        result['controller_transfer_before_validation'] = write_new(output / 'controller-transfer-before-validation.json', transfer)
        relocation = extract_controller_output(None, output / "controller-output", archive_storage=transfer['archive_storage'], arm=row['arm'])
        archive_storage = {**transfer.pop('archive_storage'), 'round_trip_verified': True}
        result['controller_output_transfer'] = write_new(output / "controller-output-transfer.json", {
            "transfer": transfer, "relocation": relocation, "archive_storage": archive_storage})
        child_path = output / "controller-output/controller-result.json"
        child = json.loads(child_path.read_bytes())
        if not controller_identity_matches(child, row):
            result['shared_integrity_fault'] = 'controller_identity_mismatch'
            raise ValueError('Controller result does not belong to its unique model/task/condition')
        result.update(controller_result=reference(child_path), controller_exit_code=controller_exit,
                      controller_status=child.get("status"), ledger=child.get("ledger"))
        for field in ('terminal_boundary', 'closure_reason', 'managed_boundary', 'failure_classification'):
            if field in child:
                result[field] = child[field]
        ledger_path = output / 'controller-output' / ('ref-ledger' if row['arm'] == 'REF' else 'model-ledger') / 'ledger.json'
        if ledger_path.exists():
            result['controller_ledger'] = reference(ledger_path)
            result['adapter_halted'] = json.loads(ledger_path.read_bytes()).get('halted')
        if (controller_exit != 0 or child.get("status") != "closed" or writer_proof.get("all_quiet") is not True
                or lifecycle_expired.is_set()):
            raise RuntimeError("The native controller did not produce a trusted closed episode")
        if not diagnostic:
            try:
                validate_closed_usage(child.get('ledger'), limits)
            except ValueError:
                result['shared_integrity_fault'] = 'closed_controller_usage_unproven'
                raise
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
            "slot_id": row["slot_id"], "selection": "single_final_worktree_after_generation"})
        terminal, terminal_ref = snapshot(pair, output, name="terminal-snapshot", gitlinks=gitlinks)
        result.update(terminal_capture_after_trusted_closure=True,
                      unscored_terminal_snapshot=terminal_ref)
        if row['arm'] == 'PROJECT' and not diagnostic:
            closure = dict(child['project_closure'])
            for name in ('terminal_snapshot', 'baseline_snapshot', 'delivery_snapshot', 'delivery_evidence', 'project_candidate_lock'):
                closure[name] = controller_ref(closure[name], output / 'controller-output')
            managed_terminal = load(closure['terminal_snapshot'])
            managed_baseline = load(closure['baseline_snapshot'])
            for name in ('files', 'entry_metadata'):
                if (managed_terminal[name] != terminal[name] or managed_baseline[name] != baseline[name]):
                    result['shared_integrity_fault'] = 'managed_terminal_source_mismatch'
                    raise ValueError('Managed locked sources differ from the actual isolated actor snapshots')
            result.update(delivery_evidence=closure['delivery_evidence'], delivery_snapshot=closure['delivery_snapshot'],
                          project_baseline_snapshot=baseline_ref, project_closure=closure)
        if diagnostic:
            if not child.get("diagnostic_passed") or terminal["tree"] != baseline["tree"]:
                raise ValueError("Deployment control changed public source or did not pass every check")
            checks = child.get('checks') or {'actual_SDK_initialized': child.get('actual_SDK_initialized'),
                                            'initialized_managed_tools': child.get('initialized_managed_tools'),
                                            'unchanged_terminal_tree': True}
            result.update(status="closed", diagnostic_passed=True, checks=checks, model_calls=0)
        else:
            slot = {key: row[key] for key in ("slot_index", "slot_id", "instance_id", "repo",
                "condition_id", "seed", "execution_arm", "replicate", "source_slot_id")}
            slot.update(arm=row['arm'], model_key=row['model_key'], input_plus_output_tokens=row["generation_token_upper_bound"])
            try:
                patch = export_utf8_patch(baseline, terminal, output / "candidate.patch", policy=terminal["file_policy"])
            except (ValueError, UnicodeError) as error:
                # Export is host-only and occurs after trusted controller/model
                # closure and a complete retained terminal tree. Content rejection
                # is local; IO, permissions and uncertain closure stay global.
                raise TaskCandidateExportFailure("Settled task terminal artifact cannot be exported") from error
            lock = write_new(output / "candidate-lock.json", {"version": "software-benchmark-native-closure-v054",
                "implementation": VERSION, "claim_id": pair.claims["actor"]["sha256"], "slot": slot,
                "source_slot_id": row["source_slot_id"], "measurement_kind": "full_verified_comparison",
                "endpoint": "terminal_code", "quiescence": writer_ref, "baseline": baseline_ref,
                "candidate": terminal_ref, "patch_receipt": patch, "tree_sha256": patch["candidate_tree_sha256"],
                "delivery": None, "lock_before_grading": True, "model_calls": 0, "grading_calls": 0})
            result.update(status="closed", candidate_lock=lock, model_calls=child["ledger"]["attempts"],
                          known_actual_tokens=child["ledger"]["known_actual_tokens"])
            result['delivery_candidate_lock'] = None
            if row['arm'] == 'PROJECT':
                from .software_benchmark_project_closure_v064 import validate_delivery_evidence
                delivery = load(result['delivery_snapshot'])
                evidence = load(result['delivery_evidence'])
                result['delivery_validation'] = validate_delivery_evidence(evidence, delivery, baseline)
                if delivery['submitted']:
                    bundle = {**terminal, 'files': delivery['candidate']['files'],
                              'entry_metadata': delivery['candidate']['entry_metadata']}
                    bundle['tree'] = native_tree_manifest(bundle['files'], bundle['entry_metadata'])
                    validate_native_tree(bundle['files'], bundle['entry_metadata'], bundle['file_policy'])
                    delivery_ref = write_new(output / 'delivery-native-snapshot.json', bundle)
                    delivery_patch = export_utf8_patch(baseline, bundle, output / 'delivery-candidate.patch', policy=bundle['file_policy'])
                    code_lock = load(lock)
                    result['delivery_candidate_lock'] = write_new(output / 'delivery-candidate-lock.json', {
                        **code_lock, 'endpoint': 'last_legal_delivery', 'candidate': delivery_ref,
                        'patch_receipt': delivery_patch, 'tree_sha256': delivery_patch['candidate_tree_sha256'],
                        'delivery': result['delivery_evidence'], 'model_calls': 0, 'grading_calls': 0})
                    result['same_code_and_delivery_tree'] = code_lock['tree_sha256'] == delivery_patch['candidate_tree_sha256']
    except Exception as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)},
                      traceback=traceback.format_exc())
        if isinstance(error, TaskCandidateExportFailure):
            result["failure_category"] = "task_candidate_export_rejected"
            result["export_error"] = {"type": type(error.__cause__).__name__, "message": str(error.__cause__)}
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
            preserve_controller = False
            if writer_proof.get("all_quiet") is not True:
                observed_writers = cleanup_step("final_writer_quiescence", pair.stop_writers)
                if observed_writers is not None:
                    writer_proof = observed_writers
                    result["final_writer_quiescence"] = write_new(output / "final-writer-quiescence.json", writer_proof)
            # On an abnormal path retain the private SDK evidence before removing its own container.
            if controller is not None and not (output / "controller-output-transfer.json").exists():
                try:
                    if writer_proof.get("all_quiet") is not True:
                        raise RuntimeError("Controller evidence cannot be archived with uncertain writers")
                    before = output / 'controller-transfer-before-validation.json'
                    if before.exists():
                        transfer = json.loads(before.read_bytes())
                    else:
                        transfer = pair.download_compressed_archive('controller', '/pws/output', output / 'controller-output-failure.tar.zst')
                        write_new(output / 'controller-failure-transfer-before-validation.json', transfer)
                    target = output / ('controller-output-failure' if (output / 'controller-output').exists() else 'controller-output')
                    relocation = extract_controller_output(None, target, archive_storage=transfer['archive_storage'], arm=row['arm'])
                    storage = {**transfer.pop('archive_storage'), 'round_trip_verified': True}
                    result['failure_controller_output_transfer'] = write_new(output / "controller-failure-output-relocation.json", {
                        'transfer': transfer, 'archive_storage': storage, 'relocation': relocation})
                    failed_child = target / 'controller-result.json'
                    if failed_child.exists():
                        child = json.loads(failed_child.read_bytes())
                        if controller_identity_matches(child, row):
                            result.update(controller_result=reference(failed_child), controller_status=child.get('status'),
                                          ledger=child.get('ledger'))
                            for field in ('terminal_boundary', 'closure_reason', 'managed_boundary', 'failure_classification'):
                                if field in child:
                                    result[field] = child[field]
                        else:
                            result.setdefault('shared_integrity_fault', 'controller_identity_mismatch')
                            result['rejected_failure_controller_result'] = reference(failed_child)
                except Exception as error:
                    preserve_controller = True
                    result["evidence_retention_error"] = {"type": type(error).__name__, "message": str(error)}
            if "actor" in pair.objects and terminal_ref is None:
                try:
                    interrupted_quiet = writer_proof
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
            observed_cleanup = cleanup_step("owned_pair_cleanup", lambda: pair.cleanup(
                preserve_worktree=preserve_worktree, preserve_controller=preserve_controller))
            if observed_cleanup is not None:
                cleanup = observed_cleanup
            else:
                cleanup.update(quiescent=False, create_result_unknown=True)
        elif actor_reservation is not None:
            cleanup_step('unused_actor_reservation', lambda: policy.release_resource(actor_reservation, quiescent=True))
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
        if row["model_key"] == "QWEN" and isinstance(model_transport, HostUsageTransport):
            try:
                if result.get("model_bridge_thread_finished") is not True:
                    raise RuntimeError("Host accounting cannot close while its model bridge is alive")
                host_ledger = model_transport.snapshot()
                result["host_usage_manifest"] = reference(model_transport.folder / "manifest.json")
                result["host_ledger_snapshot"] = write_new(output / "host-ledger-final.json", host_ledger)
                no_request = zero_request_recovery(result, bridge=model_result, writers=writer_proof,
                                                   cleanup=cleanup, host_ledger=host_ledger)
                reconcile_host_usage(result, host_ledger)
                if no_request is not None:
                    no_request.update(model_transport=result.get("model_transport"),
                        writer_quiescence=result.get("final_writer_quiescence") or result.get("writer_quiescence"),
                        cleanup=result["quiescence"], host_ledger=result["host_ledger_snapshot"],
                        original_dispatch_intent=(reference(output / "model-dispatch-intent.json")
                            if (output / "model-dispatch-intent.json").exists() else None))
                    result["zero_model_recovery"] = write_new(output / "zero-model-recovery.json", no_request)
                    result.update(model_calls=0, model_dispatch_started=False,
                        zero_model_generation_proven=True,
                        model_dispatch_intent_was_present=no_request["original_dispatch_intent"] is not None)
            except Exception as error:
                result["status"] = "technical_unknown"
                result.setdefault("shared_integrity_fault", "host_qwen_accounting_not_reconciled")
                result["host_accounting_error"] = {"type": type(error).__name__, "message": str(error)}
    if diagnostic:
        result["passed"] = result["status"] == "closed" and cleanup["quiescent"] is True
    result["failure_scope"] = classify_failure_scope(result, cleanup)
    result["batch_stop_required"] = result["failure_scope"] == "global"
    return write_new(output / "result.json", result)


def run_episode(row, resident, *, stop_event=None, api_transport_factory=None):
    return _run(row, resident, stop_event=stop_event, api_transport_factory=api_transport_factory)


def run_diagnostic(index=1, *, stop_event=None):
    auth = policy.require_v066_allowed("v066.run")
    plan = load(auth["plan"])
    if type(index) is not int or index not in (1, 2, 3, 4):
        raise ValueError("Only the explicitly planned BASE and FIX controls may run")
    spec = plan["resources"].get(f"diagnostic-{index}-actor", {})
    rows = [item for item in plan["rows"] if item["slot_id"] == spec.get("slot_id")]
    if (len(rows) != 1 or spec.get("diagnostic") is not True
            or spec.get("execution_arm") != rows[0]["execution_arm"]):
        raise ValueError("Diagnostic number lacks an exact BASE/FIX resource grant")
    row = rows[0]
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
