from pathlib import Path

import pytest

from proworksim import software_benchmark_pressure_v076 as pressure

GIB = pressure.GIB


def row(index, *, model="DEEPSEEK", started=None):
    return {"slot_id": f"v064:fixture-{index}:{model}_REF_B5000K:{index}",
            "model_key": model, "ownership_token": f"owned-slot-{index:024d}",
            "started_unix": index if started is None else started}


def harness(rows=(), **kwargs):
    current = {"memory": 900 * GIB, "time": 10.0, "rows": list(rows)}
    aborted = []
    watchdog = pressure.PressureWatchdog(lambda: current["rows"],
        lambda pair, evidence: aborted.append((pair, evidence)),
        memory_probe=lambda: current["memory"], clock=lambda: current["time"],
        wall_clock=lambda: 1000 + current["time"], **kwargs)
    return watchdog, current, aborted


def test_hysteresis_preserves_pause_until_resume_and_staleness_fails_closed():
    guard, state, _ = harness()
    assert not guard.admission()["admit"]
    assert guard.tick()["admit"]
    state["memory"] = 255 * GIB
    assert not guard.tick()["admit"]
    state["memory"] = 319 * GIB
    assert not guard.tick()["admit"]
    state["memory"] = 320 * GIB
    assert guard.tick()["admit"]
    state["time"] += 5.01
    assert guard.admission()["fresh"] is False
    assert guard.admission()["admit"] is False


def test_emergency_cancels_latest_whole_owned_api_pair_never_qwen_or_twice():
    guard, state, aborted = harness([row(1), row(3), row(2), row(999, model="QWEN")])
    state["memory"] = 192 * GIB
    first = guard.tick()
    assert first["Qwen_registry_rows_excluded"] == 1 and not first["admit"]
    assert aborted[0][0]["slot_id"] == row(3)["slot_id"]
    assert aborted[0][1]["stop_entire_owned_pair"]
    assert aborted[0][1]["technical_unknown"] and not aborted[0][1]["automatic_retry"]
    assert first["API_pair_memory_observations"][0]["pair_memory_current_bytes"] is None
    guard.tick()
    assert len(aborted) == 1
    state["time"] += 1
    guard.tick()
    assert aborted[-1][0]["slot_id"] == row(2)["slot_id"]
    state["rows"] = [row(3)]
    state["time"] += 1
    guard.tick()
    assert len(aborted) == 2  # A consumed episode is never selected again.


def test_critical_pressure_aborts_at_most_four_latest_pairs_per_second():
    guard, state, aborted = harness([row(i) for i in range(1, 8)])
    state["memory"] = 127 * GIB
    result = guard.tick()
    assert [item[0]["slot_id"] for item in aborted] == [row(i)["slot_id"] for i in (7, 6, 5, 4)]
    assert len(result["abort_requests_this_observation"]) == 4
    guard.tick()
    assert len(aborted) == 4
    state["time"] += 1
    guard.tick()
    assert len(aborted) == 7


def test_bad_observation_or_registry_cannot_admit_or_target_unowned_objects():
    guard, state, aborted = harness([row(1)])
    guard.tick()
    state["memory"] = None
    assert guard.tick()["reason"] == "pressure_observation_unavailable"
    assert not guard.admission()["admit"]
    state["memory"] = 100 * GIB
    state["rows"] = [{**row(1), "ownership_token": ""}]
    assert not guard.tick()["admit"] and aborted == []
    state["rows"] = [row(1), row(1)]
    assert not guard.tick()["admit"] and aborted == []


def test_callback_error_keeps_consumed_cancellation_and_does_not_replay():
    guard, state, _ = harness([row(1)])
    called = []
    def broken(pair, evidence):
        called.append(pair["slot_id"])
        raise RuntimeError("unknown local callback outcome")
    guard.request_abort = broken
    state["memory"] = 180 * GIB
    assert guard.tick()["last_abort"]["outcome"] == "abort_callback_outcome_unknown"
    state["time"] += 10
    guard.tick()
    assert called == [row(1)["slot_id"]]


def fixture_container(tmp_path):
    slot = row(1)["slot_id"]
    digest, container_id, pid = "b" * 64, "a" * 64, 4321
    claim_ref = {"sha256": digest}
    claim = {"spec": {"slot_id": slot, "role": "actor", "image_id": "sha256:" + "c" * 64},
             "key": "actor-1", "docker_name": "pws-v066-owned-fixture"}
    attrs = {"Id": container_id, "Image": claim["spec"]["image_id"],
             "Name": "/" + claim["docker_name"], "State": {"Running": True, "Pid": pid},
             "Config": {"Labels": {"proworksim.owner": "v066-owned-private-docker-actor-pair-r1",
                                    "proworksim.resource": claim["key"], "proworksim.claim": digest}}}
    proc = tmp_path / "proc"
    (proc / str(pid)).mkdir(parents=True)
    (proc / str(pid) / "stat").write_text(str(pid) + " (a process name) " + " ".join(["0"] * 19 + ["1234"]))
    group = "/system.slice/docker-" + container_id + ".scope"
    (proc / str(pid) / "cgroup").write_text("0::" + group + "\n")
    cgroups = tmp_path / "cgroups"
    path = cgroups / group.lstrip("/") / "memory.current"
    path.parent.mkdir(parents=True)
    path.write_text(str(2 * GIB))
    return claim_ref, claim, attrs, proc, cgroups


def test_owned_cgroup_telemetry_binds_claim_full_id_and_process_start(tmp_path):
    claim_ref, claim, attrs, proc, cgroups = fixture_container(tmp_path)
    checked = []
    def validate(ref):
        checked.append(ref)
        return claim
    container = pressure.capture_owned_container(claim_ref, attrs, validate_claim=validate, proc_root=proc)
    assert checked == [claim_ref]
    assert pressure.owned_memory_current(container, proc_root=proc, cgroup_root=cgroups) == 2 * GIB
    stat = proc / str(container.pid) / "stat"
    stat.write_text(stat.read_text().replace("1234", "9999"))
    with pytest.raises(ValueError, match="no longer current"):
        pressure.owned_memory_current(container, proc_root=proc, cgroup_root=cgroups)


def test_foreign_container_or_cgroup_is_never_read(tmp_path):
    claim_ref, claim, attrs, proc, _ = fixture_container(tmp_path)
    attrs["Config"]["Labels"]["proworksim.claim"] = "d" * 64
    with pytest.raises(ValueError, match="exact running owned"):
        pressure.capture_owned_container(claim_ref, attrs, validate_claim=lambda ref: claim, proc_root=proc)
    attrs["Config"]["Labels"]["proworksim.claim"] = claim_ref["sha256"]
    (proc / str(attrs["State"]["Pid"]) / "cgroup").write_text("0::/system.slice/other.service\n")
    with pytest.raises(ValueError, match="PID/cgroup"):
        pressure.capture_owned_container(claim_ref, attrs, validate_claim=lambda ref: claim, proc_root=proc)


def test_optional_cgroup_failure_is_unknown_not_zero_or_a_foreign_abort(tmp_path):
    claim_ref, claim, attrs, proc, _ = fixture_container(tmp_path)
    item = pressure.capture_owned_container(claim_ref, attrs, validate_claim=lambda ref: claim, proc_root=proc)
    guard, _, aborted = harness([{**row(1), "containers": (item,)}])
    guard.container_probe = lambda value: (_ for _ in ()).throw(FileNotFoundError("gone"))
    result = guard.tick()
    assert result["admit"] and aborted == []
    assert result["API_pair_memory_observations"][0]["pair_memory_current_bytes"] is None
    assert result["API_pair_memory_observations"][0]["container_observation_failures"]


def test_start_close_is_bounded_read_only_and_cannot_restart(tmp_path):
    guard, _, aborted = harness()
    assert guard.start().admission()["admit"]
    guard.close()
    assert not guard.admission()["admit"] and aborted == []
    assert not guard._thread.is_alive()
    with pytest.raises(RuntimeError):
        guard.start()
    path = tmp_path / "meminfo"
    path.write_text("MemTotal: 1000 kB\nMemAvailable: 321 kB\n")
    assert pressure.host_available_memory(path) == 321 * 1024
    assert Path(path).read_text() == "MemTotal: 1000 kB\nMemAvailable: 321 kB\n"


def test_required_parent_missing_or_wrong_bound_cannot_admit_even_with_free_host_memory():
    guard, _, aborted = harness(require_parent=True)
    result = guard.tick()
    assert not result["fresh"] and not result["admit"]
    assert result["parent_pressure"]["available_bytes"] is None and aborted == []
    parent = {"qualified": True, "current_bytes": 1 * GIB, "max_bytes": 225 * GIB}
    guard.parent_probe = lambda: parent
    result = guard.tick()
    assert not result["fresh"] and not result["admit"]
    parent["max_bytes"] = 224 * GIB
    assert guard.tick()["admit"]
    host_only, _, _ = harness()
    result = host_only.tick()
    assert result["fresh"] and result["admit"] and not result["parent_pressure"]["required"]


def test_parent_headroom_hysteresis_and_probe_failure_remain_separate_from_host():
    parent = {"qualified": True, "current_bytes": 128 * GIB, "max_bytes": 224 * GIB}
    guard, state, aborted = harness(parent_probe=lambda: dict(parent), require_parent=True)
    assert guard.tick()["admit"]  # Parent has exactly96 GiB available.
    parent["current_bytes"] = 161 * GIB  #63 GiB parent headroom; host still900.
    result = guard.tick()
    assert result["fresh"] and not result["admit"] and result["reason"] == "api_parent_hysteresis_pause"
    parent["current_bytes"] = 129 * GIB  #95 GiB does not clear hysteresis.
    assert not guard.tick()["admit"]
    parent["current_bytes"] = 128 * GIB
    assert guard.tick()["admit"]
    state["memory"] = 255 * GIB
    assert not guard.tick()["admit"]  # Parent recovery never bypasses host pressure.
    state["memory"] = 320 * GIB
    assert guard.tick()["admit"]
    guard.parent_probe = lambda: (_ for _ in ()).throw(OSError("parent disappeared"))
    result = guard.tick()
    assert not result["fresh"] and not result["admit"]
    assert result["parent_pressure"]["error"]["type"] == "OSError"
    assert result["memory_available_bytes"] == 320 * GIB and aborted == []


def test_parent_emergency_uses_owned_latest_api_pair_then_bounded_critical_batch():
    parent = {"qualified": True, "current_bytes": 208 * GIB, "max_bytes": 224 * GIB}
    guard, state, aborted = harness([row(i) for i in range(1, 8)], parent_probe=lambda: dict(parent))
    result = guard.tick()
    assert len(aborted) == 1 and aborted[0][0]["slot_id"] == row(7)["slot_id"]
    assert result["last_abort"]["reason"] == "api_parent_memory_emergency"
    assert result["memory_available_bytes"] == 900 * GIB and not result["admit"]
    parent["current_bytes"] = 216 * GIB  # Exactly8 GiB invokes critical batch.
    state["time"] += 1
    result = guard.tick()
    assert [value[0]["slot_id"] for value in aborted[1:]] == [row(i)["slot_id"] for i in (6, 5, 4, 3)]
    assert len(result["abort_requests_this_observation"]) == 4
    guard.tick()
    assert len(aborted) == 5


def test_parent_boundary_overrun_is_emergency_not_unknown_and_host_failure_is_conservative():
    parent = {"qualified": True, "current_bytes": 225 * GIB, "max_bytes": 224 * GIB}
    guard, state, aborted = harness([row(1), row(2)], parent_probe=lambda: dict(parent))
    result = guard.tick()
    assert result["fresh"] and not result["admit"]
    assert result["parent_pressure"]["available_bytes"] == 0 and len(aborted) == 2
    state["memory"] = None
    result = guard.tick()
    assert not result["fresh"] and not result["admit"]
