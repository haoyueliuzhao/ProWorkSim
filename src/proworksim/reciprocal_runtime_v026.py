"""New C1 work protocol; unchanged shared actor, policy parser and role scheduler."""

import copy
import json
import types
import uuid
from pathlib import Path

from .core.journal import canonical_digest
from .deterministic_work_v024 import (
    DeterministicCompactWorkModelPolicy,
    DeterministicWorkInterface,
    _operation_identity,
)
from .experience import ExperienceRecorder, capture_port
from .online_collection import _config
from .staff_runtime import StaffRuntime
from .storage import atomic_write, digest, json_bytes

VERSION = "reciprocal-work-runtime-v0.26"
CONDITIONS = ("normal", "single_pass")


class ReciprocalCompactPolicy(DeterministicCompactWorkModelPolicy):
    """Only coalesce equal public contracts and omit role-history audit hashes.

    No world access, tool-result edits, new reads, task solutions or selection by
    reward. Every retained tool message remains exactly as actually returned.
    """

    def _select_messages(self, memory):
        messages, inherited = super()._select_messages(memory)
        result = copy.deepcopy(messages)
        changes = []
        for index, message in enumerate(result):
            if message.get("role") != "user":
                continue
            try:
                body = json.loads(message.get("content", ""))
            except (ValueError, TypeError):
                continue
            if not isinstance(body, dict) or not isinstance(body.get("observation"), dict):
                continue
            observation = body["observation"]
            works = list(observation.get("work_items", {}).values())
            shared = {}
            if len(works) > 1 and "shared_work_contract" not in observation:
                for field in ("goal",):
                    values = [work.get(field) for work in works]
                    if (
                        values[0] is not None
                        and not any(field + "_reference" in work for work in works)
                        and all(
                            canonical_digest(value) == canonical_digest(values[0])
                            for value in values
                        )
                    ):
                        shared[field] = copy.deepcopy(values[0])
                        for work in works:
                            del work[field]
                            work[field + "_reference"] = "observation.shared_work_contract." + field
                for field in ("online_scope", "public_format"):
                    requirements = [work.get("requirements", {}) for work in works]
                    values = [req.get(field) for req in requirements]
                    if (
                        values[0] is not None
                        and not any(field + "_reference" in req for req in requirements)
                        and all(
                            canonical_digest(value) == canonical_digest(values[0])
                            for value in values
                        )
                    ):
                        shared[field] = copy.deepcopy(values[0])
                        for req in requirements:
                            del req[field]
                            req[field + "_reference"] = "observation.shared_work_contract." + field
            if shared:
                observation["shared_work_contract"] = shared
            for work in works:
                if (
                    "visible_requirements_reference" not in work
                    and isinstance(body.get("role_task"), str)
                    and work.get("visible_requirements") == [body["role_task"]]
                ):
                    work.pop("visible_requirements")
                    work["visible_requirements_reference"] = "role_task"
            for action in body.get("own_action_history", []):
                for key in ("arguments_sha256", "response_sha256", "original_message_index"):
                    action.pop(key, None)
                for key in ("control_status", "reference", "submission_id"):
                    if action.get(key) is None:
                        action.pop(key, None)
            body["presentation_note"] = (
                "Shared work contract fields above apply by exact reference to both works; only identical text was coalesced. "
                "Own action history keeps tools, scoped arguments, results and references; audit-only hashes/indexes remain in the archive. "
                "All retained real tool messages are unchanged. No private fact, selected evidence or work action is supplied by this view."
            )
            message["content"] = json.dumps(
                body, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            )
            changes.append(index)
        # Input-consumption evidence can still compare exact actual tool bytes.
        assert [m for m in result if m.get("role") == "tool"] == [
            m for m in messages if m.get("role") == "tool"
        ]
        audit = {
            "version": "reciprocal-role-local-view-v0.26",
            "parent_selection": inherited,
            "selected_messages_sha256": digest(json_bytes(result)),
            "changed_user_message_indices": changes,
            "all_selected_tool_messages_unchanged": True,
            "scope": "Exact public contract duplicates and audit-only action-history metadata; no content summarization or tool-result rewriting.",
        }
        return result, audit


def runtime(owner, prepared, folder, condition, *, episode_key):
    if condition not in CONDITIONS:
        raise ValueError("Unknown frozen communication condition")
    folder = Path(folder)
    # The caller supplies only the paired repetition seed, never a hidden case
    # ID or private value. Counterfactual states retain actual separate worlds.
    namespace = [VERSION, prepared.case["prototype"], str(episode_key)]
    prepared.world._v024_namespace = namespace
    prepared.world._operation_identity = types.MethodType(_operation_identity, prepared.world)
    policies, ports, captures, interfaces = {}, {}, {}, {}
    variant = "v26_normal" if condition == "normal" else "v26_single_pass"
    for role in prepared.scenario["roles"]:
        label = role["role_id"]
        interface = DeterministicWorkInterface(
            prepared.world.session(role["actor"], role["project"]),
            label,
            audit_dir=folder / "public-projections" / label,
            variant=variant,
            presentation="compact_v14",
        )
        interfaces[label] = interface
        ports[label] = capture_port(interface, captures.setdefault(label, []))
        config = _config(
            owner, label, role["config"]["task"], prepared.case["role_decision_limits"]
        )
        policies[label] = ReciprocalCompactPolicy(
            config,
            visible_namespace=namespace,
            transport=owner.transport,
            audit_dir=folder / "model-calls" / label,
        )
        role.update(policy="model", config=copy.deepcopy(policies[label].config))
    prepared.scenario["variation"]["communication_condition"] = condition
    run = StaffRuntime(
        ports,
        policies,
        recorder=ExperienceRecorder(),
        run_id="v026-" + canonical_digest(namespace)[:24],
    )
    atomic_write(
        folder / "visible-identity.json",
        json_bytes(
            {
                "version": VERSION,
                "visible_namespace": namespace,
                "communication_condition": condition,
                "visible_runtime_id": run.run_id,
                "actual_run_id": uuid.uuid4().hex,
                "actual_instance_id": prepared.world.state["instance_id"],
                "actual_branch_id": prepared.world.state["branch_id"],
                "scope": "Counterfactual variants share neutral public names; actual world IDs remain separate. Communication conditions keep the same business tools and decision/output budget. Extra communication restrictions are declared, not hidden.",
            }
        ),
    )
    return run, captures, interfaces
