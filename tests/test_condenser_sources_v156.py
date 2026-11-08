"""CPU-only real frozen template, synthetic immutable SDK-event records."""

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment

from proworksim.software_condenser_input_sources_v156 import annotate_condenser_wire
from proworksim.software_input_provenance_v156 import build_request, canonical


TextContent = type("TextContent", (), {"__init__": lambda self, text: setattr(self, "text", text)})


class EventFixture:
    def __init__(self, row):
        self.row = copy.deepcopy(row)
        self.id = row["id"]
        self.activated_skills = []
        self.thinking_blocks = []

    def model_dump(self, mode):
        assert mode == "json"
        return copy.deepcopy(self.row)

    def to_llm_message(self):
        row = self.row
        return SimpleNamespace(role=row["role"], content=[TextContent(row["text"])])

    def __str__(self):
        row = self.row
        text = row["text"]
        displayed = text[:497] + "..." if len(text) > 500 else text
        return f"{row['kind']} ({row['source']})\n  {row['role']}: {displayed}"


def reference(path):
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def fixture(tmp_path):
    template_path = Path(
        "runs/v016-sdk/resident-venv/lib/python3.12/site-packages/openhands/sdk/context/condenser/prompts/summarizing_prompt.j2"
    ).resolve()
    template = Environment(autoescape=False).from_string(template_path.read_text())

    def render(events):
        return template.render(events=events).strip()

    observation = json.dumps(
        {
            "role_task": "repair",
            "observation": {
                "messages": [
                    {
                        "actor_id": "member_002",
                        "recipient": "member_001",
                        "sequence": 7,
                        "body": "same",
                    }
                ],
                "large": "x" * 1000,
            },
        },
        ensure_ascii=False,
    )
    rows = [
        {
            "id": "user-event",
            "kind": "MessageEvent",
            "source": "user",
            "role": "user",
            "text": observation,
        },
        {
            "id": "summary-event",
            "kind": "CondensationSummaryEvent",
            "source": "environment",
            "role": "user",
            "text": "same",
        },
        {
            "id": "own-event",
            "kind": "MessageEvent",
            "source": "agent",
            "role": "assistant",
            "text": "same",
        },
    ]
    sources = tmp_path / "sources.json"
    ids = [row["id"] for row in rows]
    sources.write_text(
        json.dumps(
            {
                "owner_id": "member_001",
                "events": rows,
                "event_ids": ids,
                "source": "this_conversation_view_only",
            }
        )
    )
    worker = SimpleNamespace(
        _history_trace_v110=SimpleNamespace(
            pending={"owner_id": "member_001", "event_ids": ids, "sources": reference(sources)}
        )
    )
    wire = {
        "model": "deepseek-flash",
        "messages": [{"role": "user", "content": render([str(EventFixture(row)) for row in rows])}],
        "max_tokens": 200,
    }
    inject = {
        "template_renderer": render,
        "event_loader": EventFixture,
        "template_reference": reference(template_path),
    }
    return worker, wire, inject


def identity():
    return {
        "request_id": "request-1",
        "episode_id": "episode-1",
        "member_id": "member_001",
        "decision_id": "summary-1",
        "attempt_id": "request-1",
        "model_alias": "deepseek-flash",
        "request_time": "2026-11-08T00:00:00Z",
    }


def test_real_template_slots_preserve_bytes_clip_and_distinct_event_origins(tmp_path):
    worker, wire, inject = fixture(tmp_path)
    output, template, evidence = annotate_condenser_wire(wire, worker, "member_001", **inject)
    built = build_request(output, identity(), template_source=template)
    assert built.payload_bytes == canonical(wire).encode()
    assert evidence["source_mapping"] == "explicit_condenser_template_event_slots"
    assert evidence["events"][0]["existing_sdk_preview_truncated"]
    assert evidence["events"][0]["display_text_characters"] == 500
    spans = [s for s in built.manifest["spans"] if s["kind"] == "text_fragment"]
    categories = {s["source"]["category"] for s in spans if s["source"]}
    assert {"Task", "Peer-message", "Summary", "Self-history", "Base/Template"} <= categories
    peer = next(s for s in spans if s["source"] and s["source"]["category"] == "Peer-message")
    assert peer["source"]["origin_event_id"] == "unbound-local-control:world-message:7"
    assert peer["source"]["origin_member_id"] == "member_002"
    assert peer["source"]["transformation"] == "excerpt"
    summary = next(s for s in spans if s["source"] and s["source"]["category"] == "Summary")
    own = next(s for s in spans if s["source"] and s["source"]["category"] == "Self-history")
    assert summary["source"]["origin_event_id"] != own["source"]["origin_event_id"]
    assert not evidence["actual_prompt_changed"]


def test_unmatched_actual_prompt_preserves_unknown_and_original_bytes(tmp_path):
    worker, wire, inject = fixture(tmp_path)
    wire["messages"][0]["content"] += "a genuine unbound suffix"
    output, template, evidence = annotate_condenser_wire(wire, worker, "member_001", **inject)
    assert output == wire and template is None and evidence["source_unavailable"]


def test_cross_member_source_binding_is_not_relabelled_self_history(tmp_path):
    worker, wire, inject = fixture(tmp_path)
    output, template, evidence = annotate_condenser_wire(wire, worker, "member_002", **inject)
    assert output == wire and template is None and evidence["source_unavailable"]


def test_original_private_events_do_not_require_dynamic_class_deserialization(tmp_path):
    worker, wire, inject = fixture(tmp_path)
    trace = worker._history_trace_v110
    rows = json.loads(Path(trace.pending["sources"]["path"]).read_text())["events"]
    trace.event_provider = lambda: [EventFixture(row) for row in rows]

    def cannot_deserialize(_):
        raise ValueError("Unknown kind for a historical dynamic tool class")

    inject["event_loader"] = cannot_deserialize
    output, template, evidence = annotate_condenser_wire(wire, worker, "member_001", **inject)
    assert evidence["source_mapping"] == "explicit_condenser_template_event_slots"
    assert evidence["original_live_event_count"] == 3 and evidence["sdk_decoded_event_count"] == 0
    assert (
        build_request(output, identity(), template_source=template).payload_bytes
        == canonical(wire).encode()
    )
