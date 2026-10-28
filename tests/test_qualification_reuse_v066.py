import importlib.util
import json
from pathlib import Path

import pytest

from proworksim import software_benchmark_qualification_reuse_v066 as reuse
from proworksim import software_benchmark_scorer_v064 as old_scorer
from proworksim import software_benchmark_scorer_v066 as scorer
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("v066_grading_test", ROOT / "tools/run_capability_grading_v066.py")
grading = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grading)


def test_actual_five_components_preserve_official_and_environment_logic():
    for component in reuse.COMPONENTS:
        base = ROOT / "src/proworksim" / ("software_benchmark_" + component)
        old, new = (Path(str(base) + f"_v{version}.py").read_text() for version in ("064", "066"))
        assert reuse.compare_sources(old, new, scorer=component == "scorer")
    with pytest.raises(ValueError, match="differs beyond"):
        reuse.compare_sources("def score(): return True", "def score(): return False", scorer=True)
    with pytest.raises(ValueError, match="differs beyond"):
        reuse.compare_sources("TIMEOUT = 1800", "TIMEOUT = 3600")


def manifest_fixture(tmp_path):
    old = {"version": "v064-offline-capability-official-scorer-r1", "limits": {"timeout_seconds": 1800},
        "parent": {"official_version": "5.0.2"}, "diagnostic_upstream_sha256": "unchanged"}
    new = {**old, "version": "v066-offline-capability-official-scorer-r1"}
    for field in reuse.SOURCE_MANIFEST_FIELDS:
        for version, manifest in (("064", old), ("066", new)):
            path = tmp_path / f"{field}_v{version}.py"
            path.write_text("# local source\n")
            manifest[field] = reference(path)
    return old, new


def test_manifest_rejects_changed_limits_decoder_and_upstream(tmp_path):
    old, new = manifest_fixture(tmp_path)
    assert reuse.equivalent_manifest_fields(old, new) == ["diagnostic_upstream_sha256", "limits", "parent"]
    for changes in ({"limits": {"timeout_seconds": 3600}}, {"diagnostic_upstream_sha256": "changed"},
                    {"parent": {"official_version": "different"}}):
        with pytest.raises(ValueError, match="dependencies or limits"):
            reuse.equivalent_manifest_fields(old, {**new, **changes})


def reuse_fixture(tmp_path, monkeypatch):
    plan_path, inventory_path = tmp_path / "plan.json", tmp_path / "inventory.json"
    run_root = tmp_path / "coordinator"
    monkeypatch.setattr(reuse.policy, "PLAN_FILE", plan_path)
    monkeypatch.setattr(reuse.policy, "RESUME_FILE", inventory_path)
    monkeypatch.setattr(reuse.policy, "COORDINATOR_RUN_ROOT", run_root)
    config = {"instance_id": "fixture", "scorer_request_base": {"image": "fixed-image"}}
    config_ref = write_new(tmp_path / "config.json", config)
    plans = {"environments": {"fixture": {"configuration": config_ref}}}
    old_plan = write_new(tmp_path / "old-plan.json", plans)
    plan = write_new(plan_path, plans)
    original = write_new(tmp_path / "old-qualified.json", {"passed": True})
    inventory = write_new(inventory_path, {"old_qualified": {"fixture": original}, "original_plan": old_plan})
    proof = {"old_manifest": {}, "new_manifest": {}, "valid": True}
    proof_ref = write_new(tmp_path / "proof.json", proof)
    monkeypatch.setattr(reuse, "equivalence_value", lambda *args: proof)
    target = run_root / "qualifications/fixture.json"
    target.parent.mkdir(parents=True)
    wrapper = {"version": reuse.VERSION, "instance_id": "fixture", "passed": True, "model_calls": 0,
        "plan": plan, "original_plan": old_plan, "original_qualification": original,
        "continuation_inventory": inventory, "equivalence_proof": proof_ref}
    ref = write_new(target, wrapper)
    return ref, config, plan, original, old_plan


def test_reuse_calls_real_old_validation_path_and_preserves_failure(tmp_path, monkeypatch):
    ref, config, plan, original, old_plan = reuse_fixture(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(old_scorer, "validate_qualification", lambda *args: calls.append(args) or {"passed": True})
    assert scorer.validate_qualification(ref, config, plan)["version"] == reuse.VERSION
    assert calls == [(original, config, old_plan)]
    def invalid(*args):
        raise ValueError("Original empty control lacks trustworthy cleanup")
    monkeypatch.setattr(old_scorer, "validate_qualification", invalid)
    with pytest.raises(ValueError, match="trustworthy cleanup"):
        scorer.validate_qualification(ref, config, plan)


def test_foreign_reuse_ref_fails_before_old_validator(tmp_path, monkeypatch):
    ref, config, plan, _, _ = reuse_fixture(tmp_path, monkeypatch)
    value = json.loads(Path(ref["path"]).read_bytes())
    value["original_qualification"] = write_new(tmp_path / "another-qualified.json", {"passed": True})
    Path(ref["path"]).write_text(json.dumps(value))
    monkeypatch.setattr(old_scorer, "validate_qualification", lambda *args: pytest.fail("Foreign proof entered validator"))
    with pytest.raises(ValueError, match="exact admitted old task"):
        scorer.validate_qualification(reference(ref["path"]), config, plan)


def test_control_plan_skips_109_qualified_and_three_failures_but_replaces_cancelled_control(tmp_path, monkeypatch):
    monkeypatch.setattr(grading.policy, "PLAN_FILE", tmp_path / "plan.json")
    monkeypatch.setattr(grading.policy, "RESUME_FILE", tmp_path / "inventory.json")
    monkeypatch.setattr(grading.policy, "GRADING_ROOT", tmp_path / "grading")
    monkeypatch.setattr(grading, "RUN_ROOT", tmp_path / "coordinator")
    qualified = {f"qualified-{i}": {"status": "qualified"} for i in range(109)}
    failures = {f"failed-{i}": {"status": "not_qualified"} for i in range(3)}
    new = ["django__django-14122", *[f"new-{i}" for i in range(387)]]
    tasks = [*qualified, *failures, *new]
    config = write_new(tmp_path / "config.json", {})
    write_new(grading.policy.PLAN_FILE, {"environments": {task: {"configuration": config} for task in tasks}})
    write_new(grading.policy.RESUME_FILE, {"qualifications": {**qualified, **failures}})
    manifest = write_new(tmp_path / "manifest.json", {})
    monkeypatch.setattr(grading, "prepare_manifest", lambda: manifest)
    monkeypatch.setattr(grading, "prepare_reused_qualifications", lambda: qualified)
    monkeypatch.setattr(grading.environment, "request_fields", lambda task: {"environment_revision": None, "network_resolution": None})
    refs = grading.prepare_controls()
    requests = [grading.load(ref) for ref in refs]
    assert len(requests) == 776 and {r["instance_id"] for r in requests} == set(new)
    assert {r["patch_kind"] for r in requests if r["instance_id"] == "django__django-14122"} == {"gold", "empty"}


def test_prepare_score_rejects_closed_predecessor_result(tmp_path, monkeypatch):
    slot = "v064:task:QWEN_REF_B5000K:1"
    row = {"slot_id": slot, "slot_index": 0, "configuration": {"frozen": True}}
    monkeypatch.setattr(grading.policy, "PLAN_FILE", tmp_path / "plan.json")
    monkeypatch.setattr(grading.policy, "RESUME_FILE", tmp_path / "inventory.json")
    monkeypatch.setattr(grading, "BATCH_ROOT", tmp_path / "new")
    write_new(grading.policy.PLAN_FILE, {"rows": [row]})
    write_new(grading.policy.RESUME_FILE, {"continuation_slot_ids": []})
    result = write_new(tmp_path / "old-result.json", {"slot_id": slot, "configuration": row["configuration"],
        "measurement_kind": "full_verified_comparison", "status": "closed"})
    with pytest.raises(ValueError, match="retain all old score"):
        grading.prepare_score(result)
