"""S1, FREE2 and REVIEW2 on one managed repository and accounting contract.

This is an implementation contract, not permission to run paid evaluations.
Roles affect instructions and the explicitly declared REVIEW2 delivery gate;
they never create new filesystem, process, network or controller authority.
"""
from __future__ import annotations

import copy
import hashlib
import json

VERSION = "v141-s1-free2-review2-contract-r1"
GROUP_IDS = ("S1", "FREE2", "REVIEW2")
MEMBER_COUNTS = {"S1": 1, "FREE2": 2, "REVIEW2": 2}
MEMBER_POOL = ("member_001", "member_002")
DELIVERY_MEMBER = MEMBER_POOL[0]
TEAM_TOKEN_BUDGET = 5_000_000


def organization(group):
    if group not in GROUP_IDS:
        raise ValueError("Only S1, FREE2 and REVIEW2 are in this implementation contract")
    members = list(MEMBER_POOL[:MEMBER_COUNTS[group]])
    if group == "S1":
        titles = [("独立成员", "Locate, implement, verify and deliver the unchanged issue yourself.")]
        mechanism = "single_member_managed_baseline"
        instruction = "There is one actual member and no hidden collaborator."
    elif group == "FREE2":
        titles = [("自主协作者", "Choose and explicitly describe your own contribution and collaborate as useful.")]*2
        mechanism = "self_declared_responsibilities_without_fixed_role_gates"
        instruction = ("No manager, developer or reviewer role is assigned in advance. Both members may "
            "locate, implement, test, review and integrate with the same managed permissions. "
            "Use explicit task ownership transfers when needed. A role declaration is coordination, not authority.")
    else:
        titles = [("开发兼交付", "Locate, design and implement; publish the exact final candidate for independent review."),
                  ("独立复核", "Independently adopt and test the author's fixed candidate, then accept or request changes.")]
        mechanism = "candidate_version_independent_review"
        instruction = ("member_001 develops and delivers; member_002 independently reviews the exact "
            "fixed author candidate. An accepted review requires actual adoption and same-version public "
            "test execution. Editing the author version requires another fixed candidate and review.")
    return {
        "version": VERSION, "id": group, "name": group,
        "fixed_members": members, "member_count": len(members),
        "roles": {member: {"title": title, "instruction": text}
                  for member, (title, text) in zip(members, titles, strict=True)},
        "communication_edges": [[a, b] for a in members for b in members if a != b],
        "delivery_member": DELIVERY_MEMBER,
        "phases": [{"name": "shared-budget-fair-opportunities", "active_members": members,
                    "opportunities": len(members)}],
        "mechanism": mechanism, "organization_instruction": instruction,
        "independent_review_required_for_delivery": group == "REVIEW2",
        "declarations_override_frozen_roles": group == "FREE2",
        "role_file_ACLs_unchanged": True, "public_task_board_is_shared": True,
        "role_descriptions_are_instructions_not_new_tool_powers": True,
        "schedule_semantics": "All fixed live members eligible; fair scheduler controls actual opportunities.",
        "automatic_merge_test_accept_submit": False,
        "formal_execution_authorized": False,
    }


get_organization = organization


def validate_organization(spec):
    if not isinstance(spec, dict) or spec != organization(spec.get("id")):
        raise ValueError("The role baseline, fixed roster or explicit acceptance rule changed")
    return copy.deepcopy(spec)


def catalog():
    return [organization(group) for group in GROUP_IDS]


def catalog_sha256():
    return hashlib.sha256(json.dumps(catalog(), sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def condition(group):
    """Small provider/runtime view; it deliberately grants no runtime resources."""
    return organization(group)


def shared_strategy(group):
    return {"version": VERSION, "organization_id": group,
            "fixed_members": organization(group)["fixed_members"],
            "shared_team_token_budget": TEAM_TOKEN_BUDGET,
            "context": 131072, "max_input": 98304, "max_output": 32768,
            "thinking": False, "private_member_histories": True,
            "shared_source_and_managed_file_permissions": True,
            "final_code_member": DELIVERY_MEMBER,
            "independent_review_required_for_delivery": group == "REVIEW2",
            "model_calls_authorized_by_this_contract": 0}
