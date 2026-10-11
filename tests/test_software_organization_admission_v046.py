"""Finite CPU counterexamples for single-capacity, four-pair source admission."""

import copy
import hashlib

import pytest

from proworksim.storage import digest, json_bytes
from scripts import software_organization_admission_v046 as admission
from scripts import software_organization_v045 as original


def plan_fixture():
    units = original.assignments()
    return {
        "assignments": units,
        "cases": {
            w: [
                {
                    **{k: u[k] for k in ("case_id", "condition", "first_member")},
                    "team_limits": dict(admission.TEAM_LIMITS),
                }
                for u in rows
            ]
            for w, rows in units.items()
        },
    }


def test_inventory_uses_all_prelocked_pairs_and_original_initial_cases():
    plan = plan_fixture()
    before = copy.deepcopy(plan)
    result = admission.paired_inventory(plan)
    assert plan == before and tuple(result["assignments"]) == admission.WORKERS
    assert [u["slot_id"] for u in result["baseline_units"]] == list(admission.BASELINE_IDS)
    assert [rows[0]["first_member"] for rows in result["assignments"].values()] == [
        "member_002",
        "member_001",
        "member_002",
        "member_001",
    ]
    assert [rows[0]["sampling_seed"] for rows in result["assignments"].values()] == [
        202610100451,
        202610100452,
    ] * 2
    assert all(
        rows[0]["condition"] == "F2" and rows[0]["context_limit"] == 18432
        for rows in result["assignments"].values()
    )
    assert admission.budget_caps()["new_treatment"] == dict(
        decisions=512, attempts=512, total_tokens=2000000, run_tests=128
    )
    assert admission.budget_caps()["total_new_actual_tokens_max"] == 2018432
    assert admission.budget_caps()["original24_unused_tokens_not_transferred"] == 3703444
    assert admission.budget_caps()["transfer_old_unused"] is False


@pytest.mark.parametrize(
    "fault", ["first", "seed", "condition", "budget", "duplicate", "missing_nontrigger"]
)
def test_inventory_rejects_selection_or_case_change(fault):
    p = plan_fixture()
    worker = "block-r1-s1"
    rows = p["assignments"][worker]
    i = next(i for i, u in enumerate(rows) if u["condition"] == "F2")
    if fault == "first":
        rows[i]["first_member"] = "member_002"
    elif fault == "seed":
        rows[i]["sampling_seed"] += 1
    elif fault == "condition":
        rows[i]["condition"] = "O3"
    elif fault == "budget":
        p["cases"][worker][i]["team_limits"]["max_total_tokens"] += 1000
    elif fault == "duplicate":
        rows[0] = copy.deepcopy(rows[i])
    else:
        rows.pop(i)
        p["cases"][worker].pop(i)
    with pytest.raises(ValueError):
        admission.paired_inventory(p)


def source_fixture(tmp_path, monkeypatch):
    path = tmp_path / "src/model.py"
    path.parent.mkdir()
    data = b"# unchanged native implementation\n"
    path.write_bytes(data)
    tree = hashlib.sha256(b"src/model.py" + data).hexdigest()
    monkeypatch.setattr(admission, "ORIGINAL_TREE", tree)
    for name in admission.NEW_CODE:
        p = tmp_path / name
        p.parent.mkdir(exist_ok=True)
        p.write_text("# isolated v046\n")
    return {"source_files": {"src/model.py": digest(data)}, "source": {"source_tree_sha256": tree}}


def test_source_delta_preserves_old_native_code_and_only_declared_additions(tmp_path, monkeypatch):
    plan = source_fixture(tmp_path, monkeypatch)
    assert admission.source_audit(plan, tmp_path)["all_prior_bytes_unchanged"] is True
    (tmp_path / "src/model.py").write_text("# changed precision\n")
    with pytest.raises(ValueError, match="old source bytes"):
        admission.source_audit(plan, tmp_path)


def test_undeclared_capacity_fallback_dependency_rejected(tmp_path, monkeypatch):
    plan = source_fixture(tmp_path, monkeypatch)
    (tmp_path / "scripts/fallback.py").write_text("# another length\n")
    with pytest.raises(ValueError, match="isolated v046"):
        admission.source_audit(plan, tmp_path)


def binding_fixture():
    recipe = {
        "max_length": 16384,
        "max_output_tokens": 2048,
        "temperature": 0.7,
        "members": ["member_a", "member_b", "software_inactive"],
    }
    profile = {
        "max_context_tokens": 16384,
        "max_output_tokens": 2048,
        "dtype": "bfloat16",
        "backend": "original",
    }
    new_recipe = {**recipe, "max_length": 18432}
    new_profile = {**profile, "max_context_tokens": 18432}
    identity = {
        "policy_version": "original3",
        "adapter_sha256": "weights",
        "base_manifest_sha256": "base",
        "inference_profile_sha256": digest(json_bytes(profile)),
    }
    value = {
        "version": "software-capacity-binding-v0.46",
        "passed": True,
        "original_context_limit": 16384,
        "context_limit": 18432,
        "reserved_output_tokens": 2048,
        "original_recipe": recipe,
        "capacity_recipe": new_recipe,
        "original_inference_profile": profile,
        "capacity_inference_profile": new_profile,
        "original_actor_identity": identity,
        "capacity_actor_identity": {
            **identity,
            "inference_profile_sha256": digest(json_bytes(new_profile)),
        },
        "protected_components_unchanged": {
            "actor": True,
            "critic": True,
            "optimizers": True,
            "rng": True,
        },
        "new_parameter_updates": 0,
        "new_backward_calls": 0,
    }
    for key, body in [
        ("original_recipe_sha256", recipe),
        ("capacity_recipe_sha256", new_recipe),
        ("original_profile_sha256", profile),
        ("capacity_profile_sha256", new_profile),
    ]:
        value[key] = digest(json_bytes(body))
    return value, {"expected_actor_identity": identity}


def test_binding_changes_only_two_capacity_metadata_fields_not_weights():
    binding, plan = binding_fixture()
    before = copy.deepcopy(binding)
    assert admission.validate_capacity_binding(binding, plan) == binding["capacity_actor_identity"]
    assert (
        binding == before
        and binding["original_actor_identity"] != binding["capacity_actor_identity"]
    )


@pytest.mark.parametrize(
    "fault", ["length", "output", "precision", "backend", "temperature", "weights", "RNG", "hash"]
)
def test_capacity_binding_rejects_broader_treatment_or_unproved_state(fault):
    value, plan = binding_fixture()
    if fault == "length":
        value["capacity_recipe"]["max_length"] = 32768
    elif fault == "output":
        value["capacity_recipe"]["max_output_tokens"] = 4096
    elif fault == "precision":
        value["capacity_inference_profile"]["dtype"] = "float16"
    elif fault == "backend":
        value["capacity_inference_profile"]["backend"] = "other"
    elif fault == "temperature":
        value["capacity_recipe"]["temperature"] = 1.0
    elif fault == "weights":
        value["capacity_actor_identity"]["adapter_sha256"] = "new-weights"
    elif fault == "RNG":
        value["protected_components_unchanged"]["rng"] = False
    else:
        value["capacity_recipe_sha256"] = "bad"
    with pytest.raises(ValueError):
        admission.validate_capacity_binding(value, plan)


class Reader:
    def __init__(self, values):
        self.values = values

    def read(self, ref):
        return self.values[ref["path"]]


def qualification_fixture():
    binding, base = binding_fixture()
    plan = {k: ("fixed:" + k) for k in admission.DEPENDENCIES}
    plan.update(base, common={"path": "common", "sha256": "same"})
    checks = {
        k: True
        for k in (
            "exact_original_and_selected_request",
            "exact_serialized_prompt_tokens",
            "exact_native_input_ids",
            "output_nonempty",
            "output_within_reservation",
            "all_generated_tokens_retained",
            "usage_consistent",
            "numerical_path_unchanged",
            "zero_parameter_updates",
        )
    }
    value = {
        "version": "software-organization-capacity-qualification-v0.46",
        "passed": True,
        "status": "passed",
        "candidate_context": 18432,
        "target_prompt_tokens": 16384,
        "reserved_output_tokens": 2048,
        "max_native_calls": 1,
        "actual_model_calls": 1,
        "native_calls_started": 1,
        "usage_complete": True,
        "usage": {"prompt_tokens": 16384, "completion_tokens": 1, "total_tokens": 16385},
        "calls": [{"response": "bound"}],
        "python_executable": "/sdk/bin/python",
        "python_prefix": "/sdk",
        "checks": checks,
        "source_before": {"code_dirty": False, "code_commit": "frozen"},
        "source_after": {"code_dirty": False, "code_commit": "frozen"},
        "original_plan": {"path": "plan"},
        "original_common": {"path": "common", "sha256": "same"},
        "capacity_binding": {"path": "binding"},
        "world_instances": 0,
        "tools_executed": 0,
        "new_actor_steps": 0,
        "new_critic_steps": 0,
        "new_backward_calls": 0,
    }
    return value, plan, Reader({"binding": binding, "plan": plan})


def test_exact_neutral_request_crosses_old_limit_without_full_length_claim():
    value, plan, reader = qualification_fixture()
    proof = admission.validate_model_qualification(value, plan, reader)
    assert proof["new_model_calls"] == 1 and proof["actual_total_tokens"] == 16385


@pytest.mark.parametrize(
    "fault",
    [
        "empty",
        "prompt",
        "overoutput",
        "retry",
        "uncertain",
        "truncate",
        "world",
        "source",
        "common",
        "failed",
        "zero_without_evidence",
    ],
)
def test_qualification_rejects_missing_native_proof_or_extra_sampling(fault):
    value, plan, reader = qualification_fixture()
    if fault == "empty":
        value["usage"].update(completion_tokens=0, total_tokens=16384)
    elif fault == "prompt":
        value["usage"].update(prompt_tokens=16383, total_tokens=16384)
    elif fault == "overoutput":
        value["usage"].update(completion_tokens=2049, total_tokens=18433)
    elif fault == "retry":
        value.update(actual_model_calls=2, native_calls_started=2)
    elif fault == "uncertain":
        value["usage_complete"] = False
    elif fault == "truncate":
        value["checks"]["exact_native_input_ids"] = False
    elif fault == "world":
        value["world_instances"] = 1
    elif fault == "source":
        value["source_after"]["code_commit"] = "changed"
    elif fault == "common":
        value["original_common"]["sha256"] = "another"
    elif fault == "failed":
        value.update(passed=False, status="failed_no_successor")
    else:
        value.update(
            actual_model_calls=0,
            native_calls_started=0,
            status="reused_no_new_call",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )
    with pytest.raises(ValueError):
        admission.validate_model_qualification(value, plan, reader)


def test_existing_admission_is_never_overwritten(tmp_path):
    path = tmp_path / "existing.json"
    path.write_text("preserved")
    with pytest.raises(ValueError, match="preserve any previous"):
        admission.create_admission("missing", "missing", "missing", "missing", path)
    assert path.read_text() == "preserved"
