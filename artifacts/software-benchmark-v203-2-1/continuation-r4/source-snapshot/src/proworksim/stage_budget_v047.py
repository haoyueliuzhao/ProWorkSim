"""v047 forward-only stage allowances over one unchanged actual-usage ledger."""

from __future__ import annotations

import copy

from .software_collaboration_v033 import TestBudget
from .software_organization_runtime_v038 import SharedTeamBudget
from .storage import atomic_write, digest, json_bytes
from .team_budget_v033 import V033PolicyBoundaryError
from .tool_outcomes import ToolRejection

VERSION = "organization-stage-budget-v0.47"
RESOURCE_KEYS = ("max_total_tokens", "max_decisions", "max_attempts", "max_test_runs")


def stage_plan(condition, token_budget):
    if condition not in ("S1", "D2", "D4", "I2", "I4", "P2", "P4"):
        raise ValueError("Unknown v047 architecture")
    if token_budget not in (250000, 500000):
        raise ValueError("v047 uses only the two independently declared token budgets")
    count = int(condition[1])
    members = [f"member_{index:03d}" for index in range(1, count + 1)]
    if condition[0] in "SD":
        rows = [("free", members, 100, 128, 32, False)]
    elif condition[0] == "I":
        rows = [("generate", members, 70, 88, 24, True), ("select", members[:1], 30, 40, 8, False)]
    elif condition == "P2":
        rows = [
            ("implement", members[:1], 60, 76, 20, False),
            ("review_revise_submit", members[1:], 40, 52, 12, False),
        ]
    else:
        rows = [
            ("implement", members[:1], 35, 44, 8, False),
            ("review", members[1:2], 20, 26, 8, False),
            ("revise_integrate", members[2:3], 25, 32, 8, False),
            ("validate_submit", members[3:], 20, 26, 8, False),
        ]
    return [
        {
            "stage_id": name,
            "members": active,
            "token_percent": percent,
            "limits": {
                "max_total_tokens": token_budget * percent // 100,
                "max_decisions": decisions,
                "max_attempts": decisions,
                "max_test_runs": tests,
            },
            "equal_member_subpools": split,
            "submit_allowed": index == len(rows) - 1,
        }
        for index, (name, active, percent, decisions, tests, split) in enumerate(rows)
    ]


def _active(plan, state):
    index = state["stage_index"]
    if type(index) is not int or not 0 <= index < len(plan):
        raise ValueError("Stage index is outside the frozen plan")
    row = plan[index]
    if state["stage_id"] != row["stage_id"]:
        raise ValueError("Stage identity differs from the frozen plan")
    return index, row


def _allowance(plan, state, key, member):
    index, stage = _active(plan, state)
    if stage["equal_member_subpools"]:
        if member is None:
            return stage["limits"][key]
        return stage["limits"][key] // len(stage["members"])
    return sum(row["limits"][key] for row in plan[: index + 1])


class StageBudgetBoundaryError(V033PolicyBoundaryError):
    """A local phase boundary, never permanent member or episode retirement."""

    STATUSES = V033PolicyBoundaryError.STATUSES | {"stage_budget_exhausted"}


class StageTeamBudget(SharedTeamBudget):
    def __init__(self, *, stage_provider, stage_plan, **kwargs):
        self.stage_provider = stage_provider
        self.stage_plan = copy.deepcopy(stage_plan)
        super().__init__(**kwargs)
        totals = {
            key: sum(row["limits"][key] for row in self.stage_plan)
            for key in ("max_total_tokens", "max_decisions", "max_attempts")
        }
        if totals != self._state["limits"]:
            raise ValueError("Stage allowances must sum to the original team allowance")

    def _stage_rows(self, member=None):
        state = self.stage_provider()
        _, stage = _active(self.stage_plan, state)
        rows = list(self._state["records"].values())
        if stage["equal_member_subpools"]:
            rows = [
                row
                for row in rows
                if row.get("stage_id") == stage["stage_id"]
                and (member is None or row["member"] == member)
            ]
        return state, stage, rows

    def stage_snapshot(self, member=None):
        with self._lock:
            state, stage, rows = self._stage_rows(member)
            charged = sum(row.get("charge", {}).get("charged_tokens", 0) for row in rows)
            held = sum(
                row["reservation"]["token_reservation"]
                for row in rows
                if row["status"] in {"reserved", "attempting"}
            )
            attempts = sum(row.get("attempt_started", False) for row in rows)
            pending = sum(row["status"] == "reserved" for row in rows)
            limits = {
                key: _allowance(self.stage_plan, state, key, member)
                for key in ("max_total_tokens", "max_decisions", "max_attempts")
            }
            value = {
                "version": VERSION,
                "stage_id": stage["stage_id"],
                "stage_index": state["stage_index"],
                "member_id": member,
                "limits": limits,
                "decisions": len(rows),
                "attempts": attempts,
                "charged_tokens": charged,
                "held_tokens": held,
                "remaining_decisions": limits["max_decisions"] - len(rows),
                "remaining_attempts": limits["max_attempts"] - attempts - pending,
                "available_tokens": limits["max_total_tokens"] - charged - held,
                "scope": "Equal independent generator subpool"
                if stage["equal_member_subpools"]
                else "Cumulative released allowance; all earlier usage deducted, remainder only moves forward",
            }
            value["state_sha256"] = digest(json_bytes(value))
            return value

    def _stage_fail(self, member, reason, limits):
        state = self.stage_snapshot(member)
        raise StageBudgetBoundaryError(
            "stage_budget_exhausted",
            reason,
            memory={"stage_budget": state},
            details={
                "limits": limits,
                "budget_kind": "stage_budget",
                "stage_budget": state,
                "team_budget": self.snapshot(),
                "permanent_retirement": False,
            },
        )

    def _eligible(self, member):
        state = self.stage_provider()
        _, stage = _active(self.stage_plan, state)
        if (
            member not in stage["members"]
            or member in state.get("finished_members", [])
            or member in state.get("unavailable_members", [])
            or member not in state.get("live_members", stage["members"])
            or state.get("closed")
        ):
            self._stage_fail(
                member,
                "This member has no active opportunity in the current stage",
                ["stage_membership"],
            )

    def consume_decision(self, member, call_id):
        with self._lock:
            self._member(member)
            self._eligible(member)
            if self.stage_snapshot(member)["remaining_decisions"] <= 0:
                self._stage_fail(
                    member, "Current stage decision allowance exhausted", ["stage_max_decisions"]
                )
            result = super().consume_decision(member, call_id)
            self._state["records"][call_id]["stage_id"] = self.stage_provider()["stage_id"]
            return self.snapshot() if result is not None else result

    def reserve(self, member, call_id, reservation):
        with self._lock:
            self._eligible(member)
            row = self._record(member, call_id)
            if row.get("stage_id") != self.stage_provider()["stage_id"]:
                self._fail("A call cannot reserve across a stage transition", integrity=True)
            before = self.stage_snapshot(member)
            # The original identity/context/global admission checks retain priority.
            result = super().reserve(member, call_id, reservation)
            failed = []
            if before["remaining_attempts"] <= 0:
                failed.append("stage_max_attempts")
            if reservation["token_reservation"] > before["available_tokens"]:
                failed.append("stage_max_total_tokens")
            if failed:
                row.update(
                    status="admission_rejected",
                    rejected_reservation=copy.deepcopy(reservation),
                    admission_limits=failed,
                    budget_kind="stage_budget",
                )
                self._stage_fail(
                    member, "Exact request reservation exceeds the released stage allowance", failed
                )
            return result

    def mark_dispatched(self, member, call_id):
        """Host receipt immediately before calling the actual resident transport."""
        with self._lock:
            row = self._record(member, call_id)
            if row["status"] != "attempting" or row.get("dispatch_started"):
                self._fail(
                    "Dispatch marker requires one pending, not-yet-dispatched attempt",
                    integrity=True,
                )
            row["dispatch_started"] = True
            return self.snapshot()

    def cancel_before_dispatch(self, member, call_id, reason="soft_deadline_before_dispatch"):
        """Cancel only a proven host pre-dispatch boundary, retaining its decision."""
        with self._lock:
            row = self._record(member, call_id)
            if (
                row["status"] not in {"reserved", "attempting"}
                or row.get("dispatch_started")
                or "charge" in row
            ):
                self._fail(
                    "Dispatched or settled work cannot be cancelled as pre-dispatch", integrity=True
                )
            row.update(
                status="cancelled_before_dispatch",
                attempt_started=False,
                cancellation={
                    "reason": reason,
                    "dispatch_started": False,
                    "actual_usage": 0,
                    "charged_tokens": 0,
                },
            )
            return self.snapshot()

    def assert_transition_ready(self):
        if any(
            row["status"] in {"reserved", "attempting"} for row in self._state["records"].values()
        ):
            raise ValueError(
                "A stage cannot advance while an original reservation or attempt is pending"
            )


class StageTestBudget(TestBudget):
    def __init__(self, output=None, *, stage_provider, stage_plan):
        super().__init__(output)
        self.stage_provider, self.stage_plan = stage_provider, copy.deepcopy(stage_plan)

    def stage_snapshot(self, member=None):
        state = self.stage_provider()
        _, stage = _active(self.stage_plan, state)
        rows = self.records
        if stage["equal_member_subpools"]:
            rows = [
                row
                for row in rows
                if row["stage_id"] == stage["stage_id"]
                and (member is None or row["actor_id"] == member)
            ]
        limit = _allowance(self.stage_plan, state, "max_test_runs", member)
        return {
            "stage_id": stage["stage_id"],
            "member_id": member,
            "limit": limit,
            "used": len(rows),
            "remaining": limit - len(rows),
        }

    def consume(self, actor):
        state = self.stage_provider()
        _, stage = _active(self.stage_plan, state)
        if (
            actor not in stage["members"]
            or actor in state.get("finished_members", [])
            or actor in state.get("unavailable_members", [])
            or actor not in state.get("live_members", stage["members"])
            or state.get("closed")
            or self.stage_snapshot(actor)["remaining"] <= 0
        ):
            raise ToolRejection(
                "No public test allowance is available in this member's current stage",
                code="stage_test_budget_exhausted",
                category="capability_gap",
            )
        super().consume(actor)
        self.records[-1]["stage_id"] = stage["stage_id"]
        if self.output is not None:
            atomic_write(self.output, json_bytes(self.snapshot()))
