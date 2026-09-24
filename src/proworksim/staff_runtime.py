"""One action opportunity at a time for independently configured worker policies.

The runtime knows no reconciliation, report, issue, source-matching or repair
algorithm. It supplies actual public interfaces, preserves private policy memory,
executes decisions, and records refusals. Business planning belongs to policies.
"""

import copy
import uuid

from .experience import ExperienceRecorder
from .storage import digest, json_bytes
from .tool_outcomes import classify_tool_result, port_exception

RUNTIME_VERSION = "staff-runtime-v0.11"


class PolicyBoundaryError(Exception):
    """Declared adapter failure; ordinary policy exceptions remain policy_error."""

    STATUSES = frozenset({"model_service_error", "model_format_error", "model_budget_exhausted"})

    def __init__(self, status, reason, *, memory, events=None, details=None):
        if status not in self.STATUSES or not isinstance(memory, dict):
            raise ValueError("Invalid declared policy boundary failure")
        super().__init__(reason)
        self.status, self.memory = status, copy.deepcopy(memory)
        self.events, self.details = copy.deepcopy(events or []), copy.deepcopy(details or {})


def _nonnegative(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(label + " must be a nonnegative integer")


def _policy_identity(policy):
    return {
        "implementation": type(policy).__module__ + "." + type(policy).__qualname__,
        "config": copy.deepcopy(getattr(policy, "config", {})),
    }


class StaffRuntime:
    def __init__(self, ports, policies, checkpoint=None, run_id=None, recorder=None):
        if (
            not isinstance(ports, dict)
            or not ports
            or not isinstance(policies, dict)
            or set(ports) != set(policies)
            or any(not isinstance(label, str) or not label for label in ports)
        ):
            raise ValueError("Runtime needs the same nonempty labeled ports and policies")
        self.ports, self.policies = dict(ports), dict(policies)
        self.labels = list(ports)
        identities = {label: _policy_identity(policy) for label, policy in policies.items()}
        json_bytes(identities)
        saved = copy.deepcopy(checkpoint) if checkpoint is not None else None
        if saved is not None:
            if (
                saved.get("version") != RUNTIME_VERSION
                or saved.get("labels") != self.labels
                or saved.get("policy_identities") != identities
            ):
                raise ValueError(
                    "Checkpoint runtime, labels/order and policy configuration must match"
                )
            for name in ("actions", "opportunities", "cursor"):
                _nonnegative(saved.get(name), name)
            if set(saved.get("roles", {})) != set(self.labels):
                raise ValueError("Checkpoint role memories do not match bindings")
            json_bytes(saved)
        self.run_id = saved["run_id"] if saved else (run_id or uuid.uuid4().hex)
        self.actions = saved["actions"] if saved else 0
        self.opportunities = saved["opportunities"] if saved else 0
        self.cursor = saved["cursor"] if saved else 0
        self.policy_identities = identities
        self.roles = (
            saved["roles"]
            if saved
            else {
                label: {
                    "memory": {},
                    "last_action": None,
                    "last_result": None,
                    "status": "ready",
                    "actions": 0,
                    "opportunities": 0,
                    "identity": None,
                }
                for label in self.labels
            }
        )
        previous_events = saved["experience"]["events"] if saved else None
        if (
            recorder is not None
            and previous_events is not None
            and recorder.events != previous_events
        ):
            raise ValueError("Resume recorder must preserve the checkpoint experience exactly")
        self.recorder = recorder or ExperienceRecorder(previous_events)
        self._in_step = False

    def snapshot(self):
        if self._in_step:
            raise ValueError("Checkpoint is only supported after a complete opportunity returns")
        return copy.deepcopy(
            {
                "version": RUNTIME_VERSION,
                "run_id": self.run_id,
                "labels": self.labels,
                "policy_identities": self.policy_identities,
                "actions": self.actions,
                "opportunities": self.opportunities,
                "cursor": self.cursor,
                "roles": self.roles,
                "experience": self.recorder.snapshot(),
            }
        )

    def _finish(self, label, status, reason, **details):
        self.roles[label].update(status=status, reason=reason)
        if status == "binding_mismatch":
            self.recorder.record(
                "binding_error",
                {"status": status, "reason": reason, "policy_invoked": False},
                worker_id=label,
            )
        return {
            "worker_id": label,
            "status": status,
            "reason": reason,
            "action_performed": False,
            **details,
        }

    def _read_port(self, label, operation):
        value = getattr(self.ports[label], operation)()
        kind = "public_tools" if operation == "tools" else "public_observation"
        self.recorder.record(kind, value, worker_id=label)
        return value

    def step(self):
        """Grant one role an opportunity; execute at most one real tool call."""
        if self._in_step:
            raise ValueError("Runtime is single writer and cannot be entered recursively")
        self._in_step = True
        try:
            return self._step()
        finally:
            self._in_step = False

    def _step(self):
        label = self.labels[self.cursor % len(self.labels)]
        self.cursor += 1
        self.opportunities += 1
        role = self.roles[label]
        role["opportunities"] += 1
        try:
            definitions = self._read_port(label, "tools")
            observation = self._read_port(label, "observe")
        except Exception as exc:
            failure = port_exception(exc, operation="observation", context={"worker_id": label})
            self.recorder.record("interface_error", failure, worker_id=label)
            return self._finish(
                label, "environment_error", "Public interface raised", error=failure
            )
        identity = {
            "world_id": observation.get("world_id"),
            "instance_id": observation.get("instance_id"),
            "branch_id": observation.get("branch_id"),
            "actor_id": observation.get("actor_id"),
            "project_ids": sorted(observation.get("projects", {})),
        }
        if any(
            not isinstance(identity[key], str) or not identity[key]
            for key in ("world_id", "instance_id", "branch_id", "actor_id")
        ):
            return self._finish(
                label, "binding_mismatch", "Public port lacks a complete world identity"
            )
        if role["identity"] is not None and role["identity"] != identity:
            return self._finish(
                label, "binding_mismatch", "Public identity differs from saved role context"
            )
        role["identity"] = identity
        opportunity_id = f"staff-opportunity-{self.run_id}-{self.opportunities}"
        context = {
            "worker_id": label,
            "run_id": self.run_id,
            "opportunity_id": opportunity_id,
            "opportunity_index": self.opportunities,
            "tools": copy.deepcopy(definitions),
            "observation": copy.deepcopy(observation),
            "memory": copy.deepcopy(role["memory"]),
            "last_action": copy.deepcopy(role["last_action"]),
            "last_result": copy.deepcopy(role["last_result"]),
        }
        event_hook = getattr(self.policies[label], "bind_event_sink", None)
        try:
            if event_hook is not None:
                event_hook(
                    lambda kind, payload: self.recorder.record(
                        kind,
                        {**copy.deepcopy(payload), "opportunity_id": opportunity_id},
                        worker_id=label,
                    )
                )
            decision = self.policies[label].decide(context)
            json_bytes(decision)
            if (
                not isinstance(decision, dict)
                or decision.get("kind") not in {"act", "wait", "done"}
                or not isinstance(decision.get("memory"), dict)
            ):
                raise ValueError("Policy must return a declared decision with its own JSON memory")
            if decision["kind"] == "act" and (
                not isinstance(decision.get("action"), str)
                or not decision["action"]
                or not isinstance(decision.get("arguments"), dict)
                or bool(set(decision["arguments"]) & {"request_key", "action"})
            ):
                raise ValueError("Action decision requires a tool name and argument object")
        except PolicyBoundaryError as exc:
            json_bytes(exc.memory)
            role["memory"] = copy.deepcopy(exc.memory)
            for event in exc.events:
                self.recorder.record(event["kind"], event["payload"], worker_id=label)
            error = {
                "type": type(exc).__name__,
                "message": str(exc),
                "status": exc.status,
                "opportunity_id": opportunity_id,
                **exc.details,
            }
            self.recorder.record("model_boundary_error", error, worker_id=label)
            return self._finish(label, exc.status, str(exc), error=error)
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
            self.recorder.record("policy_error", error, worker_id=label)
            return self._finish(label, "policy_error", "Policy decision failed", error=error)
        finally:
            if event_hook is not None:
                event_hook(None)
        public_decision = {
            key: copy.deepcopy(value) for key, value in decision.items() if key != "memory"
        }
        self.recorder.record(
            "policy_decision",
            {
                "decision": public_decision,
                "memory_before_sha256": digest(json_bytes(role["memory"])),
                "memory_after_sha256": digest(json_bytes(decision["memory"])),
            },
            worker_id=label,
        )
        role["memory"] = copy.deepcopy(decision["memory"])
        if decision["kind"] != "act":
            status = "completed" if decision["kind"] == "done" else "worker_waiting"
            if status == "worker_waiting" and any(
                item.get("owner_role") == observation.get("actor_id")
                and item.get("status") == "blocked"
                for item in observation.get("work_items", {}).values()
            ):
                status = "world_blocked"
            return self._finish(
                label, status, decision.get("reason", decision["kind"]), decision=public_decision
            )
        self.actions += 1
        role["actions"] += 1
        key = f"staff-{self.run_id}-{self.actions}"
        action = {"action": decision["action"], "arguments": copy.deepcopy(decision["arguments"])}
        payload = {**action, "request_key": key}
        if decision.get("model_call_id"):
            payload["opportunity_id"] = opportunity_id
        for name in ("model_call_id", "model_tool_call_id", "decision_id"):
            if name in decision:
                payload[name] = copy.deepcopy(decision[name])
        try:
            response = self.ports[label].call(
                action["action"], request_key=key, **action["arguments"]
            )
            payload["response"] = copy.deepcopy(response)
        except Exception as exc:
            payload["exception"] = {"type": type(exc).__name__, "message": str(exc)}
            response = port_exception(exc, operation="call", context={"worker_id": label})
        self.recorder.record("tool_call", payload, worker_id=label)
        if decision.get("model_call_id"):
            self.recorder.record(
                "model_action_link",
                {
                    "model_call_id": decision["model_call_id"],
                    "model_tool_call_id": decision.get("model_tool_call_id"),
                    "opportunity_id": opportunity_id,
                    "request_key": key,
                    "world_action_id": response.get("action_id")
                    if isinstance(response, dict)
                    else None,
                    "world_command_id": response.get("command_id")
                    if isinstance(response, dict)
                    else None,
                    "world_response": copy.deepcopy(response),
                },
                worker_id=label,
            )
        role["last_action"], role["last_result"] = action, copy.deepcopy(response)
        if not isinstance(response, dict) or type(response.get("ok")) is not bool:
            result = self._finish(
                label, "environment_error", "Public tool returned no explicit result"
            )
        elif response["ok"]:
            result = self._finish(label, "running", "Actual policy action returned successfully")
        else:
            failure = classify_tool_result(response)
            result = self._finish(
                label, failure["status"], "Actual tool refusal preserved", rejection=failure
            )
        return {
            **result,
            "action_performed": True,
            "response": copy.deepcopy(response),
            "decision": public_decision,
        }

    def run(self, max_actions=100, max_opportunities=300):
        _nonnegative(max_actions, "Action budget")
        _nonnegative(max_opportunities, "Opportunity budget")
        start_actions, start_opportunities = self.actions, self.opportunities
        idle, outcomes = set(), []
        status = "budget_exhausted"
        while (
            self.actions - start_actions < max_actions
            and self.opportunities - start_opportunities < max_opportunities
        ):
            outcome = self.step()
            outcomes.append(outcome)
            label = outcome["worker_id"]
            if outcome["action_performed"]:
                idle.clear()
            else:
                idle.add(label)
            if len(idle) == len(self.labels):
                states = {self.roles[key]["status"] for key in self.labels}
                if states == {"completed"}:
                    status = "completed"
                elif "environment_error" in states:
                    status = "environment_error"
                elif "binding_mismatch" in states:
                    status = "binding_mismatch"
                elif states & PolicyBoundaryError.STATUSES:
                    status = next(
                        name
                        for name in (
                            "model_service_error",
                            "model_format_error",
                            "model_budget_exhausted",
                        )
                        if name in states
                    )
                elif "policy_error" in states:
                    status = "policy_error"
                elif "world_blocked" in states:
                    status = "world_blocked"
                else:
                    status = "worker_waiting"
                break
        boundary = {
            "run_id": self.run_id,
            "status": status,
            "actions": self.actions - start_actions,
            "opportunities": self.opportunities - start_opportunities,
        }
        self.recorder.record("run_boundary", boundary)
        return {
            **boundary,
            "total_actions": self.actions,
            "total_opportunities": self.opportunities,
            "roles": copy.deepcopy(self.roles),
            "outcomes": outcomes,
            "experience": self.recorder.snapshot(),
        }
