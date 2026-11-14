"""Observer integrity, request-bound views, and time-scoped assessment contracts.

This module is an evaluator-side contract, not an organizational detector or a
policy input adapter. The capture boundary must authenticate request attribution
and provider acceptance. Hashes establish consistency with supplied bytes, not
independent proof that a provider was called. CPU witnesses remain CPU witnesses.
No published artifact, event, or reconstructed source is expanded into a member
view. A view uses one actual accepted request; historical context omitted from
that request is not silently restored.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping


INTEGRITY_DIMENSIONS = (
    "requests", "responses", "tool_receipts", "ownership", "dependencies",
    "communication", "versions", "delivery",
)
INTEGRITY_STATES = ("COMPLETE", "PARTIAL", "INVALID")
LAYER_VALUES = {
    "exposure": {"EXPOSED", "NOT_EXPOSED", "UNKNOWN"},
    "preconditions": {"MET", "UNMET", "UNKNOWN"},
    "authorization": {"ALLOWED", "DENIED", "UNKNOWN"},
    "necessity": {"NECESSARY", "UNNECESSARY", "UNKNOWN"},
    "decision": {"CALLED", "NOT_CALLED", "UNKNOWN"},
    "outcome": {"IMPROVED", "UNCHANGED", "WORSENED", "UNKNOWN"},
}
NECESSITY_BASES = {
    "scoped_work_requirement", "independent_execution_witness", "human_review",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _identity(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} requires a nonempty identity")
    return value


def _time(value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Time must be a numeric point in the episode capture clock")
    if not math.isfinite(value) or value < 0:
        raise ValueError("Time must be finite and nonnegative")
    return value


def _json(raw: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Ambiguous duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f"Non-JSON constant: {value}")

    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                       parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError("Captured JSON must be an object")
    return value


def _strings(values: Any, field: str) -> set[str]:
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{field} must be an explicit source list")
    return {_identity(value, field) for value in values}


def assess_integrity(
    episode_id: str,
    dimensions: Mapping[str, Mapping[str, Any]],
    *,
    required_dimensions: tuple[str, ...] = INTEGRITY_DIMENSIONS,
    fatal_errors: tuple[str, ...] = (),
) -> dict:
    """Evaluate source coverage, never infer semantic event absence.

    Each dimension accepts expected_sources, observed_sources, invalid_sources,
    coverage_closed, and coverage_evidence. A closed source inventory requires
    explicit coverage evidence; a missing optional semantic event is not itself
    a missing source. Corruption invalidates its dimension. Other independent
    dimensions remain usable unless an episode-wide fatal error is supplied.
    """
    _identity(episode_id, "episode_id")
    required = _strings(required_dimensions, "required_dimensions")
    if not required:
        raise ValueError("At least one required integrity dimension is needed")
    fatal = sorted(_strings(fatal_errors, "fatal_errors"))
    result = {}
    for name in sorted(required | set(dimensions)):
        _identity(name, "dimension")
        item = dimensions.get(name, {})
        expected = _strings(item.get("expected_sources", []), "expected_sources")
        observed = _strings(item.get("observed_sources", []), "observed_sources")
        invalid = _strings(item.get("invalid_sources", []), "invalid_sources")
        coverage = sorted(_strings(item.get("coverage_evidence", []), "coverage_evidence"))
        closed = item.get("coverage_closed", False)
        if type(closed) is not bool:
            raise ValueError("coverage_closed must be explicit boolean")
        if closed and not coverage:
            raise ValueError("Closed coverage requires independent inventory/closure evidence")
        missing = expected - observed
        usable = observed - invalid
        if fatal or invalid:
            status = "INVALID"
        elif closed and not missing:
            status = "COMPLETE"
        else:
            status = "PARTIAL"
        reasons = []
        if missing:
            reasons.append("expected_sources_missing")
        if not closed:
            reasons.append("coverage_not_closed")
        if invalid:
            reasons.append("dimension_integrity_broken")
        if fatal:
            reasons.append("episode_integrity_broken")
        result[name] = {
            "status": status, "expected_sources": sorted(expected),
            "observed_sources": sorted(observed), "missing_sources": sorted(missing),
            "invalid_sources": sorted(invalid), "usable_sources": sorted(usable),
            "coverage_closed": closed, "coverage_evidence": coverage,
            "analysis_eligible": status != "INVALID" and (bool(usable) or status == "COMPLETE"),
            "absence_eligible": status == "COMPLETE", "reasons": reasons,
        }
    states = [result[name]["status"] for name in required]
    if fatal or all(state == "INVALID" for state in states):
        status = "INVALID"
    elif all(state == "COMPLETE" for state in states):
        status = "COMPLETE"
    else:
        status = "PARTIAL"
    return {
        "schema": "observer-integrity-v203.2.1", "episode_id": episode_id,
        "status": status, "required_dimensions": sorted(required), "dimensions": result,
        "fatal_errors": fatal,
        "analysis_dimensions": [name for name, item in result.items() if item["analysis_eligible"]],
        "missing_is_not_negative": True,
        "complete_means_source_coverage_not_semantic_truth": True,
    }


@dataclass(frozen=True)
class AcceptedRequest:
    episode_id: str
    actor: str
    request_id: str
    decision_id: str | None
    accepted_at: int | float
    raw_request: bytes
    request_sha256: str
    receipt_bytes: bytes
    mode: str

    def __post_init__(self):
        for name in ("episode_id", "actor", "request_id"):
            _identity(getattr(self, name), name)
        if self.decision_id is not None:
            _identity(self.decision_id, "decision_id")
        _time(self.accepted_at)
        if type(self.raw_request) is not bytes or type(self.receipt_bytes) is not bytes:
            raise ValueError("Transport captures must be immutable bytes")
        if _sha(self.raw_request) != self.request_sha256:
            raise ValueError("Actual request bytes do not match the captured SHA-256")
        wire = _json(self.raw_request)
        if not isinstance(wire.get("messages"), list):
            raise ValueError("Member projection requires the actual request message list")
        if "tools" in wire and not isinstance(wire["tools"], list):
            raise ValueError("Actual request tools must be a list")
        receipt = _json(self.receipt_bytes)
        _identity(receipt.get("id"), "provider response id")
        usage = receipt.get("usage")
        if not isinstance(usage, dict):
            raise ValueError("Prepared requests cannot establish provider acceptance")
        values = [usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")]
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("Acceptance requires the actual nonnegative provider usage")
        if values[0] + values[1] != values[2]:
            raise ValueError("Inconsistent provider usage")
        if self.mode not in {"real_provider", "cpu_scripted"}:
            raise ValueError("The evidence transport mode must be explicit")

    @classmethod
    def from_bytes(
        cls, *, episode_id: str, actor: str, request_id: str, decision_id: str | None,
        accepted_at: int | float, raw_request: bytes, request_sha256: str,
        provider_receipt: Mapping[str, Any], mode: str,
    ) -> AcceptedRequest:
        return cls(episode_id, actor, request_id, decision_id, accepted_at,
                   raw_request, request_sha256, _canonical(provider_receipt), mode)

    @property
    def wire(self) -> dict:
        return _json(self.raw_request)


@dataclass(frozen=True)
class MemberView:
    episode_id: str
    actor: str
    at_time: int | float
    accepted_request: AcceptedRequest | None

    def __post_init__(self):
        _identity(self.episode_id, "episode_id")
        _identity(self.actor, "actor")
        _time(self.at_time)
        request = self.accepted_request
        if request is not None:
            if request.episode_id != self.episode_id or request.actor != self.actor:
                raise PermissionError("Request belongs to another episode/member")
            if request.accepted_at > self.at_time:
                raise ValueError("Future request cannot be used in an earlier member view")

    def to_dict(self) -> dict:
        request = self.accepted_request
        return {
            "schema": "observer-member-view-v203.2.1", "view_scope": "MEMBER",
            "episode_id": self.episode_id, "actor": self.actor, "at_time": self.at_time,
            "visibility": "PRESENTED" if request else "UNKNOWN",
            "request_id": request.request_id if request else None,
            "decision_id": request.decision_id if request else None,
            "accepted_at": request.accepted_at if request else None,
            "request_sha256": request.request_sha256 if request else None,
            "evidence_mode": request.mode if request else None,
            "request": request.wire if request else None,
            "read_understood_or_adopted_not_inferred": True,
        }


@dataclass(frozen=True)
class GlobalView:
    episode_id: str
    at_time: int | float
    event_bytes: tuple[bytes, ...]

    def __post_init__(self):
        _identity(self.episode_id, "episode_id")
        _time(self.at_time)
        if type(self.event_bytes) is not tuple:
            raise ValueError("Global view events must be immutable")
        seen = set()
        for raw in self.event_bytes:
            if type(raw) is not bytes:
                raise ValueError("Global event capture must be bytes")
            event = _json(raw)
            _identity(event.get("event_id"), "event_id")
            if event["event_id"] in seen:
                raise ValueError("Duplicate global event identity")
            seen.add(event["event_id"])
            if event.get("episode_id") != self.episode_id:
                raise ValueError("Global event belongs to a different episode")
            if _time(event.get("occurred_at")) > self.at_time:
                raise ValueError("Future evaluator event is outside this snapshot")

    def to_dict(self) -> dict:
        return {
            "schema": "observer-global-view-v203.2.1", "view_scope": "GLOBAL_EVALUATOR",
            "episode_id": self.episode_id, "at_time": self.at_time,
            "events": [_json(raw) for raw in self.event_bytes], "policy_input_allowed": False,
        }


class ObserverViews:
    def __init__(self, episode_id: str, members: tuple[str, ...] | list[str]):
        self.episode_id = _identity(episode_id, "episode_id")
        self.members = frozenset(_strings(members, "members"))
        if not self.members:
            raise ValueError("Explicit member identities are required")
        self._requests: dict[str, AcceptedRequest] = {}
        self._events: dict[str, bytes] = {}

    def add_request(self, request: AcceptedRequest) -> None:
        if not isinstance(request, AcceptedRequest):
            raise TypeError("Only byte-bound accepted requests can feed member views")
        if request.episode_id != self.episode_id or request.actor not in self.members:
            raise PermissionError("Request attribution is outside the configured episode/members")
        old = self._requests.get(request.request_id)
        if old is not None and old != request:
            raise ValueError("Immutable accepted request identity was reused")
        self._requests[request.request_id] = request

    def add_global_event(self, event: Mapping[str, Any]) -> None:
        raw = _canonical(event)
        GlobalView(self.episode_id, event.get("occurred_at"), (raw,))
        event_id = event["event_id"]
        if event_id in self._events and self._events[event_id] != raw:
            raise ValueError("Immutable global event identity was reused")
        self._events[event_id] = raw

    def member_view(self, actor: str, at_time: int | float,
                    request_id: str | None = None) -> MemberView:
        _time(at_time)
        if actor not in self.members:
            raise PermissionError("Unknown member")
        if request_id is not None:
            if request_id not in self._requests:
                raise ValueError("No accepted request with this identity")
            selected = self._requests[request_id]
        else:
            candidates = [request for request in self._requests.values()
                          if request.actor == actor and request.accepted_at <= at_time]
            selected = max(candidates, key=lambda request: request.accepted_at, default=None)
            if selected and sum(r.accepted_at == selected.accepted_at for r in candidates) > 1:
                raise ValueError("Tied request times require explicit request_id")
        return MemberView(self.episode_id, actor, at_time, selected)

    def global_view(self, at_time: int | float) -> GlobalView:
        _time(at_time)
        events = [raw for raw in self._events.values() if _json(raw)["occurred_at"] <= at_time]
        events.sort(key=lambda raw: (_json(raw)["occurred_at"], _json(raw)["event_id"]))
        return GlobalView(self.episode_id, at_time, tuple(events))


def _pointer(document: Any, pointer: str) -> Any:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("Evidence requires an explicit JSON pointer")
    current = document
    for segment in pointer[1:].split("/"):
        # Reject malformed escapes and Python's permissive negative indices.
        raw = segment.replace("~1", "").replace("~0", "")
        if "~" in raw:
            raise ValueError("Malformed JSON pointer escape")
        key = segment.replace("~1", "/").replace("~0", "~")
        try:
            if isinstance(current, list):
                if not key.isascii() or not key.isdecimal() or str(int(key)) != key:
                    raise ValueError("Evidence array index is not canonical")
                current = current[int(key)]
            elif isinstance(current, dict):
                current = current[key]
            else:
                raise ValueError("Evidence pointer descends through a scalar")
        except (KeyError, IndexError) as exc:
            raise ValueError("Evidence is not present in the selected view") from exc
    return current


def make_evidence(view: MemberView | GlobalView, json_pointer: str,
                  *, event_id: str | None = None) -> dict:
    """Reference exact presented JSON, or a separately typed evaluator event."""
    if isinstance(view, MemberView):
        request = view.accepted_request
        if request is None:
            raise ValueError("No accepted request exists at this member/time")
        if event_id is not None:
            raise PermissionError("Evaluator events cannot feed member evidence")
        if not (json_pointer == "/messages" or json_pointer.startswith("/messages/")
                or json_pointer == "/tools" or json_pointer.startswith("/tools/")):
            raise PermissionError("Member evidence must point into actual messages/tools")
        value = _pointer(request.wire, json_pointer)
        return {
            "view_scope": "MEMBER", "episode_id": view.episode_id, "actor": view.actor,
            "request_id": request.request_id, "decision_id": request.decision_id,
            "request_sha256": request.request_sha256, "accepted_at": request.accepted_at,
            "json_pointer": json_pointer, "value_sha256": _sha(_canonical(value)),
        }
    if isinstance(view, GlobalView):
        for raw in view.event_bytes:
            event = _json(raw)
            if event["event_id"] == event_id:
                value = _pointer(event, json_pointer)
                return {
                    "view_scope": "GLOBAL_EVALUATOR", "episode_id": view.episode_id,
                    "event_id": event_id, "occurred_at": event["occurred_at"],
                    "event_sha256": _sha(raw), "json_pointer": json_pointer,
                    "value_sha256": _sha(_canonical(value)),
                }
        raise ValueError("Global evidence must refer to an event in this snapshot")
    raise TypeError("Evidence requires a typed, bounded view")


def _check_evidence(evidence: Any, view: MemberView | GlobalView | None) -> list[dict]:
    if not isinstance(evidence, list):
        raise ValueError("Evidence references must be a list")
    if evidence and view is None:
        raise ValueError("Evidence validation requires its bounded source view")
    result = []
    for ref in evidence:
        if not isinstance(ref, dict):
            raise ValueError("Evidence must be a byte-bound JSON pointer reference")
        expected = make_evidence(view, ref.get("json_pointer"), event_id=ref.get("event_id"))
        if ref != expected:
            raise ValueError("Evidence attribution, time, bytes, or scope does not match the view")
        result.append(copy.deepcopy(ref))
    return result


def validate_stage_assessment(row: Mapping[str, Any],
                              view: MemberView | GlobalView | None = None) -> dict:
    """Normalize unknowns and validate provenance; never assign scientific truth.

    A revision/time-specific record is returned. Different records for the same
    task do not overwrite each other or become permanent task labels. Unknown
    labels are excluded from negative cases. Operation decision (CALLED) and
    organizational decision (INTERVENE) are separate objects.
    """
    result = copy.deepcopy(dict(row))
    for name in ("episode_id", "task_id"):
        _identity(result.get(name), name)
    _time(result.get("at_time"))
    if type(result.get("task_revision")) is not int or result["task_revision"] < 0:
        raise ValueError("A stage assessment must bind the exact task revision")
    if result.get("phase") not in {f"T{index}" for index in range(7)}:
        raise ValueError("A stage assessment must bind one lifecycle phase T0-T6")
    scope = result.setdefault("view_scope", "MEMBER")
    if scope not in {"MEMBER", "GLOBAL_EVALUATOR"}:
        raise ValueError("Member and global evaluator assessments must remain separate")
    if scope == "MEMBER":
        _identity(result.get("actor"), "actor")
    if view is not None:
        typed_scope = "MEMBER" if isinstance(view, MemberView) else "GLOBAL_EVALUATOR"
        if not isinstance(view, (MemberView, GlobalView)) or scope != typed_scope:
            raise PermissionError("Assessment cannot cross the evaluator/member boundary")
        if result["episode_id"] != view.episode_id or result["at_time"] != view.at_time:
            raise ValueError("Assessment time/episode must exactly match its bounded view")
        if isinstance(view, MemberView):
            if result["actor"] != view.actor:
                raise PermissionError("Assessment actor does not match the member view")
            accepted = view.accepted_request
            request_id = accepted.request_id if accepted else None
            if result.get("request_id") != request_id:
                raise ValueError("Assessment must bind the actual decision request")
            bindings = {
                "decision_id": accepted.decision_id if accepted else None,
                "request_sha256": accepted.request_sha256 if accepted else None,
                "request_accepted_at": accepted.accepted_at if accepted else None,
                "evidence_mode": accepted.mode if accepted else None,
            }
            for name, value in bindings.items():
                if name in result and result[name] != value:
                    raise ValueError(f"Assessment {name} differs from the accepted request")
                result[name] = value
    for label in ("dependency", "misalignment"):
        value = result.setdefault(label, "UNKNOWN")
        if value not in {"PRESENT", "ABSENT", "UNKNOWN"}:
            raise ValueError("Dependency and misalignment need independent scientific labels")
        evidence = _check_evidence(result.get(label + "_evidence", []), view)
        if value != "UNKNOWN" and not evidence:
            raise ValueError("Substantive scientific labels need scoped evidence")
        result[label + "_evidence"] = evidence
    decision = result.setdefault("decision", "ABSTAIN")
    if decision not in {"NO_CHANGE", "ABSTAIN", "INTERVENE"}:
        raise ValueError("NO_CHANGE and ABSTAIN must remain separate")
    decision_evidence = _check_evidence(result.get("decision_evidence", []), view)
    if decision != "ABSTAIN" and not decision_evidence:
        raise ValueError("A substantive organizational decision requires source evidence")
    if decision == "NO_CHANGE" and result["misalignment"] != "ABSENT":
        raise ValueError("Unknown misalignment cannot be converted into NO_CHANGE")
    if decision == "INTERVENE" and result["misalignment"] != "PRESENT":
        raise ValueError("Dependency alone does not justify intervention")
    result["decision_evidence"] = decision_evidence
    layers = result.get("layers", {})
    if not isinstance(layers, dict) or set(layers) - set(LAYER_VALUES):
        raise ValueError("Only the six explicit operation assessment layers are supported")
    normalized_layers = {}
    for name, values in LAYER_VALUES.items():
        layer = copy.deepcopy(layers.get(name, {}))
        if not isinstance(layer, dict):
            raise ValueError("Each operation layer needs its own status and evidence")
        value = layer.setdefault("value", "UNKNOWN")
        if value not in values:
            raise ValueError(f"Invalid {name} assessment")
        evidence = _check_evidence(layer.get("evidence", []), view)
        if value != "UNKNOWN" and not evidence:
            raise ValueError(f"Non-unknown {name} needs independent source evidence")
        if name == "necessity" and value != "UNKNOWN" and layer.get("basis") not in NECESSITY_BASES:
            raise ValueError("Necessity needs a scoped requirement/witness, never call counts")
        layer["evidence"] = evidence
        normalized_layers[name] = layer
    if any(layer["value"] != "UNKNOWN" for layer in normalized_layers.values()):
        _identity(result.get("operation"), "operation")
    result["layers"] = normalized_layers
    result.update({
        "schema": "observer-stage-assessment-v203.2.1", "schema_valid": True,
        "semantic_truth_not_verified": True, "is_permanent_task_label": False,
        "source_view_validated": view is not None,
        "unknowns_must_not_be_counted_as_negatives": True, "world_actions": 0,
    })
    return result
