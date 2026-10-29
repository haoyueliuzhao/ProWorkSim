import json
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_api_parent_v076 as parent


def _proposal():
    return {"description": "ProWorkSim v076 API aggregate boundary async-control",
            "create_command": parent.creation_command("ProWorkSim v076 API aggregate boundary async-control")}


def _properties():
    return {"LoadState": "loaded", "ActiveState": "active", "Transient": "yes",
        "ControlGroup": parent.CGROUP, "Description": _proposal()["description"],
        "MemoryMax": str(parent.MEMORY_BYTES), "MemorySwapMax": "0", "TasksMax": str(parent.TASKS_MAX),
        "MemoryAccounting": "yes", "StopWhenUnneeded": "no", "CollectMode": "inactive"}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, duration):
        assert 0 < duration <= .1
        self.now += duration


def test_returned_job_waits_for_active_then_kernel_qualification(monkeypatch):
    clock = Clock()
    properties = iter([{"LoadState": "not-found"}, {**_properties(), "ActiveState": "activating"}, _properties()])
    reads = []
    def inspect(**kwargs):
        reads.append(kwargs["timeout"])
        return next(properties)
    monkeypatch.setattr(parent, "inspect_systemd", inspect)
    monkeypatch.setattr(parent, "kernel_boundary", lambda: {"memory_max_bytes": parent.MEMORY_BYTES})
    result = parent.wait_qualified(_proposal(), clock=clock, sleeper=clock.sleep,
                                   runner=lambda *a, **kw: pytest.fail("Do not reissue start"))
    assert result["polls"] == 3 and result["elapsed_seconds"] == pytest.approx(.2)
    assert result["start_commands_resent"] == 0
    assert reads == [3.0, 3.0, 3.0]


def test_pending_job_times_out_without_unbounded_wait_or_start_retry(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(parent, "inspect_systemd", lambda **kw: {"LoadState": "loaded", "ActiveState": "activating"})
    with pytest.raises(parent.ParentQualificationUnknown) as found:
        parent.wait_qualified(_proposal(), clock=clock, sleeper=clock.sleep,
                              runner=lambda *a, **kw: pytest.fail("Do not reissue start"))
    assert found.value.observation["elapsed_seconds"] == pytest.approx(15)
    assert found.value.observation["start_commands_resent"] == 0
    assert found.value.observation["last_properties"]["ActiveState"] == "activating"


def test_creation_submits_once_and_retains_unknown_without_false_ready(tmp_path, monkeypatch):
    run = tmp_path / "runtime"
    monkeypatch.setattr(parent, "RUN", run)
    monkeypatch.setattr(parent, "CREATED", run / "created.json")
    monkeypatch.setattr(parent, "RELEASED", run / "released.json")
    for name in ("AUTHORIZATION", "PROPOSAL"):
        path = tmp_path / (name.lower() + ".json")
        path.write_text("{}")
        monkeypatch.setattr(parent, name, path)
    monkeypatch.setattr(parent, "approved", lambda: ({}, _proposal()))
    monkeypatch.setattr(parent, "inspect_systemd", lambda **kw: {"LoadState": "not-found"})
    def unqualified(*args, **kwargs):
        raise parent.ParentQualificationUnknown({"polls": 150, "elapsed_seconds": 15,
                                                "start_commands_resent": 0})
    monkeypatch.setattr(parent, "wait_qualified", unqualified)
    commands = []
    def runner(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout='o "/org/freedesktop/systemd1/job/123"', stderr="")
    with pytest.raises(parent.ParentQualificationUnknown):
        parent.create(runner=runner)
    assert len(commands) == 1 and "StartTransientUnit" in commands[0]
    assert not parent.CREATED.exists()
    proof = json.loads((run / "qualification-unknown.json").read_bytes())
    assert proof["status"] == "technical_unknown" and proof["automatic_retry"] is False
    assert proof["new_start_commands"] == 1


def test_absence_inspection_uses_getunit_without_loading_a_slice():
    commands = []
    def runner(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=1, stdout="", stderr="Call failed: Unit " + parent.SLICE + " not loaded.")
    value = parent.inspect_systemd(runner=runner)
    assert value["LoadState"] == "not-found"
    assert len(commands) == 1 and "GetUnit" in commands[0]
    assert "LoadUnit" not in commands[0] and "systemctl" not in commands[0]
