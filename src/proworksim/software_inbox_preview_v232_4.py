"""Attach a native full-text lookup to a truncated, accepted diagnosis in its recipient's inbox."""

from .software_context_builder_v230 import compact, identity, object_text, recover_observations
from .software_context_v232 import checked_context
from .software_fixed_organization_clone_v131 import clone_function
from .software_handoff_receive_v232_3 import RecipientExecution
from .software_organization_v232 import Endpoint


def add_lookup(shown, manifest, actor, role, duty, task, events):
    if (
        role != "worker"
        or not duty
        or duty.get("status") != "handed_off"
        or duty.get("recipient") != actor
    ):
        return
    if not any(t["function"]["name"] == "read_work_event" for t in shown.get("tools", ())):
        return
    sequence = duty.get("message_sequence")
    snapshots = recover_observations(shown)
    if not snapshots or not isinstance(sequence, int):
        return
    index = max(snapshots)
    inbox = snapshots[index]
    if inbox.get("actor_id") != actor:
        return

    def matches(event):
        return (
            event.get("sequence") == sequence
            and event.get("kind") == "work_message"
            and event.get("actor_id") == duty["owner"]
            and event.get("recipient") == actor
            and event.get("task_id") == task
        )

    preview = next((m.get("body") for m in inbox.get("messages", []) if matches(m)), None)
    if not isinstance(preview, str) or not preview:
        return
    event = next((e for e in reversed(events) if matches(e)), None)
    if event is None:
        return
    full = event["body"]
    if len(preview) >= len(full) or not full.startswith(preview):
        return
    card = {
        "message_sequence": sequence,
        "displayed_characters": len(preview),
        "total_characters": len(full),
        "read_full_text": {"tool": "read_work_event", "arguments": {"sequence": sequence}},
    }
    message = shown["messages"][index]
    content = object_text(message["content"])
    message["content"] = compact({**content, "truncated_handoff": card})
    manifest["items"][index]["shown_hash"] = identity(message)
    manifest["handoff_preview_notice"] = {"message_index": index, **card}
    manifest["shown_wire"] = identity(shown)


class PreviewExecution(RecipientExecution):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        def project(raw, actor, role, version, history):
            shown, manifest = checked_context(raw, actor, role, version, history)
            if self.runtime is not None and self.recipient_state in ("ready", "consumed"):
                world = self.runtime.prepared.world
                duty = world.protocol()["graph_control"]["duties"].get(self.receive_task)
                add_lookup(
                    shown,
                    manifest,
                    actor,
                    role,
                    duty,
                    self.receive_task,
                    world.state["software_events"],
                )
            return shown, manifest

        # Use exactly the same transform for native token counts and the paid endpoint.
        method = clone_function(
            Endpoint.post, {**Endpoint.post.__globals__, "checked_context": project}
        )
        self.worker.post = method.__get__(self.worker, Endpoint)
