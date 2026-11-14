"""Common inference and managed permissions for the three P0/P1 baselines.

The implementation is v141; only the separately authorized v203.2.1 pilot may use
the concrete model identities. This module creates no paid or Docker authority.
"""
from __future__ import annotations

import copy
import re

from . import software_benchmark_alignment_contract_v130 as single
from . import software_role_baseline_contract_v141 as roles
from .storage import digest, json_bytes

VERSION = "v141-common-s1-free2-review2-execution-r1"
RUN_VERSION = "v203.2.1"
GROUP_IDS = ("REVIEW2",)
TEAM_TOKEN_BUDGET = roles.TEAM_TOKEN_BUDGET


def organization(group):
    return roles.organization(group)


def shared_strategy(group):
    spec = organization(group)
    value = single.shared_strategy()
    value.update(version=VERSION)
    value["final_review"].update(
        maximum=spec["member_count"], maximum_per_member=1,
        scope="once_per_member_per_episode", shared_pool=True)
    value["history"].update(
        scope="one_private_conversation_per_member",
        other_members_private_history_visible=False)
    value["public_tests"].update(
        result_evidence_revision="v141-session-bound-public-test-execution-r1",
        command_root_and_nested_sessions_separate=True,
        dependency_compatibility_revision="v130")
    value["organization"] = {
        "id": group, "member_count": spec["member_count"],
        "specification_sha256": digest(json_bytes(spec)),
        "fixed_roster": True, "dynamic_membership": False,
        "schedule": "same_fair_round_robin_single_writer",
        "role_declarations_change_authority": False,
        "independent_review_required_for_delivery": group == "REVIEW2",
        "delivery_member": "member_001", "best_of_members": False,
        "automatic_merge_test_accept_submit": False,
        "member_done_is_team_done": False,
        "foreign_organization_stage_gates": False,
    }
    value["observability"] = {
        "version": "v141", "solver_sees_other_private_histories": False,
        "measurement_only_model_calls": 0,
        "unknown_information_receipt_is_not_zero": True,
        "whole_request_attribution_is_net_communication_cost": False,
    }
    return value


def condition(group):
    spec = organization(group)
    value = single.condition("PROJECT")
    value.update(
        version="v141-role-baseline-condition-r1",
        condition_id=f"DEEPSEEK_NT_{group}_V141_B5000K",
        group_id=group, organization_id=group,
        single_agent=spec["member_count"] == 1,
        fixed_members=spec["fixed_members"], member_count=spec["member_count"],
        fixed_organization=spec, execution_strategy=shared_strategy(group),
        code_endpoint="member_001_terminal_code",
        delivery_endpoint="member_001_last_legal_delivery",
        primary_business_endpoint="official_legal_delivery",
        code_endpoint_is_separate=True,
    )
    value["episode_limits"]["input_plus_output_tokens"] = TEAM_TOKEN_BUDGET
    value["retained_interface_differences"].update(
        tool_family="managed_role_baseline",
        organization_contracts_enforced=True,
        base_tool_permissions_shared=True,
        review_acceptance_gate_is_an_explicit_treatment=group == "REVIEW2")
    return value


def validate_condition(value):
    if not isinstance(value, dict) or value != condition(value.get("organization_id")):
        raise ValueError("The model, shared budget, private contexts or explicit role policy changed")
    return {**value["episode_limits"], "context_limit": value["inference"]["total_context"]}


def validate_plan_identity(row):
    expected = condition(row.get("organization_id"))
    task, seed = row.get("instance_id"), row.get("seed")
    if (not isinstance(task, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-\d+", task)
            or type(seed) is not int or seed < 0
            or row.get("group_id") != expected["group_id"]
            or row.get("condition_id") != expected["condition_id"]
            or row.get("slot_id") != f"{RUN_VERSION}:{task}:{expected['condition_id']}:{seed}"
            or row.get("arm") != "PROJECT" or row.get("execution_arm") != "PROJECT"
            or row.get("fixed_members") != expected["fixed_members"]
            or row.get("member_count") != expected["member_count"]):
        raise ValueError("A pilot row must bind the original issue, new attempt and actual member roster")
    return row


def validate_controller_identity(config, arm="PROJECT"):
    validate_plan_identity({**config, "instance_id": config.get("public_task", {}).get("instance_id"), "arm": arm})
    if (arm != "PROJECT"
            or config.get("execution_alignment") != shared_strategy(config["organization_id"])
            or not re.fullmatch(r"[0-9a-f]{64}", config.get("public_test_contract_sha256", ""))):
        raise ValueError("The controller must use its new frozen strategy and exact public-test contract")
    return config


def initial_message(problem_statement, *, public_context=""):
    return single.initial_message(problem_statement, public_context=public_context)


def preparation_profile():
    return {
        "version": VERSION, "implementation_only": True,
        "execution_authorized": False,
        "conditions": {group: copy.deepcopy(condition(group)) for group in GROUP_IDS},
        "parameter_training": False, "RSI_updates": False, "compression_treatment": False,
    }
