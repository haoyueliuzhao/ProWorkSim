"""Source-bound admission for the sole 18432-token four-pair capacity candidate.

All v045 outcomes and sources remain sealed. This module only joins existing
CPU, native-support and at-most-one actual neutral qualification receipts.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
from pathlib import Path

from proworksim.storage import digest, json_bytes
from scripts.run_ne_v021 import write
from scripts.software_organization_admission_v044 import EvidenceReader
from scripts.software_organization_admission_v045 import source_files
from scripts.software_organization_resume_admission_v045 import bind_refs, read_path

VERSION = "software-organization-capacity-admission-v0.46"
SOURCE = Path(__file__).resolve().parents[1]
CONTEXT = 18432
ORIGINAL_CONTEXT = 16384
OUTPUT_RESERVATION = 2048
ORIGINAL_TREE = "944e4ae925423b62af54db5c5bd1bef8c5c7f7684ed23a89a533ae4c73035163"
ORIGINAL_PLAN_SHA = "d1db9ae8b6487792bd0e021751d0153ecdc5f1bf73800b5fc5b33e8c64f1f82b"
PRIOR_PLAN_SHA = "458b7652a4001c797ba0f360d9819cf801f2dbb8034d52ff24a5525ca516df97"
COST_SHA = "3a604e9ed25a94766fdc50a4ce14832c1f267d4a1cd79a8f45a554c92d4f9f3d"
BASELINE_IDS = ("org45-r1-s0-F2", "org45-r1-s1-F2", "org45-r3-s0-F2", "org45-r3-s1-F2")
WORKERS = ("block-r1-s0", "block-r1-s1", "block-r3-s0", "block-r3-s1")
TEAM_LIMITS = {
    "max_decisions": 128,
    "max_attempts": 128,
    "max_total_tokens": 500000,
    "max_test_runs": 32,
}
DEPENDENCIES = (
    "common",
    "model_references",
    "expected_actor_identity",
    "expected_state_sha256",
    "runtime_dependency_path",
    "source_partition",
    "business_bindings",
)
NEW_CODE = frozenset(
    {
        "scripts/software_organization_v046.py",
        "scripts/software_organization_admission_v046.py",
        "tests/test_software_organization_v046.py",
        "tests/test_software_organization_admission_v046.py",
        "scripts/software_organization_capacity_qualification_v046.py",
        "tests/test_software_organization_capacity_qualification_v046.py",
        "scripts/measure_organization_budget_v046.py",
        "scripts/measure_organization_projection_v046.py",
        "scripts/measure_organization_feedback_v046.py",
        "scripts/measure_organization_work_v046.py",
        "scripts/software_organization_stop_policy_v046.py",
        "tests/test_measure_organization_budget_v046.py",
        "tests/test_measure_organization_projection_v046.py",
        "tests/test_measure_organization_work_v046.py",
        "tests/test_software_organization_stop_policy_v046.py",
    }
)


def require(condition, reason):
    if not condition:
        raise ValueError("v046 capacity admission rejected: " + reason)


def budget_caps():
    return {
        "new_treatment": {
            "decisions": 512,
            "attempts": 512,
            "total_tokens": 2000000,
            "run_tests": 128,
        },
        "qualification": {
            "max_model_calls": 1,
            "max_actual_tokens": 18432,
            "prompt_tokens": 16384,
            "max_output_tokens": 2048,
            "world_actions": 0,
        },
        "total_new_actual_tokens_max": 2018432,
        "historical_baseline_actual": {
            "decisions": 150,
            "attempts": 142,
            "total_tokens": 1971513,
            "run_tests": 2,
        },
        "original24_unused_tokens_not_transferred": 3703444,
        "transfer_old_unused": False,
        "other_context_candidates": [],
        "automatic_A_or_training": False,
    }


def paired_inventory(original_plan):
    """Read the old plan, preserving all four prelocked pairs including nontriggers."""
    result, cases, baselines = {}, {}, []
    require(
        set(WORKERS) <= set(original_plan.get("assignments", {})),
        "original root/seed blocks missing",
    )
    for worker, baseline in zip(WORKERS, BASELINE_IDS, strict=True):
        units = original_plan["assignments"][worker]
        matches = [
            (u, c)
            for u, c in zip(units, original_plan["cases"][worker], strict=True)
            if u["slot_id"] == baseline
        ]
        require(len(matches) == 1, "missing or duplicate prelocked F2 baseline")
        unit, case = matches[0]
        require(
            unit["condition"] == "F2"
            and unit["root_label"] in ("HA", "HB")
            and unit["sampling_seed"] == (202610100451 if worker.endswith("s0") else 202610100452)
            and unit["first_member"] == ("member_002" if worker.endswith("s0") else "member_001"),
            "prelocked seed, root or original first member changed",
        )
        require(
            case["team_limits"] == TEAM_LIMITS
            and all(case[k] == unit[k] for k in ("case_id", "condition", "first_member")),
            "original F2 case or budget changed",
        )
        new = copy.deepcopy(unit)
        new.update(
            slot_id=unit["slot_id"].replace("org45-", "org46-", 1) + "-C18432",
            baseline_slot_id=baseline,
            capacity_treatment="C18432",
            context_limit=CONTEXT,
        )
        result[worker] = [new]
        cases[worker] = [copy.deepcopy(case)]
        baselines.append(copy.deepcopy(unit))
    ids = [u["slot_id"] for rows in result.values() for u in rows]
    require(
        len(set(ids)) == 4 and not set(ids) & set(BASELINE_IDS),
        "new treatment identities duplicate historical work",
    )
    return {"assignments": result, "cases": cases, "baseline_units": baselines}


def source_audit(prior_plan, source_root=SOURCE):
    root = Path(source_root).resolve()
    old = prior_plan["source_files"]
    current = source_files(root)
    require(
        bool(old) and all(current.get(name) == sha for name, sha in old.items()),
        "old source bytes changed or disappeared",
    )
    added = set(current) - set(old)
    require(added == NEW_CODE, "only declared isolated v046 source/test additions are allowed")
    h = hashlib.sha256()
    for name in sorted(n for n in current if n.startswith("src/") and n.endswith(".py")):
        h.update(name.encode())
        h.update((root / name).read_bytes())
    require(
        h.hexdigest() == ORIGINAL_TREE == prior_plan["source"]["source_tree_sha256"],
        "original native/model-visible source changed",
    )
    return {
        "all_prior_bytes_unchanged": True,
        "prior_file_count": len(old),
        "source_tree_sha256": h.hexdigest(),
        "prior_files": dict(old),
        "new_files": {n: current[n] for n in sorted(added)},
        "source_files": current,
    }


def validate_capacity_binding(value, original_plan):
    """The sole treatment changes capacity metadata after exact old common restore."""
    require(
        value.get("version") == "software-capacity-binding-v0.46" and value.get("passed") is True,
        "capacity metadata binding did not pass",
    )
    require(
        (
            value.get("original_context_limit"),
            value.get("context_limit"),
            value.get("reserved_output_tokens"),
        )
        == (ORIGINAL_CONTEXT, CONTEXT, OUTPUT_RESERVATION),
        "not the single18432/2048 candidate",
    )
    old_recipe, new_recipe = value["original_recipe"], value["capacity_recipe"]
    require(
        old_recipe.get("max_length") == ORIGINAL_CONTEXT
        and old_recipe.get("max_output_tokens") == OUTPUT_RESERVATION
        and new_recipe == {**old_recipe, "max_length": CONTEXT},
        "recipe changes beyond capacity",
    )
    old_profile, new_profile = (
        value["original_inference_profile"],
        value["capacity_inference_profile"],
    )
    require(
        old_profile.get("max_context_tokens") == ORIGINAL_CONTEXT
        and new_profile == {**old_profile, "max_context_tokens": CONTEXT},
        "numerical/profile changes beyond capacity",
    )
    for key, body in (
        ("original_recipe_sha256", old_recipe),
        ("capacity_recipe_sha256", new_recipe),
        ("original_profile_sha256", old_profile),
        ("capacity_profile_sha256", new_profile),
    ):
        require(value.get(key) == digest(json_bytes(body)), "binding digest mismatch: " + key)
    old_identity, new_identity = value["original_actor_identity"], value["capacity_actor_identity"]
    require(
        old_identity == original_plan["expected_actor_identity"]
        and new_identity
        == {**old_identity, "inference_profile_sha256": value["capacity_profile_sha256"]},
        "capacity identity changed weights/base/policy rather than only profile metadata",
    )
    require(
        bool(value.get("protected_components_unchanged"))
        and all(v is True for v in value["protected_components_unchanged"].values())
        and value.get("new_parameter_updates") == value.get("new_backward_calls") == 0,
        "common state or numerical path not protected",
    )
    return new_identity


def validate_baselines(rows, inventory):
    byid = {r["slot_id"]: r for r in rows}
    require(
        len(rows) == len(byid) == 4 and tuple(r["slot_id"] for r in rows) == BASELINE_IDS,
        "not exactly the four prelocked controls",
    )
    for unit in inventory["baseline_units"]:
        row = byid[unit["slot_id"]]
        require(
            all(row.get(k) == v for k, v in unit.items())
            and row.get("status") == "closed"
            and type(row.get("R")) is int
            and row["R"] == 0
            and row.get("submitted") is False,
            "historical control identity or formal result changed",
        )
    totals = {
        k: sum(r["usage"][k] for r in rows) for k in ("decisions", "attempts", "total_tokens")
    }
    totals["run_tests"] = sum(r["tests"]["accepted_run_tests_calls"] for r in rows)
    require(
        totals == budget_caps()["historical_baseline_actual"], "historical control cost changed"
    )
    return totals


def validate_cpu_controls(controls, source):
    require(controls.get("passed") is True, "CPU host/measurement controls did not pass")
    require(
        controls.get("source_files") == source["source_files"],
        "CPU controls do not bind all current sources",
    )
    require(
        controls.get("new_model_calls", 0) == 0
        and controls.get("new_test_or_acceptance_executions", 0) == 0,
        "CPU controls contain undeclared model or business executions",
    )


def validate_native_support(value, original_plan):
    """Filled to the source-review contract; never retokenize or run a model."""
    require(
        value.get("passed") is True,
        "original native path does not support the sole capacity candidate",
    )
    require(value.get("context_limit") == CONTEXT, "native support is for another context length")
    require(
        value.get("new_model_calls") == 0,
        "native support receipt is not a zero-model source review",
    )
    require(
        value.get("unchanged_rope_precision_quantization_attention_backend") is True,
        "native support requires a prohibited numeric or position extension",
    )


def validate_model_qualification(value, original_plan, reader):
    """Accept only the sealed exact neutral request, never a successful business task."""
    require(
        value.get("version") == "software-organization-capacity-qualification-v0.46"
        and value.get("passed") is True
        and value.get("status") in ("passed", "reused_no_new_call"),
        "single capacity qualification failed or absent",
    )
    require(
        value.get("candidate_context") == CONTEXT
        and value.get("target_prompt_tokens") == ORIGINAL_CONTEXT
        and value.get("reserved_output_tokens") == OUTPUT_RESERVATION
        and value.get("max_native_calls") == 1,
        "qualification did not use exact P16384/O2048/C18432",
    )
    calls, starts = value.get("actual_model_calls"), value.get("native_calls_started")
    require(
        type(calls) is int
        and calls in (0, 1)
        and starts == calls
        and value.get("usage_complete") is True,
        "qualification exceeded one request or has uncertain usage",
    )
    require(
        value.get("world_instances") == value.get("tools_executed") == 0
        and value.get("new_actor_steps")
        == value.get("new_critic_steps")
        == value.get("new_backward_calls")
        == 0,
        "qualification altered a world or model",
    )
    usage = value.get("usage", {})
    require(
        all(
            type(usage.get(k)) is int and usage[k] >= 0
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")
        )
        and usage["prompt_tokens"] + usage["completion_tokens"] == usage["total_tokens"] <= CONTEXT,
        "qualification token cost not exact and bounded",
    )
    checks = value.get("checks", {})
    required = {
        "exact_original_and_selected_request",
        "exact_serialized_prompt_tokens",
        "exact_native_input_ids",
        "output_nonempty",
        "output_within_reservation",
        "all_generated_tokens_retained",
        "usage_consistent",
        "numerical_path_unchanged",
        "zero_parameter_updates",
    }
    require(
        required <= set(checks) and all(v is True for v in checks.values()),
        "qualification exact-input/output/numeric checks incomplete",
    )
    if calls == 1:
        require(
            value["status"] == "passed"
            and len(value.get("calls", [])) == 1
            and usage["prompt_tokens"] == 16384
            and 0 < usage["completion_tokens"] <= 2048,
            "qualification did not cross old16K with a nonempty actual output",
        )
    else:
        require(
            value["status"] == "reused_no_new_call"
            and usage["total_tokens"] == 0
            and value.get("reused_qualification"),
            "zero-call qualification needs existing exact evidence",
        )
        previous = reader.read(value["reused_qualification"])
        require(
            previous.get("passed") is True
            and previous.get("candidate_context") == CONTEXT
            and previous.get("actual_model_calls") == previous.get("native_calls_started") == 1,
            "invalid historical capacity qualification reuse",
        )
        validate_model_qualification(previous, original_plan, reader)
    require(
        value.get("source_before") == value.get("source_after")
        and value.get("source_before", {}).get("code_dirty") is False,
        "qualification source changed during execution",
    )
    qualified_plan = reader.read(value["original_plan"])
    require(
        all(qualified_plan[k] == original_plan[k] for k in DEPENDENCIES),
        "qualification used another original common/native path",
    )
    require(
        value["original_common"]["sha256"] == original_plan["common"]["sha256"],
        "qualification common reference changed",
    )
    require(
        isinstance(value.get("python_executable"), str)
        and isinstance(value.get("python_prefix"), str)
        and Path(value["python_executable"]).is_absolute()
        and Path(value["python_prefix"]).is_absolute(),
        "qualification SDK executable/prefix identity missing",
    )
    binding = reader.read(value["capacity_binding"])
    identity = validate_capacity_binding(binding, original_plan)
    return {
        "capacity_actor_identity": identity,
        "capacity_binding": value["capacity_binding"],
        "capacity_recipe_sha256": binding["capacity_recipe_sha256"],
        "capacity_profile_sha256": binding["capacity_profile_sha256"],
        "new_model_calls": calls,
        "actual_total_tokens": usage["total_tokens"],
        "python_executable": value["python_executable"],
        "python_prefix": value["python_prefix"],
    }


def build_admission(
    data_root, cpu_controls, native_support, model_qualification, *, source_root=SOURCE
):
    root = Path(data_root).resolve()
    reader = EvidenceReader()
    refs = {}

    def load(name, path):
        value, refs[name] = read_path(reader, path)
        return value

    original = load("original24_plan", root / "runs/software-organization-v045/plan.json")
    prior = load(
        "completed24_source_plan", root / "runs/software-organization-v045-complete-r1/plan.json"
    )
    for plan, expected in ((original, ORIGINAL_PLAN_SHA), (prior, PRIOR_PLAN_SHA)):
        require(
            plan.get("plan_sha256")
            == expected
            == digest(json_bytes({k: v for k, v in plan.items() if k != "plan_sha256"})),
            "historical plan was changed",
        )
    require(
        all(original[k] == prior[k] for k in DEPENDENCIES),
        "historical common/task/model references differ",
    )
    source = source_audit(prior, source_root)
    inventory = paired_inventory(original)
    cost_ref = {
        "path": str(root / "runs/v045-complete-r1-final-analysis/cost-review.json"),
        "sha256": COST_SHA,
    }
    cost = reader.read(cost_ref)
    require(
        cost.get("final") is True
        and cost.get("final_complete") is True
        and cost.get("issues") == [],
        "original24 have not been sealed",
    )
    rows = [next(r for r in cost["slots"] if r["slot_id"] == identity) for identity in BASELINE_IDS]
    totals = validate_baselines(rows, inventory)
    baseline_refs = []
    for row in rows:
        result_ref = row["sources"]["slot-result.json"]
        result = reader.read(result_ref)
        require(
            result["usage"] == row["usage"]
            and result["R"] == row["R"]
            and result["submitted"] == row["submitted"],
            "control result changed after original sealed cost audit",
        )
        baseline_refs.append(
            {
                "slot_id": row["slot_id"],
                "result": result_ref,
                "cost_review": cost_ref,
                "usage": row["usage"],
                "run_tests": row["tests"]["accepted_run_tests_calls"],
                "R": row["R"],
                "source_refs": row["sources"],
                "replay_permitted": False,
            }
        )
    trigger = load(
        "historical_trigger",
        root / "runs/v045-complete-r1-final-analysis/probe-trigger-review.json",
    )
    require(
        trigger.get("final") is True
        and trigger.get("selected_branch") == "C"
        and trigger.get("C_plus_context_length") is None
        and trigger.get("execution_permitted") is False
        and trigger.get("prelocked_baseline_slot_ids") == list(BASELINE_IDS),
        "original proposal history changed",
    )
    controls = load("cpu_controls", cpu_controls)
    validate_cpu_controls(controls, source)
    native = load("native_support", native_support)
    validate_native_support(native, original)
    qualified = load("model_qualification", model_qualification)
    qualification = validate_model_qualification(qualified, original, reader)
    require(
        not native.get("qualification_required") or qualification["new_model_calls"] == 1,
        "native source review found no exact existing qualification; one actual request required",
    )
    require(
        qualified.get("source_files") == source["source_files"],
        "qualification source files changed",
    )
    require(
        Path(qualification["python_executable"]).resolve()
        == (root / "runs/v016-sdk/resident-venv/bin/python").resolve()
        and Path(qualification["python_prefix"]).resolve()
        == (root / "runs/v016-sdk/resident-venv").resolve(),
        "qualification did not use the original SDK interpreter environment",
    )
    require(
        qualified["cpu_controls"]["sha256"] == refs["cpu_controls"]["sha256"]
        and qualified["native_support"]["sha256"] == refs["native_support"]["sha256"],
        "qualification did not consume the admitted CPU/native prerequisites",
    )
    bind_refs(
        [
            controls.get("checks", []),
            native.get("sources", {}),
            qualified.get("sources", {}),
            original["common"],
            original["model_references"],
        ],
        reader,
    )
    output = {
        "version": VERSION,
        "passed": True,
        "data_root": str(root),
        "historical_refs": refs,
        "source_audit": source,
        "source_files": source["source_files"],
        "remaining_assignments": inventory["assignments"],
        "remaining_cases": inventory["cases"],
        "baseline_units": inventory["baseline_units"],
        "baseline_refs": baseline_refs,
        "baseline_actual": totals,
        "baseline_worker_gpu_seconds": None,
        "baseline_timing_scope": "Historical controls shared resident workers with other conditions; no arbitrary GPU-time allocation.",
        "original_model_identity": {k: original[k] for k in DEPENDENCIES},
        "capacity_qualification": qualification,
        "budget_caps": budget_caps(),
        "bound_evidence": list(reader.checked.values()),
        "new_model_calls": 0,
        "new_tokenizer_calls": 0,
        "new_test_or_acceptance_executions": 0,
        "new_world_actions": 0,
        "new_backward_calls": 0,
        "scope": "Sole C18432 candidate on all four prelocked F2 pairs, including nontriggers. Original initial states and seeds retained; no baseline replay, additional length, automatic A/training, or unused-token transfer.",
    }
    output["admission_sha256"] = digest(json_bytes(output))
    return output


def create_admission(
    data_root, cpu_controls, native_support, model_qualification, output, *, source_root=SOURCE
):
    output = Path(output)
    require(not output.exists(), "preserve any previous admission receipt")
    value = build_admission(
        data_root, cpu_controls, native_support, model_qualification, source_root=source_root
    )
    write(output, value)
    return value


def validate_admission(path, *, source_root=SOURCE):
    reader = EvidenceReader()
    value, _ = read_path(reader, path)
    require(
        value.get("version") == VERSION
        and value.get("passed") is True
        and value.get("admission_sha256")
        == digest(json_bytes({k: v for k, v in value.items() if k != "admission_sha256"})),
        "saved admission digest or status changed",
    )
    refs = value["historical_refs"]
    rebuilt = build_admission(
        value["data_root"],
        refs["cpu_controls"]["path"],
        refs["native_support"]["path"],
        refs["model_qualification"]["path"],
        source_root=source_root,
    )
    require(rebuilt == value, "saved source or bounded qualification changed")
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("create", "validate"))
    parser.add_argument("--data-root", type=Path, default=SOURCE)
    parser.add_argument("--cpu-controls", type=Path)
    parser.add_argument("--native-support", type=Path)
    parser.add_argument("--model-qualification", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = (
        create_admission(
            args.data_root,
            args.cpu_controls,
            args.native_support,
            args.model_qualification,
            args.output,
        )
        if args.mode == "create"
        else validate_admission(args.output)
    )
    print(
        {
            "passed": value["passed"],
            "pairs": 4,
            "context": CONTEXT,
            "admission_sha256": value["admission_sha256"],
        }
    )


if __name__ == "__main__":
    main()
