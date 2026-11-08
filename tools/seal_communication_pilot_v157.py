"""Seal the already authorized pilot only after actual readiness evidence exists."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

from proworksim import software_benchmark_scope_v157 as scope
from proworksim.software_benchmark_alignment_contract_v157 import VERSION as ALIGNMENT
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_communication_admission_v157 import (
    assess_dispatch, validate_amendment,
)


def passed(path):
    ref = reference(path)
    value = scope.load(ref)
    if value.get("passed") is not True:
        raise ValueError("Required evidence has not passed: "+str(path))
    return ref, value


def local_tool(name):
    spec = importlib.util.spec_from_file_location(name, scope.ROOT/"tools"/(name+".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def seal(deployment_controls, integration_review):
    if scope.AUTH_FILE.exists() or scope.LEDGER_FILE.exists():
        raise PermissionError("Never reseal an authorized or accounted experiment")
    from proworksim.software_benchmark_diagnostics_v157 import validate_preparation
    from proworksim.software_benchmark_grading_v157 import validate_environment_preparation
    from proworksim.software_benchmark_host_api_v157 import prepare_schemas
    source_closure = local_tool("seal_role_pilot_v143").source_closure
    prepare_unit = local_tool("launch_communication_pilot_v157").prepare

    base = scope.ARTIFACT_ROOT
    amendment_ref = reference(base/"user-amendment-r1/authorization.json")
    amendment = validate_amendment(scope.load(amendment_ref))
    physical_ref = reference(base/"physical-source-admission-r1/summary.json")
    physical = scope.load(physical_ref)
    if physical.get("revised_measurement_admission", {}).get("passed") is not True:
        raise ValueError("Actual-SDK physical capture has not passed revised measurement admission")
    sdk_ref, _ = passed(base/"communication-sdk-r4/summary.json")
    budget_ref, _ = passed(base/"budget-controls-r1/summary.json")
    runtime_ref = reference(base/"communication-runtime-controls-r1/summary.json")
    runtime_control = scope.load(runtime_ref)
    if (runtime_control.get('CPU_unit_tests', {}).get('passed') != 7
            or runtime_control.get('API_calls') != 0):
        raise ValueError('The seven runtime mechanism controls have not passed')
    deployment_ref, _ = passed(deployment_controls)
    review_ref, review = passed(integration_review)
    if review.get("unresolved_blocking_findings"):
        raise ValueError("Independent review still has a blocking integration finding")
    diagnostics = validate_preparation()
    environment = validate_environment_preparation()
    if (diagnostics.get("passed") is not True or environment.get("passed") is not True
            or len(environment.get("qualifications", {})) != 24):
        raise ValueError("The complete fixed panel lacks actual environment admission evidence")
    diagnostic_ref = reference(scope.PREPARATION_QUALIFICATION_FILE)
    environment_ref = scope.retain(base/"final-admission-r1/environment.json", environment)
    bundle_ref = reference(scope.ROOT/"runs/software-benchmark-v157/sdk-bundle-r1/manifest.json")
    bundle = scope.load(bundle_ref)
    probe = bundle.get("probe", {})
    if (probe.get("model_calls") != 0
            or set(probe.get("organization_ids", [])) != {"C0", "C1", "C2"}
            or probe.get("all_controller_and_worker_entrypoints_imported") is not True):
        raise ValueError("The actual isolated SDK bundle was not qualified")
    schemas = prepare_schemas()
    unit = prepare_unit()["specification"]
    roots = [p for folder in ("src/proworksim", "tools")
             for p in (scope.ROOT/folder).glob("*v157.py")]
    roots.append(scope.ROOT/"tools/run_offline_scorer_v096.py")
    files = source_closure(scope.ROOT, roots=roots)
    source = scope.retain(scope.SOURCE_FILE, {"version": scope.VERSION, "files": files,
        "bundle": bundle_ref, "frozen_before_formal_model_call": True})
    binding_refs = {
        "real_SDK_source_capture": physical_ref,
        "shared_agent_condenser_compressor_budget": budget_ref,
        "physical_retry_and_cash_reconciliation": physical_ref,
        "immutable_publication_and_same_pull_permissions": runtime_ref,
        "C0_existing_preview_preserved": sdk_ref,
        "natural_message_fact_coverage": runtime_ref,
        "separate_condition_and_scoring_identity": deployment_ref,
        "frozen_panel_and_source_closure": source,
        "bounded_isolated_runtime": diagnostic_ref,
        "zero_model_environment_admission": environment_ref,
    }
    gate = assess_dispatch(physical, amendment, {
        k: {"passed": True, "evidence": v} for k, v in binding_refs.items()})
    gate.update(source_token_mode="estimated_provider_total_authoritative",
                independent_review=review_ref, actual_container_diagnostics=diagnostic_ref,
                control_evidence_not_model_capability_result=True,
                initial_activation_wave=1,
                qualified_environment_count=environment.get('qualified_count', 24),
                environment_blocked_tasks=environment.get('blocked_tasks', []),
                unqualified_tasks_not_dispatched_or_counted_as_model_failures=True)
    if not gate["dispatch_enabled"]:
        raise ValueError("All actual deployment and revised measurement gates must pass")
    gate_ref = scope.retain(base/"final-admission-r1/gate.json", gate)
    grant = scope.retain(scope.USER_GRANT_FILE, {"approved": True, "API_cash_cap_CNY": "500.00",
        "actual_user_reply": amendment["user_response"], "measurement_and_cash_amendment": amendment_ref,
        "standing_non_disruptive_Docker_permission": reference(scope.STANDING_POLICY_FILE),
        "new_shared_host_root_configuration_authorized": False})
    proposal = scope.retain(scope.PROPOSAL_FILE, {"version": scope.VERSION, "plan": reference(scope.PLAN_FILE),
        "source_index": source, "user_grant": grant, "gate": gate_ref,
        "constraints": scope.CONSTRAINTS, "new_independent_cash_cap_CNY": "500.00",
        "API_model": "deepseek-flash", "thinking": False, "conditions": ["C0", "C1", "C2"],
        "fixed_organization": "REVIEW2", "planned_tasks": 24, "planned_team_episodes": 72,
        "waves": 2, "team_input_output_cap": 5_000_000, "upper_token_budget": 360_000_000,
        "scoring_async": True, "wave_gate_reads_scores": False,
        "old_ledgers_changed": False, "shared_host_configuration_changes": 0,
        "diagnostics_reused_not_replayed": diagnostics, "environment": environment_ref,
        "tool_schemas": schemas, "coordinator_unit": unit, "bundle": bundle_ref})
    authority = scope.retain(scope.AUTH_FILE, {"version": scope.VERSION, "status": "approved",
        "execution_alignment_version": ALIGNMENT, "plan": reference(scope.PLAN_FILE),
        "source_index": source, "proposal": proposal, "user_grant": grant,
        "gate": gate_ref, "API_cash_cap_CNY": "500.00", "constraints": scope.CONSTRAINTS,
        "shared_host_configuration_changes": 0})
    return {"authority": authority, "proposal": proposal, "gate": gate_ref,
            "source_index": source, "model_calls": 0, "launch_performed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--deployment-controls", type=Path, required=True)
    parser.add_argument("--integration-review", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(seal(args.deployment_controls, args.integration_review), ensure_ascii=False))
