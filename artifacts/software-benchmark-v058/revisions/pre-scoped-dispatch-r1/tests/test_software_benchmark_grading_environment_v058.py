"""Offline contracts; no Docker daemon, namespace, service or socket is used."""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_grading_environment_v058 as environment
from proworksim.software_benchmark_shared_server_hold_v057 import SharedServerHold


LIMITS = {"memory_bytes": 16 * 1024**3, "nano_cpus": 4 * 10**9, "pids_limit": 512}
TASK = "psf__requests-2931"


def fixture(tmp_path):
    observation = {"mapping": {"instance_id": TASK, "official_tree": "tree"},
                   "cpuset_cpus": "0-3", "path": str(tmp_path / "initial.json"),
                   "image_id": "image", "base_commit": "base", "environment_revision": "frozen"}
    attrs = {"Image": "image", "Mounts": [], "HostConfig": {
        "NetworkMode": "none", "Privileged": False, "CapAdd": ["NET_ADMIN"], "CapDrop": ["ALL"],
        "SecurityOpt": ["no-new-privileges:true"], "CpusetCpus": "0-3", "IpcMode": "private",
        "Memory": LIMITS["memory_bytes"], "MemorySwap": LIMITS["memory_bytes"],
        "NanoCpus": LIMITS["nano_cpus"], "PidsLimit": LIMITS["pids_limit"],
    }}
    calls = []

    class Container:
        id = "owned-synthetic-container"

        def __init__(self):
            self.attrs = attrs

        def reload(self):
            calls.append("reload")

        def start(self):
            calls.append("start")

        def exec_run(self, argv):
            calls.append(("exec", argv))
            assert argv[:2] == ["/bin/bash", "-c"]
            return SimpleNamespace(exit_code=0, output=b"base\ntree\n")

        def put_archive(self, path, content):
            calls.append(("put_archive", path, content))
            return True

    class Delegate:
        def create(self, **kwargs):
            calls.append(("create", kwargs))
            return Container()

    tracking = {"create_result_unknown": False, "owned_container_ids": []}
    provider = environment.EnvironmentContainers(Delegate(), "image", LIMITS, observation, tracking=tracking)
    return provider, observation, attrs, calls, tracking


def test_hold_blocks_create_and_start_before_any_delegate_access(monkeypatch, tmp_path):
    provider, observation, _, calls, tracking = fixture(tmp_path)

    def held(_):
        raise SharedServerHold("held")

    monkeypatch.setattr(environment, "require_experiment_dispatch_allowed", held)
    with pytest.raises(SharedServerHold):
        provider.create(image="image")
    wrapped = environment.EnvironmentContainer(object(), observation, LIMITS)
    with pytest.raises(SharedServerHold):
        wrapped.start()
    assert calls == [] and tracking["owned_container_ids"] == []
    assert not (tmp_path / "initial.json").exists()


def test_create_refuses_host_access_and_shared_namespaces(monkeypatch, tmp_path):
    monkeypatch.setattr(environment, "require_experiment_dispatch_allowed", lambda _: None)
    provider, _, _, calls, tracking = fixture(tmp_path)
    for override in (
        {"network_mode": "host"}, {"network_mode": "container:unrelated"},
        {"pid_mode": "host"}, {"ipc_mode": "container:unrelated"},
        {"privileged": True}, {"cap_add": ["SYS_ADMIN"]},
        {"volumes": {"/var/run/docker.sock": {"bind": "/socket"}}},
        {"devices": ["/dev/kvm"]}, {"security_opt": ["apparmor=unconfined"]},
        {"ports": {80: 8080}}, {"sysctls": {"net.ipv4.ip_forward": "1"}},
    ):
        with pytest.raises(ValueError):
            provider.create(image="image", **override)
    assert calls == [] and tracking["create_result_unknown"] is False


def test_known_legacy_ca_blocker_cannot_create_a_grader(monkeypatch, tmp_path):
    monkeypatch.setattr(environment, "require_experiment_dispatch_allowed", lambda _: None)
    provider, observation, _, calls, _ = fixture(tmp_path)
    for task in ("psf__requests-1766", "psf__requests-1921"):
        observation["mapping"]["instance_id"] = task
        with pytest.raises(ValueError, match="frozen-profile blocker"):
            provider.create(image="image")
    assert calls == []


def test_create_enforces_limits_and_clears_proxy_and_ca_overrides(monkeypatch, tmp_path):
    monkeypatch.setattr(environment, "require_experiment_dispatch_allowed", lambda _: None)
    provider, _, _, calls, tracking = fixture(tmp_path)
    wrapped = provider.create(image="image", environment=["HTTP_PROXY=http://invalid", "OPENSSL_CONF=/host/config"])
    kwargs = calls[0][1]
    assert kwargs["network_mode"] == "none" and kwargs["cap_drop"] == ["ALL"]
    assert kwargs["cap_add"] == ["NET_ADMIN"] and kwargs["privileged"] is False
    assert kwargs["mem_limit"] == kwargs["memswap_limit"] == LIMITS["memory_bytes"]
    assert kwargs["environment"]["HTTP_PROXY"] == "" and "OPENSSL_CONF" not in kwargs["environment"]
    assert tracking == {"create_result_unknown": False, "owned_container_ids": [wrapped.id]}
    legacy = environment.fixture_environment(environment.PROFILES["psf__requests-1921"], {})
    assert legacy["REQUESTS_CA_BUNDLE"] == environment.FIXTURES + "/httpbin-certs/cacert.pem"
    assert legacy["HTTPBIN_URL"] == "http://httpbin.org/" and "OPENSSL_CONF" not in legacy


def test_actual_container_config_and_namespace_proofs_are_required(tmp_path):
    _, observation, attrs, _, _ = fixture(tmp_path)
    profile = environment.PROFILES[TASK]
    environment.validate_container_config(attrs, observation, LIMITS, profile)
    for host_delta in ({"Privileged": True}, {"NetworkMode": "host"}, {"CapAdd": ["SYS_ADMIN"]},
                       {"Memory": 0}, {"PidMode": "host"}, {"Binds": ["/host:/host"]}):
        changed = copy.deepcopy(attrs)
        changed["HostConfig"].update(host_delta)
        with pytest.raises(ValueError):
            environment.validate_container_config(changed, observation, LIMITS, profile)
    host = dict(zip(environment.NAMESPACES, (10, 11, 12, 13)))
    grader = dict(zip(environment.NAMESPACES, (20, 21, 22, 23)))
    assert environment.namespace_evidence(grader, host)["all_distinct"] is True
    for key in environment.NAMESPACES:
        with pytest.raises(ValueError, match="distinct"):
            environment.namespace_evidence({**grader, key: host[key]}, host)


def test_start_records_isolation_before_container_local_preparation(monkeypatch, tmp_path):
    monkeypatch.setattr(environment, "require_experiment_dispatch_allowed", lambda _: None)
    monkeypatch.setattr(environment, "validate_environment", lambda _: {"profiles": environment.PROFILES})
    monkeypatch.setattr(environment, "archive_assets", lambda _: b"synthetic-assets")
    provider, observation, _, calls, _ = fixture(tmp_path)
    wrapper = provider.create(image="image")
    seen = []

    def checked_exec(_, argv, *, timeout_note):
        seen.append(timeout_note)
        if timeout_note == "Private grader namespaces":
            return json.dumps({key: environment.os.stat("/proc/self/ns/" + key).st_ino + 1
                               for key in environment.NAMESPACES})
        if timeout_note == "Container-local TCP timeout":
            return json.dumps({"real_connect_timeout": True})
        if timeout_note == "Effective dependency inventory":
            return "{}"
        return ""

    monkeypatch.setattr(environment, "checked_exec", checked_exec)
    wrapper.start()
    assert seen[0] == "Private grader namespaces"
    assert "Container-local TCP timeout" in seen
    result = json.loads((tmp_path / "initial.json").read_text())
    assert result["local_httpbin"] is True and result["standalone_httpbin"] is False
    assert result["effective_network_mode"] == "none" and result["task_files_changed"] is False
    assert result["namespace_evidence"]["all_distinct"] is True
    assert result["environment_revision"] == observation["environment_revision"]
    assert any(isinstance(row, tuple) and row[0] == "put_archive" for row in calls)
