"""Instance-local role presentation over the original v117 SDK projection.

No source history, condenser, tools, world permissions or host API is replaced.
The existing SDK counting and dispatch preparation both invoke this hook.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import MethodType

from .software_benchmark_history_v117 import REFERENCE_KEY, SummarizingManagedContextTransport
from .software_role_context_v203_2_3 import (
    Candidate, PresentedSource, canonical, digest, project_request, select_context,
)

VERSION = "v203.2.3-feedback-index-bound-role-presentation-r3"
FIELDS = ("messages", "handoffs", "patches", "all_fixed_patches",
          "current_version_test_coverage", "delivery_status", "organization_protocol")


class SourceResolutionUnavailable(ValueError):
    """No verified original source for a post-feedback projection coordinate."""


def resolve_sources(request, baseline, feedback, history, registered):
    """Translate v117 indices through the original format-feedback projection.

    Both positions refer to the current SDK request, including after condenser
    replacement. No archived/pre-summary source is invented or searched for.
    """
    mapping = feedback.get("selected_indices")
    if (not isinstance(mapping, list) or len(mapping) != len(baseline["messages"])
            or any(type(i) is not int or not 0 <= i < len(request["messages"]) for i in mapping)
            or mapping != sorted(set(mapping))):
        raise SourceResolutionUnavailable("invalid_format_feedback_index_map")
    result = []
    for row in history["rewritten_observations"]:
        index = row["message_index"]
        if type(index) is not int or not 0 <= index < len(mapping):
            raise SourceResolutionUnavailable("invalid_post_feedback_observation_index")
        original_index = mapping[index]
        message = request["messages"][original_index]
        content = message.get("content")
        if message.get("role") != "user" or not isinstance(content, str) or content not in registered:
            raise SourceResolutionUnavailable("original_registered_observation_unavailable")
        original_hash = hashlib.sha256(content.encode()).hexdigest()
        try:
            marker = json.loads(baseline["messages"][index]["content"])[REFERENCE_KEY]
            if row["original_content_sha256"] != original_hash or marker["original_content_sha256"] != original_hash:
                raise SourceResolutionUnavailable("observation_hash_does_not_match_mapped_source")
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise SourceResolutionUnavailable("mapped_observation_marker_unavailable") from error
        result.append((index, original_index, message, marker, original_hash))
    return result


def field_span(text, payload, field):
    """Locate a full direct observation field in the actual Harness JSON codec."""
    encode = lambda value: json.dumps(value, ensure_ascii=False, allow_nan=False)
    if encode(payload) != text:
        raise ValueError("Unexpected registered Harness observation serialization")
    top = []
    for key, value in payload.items():
        if key == "observation":
            break
        top.append(encode(key) + ": " + encode(value))
    prefix = "{" + (", ".join(top) + ", " if top else "") + '"observation": {'
    before = []
    for key, value in payload["observation"].items():
        if key == field:
            prefix += (", ".join(before) + ", " if before else "") + encode(key) + ": "
            start = len(prefix)
            raw = encode(value)
            if text[start:start + len(raw)] != raw:
                raise ValueError("Whole field source span did not match actual observation")
            return start, start + len(raw)
        before.append(encode(key) + ": " + encode(value))
    raise ValueError("Missing observation field")


def install(runtime, *, condition, folder, budget_tokens, count, request_budget_tokens):
    if condition not in {"K0", "K1", "K2"} or set(runtime.policies) != {"member_001", "member_002"}:
        raise ValueError("Install only one declared K arm over fixed REVIEW2")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    installed = {}
    for member, worker in runtime.policies.items():
        transport = worker.transport
        if (not isinstance(transport, SummarizingManagedContextTransport)
                or worker.meter["decisions"] or getattr(transport, "_role_context_v203_2_3", None)):
            raise ValueError("Role projection requires a fresh original v117 member transport")
        original = transport.select_for_member
        receipts = []

        def select(self, request, actor, *, original=original, worker=worker, member=member, receipts=receipts):
            if actor != member or self is not worker.transport:
                raise ValueError("Cross-member role context transport")
            baseline, feedback, history = original(request, actor)

            def passthrough(reason=None):
                # K0 never depends on candidate extraction. K1/K2 only fall back
                # when a source cannot be proven; the deviation is explicit.
                proof = {"condition": condition, "admitted": reason is None,
                    "request_projection_applied": False, "baseline_unchanged": True,
                    "rejection": reason, "safe_fallback": "original_v117_baseline" if reason else None,
                    "format_feedback_removed_indices": feedback.get("removed_indices", []),
                    "model_input_and_budget_still_use_original_transport": True}
                receipt = {"version": VERSION, "condition": condition, "member": member,
                    "original_request_sha256": digest(request), "baseline_request_sha256": digest(baseline),
                    "selected_request_sha256": digest(baseline), "actual_registered_sources": len(worker._observation_texts),
                    "selected_sources": [], "selected_metadata": [], "selected_fields": [], "source_ids": [],
                    "source_index_mapping": [], "role": None, "current_version": None,
                    "online_runtime_installed": True, "condenser_not_modified": True,
                    "K0_candidate_extraction_bypassed": condition == "K0", "proof": proof}
                receipts.append(receipt)
                with (folder / (member + ".jsonl")).open("a") as stream:
                    stream.write(canonical(receipt) + "\n")
                return baseline, feedback, {**history, "role_context_projection": receipt}

            if condition == "K0":
                return passthrough()
            observations = worker._observation_texts
            registered = set(observations)
            sources, candidates, slots = [], [], {}
            try:
                mapped_sources = resolve_sources(request, baseline, feedback, history, registered)
            except SourceResolutionUnavailable as error:
                return passthrough(str(error))
            latest = None
            for message in reversed(request["messages"]):
                if message.get("role") == "user" and message.get("content") in registered:
                    latest = json.loads(message["content"])
                    break
            if latest is None:
                return passthrough("no_registered_literal_observation_in_current_request")
            observation = latest["observation"]
            if observation.get("actor_id") != member:
                raise ValueError("Latest actual observation belongs to another member")
            for index, original_index, message, marker, original_hash in mapped_sources:
                payload = json.loads(message["content"])
                if payload["observation"].get("actor_id") != member:
                    raise ValueError("Candidate belongs to another member")
                reference = "v117:" + original_hash + ":" + str(marker["anchor_message_index"]) + ":" + marker["anchor_content_sha256"]
                source_id = digest([runtime.owner.window_id, member, index, original_hash])
                sources.append(PresentedSource(source_id=source_id, episode=runtime.owner.window_id,
                    member=member, message_index=index, presented_step=observations.index(message["content"]),
                    message=copy.deepcopy(message), reference=reference, owner_member=member))
                for field in FIELDS:
                    if not payload["observation"].get(field):
                        continue
                    start, end = field_span(message["content"], payload, field)
                    # An aggregate patch/message directory may contain several
                    # versions. Never relabel them with the observer workspace.
                    version = ({"version": "/observation/workspace_reference"}
                        if field == "current_version_test_coverage" else
                        {"version": "/observation/delivery_status/source_reference"}
                        if field == "delivery_status" else {})
                    candidates.append(Candidate(source_id, start=start, end=end,
                        metadata_pointers=version,
                        field_pointer="/observation/" + field))
                slots[source_id] = index
            role = "reviewer" if member == "member_002" else "developer"
            if member == "member_001" and observation.get("delivery_status", {}).get("next_explicit_tool") == "submit_integration":
                role = "delivery"
            selection = select_context(sources, candidates, condition=condition,
                episode=runtime.owner.window_id, member=member, decision_step=len(observations),
                task=observation["contract"], role=role,
                current_version=observation.get("workspace_reference"), budget_tokens=budget_tokens, count=count)
            selected, proof = project_request(baseline, selection, slots=slots,
                request_budget_tokens=request_budget_tokens, count=count)
            if selected.get("tools") != baseline.get("tools"):
                raise ValueError("Role presentation changed tool permissions")
            receipt = {"version": VERSION, "member": member, "condition": condition,
                "original_request_sha256": digest(request), "baseline_request_sha256": digest(baseline),
                "selected_request_sha256": digest(selected), "actual_registered_sources": len(observations),
                "selected_sources": [card["source_id"] for card in selection["selected"]],
                "selected_metadata": [card["metadata"] for card in selection["selected"]],
                "selected_fields": [card.get("kind_source_pointer") for card in selection["selected"]],
                "source_ids": [source.source_id for source in sources],
                "source_index_mapping": [{"projected_index": index, "original_index": old_index,
                    "original_content_sha256": sha} for index, old_index, _, _, sha in mapped_sources],
                "format_feedback_removed_indices": feedback.get("removed_indices", []),
                "role": role, "current_version": observation.get("workspace_reference"),
                "online_runtime_installed": True, "condenser_not_modified": True,
                "reference_kind": "same_input_v117_static_anchor",
                "model_callable_reader": False,
                "arbitrary_pre_summary_history_recoverable": False,
                "eligible_historical_dynamic_fields_retained_in_baseline": not proof.get("request_projection_applied", False),
                "intervention": "remove_eligible_historical_fields_then_present_selected_whole_cards", "proof": proof}
            receipts.append(receipt)
            with (folder / (member + ".jsonl")).open("a") as stream:
                stream.write(canonical(receipt) + "\n")
            history = {**history, "role_context_projection": receipt}
            return selected, feedback, history

        transport.select_for_member = MethodType(select, transport)
        transport._role_context_v203_2_3 = {"condition": condition, "receipts": receipts}
        installed[member] = transport._role_context_v203_2_3
    return installed
