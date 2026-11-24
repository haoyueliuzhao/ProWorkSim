"""Reserve one native recipient turn until an evidence-bound diagnosis enters its inbox."""

from copy import deepcopy

from .software_graph_execution_v230 import CALL_BOUND
from .software_handoff_v232_2 import ProtectedHandoffExecution


class RecipientExecution(ProtectedHandoffExecution):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.recipient_state = "inactive"

    def activate(self, node, observer, frozen, choice):
        target = frozen["options"][choice["option"]]
        diagnosis = target["op"] == "diagnosis"
        if diagnosis:
            budget = self.runtime.team_budget.snapshot()
            if (
                budget["available_tokens"] < 5 * CALL_BOUND
                or min(budget["remaining_attempts"], budget["remaining_decisions"]) < 5
            ):
                return {
                    "activated": False,
                    "reason": "recipient_request_unavailable",
                    "required": 5 * CALL_BOUND,
                }
        record = super().activate(node, observer, frozen, choice)
        if diagnosis and record.get("changed"):
            self.receive_task = target["task"]
            self.recipient = record["after"]["duties"][self.receive_task]["recipient"]
            self.receive_grant = ("receive_handoff", self.recipient)
            self.recipient_state = "reserved"
            self.native_limit -= CALL_BOUND
            self.runtime.team_budget.native_allocation = self.native_limit
            self.receipt_note("recipient_reserved", {"tokens": CALL_BOUND})
        return record

    def receipt_note(self, kind, details):
        self.trace.observe(
            kind,
            [self.version, self.runtime.opportunities],
            layer=2,
            graph=self.version,
            agent=self.recipient,
            result=kind,
            details={"task": self.receive_task, **details},
        )

    def select_next(self):
        rt = self.runtime
        if self.recipient_state == "reserved":
            control = rt.prepared.world.protocol()["graph_control"]
            duty = control["duties"].get(self.receive_task, {})
            if duty.get("status") == "handed_off" and duty.get("recipient") == self.recipient:
                # The world commit is the trigger. No peer text is inserted into the recipient session.
                self.native_limit += CALL_BOUND
                for credit in (self.hold, self.repair):
                    if credit in self.grants:
                        self.grants.remove(credit)
                        self.note("repair_released", {"reason": "duty_closed"})
                self.pending_task = None
                self.grants.insert(0, self.receive_grant)
                self.recipient_state = "ready"
                self.receipt_note(
                    "recipient_eligible",
                    {"message_sequence": duty["message_sequence"], "evidence": duty["evidence"]},
                )
            elif self.recipient in rt.stopped or self.diagnostician in rt.stopped:
                self.native_limit += CALL_BOUND
                self.recipient_state = "released"
                self.receipt_note(
                    "recipient_released", {"reason": "member_permanently_stopped_before_handoff"}
                )
        if self.recipient_state == "ready":
            if (
                not self.wake("receive_handoff", self.recipient)
                or self.recipient not in rt.prepared.world.organization_active_members()
            ):
                self.grants.remove(self.receive_grant)
                self.selected_phase = None
                self.recipient_state = "unavailable"
                self.receipt_note("recipient_blocked", {"reason": "recipient_unavailable"})
            else:
                rt.team_budget.native_allocation = (
                    self.native_limit - (len(self.grants) - 1) * CALL_BOUND
                )
                rt.sync_members()
                rt.organization_blocked = False
                rt._selected = rt.schedule.choose({self.recipient})
                rt.cursor = rt.labels.index(self.recipient)
                self.selected_phase = self.receive_grant
                return deepcopy(rt._selected)
        return super().select_next()

    def post(self, route, payload):
        response = super().post(route, payload)
        if self.recipient_state == "ready" and self.receive_grant not in self.grants:
            self.recipient_state = "consumed"
        return response
