"""Owned Docker actors/controllers with no host mounts or namespace operations.

One new named volume holds each task's live /testbed. The actor sees it read-
write; its trusted SDK controller sees the same files read-only. Every Docker
creation consumes an exact durable v061 grant, and cleanup touches only objects
whose immutable identity and ownership labels match that grant.
"""
from __future__ import annotations

import hashlib
import errno
import io
import json
import os
from pathlib import Path, PurePosixPath
import select
import socket
import tarfile
import threading
import time

from . import software_benchmark_dispatch_v061 as policy
from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_tls_transport_v059 import DockerFrameDecoder
from .software_benchmark_network_v055 import validate_actor_ready as validate_original_actor_ready

VERSION = "v061-owned-private-docker-actor-pair-r1"
ROLES = {"actor": (4, 16 * 1024**3, 512), "controller": (2, 4 * 1024**3, 256)}
RUNTIME = "/opt/pws-runtime"
MAX_RPC_LINE = 32 * 1024**2
MAX_STDERR = 256 * 1024**2


def validate_actor_ready(ready, *, public_environment_sha256, host_namespaces=None):
    """Keep the original native checks and prove actual Docker namespaces differ."""
    proof = validate_original_actor_ready(ready)
    if (ready.get("implementation") != "v061-private-docker-native-worker-r1"
            or ready.get("public_environment_sha256") != public_environment_sha256):
        raise ValueError("Native Docker actor differs from its pinned worker/environment")
    host = host_namespaces or {name: os.stat("/proc/self/ns/" + name).st_ino for name in ("mnt", "pid", "net", "ipc")}
    actor = ready["isolation"].get("namespaces", {})
    if any(type(actor.get(name)) is not int or actor[name] <= 0 or actor[name] == host[name] for name in host):
        raise ValueError("Docker actor shares a host namespace")
    removed = ready["isolation"].get("private_packages", {})
    expected = {RUNTIME + "/" + name for name in ("site", "overlay", "upstream-tools", "project")}
    if set(removed) != expected or set(removed.values()) != {"removed_before_first_tool"}:
        raise ValueError("Actor still exposes private SDK dependency files")
    return {**proof, "version": VERSION, "model_route": "none_in_actor; independent_trusted_controller",
            "namespaces": {"host": host, "actor": actor, "all_distinct": True}}


def _load(ref):
    return json.loads(checked(ref).read_bytes())


def labels_for(claim_ref, claim):
    return {"proworksim.owner": VERSION, "proworksim.resource": claim["key"],
            "proworksim.claim": claim_ref["sha256"]}


def volume_options(claim_ref, claim):
    if claim["spec"]["role"] not in {"volume", "diagnostic_volume"}:
        raise ValueError("Only the reviewed new task volume may be created")
    return {"name": claim["docker_name"], "driver": "local", "driver_opts": {},
            "labels": labels_for(claim_ref, claim)}


def container_options(role, claim_ref, claim, volume, launch_argv, *, environment=None, cpuset=None):
    if role not in ROLES or claim["spec"]["role"].replace("diagnostic_", "") != role:
        raise ValueError("Container role differs from the exact claim")
    if (not isinstance(launch_argv, list) or not launch_argv
            or any(not isinstance(x, str) or "\0" in x for x in launch_argv)
            or launch_argv[0] not in {RUNTIME + "/sysroot/usr/lib64/ld-linux-x86-64.so.2", RUNTIME + "/bin/python"}):
        raise ValueError("Only the fixed private Python loader may start the container")
    if not isinstance(volume, str) or not volume.startswith("pws-v061-") or "/" in volume:
        raise ValueError("An explicitly owned Docker named volume is required")
    env = dict(environment or {})
    for key, value in env.items():
        if not isinstance(key, str) or not isinstance(value, str) or "\0" in key + value:
            raise ValueError("Container environment must be text")
        if key.lower() in {"http_proxy", "https_proxy", "all_proxy"} and value:
            raise ValueError("No proxy may enter the isolated runtime")
    env.update(CUDA_VISIBLE_DEVICES="", NVIDIA_VISIBLE_DEVICES="void",
               HTTP_PROXY="", HTTPS_PROXY="", ALL_PROXY="", http_proxy="", https_proxy="", all_proxy="")
    cpu, memory, pids = ROLES[role]
    # Use Mounts, not Binds: a named Docker volume is never a host source path.
    mount = {"Type": "volume", "Source": volume, "Target": "/testbed",
             "ReadOnly": role == "controller", "VolumeOptions": {"NoCopy": role == "controller"}}
    values = {"image": claim["spec"]["image_id"], "name": claim["docker_name"],
        "labels": labels_for(claim_ref, claim), "entrypoint": launch_argv,
        "command": [], "detach": True, "stdin_open": True, "tty": False,
        "user": "0:0", "network_mode": "none", "ipc_mode": "private",
        "cap_drop": ["ALL"], "cap_add": [], "privileged": False,
        "security_opt": ["no-new-privileges:true"], "mem_limit": memory,
        "memswap_limit": memory, "nano_cpus": cpu * 10**9, "pids_limit": pids,
        "mounts": [mount], "environment": env, "working_dir": "/testbed",
        "auto_remove": False, "init": False}
    if cpuset is not None:
        if not isinstance(cpuset, str) or not cpuset or any(c not in "0123456789,-" for c in cpuset):
            raise ValueError("CPU affinity must be an explicit numeric Docker CPU set")
        values["cpuset_cpus"] = cpuset
    return values


def validate_volume(volume, claim_ref, claim):
    volume.reload()
    attrs = volume.attrs
    if (attrs.get("Name") != claim["docker_name"] or attrs.get("Driver") != "local"
            or attrs.get("Options") not in (None, {})
            or any((attrs.get("Labels") or {}).get(k) != v for k, v in labels_for(claim_ref, claim).items())):
        raise ValueError("Docker volume identity, driver options or ownership differs")
    return attrs


def validate_container_identity(container, claim_ref, claim):
    container.reload()
    attrs, expected = container.attrs, labels_for(claim_ref, claim)
    if (attrs.get("Image") != claim["spec"]["image_id"]
            or attrs.get("Name", "").removeprefix("/") != claim["docker_name"]
            or any((attrs.get("Config", {}).get("Labels") or {}).get(k) != v for k, v in expected.items())):
        raise ValueError("Docker object is not the exact owned resource")
    return attrs


def validate_container(container, role, claim_ref, claim, volume):
    attrs = validate_container_identity(container, claim_ref, claim)
    host, config = attrs.get("HostConfig", {}), attrs.get("Config", {})
    cpu, memory, pids = ROLES[role]
    if (attrs.get("Image") != claim["spec"]["image_id"]
            or attrs.get("Name", "").removeprefix("/") != claim["docker_name"]
            or host.get("NetworkMode") != "none" or host.get("Privileged") is not False
            or host.get("Binds") or host.get("Devices") or host.get("DeviceRequests")
            or host.get("PortBindings") or host.get("VolumesFrom")
            or host.get("PidMode") not in (None, "") or host.get("IpcMode") != "private"
            or host.get("CapDrop") != ["ALL"] or host.get("CapAdd") not in (None, [])
            or host.get("Memory") != memory or host.get("MemorySwap") != memory
            or host.get("NanoCpus") != cpu * 10**9 or host.get("PidsLimit") != pids
            or "no-new-privileges:true" not in host.get("SecurityOpt", [])
            or config.get("User") not in ("0", "0:0") or config.get("Tty") is not False):
        raise ValueError("Actual Docker container exceeds its reviewed resource or isolation scope")
    mounts = attrs.get("Mounts", [])
    if (len(mounts) != 1 or mounts[0].get("Type") != "volume"
            or mounts[0].get("Name") != volume or mounts[0].get("Destination") != "/testbed"
            or mounts[0].get("RW") is not (role == "actor")):
        raise ValueError("Only this actor/controller pair's named /testbed volume is allowed")
    return attrs


def file_archive(name, data, *, mode=0o600):
    if not isinstance(name, str) or not name or "/" in name or name in {".", ".."}:
        raise ValueError("Archive file name must be a single component")
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        entry = tarfile.TarInfo(name)
        entry.size, entry.mode, entry.uid, entry.gid = len(data), mode, 0, 0
        archive.addfile(entry, io.BytesIO(data))
    return output.getvalue()


def validate_runtime_archive(path):
    """A copied SDK tar may populate only its private runtime and control dirs."""
    count = 0
    with tarfile.open(path, "r:*") as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            parts = name.parts
            allowed = (parts in (("opt",), ("pws",))
                       or parts[:2] in (("opt", "pws-runtime"), ("pws", "control"), ("pws", "output")))
            if (name.is_absolute() or ".." in parts or not allowed
                    or not (member.isfile() or member.isdir()) or member.mode & ~0o777
                    or member.uid != 0 or member.gid != 0):
                raise ValueError("SDK archive contains material outside the private copied runtime")
            if parts in (("opt",), ("pws",)) and not member.isdir():
                raise ValueError("SDK archive ancestors must be directories")
            count += 1
    if count == 0:
        raise ValueError("Empty copied runtime archive")
    return count


class DockerStdioChannel:
    """Turn Docker's multiplexed stdout/stderr into bounded native JSON lines."""

    def __init__(self, stream, stderr_file, *, max_line=MAX_RPC_LINE, clock=time.monotonic):
        self.stream, self.socket = stream, getattr(stream, "_sock", stream)
        self.stderr = stderr_file
        self.decoder, self.buffer = DockerFrameDecoder(), bytearray()
        self.max_line, self.clock = max_line, clock
        self.stderr_bytes, self.eof = 0, False
        self.stdin_close_notes = []
        self.writer_lock = threading.Lock()

    def readline(self, deadline):
        while True:
            split = self.buffer.find(b"\n")
            if split >= 0:
                line = bytes(self.buffer[:split + 1])
                del self.buffer[:split + 1]
                return line
            if self.eof:
                if self.buffer:
                    raise RuntimeError("Native RPC stdout ended with a partial JSON line")
                return b""
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise TimeoutError("Docker native RPC deadline exceeded")
            if not select.select([self.socket], [], [], min(1.0, remaining))[0]:
                continue
            chunk = self.socket.recv(65536)
            if not chunk:
                self.decoder.finish()
                self.eof = True
                continue
            for stream, data in self.decoder.feed(chunk):
                if stream == 1:
                    self.buffer.extend(data)
                    if len(self.buffer) > self.max_line:
                        raise RuntimeError("Native RPC stdout exceeds bounded transport capacity")
                elif stream == 2:
                    self.stderr_bytes += len(data)
                    if self.stderr_bytes > MAX_STDERR:
                        raise RuntimeError("Owned runtime stderr exceeds its bounded log capacity")
                    self.stderr.write(data)
                    self.stderr.flush()
                else:
                    raise RuntimeError("Docker reported an unexpected exec stream")

    def write(self, data):
        if not isinstance(data, bytes) or len(data) > self.max_line:
            raise ValueError("Native RPC writes must be bounded byte strings")
        with self.writer_lock:
            self.socket.sendall(data)

    def close_stdin(self):
        with self.writer_lock:
            try:
                self.socket.shutdown(socket.SHUT_WR)
            except OSError as error:
                if error.errno in (errno.ENOTCONN, errno.EPIPE, errno.ECONNRESET):
                    self.stdin_close_notes.append({"errno": error.errno, "reason": "peer_already_closed_at_input_EOF"})
                elif not self.eof:
                    raise

    def close(self):
        self.stream.close()
        if self.socket is not self.stream:
            self.socket.close()


class StdioBridge:
    """Duplex host relay; it does not parse or execute an Agent command."""

    def __init__(self, actor, controller, *, deadline):
        self.actor, self.controller, self.deadline = actor, controller, deadline
        self.errors, self.counts, self.threads = [], {"actor_to_controller": 0, "controller_to_actor": 0}, []

    def _pump(self, source, destination, direction):
        try:
            while line := source.readline(self.deadline):
                # Only validate framing; preserve exact official request/response bytes.
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("Native RPC message must be an object")
                destination.write(line)
                self.counts[direction] += 1
            destination.close_stdin()
        except Exception as error:
            self.errors.append({"direction": direction, "type": type(error).__name__, "message": str(error)})

    def start(self):
        if self.threads:
            raise ValueError("A bridge cannot be restarted")
        for source, target, direction in ((self.actor, self.controller, "actor_to_controller"),
                                          (self.controller, self.actor, "controller_to_actor")):
            thread = threading.Thread(target=self._pump, args=(source, target, direction), daemon=True,
                                      name="v061-native-stdio-" + direction)
            self.threads.append(thread)
            thread.start()
        return self

    def join(self, timeout):
        end = time.monotonic() + timeout
        for thread in self.threads:
            thread.join(max(0, end - time.monotonic()))
        return {"threads_finished": all(not t.is_alive() for t in self.threads),
                "errors": list(self.errors), "frames": dict(self.counts),
                "actor_input_EOF_notes": list(getattr(self.actor, "stdin_close_notes", [])),
                "controller_input_EOF_notes": list(getattr(self.controller, "stdin_close_notes", []))}

    def close(self):
        for channel in (self.actor, self.controller):
            channel.close()
        return self.join(5)


class OwnedActorPair:
    """Creation, attestation and cleanup of exactly one reviewed task pair."""

    def __init__(self, client, *, slot_index, original_slot_id, instance_id, diagnostic=False, diagnostic_index=1,
                 deadline=None):
        self.client, self.slot_index = client, slot_index
        self.original_slot_id, self.instance_id = original_slot_id, instance_id
        self.diagnostic = diagnostic
        if type(diagnostic_index) is not int or not 1 <= diagnostic_index <= 3:
            raise ValueError("Only the three predeclared deployment controls are allowed")
        self.diagnostic_index = diagnostic_index
        self.deadline = deadline
        self.claims, self.claim_bodies, self.objects = {}, {}, {}
        self.unknown_create, self.channels = set(), []

    def _key(self, role):
        return f"diagnostic-{self.diagnostic_index}-{role}" if self.diagnostic else role + "-" + str(self.slot_index)

    def _authorize(self, operation):
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise TimeoutError("Owned actor/controller pair lifecycle expired before another operation")
        return policy.require_v061_allowed(operation, original_slot_id=self.original_slot_id,
                                           instance_id=self.instance_id)

    def _claim(self, role):
        if role in self.claims:
            raise ValueError("This actor-pair resource attempt is already consumed")
        ref = policy.claim_resource(self._key(role))
        self.claims[role], self.claim_bodies[role] = ref, _load(ref)
        return ref, self.claim_bodies[role]

    def create_volume(self):
        self._authorize("v061.volume.create")
        ref, claim = self._claim("volume")
        self.unknown_create.add("volume")
        try:
            volume = self.client.volumes.create(**volume_options(ref, claim))
        except Exception:
            try:
                volume = self.client.volumes.get(claim["docker_name"])
                validate_volume(volume, ref, claim)
                self.objects["volume"] = volume
                self.unknown_create.discard("volume")
            except Exception:
                pass
            raise
        self.objects["volume"] = volume
        validate_volume(volume, ref, claim)
        self.unknown_create.discard("volume")
        return volume

    def create_container(self, role, launch_argv, *, environment=None, cpuset=None):
        if role not in ROLES or "volume" not in self.objects:
            raise ValueError("The actor pair requires its owned volume before either container")
        self._authorize("v061." + role + ".create")
        if role == "controller" and "actor" not in self.objects:
            raise ValueError("Actor creation populates the new task volume before controller attachment")
        ref, claim = self._claim(role)
        volume = self.claim_bodies["volume"]["docker_name"]
        if cpuset is None:
            available = sorted(os.sched_getaffinity(0))
            if self.diagnostic:
                if len(available) < 4:
                    raise ValueError("The deployment control requires four visible CPUs")
                cpuset = ",".join(map(str, available[:4]))
            else:
                actor_claim = claim if role == "actor" else self.claim_bodies["actor"]
                lane = int(Path(actor_claim["lease"]).stem.rsplit("-", 1)[1])
                if len(available) < 12 or lane not in (0, 1):
                    raise ValueError("Two private actor/controller pairs require twelve visible CPUs")
                selected = available[lane * 6:lane * 6 + 6]
                cpuset = ",".join(map(str, selected[:4] if role == "actor" else selected[4:]))
        options = container_options(role, ref, claim, volume, launch_argv, environment=environment, cpuset=cpuset)
        self.unknown_create.add(role)
        try:
            container = self.client.containers.create(**options)
        except Exception:
            try:
                container = self.client.containers.get(claim["docker_name"])
                validate_container(container, role, ref, claim, volume)
                self.objects[role] = container
                self.unknown_create.discard(role)
            except Exception:
                pass
            raise
        self.objects[role] = container
        validate_container(container, role, ref, claim, volume)
        self.unknown_create.discard(role)
        return container

    def upload_archive(self, role, source_ref, *, destination="/"):
        if role not in ROLES or role not in self.objects or destination != "/":
            raise ValueError("Only copied trusted runtime/control files may be uploaded")
        source = checked(source_ref)
        validate_runtime_archive(source)
        with source.open("rb") as stream:
            if self.objects[role].put_archive(destination, stream) is not True:
                raise RuntimeError("Runtime archive transfer was not acknowledged")

    def upload_file(self, role, destination, data, *, mode=0o600):
        path = Path(destination)
        if role not in ROLES or str(path.parent) not in {"/pws/control", "/pws/output"}:
            raise ValueError("Only bounded control/output file paths may be uploaded")
        if self.objects[role].put_archive(str(path.parent), file_archive(path.name, data, mode=mode)) is not True:
            raise RuntimeError("Private control file transfer was not acknowledged")

    def attach(self, role, stderr_file):
        if role not in ROLES or role not in self.objects:
            raise ValueError("Only this pair's created actor/controller may be attached")
        stream = self.client.api.attach_socket(self.objects[role].id,
            params={"stdin": 1, "stdout": 1, "stderr": 1, "stream": 1})
        channel = DockerStdioChannel(stream, stderr_file)
        self.channels.append(channel)
        return channel

    def start(self, role):
        self._authorize("v061." + role + ".start")
        container = self.objects[role]
        validate_container(container, role, self.claims[role], self.claim_bodies[role],
                           self.claim_bodies["volume"]["docker_name"])
        container.start()
        return validate_container(container, role, self.claims[role], self.claim_bodies[role],
                                  self.claim_bodies["volume"]["docker_name"])

    def download_archive(self, role, path, destination, *, maximum_bytes=8 * 1024**3):
        if role not in ROLES or path not in {"/pws/output", "/testbed"}:
            raise ValueError("Only final output or the owned public worktree may be exported")
        destination = Path(destination)
        digest, count = hashlib.sha256(), 0
        chunks, stat = self.objects[role].get_archive(path)
        with destination.open("xb") as output:
            for chunk in chunks:
                count += len(chunk)
                if count > maximum_bytes:
                    raise RuntimeError("Owned output archive exceeds its reviewed export bound")
                output.write(chunk)
                digest.update(chunk)
        return {"archive": reference(destination), "docker_path_stat": stat,
                "container_id": self.objects[role].id, "role": role, "container_claim": self.claims[role],
                "owned_volume_claim": self.claims["volume"], "container_path": path,
                "stream_sha256": digest.hexdigest(), "bytes": count}

    def stop_writers(self):
        evidence = []
        for role in ("controller", "actor"):
            if role not in self.objects:
                continue
            container = self.objects[role]
            validate_container_identity(container, self.claims[role], self.claim_bodies[role])
            if container.attrs.get("State", {}).get("Running"):
                container.stop(timeout=10)
            container.reload()
            state = container.attrs.get("State", {})
            if state.get("Running") is not False or state.get("Pid") != 0:
                raise RuntimeError("Owned writer namespace has not fully stopped")
            evidence.append({"role": role, "container_id": container.id, "state": state,
                             "claim": self.claims[role]})
        return {"all_quiet": not self.unknown_create, "errors": [], "writers": evidence,
                "create_result_unknown_roles": sorted(self.unknown_create),
                "proof_kind": "private Docker PID1 exit/stop; actor and controller namespace writers stopped"}

    def cleanup(self, *, preserve_worktree=False):
        errors, removed, retained = [], [], []
        for channel in self.channels:
            try:
                channel.close()
            except Exception as error:
                errors.append({"channel": type(error).__name__, "message": str(error)})
        for role in ("controller", "actor"):
            if role not in self.objects:
                continue
            container = self.objects[role]
            try:
                validate_container_identity(container, self.claims[role], self.claim_bodies[role])
                if container.attrs.get("State", {}).get("Running"):
                    container.stop(timeout=10)
                container.reload()
                state = container.attrs.get("State", {})
                if state.get("Running") or state.get("Pid") != 0:
                    raise RuntimeError("Owned container remains running")
                if preserve_worktree and role == "actor":
                    retained.append({"role": role, "container_id": container.id,
                        "name": self.claim_bodies[role]["docker_name"], "claim": self.claims[role],
                        "running": False, "pid": 0,
                        "reason": "Interrupted worktree archive incomplete; retain exact stopped source"})
                else:
                    container.remove(force=False)
                    removed.append(role)
                self.unknown_create.discard(role)
            except Exception as error:
                if type(error).__name__ == "NotFound":
                    self.unknown_create.discard(role)
                    removed.append(role)
                else:
                    errors.append({"role": role, "type": type(error).__name__, "message": str(error)})
        settled_roles = set(removed) | {row["role"] for row in retained}
        if ("volume" in self.objects and not self.unknown_create.intersection(ROLES)
                and all(role not in self.objects or role in settled_roles for role in ROLES)):
            try:
                volume = self.objects["volume"]
                validate_volume(volume, self.claims["volume"], self.claim_bodies["volume"])
                if preserve_worktree and "actor" in settled_roles and "actor" not in removed:
                    retained.append({"role": "volume", "name": self.claim_bodies["volume"]["docker_name"],
                        "claim": self.claims["volume"], "reason": "Preserve stopped interrupted-worktree evidence"})
                else:
                    volume.remove(force=False)
                    removed.append("volume")
                self.unknown_create.discard("volume")
            except Exception as error:
                if type(error).__name__ == "NotFound":
                    self.unknown_create.discard("volume")
                    removed.append("volume")
                else:
                    errors.append({"role": "volume", "type": type(error).__name__, "message": str(error)})
        if not errors and not self.unknown_create:
            for role in set(removed) | {row["role"] for row in retained}:
                try:
                    policy.release_resource(self.claims[role], quiescent=True)
                except Exception as error:
                    errors.append({"role": role, "lease_release": type(error).__name__, "message": str(error)})
        return {"version": VERSION, "quiescent": not errors and not self.unknown_create,
            "removed_roles": removed, "cleanup_errors": errors,
            "retained_objects": retained, "all_owned_objects_removed": not retained and not errors and not self.unknown_create,
            "create_result_unknown": bool(self.unknown_create),
            "create_result_unknown_roles": sorted(self.unknown_create),
            "claims": self.claims, "unrelated_objects_touched": False}
