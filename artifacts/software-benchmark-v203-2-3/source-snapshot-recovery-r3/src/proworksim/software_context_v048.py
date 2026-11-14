"""Frozen candidate 1: exact same-input field references after v041, before v028.

The prior library, world and feedback lifecycle are unchanged. This is a new
model-visible representation, not a claim of behavioral equivalence.
"""
from __future__ import annotations

import copy
import json

from . import software_context_v044 as previous
from .software_context_v028 import project_software_request as capacity_project
from .software_context_v034 import observation_messages
from .software_context_v041 import (
    MEMBER_SCOPE_FIELDS, _member_identity, _root_identity, deduplicate_static_snapshots,
)
from .software_feedback_v044 import project_format_feedback
from .storage import digest, json_bytes

VERSION = "software-context-v0.48-candidate-1"
CANDIDATE_VERSION = "same-input-exact-field-reference-v0.48-candidate-1"
CANDIDATE_SHA256 = "dec0b1cdbd0197be473f093341cb075c9f15cb3c8dc211980623aa113f631e29"
ALLOWLIST = (
    "/observation/architecture/stage_plan",
    "/observation/architecture/allowed_tools",
    "/observation/execution_condition/initial_members",
    "/observation/member_registry",
    "/observation/patches",
)
REFERENCE_KEY = "$same_input_ref"
REFERENCE_ANCHOR = "first_observation#"
PROTECTED_MARGIN_TOKENS = previous.PROTECTED_MARGIN_TOKENS
Gamma0Transport = previous.SoftwareContextTransport
project_gamma0_request = previous.project_software_request
_MISSING = object()


def presentation_identity(gamma="G1"):
    if gamma not in {"G0", "G1"}:
        raise ValueError("Only the two frozen v048 representations are declared")
    return {"gamma": gamma, "projection_version": VERSION if gamma == "G1" else previous.VERSION,
        "candidate_version": CANDIDATE_VERSION, "candidate_sha256": CANDIDATE_SHA256,
        "world_runtime_library": "v047", "feedback_library": "v044",
        "static_deduplication_library": "v041", "capacity_selector_library": "v028",
        "behavioral_equivalence_claimed": False}


def _get(payload, pointer):
    value = payload
    for key in pointer.split("/")[1:]:
        if not isinstance(value, dict) or key not in value:
            return _MISSING
        value = value[key]
    return value


def _set(payload, pointer, value):
    keys = pointer.split("/")[1:]
    parent = payload
    for key in keys[:-1]:
        parent = parent[key]
    parent[keys[-1]] = value


def _contains_reference(value):
    if isinstance(value, dict):
        return REFERENCE_KEY in value or any(_contains_reference(item) for item in value.values())
    return isinstance(value, list) and any(_contains_reference(item) for item in value)


def _strict_observations(request):
    """SDK already checked exact provenance; reject ambiguous JSON conservatively."""
    def pairs(rows):
        value = {}
        for key, item in rows:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = item
        return value

    observations = list(observation_messages(request))
    for index, _ in observations:
        try:
            payload = json.loads(request["messages"][index]["content"], object_pairs_hook=pairs)
            json_bytes(payload)
        except (ValueError, TypeError):
            return None
    return observations


def reference_equal_fields(request, *, source_request, member_id):
    """Project only the frozen five paths; bind roots before old static removal."""
    selected = copy.deepcopy(request)
    evidence = {"version": CANDIDATE_VERSION, "candidate_sha256": CANDIDATE_SHA256,
        "allowlist": list(ALLOWLIST), "reference_key": REFERENCE_KEY,
        "reference_anchor": REFERENCE_ANCHOR, "eligible": False,
        "generated_references": [], "retained_fields": [],
        "member_identity_fields": list(MEMBER_SCOPE_FIELDS),
        "input_request_sha256": digest(json_bytes(request))}
    original = _strict_observations(source_request)
    observations = _strict_observations(request)
    reason = None
    if original is None or observations is None:
        reason = "ambiguous_observation_json"
    elif len(original) != 2 or len(observations) != 2:
        reason = "requires_exactly_two_observations"
    elif [i for i, _ in original] != [i for i, _ in observations]:
        reason = "observation_positions_changed_before_reference"
    else:
        first_identity, latest_identity = [_member_identity(payload["observation"]) for _, payload in original]
        first_root, latest_root = [_root_identity(payload["observation"]) for _, payload in original]
        if (first_identity is None or latest_identity is None or not isinstance(member_id, str)
                or first_identity["actor_id"] != member_id or json_bytes(first_identity) != json_bytes(latest_identity)):
            reason = "member_identity_or_bound_member_differs"
        elif first_root is None or latest_root is None or json_bytes(first_root) != json_bytes(latest_root):
            reason = "original_root_identity_differs"
        elif any(json_bytes(_member_identity(payload["observation"])) != json_bytes(first_identity)
                 for _, payload in observations):
            reason = "member_identity_changed_during_static_projection"
    if reason is None:
        (first_index, first), (latest_index, latest) = observations
        evidence.update(eligible=True, member_identity=first_identity, root_identity=first_root,
            first_observation_index=first_index, latest_observation_index=latest_index)
        for path in ALLOWLIST:
            target, value = _get(first, path), _get(latest, path)
            if target is _MISSING or value is _MISSING:
                retained_reason = "missing_path"
            elif _contains_reference(target) or _contains_reference(value):
                retained_reason = "existing_structural_reference_marker"
            elif json_bytes(target) != json_bytes(value):
                retained_reason = "different_exact_value"
            else:
                reference = {REFERENCE_KEY: REFERENCE_ANCHOR + path}
                _set(latest, path, reference)
                evidence["generated_references"].append({"path": path,
                    "reference": reference, "value_sha256": digest(json_bytes(value)),
                    "value_bytes": len(json_bytes(value)), "first_observation_index": first_index,
                    "latest_observation_index": latest_index})
                continue
            evidence["retained_fields"].append({"path": path, "reason": retained_reason})
        if evidence["generated_references"]:
            selected["messages"][latest_index]["content"] = json.dumps(latest, ensure_ascii=False, allow_nan=False)
    evidence["ineligible_reason"] = reason
    evidence["referenced_request_sha256"] = digest(json_bytes(selected))
    validate_reference_projection(selected, request, list(range(len(request["messages"]))), evidence)
    return selected, evidence


def validate_reference_projection(selected, before_reference, selected_indices, evidence):
    """Resolve only generated markers, preserving preexisting task data markers."""
    expected = copy.deepcopy(before_reference)
    expected["messages"] = [copy.deepcopy(before_reference["messages"][index]) for index in selected_indices]
    resolved = copy.deepcopy(selected)
    references = evidence["generated_references"]
    if references:
        observations = _strict_observations(selected)
        if observations is None or len(observations) != 2:
            raise ValueError("Generated reference lacks both retained same-input observations")
        (first_index, first), (latest_index, latest) = observations
        if (selected_indices[first_index] != evidence["first_observation_index"]
                or selected_indices[latest_index] != evidence["latest_observation_index"]
                or any(json_bytes(_member_identity(payload["observation"])) != json_bytes(evidence["member_identity"])
                       for _, payload in observations)):
            raise ValueError("Generated reference target or member binding changed")
        for row in references:
            path = row["path"]
            if path not in ALLOWLIST or row["reference"] != {REFERENCE_KEY: REFERENCE_ANCHOR + path}:
                raise ValueError("Generated reference points outside the frozen allowlist")
            actual, value = _get(latest, path), _get(first, path)
            if (actual != row["reference"] or value is _MISSING or _contains_reference(value)
                    or digest(json_bytes(value)) != row["value_sha256"]):
                raise ValueError("Generated reference is dangling, nested or altered")
            _set(latest, path, copy.deepcopy(value))
        # The v041 latest JSON envelope may retain original whitespace. Restore
        # its text only after exact structural JSON-byte equality is established.
        expected_payload = json.loads(expected["messages"][latest_index]["content"])
        if json_bytes(latest) != json_bytes(expected_payload):
            raise ValueError("Resolved latest observation differs from the v041 input")
        resolved["messages"][latest_index]["content"] = expected["messages"][latest_index]["content"]
    if json_bytes(resolved) != json_bytes(expected):
        raise ValueError("Reference projection changed a nonallowlisted field or retained message")
    return {"passed": True, "generated_reference_count": len(references),
        "selected_indices": list(selected_indices), "restored_request_sha256": digest(json_bytes(resolved)),
        "target_retained_in_same_input": bool(references)}


def _protected_request(request):
    """Same complete-round rule as v042, without applying static projection twice."""
    messages = request["messages"]
    pairs, claimed = [], set()
    for index, message in enumerate(messages):
        calls = message.get("tool_calls") or []
        if message.get("role") != "assistant" or not calls:
            continue
        if len(calls) != 1 or index + 1 >= len(messages):
            raise ValueError("Expected one complete managed tool round")
        following = messages[index + 1]
        if following.get("role") != "tool" or following.get("tool_call_id") != calls[0]["id"]:
            raise ValueError("Tool result must match its actual assistant call")
        pairs.append((index, index + 1))
        claimed.add(index + 1)
    if any(message.get("role") == "tool" and index not in claimed for index, message in enumerate(messages)):
        raise ValueError("Cannot project an orphan tool result")
    removed = {index for pair in pairs[:-1] for index in pair}
    indices = [index for index in range(len(messages)) if index not in removed]
    selected = copy.deepcopy(request)
    selected["messages"] = [copy.deepcopy(messages[index]) for index in indices]
    return selected, {"selected_indices": indices, "removed_indices": sorted(removed),
        "complete_tool_rounds": [list(pair) for pair in pairs],
        "latest_complete_round_preserved": list(pairs[-1]) if pairs else None}


def _prepare(request, ledger, member_id):
    formatted, feedback = project_format_feedback(request, ledger=ledger, member_id=member_id)
    static, deduplication = deduplicate_static_snapshots(formatted)
    referenced, references = reference_equal_fields(static, source_request=formatted, member_id=member_id)
    return formatted, feedback, static, deduplication, referenced, references


def protected_software_request(request, *, ledger=None, member_id=None):
    _, feedback, static, deduplication, referenced, references = _prepare(request, ledger, member_id)
    protected, rounds = _protected_request(referenced)
    validation = validate_reference_projection(protected, static, rounds["selected_indices"], references)
    indices = [feedback["selected_indices"][i] for i in rounds["selected_indices"]]
    return protected, {"version": VERSION, "actual_presentation": presentation_identity(),
        "format_feedback_projection": feedback, "deduplication": deduplication,
        "same_input_references": references, "reference_validation": validation,
        "context_stage_projection": rounds, "selected_indices": indices,
        "removed_indices": [i for i in range(len(request["messages"])) if i not in indices],
        "request_sha256": digest(json_bytes(protected))}


def project_software_request(request, *, render, tokenizer, context_limit, ledger=None, member_id=None):
    formatted, feedback, static, deduplication, referenced, references = _prepare(request, ledger, member_id)
    selected, capacity = capacity_project(referenced, render=render, tokenizer=tokenizer, context_limit=context_limit)
    protected, rounds = _protected_request(referenced)
    selected_validation = validate_reference_projection(selected, static, capacity["selected_indices"], references)
    protected_validation = validate_reference_projection(protected, static, rounds["selected_indices"], references)
    protected_rendered, _, _ = render(protected)
    protected_ids = tokenizer(protected_rendered, add_special_tokens=False)["input_ids"]
    original_rendered, _, _ = render(request)
    formatted_rendered, _, _ = render(formatted)
    static_rendered, _, _ = render(static)
    mapping = feedback["selected_indices"]
    indices = [mapping[i] for i in capacity["selected_indices"]]
    protected_indices = [mapping[i] for i in rounds["selected_indices"]]
    headroom = context_limit - request["max_tokens"] - len(protected_ids)
    protected_evidence = {"version": VERSION, "format_feedback_projection": feedback,
        "context_stage_projection": rounds, "selected_indices": protected_indices,
        "removed_indices": [i for i in range(len(request["messages"])) if i not in protected_indices],
        "request_sha256": digest(json_bytes(protected)), "reference_validation": protected_validation}
    return selected, {**capacity, "version": VERSION, "actual_presentation": presentation_identity(),
        "inherited_context_version": previous.VERSION, "format_feedback_projection": feedback,
        "deduplication": deduplication, "same_input_references": references,
        "selected_reference_validation": selected_validation, "protected_reference_validation": protected_validation,
        "context_stage_projection": capacity, "inherited_capacity_projection": capacity,
        "original_request_sha256": digest(json_bytes(request)),
        "original_prompt_tokens": len(tokenizer(original_rendered, add_special_tokens=False)["input_ids"]),
        "format_projected_prompt_tokens_before_context": len(tokenizer(formatted_rendered, add_special_tokens=False)["input_ids"]),
        "static_prompt_tokens_before_references": len(tokenizer(static_rendered, add_special_tokens=False)["input_ids"]),
        "reference_projected_prompt_tokens_before_capacity": capacity["original_prompt_tokens"],
        "selected_indices": indices,
        "removed_indices": [i for i in range(len(request["messages"])) if i not in indices],
        "retained_messages_unchanged": all(message == request["messages"][i] for message, i in zip(selected["messages"], indices)),
        "protected_projection": protected_evidence, "protected_prompt_tokens": len(protected_ids),
        "protected_request_sha256": digest(json_bytes(protected)),
        "protected_input_ids_sha256": digest(json_bytes(protected_ids)),
        "protected_rendered_prompt_sha256": digest(protected_rendered.encode()),
        "protected_selected_indices": protected_indices, "protected_headroom_tokens": headroom,
        "protected_margin_tokens": PROTECTED_MARGIN_TOKENS,
        "protected_headroom_after_margin": headroom - PROTECTED_MARGIN_TOKENS,
        "index_scope": "Top-level indices map to original transport input; static/reference/capacity indices map to feedback-projected input. Reference anchor is the retained first observation, never an absolute index.",
        "scope": "Frozen G1 candidate1: v044 feedback, unchanged v041 static removal, five exact same-input field references, unchanged v028 round selection. Full latest feedback/pages and all nonallowlisted fields preserved. Margin is diagnostic only."}


class SoftwareContextTransport(previous.SoftwareContextTransport):
    """Reuse original turn binding, budget seal, dispatch, archive and accounting."""
    def _project(self, request):
        if self._turn is None:
            raise ValueError("v048 context preparation requires its bound runner turn")
        return project_software_request(request, render=self.owner.prepare_request,
            tokenizer=self.owner.tokenizer, context_limit=self.owner.recipe["max_length"],
            ledger=self.feedback_ledger, member_id=self._turn["member_id"])
