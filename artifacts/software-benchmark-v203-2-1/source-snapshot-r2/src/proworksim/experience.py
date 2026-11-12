"""Actual runtime observations and actions, separate from world business state."""

import copy

from .storage import digest, json_bytes

EXPERIENCE_VERSION = "staff-experience-v0.10"


class ExperienceRecorder:
    def __init__(self, events=None):
        self.events = copy.deepcopy(events or [])
        for index, event in enumerate(self.events):
            if not isinstance(event, dict) or event.get("sequence") != index:
                raise ValueError("Experience must preserve its original consecutive sequence")
        json_bytes(self.events)

    def record(self, kind, payload, worker_id=None):
        if not isinstance(kind, str) or not kind:
            raise ValueError("Experience kind must be nonempty text")
        event = {"sequence": len(self.events), "kind": kind, "payload": copy.deepcopy(payload)}
        if worker_id is not None:
            event["worker_id"] = worker_id
        json_bytes(event)
        self.events.append(event)
        return copy.deepcopy(event)

    def snapshot(self):
        return {"version": EXPERIENCE_VERSION, "events": copy.deepcopy(self.events)}

    def for_worker(self, worker_id):
        return copy.deepcopy([event for event in self.events if event.get("worker_id") == worker_id])

    def summary(self):
        counts = {}
        for event in self.events:
            counts[event["kind"]] = counts.get(event["kind"], 0) + 1
        return {"version": EXPERIENCE_VERSION, "count": len(self.events), "kinds": counts,
                "sha256": digest(json_bytes(self.events))}


def capture_port(session, captured):
    """Independent interface capture, usable for conformance without reconstruction."""
    class Port:
        __slots__ = ()

        def tools(self):
            value = session.tools()
            captured.append({"kind": "public_tools", "payload": copy.deepcopy(value)})
            return value

        def observe(self):
            value = session.observe()
            captured.append({"kind": "public_observation", "payload": copy.deepcopy(value)})
            return value

        def call(self, action, request_key=None, **arguments):
            payload = {"action": action, "arguments": copy.deepcopy(arguments),
                       "request_key": request_key}
            try:
                result = session.call(action, request_key=request_key, **arguments)
            except Exception as exc:
                payload["exception"] = {"type": type(exc).__name__, "message": str(exc)}
                captured.append({"kind": "tool_call", "payload": payload})
                raise
            payload["response"] = copy.deepcopy(result)
            captured.append({"kind": "tool_call", "payload": payload})
            return result

    return Port()
