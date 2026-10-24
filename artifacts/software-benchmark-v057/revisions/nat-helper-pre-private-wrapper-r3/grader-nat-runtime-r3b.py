"""Host-owned slirp NAT for two private grader-only network namespaces.

No host routes, iptables, network mode, mounts or GPU devices are changed.
Keepers are disposable sleep containers from one pinned requests image; only
explicitly bound grading containers may join their namespaces.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_queue_v056 import lock
from .storage import digest

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs/software-benchmark-v057"
SOURCE_REQUESTS = RUNS / "grading-environment-r1/source-requests.json"
SOCKET = ROOT / "runs/software-panel-v053/docker/docker.sock"
DOCKER = ROOT / "runs/software-benchmark-v054/scorer-venv/bin/docker"
VERSION = "v057-grader-private-netns-nat-r3"
IMAGES = {
    "psf__requests-2931": "sha256:d169b644e994bc20c0d77719b008e34fdd9afab2c211d7f52e27a578e692c75b",
    "psf__requests-1921": "sha256:ef715951df0c8e5504514a14c03362da52774c57faa88f990965b8787512d171",
    "psf__requests-5414": "sha256:ff5caf954ad336865c3614fa0157f383a8e80c40ec802625347d119e3e33965e",
    "psf__requests-1766": "sha256:04d36df979a3cc89ceba67df58abd56e975e3b43db54ef69e94ec1ff5223d020",
}
KEEPER_IMAGE = IMAGES["psf__requests-1921"]


def _run(argv, *, timeout=30, check=True):
    env = dict(os.environ)
    for name in ("DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        env.pop(name, None)
    env.update(HTTP_PROXY="", HTTPS_PROXY="", ALL_PROXY="", http_proxy="", https_proxy="", all_proxy="",
               NO_PROXY="*", no_proxy="*")
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False, env=env)
    if check and result.returncode:
        raise RuntimeError(json.dumps({"returncode": result.returncode, "command": argv,
                                       "stderr": result.stderr[-5000:]}, ensure_ascii=False))
    return result


def docker(*args, check=True):
    return _run([str(DOCKER), "--host", "unix://" + str(SOCKET), *args], check=check)


def inspect_container(identity):
    value = docker("inspect", identity, check=False)
    if value.returncode:
        if "no such" in value.stderr.lower():
            return None
        raise RuntimeError(value.stderr.strip())
    rows = json.loads(value.stdout)
    if len(rows) != 1:
        raise ValueError("Expected exactly one private Docker container")
    return rows[0]


def _process(pid):
    if type(pid) is not int or pid <= 0:
        raise ValueError("A positive host PID is required")
    raw = Path(f"/proc/{pid}/stat").read_text()
    fields = raw[raw.rfind(")") + 2:].split()
    return {"pid": pid, "start_ticks": int(fields[19]), "state": fields[0]}


def _netns(pid):
    return int(_run(["sudo", "-n", "stat", "-Lc", "%i", f"/proc/{int(pid)}/ns/net"]).stdout.strip())


def _unit(name):
    if not name.startswith("proworksim-v057-grader-nat-") or "/" in name:
        raise ValueError("Only this helper's exact transient unit may be inspected")
    result = _run(["sudo", "-n", "systemctl", "show", name,
                   "-p", "ActiveState", "-p", "SubState", "-p", "MainPID",
                   "-p", "InvocationID", "-p", "LoadState"], check=False)
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def _root(directory):
    root = Path(directory).resolve()
    if not root.is_relative_to(RUNS) or root == RUNS:
        raise ValueError("NAT receipts must use an independent v057 root")
    return root


def _sources():
    rows = json.loads(SOURCE_REQUESTS.read_bytes())
    if {row["instance_id"]: row["image_id"] for row in rows} != IMAGES:
        raise ValueError("NAT is restricted to the four pinned requests task images")
    for row in rows:
        request = json.loads(checked(row["request"]).read_bytes())
        if (request["image"]["image_id"] != row["image_id"]
                or Path(request["docker_socket"]).resolve() != SOCKET
                or checked(request["docker_cli"]) != DOCKER):
            raise ValueError("Private Docker/image binding differs from the frozen task")
    if not SOCKET.is_socket():
        raise ValueError("The admitted private Docker socket is unavailable")
    return {"source_requests": reference(SOURCE_REQUESTS), "helper": reference(__file__),
            "docker_cli": reference(DOCKER), "slirp4netns": reference("/usr/bin/slirp4netns")}


def _keeper_matches(container, tag, lane):
    labels = container["Config"].get("Labels") or {}
    host = container["HostConfig"]
    if (container["Image"] != KEEPER_IMAGE or host["NetworkMode"] != "none"
            or host.get("Privileged") or host.get("Binds") or host.get("Devices") or host.get("DeviceRequests")
            or container.get("Mounts") or host.get("CapAdd")
            or host.get("Memory") != 64 * 1024**2 or host.get("NanoCpus") != 100_000_000
            or not host.get("ReadonlyRootfs") or host.get("Dns") != ["10.0.2.3"]
            or labels.get("proworksim.owner") != VERSION or labels.get("proworksim.registry") != tag
            or labels.get("proworksim.lane") != str(lane)):
        raise ValueError("Keeper ownership or isolation/resource properties differ")


def validate_registry(registry_reference):
    registry = json.loads(checked(registry_reference).read_bytes())
    root = _root(registry["root"])
    if (registry.get("version") != VERSION or registry.get("ready") is not True
            or registry.get("allowed_image_ids") != IMAGES or len(registry.get("lanes", [])) != 2
            or (root / "closed.json").exists() or registry.get("source_manifest") != _sources()):
        raise ValueError("A live, exact two-lane NAT registry is required")
    for lane in registry["lanes"]:
        container = inspect_container(lane["keeper_id"])
        if container is None or not container["State"]["Running"]:
            raise ValueError("Keeper is no longer running")
        _keeper_matches(container, registry["registry_tag"], lane["lane"])
        pid = int(container["State"]["Pid"])
        identity = _process(pid)
        unit = _unit(lane["slirp_unit"])
        if (pid != lane["keeper_pid"] or identity["start_ticks"] != lane["keeper_start_ticks"]
                or _netns(pid) != lane["keeper_netns_inode"]
                or unit.get("ActiveState") != "active"
                or unit.get("InvocationID") != lane["slirp_unit_identity"]["InvocationID"]
                or int(unit.get("MainPID", 0)) != lane["slirp_process"]["pid"]
                or _process(lane["slirp_process"]["pid"])["start_ticks"] != lane["slirp_process"]["start_ticks"]):
            raise ValueError("NAT namespace or owned slirp service identity changed")
    return registry


def start_registry(directory):
    root = _root(directory)
    root.mkdir(parents=True, exist_ok=True)
    with lock(root / "lifecycle.lock"):
        if (root / "registry.json").exists():
            ref = reference(root / "registry.json")
            validate_registry(ref)
            return ref
        if (root / "intent.json").exists():
            raise ValueError("An interrupted NAT start needs owned-resource cleanup, not an implicit replay")
        sources = _sources()
        tag = digest(str(root).encode())[:16]
        intent = {"version": VERSION, "root": str(root), "registry_tag": tag,
            "source_manifest": sources, "lanes": [{"lane": lane,
                "keeper_name": f"pws-v057-grader-net-{tag}-{lane}",
                "slirp_unit": f"proworksim-v057-grader-nat-{tag}-{lane}.service"} for lane in (0, 1)]}
        write_new(root / "intent.json", intent)
        lanes = []
        for lane in intent["lanes"]:
            folder = root / f"lane-{lane['lane']}"
            folder.mkdir(mode=0o700)
            create = ["create", "--name", lane["keeper_name"], "--network", "none", "--dns", "10.0.2.3",
                "--cpus", "0.1", "--memory", "64m", "--pids-limit", "32", "--read-only",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges=true",
                "--label", "proworksim.owner=" + VERSION, "--label", "proworksim.registry=" + tag,
                "--label", "proworksim.lane=" + str(lane["lane"]), "--entrypoint", "/bin/sleep",
                KEEPER_IMAGE, "infinity"]
            keeper_id = docker(*create).stdout.strip()
            if len(keeper_id) != 64 or any(c not in "0123456789abcdef" for c in keeper_id):
                raise ValueError("Docker did not return a full owned keeper identity")
            write_new(folder / "created.json", {**lane, "keeper_id": keeper_id, "command": create})
            docker("start", keeper_id)
            container = inspect_container(keeper_id)
            _keeper_matches(container, tag, lane["lane"])
            pid = int(container["State"]["Pid"])
            process = _process(pid)
            netns = _netns(pid)
            host_netns = os.stat("/proc/self/ns/net").st_ino
            if netns == host_netns:
                raise ValueError("Keeper cannot share the host network namespace")
            command = ["sudo", "-n", "systemd-run", "--quiet", "--unit=" + lane["slirp_unit"],
                "--property=Restart=no", "--property=KillMode=control-group", "--property=TimeoutStopSec=10",
                "--property=CPUQuota=50%", "--property=MemoryMax=256M", "--property=TasksMax=32",
                "/usr/bin/slirp4netns", "--configure", "--disable-host-loopback",
                "--enable-sandbox", "--enable-seccomp", str(pid), "tap0"]
            write_new(folder / "slirp-launch.json", {"command": command, "keeper_process": process,
                "keeper_netns_inode": netns, "host_netns_inode": host_netns})
            _run(command)
            initial_unit = _unit(lane["slirp_unit"])
            if not initial_unit.get("InvocationID"):
                raise RuntimeError("Owned slirp launch lacks an invocation identity")
            write_new(folder / "slirp-started.json", {"unit": lane["slirp_unit"],
                "unit_identity": initial_unit, "launch_command": command})
            until = time.monotonic() + 20
            while True:
                unit = _unit(lane["slirp_unit"])
                if unit.get("ActiveState") == "failed":
                    raise RuntimeError("Owned slirp service failed; retain its journal and clean its exact unit")
                proof = _run(["sudo", "-n", "nsenter", "--target", str(pid), "--net", "--",
                              "ip", "-j", "addr", "show", "dev", "tap0"], check=False)
                if unit.get("ActiveState") == "active" and int(unit.get("MainPID", 0)) > 0 and proof.returncode == 0:
                    break
                if time.monotonic() >= until:
                    raise TimeoutError("Private grader tap interface did not become ready")
                time.sleep(.1)
            if _process(pid)["start_ticks"] != process["start_ticks"] or _netns(pid) != netns:
                raise ValueError("Keeper identity changed during slirp configuration")
            observation = {**lane, "keeper_id": keeper_id, "keeper_pid": pid,
                "keeper_start_ticks": process["start_ticks"], "keeper_netns_inode": netns,
                "host_netns_inode": host_netns, "network_mode": "container:" + keeper_id,
                "slirp_unit_identity": unit, "slirp_process": _process(int(unit["MainPID"])),
                "tap_addresses": json.loads(proof.stdout), "host_loopback_disabled": True,
                "slirp_sandbox": True, "slirp_seccomp": True, "host_network_modified": False}
            observation["proof"] = write_new(folder / "ready.json", observation)
            lanes.append(observation)
        return write_new(root / "registry.json", {"version": VERSION, "root": str(root),
            "ready": True, "registry_tag": tag, "source_manifest": sources,
            "keeper_image_id": KEEPER_IMAGE, "private_docker_socket": str(SOCKET),
            "allowed_image_ids": IMAGES, "lanes": lanes, "actor_network_access": False,
            "host_mounts": [], "gpu_devices": [], "forwarded_host_ports": [],
            "scope": "Only explicitly bound private graders; direct NAT, no HTTP proxy"})


def close_registry(directory):
    root = _root(directory)
    with lock(root / "lifecycle.lock"):
        if (root / "closed.json").exists():
            return reference(root / "closed.json")
        intent = json.loads((root / "intent.json").read_bytes())
        if intent.get("version") != VERSION or intent.get("root") != str(root):
            raise ValueError("Unknown NAT ownership intent")
        rows, errors = [], []
        for lane in intent["lanes"]:
            try:
                container = inspect_container(lane["keeper_name"])
                if container is not None:
                    _keeper_matches(container, intent["registry_tag"], lane["lane"])
                    folder = root / f"lane-{lane['lane']}"
                    if (folder / "created.json").exists():
                        created = json.loads((folder / "created.json").read_bytes())
                        if created["keeper_id"] != container["Id"]:
                            raise ValueError("Keeper name now refers to another container")
                    ids = docker("ps", "-q", "--no-trunc").stdout.split()
                    for identity in ids:
                        if identity == container["Id"]:
                            continue
                        peer = inspect_container(identity)
                        if peer and peer["HostConfig"]["NetworkMode"] == "container:" + container["Id"]:
                            raise RuntimeError("A grader is still using this namespace; do not release it")
                unit = _unit(lane["slirp_unit"])
                ready_path = root / f"lane-{lane['lane']}" / "ready.json"
                if unit.get("ActiveState") in {"active", "activating", "deactivating"}:
                    if not ready_path.exists():
                        launched = json.loads((ready_path.parent / "slirp-started.json").read_bytes())
                        if unit.get("InvocationID") != launched["unit_identity"]["InvocationID"]:
                            raise ValueError("Partial launch unit was replaced; do not stop it")
                    else:
                        ready = json.loads(ready_path.read_bytes())
                        if unit.get("InvocationID") != ready["slirp_unit_identity"]["InvocationID"]:
                            raise ValueError("Slirp unit was replaced; do not stop it")
                    _run(["sudo", "-n", "systemctl", "stop", lane["slirp_unit"]])
                unit_after = _unit(lane["slirp_unit"])
                if unit_after.get("ActiveState") not in {"inactive", "failed", None}:
                    raise RuntimeError("Owned slirp service did not stop")
                if container is not None:
                    if container["State"]["Running"]:
                        docker("stop", "--time", "2", container["Id"])
                    docker("rm", container["Id"])
                    if inspect_container(container["Id"]) is not None:
                        raise RuntimeError("Owned keeper is still present")
                rows.append({"lane": lane["lane"], "keeper_id": container["Id"] if container else None,
                    "slirp_unit": lane["slirp_unit"], "slirp_state": unit_after, "quiescent": True})
            except Exception as error:
                errors.append({"lane": lane["lane"], "type": type(error).__name__, "message": str(error)})
        result = {"version": VERSION, "quiescent": not errors, "lanes": rows, "errors": errors,
                  "other_containers_or_units_signalled": False, "host_network_changed": False}
        if errors:
            write_new(root / ("cleanup-failed-" + str(time.time_ns()) + ".json"), result)
            raise RuntimeError("Owned NAT cleanup remains incomplete: " + json.dumps(errors))
        return write_new(root / "closed.json", result)
