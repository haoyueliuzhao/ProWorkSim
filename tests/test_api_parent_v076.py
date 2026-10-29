import json
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_api_parent_v076 as parent
from proworksim import software_benchmark_episodes_v076 as episodes


def _proposal():
    return {"description": "ProWorkSim v076 API aggregate boundary test",
            "create_command": parent.creation_command("ProWorkSim v076 API aggregate boundary test"),
            "stop_command": parent.stopping_command()}


def _properties():
    return {"LoadState": "loaded", "ActiveState": "active", "Transient": "yes",
        "ControlGroup": parent.CGROUP, "Description": _proposal()["description"],
        "MemoryMax": str(parent.MEMORY_BYTES), "MemorySwapMax": "0", "TasksMax": str(parent.TASKS_MAX),
        "MemoryAccounting": "yes", "StopWhenUnneeded": "no", "CollectMode": "inactive"}


def test_review_command_is_one_new_slice_with_fail_mode_and_exact_limits():
    command = parent.creation_command(_proposal()["description"])
    assert "StartTransientUnit" in command
    assert command[command.index(parent.SLICE) + 1] == "fail"
    assert "-" not in parent.SLICE
    assert command[command.index("MemoryMax") + 2] == str(224 * 1024**3)
    assert command[command.index("MemorySwapMax") + 2] == "0"
    assert command[command.index("TasksMax") + 2] == "32768"
    assert "CPUQuota" not in command
    assert parent.stopping_command()[-1] == parent.SLICE


def test_missing_specific_approval_prevents_creation_before_any_command(tmp_path, monkeypatch):
    monkeypatch.setattr(parent, "AUTHORIZATION", tmp_path / "absent.json")
    def forbidden(*args, **kwargs):
        pytest.fail("No command may run without the exact approval")
    with pytest.raises(PermissionError, match="specific user approval"):
        parent.create(runner=forbidden)


def test_existing_object_is_not_adopted_or_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(parent, "approved", lambda: ({}, _proposal()))
    for name in ("RUN", "CREATED", "RELEASED"):
        monkeypatch.setattr(parent, name, tmp_path / name.lower())
    monkeypatch.setattr(parent, "inspect_systemd", lambda **kwargs: {"LoadState": "loaded", "ActiveState": "active"})
    def inspect(command, **kwargs):
        pytest.fail("Do not issue a mutation for an existing object")
    with pytest.raises(PermissionError, match="existing"):
        parent.create(runner=inspect)


def test_identity_and_limits_must_match():
    assert parent.validate_properties(_properties(), _proposal())
    for key, value in [("Description", "foreign"), ("MemoryMax", "max"),
                       ("ControlGroup", "/system.slice"), ("Transient", "no")]:
        with pytest.raises(PermissionError):
            parent.validate_properties({**_properties(), key: value}, _proposal())


def test_kernel_boundary_verifies_parent_max_swap_and_no_direct_process(tmp_path):
    folder = tmp_path / parent.SLICE
    folder.mkdir()
    values = {"memory.max": str(parent.MEMORY_BYTES), "memory.swap.max": "0",
              "pids.max": str(parent.TASKS_MAX), "cgroup.procs": ""}
    for name, value in values.items():
        (folder / name).write_text(value)
    assert parent.kernel_boundary(cgroup_root=tmp_path)["memory_max_bytes"] == parent.MEMORY_BYTES
    (folder / "memory.swap.max").write_text("max")
    with pytest.raises(PermissionError):
        parent.kernel_boundary(cgroup_root=tmp_path)


def test_api_actual_cgroup_membership_must_match_exact_parent(tmp_path, monkeypatch):
    monkeypatch.setattr(parent, "require_qualified", lambda: {"qualification": "test"})
    identity = "a" * 64
    attrs = {"Id": identity, "HostConfig": {"CgroupParent": parent.SLICE},
             "State": {"Running": True, "Pid": 42}}
    pid = tmp_path / "42"
    pid.mkdir()
    (pid / "cgroup").write_text("0::" + parent.CGROUP + "/docker-" + identity + ".scope\n")
    assert parent.validate_container_parent(attrs, require_running=True, proc_root=tmp_path)
    (pid / "cgroup").write_text("0::/system.slice/docker-" + identity + ".scope\n")
    with pytest.raises(PermissionError, match="outside"):
        parent.validate_container_parent(attrs, require_running=True, proc_root=tmp_path)


def test_new_api_options_keep_original_isolation_and_parent_qwen_unaffected(monkeypatch):
    monkeypatch.setattr(parent, "require_qualified", lambda: {"qualification": "test"})
    policy = SimpleNamespace()
    api = episodes.api_episode(policy)
    native = episodes.episode(policy)
    claim = {"spec": {"role": "actor", "image_id": "sha256:" + "a" * 64},
             "docker_name": "pws-v066-example", "key": "actor-1"}
    args = ("actor", {"sha256": "b" * 64}, claim, "pws-v066-volume", ["/opt/pws-runtime/bin/python"])
    api_options = api.OwnedActorPair.create_container.__globals__["container_options"](*args)
    native_options = native.OwnedActorPair.create_container.__globals__["container_options"](*args)
    assert api_options.pop("cgroup_parent") == parent.SLICE
    assert api_options == native_options
    assert native_options["network_mode"] == "none"
    assert native_options["cap_drop"] == ["ALL"]
    assert native_options["mem_limit"] == 16 * 1024**3


def test_unqualified_parent_rejects_api_before_claim_or_episode(monkeypatch):
    def unavailable():
        raise PermissionError("parent not approved")
    monkeypatch.setattr(parent, "require_qualified", unavailable)
    binding = object.__new__(episodes.EpisodeBindings)
    binding.api = SimpleNamespace(run_episode=lambda *a, **kw: pytest.fail("Cannot enter model/claim path"))
    with pytest.raises(PermissionError, match="not approved"):
        binding.run_api({"model_key": "DEEPSEEK", "input_plus_output_tokens": 5_000_000}, {})


def test_pending_actor_claim_blocks_slice_stop_before_any_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(parent, "approved", lambda: ({}, _proposal()))
    monkeypatch.setattr(parent, "require_qualified", lambda: {})
    monkeypatch.setattr(parent, "inspect_systemd", lambda **kw: _properties())
    monkeypatch.setattr(parent.original, "BATCH_ROOT", tmp_path)
    claims = tmp_path / "resource-claims"
    claims.mkdir()
    (claims / "active-actor-1.json").write_text(json.dumps({"spec": {"slot_id": "v064:test:DEEPSEEK_REF_B5000K:1"}}))
    with pytest.raises(PermissionError, match="claims remain"):
        parent.stop_empty(runner=lambda *a, **kw: pytest.fail("No stop command while API claims remain"))
