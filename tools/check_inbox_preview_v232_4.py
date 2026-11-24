"""Check the intervention against actual recipient payloads and the authorized event reader."""

from proworksim.software_context_panel_v231 import ROOT
from proworksim.software_context_builder_v230 import recover_observations, identity, object_text
from proworksim.software_context_v232 import checked_context
from proworksim.software_inbox_preview_v232_4 import add_lookup
from proworksim.software_graph_execution_v230 import World
from proworksim.storage import json_bytes, read_json, atomic_write

PREVIOUS = ROOT / "runs/software-benchmark-v232-3/recipient-r1/Sphinx-9591/RECEIVE"
PLAN = ROOT / "artifacts/software-benchmark-v232-4/preview-r1"


def main():
    state = read_json(PREVIOUS / "prepared/world/control/state.json")
    world = World.__new__(World)
    world.state = state
    duty = read_json(PREVIOUS / "mechanism.json")["control"]["duties"]["work_root"]
    seq = duty["message_sequence"]
    event = world._action_read_work_event(duty["recipient"], "SOFTWARE27", seq)
    results = []
    count = 0
    for f in sorted((PREVIOUS / "api").glob("*/request.json")):
        payload = read_json(f)["payload"]
        actor = payload["member_id"]
        wire = payload["wire"]
        role = "worker" if payload["usage_id"] == "agent" else "condenser"
        archive = (
            PREVIOUS
            / "telemetry"
            / role
            / identity([payload["team_slot_id"], actor, payload["request_id"]])
        )
        original = read_json(archive / "original.json")
        m = read_json(archive / "manifest.json")
        assert m["shown_wire"] == identity(wire)
        if actor != duty["recipient"] or not any(
            msg.get("sequence") == seq
            for obs in recover_observations(wire).values()
            for msg in obs.get("messages", [])
        ):
            add_lookup(wire, m, actor, role, duty, "work_root", [event])
            assert identity(wire) == read_json(archive / "manifest.json")["shown_wire"]
            count += 1
            continue
        shown, meta = checked_context(original, actor, role, 1)
        assert identity(shown) == identity(wire)

        def project(test_actor, test_role, test_event):
            s, info = checked_context(original, actor, role, 1)
            add_lookup(s, info, test_actor, test_role, duty, "work_root", [test_event])
            return s, info

        for who, what, source in [
            ("member_002", "worker", event),
            (actor, "condenser", event),
            (actor, role, {**event, "body": event["body"][:500]}),
            (actor, role, {**event, "recipient": "member_002"}),
        ]:
            s, info = project(who, what, source)
            assert "handoff_preview_notice" not in info and identity(s) == identity(wire)
        shown, meta = project(actor, role, event)
        note = meta["handoff_preview_notice"]
        assert (note["displayed_characters"], note["total_characters"]) == (500, len(event["body"]))
        args = note["read_full_text"]["arguments"]
        assert note["read_full_text"]["tool"] == "read_work_event"
        retrieved = world._action_read_work_event(actor, "SOFTWARE27", **args)
        assert retrieved == event and recover_observations(shown) == recover_observations(wire)
        idx = note["message_index"]
        value = object_text(shown["messages"][idx]["content"])
        assert value.pop("truncated_handoff")["message_sequence"] == seq and value == object_text(
            wire["messages"][idx]["content"]
        )
        assert all(
            m1 == m2
            for i, (m1, m2) in enumerate(zip(wire["messages"], shown["messages"]))
            if i != idx
        )
        results.append(
            {
                "source_request": payload["request_id"],
                "notice": note,
                "full_body_hash": identity(retrieved["body"]),
            }
        )
    assert len(results) == 2 and count == 11
    atomic_write(
        PLAN / "gate.json",
        json_bytes(
            {
                "provider_calls": 0,
                "verified_full_lookup_on_prior_requests": results,
                "unchanged_other_requests": count,
                "controls": ["full short message", "wrong recipient", "condenser", "foreign event"],
                "observation_reconstruction_unchanged": True,
            }
        ),
    )


if __name__ == "__main__":
    main()
