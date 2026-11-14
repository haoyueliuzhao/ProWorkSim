"""Offline K0/K1/K2 selection over an already-presented private history.

This module neither reads the World nor installs a runtime hook. The caller must
supply trusted presentation receipts and pre-existing private-reader references.
Candidate labels are checked against exact JSON values in those observations;
being authorized to read a source alone does not make it eligible here.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Callable, Mapping, Sequence

from .software_context_compression_v175 import is_observation

VERSION = "v203.2.3-role-context-selector-r2"
CONDITIONS = ("K0", "K1", "K2")
ROLES = ("developer", "reviewer", "delivery")
METADATA = {"kind", "version", "paths", "responsibility"}
V117_MARKER = "_v117_same_input_static_fields"
EVIDENCE_KEY = "_v203_2_3_retained_observed_evidence"
NOTICE_KEY = "_v203_2_3_history_selection"
STRUCTURAL_KINDS = {
    "/observation/current_version_test_coverage": "test",
    "/observation/delivery_status": "delivery",
    "/observation/messages": "message",
    "/observation/handoffs": "handoff",
    "/observation/patches": "diff",
    "/observation/all_fixed_patches": "diff",
    "/observation/fixed_organization/all_fixed_patches": "diff",
    "/observation/organization_protocol": "review_feedback",
    "/observation/workspace_reference": "version",
}
ROLE_KINDS = {
    "developer": {"diagnostic": 12, "review_feedback": 12, "code": 8, "diff": 6,
                  "message": 8, "handoff": 10,
                  "read_task": 6, "read_file": 8, "write_file": 12, "fix_patch": 12},
    "reviewer": {"diff": 12, "test": 12, "risk": 12, "review_feedback": 8,
                 "message": 4, "handoff": 6,
                 "run_tests": 12, "org_review_patch": 12},
    "delivery": {"delivery": 12, "test": 12, "risk": 12, "diff": 6,
                 "message": 4, "handoff": 10,
                 "submit_integration": 12, "run_tests": 8},
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def estimate_tokens(text: str) -> int:
    """Deterministic UTF-8 byte/4 heuristic, never a provider token measurement."""
    return (len(text.encode("utf-8")) + 3) // 4


@dataclass(frozen=True)
class PresentedSource:
    source_id: str
    episode: str
    member: str
    message_index: int
    presented_step: int
    message: Mapping
    reference: str
    origin_domain: str = "member_history"
    owner_member: str | None = None
    published: bool = False


@dataclass(frozen=True)
class Candidate:
    source_id: str
    start: int = 0
    end: int | None = None
    metadata_pointers: Mapping[str, str] = field(default_factory=dict)
    protected: bool = False
    field_pointer: str | None = None


class SourceRejected(ValueError):
    """A candidate has no verified source in this presented private prefix."""


def _reference(reference):
    if not isinstance(reference, str):
        raise SourceRejected("A source-bound full-text reference is required")
    if reference.startswith("ctx:"):
        return {"kind": "private_reader"}
    match = re.fullmatch(r"v117:([0-9a-f]{64}):(\d+):([0-9a-f]{64})", reference)
    if match:
        return {"kind": "v117_same_input", "original_content_sha256": match[1],
                "anchor_message_index": int(match[2]), "anchor_content_sha256": match[3]}
    raise SourceRejected("Unrecognized source-bound full-text reference")


def _pointer(value, pointer):
    if pointer == "":
        return value
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise SourceRejected("Metadata needs a JSON pointer into the original observation")
    try:
        for part in pointer[1:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            value = value[int(part)] if isinstance(value, list) else value[part]
    except (KeyError, IndexError, ValueError, TypeError) as error:
        raise SourceRejected("Metadata pointer is absent from the original observation") from error
    return value


def _tokens(text):
    return set(re.findall(r"[\w./-]+", text.lower()))


def _count(count, text):
    result = count(text)
    if type(result) is not int or result < 0:
        raise ValueError("Token estimator must return a nonnegative integer")
    return result


def _pool(sources, candidates, *, episode, member, decision_step):
    known = {}
    for source in sources:
        if source.source_id in known:
            raise SourceRejected("Duplicate source identity")
        known[source.source_id] = source
    rows = []
    seen = set()
    for candidate in candidates:
        source = known.get(candidate.source_id)
        if source is None:
            raise SourceRejected("Candidate has no presentation receipt")
        if source.episode != episode or source.member != member:
            raise SourceRejected("Cross-episode or cross-member source")
        if source.origin_domain != "member_history":
            raise SourceRejected("Evaluator, hidden, and other non-history sources are forbidden")
        if type(source.presented_step) is not int or not 0 <= source.presented_step <= decision_step:
            raise SourceRejected("Future or invalid presentation receipt")
        if source.owner_member not in (None, member) and not source.published:
            raise SourceRejected("Another member's unpublished private material")
        if type(source.message_index) is not int or source.message_index < 0:
            raise SourceRejected("Invalid source message index")
        text = source.message.get("content")
        if not is_observation(source.message):
            raise SourceRejected("Only already-presented observations may be selected")
        reference = _reference(source.reference)
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        if reference["kind"] == "v117_same_input" and reference["original_content_sha256"] != content_hash:
            raise SourceRejected("v117 reference does not identify this exact original content")
        end = len(text) if candidate.end is None else candidate.end
        if type(candidate.start) is not int or type(end) is not int or not 0 <= candidate.start < end <= len(text):
            raise SourceRejected("Candidate must be a nonempty exact source span")
        if set(candidate.metadata_pointers) - METADATA:
            raise SourceRejected("Unsupported ranking metadata")
        metadata = {}
        if candidate.metadata_pointers or candidate.field_pointer is not None:
            try:
                parsed = json.loads(text)
            except (ValueError, TypeError) as error:
                raise SourceRejected("Ranking metadata needs a structured source") from error
            metadata = {key: _pointer(parsed, pointer) for key, pointer in candidate.metadata_pointers.items()}
        if candidate.field_pointer is not None:
            if candidate.field_pointer not in STRUCTURAL_KINDS:
                raise SourceRejected("Structural kind requires an allowlisted observed field")
            try:
                excerpt = json.loads(text[candidate.start:end])
            except ValueError as error:
                raise SourceRejected("Field card must retain the entire JSON value") from error
            if canonical(excerpt) != canonical(_pointer(parsed, candidate.field_pointer)):
                raise SourceRejected("Field span does not equal its entire original field")
            kind = STRUCTURAL_KINDS[candidate.field_pointer]
            if "kind" in metadata and metadata["kind"] != kind:
                raise SourceRejected("Observed kind conflicts with fixed structural kind")
            metadata["kind"] = kind
        if "kind" in metadata and not isinstance(metadata["kind"], str):
            raise SourceRejected("kind must be an observed string")
        for key in ("paths", "responsibility"):
            if key in metadata and not (isinstance(metadata[key], list) and all(isinstance(x, str) for x in metadata[key])):
                raise SourceRejected(key + " must be an observed list of strings")
        identity = digest([source.source_id, candidate.start, end])
        if identity in seen:
            raise SourceRejected("Duplicate candidate span")
        seen.add(identity)
        card = {
            "candidate_id": identity, "source_id": source.source_id,
            "source_message_index": source.message_index,
            "source_message_sha256": digest(source.message),
            "source_content_sha256": content_hash,
            "source_span": [candidate.start, end], "text": text[candidate.start:end],
            "metadata": copy.deepcopy(metadata),
            "metadata_source_pointers": dict(candidate.metadata_pointers),
            "kind_source_pointer": candidate.field_pointer,
            "source_reference": source.reference,
            "reference_semantics": ("private_context_read" if reference["kind"] == "private_reader"
                                    else "audit_locator_no_model_reader_after_dynamic_selection"),
            "historical_evidence_not_current_validation": True,
        }
        rows.append({"card": card, "protected": candidate.protected,
                     "presented_step": source.presented_step})
    return sorted(rows, key=lambda row: row["card"]["candidate_id"])


def select_context(
    sources: Sequence[PresentedSource], candidates: Sequence[Candidate], *,
    condition: str, episode: str, member: str, decision_step: int,
    task: str, role: str, responsibilities: Sequence[str] = (), current_version=None,
    budget_tokens: int, count: Callable[[str], int] = estimate_tokens,
):
    """Return exact cards and audit data; never mutate inputs or truncate a card.

    ``budget_tokens`` covers the complete rendered selection, including provenance
    and reader references. Whole-request admission is handled by project_request.
    A protected-card overflow rejects the entire proposed intervention explicitly.
    K0 performs no candidate reads; the existing Harness request remains intact.
    """
    if condition not in CONDITIONS or role not in ROLES:
        raise ValueError("Unknown condition or role")
    if type(budget_tokens) is not int or budget_tokens < 0:
        raise ValueError("Budget must be a nonnegative integer")
    if type(decision_step) is not int or decision_step < 0:
        raise ValueError("Decision step must be a nonnegative integer")
    proof = {"version": VERSION, "condition": condition, "budget_tokens_local_estimate": budget_tokens,
             "token_accounting": "local_estimate_only", "provider_exact_tokens_claimed": False,
             "selector_installs_runtime": False, "reread_and_summary_costs": "not_measured_by_selector",
             "same_candidate_and_rendering_rules": True, "unmet_protected": [], "omitted": []}
    if condition == "K0":
        proof.update(admitted=True, baseline_unchanged=True, selected_tokens_local_estimate=0)
        return {"selected": [], "rendered": "", "proof": proof}
    pool = _pool(sources, candidates, episode=episode, member=member, decision_step=decision_step)
    proof["candidate_pool_sha256"] = digest(pool)
    proof["candidate_pool_size"] = len(pool)
    proof["ranking_policy"] = {"lexical_overlap_weight": 10, "responsibility_weight": 8,
                               "exact_version_weight": 8, "version_bound_test_weight": 8,
                               "role_kind_weights": copy.deepcopy(ROLE_KINDS)}
    query = _tokens(task)
    ranked = []
    for row in pool:
        card = row["card"]
        metadata = card["metadata"]
        generic = 10 * len(query & _tokens(card["text"]))
        bonuses = {"role": 0, "responsibility": 0, "exact_version": 0, "version_bound_validation": 0}
        exact = current_version is not None and metadata.get("version") is not None and canonical(metadata["version"]) == canonical(current_version)
        if condition == "K2":
            bonuses["role"] = ROLE_KINDS[role].get(metadata.get("kind"), 0)
            bonuses["responsibility"] = 8 * bool(set(responsibilities) & set(metadata.get("paths", []) + metadata.get("responsibility", [])))
            bonuses["exact_version"] = 8 * exact
            # A workspace version in the enclosing observation does not prove
            # that an embedded test was executed on that version.
            test_version_bound = (card["kind_source_pointer"] is None or
                                  card["metadata_source_pointers"].get("version", "").startswith(
                                      card["kind_source_pointer"] + "/"))
            bonuses["version_bound_validation"] = 8 * (exact and metadata.get("kind") == "test" and test_version_bound)
        ranked.append((row, {"generic": generic, **bonuses, "total": generic + sum(bonuses.values())}))
    # Protection and tie-break rules are identical for both conditions.
    ranked.sort(key=lambda pair: (not pair[0]["protected"], -pair[1]["total"],
                                  -pair[0]["presented_step"], pair[0]["card"]["candidate_id"]))
    selected = []
    v117_fields = [row["card"] for row in pool
                   if _reference(row["card"]["source_reference"])["kind"] == "v117_same_input"]
    notice = {"operation": "historical_dynamic_field_selection",
              "v117_markers_describe_upstream_static_projection_only": True,
              "eligible_field_count": len(v117_fields),
              "omitted_dynamic_fields_have_no_model_reread_tool": True,
              "lossless_full_history_reconstruction_claimed": False} if v117_fields else None
    def render(cards):
        if notice is not None:
            return canonical({NOTICE_KEY: notice, EVIDENCE_KEY: cards})
        return canonical({EVIDENCE_KEY: cards}) if cards else ""
    for row, score in ranked:
        card = row["card"]
        if _count(count, render(selected + [card])) <= budget_tokens:
            selected.append(card)
        else:
            proof["omitted"].append({"candidate_id": card["candidate_id"], "reason": "whole_card_budget"})
            if row["protected"]:
                proof["unmet_protected"].append(card["candidate_id"])
    proof["ranking"] = [{"candidate_id": row["card"]["candidate_id"], "score": score,
                         "protected": row["protected"]} for row, score in ranked]
    rendered = render(selected)
    proof.update(admitted=not proof["unmet_protected"] and _count(count, rendered) <= budget_tokens,
                 selected_tokens_local_estimate=_count(count, rendered),
                 selected_ids=[card["candidate_id"] for card in selected],
                 source_references=[card["source_reference"] for card in selected])
    selected_sources = {row["card"]["source_id"] for row in pool}
    return {"selected": selected, "rendered": rendered, "proof": proof,
            "pool_cards": [row["card"] for row in pool],
            "source_messages": {source.source_id: copy.deepcopy(source.message)
                                for source in sources if source.source_id in selected_sources}}


def project_request(baseline_request, selection, *, slots: Mapping[str, int],
                    request_budget_tokens: int, count=estimate_tokens):
    """Prepare an SDK-shaped request without installing it or changing tools.

    ``baseline_request`` must already be the unmodified Harness projection.
    Slots are existing historical observation placeholders with context_read
    references or validated v117 same-input anchors. The latter needs no new
    reader. The adapter verifies the upstream lossless v117 baseline, then removes
    eligible historical dynamic fields and presents only selected complete cards.
    The resulting input is deliberately NOT lossless; source locators identify
    audit originals, not a newly granted model reader. Actions/tools stay intact.
    """
    result = copy.deepcopy(baseline_request)
    proof = copy.deepcopy(selection["proof"])
    if type(request_budget_tokens) is not int or request_budget_tokens < 0:
        raise ValueError("Request budget must be a nonnegative integer")
    before = _count(count, canonical(baseline_request))
    proof["baseline_request_tokens_local_estimate"] = before
    proof["request_budget_tokens_local_estimate"] = request_budget_tokens
    proof["request_projection_applied"] = False
    if proof["condition"] != "K0" and proof["admitted"]:
        grouped = {}
        all_cards = selection.get("pool_cards", selection["selected"])
        for card in all_cards:
            index = slots.get(card["source_id"])
            if type(index) is not int or not 0 <= index < len(result["messages"]):
                raise SourceRejected("Selected source has no valid historical placeholder slot")
            message = result["messages"][index]
            reference = _reference(card["source_reference"])
            if reference["kind"] == "private_reader":
                if message.get("role") not in ("user", "tool") or card["source_reference"] not in message.get("content", ""):
                    raise SourceRejected("Historical placeholder must retain its private-reader reference")
            else:
                try:
                    body = json.loads(message["content"])
                    marker = body[V117_MARKER]
                    anchor_index = reference["anchor_message_index"]
                    if (message.get("role") != "user" or index != card["source_message_index"]
                            or not index < anchor_index < len(result["messages"])
                            or any(marker.get(key) != value for key, value in reference.items() if key != "kind")
                            or marker["original_content_sha256"] != card["source_content_sha256"]
                            or hashlib.sha256(result["messages"][anchor_index]["content"].encode()).hexdigest() != reference["anchor_content_sha256"]
                            or EVIDENCE_KEY in body):
                        raise SourceRejected("v117 historical slot or literal anchor has changed")
                    from .software_benchmark_history_v117 import STATIC_PATHS, _get, _parent
                    restored = copy.deepcopy(body)
                    del restored[V117_MARKER]
                    anchor = json.loads(result["messages"][anchor_index]["content"])
                    original = selection["source_messages"][card["source_id"]]
                    if digest(original) != card["source_message_sha256"]:
                        raise SourceRejected("Original source message binding changed")
                    fields = marker["omitted_equal_paths"]
                    if not fields or len(fields) != len(set(fields)):
                        raise SourceRejected("Invalid v117 omitted field list")
                    for pointer in fields:
                        if pointer not in STATIC_PATHS:
                            raise SourceRejected("v117 reference attempts to omit a dynamic field")
                        parent, key = _parent(restored, pointer)
                        if key in parent:
                            raise SourceRejected("v117 referenced field was not omitted")
                        parent[key] = copy.deepcopy(_get(anchor, pointer))
                    if canonical(restored) != canonical(json.loads(original["content"])):
                        raise SourceRejected("v117 historical content differs from original source")
                except (KeyError, ValueError, TypeError, AttributeError) as error:
                    raise SourceRejected("Invalid v117 historical source projection") from error
            grouped.setdefault(index, []).append(card)
        v117_selection = bool(grouped) and all(
            _reference(card["source_reference"])["kind"] == "v117_same_input" for card in all_cards)
        removed_fields = []
        if v117_selection:
            # Validate every source before any mutation. The same entire pool is
            # removed in K1 and K2, including cards that did not fit the budget.
            for index, cards in grouped.items():
                body = json.loads(result["messages"][index]["content"])
                pointers = set()
                for card in cards:
                    pointer = card.get("kind_source_pointer")
                    if pointer not in STRUCTURAL_KINDS or pointer in pointers:
                        raise SourceRejected("Dynamic selection requires unique complete allowlisted fields")
                    if any(pointer.startswith(old + "/") or old.startswith(pointer + "/") for old in pointers):
                        raise SourceRejected("Overlapping field cards are not allowed")
                    pointers.add(pointer)
                    parent, key = _parent(body, pointer)
                    if canonical(parent[key]) != canonical(json.loads(card["text"])):
                        raise SourceRejected("Eligible dynamic field no longer equals its whole original card")
                    del parent[key]
                    removed_fields.append({"source_id": card["source_id"], "message_index": index,
                                           "pointer": pointer, "audit_reference": card["source_reference"]})
                result["messages"][index]["content"] = canonical(body)
            grouped = {min(grouped): selection["selected"]}
            additions = {min(grouped): selection["rendered"]}
        else:
            # Private-reader placeholders were already masked by their caller.
            grouped = {}
            for card in selection["selected"]:
                grouped.setdefault(slots[card["source_id"]], []).append(card)
            additions = {index: "\n" + canonical({EVIDENCE_KEY: cards}) for index, cards in grouped.items()}
        added_cost = sum(_count(count, text) for text in additions.values())
        proof["projection_added_tokens_local_estimate"] = added_cost
        for index, text in additions.items():
            if v117_selection:
                body = json.loads(result["messages"][index]["content"])
                body.update(json.loads(text))
                result["messages"][index]["content"] = canonical(body)
            else:
                result["messages"][index]["content"] += text
        # Count the actual added content too: separate slot wrappers and JSON
        # escaping are part of the intervention budget, not free overhead.
        actual_added_cost = sum(max(0, _count(count, result["messages"][i]["content"])
                                   - _count(count, baseline_request["messages"][i]["content"]))
                                for i in grouped)
        added_cost = max(added_cost, actual_added_cost)
        proof["projection_added_tokens_local_estimate"] = added_cost
        if added_cost > proof["budget_tokens_local_estimate"]:
            result = copy.deepcopy(baseline_request)
            proof.update(admitted=False, rejection="rendered_slot_budget", baseline_unchanged=True)
        elif _count(count, canonical(result)) > request_budget_tokens:
            result = copy.deepcopy(baseline_request)
            proof.update(admitted=False, rejection="whole_request_budget", baseline_unchanged=True)
        else:
            proof["request_projection_applied"] = bool(grouped)
            proof["eligible_dynamic_fields_removed"] = removed_fields
            proof["selection_not_only_duplicate_salience"] = v117_selection
            proof["lossless_full_history_reconstruction_claimed"] = False if v117_selection else None
    after = _count(count, canonical(result))
    proof["request_tokens_local_estimate"] = after
    proof["request_capacity_fits_local_estimate"] = after <= request_budget_tokens
    if not proof["request_capacity_fits_local_estimate"]:
        proof.update(admitted=False, rejection="baseline_request_over_budget")
    return result, proof
