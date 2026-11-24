"""One conditional, same-member repair opportunity for a rejected diagnosis handoff."""

from copy import deepcopy
import json

from .software_context_builder_v230 import compact
from .software_graph_execution_v230 import CALL_BOUND
from .software_organization_v232 import OrganizationExecution


class HandoffExecution(OrganizationExecution):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pending_task = None
        self.example_sent = False
        self.attempt = None

    def note(self, kind, details):
        self.trace.observe(
            kind,
            [self.version, self.runtime.opportunities],
            layer=2,
            graph=self.version,
            agent=self.diagnostician,
            result=kind,
            details=details,
        )

    def activate(self, node, observer, frozen, choice):
        target = frozen["options"][choice["option"]]
        diagnosis = target["op"] == "diagnosis"
        if diagnosis:
            budget = self.runtime.team_budget.snapshot()
            if (
                budget["available_tokens"] < 4 * CALL_BOUND
                or min(budget["remaining_attempts"], budget["remaining_decisions"]) < 4
            ):
                return {
                    "activated": False,
                    "reason": "handoff_contingency_unavailable",
                    "required": 4 * CALL_BOUND,
                }
        record = super().activate(node, observer, frozen, choice)
        if diagnosis and record.get("changed"):
            self.pending_task = target["task"]
            self.diagnostician = target["assignee"]
            self.hold = ("handoff_contingency", self.diagnostician)
            self.repair = ("handoff_repair", self.diagnostician)
            self.grants.append(self.hold)
            self.note("repair_reserved", {"tokens": CALL_BOUND, "task": self.pending_task})
        return record

    def bind_recorder(self, runtime):
        super().bind_recorder(runtime)
        original = runtime.recorder.record

        def record(kind, payload, worker_id=None):
            result = original(kind, payload, worker_id=worker_id)
            if (
                self.pending_task is None
                or worker_id != self.diagnostician
                or self.hold not in self.grants
            ):
                return result
            if kind == "model_response":
                calls = payload["response"]["choices"][0]["message"].get("tool_calls") or []
                self.attempt = None
                if len(calls) == 1 and calls[0]["function"]["name"] == "send_message":
                    try:
                        args = json.loads(calls[0]["function"]["arguments"])
                    except (ValueError, TypeError):
                        return result
                    if (
                        isinstance(args, dict)
                        and args.get("task_id") == self.pending_task
                        and isinstance(args.get("body"), str)
                        and args["body"].startswith("DIAG ")
                    ):
                        self.attempt = (
                            payload["call_id"],
                            payload["opportunity_id"],
                            calls[0]["id"],
                        )
            elif (
                kind == "model_format_error"
                and self.attempt
                and self.attempt[:2] == (payload["call_id"], payload["opportunity_id"])
            ):
                error = (
                    payload.get("parse_diagnostics", {}).get("adapter_parser", {}).get("failure")
                    or {}
                )
                if error.get("stage") == "public_schema":
                    self.grants.remove(self.hold)
                    self.grants.insert(0, self.repair)
                    self.note(
                        "repair_triggered",
                        {
                            "call": self.attempt[0],
                            "tool_call_id": self.attempt[2],
                            "opportunity": self.attempt[1],
                            "constraint": error.get("constraint"),
                        },
                    )
                self.attempt = None
            return result

        runtime.recorder.record = record

    def select_next(self):
        if self.pending_task is None:
            return super().select_next()
        rt = self.runtime
        world = rt.prepared.world
        duty = world.protocol()["graph_control"]["duties"].get(self.pending_task, {})
        if duty.get("status") != "pending":
            for grant in (self.hold, self.repair):
                if grant in self.grants:
                    self.grants.remove(grant)
                    self.note("repair_released", {"reason": "duty_closed"})
            self.pending_task = None
            return super().select_next()
        if not self.example_sent:
            boundary = world.protocol()["graph_control"]["versions"][-1]["after_event"]
            seq = next(
                (
                    e["sequence"]
                    for e in reversed(world.state["software_events"])
                    if e["actor_id"] == self.diagnostician
                    and e["sequence"] > boundary
                    and (e["kind"] in ("read", "test", "search") or "review" in e["kind"])
                ),
                None,
            )
            if seq is not None:
                args = {
                    "recipient": duty["recipient"],
                    "task_id": self.pending_task,
                    "body": f"DIAG {seq} <your specific finding supported by this event>",
                }
                rt.policies[self.diagnostician].conversation.send_message(
                    "When ready to hand off, call send_message with this argument shape: "
                    + compact(args)
                    + ". Replace the placeholder with your own finding. Use that event only if it supports the finding, otherwise cite another listed own event. Do not add a recipe argument."
                )
                self.note("handoff_example", {"arguments": args})
                self.example_sent = True
        if self.grants and self.grants[0] == self.repair:
            if (
                self.wake("handoff_repair", self.diagnostician)
                and self.diagnostician in world.organization_active_members()
            ):
                rt.team_budget.native_allocation = (
                    self.native_limit - (len(self.grants) - 1) * CALL_BOUND
                )
                rt.sync_members()
                rt.organization_blocked = False
                rt._selected = rt.schedule.choose({self.diagnostician})
                rt.cursor = rt.labels.index(self.diagnostician)
                self.selected_phase = self.repair
                return deepcopy(rt._selected)
            self.grants.pop(0)
            self.note("repair_released", {"reason": "member_unavailable"})
        if self.grants == [self.hold]:
            rt.team_budget.native_allocation = self.native_limit
            if rt.team_budget.snapshot()["available_tokens"] >= 2 * CALL_BOUND:
                rt.team_budget.native_allocation -= CALL_BOUND
                choice = self.normal_select()
                if choice is not None:
                    return choice
            self.grants.clear()
            self.note("repair_released", {"reason": "last_ordinary_window_closed_without_trigger"})
        return super().select_next()
