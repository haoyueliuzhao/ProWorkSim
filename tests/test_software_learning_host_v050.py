"""Finite v050 orchestration and missing-value controls; no GPU/model work."""
import copy
import json

import pytest

from proworksim import software_organization_measurement_v050 as measured
from proworksim import software_organization_runtime_v049 as old_runtime
from proworksim import software_organization_runtime_v050 as runtime
from proworksim.software_organization_v050 import build_software_collaboration_case, case_spec, CASE_IDS
from scripts import software_learning_v050 as host
from scripts import software_learning_supervisor_v050 as supervisor
from scripts import software_learning_reporting_v050 as reporting
from scripts.run_ne_v021 import write
from test_software_organization_measurement_v049 import stop_fixture, seal_guard
from test_software_organization_runtime_v049 import sdk_owner
from proworksim.software_context_v048 import SoftwareContextTransport
from test_software_organization_runtime_v038 import action


def plan():
    return {"inventory": json.loads(host.DESIGN.read_text())}


def states():
    return supervisor.initial_states(plan())


def completed(values, names):
    for name in names:
        values[name].update(status="complete", attempted=True)
    return values


def test_full_inventory_and_shards_match_frozen_design():
    current = plan()
    host.validate_inventory(current["inventory"])
    units = reporting.inventory(current)
    assert len(units) == len({u["slot_id"] for u in units}) == 56
    for name in host.COLLECTION:
        assert [u["slot_id"] for u in host.worker_units(current, name)] == current["inventory"]["collection_shards"][name]
    for branch in host.BRANCHES:
        for shard in (0, 1):
            assert [u["unit_id"] for u in host.worker_units(current, f"dev-{branch}-{shard}")] == current["inventory"]["development_shards"][str(shard)]


def test_dependencies_require_all24_then_cpu_support_then_actual_B_direction():
    value = states()
    assert supervisor.eligible_workers(value) == ["s_star"]
    completed(value, ["s_star"])
    assert supervisor.eligible_workers(value) == list(host.COLLECTION)
    completed(value, host.COLLECTION[:2])
    assert supervisor.eligible_workers(value, {"run_B50": True}) == [host.COLLECTION[2]]
    completed(value, host.COLLECTION[2:])
    assert supervisor.eligible_workers(value) == []
    assert supervisor.eligible_workers(value, {"run_B50": True}) == ["update-B"]
    completed(value, ["update-B"])
    assert supervisor.eligible_workers(value, {"run_B50": True}) == []
    direction = {"selected": True, "reliable_base_material": True}
    assert supervisor.eligible_workers(value, {"run_B50": True}, direction) == ["update-Q_plus", "update-Q_minus", "dev-S_star-0", "dev-S_star-1", "dev-B-0", "dev-B-1"]
    completed(value, ["update-Q_plus"])
    assert "dev-Q_plus-0" in supervisor.eligible_workers(value, {"run_B50": True}, direction)
    assert "dev-Q_minus-0" not in supervisor.eligible_workers(value, {"run_B50": True}, direction)


def test_no_support_disables_all_training_and_development_without_erasing_collection():
    value = completed(states(), ["s_star", *host.COLLECTION])
    disabled = supervisor.apply_support_gate(value, {"run_B50": False})
    assert disabled == [*host.UPDATES, *host.DEVELOPMENT]
    assert all(value[name]["attempted"] is False for name in disabled)
    assert supervisor.eligible_workers(value, {"run_B50": False}) == []
    assert all(value[name]["status"] == "complete" for name in host.COLLECTION)


def test_gradient_degenerate_allows_only_Sstar_B_development():
    value = completed(states(), ["s_star", *host.COLLECTION, "update-B"])
    direction = {"selected": False, "reliable_base_material": True}
    supervisor.apply_not_applicable(value, direction)
    assert supervisor.eligible_workers(value, {"run_B50": True}, direction) == ["dev-S_star-0", "dev-S_star-1", "dev-B-0", "dev-B-1"]


@pytest.mark.parametrize("gate", [{}, {"run_B50": None}, {"run_B50": 1}])
def test_ambiguous_support_does_not_release_or_end_inventory(gate):
    value = completed(states(), ["s_star", *host.COLLECTION])
    with pytest.raises(ValueError):
        supervisor.apply_support_gate(value, gate)


def test_conditional_gate_cannot_hide_attempted_update():
    value = completed(states(), ["s_star", *host.COLLECTION])
    value["update-B"].update(status="stopped", attempted=True)
    with pytest.raises(ValueError):
        supervisor.apply_support_gate(value, {"run_B50": False})


@pytest.mark.parametrize("kind,elapsed,expected", [("episode", 6000, "episode_hard_deadline"), ("training_step", 900, "single_task_budget"), ("boundary", 600, "single_task_budget"), ("loading", 900, "single_task_budget")])
def test_original_task_resource_bounds_retained(kind, elapsed, expected):
    assert supervisor.task_stop_reason({"kind": kind, "started_at": 0}, now=elapsed, rss_bytes=0) == expected


def test_training_has_separate48h_cap_not_episode6000():
    value = {"started_at": 10, "ended_at": None, "maximum_seconds": 172800}
    assert supervisor.training_stop_reason("update-B", value, now=6010) is None
    assert supervisor.training_stop_reason("update-B", value, now=172810) == "training_compute_budget"
    assert supervisor.training_stop_reason("collect-0", value, now=172810) is None
    value["ended_at"] = 5000
    assert supervisor.training_stop_reason("update-B", value, now=172810) is None
    assert supervisor.training_stop_reason("update-B", {}, now=50) == "training_compute_budget_unbound"


def test_gpu_scope_is_all_eight_but_same_memory_and_parallel_guards():
    assert host.GPU_ORDER == tuple(range(8))
    assert host.LIMITS["minimum_free_gpu_mib"] == 57344
    assert host.LIMITS["gpu_capacity_stability_seconds"] == 60
    assert host.LIMITS["max_parallel_model_instances"] == 3
    for gpu in host.GPU_ORDER:
        env = supervisor.worker_env({"runtime_dependency_path": "/fixture"}, gpu)
        assert env["CUDA_VISIBLE_DEVICES"] == str(gpu)
    assert host.LIMITS["max_forward_calls_per_update"] == 2 * 3072 + 6


@pytest.mark.parametrize("missing", [False, True])
def test_reporting_compares_Sstar_and_keeps_missing_pair_null(missing):
    units = reporting.inventory(plan())
    rows = []
    for unit in units:
        result = 0 if unit["phase"] == "development" and unit["branch"] == "S_star" else 1
        rows.append({**unit, "status": "closed", "R_joint": result, "Q_joint": result,
            "R_token": result, "Q_token": result, "cost": {"known_actual_tokens": 1, "complete_actual_tokens": 1}})
    if missing:
        rows[24 + 8].update(status="technical_unknown", R_joint=None, Q_joint=None)
        rows[24 + 8]["cost"]["complete_actual_tokens"] = None
    out = reporting.aggregate_rows(units, rows, {"selected": True, "epsilon": .1})
    assert out["contrasts"]["B_minus_S_star"] == (None if missing else 1)
    assert out["branches"]["B"]["metrics"]["R_joint"]["planned_denominator"] == 8
    assert out["finite_difference"] == 0
    assert out["generation"]["complete_actual_tokens"] == (None if missing else 56)


def test_frozen_owner_policy_class_is_original_and_new_metadata_is_strict():
    assert runtime.worker_type is old_runtime.worker_type
    data = stop_fixture()
    data["row"]["version"] = runtime.VERSION
    data["evidence"]["version"] = runtime.VERSION
    data["feedback"]["version"] = measured.VERSION
    data["feedback"]["capacity_binding"]["version"] = "v050-original-loaded-state-capacity-binding"
    assert measured.assess_records(**data)["decision"] == "continue"
    data["row"]["version"] = old_runtime.VERSION
    assert measured.assess_records(**data)["decision"] == "global_pause"


@pytest.mark.parametrize("development", [False, True])
def test_new_window_native_sdk_retains_same_O1_and_mechanical_route(tmp_path, monkeypatch, development):
    owner = sdk_owner({"member_001": [action("staff_done", reason="Current work done")],
        "member_002": [action("send_message", recipient="member_001", task_id="root_goal", body="Real new request")]})
    seal_guard(owner)
    monkeypatch.setattr(runtime, "_capture_slot_guard", lambda current: copy.deepcopy(current.learning))
    from proworksim.software_organization_tasks_v050 import DEVELOPMENT_CASE_IDS
    case_id = DEVELOPMENT_CASE_IDS[-1] if development else CASE_IDS[0]
    prepared = build_software_collaboration_case(case_spec(case_id), tmp_path / "prepared")
    if not development:
        owner.begin_window("v050-o1-learning-window-01")
    folder = tmp_path / "slot"
    row = runtime.collect_episode(owner, prepared, folder, sampling_seed=50, slot_id="v050-cpu-fixture",
        manage_owner_window=development, transport_factory=SoftwareContextTransport,
        learning_binding={"branch": "S_star", "explicit_cpu_fixture": True})
    proof = measured.measure_slot(row)
    assert proof["decision"] == "continue", proof
    assert row["version"] == runtime.VERSION
    assert row["online_window_id"] == ("organization-v050:v050-cpu-fixture" if development else "v050-o1-learning-window-01")
    assert row["episode_start_steps"] == {"actor_steps": 4, "critic_steps": 4, "policy_revision": 4}
    assert row["R"] == 0 and row["usage"]["attempts"] > 0
    assert row["member_lifecycle"]["live_at_end"] == 2


def test_loaded_branch_steps_allow_original_zero_signal_boundary(tmp_path, monkeypatch):
    from types import SimpleNamespace
    root = tmp_path / "run"
    checkpoint = {"actor_identity": {"x": 1}, "actor_steps": 4, "critic_steps": 5}
    write(root / "plan.json", {})
    write(root / "update-B/actual/checkpoint/checkpoint.json", checkpoint)
    owner = SimpleNamespace(actor_steps=4, critic_steps=5,
        restore_checkpoint=lambda folder: checkpoint, freeze_identity=lambda: {"x": 1})
    assert host._restored_state(owner, root, "B", tmp_path / "out") == checkpoint
    owner.critic_steps = 6
    with pytest.raises(ValueError):
        host._restored_state(owner, root, "B", tmp_path / "bad")


def test_forward_cap_blocks_next_native_dispatch_and_restores_original_callable(tmp_path):
    from types import SimpleNamespace
    calls = []
    def original_call(value):
        calls.append(value)
        return value
    owner = SimpleNamespace(learning_logprobs=original_call, torch=SimpleNamespace(is_grad_enabled=lambda: True))
    write(tmp_path / "training-compute.json", {"forward_upper": 2})
    with host.training_progress(owner, tmp_path):
        assert owner.learning_logprobs("first") == "first"
        assert owner.learning_logprobs("second") == "second"
        with pytest.raises(RuntimeError, match="before another dispatch"):
            owner.learning_logprobs("third")
    assert calls == ["first", "second"] and owner.learning_logprobs is original_call
    receipt = json.loads((tmp_path / "training-compute.json").read_text())
    assert receipt["native_forward_started"] == receipt["native_forward_completed"] == 2
    assert receipt["native_gradient_forward_started"] == 2 and receipt["native_no_grad_forward_started"] == 0


def test_actual_admission_list_shape_reaches_cpu_gate_and_freezes_compute(tmp_path, monkeypatch):
    from proworksim import software_learning_v050 as learning
    from proworksim import software_allocation_v050 as allocation
    admission = {"decisions": [{"call_id": "a"}, {"call_id": "b"}], "scheduled_slots": 24}
    monkeypatch.setattr(host, "frozen", lambda root: {"source": {}, "inventory": {}, "s_star_recipe": {}})
    monkeypatch.setattr(host, "materialize_entries", lambda *a: ([{"slot_id": "fixture"}], []))
    monkeypatch.setattr(learning, "prepare_training_admission", lambda *a: admission)
    monkeypatch.setattr(allocation, "build_support_report", lambda *a, **k: {"fixture": True})
    monkeypatch.setattr(allocation, "pretraining_support_gate", lambda *a: {"run_B50": False})
    write(tmp_path / "declaration.json", {})
    gate = host.run_support_gate(tmp_path)
    assert gate["run_B50"] is False
    assert json.loads((tmp_path / "pretraining-admission.json").read_text()) == admission
    compute = host.training_compute_receipt(admission, started_at=3)
    assert compute["admitted_rows"] == compute["actor_backward_upper"] == compute["critic_backward_upper"] == 2
    assert compute["forward_upper"] == 10 and compute["started_at"] == 3
    with pytest.raises(ValueError):
        host.training_compute_receipt({"decisions": [{}] * 3073})


def test_every_new_material_is_source_frozen_and_mutation_rejects_launch(tmp_path, monkeypatch):
    from scripts.run_ne_v021 import reference
    real_source = host.SOURCE
    real_design = json.loads(host.DESIGN.read_text())
    assets = [p for p in (real_source / "examples/software-learning-v050").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    assert len(assets) >= 22
    for p in assets:
        destination = tmp_path / p.relative_to(real_source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(p.read_bytes())
    monkeypatch.setattr(host, "SOURCE", tmp_path)
    monkeypatch.setattr(host, "DESIGN", tmp_path / "docs/experiments/software-learning-v050-design.json")
    monkeypatch.setattr(host, "CONTROLS", tmp_path / "docs/experiments/software-learning-v050-cpu-controls.json")
    monkeypatch.setattr(host.original, "source_files", lambda: {})
    write(host.DESIGN, real_design)
    write(host.CONTROLS, {})
    for relative in ("docs/experiments/software-learning-v050-protocol.md", "docs/reference/audit-v049-next-v050.md"):
        p = tmp_path / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("fixture source")
    before = host.source_files()
    assert all(str(p.relative_to(real_source)) in before for p in assets)
    frozen = host.seal({"version": host.VERSION, "source": {}, "source_files": before,
        "design": reference(host.DESIGN), "limits": host.LIMITS, "workers": list(host.WORKERS),
        "gpu_preference": list(host.GPU_ORDER), "inventory": real_design}, "plan_sha256")
    write(tmp_path / "plan.json", frozen)
    monkeypatch.setattr(host, "code_identity", lambda: {})
    victim = tmp_path / assets[0].relative_to(real_source)
    victim.write_bytes(victim.read_bytes() + b"\n")
    assert host.source_files() != before
    with pytest.raises(ValueError, match="Frozen v050"):
        host.frozen(tmp_path)


def test_host_support_gate_uses_full_24slot_actual_cpu_admission_and_support(tmp_path, monkeypatch):
    from test_software_learning_v050 import fixture
    entries, declaration, recipe, design, admission, support = fixture(residual=True)
    monkeypatch.setattr(host, "frozen", lambda root: {"source": {}, "inventory": design, "s_star_recipe": recipe})
    monkeypatch.setattr(host, "materialize_entries", lambda *a: (entries, []))
    write(tmp_path / "declaration.json", declaration)
    gate = host.run_support_gate(tmp_path)
    assert gate["run_B50"] is True
    assert json.loads((tmp_path / "pretraining-admission.json").read_text()) == admission
    assert json.loads((tmp_path / "support-before-training.json").read_text()) == support
    compute = host.training_compute_receipt(admission, started_at=3)
    assert compute["admitted_rows"] == 72 and compute["forward_upper"] == 150
    assert support["global_member_denominator_factor"] == 48
