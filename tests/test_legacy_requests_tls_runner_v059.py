"""CPU-only runner controls; no Docker, TCP connection, or real timer is started."""
import copy
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_candidates_v054 import write_new

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tls_runner_v059", ROOT / "tools/check_legacy_requests_tls_v059.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def attrs(image="sha256:" + "a" * 64, labels=None):
    return {"Image": image, "Config": {"User": "root", "Labels": {"image.label": "retained", **(labels or {})}},
            "Mounts": [], "State": {"Running": False}, "HostConfig": {
                "NetworkMode": "none", "Memory": 4 * 1024**3, "MemorySwap": 4 * 1024**3,
                "NanoCpus": 2 * 10**9, "PidsLimit": 64, "CapAdd": ["NET_BIND_SERVICE"],
                "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"],
                "ExtraHosts": ["httpbin.org:127.0.0.1"], "IpcMode": "private"}}


def test_pending_authorization_precedes_dns_or_resource_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.policy, "AUTHORIZATION_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(runner, "RUN_ROOT", tmp_path / "never-created")
    monkeypatch.setattr(runner.socket, "getaddrinfo", lambda *a, **k: pytest.fail("DNS before authorization"))
    monkeypatch.setattr(runner.socket, "socket", lambda *a, **k: pytest.fail("socket before authorization"))
    with pytest.raises(runner.policy.TLSDiagnosticDenied):
        runner.run()
    assert not (tmp_path / "never-created").exists()


def test_actual_container_configuration_retains_labels_but_rejects_privilege():
    labels = {"proworksim.owner": "fixed", "proworksim.task": "task"}
    actual = attrs(labels=labels)
    runner.inspect_isolation(actual, actual["Image"], labels)
    for field, value in (("Privileged", True), ("NetworkMode", "host"), ("CapAdd", ["SYS_ADMIN"]),
                         ("PortBindings", {"443/tcp": [{}]}), ("MemorySwap", -1)):
        wrong = copy.deepcopy(actual)
        wrong["HostConfig"][field] = value
        with pytest.raises(ValueError):
            runner.inspect_isolation(wrong, actual["Image"], labels)
    wrong = copy.deepcopy(actual)
    wrong["Config"]["Labels"]["proworksim.owner"] = "another"
    with pytest.raises(ValueError):
        runner.inspect_isolation(wrong, actual["Image"], labels)


def test_two_probes_keep_original_ca_and_have_bounded_source():
    compile(runner.PROBE_SOURCE, "probe", "exec")
    assert "load_verify_locations(cafile=str(ca))" in runner.PROBE_SOURCE
    assert "load_default_certs" not in runner.PROBE_SOURCE
    assert "ssl.CERT_REQUIRED" in runner.PROBE_SOURCE and "context.check_hostname" in runner.PROBE_SOURCE
    assert "allow_redirects=False" in runner.PROBE_SOURCE and "signal.alarm(25)" in runner.PROBE_SOURCE
    assert "verify=False" not in runner.PROBE_SOURCE and "ca_sha256_after" in runner.PROBE_SOURCE


@pytest.mark.parametrize("connection", ["complete", "local_probe_failure", "upstream_connect_failure"])
def test_fake_lifecycle_handles_inherited_labels_and_closes_only_own_container(tmp_path, monkeypatch, connection):
    calls = []
    image_id = "sha256:" + "a" * 64
    task = "psf__requests-1766"
    mapping = {"official_head": "b" * 40, "official_tree": "c" * 40}
    original = {"baseline_mapping": write_new(tmp_path / "mapping.json", mapping)}
    monkeypatch.setattr(runner.policy, "require_tls_diagnostic_allowed", lambda *a: {})
    monkeypatch.setattr(runner.policy, "validate_task_image", lambda *a: original)

    class Container:
        id = "d" * 64
        def __init__(self, options):
            self.attrs = attrs(image_id, options["labels"])
        def reload(self): pass
        def start(self):
            calls.append("start")
            self.attrs["State"]["Running"] = True
        def stop(self, timeout):
            calls.append("stop")
            self.attrs["State"]["Running"] = False
        def remove(self, force):
            assert force is False
            calls.append("remove")

    class Timer:
        def __init__(self, seconds, function):
            assert 0 < seconds <= 120
        def start(self): pass
        def cancel(self): pass
        def join(self, timeout): pass
        def is_alive(self): return False

    def create(**options):
        assert options["cap_add"] == ["NET_BIND_SERVICE"] and options["network_mode"] == "none"
        assert not any(k in options for k in ("volumes", "ports", "devices"))
        calls.append("create")
        return Container(options)

    def exec_text(container, argv):
        if "rev-parse" in argv:
            return mapping["official_head"] + "\n" + mapping["official_tree"] + "\n"
        if "status" in argv:
            return ""
        return json.dumps({k: os.stat("/proc/self/ns/" + k).st_ino + 1 for k in ("net", "mnt", "pid", "ipc")})

    def probe(client, container, instance, mode, resolution, budget, folder):
        assert budget.started_at is not None and instance == task
        calls.append(mode)
        return {"transport": {"upstream_connected": connection == "complete",
                              "accepted": connection == "upstream_connect_failure"},
                "probe": {"ca_unchanged": True}}

    client = SimpleNamespace(images=SimpleNamespace(get=lambda _: SimpleNamespace(
        id=image_id, attrs={"Os": "linux", "Architecture": "amd64"})),
        containers=SimpleNamespace(create=create))
    monkeypatch.setattr(runner.threading, "Timer", Timer)
    monkeypatch.setattr(runner, "exec_text", exec_text)
    monkeypatch.setattr(runner, "run_probe", probe)
    result = runner.run_task(client, {"image_ids": {task: image_id}}, task, {}, tmp_path / "task")
    assert result["status"] == "diagnostic_complete"
    expected = ["create", "start", "stdlib"] + (["legacy"] if connection == "complete" else []) + ["stop", "remove"]
    assert calls == expected
    if connection != "complete":
        assert result["shared_transport_unavailable"] is (connection == "upstream_connect_failure")
    quiet = json.loads((tmp_path / "task/quiescence.json").read_text())
    assert quiet["quiescent"] is True and quiet["owned_container_ids"] == ["d" * 64]


def test_lost_create_response_recovers_only_exact_owned_name_and_labels(tmp_path, monkeypatch):
    image_id, task = "sha256:" + "a" * 64, "psf__requests-1766"
    original = {"baseline_mapping": write_new(tmp_path / "mapping.json", {})}
    monkeypatch.setattr(runner.policy, "require_tls_diagnostic_allowed", lambda *a: {})
    monkeypatch.setattr(runner.policy, "validate_task_image", lambda *a: original)
    recorded, removed = {}, []

    class Container:
        id = "e" * 64
        def __init__(self):
            self.attrs = {"Image": image_id, "Config": {"Labels": recorded["labels"]}, "State": {"Running": False}}
        def reload(self): pass
        def remove(self, force):
            assert force is False
            removed.append(self.id)

    def create(**options):
        recorded.update(options)
        raise TimeoutError("synthetic response loss")

    def get(name):
        assert name == recorded["name"]
        return Container()

    client = SimpleNamespace(images=SimpleNamespace(get=lambda _: SimpleNamespace(
        id=image_id, attrs={"Os": "linux", "Architecture": "amd64"})),
        containers=SimpleNamespace(create=create, get=get))
    result = runner.run_task(client, {"image_ids": {task: image_id}}, task, {}, tmp_path / "task")
    quiet = json.loads((tmp_path / "task/quiescence.json").read_text())
    assert result["status"] == "technical_unknown" and quiet["quiescent"] is True
    assert quiet["create_result_unknown"] is False and removed == ["e" * 64]
