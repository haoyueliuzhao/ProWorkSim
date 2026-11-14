"""Preparation-only specification for aligned single-agent execution strategies.

This is not a run plan or a new API/Docker grant. It contains no credentials,
task selection, hidden evaluator material, or dispatch implementation.
"""
from __future__ import annotations

import copy
import re

from . import software_benchmark_deepseek_contract_v105 as model_contract
from .software_benchmark_native_control_v062 import FINISH_REVIEW
from .storage import digest

VERSION = "v110-single-agent-strategy-alignment-r1"
SDK_VERSION = "1.49.6"
CONDENSER_PARAMETERS = {
    "max_size": 80,
    "keep_first": 4,
    "max_tokens": None,
    "hard_reset_retries": 1,
}
WORKFLOW_GUIDANCE = """Repair and verification workflow:
- Derive a short checklist from the issue's requested behaviors, public interfaces and edge cases. Check each separately against the implementation.
- Read the public repository documentation and tests to choose focused public tests or reproductions. Use the supplied public execution context and the available documented test entrypoint.
- Derive expected behavior from the issue and public contract independently of the current patch. A test that merely reproduces the patch's output does not establish correctness.
- Follow the actual tools' schemas. Record command failures, collection errors, missing dependencies and unexecuted tests accurately. A broad public test failure is not hidden evaluation feedback.
- Before ending, compare the current patch and public evidence against the checklist. Reuse sufficient same-version evidence instead of repeating an identical test without a reason.
All actions, self-review and history summarization share this task's original cumulative token, attempt, decision and time limits."""


def shared_strategy():
    return {
        "version": VERSION,
        "SDK_version": SDK_VERSION,
        "final_review": {"maximum": 1, "message_sha256": digest(FINISH_REVIEW.encode()),
                         "same_conversation": True, "budget_reset": False,
                         "accepted_episode_stop_may_resume": False},
        "history": {"kind": "LLMSummarizingCondenser", **CONDENSER_PARAMETERS,
                    "usage_id": "condenser", "same_model_and_token_pool": True,
                    "counts_as_model_attempt": True, "counts_as_agent_decision": False,
                    "source": "current_member_conversation_only",
                    "protect_unpresented_input_and_latest_complete_tool_round": True,
                    "derived_summary_is_authoritative_evidence": False,
                    "summary_failure_blocks_later_dispatch": True},
        "public_tests": {"selector_contract": "v110", "hidden_test_selection": False,
                         "fixed_task_interpreter_and_cwd": True,
                         "arbitrary_shell_added_to_PROJECT": False},
        "workflow_guidance_sha256": digest(WORKFLOW_GUIDANCE.encode()),
    }


def condition(arm):
    base = model_contract.condition(arm)
    name = f"DEEPSEEK_NT_{arm}_ALIGNED_B5000K"
    return {**base, "version": "v110-aligned-interface-condition-r1",
            "condition_id": name, "group_id": name,
            "execution_strategy": shared_strategy(),
            "retained_interface_differences": {
                "tool_family": "native" if arm == "REF" else "managed",
                "stuck_detection": arm == "REF",
                "maximum_stuck_corrections": 2 if arm == "REF" else 0,
                "explicit_same_version_delivery": arm == "PROJECT",
            }}


def validate_condition(value):
    if not isinstance(value, dict) or value != condition(value.get("arm")):
        raise ValueError("The aligned model/resources/strategy or declared interface boundary changed")
    return {**value["episode_limits"], "context_limit": model_contract.CONTEXT_TOKENS}


def validate_plan_identity(row):
    """Reject stale experiment identities before any capacity/resource claim."""
    arm = row.get('arm')
    if arm not in {'REF', 'PROJECT'}:
        raise ValueError('Only the new REF/PROJECT plan identities are allowed')
    expected = condition(arm)
    task, seed = row.get('instance_id'), row.get('seed')
    if (not isinstance(task, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-\d+', task)
            or type(seed) is not int or seed < 0
            or row.get('condition_id') != expected['condition_id']
            or row.get('slot_id') != f"v110:{task}:{expected['condition_id']}:{seed}"
            or row.get('execution_arm') != arm):
        raise ValueError('Bind a new v110 task, arm, condition and seed before resource admission')
    return row


def validate_controller_identity(config, arm):
    expected = condition(arm)
    task = config.get('public_task', {}).get('instance_id')
    seed = config.get('seed')
    if (not isinstance(task, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-\d+', task)
            or type(seed) is not int or seed < 0
            or config.get('condition_id') != expected['condition_id']
            or config.get('slot_id') != f"v110:{task}:{expected['condition_id']}:{seed}"
            or config.get('execution_alignment') != shared_strategy()
            or not isinstance(config.get('public_test_contract_sha256'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', config['public_test_contract_sha256'])):
        raise ValueError('Bind a new v110 identity and the exact shared/public-test contracts')
    return config


def initial_message(problem_statement, *, public_context=""):
    if not isinstance(problem_statement, str) or not problem_statement.strip():
        raise ValueError("The unchanged public problem statement is required")
    if not isinstance(public_context, str):
        raise TypeError("Public context must be admitted text")
    return "\n\n".join(part for part in (problem_statement, WORKFLOW_GUIDANCE, public_context) if part)


def preparation_profile():
    return {"version": VERSION, "implementation_only": True,
            "execution_authorized": False, "new_model_calls_authorized": 0,
            "new_Docker_objects_authorized": 0, "cash_budget": None,
            "panel": None, "seeds": None,
            "conditions": {arm: copy.deepcopy(condition(arm)) for arm in ("REF", "PROJECT")}}
