"""Record a sender decision and a separate, evidence-bound recipient disposition."""

from copy import deepcopy
from .software_context_builder_v230 import compact, object_text, recover_observations
from .software_graph_execution_v230 import World, CALL_BOUND
from .software_inbox_preview_v232_4 import PreviewExecution

EVIDENCE_TOOLS = {
    "read_file",
    "search_file",
    "search_repository",
    "run_tests",
    "run_patch_review_tests",
    "read_test_result",
    "read_work_event",
    "diff_workspace",
}
CHOICES = {"ADOPT", "DEFER", "REJECT", "SKIP"}


def eligible_existing(world, actor):
    ref = world.org_current_identity(actor)["source_reference"]
    return [
        e["sequence"]
        for e in world.state["software_events"]
        if e["actor_id"] == actor
        and e.get("source_reference") == ref
        and e["kind"] in ("read", "search", "test")
    ]


def has_full(wire, event):

    def matches(item):
        return isinstance(item, dict) and all(
            item.get(k) == event[k] for k in ("sequence", "recipient", "actor_id", "body")
        )

    for m in wire["messages"]:
        if m["role"] == "tool":
            v = object_text(m.get("content")) or {}
            if v.get("ok") and matches(v.get("result")):
                return True
    return any(
        matches(m) for obs in recover_observations(wire).values() for m in obs.get("messages", [])
    )


class DecisionWorld(World):
    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        ctrl = self.protocol().get("graph_control") or {}
        tid = getattr(self, "decision_task", None)
        duty = ctrl.get("duties", {}).get(tid)
        invoke = super()._tool_project_action
        if duty is None:
            return invoke(actor, project_id, tool, arguments, interface_profile)
        body = arguments.get("body", "") if tool == "send_message" else ""
        fields = body.split(maxsplit=2)
        tag = fields[0] if fields else ""
        if tag in CHOICES and (
            actor != duty["recipient"]
            or duty["status"] != "handed_off"
            or duty.get("recipient_disposition")
        ):
            self.org_reject(
                "Disposition must address one delivered, unprocessed diagnosis.",
                "no_open_disposition",
            )
        if actor == duty["owner"] and duty["status"] == "pending" and self.sender_due:
            choice = (
                arguments.get("task_id") == tid and arguments.get("recipient") == duty["recipient"]
            )
            if duty.get("awaiting_evidence") and tool in EVIDENCE_TOOLS:
                result = invoke(actor, project_id, tool, arguments, interface_profile)
                duty["awaiting_evidence"] = False
                return result
            if not choice or tag not in ("DIAG", "BLOCK", "NEED"):
                self.org_reject(
                    "Send your diagnosis, a concrete BLOCK, or NEED followed by the missing evidence.",
                    "sender_disposition_due",
                )
            if tag == "NEED" and (len(body.split(maxsplit=1)) != 2 or duty.get("evidence_request")):
                self.org_reject(
                    "Name one missing piece of evidence; this extension is available once.",
                    "invalid_evidence_request",
                )
            result = invoke(actor, project_id, tool, arguments, interface_profile)
            row = {"choice": tag, "sequence": result["message_sequence"], "body": body}
            duty.setdefault("sender_decisions", []).append(row)
            if tag == "BLOCK":
                duty["status"] = "blocked"
            if tag == "NEED":
                duty.update(awaiting_evidence=True, evidence_request=row)
            return result
        if (
            actor == duty["recipient"]
            and duty["status"] == "handed_off"
            and not duty.get("recipient_disposition")
        ):
            seq = duty["message_sequence"]
            if tool == "read_work_event" and arguments.get("sequence") == seq:
                if seq in self.full_exposures:
                    self.org_reject(
                        "Full text already presented. Record the disposition and reason.",
                        "recipient_disposition_due",
                    )
                return invoke(actor, project_id, tool, arguments, interface_profile)
            if (
                tag not in CHOICES
                or len(fields) != 3
                or fields[1] != str(seq)
                or arguments.get("recipient") != duty["owner"]
                or arguments.get("task_id") != tid
            ):
                self.org_reject(
                    f"Read message {seq} or record its explicit disposition by send_message before proceeding.",
                    "recipient_disposition_due",
                )
            evidence = None
            reason = fields[2]
            if tag == "SKIP":
                parts = reason.split(maxsplit=1)
                if (
                    len(parts) != 2
                    or not parts[0].isdecimal()
                    or int(parts[0]) not in eligible_existing(self, actor)
                ):
                    self.org_reject(
                        "SKIP requires a real own event on the current version and a reason.",
                        "same_version_evidence_required",
                    )
                evidence = int(parts[0])
                reason = parts[1]
            elif seq not in self.full_exposures:
                self.org_reject(
                    "Read the original addressed message, or cite sufficient same-version evidence using SKIP.",
                    "full_exposure_required",
                )
            result = invoke(actor, project_id, tool, arguments, interface_profile)
            duty["recipient_disposition"] = {
                "choice": tag,
                "reason": reason,
                "message_sequence": seq,
                "response_sequence": result["message_sequence"],
                "own_evidence": evidence,
                "source_reference": self.org_current_identity(actor)["source_reference"],
                "full_exposure_request": self.full_exposures.get(seq),
            }
            return result
        return invoke(actor, project_id, tool, arguments, interface_profile)


class DispositionExecution(PreviewExecution):
    def __init__(self, backend, *args, **kwargs):
        self.sender_credit = self.follow_credit = False

        def track(route, payload):
            response = backend(route, payload)
            if (
                route != "/chat/completions"
                or payload.get("usage_id") != "agent"
                or payload["member_id"] != getattr(self, "recipient", None)
            ):
                return response
            world = self.runtime.prepared.world
            duty = world.protocol()["graph_control"]["duties"][self.receive_task]
            if duty["status"] == "handed_off":
                seq = duty["message_sequence"]
                event = next(e for e in world.state["software_events"] if e["sequence"] == seq)
                if has_full(payload["wire"], event):
                    world.full_exposures.setdefault(seq, payload["request_id"])
            return response

        super().__init__(track, *args, **kwargs)

    def attach(self, runtime):
        super().attach(runtime)
        world = runtime.prepared.world
        world.__class__ = DecisionWorld
        world.sender_due = False
        world.full_exposures = {}

    def activate(self, node, observer, frozen, choice):
        if frozen["options"][choice["option"]]["op"] == "diagnosis":
            b = self.runtime.team_budget.snapshot()
            if (
                b["available_tokens"] < 7 * CALL_BOUND
                or min(b["remaining_attempts"], b["remaining_decisions"]) < 7
            ):
                return {
                    "activated": False,
                    "reason": "disposition_opportunities_unavailable",
                    "required": 7 * CALL_BOUND,
                }
        record = super().activate(node, observer, frozen, choice)
        if record.get("changed") and self.pending_task:
            self.sender_credit = self.follow_credit = True
            self.native_limit -= 2 * CALL_BOUND
            self.runtime.team_budget.native_allocation = self.native_limit
            self.runtime.prepared.world.decision_task = self.receive_task
            self.receipt_note(
                "disposition_credits_reserved",
                {"sender": CALL_BOUND, "recipient_followup": CALL_BOUND},
            )
        return record

    def priority(self, phase, actor):
        rt = self.runtime
        self.native_limit += CALL_BOUND
        if (
            not self.wake(phase, actor)
            or actor not in rt.prepared.world.organization_active_members()
        ):
            self.receipt_note("disposition_unavailable", {"phase": phase, "actor": actor})
            return super().select_next()
        self.grants.insert(0, (phase, actor))
        rt.team_budget.native_allocation = self.native_limit - (len(self.grants) - 1) * CALL_BOUND
        rt.sync_members()
        rt.organization_blocked = False
        rt._selected = rt.schedule.choose({actor})
        rt.cursor = rt.labels.index(actor)
        self.selected_phase = (phase, actor)
        return deepcopy(rt._selected)

    def select_next(self):
        if self.sender_credit or self.follow_credit:
            rt = self.runtime
            w = rt.prepared.world
            duty = w.protocol()["graph_control"]["duties"][self.receive_task]
            tid = self.receive_task
            if self.sender_credit and ("new_duty", self.diagnostician) not in self.grants:
                self.sender_credit = False
                if duty["status"] == "pending":
                    eligible = [
                        e["sequence"]
                        for e in w.state["software_events"]
                        if e["sequence"]
                        > w.protocol()["graph_control"]["versions"][-1]["after_event"]
                        and e["actor_id"] == self.diagnostician
                        and (e["kind"] in ("read", "test", "search") or "review" in e["kind"])
                    ]
                    sample = {
                        "recipient": self.recipient,
                        "task_id": tid,
                        "body": f"DIAG {eligible[-1] if eligible else '<own event>'} <your specific supported finding>",
                    }
                    w.sender_due = True
                    rt.policies[self.diagnostician].conversation.send_message(
                        f"Your protected disposition turn for {tid} is now due. Use send_message, recipient {self.recipient}, task_id {tid}, body only. "
                        f"Send DIAG <own event> <finding> (eligible events: {eligible[-3:]}), BLOCK <kind> <specific obstacle>, "
                        "or NEED <one specific missing piece of evidence>. NEED permits one evidence action, then DIAG or BLOCK. Choose yourself. BLOCK types: permission, dependency, in_flight, budget, state_conflict. Example arguments: "
                        + compact(sample)
                    )
                    return self.priority("sender_disposition", self.diagnostician)
                self.native_limit += CALL_BOUND
            if self.follow_credit and (
                duty["status"] == "blocked" or self.recipient_state in ("released", "unavailable")
            ):
                self.follow_credit = False
                self.native_limit += CALL_BOUND
                if self.recipient_state == "reserved":
                    self.recipient_state = "released"
                    self.native_limit += CALL_BOUND
                self.receipt_note("disposition_released_blocked", {})
            if self.follow_credit and duty["status"] == "handed_off":
                if self.recipient_state == "reserved":
                    seq = duty["message_sequence"]
                    rt.policies[self.recipient].conversation.send_message(
                        f"You received message {seq} for {tid}. Before other project work, read_work_event(sequence={seq}) if needed, then send_message to {self.diagnostician}, task_id {tid}. "
                        f"Use body ADOPT {seq} <reason>, DEFER {seq} <reason> or REJECT {seq} <reason> after seeing the full body. "
                        f"If prior evidence already suffices, use SKIP {seq} <own same-version event> <reason>. Eligible events: {eligible_existing(w, self.recipient)[-4:]}. Your technical choice is yours."
                    )
                if self.recipient_state == "consumed":
                    self.follow_credit = False
                    if not duty.get("recipient_disposition"):
                        return self.priority("record_disposition", self.recipient)
                    self.native_limit += CALL_BOUND
        return super().select_next()
