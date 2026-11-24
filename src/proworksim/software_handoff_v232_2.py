"""Retain the one-shot correction allowance throughout the owner's send eligibility."""

from copy import deepcopy
from .software_handoff_v232_1 import HandoffExecution
from .software_graph_execution_v230 import CALL_BOUND


class ProtectedHandoffExecution(HandoffExecution):
    def select_next(self):
        # The frozen r1 controller owns all phases except the isolated unused reserve.
        if self.pending_task is None or self.grants != [self.hold]:
            return super().select_next()
        rt = self.runtime
        world = rt.prepared.world
        duty = world.protocol()["graph_control"]["duties"].get(self.pending_task, {})
        if duty.get("status") != "pending":
            return super().select_next()
        if self.diagnostician in rt.stopped:
            self.grants.clear()
            self.note("repair_released", {"reason": "owner_permanently_stopped"})
            return super().select_next()
        rt.team_budget.native_allocation = self.native_limit
        snapshot = rt.team_budget.snapshot()
        remaining = snapshot["available_tokens"]
        rt.team_budget.native_allocation = self.native_limit - CALL_BOUND
        # Near the boundary offer the remaining ordinary room to the assignee first.
        # The normal SDK still measures its complete request and may reject it pre-dispatch.
        if (
            CALL_BOUND < remaining < 2 * CALL_BOUND
            and self.example_sent
            and self.diagnostician not in rt.waiting
            and self.diagnostician not in rt.work_ended
            and self.diagnostician in world.organization_active_members()
        ):
            rt.sync_members()
            rt.organization_blocked = False
            rt._selected = rt.schedule.choose({self.diagnostician})
            rt.cursor = rt.labels.index(self.diagnostician)
            self.selected_phase = None
            return deepcopy(rt._selected)
        # Do not spend the correction credit on a first send or silently cancel it on quiescence.
        return self.normal_select()
