import fcntl
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import pytest

from proworksim import software_benchmark_dispatch_v066 as original_policy
from proworksim import software_benchmark_docker_actor_v066 as original_provider
from proworksim import software_benchmark_episode_v066 as original_episode
from proworksim import software_benchmark_expansion_episode_v069 as episode
from proworksim import software_benchmark_expansion_resources_v069 as resources
from proworksim.software_benchmark_candidates_v054 import write_new

GIB = 1024**3


def fixture(tmp_path, monkeypatch):
    claims = tmp_path / "resource-claims"
    claims.mkdir()
    row = {"slot_id": "v064:fixture:DEEPSEEK_REF_B5000K:1", "slot_index": 100,
        "instance_id": "fixture", "model_key": "DEEPSEEK", "input_plus_output_tokens": 5_000_000}
    specs = {role + "-100": {"role": role, "slot_id": row["slot_id"], "instance_id": "fixture",
        "image_id": "sha256:" + "b" * 64} for role in ("actor", "controller", "volume")}
    plan_ref = write_new(tmp_path / "plan.json", {"resources": specs, "rows": [row]})
    auth = write_new(tmp_path / "primary-auth.json", {"plan": plan_ref})
    expansion_auth = write_new(tmp_path / "expansion-auth.json", {"API5M": True})
    guard_calls = []
    scope = SimpleNamespace(AUTH_FILE=Path(expansion_auth["path"]), require_allowed=lambda *args, **kwargs:
        guard_calls.append((args, kwargs)))
    monkeypatch.setattr(resources, "scope", lambda: scope)
    budget_namespace = {**original_policy.__dict__, "physical_capacity": lambda: {
        "passed": True, "memory_available_bytes": 4096 * GIB, "disk_free_bytes": 4096 * GIB}}
    raw_budget = FunctionType(original_policy._budget.__code__, budget_namespace,
        argdefs=original_policy._budget.__defaults__)
    def budget(*args):
        with (claims / "allocation.lock").open("a+b") as other:
            with pytest.raises(BlockingIOError):
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return raw_budget(*args)
    def cpu_set(role, lane=0):
        start = 4 + 6 * lane + (4 if role == "controller" else 0)
        return ",".join(map(str, range(start, start + (2 if role == "controller" else 4))))
    release_namespace = {**original_policy.__dict__, "BATCH_ROOT": tmp_path}
    release = FunctionType(original_policy.release_resource.__code__, release_namespace,
        argdefs=original_policy.release_resource.__defaults__)
    fake = SimpleNamespace(require_v066_allowed=lambda *args, **kwargs: {"plan": plan_ref},
        _cached_json=lambda ref: json.loads(Path(ref["path"]).read_bytes()),
        load=original_policy.load, _budget=budget, _write_claim=original_policy._write_claim,
        AUTHORIZATION_FILE=Path(auth["path"]), PLAN_FILE=Path(plan_ref["path"]),
        cpu_set=cpu_set, release_resource=release)
    monkeypatch.setattr(resources, "primary", fake)
    monkeypatch.setattr(resources, "BATCH_ROOT", tmp_path)
    return row, claims, guard_calls, specs


def active(claims, name, role, cpu, memory):
    path = claims / name
    path.write_text(json.dumps({"spec": {"role": role}, "reserved_cpu": cpu,
        "reserved_memory_bytes": memory, "reserved_spool_bytes": 0}))
    return path


def test_expanded_pair_uses_original_lock_shared_cpu_and_full_limits(tmp_path, monkeypatch):
    _, claims, _, _ = fixture(tmp_path, monkeypatch)
    old = [active(claims, f"active-actor-{i}.json", "actor", 6, 32 * GIB) for i in range(12)]
    before = {path: path.read_bytes() for path in old}
    actor = resources.claim_resource("actor-100")
    volume = resources.claim_resource("volume-100")
    controller = resources.claim_resource("controller-100")
    body = resources.primary.load(actor)
    assert body["lane"] == 12 and body["CPU_sharing"]["original_CPU_lane"] == 0
    assert body["reserved_cpu"] == 6 and body["reserved_memory_bytes"] == 32 * GIB
    assert body["admission"]["grader_headroom"]["missing_reserved_grader_slots"] == 2
    assert "expansion_authorization" in body and not list(claims.glob("model-*.json"))
    module = episode.provider()
    name = resources.primary.load(volume)["docker_name"]
    for role, ref, cpu, count in (("actor", actor, 4, 4), ("controller", controller, 2, 2)):
        options = module.container_options(role, ref, resources.primary.load(ref), name,
            ["/opt/pws-runtime/bin/python"], cpuset=resources.cpu_set(role, 12))
        assert options["nano_cpus"] == cpu * 10**9
        assert options["mem_limit"] == options["memswap_limit"] == 16 * GIB
        assert len(options["cpuset_cpus"].split(",")) == count
    resources.release_resource(actor, quiescent=True)
    assert (claims / "active-actor-12.json").exists()
    resources.release_resource(controller, quiescent=True)
    resources.release_resource(volume, quiescent=True)
    assert not (claims / "active-actor-12.json").exists()
    assert all(path.read_bytes() == value for path, value in before.items())


def test_two_grader_headroom_refuses_eighteenth_until_old_coordinator_drains(tmp_path, monkeypatch):
    _, claims, _, _ = fixture(tmp_path, monkeypatch)
    for lane in range(17):
        active(claims, f"active-actor-{lane}.json", "actor", 6, 32 * GIB)
    for lane in (1, 2):
        active(claims, f"active-model-{lane}.json", "model", 12, 96 * GIB)
    active(claims, "active-new-coordinator.json", "auxiliary_coordinator", 4, 16 * GIB)
    old = active(claims, "active-old-coordinator.json", "auxiliary_coordinator", 4, 16 * GIB)
    with pytest.raises(resources.ResourceBusy):
        resources.claim_resource("actor-100")
    assert not (claims / "actor-100.json").exists() and not (claims / "active-actor-17.json").exists()
    old.unlink()  # Only this isolated fixture's simulated natural drain.
    third = active(claims, "active-model-3.json", "model", 12, 96 * GIB)
    with pytest.raises(resources.ResourceBusy):
        resources.claim_resource("actor-100")
    assert not (claims / "actor-100.json").exists()
    third.unlink()
    ref = resources.claim_resource("actor-100")
    body = resources.primary.load(ref)
    assert body["lane"] == 17
    assert body["admission"]["reserved_memory_bytes_after"] == 832 * GIB
    assert body["admission"]["grader_headroom"]["cpu"] == 8


def test_existing_graders_not_reserved_twice():
    graders = [{"spec": {"role": "score"}}, {"spec": {"role": "control"}}]
    assert resources.grader_headroom(graders) == {"active_graders": 2,
        "missing_reserved_grader_slots": 0, "cpu": 0, "memory_bytes": 0}
    assert resources.grader_headroom(graders[:1])["memory_bytes"] == 16 * GIB
    assert resources.grader_headroom([])["memory_bytes"] == 32 * GIB


def test_high_budget_and_foreign_claim_rejected_before_mutation(tmp_path, monkeypatch):
    _, claims, _, _ = fixture(tmp_path, monkeypatch)
    data = json.loads(resources.primary.PLAN_FILE.read_bytes())
    data["rows"][0]["input_plus_output_tokens"] = 7_500_000
    resources.primary.PLAN_FILE.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="DeepSeek 5M"):
        resources.claim_resource("actor-100")
    assert not (claims / "actor-100.json").exists()
    foreign = write_new(claims / "actor-999.json", {"version": resources.VERSION, "key": "actor-999",
        "spec": {"role": "actor", "slot_id": "foreign"}, "lane": 0})
    with pytest.raises(ValueError, match="Foreign"):
        resources.release_resource(foreign, quiescent=True)
    assert not (claims / "actor-999.released.json").exists()


def test_private_namespaces_leave_original_policy_and_code_unchanged():
    actor_policy, episode_policy = original_provider.policy, original_episode.policy
    own_pair = episode.provider().OwnedActorPair
    private = episode.episode()
    assert own_pair._claim.__globals__["policy"] is resources
    assert private._run.__globals__["policy"] is resources
    assert private._run.__globals__["OwnedActorPair"] is own_pair
    assert private._run.__code__ is original_episode._run.__code__
    assert original_provider.policy is actor_policy and original_episode.policy is episode_policy
    assert original_provider.OwnedActorPair._claim.__globals__["policy"] is actor_policy
    assert resources.CONSTRAINTS["maximum_combined_reserved_cpu"] == 152
    assert resources.CONSTRAINTS["maximum_combined_reserved_memory_bytes"] == 832 * GIB


def test_expired_pair_still_requires_owned_drain_guard_for_cleanup(tmp_path, monkeypatch):
    row, claims, guards, _ = fixture(tmp_path, monkeypatch)
    claim = resources.claim_resource("actor-100")
    pair = episode.provider().OwnedActorPair(SimpleNamespace(), slot_index=100,
        slot_id=row["slot_id"], instance_id=row["instance_id"], deadline=-1, actor_reservation=claim)
    with pytest.raises(TimeoutError):
        pair.create_volume()
    result = pair.cleanup()
    assert result["quiescent"] is True and result["proven_uncreated_claim_roles"] == ["actor"]
    assert not (claims / "active-actor-0.json").exists()
    assert any(args[0] == "v069.drain" and kwargs["slot_id"] == row["slot_id"] for args, kwargs in guards)
