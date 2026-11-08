"""Explicit dual-basis measurement admission; no fabricated provider precision.

This replaces only v156's requirement for exact provider-token source mapping.
All source, response, ledger and permission integrity gates remain required.
The module is pure and cannot launch a process or spend API funds.
"""
from __future__ import annotations

import copy
from decimal import Decimal

VERSION = "v157-dual-basis-communication-admission-r1"
REQUIRED_GATES = (
    "G0-1", "G0-2-payload-local-estimate", "G0-3", "G0-4",
    "G0-5", "G0-6", "G0-7", "G0-8",
)
DEPLOYMENT_GATES = (
    "real_SDK_source_capture",
    "shared_agent_condenser_compressor_budget",
    "physical_retry_and_cash_reconciliation",
    "immutable_publication_and_same_pull_permissions",
    "C0_existing_preview_preserved",
    "natural_message_fact_coverage",
    "separate_condition_and_scoring_identity",
    "frozen_panel_and_source_closure",
    "bounded_isolated_runtime",
    "zero_model_environment_admission",
)


def validate_amendment(grant):
    """Validate the user's new independent cash/measurement scope, not old funds."""
    if not isinstance(grant, dict):
        raise ValueError("A concrete user grant is required")
    required = {
        "version": VERSION,
        "source_attribution_basis": "local_fragment_estimate",
        "total_token_authority": "physical_provider_usage",
        "provider_exact_source_claim": False,
        "planned_tasks": 24,
        "planned_team_episodes": 72,
        "conditions": ["C0", "C1", "C2"],
        "organization_id": "REVIEW2",
        "team_input_output_token_cap": 5_000_000,
        "batch_input_output_token_upper_bound": 360_000_000,
        "cash_scope": "new_independent_shared_ledger",
        "old_ledgers_changed": False,
        "model_start_authorized": True,
        "completion_guaranteed_by_cash_cap": False,
    }
    if any(grant.get(key) != value for key, value in required.items()):
        raise ValueError("Grant does not match the approved 24-task/72-episode pilot")
    if Decimal(str(grant.get("cash_cap_CNY"))) != Decimal("500.00"):
        raise ValueError("The new pilot cash cap is exactly 500 CNY")
    if not grant.get("user_response") or not grant.get("answered_question"):
        raise ValueError("The explicit user response and its question must be retained")
    return copy.deepcopy(grant)


def assess_measurement(measurement, amendment):
    """Keep historical provider-exact failure visible while applying the revision."""
    validate_amendment(amendment)
    gates = measurement.get("gates", {})
    failed = [name for name in REQUIRED_GATES if gates.get(name) is not True]
    if measurement.get("payload_local_estimated_unattributed_fraction") is None:
        failed.append("missing_local_estimate_total")
    elif not 0 <= measurement["payload_local_estimated_unattributed_fraction"] <= 0.02:
        failed.append("local_estimate_unknown_exceeds_2pct")
    p95 = measurement.get("payload_local_estimated_request_p95")
    if p95 is None or not 0 <= p95 <= 0.05:
        failed.append("local_estimate_request_p95_exceeds_5pct")
    return {
        "version": VERSION,
        "passed": not failed,
        "failed_gates": failed,
        "basis": "API_total_exact_source_local_estimate",
        "original_gates": copy.deepcopy(gates),
        "provider_exact_source_gate_required": False,
        "provider_exact_source_gate_observed": gates.get("G0-2-provider-exact") is True,
        "provider_exact_source_claim": False,
        "historical_exact_gate_not_rewritten": True,
        "source_estimates_rescaled_to_provider_usage": False,
        "analytic_subaccounts_added_to_total": False,
        "strict_weight_freeze_claim": False,
    }


def assess_dispatch(measurement, amendment, deployment):
    """All bindings need concrete passing evidence in addition to user funding."""
    result = assess_measurement(measurement, amendment)
    missing = []
    for name in DEPLOYMENT_GATES:
        item = deployment.get(name)
        if (not isinstance(item, dict) or item.get("passed") is not True
                or not isinstance(item.get("evidence"), dict)
                or not item["evidence"].get("path")
                or not item["evidence"].get("sha256")):
            missing.append(name)
    return {**result,
            "passed": result["passed"] and not missing,
            "measurement_passed": result["passed"],
            "missing_deployment_gates": missing,
            "dispatch_enabled": result["passed"] and not missing,
            "deployment": copy.deepcopy(deployment),
            "cash_cap_CNY": "500.00",
            "real_model_calls_started": False}


def assess_wave(wave, measurement, amendment, *, planned_episodes, terminal_episodes,
                unresolved_attempts, frozen_source_verified, protocol_unchanged):
    """Score-blind between-wave gate. No score/success field is accepted here.

    Isolated temporary errors remain in the recovery inventory and do not by
    themselves block the next wave. Missing measurements or conflicting ledgers
    are different: they invalidate the measurement mechanism under comparison.
    """
    if wave != 1 or planned_episodes != 36:
        raise ValueError("The only between-wave gate follows the first 36 episodes")
    if not isinstance(unresolved_attempts, list):
        raise ValueError("Exceptions must be explicitly inventoried")
    result = assess_measurement(measurement, amendment)
    ready = (result["passed"] and terminal_episodes == planned_episodes
             and frozen_source_verified is True and protocol_unchanged is True)
    return {**result, "wave": wave, "advance_to_wave_2": ready,
            "planned_episodes": planned_episodes, "terminal_episodes": terminal_episodes,
            "exceptions_deferred": copy.deepcopy(unresolved_attempts),
            "scores_consulted": False, "strategy_changed_after_scores": False}
