"""CPU fixtures for actual-gate binding and unchanged work budgets; no model work."""

import copy
from pathlib import Path

import pytest

from proworksim.harness_learning_admission import (
    OPTIMIZATION_CHECKS,
    OPTIMIZATION_VERSION,
    validate_h2_launch,
    validate_optimization_admission,
)
from proworksim.storage import json_bytes, read_json
from scripts.build_harness_learning_v018 import build_protocols as previous_protocols
from scripts.build_harness_learning_v019 import build_protocols, optimized_profile, support_protocol
from scripts.build_harness_study_v016 import ref
from scripts.continue_harness_v017 import make_jobs, release_projects_after_learning
from scripts.retail_project_model_v017 import validate_binding
from test_candidate_selection_v015 import guard
from test_retail_project_model_v017 import fixture as selected_fixture

SOURCE = {"code_commit": "c" * 40, "code_dirty": False, "source_tree_sha256": "s" * 64}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))
    return ref(path)


def actual_gate_fixture(tmp_path, h1, manifest, monkeypatch):
    # These are artificial saved metadata, never an actual performance admission.
    monkeypatch.setattr("proworksim.audit.code_identity", lambda: copy.deepcopy(SOURCE))
    evidence = save(tmp_path / "gate-evidence.json", {"fixture_only": True})
    candidate = {"passed": True, "runtime_profile": optimized_profile(h1),
                 "weight_manifest_sha256": ref(manifest)["sha256"],
                 "checks": {k: {"passed": True, "evidence": evidence} for k in OPTIMIZATION_CHECKS}}
    report = {"version": OPTIMIZATION_VERSION, "execution_source_commit": SOURCE["code_commit"],
              "candidates": {h1["candidate_id"]: candidate}}
    path = tmp_path / "optimization.json"
    save(path, report)
    return path, report


def h2_fixture(tmp_path):
    h1root = tmp_path / "h1"
    h1 = read_json(Path(__file__).resolve().parents[1] / "examples/harness-v17/h1-plan/h1-qwen35-9b.json")
    manifest = tmp_path / "base/manifest.json"
    save(manifest, {"fixture_only": True})
    protocol_ref = save(h1root / "launch-protocol.json", h1)
    save(h1root / "resident/owner.json", {"base_identity": {"path": str(manifest.parent), "manifest": ref(manifest)}})
    save(h1root / "online/report.json", {"status": "complete", "actor_steps_total": 0,
         "critic_steps_total": 0, "windows": [{"evaluation_guard": guard()}]})
    choice = {"candidate_id": h1["candidate_id"], "harness": "native_v15", "run_root": str(h1root),
              "protocol_ref": protocol_ref, "initial_actor_identity": {"adapter_sha256": "fixture"}}
    chosen = {"status": "selected", "selected": choice}
    models = [{"candidate_id": c, "ended": True, "references": {"launch": save(tmp_path / (c + "-launch.json"), {"end": 1., "exit_code": 0})}}
              for c in ("qwen35-9b", "qwen38-27b")]
    comparison = save(tmp_path / "comparison.json", {"models": models, "selection": chosen})
    selection = save(tmp_path / "selection.json", {**chosen, "report_ref": comparison})
    return h1, manifest, selection, choice


def test_optimized_plans_preserve_all_work_slots_and_density_is_serial(tmp_path, monkeypatch):
    h1, manifest, selection, _ = h2_fixture(tmp_path)
    path, _ = actual_gate_fixture(tmp_path, h1, manifest, monkeypatch)
    old = previous_protocols(h1, "native_v15", selection)
    migration, pilot = new = build_protocols(h1, "native_v15", selection, ref(path))
    for original, updated in zip(old, new, strict=True):
        assert updated["recipe"] == original["recipe"]
        assert [w["slots"] for w in updated["windows"]] == [w["slots"] for w in original["windows"]]
        assert updated["runtime"]["profile"] == optimized_profile(h1)
        assert updated["optimization_admission"] == ref(path)
        assert updated["collector"] == "proworksim.harness_parallel_v019:collect_window"
        assert all(w["parallel_collection"] == updated["parallel_collection"] for w in updated["windows"])
        for w in updated["windows"]:
            count = len(w["slots"])
            assert ((count - 1) + 1 - count) % 2 == 0  # final logical slot is parent
    assert sum(len(w["slots"]) for w in migration["windows"]) == 8
    assert sum(len(w["slots"]) for w in pilot["windows"]) == 118
    assert pilot["primary_evaluation"]["task_weights"] == dict.fromkeys(("implement", "review", "pair", "chain"), .25)
    density = support_protocol(h1, "native_v15", selection, ref(path))
    assert density["collector"] == "proworksim.harness_collection:collect_window"
    assert len(density["windows"]) == 1 and len(density["windows"][0]["slots"]) == 16
    assert "parallel_collection" not in density and "parallel_collection" not in density["windows"][0]
    assert density["method_support_density"]["auto_O4"] is False


def test_optimization_gate_requires_actual_bound_candidate_profile_source_and_each_evidence(tmp_path, monkeypatch):
    h1, manifest, _, _ = h2_fixture(tmp_path)
    path, original = actual_gate_fixture(tmp_path, h1, manifest, monkeypatch)
    kwargs = {"candidate_id": h1["candidate_id"], "runtime_profile": optimized_profile(h1), "weight_manifest": manifest}
    assert validate_optimization_admission(ref(path), **kwargs)["status"] == "admitted"
    edits = [
        (lambda j: j.update(execution_source_commit="other-source"), "frozen execution source"),
        (lambda j: j["candidates"][h1["candidate_id"]].update(passed=False), "has not passed"),
        (lambda j: j["candidates"][h1["candidate_id"]].update(weight_manifest_sha256="other-base"), "base weights"),
        (lambda j: j["candidates"][h1["candidate_id"]]["runtime_profile"]["prefix_cache"].update(prefix_tokens=4096), "profile differs"),
    ]
    edits.extend((lambda j, check=k: j["candidates"][h1["candidate_id"]]["checks"][check].update(passed=False), "check did not pass") for k in OPTIMIZATION_CHECKS)
    for change, expected in edits:
        current = copy.deepcopy(original)
        change(current)
        save(path, current)
        with pytest.raises(ValueError, match=expected):
            validate_optimization_admission(ref(path), **kwargs)
    save(path, original)
    bound = ref(path)
    save(path, {**original, "changed_after_binding": True})
    with pytest.raises(ValueError, match="evidence bytes changed"):
        validate_optimization_admission(bound, **kwargs)
    save(path, original)
    monkeypatch.setattr("proworksim.audit.code_identity", lambda: {**SOURCE, "code_dirty": True})
    with pytest.raises(ValueError, match="clean frozen"):
        validate_optimization_admission(ref(path), **kwargs)
    monkeypatch.setattr("proworksim.audit.code_identity", lambda: SOURCE)
    save(tmp_path / "gate-evidence.json", {"changed_evidence": True})
    with pytest.raises(ValueError, match="evidence bytes changed"):
        validate_optimization_admission(ref(path), **kwargs)


def test_h2_cannot_bypass_optimization_or_start_unmeasured_pilot(tmp_path, monkeypatch):
    h1, manifest, selection, _ = h2_fixture(tmp_path)
    path, _ = actual_gate_fixture(tmp_path, h1, manifest, monkeypatch)
    migration, pilot = build_protocols(h1, "native_v15", selection, ref(path))
    kwargs = {"model_path": manifest.parent, "weight_manifest": manifest}
    assert validate_h2_launch(migration, **kwargs)["optimization"]["status"] == "admitted"
    with pytest.raises(ValueError, match="fresh after migration"):
        validate_h2_launch(migration, **kwargs, restore_checkpoint="old")
    with pytest.raises(ValueError, match="waits for an actual"):
        validate_h2_launch(pilot, **kwargs)
    altered = copy.deepcopy(migration)
    del altered["optimization_admission"]
    with pytest.raises(ValueError, match="immutable file reference"):
        validate_h2_launch(altered, **kwargs)
    altered = copy.deepcopy(migration)
    altered["windows"][0]["slots"][0]["sampling_seed"] += 1
    with pytest.raises(ValueError, match="worlds or budgets differ"):
        validate_h2_launch(altered, **kwargs)
    altered = copy.deepcopy(migration)
    altered["stage"] = "not-a-gated-stage"
    with pytest.raises(ValueError, match="explicitly gated"):
        validate_h2_launch(altered, **kwargs)
    density = support_protocol(h1, "native_v15", selection, ref(path))
    with pytest.raises(ValueError, match="Support density waits"):
        validate_h2_launch(density, **kwargs)


def test_projects_require_same_actual_optimization_and_original_placement(tmp_path, monkeypatch):
    selection, report, kwargs = selected_fixture(tmp_path)
    h1 = read_json(Path(report["models"][0]["references"]["protocol"]["path"]))
    gate, body = actual_gate_fixture(tmp_path, h1, kwargs["weight_manifest"], monkeypatch)
    binding = validate_binding(selection, **kwargs, optimization_admission=gate)
    assert binding["runtime_kind"] == "qwen_hybrid_optimized"
    assert binding["profile"] == optimized_profile(h1)
    assert binding["optimization"]["optimization_admission"] == ref(gate)
    override = tmp_path / "override.json"
    save(override, h1["runtime"]["profile"])
    with pytest.raises(ValueError, match="benchmarked original placement"):
        validate_binding(selection, **kwargs, optimization_admission=gate, runtime_profile=override, placement_reason="fixture")
    body["candidates"][h1["candidate_id"]]["passed"] = False
    save(gate, body)
    with pytest.raises(ValueError, match="has not passed"):
        validate_binding(selection, **kwargs, optimization_admission=gate)


@pytest.mark.parametrize("candidate,width", [("qwen35-9b", 2), ("qwen38-27b", 4)])
def test_replica_resources_are_checked_together_and_projects_wait_for_learning(tmp_path, candidate, width):
    h1, manifest, selection, choice = h2_fixture(tmp_path)
    h1["candidate_id"] = candidate
    h1["runtime"]["profile"]["devices"] = width
    choice.update(candidate_id=candidate, protocol_ref=save(tmp_path / "h1/launch-protocol.json", h1))
    optimization = save(tmp_path / "gate.json", {"fixture_only": True})
    jobs, _, _ = make_jobs({"python": "fixture-python", "source": str(tmp_path), "optimization_admission": optimization},
                           choice, Path(selection["path"]), tmp_path / "new-output")
    for name in ("migration", "pilot"):
        assert jobs[name]["gpus"] == list(range(width))
        assert jobs[name]["replica_gpus"] == list(range(width, 2 * width))
        assert jobs[name]["required_gpus"] == list(range(2 * width))
    projects = jobs["projects"]
    assert projects["gpus"] == list(range(width)) and not projects["replica_gpus"]
    assert projects["status"] == "blocked_on_learning"
    assert "--optimization-admission" in projects["command"]
    assert release_projects_after_learning(jobs) is False
    jobs["migration"]["status"] = "complete"
    jobs["pilot"]["status"] = "running"
    assert release_projects_after_learning(jobs) is False
    jobs["pilot"]["status"] = "failed_or_incomplete"
    assert release_projects_after_learning(jobs) is True
    assert projects["status"] == "waiting_resources"
    assert projects["learning_terminal_before_project_launch"]["pilot"] == "failed_or_incomplete"
