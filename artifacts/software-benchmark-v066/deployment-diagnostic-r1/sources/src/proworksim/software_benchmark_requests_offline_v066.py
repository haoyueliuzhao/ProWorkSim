"""Offline Requests fixtures prepared only inside a restricted grader.

This adapter has no host network helper or namespace-entering subprocess.
The existing experiment hold applies before container creation and start.
New fixture code is not evidence that any official task has qualified.
"""
from __future__ import annotations

import io
import copy
import hashlib
import json
import os
from pathlib import Path
import tarfile

from . import software_benchmark_scorer_v054 as base
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_dispatch_v066 import require_v066_allowed

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "runs/software-benchmark-v057/grading-environment-r1"
VERSION = "v064-offline-requests-fixtures-r1"
PYTHON = "/opt/miniconda3/envs/testbed/bin/python"
FIXTURES = "/opt/proworksim-test-fixtures"
PROFILES = {
    "psf__requests-1766": {"httpbin": "0.7.0", "pytest_httpbin": "0.0.7", "standalone_httpbin": True,
                           "admission_enabled": False, "blockers": ["legacy_session_send_uses_repository_ca"]},
    "psf__requests-1921": {"httpbin": "0.7.0", "pytest_httpbin": "0.0.7", "standalone_httpbin": True,
                           "admission_enabled": False, "blockers": ["legacy_session_send_uses_repository_ca"]},
    "psf__requests-2931": {"httpbin": "0.4.0", "pytest_httpbin": "0.0.7", "standalone_httpbin": False,
                           "admission_enabled": True, "blockers": []},
    "psf__requests-5414": {"httpbin": "0.7.0", "pytest_httpbin": "1.0.0", "standalone_httpbin": False,
                           "admission_enabled": True, "blockers": []},
}
COMMON = ["Flask==1.1.4", "Werkzeug==0.16.1", "Jinja2==2.11.3", "MarkupSafe==2.0.1",
          "itsdangerous==1.1.0", "click==7.1.2", "trustme==1.2.1", "pytest-mock==2.0.0",
          "pyroute2==0.7.12"]
NAMESPACES = ("net", "mnt", "pid", "ipc")
SERVER = '''from httpbin import app
from pytest_httpbin import serve
import time
serve.CERT_DIR = "/opt/proworksim-test-fixtures/httpbin-certs"
http = serve.Server(host="127.0.0.1", port=80, application=app)
https = serve.SecureServer(host="127.0.0.1", port=443, application=app)
http.start(); https.start()
while True: time.sleep(1)
'''
# This source is passed to container.exec_run only after actual namespaces have
# been compared. Importing this module does not execute it or create a socket.
NETWORK = '''import json,socket,time
from pyroute2 import IPRoute
with IPRoute() as ip:
    links=[x.get_attr("IFLA_IFNAME") for x in ip.get_links()]
    if set(links)!={"lo"}: raise RuntimeError("Expected a fresh offline network")
    if any(r.get_attr("RTA_GATEWAY") for r in ip.get_routes(family=socket.AF_INET)):
        raise RuntimeError("Offline grader must not have an external gateway")
    ip.link("add", ifname="pwstimeout", kind="dummy")
    index=ip.link_lookup(ifname="pwstimeout")[0]
    ip.addr("add", index=index, address="10.255.255.254", prefixlen=24)
    ip.link("set", index=index, state="up")
    links=[x.get_attr("IFLA_IFNAME") for x in ip.get_links()]
    if set(links)!={"lo","pwstimeout"}: raise RuntimeError("Unexpected grader network interface")
    routes=[{"dst":r.get_attr("RTA_DST"),"prefix":r["dst_len"],"gateway":r.get_attr("RTA_GATEWAY")} for r in ip.get_routes(family=socket.AF_INET)]
sock=socket.socket();sock.settimeout(.1);start=time.monotonic()
try:
    sock.connect(("10.255.255.1",80))
    raise RuntimeError("Timeout fixture unexpectedly accepted a connection")
except socket.timeout:
    print(json.dumps({"real_connect_timeout":True,"elapsed_seconds":time.monotonic()-start,"interfaces":links,"routes":routes}))
finally: sock.close()
'''
READINESS = '''import json,ssl,time,urllib.request
context=ssl.create_default_context(cafile="/opt/proworksim-test-fixtures/httpbin-certs/cacert.pem")
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
last=None
for attempt in range(40):
    try:
        for url in ("http://httpbin.org/status/200","https://httpbin.org/status/200"):
            with opener.open(url,timeout=1) as response:
                if response.status!=200: raise RuntimeError("Fixture healthcheck failed")
        print(json.dumps({"http_ready":True,"https_ready":True,"tls_verification":True,"probe_client":"stdlib with explicit fixture CA; does not prove candidate CA compatibility"}))
        break
    except Exception as error:
        last=error;time.sleep(.1)
else: raise RuntimeError("Local HTTP/TLS fixture not ready") from last
'''


def capabilities(profile):
    return ["NET_ADMIN"] + (["NET_BIND_SERVICE"] if profile["standalone_httpbin"] else [])


def fixture_environment(profile, values):
    if isinstance(values, list):
        values = dict(value.split("=", 1) for value in values)
    env = dict(values or {})
    for key in ("HTTPBIN_URL", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "OPENSSL_CONF", "SSL_CERT_FILE", "SSL_CERT_DIR"):
        env.pop(key, None)
    env.update(NO_PROXY="", no_proxy="", HTTP_PROXY="", HTTPS_PROXY="", ALL_PROXY="",
               http_proxy="", https_proxy="", all_proxy="")
    if profile["standalone_httpbin"]:
        env.update(HTTPBIN_URL="http://httpbin.org/", REQUESTS_CA_BUNDLE=FIXTURES + "/httpbin-certs/cacert.pem")
    return env


def environment_manifest():
    inventory = json.loads((ASSETS / "packages-manifest.json").read_bytes())
    wheels = [{key: item[key] for key in ("path", "sha256", "bytes")} for item in inventory["files"]]
    for item in wheels:
        checked(item)
    return {
        "version": VERSION, "adapter": reference(__file__), "profiles": PROFILES,
        "hold_module": reference(ROOT / "src/proworksim/software_benchmark_shared_server_hold_v057.py"),
        "dispatch_guard": reference(ROOT / "src/proworksim/software_benchmark_dispatch_v066.py"),
        "authorization_bound_by": "v064 plan and request; no grant hashed into its own source manifest",
        "common_requirements": COMMON, "package_inventory": reference(ASSETS / "packages-manifest.json"),
        "wheels": wheels,
        "renewed_legacy_certificates": {name: reference(ASSETS / "certs/0.0.7" / name)
                                        for name in ("cert.pem", "key.pem", "cacert.pem")},
        "certificate_renewal_evidence": reference(ASSETS / "cert-renewal.json"),
        "legacy_certificate_semantics": "CN=127.0.0.1 without SAN, as recorded in renewal evidence",
        "named_httpbin_TLS_fixture": reference(ASSETS / "httpbin-tls-fixture.json"),
        "named_httpbin_TLS_files": {name: reference(ASSETS / "certs/httpbin.org" / name)
                                    for name in ("cert.pem", "key.pem", "cacert.pem")},
        "network_mode": "none", "host_network_helper": None,
        "capabilities_by_task": {task: capabilities(profile) for task, profile in PROFILES.items()},
        "drop_capabilities": ["ALL"], "no_new_privileges": True,
        "upstream_SYS_ADMIN_default": "removed before Docker API create; never granted",
        "official_file_transfer": "patch.diff/eval.sh bytes and modes preserved; tar ownership normalized to container root",
        "network_scope": "fresh grader network namespace only; no host route/firewall changes",
        "httpbin_service_scope": "container_loopback",
        "tcp_timeout_fixture": "10.255.255.254/24 dummy link; 10.255.255.1 has no responding neighbour",
        "legacy_CA_environment_scope": "REQUESTS_CA_BUNDLE only for standalone profiles; Session.send may ignore it",
        "task_files_changed": False, "official_harness_changed": False, "actor_network_changed": False,
        "runtime_qualified": False,
    }


def freeze_environment(path):
    return write_new(path, environment_manifest())


def validate_environment(ref):
    value = json.loads(checked(ref).read_bytes())
    if value != environment_manifest():
        raise ValueError("Offline grading environment differs from its frozen profile")
    return value


def archive_assets(manifest):
    """Copy bytes rather than symlink metadata into the private fixture archive."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        def add(name, data):
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o600
            tar.addfile(info, io.BytesIO(data))
        for item in manifest["wheels"]:
            path = checked(item)
            add("wheels/" + path.name, path.read_bytes())
        for name, item in manifest["renewed_legacy_certificates"].items():
            add("certs/" + name, checked(item).read_bytes())
        for name, item in manifest["named_httpbin_TLS_files"].items():
            add("httpbin-certs/" + name, checked(item).read_bytes())
        add("serve_httpbin.py", SERVER.encode())
    return buffer.getvalue()


def checked_exec(container, argv, *, timeout_note):
    result = container.exec_run(argv)
    if result.exit_code != 0:
        raise RuntimeError(timeout_note + ": " + result.output.decode("utf-8", "replace")[-5000:])
    return result.output.decode("utf-8", "strict")


def namespace_evidence(grader, host):
    if (set(grader) != set(NAMESPACES) or set(host) != set(NAMESPACES)
            or any(type(grader[key]) is not int or type(host[key]) is not int
                   or grader[key] <= 0 or host[key] <= 0 or grader[key] == host[key]
                   for key in NAMESPACES)):
        raise ValueError("Grader must have distinct network, mount, PID and IPC namespaces")
    return {"host": host, "grader": grader, "all_distinct": True}


def validate_create_options(kwargs, image_id, profile):
    if kwargs.get("image") != image_id:
        raise ValueError("Container image differs from admission")
    forbidden = ("volumes", "mounts", "devices", "device_requests", "volumes_from", "links", "ports",
                 "publish_all_ports", "network", "networking_config", "dns", "dns_search", "dns_opt",
                 "extra_hosts", "sysctls", "runtime", "group_add", "tmpfs", "cgroup_parent",
                 "device_cgroup_rules", "storage_opt", "use_config_proxy")
    if any(kwargs.get(key) for key in forbidden) or kwargs.get("privileged"):
        raise ValueError("Host material, devices, extra networks, privilege and runtime overrides are forbidden")
    if kwargs.get("network_mode") not in (None, "none"):
        raise ValueError("Only the offline network mode is admitted")
    for key in ("pid_mode", "ipc_mode", "uts_mode", "cgroupns"):
        if kwargs.get(key) not in (None, "", "private"):
            raise ValueError("Shared namespace modes are forbidden")
    if kwargs.get("userns_mode") not in (None, ""):
        raise ValueError("User namespace overrides are forbidden")
    if kwargs.get("cap_add") not in (None, [], capabilities(profile)):
        raise ValueError("Only explicit container-local fixture capabilities are admitted")
    if kwargs.get("cap_drop") not in (None, [], ["ALL"]):
        raise ValueError("All default capabilities must be dropped")
    if kwargs.get("security_opt") not in (None, [], ["no-new-privileges:true"]):
        raise ValueError("Security profile overrides are forbidden")


def validate_container_config(attrs, request, limits, profile):
    host = attrs["HostConfig"]
    if (attrs.get("Image") != request["image_id"] or host.get("NetworkMode") != "none"
            or host.get("Privileged") or host.get("CapAdd") != capabilities(profile)
            or host.get("CapDrop") != ["ALL"] or host.get("SecurityOpt") != ["no-new-privileges:true"]
            or host.get("CpusetCpus") != request["cpuset_cpus"]
            or host.get("Memory") != limits["memory_bytes"]
            or host.get("MemorySwap") != limits["memory_bytes"]
            or host.get("NanoCpus") != limits["nano_cpus"] or host.get("PidsLimit") != limits["pids_limit"]):
        raise ValueError("Actual grader isolation or resource limits differ")
    for key in ("PidMode", "IpcMode", "UTSMode", "CgroupnsMode"):
        if host.get(key) not in (None, "", "private"):
            raise ValueError("Actual grader shares a host or other container namespace")
    if (host.get("UsernsMode") not in (None, "") or attrs.get("Mounts")
            or any(host.get(key) for key in ("Binds", "Mounts", "VolumesFrom", "Devices", "DeviceRequests",
                                            "Links", "PortBindings", "PublishAllPorts", "Sysctls"))):
        raise ValueError("Actual grader exposes host mounts, devices or networking")
    hosts = host.get("ExtraHosts") or []
    if hosts != (["httpbin.org:127.0.0.1"] if profile["standalone_httpbin"] else []):
        raise ValueError("Unexpected grader hostname mapping")


class EnvironmentContainer(base.PreparationObservedContainer):
    def __init__(self, delegate, preparation, limits):
        super().__init__(delegate, preparation)
        self.limits = limits

    def put_archive(self, path, data, **kwargs):
        """Preserve official file bytes without granting DAC_OVERRIDE to read host-owned tar entries."""
        expected = {"/tmp": "patch.diff", "/": "eval.sh"}.get(str(path))
        if expected is None or kwargs or not isinstance(data, bytes):
            raise ValueError("Unexpected official grading file transfer")
        output = io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as source:
            members = source.getmembers()
            if len(members) != 1 or not members[0].isfile() or members[0].name != expected:
                raise ValueError("Only one exact official regular file may be transferred")
            member = copy.copy(members[0])
            body = source.extractfile(members[0]).read()
            member.uid = member.gid = 0
            member.uname = member.gname = "root"
            member.pax_headers = {k: v for k, v in member.pax_headers.items()
                                  if k not in {"uid", "gid", "uname", "gname"}}
            with tarfile.open(fileobj=output, mode="w") as target:
                target.addfile(member, io.BytesIO(body))
        result = self.delegate.put_archive(path, output.getvalue())
        if result is not True:
            raise RuntimeError("Official file transfer was not confirmed")
        evidence_path = Path(self.preparation["path"])
        evidence = json.loads(evidence_path.read_bytes())
        evidence.setdefault("official_file_transfers", []).append({
            "destination": str(path), "name": expected, "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(), "mode": member.mode,
            "source_uid": members[0].uid, "source_gid": members[0].gid,
            "container_uid": 0, "container_gid": 0, "content_changed": False})
        evidence_path.write_bytes(base.canonical(evidence))
        return result

    def start(self, *args, **kwargs):
        require_v066_allowed("v066.grader.start", instance_id=self.preparation["mapping"]["instance_id"])
        request = self.preparation
        task = request["mapping"]["instance_id"]
        manifest = validate_environment(request["environment_revision"])
        profile = manifest["profiles"][task]
        if profile["admission_enabled"] is not True or profile["blockers"]:
            raise ValueError("Task environment has an unresolved frozen-profile blocker")
        self.delegate.reload()
        validate_container_config(self.delegate.attrs, request, self.limits, profile)
        result = super().start(*args, **kwargs)
        validate_container_config(self.delegate.attrs, request, self.limits, profile)
        evidence_path = Path(request["path"])
        evidence = json.loads(evidence_path.read_bytes())
        if evidence["head_git_tree"] != request["mapping"]["official_tree"] or evidence["working_tree_clean"] is not True:
            raise ValueError("Initial grader tree differs from the fixed baseline")
        host_namespaces = {key: os.stat("/proc/self/ns/" + key).st_ino for key in NAMESPACES}
        grader = json.loads(checked_exec(self.delegate, [PYTHON, "-c",
            "import os,json; print(json.dumps({k:os.stat('/proc/self/ns/'+k).st_ino for k in ('net','mnt','pid','ipc')}))"],
            timeout_note="Private grader namespaces"))
        isolation = namespace_evidence(grader, host_namespaces)
        checked_exec(self.delegate, ["mkdir", "-p", FIXTURES], timeout_note="Fixture directory")
        if self.delegate.put_archive(FIXTURES, archive_assets(manifest)) is not True:
            raise RuntimeError("Offline fixture assets were not copied")
        requirements = COMMON + ["httpbin==" + profile["httpbin"], "pytest-httpbin==" + profile["pytest_httpbin"]]
        install = checked_exec(self.delegate, [PYTHON, "-m", "pip", "install", "--no-index",
            "--disable-pip-version-check", "--find-links=" + FIXTURES + "/wheels", *requirements],
            timeout_note="Offline dependency installation")
        if profile["pytest_httpbin"] == "0.0.7":
            checked_exec(self.delegate, [PYTHON, "-c",
                "import pathlib,shutil,pytest_httpbin; d=pathlib.Path(pytest_httpbin.__file__).parent/'certs'; "
                "[shutil.copyfile('/opt/proworksim-test-fixtures/certs/'+n,d/n) for n in ('cert.pem','key.pem','cacert.pem')]"],
                timeout_note="Renew legacy test certificate without changing its CN/SAN semantics")
        network = json.loads(checked_exec(self.delegate, [PYTHON, "-c", NETWORK], timeout_note="Container-local TCP timeout"))
        health = None
        if profile["standalone_httpbin"]:
            checked_exec(self.delegate, ["/bin/bash", "-c",
                PYTHON + " " + FIXTURES + "/serve_httpbin.py >" + FIXTURES + "/httpbin.log 2>&1 < /dev/null &"],
                timeout_note="Container-loopback httpbin startup")
            health = json.loads(checked_exec(self.delegate, [PYTHON, "-c", READINESS], timeout_note="Local HTTP/TLS service"))
        status = checked_exec(self.delegate, ["git", "-c", "safe.directory=/testbed", "-C", "/testbed",
                             "status", "--porcelain"], timeout_note="Task tree remained unchanged")
        if status:
            raise ValueError("Environment preparation changed task files")
        installed = json.loads(checked_exec(self.delegate, [PYTHON, "-c",
            "import importlib.metadata as m,json; print(json.dumps({d.metadata['Name']:d.version for d in m.distributions()}))"],
            timeout_note="Effective dependency inventory"))
        evidence.update(environment_revision=request["environment_revision"], installed_packages=installed,
                        dependency_install_log=install, timeout_route=network, namespace_evidence=isolation,
                        grader_network_namespace_inode=grader["net"], host_network_namespace_shared=False,
                        effective_network_mode="none", task_files_changed=False, local_httpbin=True,
                        standalone_httpbin=profile["standalone_httpbin"], httpbin_service_scope="container_loopback",
                        httpbin_health=health, source_only_test_admission=False,
                        upstream_capabilities_removed=request.get("upstream_capabilities_removed", []),
                        actual_capabilities=self.delegate.attrs["HostConfig"].get("CapAdd"),
                        actual_dropped_capabilities=self.delegate.attrs["HostConfig"].get("CapDrop"),
                        actual_security_options=self.delegate.attrs["HostConfig"].get("SecurityOpt"),
                        candidate_CA_compatibility_verified=False)
        evidence_path.write_bytes(base.canonical(evidence))
        return result
