"""NAT preparation never admits host networking or cleans replaced ownership."""
import copy
import json

import pytest

from proworksim import software_benchmark_grader_nat_v057 as nat


def keeper():
    return {"Id": "a" * 64, "Image": nat.KEEPER_IMAGE,
        "State": {"Running": True, "Pid": 123}, "Mounts": [],
        "Config": {"Labels": {"proworksim.owner": nat.VERSION,
                              "proworksim.registry": "fixture", "proworksim.lane": "0"}},
        "HostConfig": {"NetworkMode": "none", "Privileged": False, "Binds": None,
            "Devices": [], "DeviceRequests": None, "CapAdd": None,
            "Memory": 64 * 1024**2, "NanoCpus": 100_000_000,
            "ReadonlyRootfs": True, "Dns": ["10.0.2.3"]}}


def test_keeper_rejects_host_namespace_mounts_devices_and_wrong_owner():
    row = keeper()
    nat._keeper_matches(row, "fixture", 0)
    for changed in ({"NetworkMode": "host"}, {"Binds": ["/:/host"]},
                    {"Devices": ["/dev/nvidia0"]}, {"Privileged": True}):
        bad = copy.deepcopy(row)
        bad["HostConfig"].update(changed)
        with pytest.raises(ValueError, match="ownership or isolation"):
            nat._keeper_matches(bad, "fixture", 0)
    with pytest.raises(ValueError, match="ownership or isolation"):
        nat._keeper_matches(row, "another-owner", 0)


def test_cleanup_refuses_replaced_root_unit_without_signalling(tmp_path, monkeypatch):
    monkeypatch.setattr(nat, "RUNS", tmp_path)
    root = tmp_path / "own-nat"
    folder = root / "lane-0"
    folder.mkdir(parents=True)
    unit = "proworksim-v057-grader-nat-fixture-0.service"
    (root / "intent.json").write_text(json.dumps({"version": nat.VERSION, "root": str(root),
        "registry_tag": "fixture", "lanes": [{"lane": 0, "keeper_name": "own-keeper", "slirp_unit": unit}]}))
    (folder / "created.json").write_text(json.dumps({"keeper_id": "a" * 64}))
    (folder / "ready.json").write_text(json.dumps({"slirp_unit_identity": {"InvocationID": "original"}}))
    monkeypatch.setattr(nat, "inspect_container", lambda _: keeper())
    monkeypatch.setattr(nat, "_unit", lambda _: {"ActiveState": "active", "InvocationID": "replaced"})
    calls = []

    def docker(*args, **kwargs):
        calls.append(args)
        assert args == ("ps", "-q", "--no-trunc")
        return type("Result", (), {"stdout": ""})()

    monkeypatch.setattr(nat, "docker", docker)
    monkeypatch.setattr(nat, "_run", lambda *_args, **_kwargs: pytest.fail("Do not signal a replaced unit"))
    with pytest.raises(RuntimeError, match="cleanup remains incomplete"):
        nat.close_registry(root)
    assert calls == [("ps", "-q", "--no-trunc")]
    assert not (root / "closed.json").exists()
