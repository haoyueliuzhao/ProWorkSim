import importlib.util
from pathlib import Path

import pytest

from proworksim import software_benchmark_dispatch_v066 as policy
from proworksim import software_benchmark_docker_actor_v066 as actor
from proworksim import software_benchmark_model_capacity_v066 as capacity
from proworksim import software_benchmark_ref_resident_v066 as resident
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def claims(tmp_path, monkeypatch):
    monkeypatch.setattr(policy, "BATCH_ROOT", tmp_path)
    auth = tmp_path / "authorization.json"
    auth.write_text("{}")
    monkeypatch.setattr(policy, "AUTHORIZATION_FILE", auth)
    resources = {}
    for index in range(1, 13):
        for role in ("actor", "controller", "volume", "score"):
            resources[f"{role}-{index}"] = {"role": role, "slot_id": f"slot-{index}"}
    for index in range(6):
        resources[f"model-{index}"] = {"role": "model", "model_index": index}
    plan = write_new(tmp_path / "plan.json", {"resources": resources})
    monkeypatch.setattr(policy, "require_v066_allowed", lambda *_: {"plan": plan})
    monkeypatch.setattr(policy, "physical_capacity", lambda: {
        "passed": True, "memory_available_bytes": 2048 * policy.GIB,
        "disk_free_bytes": 2048 * policy.GIB})
    return tmp_path / "resource-claims"


def test_real_pair_claim_reserves_both_16_gib_containers_once(claims):
    ref = policy.claim_resource("actor-1")
    value = policy.load(ref)
    assert value["reserved_memory_bytes"] == sum(role[1] for role in actor.ROLES.values()) == 32 * policy.GIB
    assert value["reserved_cpu"] == sum(role[0] for role in actor.ROLES.values()) == 6
    controller = policy.load(policy.claim_resource("controller-1"))
    assert controller["reserved_memory_bytes"] == controller["reserved_cpu"] == 0
    policy.release_resource(ref, quiescent=True)
    assert Path(value["lease"]).exists(), "Live controller must retain the whole pair reservation"


def test_six_models_six_pairs_two_graders_fit_but_seventh_pair_does_not(claims):
    for index in range(6):
        policy.reserve_model(index)
    for index in range(1, 7):
        policy.claim_resource(f"actor-{index}")
    for index in (1, 2):
        policy.claim_resource(f"score-{index}")
    active = [policy.load(policy.reference(path)) for path in claims.glob("active-*.json")]
    assert 16 * policy.GIB + sum(item["reserved_memory_bytes"] for item in active) == 816 * policy.GIB
    assert 4 + sum(item["reserved_cpu"] for item in active) == 120
    with pytest.raises(policy.ResourceBusy, match="Combined"):
        policy.claim_resource("actor-7")
    assert not (claims / "actor-7.json").exists()


def test_excluded_old_slot_cannot_consume_actor_or_score_identity(claims):
    for key in ("actor-0", "controller-0", "volume-0", "score-0"):
        with pytest.raises(ValueError, match="Unplanned"):
            policy.claim_resource(key)
        assert not (claims / (key + ".json")).exists()


def test_real_continuation_plan_excludes_old_model_entered_results():
    plan = policy.load(policy.reference(policy.PLAN_FILE))
    inventory = policy.load(policy.reference(policy.RESUME_FILE))
    allowed = set(inventory["allowed_generation_slot_ids"])
    assert len(allowed) == 5937 and plan["remaining_generation_slots"] == 5937
    assert plan["resource_role_counts"]["control"] == 776
    assert plan["resource_role_counts"]["actor"] == 5941
    for row in plan["rows"]:
        assert (f"actor-{row['slot_index']}" in plan["resources"]) == (row["slot_id"] in allowed)
        assert (f"score-{row['slot_index']}" in plan["resources"]) == (row["slot_id"] in allowed)
    assert plan["resources"]["diagnostic-2-actor"]["slot_id"] == plan["rows"][27]["slot_id"]
    assert plan["resources"]["diagnostic-4-actor"]["slot_id"] == plan["rows"][27]["slot_id"]


def test_new_controller_options_keep_isolation_and_reject_old_owned_volume():
    claim = {"key": "controller-27", "docker_name": "pws-v066-fixture",
             "spec": {"role": "controller", "image_id": "sha256:" + "1" * 64}}
    ref = {"sha256": "2" * 64}
    argv = [actor.RUNTIME + "/bin/python", "controller.py"]
    options = actor.container_options("controller", ref, claim, "pws-v066-volume", argv, cpuset="8,9")
    assert options["mem_limit"] == options["memswap_limit"] == 16 * policy.GIB
    assert options["nano_cpus"] == 2 * 10**9
    assert options["mounts"][0]["ReadOnly"] is True
    assert options["network_mode"] == "none" and options["cap_drop"] == ["ALL"]
    assert options["cap_add"] == [] and options["privileged"] is False
    with pytest.raises(ValueError, match="explicitly owned"):
        actor.container_options("controller", ref, claim, "pws-v064-old", argv)


def test_capacity_qualification_cannot_reuse_old_resident_or_reduce_context():
    root = policy.BATCH_ROOT / "residents/model-0"
    spec = {"index": 0, "root": str(root), "port": 18210,
        "endpoint": "http://127.0.0.1:18210", "api_key_file": str(root / "api-key.private"),
        "model_revision": capacity.MODEL_REVISION, "model_manifest": {"sha256": capacity.MANIFEST_SHA},
        "server_arguments": resident.server_arguments(18210)}
    assert capacity.validate_spec(spec) == root.resolve()
    with pytest.raises(ValueError, match="exact raw"):
        capacity.validate_spec({**spec, "root": str(policy.PREDECESSOR_ROOT / "residents/model-0")})
    with pytest.raises(ValueError, match="complete declared context"):
        capacity.parse_capacity(b"GPU KV cache size: 131071 tokens, Maximum concurrency for 131072 tokens per request: 1.00x", b"")
    assert capacity.parse_capacity(b"GPU KV cache size: 131072 tokens, Maximum concurrency for 131072 tokens per request: 1.00x", b"")["single_full_context_capacity_passed"]


def test_only_new_user_unit_names_can_be_launched(monkeypatch):
    spec = importlib.util.spec_from_file_location("v066_launcher_scope", ROOT / "tools/launch_full_benchmark_v066.py")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    monkeypatch.setattr(launcher.policy, "cpu_set", lambda *_: "0,1,2,3")
    value = {"unit": launcher.UNIT, "user_id": launcher.os.getuid(), "cpu_affinity": [0, 1, 2, 3],
        "source": reference(launcher.__file__), "ownership_token": "fixture"}
    command = launcher.command(value)
    assert "--unit=proworksim-v066-continuation.service" in command
    assert "--property=MemoryMax=16G" in command and "--property=CPUQuota=400%" in command
    assert resident.unit_name(0) == "proworksim-v066-model-0.service"
    assert resident.RPC_ROOT == ROOT / "runs/g66c1"
    assert not any(word in command for word in ("sudo", "mount", "umount", "unshare"))
    with pytest.raises(ValueError, match="ownership"):
        launcher.command({**value, "unit": "proworksim-v064-full-verified.service"})


def test_preparation_reports_only_new_inventory_and_imports_new_qualification_refs(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("v066_preparation_scope", ROOT / "tools/run_full_benchmark_v066.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from proworksim import software_benchmark_deepseek_runtime_v066 as api
    plan = policy.load(policy.reference(policy.PLAN_FILE))
    inventory = policy.load(policy.reference(policy.RESUME_FILE))
    wrappers = {task: {**ref, "path": str(tmp_path / (task + ".json"))}
                for task, ref in inventory["old_qualified"].items()}
    write_new(tmp_path / "control-plan.json", {"historical_reuses": wrappers})

    class Grading:
        def prepare_manifest(self):
            return None

        def prepare_controls(self):
            return ["already-prepared-controls"]

    monkeypatch.setattr(module, "RUN_ROOT", tmp_path)
    monkeypatch.setattr(module.policy, "create_plan", lambda: plan)
    monkeypatch.setattr(module.policy, "sources", lambda: [])
    monkeypatch.setattr(module, "grading_module", Grading)
    monkeypatch.setattr(module, "prepare_disk_boundary", lambda: {})
    monkeypatch.setattr(api, "prepare_schema_inventory", lambda: {})
    prepared = module.load(module.prepare())
    assert prepared["new_generation_rows"] == inventory["allowed_generation_slot_indices"]
    assert len(prepared["planned_panel_rows"]) == 6000
    assert prepared["new_generation_token_upper_bound"] < prepared["original_full_panel_token_upper_bound"] == 45000000000
    assert sum(item["status"] == "not_qualified" for item in prepared["reused_qualifications"].values()) == 3
    for task, ref in wrappers.items():
        assert prepared["reused_qualifications"][task]["qualification"] == ref
