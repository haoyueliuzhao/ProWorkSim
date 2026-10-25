"""Read-only evidence equivalence for the model-memory-only v061 continuation."""
from __future__ import annotations

import json
from pathlib import Path

from . import software_benchmark_dispatch_v061 as policy
from .software_benchmark_candidates_v054 import checked, reference, write_new

VERSION = "v061-private-compiler-continuation-r4"
ROOT, BATCH_ROOT, RUN_ROOT = policy.ROOT, policy.BATCH_ROOT, policy.COORDINATOR_RUN_ROOT
UNCHANGED_DIAGNOSTIC_SOURCES = (
    "src/proworksim/software_benchmark_docker_actor_v061.py",
    "src/proworksim/software_benchmark_recovery_episode_v061.py",
    "tools/run_native_worker_docker_v061.py",
    "src/proworksim/software_benchmark_model_fifo_v061.py",
    "tools/bridge_ref_model_fifo_v061.py",
    "tools/run_ref_budget_controller_v061.py",
    "src/proworksim/software_benchmark_ref_budget_v061.py",
    "src/proworksim/software_benchmark_ref_budget_v056.py",
    "src/proworksim/software_benchmark_sdk_bundle_v061.py",
    "runs/software-benchmark-v061/sdk-bundle-r3/manifest.json",
    "src/proworksim/software_benchmark_native_worker_v054.py",
    "src/proworksim/software_benchmark_network_v055.py",
    "src/proworksim/software_benchmark_tls_transport_v059.py",
    "src/proworksim/software_benchmark_snapshot_recovery_v061.py",
    "tools/run_offline_scorer_v058.py",
)


def load(ref):
    return json.loads(checked(ref).read_bytes())


def retain(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if json.loads(path.read_bytes()) != value:
            raise ValueError("Immutable continuation evidence changed: " + str(path))
        return reference(path)
    return write_new(path, value)


def assert_unentered_generation(plan):
    for row in plan["rows"]:
        if row["measurement_kind"] != "fresh_generation_recovery":
            continue
        for role in ("actor", "controller", "volume", "score"):
            if (BATCH_ROOT / "resource-claims" / (role + "-" + str(row["slot_index"]) + ".json")).exists():
                raise ValueError("A planned continuation slot already consumed a creation claim")
    if list((BATCH_ROOT / "residents-compiler-r4").glob("model-*/spec.json")):
        raise ValueError("The new compiler deployment is already entered; do not replay it")
    return True


def compiler_deployment_recovery_evidence(plan):
    """Permit redeployment only after the two pre-readiness failures closed without sampling."""
    assert_unentered_generation(plan)
    summary_ref = reference(BATCH_ROOT / "continuation/model-memory-r3/run-summary.json")
    summary = load(summary_ref)
    expected = sorted(row["slot_id"] for row in plan["rows"] if row["measurement_kind"] == "fresh_generation_recovery")
    if (summary.get("failure", {}).get("kind") != "model_admission_unavailable"
            or summary.get("generation") != {} or sorted(summary.get("unentered_generation", [])) != expected):
        raise ValueError("Prior model-memory run does not prove all thirteen generation slots unentered")
    closures = {item.get("unit"): item for item in summary.get("resident_closure", [])}
    evidence = []
    for index in (0, 1):
        folder = BATCH_ROOT / "residents" / ("model-" + str(index))
        spec_ref, closed_ref = reference(folder / "spec.json"), reference(folder / "closed.json")
        spec, closed = load(spec_ref), load(closed_ref)
        unit = "proworksim-v061-model-" + str(index) + ".service"
        closure = closures.get(unit, {})
        if (spec.get("unit") != unit or spec.get("gpu_memory_utilization") != 0.6
                or closed.get("unit") != unit or closed.get("child_exited") is not True
                or closed.get("status") != "technical_unknown" or closed.get("ready") is True
                or closed.get("error", {}).get("message") != "Owned REF engine exited before readiness"
                or closure.get("owned_unit_stopped") is not True or closure.get("closed") != closed_ref
                or (folder / "ready.json").exists() or list(folder.glob("neutral*"))):
            raise ValueError("Prior resident is not a closed pre-neutral initialization failure")
        evidence.append({"unit": unit, "specification": spec_ref, "closed": closed_ref,
                         "closure": closure, "neutral_api_calls": 0, "formal_model_calls": 0})
    return {"version": VERSION, "prior_coordinator_summary": summary_ref, "prior_residents": evidence,
        "remaining_generation": expected, "formal_generation_replayed": False,
        "new_unique_user_units": 0, "same_two_owned_model_units_redeployed": True,
        "private_compiler_repair_only": True, "model_memory_profile_changed_again": False}


def prepare_diagnostic_equivalence(active_plan_ref):
    active = load(active_plan_ref)
    equivalence = policy.validate_plan_equivalence(active["source_plan"], active_plan_ref)
    previous_ref = reference(BATCH_ROOT / "diagnostic-qualification.json")
    previous = load(previous_ref)
    if previous.get("diagnostic_index") != 2:
        raise ValueError("Only the actually completed second deployment diagnostic is reused")
    result = load(previous["result"])
    quiet = load(result["quiescence"])
    if (result.get("passed") is not True or result.get("model_calls") != 0
            or quiet.get("quiescent") is not True or quiet.get("cleanup_errors") != []
            or quiet.get("create_result_unknown") is not False
            or quiet.get("all_owned_objects_removed") is not True):
        raise ValueError("The retained deployment diagnostic is not passed and fully removed")
    old_sources = {item["path"]: item for item in previous["sources"]}
    checked_sources = []
    for name in UNCHANGED_DIAGNOSTIC_SOURCES:
        current = reference(ROOT / name)
        if old_sources.get(current["path"]) != current:
            raise ValueError("A previously tested Docker/SDK component changed: " + name)
        checked_sources.append(current)
    value = {"version": VERSION, "plan": active_plan_ref, "source_plan": active["source_plan"],
        "source_diagnostic_qualification": previous_ref, "result": previous["result"],
        "plan_equivalence": equivalence, "unchanged_runtime_sources": checked_sources,
        "sources": policy.sources(), "new_diagnostic_containers": 0,
        "model_capacity_still_requires_new_resident_admission": True}
    return retain(RUN_ROOT / "diagnostic-equivalence.json", value)


def validate_diagnostic_equivalence(ref, active_plan_ref):
    value = load(ref)
    if (value.get("version") != VERSION or value.get("plan") != active_plan_ref
            or value.get("sources") != policy.sources() or value.get("new_diagnostic_containers") != 0):
        raise ValueError("Unrecognized continuation diagnostic equivalence")
    expected = prepare_diagnostic_equivalence(active_plan_ref)
    if expected != ref:
        raise ValueError("Diagnostic equivalence differs from its fixed record")
    return value


def snapshot_score_evidence(plan, source_plan_ref):
    folder = BATCH_ROOT / "grading/score-163"
    refs = {name: reference(folder / (name + ".json")) for name in ("request", "receipt", "completion", "quiescence")}
    request, receipt, completion, quiet = (load(refs[name]) for name in ("request", "receipt", "completion", "quiescence"))
    identity = load(receipt["identity"])
    row = next(item for item in plan["rows"] if item["slot_index"] == 163)
    if (request.get("plan") != source_plan_ref or identity.get("plan") != source_plan_ref
            or request.get("original_config") != row["original_config"]
            or identity.get("candidate_lock") != request.get("candidate_lock")
            or identity.get("request") != refs["request"] or completion.get("request") != refs["request"]
            or completion.get("returncode") != 0 or receipt.get("status") != "official_report"
            or receipt.get("resolved") is not True or receipt.get("resource_key") != "score-163"
            or receipt.get("slot_id") != row["slot_id"] or receipt.get("original_slot_id") != row["slot_id"]
            or receipt.get("measurement_kind") != "original_terminal_snapshot_recovery"
            or receipt.get("model_calls") != 0 or receipt.get("actor_feedback") is not False
            or quiet.get("resource_key") != "score-163" or quiet.get("quiescent") is not True
            or quiet.get("cleanup_errors") != [] or quiet.get("create_result_unknown") is not False
            or quiet.get("deadline_reached") is not False):
        raise ValueError("The retained original snapshot score is not an exact trustworthy completion")
    official = receipt["official_result"][1][row["instance_id"]]
    if official.get("resolved") is not True or official.get("patch_successfully_applied") is not True or official.get("infra_failure"):
        raise ValueError("The retained snapshot lacks its positive official result")
    return {"request": refs["request"], "receipt": refs["receipt"], "completion": completion,
        "completion_reference": refs["completion"], "quiescence": refs["quiescence"],
        "reused_without_replay": True, "source_plan": source_plan_ref}


def prepare_reuse(active_plan_ref):
    from . import software_benchmark_scorer_v061 as scorer
    active = load(active_plan_ref)
    assert_unentered_generation(active)
    deployment = retain(RUN_ROOT / "deployment-recovery.json", compiler_deployment_recovery_evidence(active))
    eq = policy.validate_plan_equivalence(active["source_plan"], active_plan_ref)
    eq_ref = retain(RUN_ROOT / "plan-equivalence.json", eq)
    diagnostic = prepare_diagnostic_equivalence(active_plan_ref)
    qualifications = {}
    for task, entry in active["environments"].items():
        source_ref = reference(BATCH_ROOT / "qualifications" / (task + ".json"))
        source = scorer.validate_qualification(source_ref, load(entry["original_config"]), active["source_plan"])
        wrapper = {"version": scorer.VERSION, "instance_id": task, "passed": True,
            "plan": active_plan_ref, "source_plan": active["source_plan"], "source_qualification": source_ref,
            "plan_equivalence": eq_ref, "controls": source["controls"], "controls_replayed": False}
        ref = retain(RUN_ROOT / "qualifications" / (task + ".json"), wrapper)
        scorer.validate_qualification(ref, load(entry["original_config"]), active_plan_ref)
        qualifications[task] = {"status": "qualified", "qualification": ref, "reused_without_replay": True}
    snapshot = snapshot_score_evidence(active, active["source_plan"])
    value = {"version": VERSION, "plan": active_plan_ref, "source_plan": active["source_plan"],
        "diagnostic_equivalence": diagnostic, "plan_equivalence": eq_ref,
        "qualifications": qualifications, "snapshot_score": snapshot,
        "old_coordinator_plan": reference(BATCH_ROOT / "coordinator-plan.json"),
        "old_coordinator_summary": reference(BATCH_ROOT / "run-summary.json"),
        "remaining_new_generation": 13, "remaining_candidate_scores": 13,
        "deployment_recovery": deployment,
        "previous_continuation_plan": reference(BATCH_ROOT / "continuation/model-memory-r3/coordinator-plan.json"),
        "controls_to_replay": 0, "snapshot_scores_to_replay": 0,
        "sources": policy.sources()}
    return retain(RUN_ROOT / "reuse-evidence.json", value)
