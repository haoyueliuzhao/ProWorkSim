"""Requests grading fixtures with private grading-only NAT and TCP timeouts.

No task, candidate or official test is edited. All additions live outside
/testbed in a fresh grader. The dummy link belongs only to that container's
network namespace; it supplies an unanswered neighbour for timeout tests.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
from .software_benchmark_shared_server_hold_v057 import require_experiment_dispatch_allowed
import tarfile

from . import software_benchmark_scorer_v054 as base
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .storage import digest

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "runs/software-benchmark-v057/grading-environment-r1"
VERSION = "v057-requests-grading-fixtures-r3-private-nat"
PYTHON = "/opt/miniconda3/envs/testbed/bin/python"
FIXTURES = "/opt/proworksim-test-fixtures"
PROFILES = {
    "psf__requests-1766": {"httpbin": "0.7.0", "pytest_httpbin": "0.0.7", "standalone_httpbin": False},
    "psf__requests-1921": {"httpbin": "0.7.0", "pytest_httpbin": "0.0.7", "standalone_httpbin": False},
    "psf__requests-2931": {"httpbin": "0.7.0", "pytest_httpbin": "0.0.7", "standalone_httpbin": False},
    "psf__requests-5414": {"httpbin": "0.7.0", "pytest_httpbin": "1.0.0", "standalone_httpbin": False},
}
COMMON = ["Flask==1.1.4", "Werkzeug==0.16.1", "Jinja2==2.11.3", "MarkupSafe==2.0.1",
          "itsdangerous==1.1.0", "click==7.1.2", "trustme==1.2.1", "pytest-mock==2.0.0",
          "pyroute2==0.7.12"]
NETWORK = '''import json,socket,time
from pyroute2 import IPRoute
with IPRoute() as ip:
    if not ip.link_lookup(ifname="pwstimeout"):
        ip.link("add", ifname="pwstimeout", kind="dummy")
    index=ip.link_lookup(ifname="pwstimeout")[0]
    addresses={x.get_attr("IFA_ADDRESS") for x in ip.get_addr(index=index)}
    if "10.255.255.254" not in addresses:
        ip.addr("add", index=index, address="10.255.255.254", prefixlen=24)
    ip.link("set", index=index, state="up")
    links=[x.get_attr("IFLA_IFNAME") for x in ip.get_links()]
    if set(links)!={"lo","tap0","pwstimeout"}: raise RuntimeError("Unexpected grader network interface")
    routes=[{"dst":r.get_attr("RTA_DST"),"prefix":r["dst_len"],"gateway":r.get_attr("RTA_GATEWAY")} for r in ip.get_routes(family=socket.AF_INET)]
sock=socket.socket();sock.settimeout(.1);start=time.monotonic()
try:
    sock.connect(("10.255.255.1",80))
    raise RuntimeError("Timeout fixture unexpectedly accepted a connection")
except socket.timeout:
    print(json.dumps({"real_connect_timeout":True,"elapsed_seconds":time.monotonic()-start,"interfaces":links,"routes":routes}))
finally: sock.close()
'''


def environment_manifest():
    inventory = json.loads((ASSETS / "packages-manifest.json").read_bytes())
    wheels = [{key: item[key] for key in ("path", "sha256", "bytes")} for item in inventory["files"]]
    for item in wheels:
        checked(item)
    return {"version": VERSION, "adapter": reference(__file__), "profiles": PROFILES,
        "common_requirements": COMMON, "package_inventory": reference(ASSETS / "packages-manifest.json"),
        "wheels": wheels, "renewed_legacy_certificates": {
            name: reference(ASSETS / "certs/0.0.7" / name) for name in ("cert.pem", "key.pem", "cacert.pem")},
        "certificate_renewal_evidence": reference(ASSETS / "cert-renewal.json"),
        "nat_adapter": reference(ROOT / "src/proworksim/software_benchmark_grader_nat_v057.py"),
        "network_mode": "container:<owned private grading NAT keeper>", "extra_capability": "NET_ADMIN",
        "network_scope": "only a fresh grader network namespace; no host route/firewall changes",
        "tcp_timeout_fixture": "10.255.255.254/24 dummy link; 10.255.255.1 has no responding neighbour",
        "httpbin_url_for_legacy_tests": "http://httpbin.org/ (direct through isolated user-mode NAT)",
        "task_files_changed": False, "official_harness_changed": False, "actor_network_changed": False}


def freeze_environment(path):
    return write_new(path, environment_manifest())


def validate_environment(ref):
    value = json.loads(checked(ref).read_bytes())
    if value != environment_manifest():
        raise ValueError("Requests grading environment differs from its frozen profile")
    return value


def archive_assets(manifest):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for item in manifest["wheels"]:
            path = checked(item)
            tar.add(path, arcname="wheels/" + path.name, recursive=False)
        for name, item in manifest["renewed_legacy_certificates"].items():
            tar.add(checked(item), arcname="certs/" + name, recursive=False)
    return buffer.getvalue()


def checked_exec(container, argv, *, timeout_note):
    result = container.exec_run(argv)
    if result.exit_code != 0:
        raise RuntimeError(timeout_note + ": " + result.output.decode("utf-8", "replace")[-5000:])
    return result.output.decode("utf-8", "strict")


class EnvironmentContainer(base.PreparationObservedContainer):
    def start(self, *args, **kwargs):
        require_experiment_dispatch_allowed("grading_environment.container_start")
        result = super().start(*args, **kwargs)
        request = self.preparation
        task = request["mapping"]["instance_id"]
        manifest = validate_environment(request["environment_revision"])
        profile = manifest["profiles"][task]
        evidence_path = Path(request["path"])
        evidence = json.loads(evidence_path.read_bytes())
        host = self.delegate.attrs["HostConfig"]
        if (evidence["head_git_tree"] != request["mapping"]["official_tree"]
                or evidence["working_tree_clean"] is not True
                or host.get("NetworkMode") != request["effective_network_mode"]
                or host.get("CpusetCpus") != request["cpuset_cpus"]
                or host.get("CapAdd") != ["NET_ADMIN"]):
            raise ValueError("Initial grader tree, CPU or isolated network differs")
        netns = int(checked_exec(self.delegate, [PYTHON, "-c",
            "import os; print(os.stat('/proc/self/ns/net').st_ino)"], timeout_note="Private network namespace"))
        if (netns == os.stat("/proc/self/ns/net").st_ino
                or netns != request["keeper_network_namespace_inode"]):
            raise ValueError("Grader must not share the host network namespace")
        checked_exec(self.delegate, ["mkdir", "-p", FIXTURES], timeout_note="Fixture directory")
        if self.delegate.put_archive(FIXTURES, archive_assets(manifest)) is not True:
            raise RuntimeError("Offline fixture assets were not copied")
        requirements = COMMON + ["httpbin==" + profile["httpbin"],
                                 "pytest-httpbin==" + profile["pytest_httpbin"]]
        install = checked_exec(self.delegate, [PYTHON, "-m", "pip", "install", "--no-index",
            "--disable-pip-version-check", "--find-links=" + FIXTURES + "/wheels", *requirements],
            timeout_note="Offline dependency installation")
        if profile["pytest_httpbin"] == "0.0.7":
            checked_exec(self.delegate, [PYTHON, "-c",
                "import pathlib,shutil,pytest_httpbin; d=pathlib.Path(pytest_httpbin.__file__).parent/'certs'; "
                "[shutil.copyfile('/opt/proworksim-test-fixtures/certs/'+n,d/n) for n in ('cert.pem','key.pem','cacert.pem')]"],
                timeout_note="Renew legacy expired test certificate")
        network = json.loads(checked_exec(self.delegate, [PYTHON, "-c", NETWORK], timeout_note="Real TCP timeout route"))
        status = checked_exec(self.delegate, ["git", "-c", "safe.directory=/testbed", "-C", "/testbed",
                             "status", "--porcelain"], timeout_note="Task tree remained unchanged")
        if status:
            raise ValueError("Environment preparation changed task files")
        installed = json.loads(checked_exec(self.delegate, [PYTHON, "-c",
            "import importlib.metadata as m,json; print(json.dumps({d.metadata['Name']:d.version for d in m.distributions()}))"],
            timeout_note="Effective fixture dependency inventory"))
        evidence.update(environment_revision=request["environment_revision"], installed_packages=installed,
                        dependency_install_log=install, timeout_route=network,
                        grader_network_namespace_inode=netns, host_network_namespace_shared=False,
                        effective_network_mode=request["effective_network_mode"], nat_lane=request["nat_lane"],
                        task_files_changed=False, local_httpbin=profile["standalone_httpbin"],
                        source_only_test_admission=False)
        evidence_path.write_bytes(base.canonical(evidence))
        return result


class EnvironmentContainers(base.LocalContainers):
    def __init__(self, delegate, image_id, limits, observation, *, tracking):
        super().__init__(delegate, image_id, limits)
        self.observation, self.tracking = observation, tracking

    def create(self, **kwargs):
        require_experiment_dispatch_allowed("grading_environment.container_create")
        task = self.observation["mapping"]["instance_id"]
        if task not in PROFILES:
            raise ValueError("This environment revision admits only the four requests tasks")
        nat = self.observation["nat_lane"]
        registry = json.loads(checked(nat["registry"]).read_bytes())
        if (registry.get("version") != "v057-grader-private-netns-nat-r3"
                or registry.get("ready") is not True or nat["lane"] not in (0, 1)
                or registry.get("allowed_image_ids", {}).get(task) != self.image_id):
            raise ValueError("Grader NAT registry does not admit this private task lane")
        lane = next(row for row in registry["lanes"] if row["lane"] == nat["lane"])
        keeper = self.delegate.get(lane["keeper_id"])
        keeper.reload()
        ownership = digest(str(Path(nat["registry"]["path"]).parent.resolve()).encode())[:16]
        labels = keeper.attrs["Config"].get("Labels") or {}
        if (keeper.id != lane["keeper_id"] or keeper.attrs["Image"] != registry["keeper_image_id"]
                or not keeper.attrs["State"]["Running"] or keeper.attrs["State"]["Pid"] != lane["keeper_pid"]
                or labels.get("proworksim.owner") != registry["version"]
                or labels.get("proworksim.registry") != ownership
                or labels.get("proworksim.lane") != str(nat["lane"])
                or lane["network_mode"] != "container:" + keeper.id):
            raise ValueError("Private grader namespace keeper identity changed")
        if kwargs["image"] != self.image_id or kwargs.get("volumes") or kwargs.get("mounts") or kwargs.get("devices"):
            raise ValueError("No image substitution, host material, or GPU is admitted")
        self.observation.update(effective_network_mode=lane["network_mode"],
                                keeper_network_namespace_inode=lane["keeper_netns_inode"])
        kwargs.update(network_mode=lane["network_mode"], mem_limit=self.limits["memory_bytes"],
                      nano_cpus=self.limits["nano_cpus"], pids_limit=self.limits["pids_limit"])
        kwargs.update(cpuset_cpus=self.observation["cpuset_cpus"], cap_add=["NET_ADMIN"])
        env = kwargs.get("environment") or {}
        if isinstance(env, list):
            env = dict(value.split("=", 1) for value in env)
        env.update(NO_PROXY="", no_proxy="", HTTP_PROXY="", HTTPS_PROXY="", ALL_PROXY="",
                   http_proxy="", https_proxy="", all_proxy="")
        kwargs["environment"] = env
        self.tracking["create_result_unknown"] = True
        container = self.delegate.create(**kwargs)
        self.tracking["owned_container_ids"].append(container.id)
        self.tracking["create_result_unknown"] = False
        return EnvironmentContainer(container, self.observation)
