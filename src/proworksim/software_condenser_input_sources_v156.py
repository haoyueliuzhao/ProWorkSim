"""Lossless source tags for the existing SDK condenser prompt, without a model.

The real prompt is not edited. A shadow rendering of the same template uses
unique generated slot markers; actual event strings then reconstruct the real
prompt byte for byte. Existing SDK display truncation is retained and measured.
"""

from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

from .software_input_provenance_v156 import AnnotatedText, SourceFragment, TextSegment

VERSION = "v156-condenser-template-event-source-slots-r1"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read_ref(reference):
    raw = Path(reference["path"]).read_bytes()
    if _sha(raw) != reference["sha256"] or len(raw) != reference["bytes"]:
        raise ValueError("Condenser's immutable source reference changed")
    return raw


def _sdk_bindings():
    # Lazy imports: installation/import performs no SDK initialization.
    from openhands.sdk.context.condenser import llm_summarizing_condenser as implementation
    from openhands.sdk.event import Event

    path = Path(implementation.__file__).parent / "prompts/summarizing_prompt.j2"
    raw = path.read_bytes()
    reference = {"path": str(path), "sha256": _sha(raw), "bytes": len(raw)}

    def render(events):
        return implementation.render_template(str(path.parent), path.name, events=events)

    return render, Event.model_validate, reference


def _clip(segments, length):
    output, remaining = [], length
    for segment in segments:
        if remaining <= 0:
            break
        text = segment.text[:remaining]
        origin = segment.source
        if origin is not None:
            origin = replace(origin, transformation="excerpt")
        output.append(TextSegment(text, origin))
        remaining -= len(text)
    return output


def _segments(value):
    return list(value.segments) if isinstance(value, AnnotatedText) else [TextSegment(value, None)]


def _event_segments(event, row, member, template, episode_id, artifact_bindings):
    # Imported here because SDKRequestCapture lazily calls this module.
    from .software_sdk_input_sources_v156 import annotate_message, source

    rendered = str(event)
    kind = row["kind"]
    origin = {
        "event_ids": [row["id"]],
        "event_types": [kind],
        "tool_name": row.get("tool_name"),
        "events": [row],
    }
    details = {
        "event_id": row["id"],
        "event_type": kind,
        "displayed_characters": len(rendered),
        "source_scope": "actual_str_event_display_only",
        "source_row_sha256": _sha(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()),
    }
    prefix_base = f"{kind} ({row['source']})"
    if kind in {"MessageEvent", "CondensationSummaryEvent"}:
        message = event.to_llm_message()
        # Image rendering or other modality is left unknown; never infer its
        # text provenance from visually similar message content.
        if any(type(item).__name__ != "TextContent" for item in message.content):
            return [TextSegment(rendered, None)], {**details, "mapping": "unattributed_modality"}
        full = " ".join(item.text for item in message.content)
        prefix = prefix_base + f"\n  {message.role}: "
        if not full:
            return [TextSegment(rendered, None)], {
                **details,
                "mapping": "unattributed_empty_display",
            }
        # Both these frozen SDK string renderers use N_CHAR_PREVIEW=500.
        truncated = len(full) > 500
        displayed = full[:497] + "..." if truncated else full
        suffix = ""
        if kind == "MessageEvent":
            skills = getattr(event, "activated_skills", [])
            thinking = getattr(event, "thinking_blocks", [])
            suffix += f" [Skills: {', '.join(skills)}]" if skills else ""
            suffix += f" [Thinking blocks: {len(thinking)}]" if thinking else ""
        if prefix + displayed + suffix != rendered:
            return [TextSegment(rendered, None)], {
                **details,
                "mapping": "unattributed_event_renderer_mismatch",
            }
        annotated = annotate_message(
            {"role": message.role, "content": full},
            origin,
            member=member,
            episode_id=episode_id,
            artifact_bindings=artifact_bindings,
        )
        pieces = _segments(annotated["content"])
        if truncated:
            pieces = _clip(pieces, 497) + [TextSegment("...", template)]
        result = [TextSegment(prefix, template), *pieces]
        if suffix:
            result.append(TextSegment(suffix, template))
        return result, {
            **details,
            "mapping": "explicit_message_display_projection",
            "full_source_text_characters": len(full),
            "display_text_characters": len(displayed),
            "existing_sdk_preview_truncated": truncated,
        }
    if kind == "ObservationEvent":
        prefix = prefix_base + f"\n  Tool: {row['tool_name']}\n  Result: "
        if not rendered.startswith(prefix):
            return [TextSegment(rendered, None)], {
                **details,
                "mapping": "unattributed_event_renderer_mismatch",
            }
        displayed = rendered[len(prefix) :]
        annotated = annotate_message(
            {"role": "tool", "content": displayed, "name": row["tool_name"]},
            origin,
            member=member,
            episode_id=episode_id,
            artifact_bindings=artifact_bindings,
        )
        return [TextSegment(prefix, template), *_segments(annotated["content"])], {
            **details,
            "mapping": "explicit_tool_event_display",
            "full_source_text_not_assumed_displayed": True,
        }
    if kind == "ActionEvent" and row.get("source") == "agent":
        # Its thought and selected action came from this member's own event.
        return [
            TextSegment(
                rendered,
                source("Self-history", "sdk:" + row["id"], member, transformation="excerpt"),
            )
        ], {**details, "mapping": "explicit_own_action_display"}
    if kind == "SystemPromptEvent":
        return [
            TextSegment(
                rendered,
                source("Base/Template", "sdk:" + row["id"], member, transformation="template"),
            )
        ], {**details, "mapping": "explicit_system_event"}
    return [TextSegment(rendered, None)], {**details, "mapping": "unattributed_event_type"}


def annotate_condenser_wire(
    wire,
    worker,
    member,
    *,
    template_renderer=None,
    event_loader=None,
    template_reference=None,
    episode_id="unbound-local-control",
    artifact_bindings=None,
):
    """Return (same-byte annotated payload, template source, audit evidence).

    Optional dependencies exist for zero-model CPU controls. Production defaults
    load the same SDK class/template as LLMSummarizingCondenser. Unbound source,
    owner, projection, or template returns the unchanged payload as unknown.
    """
    unchanged = copy.deepcopy(wire)
    evidence = {
        "version": VERSION,
        "source_mapping": "unattributed_condenser_request",
        "actual_prompt_changed": False,
    }
    try:
        trace = getattr(worker, "_history_trace_v110", None)
        pending = getattr(trace, "pending", None)
        if not isinstance(pending, dict) or pending.get("owner_id") != member:
            raise ValueError("No current member-bound condenser source set")
        source_ref = pending["sources"]
        sources = json.loads(_read_ref(source_ref))
        rows = sources["events"]
        ids = [row["id"] for row in rows]
        if (
            not rows
            or len(set(ids)) != len(ids)
            or ids != pending["event_ids"]
            or sources.get("event_ids") != ids
            or sources.get("owner_id") != member
            or sources.get("source") != "this_conversation_view_only"
        ):
            raise ValueError("Condenser source identity/order/owner differs from the bound view")
        if template_renderer is None and event_loader is None and template_reference is None:
            template_renderer, event_loader, template_reference = _sdk_bindings()
        if (
            not callable(template_renderer)
            or not callable(event_loader)
            or not isinstance(template_reference, dict)
        ):
            raise ValueError(
                "Condenser template and event renderer need one complete explicit binding"
            )
        _read_ref(template_reference)
        template = SourceFragment(
            "Base/Template",
            "sdk-condenser-template:" + template_reference["sha256"],
            "sdk-condenser-template:" + template_reference["sha256"],
            member,
            transformation="template",
            version_sha256=template_reference["sha256"],
        )
        # ManagedAction classes are process-local. The trace already owns the
        # original immutable events, so do not deserialize these tool subclasses
        # merely to render their existing string representation.
        provider = getattr(trace, "event_provider", None)
        live = {}
        if callable(provider):
            for event in provider():
                if event.id in ids:
                    if event.id in live:
                        raise ValueError("Duplicate event identity in the bound private source")
                    live[event.id] = event
        events = [live[row["id"]] if row["id"] in live else event_loader(row) for row in rows]
        if any(event.model_dump(mode="json") != row for event, row in zip(events, rows)):
            raise ValueError("SDK event reconstruction changed a frozen source record")
        rendered_events = [str(event) for event in events]
        messages = wire.get("messages")
        if (
            wire.get("tools")
            or not isinstance(messages, list)
            or len(messages) != 1
            or messages[0].get("role") != "user"
        ):
            raise ValueError("Not the original one-message tool-free summarizer shape")
        content = messages[0].get("content")
        list_shape = (
            isinstance(content, list) and len(content) == 1 and content[0].get("type") == "text"
        )
        prompt = content[0].get("text") if list_shape else content
        if not isinstance(prompt, str) or template_renderer(rendered_events) != prompt:
            raise ValueError(
                "Actual condenser prompt differs from the exact source-bound SDK template"
            )
        markers = [f"__PWS156_SLOT_{source_ref['sha256']}_{i}__" for i in range(len(rows))]
        if any(marker in prompt for marker in markers):
            raise ValueError("A generated shadow slot marker collides with real content")
        shadow = template_renderer(markers)
        cursor, pieces, event_evidence = 0, [], []
        for marker, event, row in zip(markers, events, rows):
            if shadow.count(marker) != 1:
                raise ValueError(
                    "The frozen template does not preserve one explicit slot per event"
                )
            start = shadow.find(marker, cursor)
            if start < cursor:
                raise ValueError("The template reordered event slots")
            if start > cursor:
                pieces.append(TextSegment(shadow[cursor:start], template))
            annotated, observation = _event_segments(
                event, row, member, template, episode_id, artifact_bindings
            )
            if "".join(piece.text for piece in annotated) != str(event):
                raise ValueError(
                    "Event source annotations changed the actual string representation"
                )
            pieces.extend(annotated)
            event_evidence.append(observation)
            cursor = start + len(marker)
        if cursor < len(shadow):
            pieces.append(TextSegment(shadow[cursor:], template))
        if "".join(piece.text for piece in pieces) != prompt:
            raise ValueError("Shadow slots do not reconstruct the actual prompt byte for byte")
        result = copy.deepcopy(wire)
        result["messages"][0]["role"] = AnnotatedText((TextSegment("user", template),))
        if list_shape:
            result["messages"][0]["content"][0]["text"] = AnnotatedText(tuple(pieces))
            result["messages"][0]["content"][0]["type"] = AnnotatedText(
                (TextSegment("text", template),)
            )
        else:
            result["messages"][0]["content"] = AnnotatedText(tuple(pieces))
        evidence.update(
            source_mapping="explicit_condenser_template_event_slots",
            sources=copy.deepcopy(source_ref),
            template=copy.deepcopy(template_reference),
            event_ids=ids,
            events=event_evidence,
            actual_prompt_sha256=_sha(prompt.encode()),
            shadow_slot_count=len(ids),
            matches_actual_prompt=True,
            existing_sdk_preview_policy_unchanged=True,
            original_live_event_count=len(live),
            sdk_decoded_event_count=len(rows) - len(live),
        )
        return result, template, evidence
    except Exception as error:
        evidence.update(
            reason_type=type(error).__name__, reason=str(error), source_unavailable=True
        )
        return unchanged, None, evidence
