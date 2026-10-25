"""CPU-only native actor transport and exact Docker-scope controls."""
from collections import deque
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import types

import pytest

from proworksim import software_benchmark_docker_actor_v061 as actor

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("docker_native_worker", ROOT / "tools/run_native_worker_docker_v061.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def claim(role):
    return {"sha256": "a" * 64}, {"key": role + "-2", "docker_name": "pws-v061-" + role,
        "spec": {"role": role, "image_id": "sha256:" + "b" * 64}}


@pytest.mark.parametrize("role,read_only,cpu,ram,pids", [
    ("actor", False, 4, 16, 512), ("controller", True, 2, 4, 256)])
def test_role_options_use_only_owned_named_live_worktree(role, read_only, cpu, ram, pids):
    ref, body = claim(role)
    options = actor.container_options(role, ref, body, "pws-v061-volume",
        [actor.RUNTIME + "/sysroot/usr/lib64/ld-linux-x86-64.so.2", "python"])
    assert options["cap_drop"] == ["ALL"] and options["cap_add"] == []
    assert options["network_mode"] == "none" and options["privileged"] is False
    assert options["nano_cpus"] == cpu * 10**9 and options["mem_limit"] == ram * 1024**3
    assert options["pids_limit"] == pids and options["memswap_limit"] == options["mem_limit"]
    assert options["mounts"] == [{"Type": "volume", "Source": "pws-v061-volume", "Target": "/testbed",
        "ReadOnly": read_only, "VolumeOptions": {"NoCopy": read_only}}]
    assert "volumes" not in options and "ports" not in options and "devices" not in options
    assert options["init"] is False and options["tty"] is False


def test_host_path_mount_and_external_proxy_are_refused():
    ref, body = claim("actor")
    argv = [actor.RUNTIME + "/sysroot/usr/lib64/ld-linux-x86-64.so.2"]
    with pytest.raises(ValueError, match="named volume"):
        actor.container_options("actor", ref, body, "/data0/shared", argv)
    with pytest.raises(ValueError, match="No proxy"):
        actor.container_options("actor", ref, body, "pws-v061-volume", argv, environment={"HTTPS_PROXY": "x"})
    with pytest.raises(ValueError, match="loader"):
        actor.container_options("actor", ref, body, "pws-v061-volume", ["/bin/bash"])


def test_control_tar_never_inherits_host_uid_or_paths():
    with tarfile.open(fileobj=io.BytesIO(actor.file_archive("config.json", b'{"safe":true}'))) as tar:
        item, = tar.getmembers()
        assert (item.name, item.uid, item.gid, item.mode) == ("config.json", 0, 0, 0o600)
        assert tar.extractfile(item).read() == b'{"safe":true}'
    with pytest.raises(ValueError):
        actor.file_archive("../escape", b"")


@pytest.mark.parametrize("bad_name,bad_type", [("etc/passwd", tarfile.REGTYPE),
    ("opt/pws-runtime/link", tarfile.SYMTYPE), ("opt/pws-runtime/../../escape", tarfile.REGTYPE)])
def test_runtime_archive_cannot_write_other_paths_or_links(tmp_path, bad_name, bad_type):
    archive = tmp_path / "runtime.tar"
    with tarfile.open(archive, "w") as tar:
        item = tarfile.TarInfo(bad_name)
        item.type = bad_type
        tar.addfile(item)
    with pytest.raises(ValueError, match="outside the private"):
        actor.validate_runtime_archive(archive)


def test_actual_container_cannot_inherit_an_extra_mount_or_host_pid_mode():
    ref, body = claim("actor")
    attrs = {"Image": body["spec"]["image_id"], "Name": "/" + body["docker_name"],
        "Config": {"Labels": actor.labels_for(ref, body), "User": "0:0", "Tty": False},
        "HostConfig": {"NetworkMode": "none", "Privileged": False, "IpcMode": "private",
            "CapDrop": ["ALL"], "CapAdd": [], "Memory": 16 * 1024**3, "MemorySwap": 16 * 1024**3,
            "NanoCpus": 4 * 10**9, "PidsLimit": 512, "SecurityOpt": ["no-new-privileges:true"]},
        "Mounts": [{"Type": "volume", "Name": "pws-v061-volume", "Destination": "/testbed", "RW": True}]}
    container = types.SimpleNamespace(attrs=attrs, reload=lambda: None)
    assert actor.validate_container(container, "actor", ref, body, "pws-v061-volume") is attrs
    attrs["HostConfig"]["PidMode"] = "host"
    with pytest.raises(ValueError, match="isolation"):
        actor.validate_container(container, "actor", ref, body, "pws-v061-volume")
    attrs["HostConfig"]["PidMode"] = ""
    attrs["Mounts"].append({"Type": "bind", "Source": "/host", "Destination": "/host"})
    with pytest.raises(ValueError, match="named /testbed"):
        actor.validate_container(container, "actor", ref, body, "pws-v061-volume")


def test_private_runtime_cleanup_is_exact_and_rejects_symlinks(tmp_path):
    runtime = tmp_path / "runtime"
    roots = tuple(runtime / name for name in ("site", "overlay", "upstream-tools", "project"))
    for path in roots:
        path.mkdir(parents=True)
        (path / "module.py").write_text("original copied package")
    public = tmp_path / "testbed"
    public.mkdir()
    (public / "kept.py").write_text("baseline")
    with pytest.raises(ValueError, match="Only the private"):
        worker.remove_private_packages(runtime=runtime, private_roots=(public,))
    assert (public / "kept.py").read_text() == "baseline"
    removed = worker.remove_private_packages(runtime=runtime, private_roots=roots)
    assert all(not p.exists() for p in roots) and len(removed) == 4
    for path in roots:
        path.mkdir()
    roots[0].rmdir()
    roots[0].symlink_to(public, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        worker.remove_private_packages(runtime=runtime, private_roots=roots)
    assert (public / "kept.py").exists()


def frame(data, channel=1):
    return bytes([channel, 0, 0, 0]) + len(data).to_bytes(4, "big") + data


class FakeSocket:
    def __init__(self, chunks):
        self.chunks, self.sent, self.closed, self.shutdowns = deque(chunks), [], False, []

    def recv(self, size):
        return self.chunks.popleft()

    def sendall(self, data):
        self.sent.append(data)

    def shutdown(self, how):
        self.shutdowns.append(how)

    def close(self):
        self.closed = True


def test_stdout_lines_survive_docker_fragmentation_without_stderr_mix(monkeypatch):
    wire = frame(b'diagnostic\n', 2) + frame(b'{"id":1,') + frame(b'"value":"\xe6\xb5\x8b\xe8\xaf\x95"}\n')
    raw = FakeSocket([wire[:3], wire[3:17], wire[17:], b""])
    monkeypatch.setattr(actor.select, "select", lambda read, *a: (read, [], []))
    stderr = io.BytesIO()
    channel = actor.DockerStdioChannel(raw, stderr, clock=lambda: 0)
    assert json.loads(channel.readline(10)) == {"id": 1, "value": "测试"}
    assert channel.readline(10) == b"" and stderr.getvalue() == b"diagnostic\n"
    channel.write(b'{"op":"close"}\n')
    channel.close_stdin()
    channel.close()
    assert raw.sent == [b'{"op":"close"}\n'] and raw.closed


def test_partial_line_or_unbounded_stdout_cannot_become_valid_rpc(monkeypatch):
    monkeypatch.setattr(actor.select, "select", lambda read, *a: (read, [], []))
    for chunks, message in (([frame(b'{"id":'), b""], "partial JSON"),
                             ([frame(b"123456")], "bounded transport")):
        channel = actor.DockerStdioChannel(FakeSocket(chunks), io.BytesIO(), max_line=5 if "bounded" in message else 100, clock=lambda: 0)
        with pytest.raises(RuntimeError, match=message):
            channel.readline(10)


def test_bridge_forwards_only_complete_json_objects_and_preserves_close():
    class Channel:
        def __init__(self, data):
            self.data, self.sent, self.closed = deque(data), [], False
        def readline(self, deadline):
            return self.data.popleft() if self.data else b""
        def write(self, data):
            self.sent.append(data)
        def close_stdin(self):
            self.closed = True
        def close(self):
            pass
    left = Channel([b'{"id":1,"type":"observation"}\n'])
    right = Channel([b'{"id":1,"tool":"terminal","action":{}}\n'])
    bridge = actor.StdioBridge(left, right, deadline=100).start()
    result = bridge.join(2)
    assert result["threads_finished"] and result["errors"] == []
    assert json.loads(right.sent[0])["type"] == "observation"
    assert json.loads(left.sent[0])["tool"] == "terminal"
    assert left.closed and right.closed


def test_actual_namespace_identity_is_checked_in_addition_to_boolean(monkeypatch):
    monkeypatch.setattr(actor, "validate_original_actor_ready", lambda ready: {})
    names = dict(mnt=101, pid=102, net=103, ipc=104)
    ready = {"implementation": worker.IMPLEMENTATION, "public_environment_sha256": "original",
             "isolation": {"namespaces": dict(mnt=201, pid=202, net=203, ipc=204),
                 "private_packages": {str(p): "removed_before_first_tool" for p in worker.PRIVATE_ROOTS}}}
    assert actor.validate_actor_ready(ready, public_environment_sha256="original", host_namespaces=names)["namespaces"]["all_distinct"]
    ready["isolation"]["namespaces"]["mnt"] = names["mnt"]
    with pytest.raises(ValueError, match="shares a host"):
        actor.validate_actor_ready(ready, public_environment_sha256="original", host_namespaces=names)


def test_unknown_created_object_retains_capacity_without_touching_other_objects():
    pair = actor.OwnedActorPair(types.SimpleNamespace(), slot_index=2, original_slot_id="slot", instance_id="task")
    pair.unknown_create.add("actor")
    result = pair.cleanup()
    assert result["quiescent"] is False and result["create_result_unknown_roles"] == ["actor"]
    assert result["removed_roles"] == []


def test_actor_internal_deadline_survives_loss_of_host_supervisor(monkeypatch):
    calls = []
    monkeypatch.setattr(worker.time, "monotonic", lambda: 100)
    monkeypatch.setattr(worker.signal, "signal", lambda signum, handler: calls.append(("handler", signum, handler)))
    monkeypatch.setattr(worker.signal, "setitimer", lambda which, duration: calls.append(("timer", which, duration)))
    worker.install_lifecycle_deadline({"maximum_lifecycle_seconds": 180, "lifecycle_deadline": 250})
    assert calls[1] == ("timer", worker.signal.ITIMER_REAL, 150)
    for config in ({"maximum_lifecycle_seconds": 180, "lifecycle_deadline": 100},
                   {"maximum_lifecycle_seconds": 180, "lifecycle_deadline": 281},
                   {"maximum_lifecycle_seconds": 99999, "lifecycle_deadline": 250}):
        with pytest.raises(ValueError):
            worker.install_lifecycle_deadline(config)


def test_stopped_evidence_retention_does_not_claim_volume_deleted(monkeypatch):
    pair = actor.OwnedActorPair(types.SimpleNamespace(), slot_index=2, original_slot_id="slot", instance_id="task")
    removed, released = [], []
    for role in ("actor", "controller", "volume"):
        ref, body = claim(role)
        pair.claims[role], pair.claim_bodies[role] = {**ref, "role": role}, body
        attrs = {"State": {"Running": False, "Pid": 0}}
        pair.objects[role] = types.SimpleNamespace(id=role, attrs=attrs, reload=lambda: None,
            remove=lambda force, r=role: removed.append(r))
    monkeypatch.setattr(actor, "validate_container_identity", lambda *a: None)
    monkeypatch.setattr(actor, "validate_volume", lambda *a: None)
    monkeypatch.setattr(actor.policy, "release_resource", lambda ref, quiescent: released.append(ref["role"]))
    proof = pair.cleanup(preserve_worktree=True)
    assert proof["quiescent"] is True and proof["cleanup_errors"] == []
    assert proof["all_owned_objects_removed"] is False
    assert removed == ["controller"] and set(released) == {"actor", "controller", "volume"}
    assert {row["role"] for row in proof["retained_objects"]} == {"actor", "volume"}


def test_any_unknown_creation_prevents_pair_capacity_release(monkeypatch):
    pair = actor.OwnedActorPair(types.SimpleNamespace(), slot_index=2, original_slot_id="slot", instance_id="task")
    ref, body = claim("controller")
    pair.claims["controller"], pair.claim_bodies["controller"] = ref, body
    pair.objects["controller"] = types.SimpleNamespace(id="owned", attrs={"State": {"Running": False, "Pid": 0}},
        reload=lambda: None, remove=lambda force: None)
    pair.unknown_create.add("actor")
    monkeypatch.setattr(actor, "validate_container_identity", lambda *a: None)
    monkeypatch.setattr(actor.policy, "release_resource", lambda *a, **k: pytest.fail("Pair creation remains uncertain"))
    proof = pair.cleanup()
    assert proof["quiescent"] is False and proof["removed_roles"] == ["controller"]
