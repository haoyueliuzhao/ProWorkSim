import fcntl
import importlib.util
import json
import os
from pathlib import Path
from types import FunctionType, SimpleNamespace

import pytest

from proworksim import software_benchmark_api_scope_v067 as scope
from proworksim import software_benchmark_dispatch_v066 as primary
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("v067_launch_test", ROOT / "tools/launch_api_continuation_v067.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
GIB = 1024**3


def configure(tmp_path, monkeypatch):
    run, claims = tmp_path / "sidecar", tmp_path / "primary/resource-claims"
    run.mkdir(parents=True)
    claims.mkdir(parents=True)
    for key, value in {"RUN_ROOT": run, "CLAIM_FILE": run / "claim.json",
        "LEASE_FILE": claims / "active-v067-coordinator.json", "AUTH_FILE": run / "auth.json",
        "PLAN_FILE": run / "plan.json", "SPEC_FILE": run / "unit.json",
        "PROPOSAL_FILE": run / "proposal.json"}.items():
        monkeypatch.setattr(scope, key, value)
    write_new(scope.AUTH_FILE, {})
    write_new(scope.PLAN_FILE, {})
    # Clone only function globals in this isolated test; never mutate the live
    # frozen module's globals or any actual host resource path.
    context = {**primary.__dict__, "physical_capacity": lambda: {"passed": True,
        "memory_available_bytes": 4096 * GIB, "disk_free_bytes": 4096 * GIB}}
    real_budget = FunctionType(primary._budget.__code__, context, argdefs=primary._budget.__defaults__)
    def locked_budget(active, cpu, memory):
        with (claims / "allocation.lock").open("a+b") as independent:
            with pytest.raises(BlockingIOError):
                fcntl.flock(independent, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return real_budget(active, cpu, memory)
    fake_primary = SimpleNamespace(host_cpu_pool=lambda: list(range(176)),
        _budget=locked_budget, _write_claim=primary._write_claim,
        reference=primary.reference, load=primary.load)
    monkeypatch.setattr(scope, "primary", fake_primary)
    monkeypatch.setattr(scope, "require_allowed", lambda *args, **kwargs: None)
    return run, claims, real_budget


def test_auxiliary_claim_uses_primary_lock_budget_and_releases_only_itself(tmp_path, monkeypatch):
    run, claims, budget = configure(tmp_path, monkeypatch)
    other = claims / "active-model-0.json"
    original = b'{"reserved_cpu":140,"reserved_memory_bytes":858993459200}\n'
    other.write_bytes(original)  # 800 GiB; primary coordinator adds 16 GiB.
    ref = scope.reserve_coordinator()
    value = scope.load(ref)
    assert value["reserved_cpu"] == 4 and value["reserved_memory_bytes"] == 16 * GIB
    assert value["admission"]["reserved_memory_bytes_after"] == 832 * GIB
    assert value["cpu_affinity"] == [164, 165, 166, 167]
    active = [primary.load(reference(p)) for p in claims.glob("active-*.json")]
    with pytest.raises(primary.ResourceBusy):
        budget(active, 1, 1)
    scope.release_coordinator(ref)
    assert other.read_bytes() == original and not scope.LEASE_FILE.exists()
    assert scope.CLAIM_FILE.exists()  # No identity recycling.
    with pytest.raises(ValueError, match="cannot be restarted"):
        scope.reserve_coordinator()


@pytest.mark.parametrize("cpu,memory", [(148, 0), (0, 816 * GIB)])
def test_full_primary_pool_refuses_auxiliary_without_consuming_identity(tmp_path, monkeypatch, cpu, memory):
    _, claims, _ = configure(tmp_path, monkeypatch)
    other = claims / "active-other.json"
    data = json.dumps({"reserved_cpu": cpu, "reserved_memory_bytes": memory}).encode()
    other.write_bytes(data)
    with pytest.raises(primary.ResourceBusy):
        scope.reserve_coordinator()
    assert not scope.CLAIM_FILE.exists() and not scope.LEASE_FILE.exists()
    assert other.read_bytes() == data


def test_foreign_lease_is_not_adopted_or_deleted(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    scope.LEASE_FILE.write_bytes(b'{"foreign":true}\n')
    with pytest.raises(ValueError, match="cannot be adopted"):
        scope.reserve_coordinator()
    assert not scope.CLAIM_FILE.exists() and scope.LEASE_FILE.read_bytes() == b'{"foreign":true}\n'


def test_primary_pause_gate_rejects_overlap_and_safety_stop(tmp_path, monkeypatch):
    plan = tmp_path / "plan.json"
    write_new(plan, {"rows": [{"slot_id": "q", "model_key": "QWEN"}, {"slot_id": "d", "model_key": "DEEPSEEK"}]})
    monkeypatch.setattr(scope, "primary", SimpleNamespace(COORDINATOR_RUN_ROOT=tmp_path,
        PLAN_FILE=plan, load=primary.load, reference=reference))
    cursor = {"phase": "running", "failure": None, "active_generation": ["q"],
        "provider_failures": {"DEEPSEEK": {"reason": "api_initialization_unavailable"}}}
    path = tmp_path / "cursor.json"
    path.write_text(json.dumps(cursor))
    assert scope.primary_cursor()["active_generation"] == ["q"]
    for changes, error in [({"active_generation": ["d"]}, ValueError),
                           ({"provider_failures": {}}, ValueError),
                           ({"failure": {"reason": "cleanup_unknown"}}, RuntimeError)]:
        path.write_text(json.dumps({**cursor, **changes}))
        with pytest.raises(error):
            scope.primary_cursor()


def test_host_limits_match_four_unused_cpus_and_sixteen_gib(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    cgroup = tmp_path / scope.UNIT
    cgroup.mkdir()
    proc = tmp_path / "proc-cgroup"
    proc.write_text("0::/" + scope.UNIT + "\n")
    for name, value in {"memory.max": str(16 * GIB), "memory.swap.max": "0", "pids.max": "512"}.items():
        (cgroup / name).write_text(value)
    monkeypatch.setattr(scope, "Path", lambda path: proc if path == "/proc/self/cgroup"
        else tmp_path if path == "/sys/fs/cgroup" else Path(path))
    monkeypatch.setattr(scope, "os", SimpleNamespace(getuid=lambda: 1000, geteuid=lambda: 1000,
        sched_getaffinity=lambda _: {164, 165, 166, 167}))
    assert scope.verify_host_limits()["cpu_affinity"] == [164, 165, 166, 167]
    assert not set(scope.cpu_affinity()) & set(range(164))
    (cgroup / "memory.max").write_text(str(17 * GIB))
    with pytest.raises(ValueError, match="exact CPU/RAM/PID"):
        scope.verify_host_limits()


def launch_fixture(tmp_path, monkeypatch):
    run, _, _ = configure(tmp_path, monkeypatch)
    monkeypatch.setattr(launcher, "RUN_ROOT", run)
    value = {"version": scope.VERSION, "unit": scope.UNIT, "user_id": os.getuid(),
        "plan": reference(scope.PLAN_FILE), "source": reference(launcher.__file__),
        "cpu_affinity": [164, 165, 166, 167], "cpu_quota_percent": 400,
        "memory_max_bytes": 16 * GIB, "memory_swap_max_bytes": 0, "tasks_max": 512,
        "restart": "no", "timeout_stop_seconds": 420, "kill_mode": "mixed", "ownership_token": "a" * 32}
    unit_ref = write_new(scope.SPEC_FILE, value)
    write_new(scope.PROPOSAL_FILE, {"unit": unit_ref})
    claims, commands = [], []
    monkeypatch.setattr(scope, "reserve_coordinator", lambda: claims.append("aux") or reference(scope.AUTH_FILE))
    monkeypatch.setattr(launcher, "user_manager_environment", lambda: {})
    monkeypatch.setattr(launcher, "subprocess", SimpleNamespace(run=lambda command, **kwargs:
        commands.append(command) or SimpleNamespace(returncode=0, stdout="", stderr="")))
    return value, claims, commands


def test_launcher_fixed_limits_match_scope_without_starting_a_service(tmp_path, monkeypatch):
    _, claims, commands = launch_fixture(tmp_path, monkeypatch)
    launcher.launch()
    command = commands[0]
    assert claims == ["aux"]
    assert "--property=CPUAffinity=164 165 166 167" in command
    assert "--property=CPUQuota=400%" in command and "--property=MemoryMax=16G" in command
    assert "--property=MemorySwapMax=0" in command and "--property=TasksMax=512" in command


def test_launcher_rejects_changed_spec_before_reservation_or_service(tmp_path, monkeypatch):
    value, claims, commands = launch_fixture(tmp_path, monkeypatch)
    scope.SPEC_FILE.write_text(json.dumps({**value, "cpu_affinity": [0, 1, 2, 3]}))
    with pytest.raises(ValueError, match="specification changed"):
        launcher.launch()
    assert claims == [] and commands == []
