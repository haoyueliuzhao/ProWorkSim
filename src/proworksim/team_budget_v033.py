"""One shared v0.33 decision/attempt/token ledger for a fixed software episode.

Reservations are not usage. A completed local call is charged once from its
actual, identity-bound token trace; an uncertain attempted call retains its full
reservation. This module neither generates an action nor evaluates work.
"""
import copy
import threading

from .staff_runtime import PolicyBoundaryError
from .storage import digest, json_bytes

VERSION = "shared-team-budget-v0.33"


class V033PolicyBoundaryError(PolicyBoundaryError):
    """Versioned blocking states without changing the historical runtime enum."""
    STATUSES = PolicyBoundaryError.STATUSES | {
        "team_budget_exhausted", "execution_integrity_error", "model_permission_error"}


class SharedTeamBudget:
    def __init__(self, *, max_decisions=128, max_attempts=128, max_total_tokens=500000,
                 members, team_id, require_exact_resident=True):
        limits = {"max_decisions": max_decisions, "max_attempts": max_attempts,
                  "max_total_tokens": max_total_tokens}
        if any(type(value) is not int or value <= 0 for value in limits.values()):
            raise ValueError("Team budget limits must be positive integers")
        members = list(members)
        if (not members or len(set(members)) != len(members)
                or any(not isinstance(member, str) or not member for member in members)
                or not isinstance(team_id, str) or not team_id or type(require_exact_resident) is not bool):
            raise ValueError("A team ledger requires a fixed episode and distinct explicit members")
        self._lock = threading.RLock()
        self._state = {"version": VERSION, "team_id": team_id, "members": members,
                       "limits": limits, "require_exact_resident": require_exact_resident,
                       "binding": None, "records": {}, "integrity_failure": None}

    def snapshot(self):
        with self._lock:
            value = copy.deepcopy(self._state)
            rows = list(value["records"].values())
            charged = sum(row.get("charge", {}).get("charged_tokens", 0) for row in rows)
            held = sum(row["reservation"]["token_reservation"] for row in rows
                       if row["status"] in {"reserved", "attempting"})
            attempts = sum(row.get("attempt_started", False) for row in rows)
            value.update(decisions=len(rows), attempts=attempts, charged_tokens=charged, held_tokens=held,
                         remaining_decisions=value["limits"]["max_decisions"] - len(rows),
                         remaining_attempts=value["limits"]["max_attempts"] - attempts,
                         available_tokens=value["limits"]["max_total_tokens"] - charged - held)
            value["state_sha256"] = digest(json_bytes(value))
            return value

    def _fail(self, reason, *, limits=(), integrity=False, status=None, budget_kind=None):
        if integrity:
            self._state["integrity_failure"] = reason
        snapshot = self.snapshot()
        details = {"limits": list(limits), "team_budget": snapshot}
        if budget_kind is not None:
            details["budget_kind"] = budget_kind
        raise V033PolicyBoundaryError(status or ("execution_integrity_error" if integrity else "team_budget_exhausted"),
                                      reason, memory={"team_budget": snapshot}, details=details)

    def _member(self, member):
        if self._state["integrity_failure"]:
            self._fail(self._state["integrity_failure"], integrity=True)
        if member not in self._state["members"]:
            self._fail("Worker is not a member of this episode's team ledger", integrity=True)

    def _record(self, member, call_id):
        self._member(member)
        row = self._state["records"].get(call_id)
        if row is None or row["member"] != member:
            self._fail("Team call identity is absent or belongs to another member", integrity=True)
        return row

    def consume_decision(self, member, call_id):
        with self._lock:
            self._member(member)
            if not isinstance(call_id, str) or not call_id or call_id in self._state["records"]:
                self._fail("A consumed team decision identity cannot be reused or resampled", integrity=True)
            if self.snapshot()["remaining_decisions"] <= 0:
                self._fail("Shared team decision budget exhausted", limits=["team_max_decisions"])
            self._state["records"][call_id] = {"member": member, "call_id": call_id,
                                              "status": "decision_consumed", "attempt_started": False}
            return self.snapshot()

    def reserve(self, member, call_id, reservation):
        with self._lock:
            row = self._record(member, call_id)
            if row["status"] != "decision_consumed":
                self._fail("A team decision may reserve only one actual attempt", integrity=True)
            amount = reservation.get("token_reservation")
            if type(amount) is not int or amount <= 0:
                self._fail("Team reservation lacks a positive token upper bound", integrity=True)
            if self._state["require_exact_resident"]:
                prepared = reservation.get("preparation") or {}
                if not isinstance(prepared, dict):
                    self._fail("Team admission requires structured resident preparation", integrity=True)
                payload = {key: value for key, value in prepared.items() if key != "preparation_sha256"}
                bounds_valid = (type(prepared.get("prompt_tokens")) is int and prepared["prompt_tokens"] > 0
                    and type(prepared.get("reserved_output_tokens")) is int and prepared["reserved_output_tokens"] > 0
                    and type(prepared.get("context_limit")) is int
                    and 0 < prepared["reserved_output_tokens"] < prepared["context_limit"])
                if (reservation.get("reservation_kind") != "exact_resident_prompt"
                        or prepared.get("version") != "resident-request-budget-v0.31r3"
                        or prepared.get("preparation_sha256") != digest(json_bytes(payload))
                        or not bounds_valid
                        or type(prepared.get("fits")) is not bool
                        or prepared["fits"] != (prepared["prompt_tokens"] + prepared["reserved_output_tokens"] <= prepared["context_limit"])
                        or prepared.get("window_id") != self._state["team_id"]
                        or not prepared.get("actor_identity")
                        or amount != prepared.get("prompt_tokens", -1) + prepared.get("reserved_output_tokens", -1)
                        or any(not isinstance(prepared.get(key), str) or len(prepared[key]) != 64
                               or any(character not in "0123456789abcdef" for character in prepared[key]) for key in (
                            "original_request_sha256", "selected_request_sha256", "rendered_prompt_sha256",
                            "input_ids_sha256", "recipe_sha256"))):
                    self._fail("Team admission requires the sealed exact resident prompt and episode identity", integrity=True)
                binding = {key: copy.deepcopy(prepared[key]) for key in ("actor_identity", "window_id", "recipe_sha256")}
                if self._state["binding"] is not None and self._state["binding"] != binding:
                    self._fail("Team members must use the same frozen actor, window and recipe", integrity=True)
                if prepared["fits"] is False:
                    row.update(status="admission_rejected", rejected_reservation=copy.deepcopy(reservation),
                               admission_limits=["context_capacity"], budget_kind="context_capacity")
                    self._fail("The irreducible selected prompt exceeds the fixed context capacity before generation",
                               limits=["context_capacity"], status="model_budget_exhausted", budget_kind="context_capacity")
            else:
                binding = None
            snapshot = self.snapshot()
            pending = sum(record["status"] == "reserved" for record in self._state["records"].values())
            failed = []
            if snapshot["attempts"] + pending >= self._state["limits"]["max_attempts"]:
                failed.append("team_max_attempts")
            if amount > snapshot["available_tokens"]:
                failed.append("team_max_total_tokens")
            if failed:
                row.update(status="admission_rejected", rejected_reservation=copy.deepcopy(reservation),
                           admission_limits=failed)
                self._fail("Shared team budget prevents another generation", limits=failed)
            if binding is not None:
                self._state["binding"] = binding
            row.update(status="reserved", reservation=copy.deepcopy(reservation))
            return self.snapshot()

    def begin_attempt(self, member, call_id):
        with self._lock:
            row = self._record(member, call_id)
            if row["status"] != "reserved":
                self._fail("Generation requires one still-held team reservation", integrity=True)
            row.update(status="attempting", attempt_started=True)

    def settle(self, member, call_id, body=None):
        """Settle once; repeated identical cleanup is idempotent, never a refund."""
        with self._lock:
            row = self._record(member, call_id)
            body_sha = digest(json_bytes(body))
            if row["status"] == "settled":
                if row["charge"]["response_body_sha256"] != body_sha:
                    self._fail("An already settled call cannot acquire another response or usage", integrity=True)
                return copy.deepcopy(row["charge"])
            if row["status"] != "attempting":
                self._fail("Only an actually attempted call can consume response tokens", integrity=True)
            reservation = row["reservation"]
            charge = {"charged_tokens": reservation["token_reservation"],
                      "usage_status": "uncertain_attempt_charged_reservation",
                      "reported_usage": None, "response_body_sha256": body_sha}
            integrity_error = None
            if body is not None:
                usage = body.get("usage") if isinstance(body, dict) else None
                valid = (isinstance(usage, dict) and all(type(usage.get(key)) is int and usage[key] >= 0
                         for key in ("prompt_tokens", "completion_tokens", "total_tokens")))
                if not valid or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]:
                    integrity_error = "Actual resident usage is missing, malformed or internally inconsistent"
                elif usage["total_tokens"] > reservation["token_reservation"]:
                    integrity_error = "Actual resident usage exceeds its admitted upper bound"
                elif self._state["require_exact_resident"]:
                    prepared = reservation["preparation"]
                    trace = body.get("token_trace") or {}
                    inputs, outputs = trace.get("input_ids"), trace.get("output_ids")
                    if (not isinstance(inputs, list) or not isinstance(outputs, list)
                            or any(type(token) is not int for token in [*inputs, *outputs])
                            or digest(json_bytes(inputs)) != prepared["input_ids_sha256"]
                            or len(inputs) != usage["prompt_tokens"] or len(outputs) != usage["completion_tokens"]
                            or usage["prompt_tokens"] != prepared["prompt_tokens"]
                            or usage["completion_tokens"] > prepared["reserved_output_tokens"]
                            or body.get("actor_identity") != prepared["actor_identity"]
                            or body.get("online_window_id") != prepared["window_id"]
                            or not isinstance(body.get("id"), str) or not body["id"]):
                        integrity_error = "Actual resident trace/usage/actor/window differs from its held reservation"
                if integrity_error is None:
                    response_id = body.get("id")
                    if response_id and any(other.get("charge", {}).get("response_id") == response_id
                                           for key, other in self._state["records"].items() if key != call_id):
                        integrity_error = "A resident response identity was reused across team decisions"
                    else:
                        charge.update(charged_tokens=usage["total_tokens"], usage_status="reported_actual_trace",
                                      reported_usage=copy.deepcopy(usage), response_id=response_id)
            row.update(status="settled", charge=charge)
            if integrity_error:
                row["integrity_error"] = integrity_error
                self._fail(integrity_error, integrity=True)
            return copy.deepcopy(charge)

    def cleanup(self, member, call_id):
        """Release only pre-generation holds; attempted unknown work is charged."""
        with self._lock:
            row = self._state["records"].get(call_id)
            if row is None:
                return
            if row["member"] != member:
                self._fail("Cannot clean up another member's team call", integrity=True)
            if row["status"] == "reserved":
                row["status"] = "cancelled_before_attempt"
            elif row["status"] == "attempting":
                self.settle(member, call_id, None)

    @classmethod
    def from_snapshot(cls, snapshot):
        """Restore one shared ledger; pending attempts cannot be replayed for free."""
        payload = {key: value for key, value in snapshot.items() if key != "state_sha256"}
        if snapshot.get("state_sha256") != digest(json_bytes(payload)) or snapshot.get("version") != VERSION:
            raise ValueError("Team snapshot checksum/version mismatch")
        value = cls(**snapshot["limits"], members=snapshot["members"], team_id=snapshot["team_id"],
                    require_exact_resident=snapshot["require_exact_resident"])
        for key in value._state:
            value._state[key] = copy.deepcopy(snapshot[key])
        if value.snapshot() != snapshot:
            raise ValueError("Team snapshot counters do not match its original call ledger")
        if min(snapshot["remaining_decisions"], snapshot["remaining_attempts"], snapshot["available_tokens"]) < 0:
            raise ValueError("Team snapshot exceeds its frozen allowance")
        for call_id, row in value._state["records"].items():
            if row["call_id"] != call_id or row["member"] not in value._state["members"]:
                raise ValueError("Team snapshot call/member identity mismatch")
            if row["status"] in {"reserved", "attempting"}:
                value.cleanup(row["member"], call_id)
                row["restored_pending_call_not_resampled"] = True
        return value
