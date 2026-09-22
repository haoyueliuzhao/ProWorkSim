"""Single-writer transaction runner shared by independently bound worlds.

Domain adapters supply identities, command frames, effects and event policies.
This runner owns only locking, atomic journal commits and bounded recovery.
"""

import copy
import shutil
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from . import journal
from .transitions import execute_transition, ordered_due_events, ActionFrame, changed_paths
from .projections import projection_paths, WORK_CACHE_FIELDS, CONDITION_CACHE_FIELDS
from .visibility import project_fields
from ..schema import InteractionRecord, WorldSnapshot
from ..storage import Store, atomic_write, digest, json_bytes, read_json


class WorldError(ValueError):
    pass


class WorldRunner:
    runtime_schema = "0.5"

    def _operation_identity(self, actor, action, arguments, request_key):
        """Return the trusted command identity and canonical payload digest."""
        command_id = f"command:{actor}:{request_key if request_key is not None else uuid.uuid4().hex}"
        payload_digest = journal.canonical_digest({"action": action, "arguments": arguments})
        return command_id, payload_digest

    def _after_command(self, record):
        """Adapter hook for deterministic scheduling before the command commit."""

    def __init__(self, root):
        self.store = Store(root)
        with self.store.lock():
            self.state = self.store.load()
            if self.state["schema_version"] != self.runtime_schema:
                raise WorldError(
                    "Runtime requires the current schema; use the historical frozen runtime or an explicit trusted-checkpoint import for older worlds"
                )
            self.store.recover(self.state)
        self._reads = []
        self._writes = []
        self.fault_hook = None
        self._operation_context = {}
        self.store.fault_hook = self._storage_fault

    def _fault(self, phase, details=None):
        if self.fault_hook is not None:
            self.fault_hook(phase, {**self._operation_context, **(details or {})})

    def _storage_fault(self, phase, details):
        self._fault(phase, details)

    def _complete_frame(self, frame):
        projected = (
            projection_paths(self.state)
            + tuple(("work_items", "*", field) for field in WORK_CACHE_FIELDS)
            + tuple(("condition_specs", "*", field) for field in CONDITION_CACHE_FIELDS)
        )
        return ActionFrame(
            frame.name,
            frame.paths,
            frame.derived_paths + projected,
            frame.immutable_submission_extensions,
            frame.append_only_extensions,
        )

    def _preflight(self):
        previous = copy.deepcopy(self.state)
        self._derive(self.state)
        return [list(path) for path in changed_paths(previous, self.state)]

    def act(self, actor, action, arguments=None, request_key=None):
        started = time.monotonic()
        arguments = {} if arguments is None else arguments
        with self.store.lock():
            self.state = self.store.load()
            self._role(actor)
            self.store.recover(self.state)
            preflight_delta = self._preflight()
            try:
                command_id, request_digest = self._operation_identity(
                    actor, action, arguments, request_key
                )
            except (ValueError, TypeError):
                return {
                    "ok": False,
                    "error": {
                        "type": "InvalidInput",
                        "message": "Command identity requires a finite JSON payload",
                    },
                    "command_committed": False,
                }
            if request_key is not None and (not isinstance(request_key, str) or not request_key):
                return {
                    "ok": False,
                    "error": {
                        "type": "InvalidCommandIdentity",
                        "message": "request_key must be a nonempty string",
                    },
                    "command_committed": False,
                }
            self._operation_context = {
                "operation_id": command_id,
                "kind": "command",
                "action": action,
                "actor": actor,
            }
            try:
                old = journal.lookup_operation(self.state, command_id, actor, request_digest)
            except journal.CommandConflict as exc:
                return {
                    "ok": False,
                    "error": {"type": "CommandConflict", "message": str(exc)},
                    "command_id": command_id,
                    "command_committed": False,
                }
            if old is not None:
                event_errors = self._drain_events()
                result = copy.deepcopy(old["public_result"])
                return self._attach_event_errors(result, event_errors)
            before = copy.deepcopy(self.state)
            self._reads, self._writes = [], []
            try:
                if not isinstance(arguments, dict):
                    raise WorldError("Tool arguments must be an object")
                json_bytes(arguments)
                handler = (
                    getattr(self, f"_tool_{action}", None) if isinstance(action, str) else None
                )
                if handler is None:
                    raise WorldError("Unknown tool")
                result, transition = execute_transition(
                    self.state,
                    self._complete_frame(self._action_frame(actor, action, arguments)),
                    lambda: handler(actor, **arguments),
                    self._derive,
                    after_apply=lambda: self._fault("after_apply"),
                )
                output = {"ok": True, "result": project_fields(result, {"acceptance_spec_ref"})}
                json_bytes(output)
            except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError) as exc:
                self.state = before
                self.store.recover(self.state)
                self._reads, self._writes = [], []
                transition = getattr(
                    exc,
                    "transition_receipt",
                    {
                        "receipt_version": "phase-deltas-v0.5",
                        "contract": action,
                        "rolled_back": True,
                        "failed_phase": "validation_before_apply",
                        "apply_delta": None,
                        "derive_delta": None,
                        "net_delta": [],
                        "primary_region_changes": [],
                        "projection_region_changes": [],
                    },
                )
                output = {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
            transition["preflight_projection_delta"] = preflight_delta
            self.state["clock"] += 1
            record = asdict(
                InteractionRecord(
                    action_id=f"action-{len(self.state['interactions']) + 1}",
                    actor_id=actor,
                    action=action,
                    inputs=arguments,
                    output=copy.deepcopy(output),
                    logical_time=self.state["clock"],
                    reads=self._reads,
                    writes=self._writes,
                    wall_seconds=time.monotonic() - started,
                )
            )
            record.update(request_key=request_key, transition_id=command_id, transition=transition)
            self.state["interactions"].append(record)
            self._after_command(record)
            public_result = {
                **output,
                "action_id": record["action_id"],
                "logical_time": self.state["clock"],
                "command_id": command_id,
                "command_committed": True,
                "committed_revision": self.state.get("state_revision", 0) + 1,
            }
            journal.record_operation(
                self.state, command_id, actor, request_digest, public_result, transition, "command"
            )
            self.store.save(self.state)
            self._fault("after_command_commit")
            event_errors = self._drain_events()
            return self._attach_event_errors(public_result, event_errors)

    @staticmethod
    def _attach_event_errors(result, errors):
        pending = [error for error in errors if not error["event_committed"]]
        delivery = [error for error in errors if error["event_committed"]]
        if pending:
            result["pending_event_errors"] = pending
        if delivery:
            result["event_delivery_errors"] = delivery
        return result

    def _drain_events(self):
        errors = []
        for event in ordered_due_events(self.state["events"], self.state["clock"]):
            if event not in self.state["events"]:
                continue
            before = copy.deepcopy(self.state)
            committed = False
            try:
                operation_id = "event:" + event["event_id"]
                digest_value = journal.canonical_digest(
                    {k: event[k] for k in ("event_id", "kind", "at", "payload")}
                )
                actor = self._event_actor(event)
                self._operation_context = {
                    "operation_id": operation_id,
                    "kind": "event",
                    "action": event["kind"],
                    "actor": actor,
                }
                previous = journal.lookup_operation(self.state, operation_id, actor, digest_value)
                if previous is not None:
                    self.state["events"].remove(event)
                    self.store.save(self.state)  # queue acknowledgement only, no second effect
                    continue
                frame = self._complete_frame(self._event_frame(event))
                result, receipt = execute_transition(
                    self.state, frame, lambda: self._apply_event(event), self._derive
                )
                self._fault("before_event_commit")
                self.state["events"].remove(event)
                history = {
                    **event,
                    "outcome": result["outcome"],
                    "transition_id": operation_id,
                    "transition": receipt,
                }
                self.state["event_history"].append(history)
                journal.record_operation(
                    self.state, operation_id, actor, digest_value, result, receipt, "event"
                )
                self.store.save(self.state)
                committed = True
                self._fault("after_event_commit")
            except Exception as exc:
                # Once the snapshot is committed, only delivery/acknowledgement
                # failed. Never recover files using the older in-memory prefix.
                self.state = self.store.load() if committed else before
                self.store.recover(self.state)
                errors.append(
                    {
                        "event_id": event.get("event_id"),
                        "event_committed": committed,
                        "stage": "post_commit_delivery" if committed else "pre_commit",
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                    }
                )
                attempt = {
                    **errors[-1],
                    "transition_id": "event:" + event.get("event_id", "missing"),
                    "bound_actor": self._operation_context.get("actor"),
                    "request_digest": locals().get("digest_value"),
                    "pre_state_revision": before.get("state_revision", 0),
                    "committed_prefix_revision": self.state.get("state_revision", 0),
                    "semantics_version": self.state.get("semantics_version", journal.SEMANTICS_VERSION),
                    "receipt": getattr(exc, "transition_receipt", None),
                }
                self.state.setdefault("event_attempts", []).append(attempt)
                self.store.save(self.state)  # Diagnostic Q/O record, no new formal effect.
                break  # Preserve ordered pending suffix for a later explicit retry.
        return errors

    def recover(self):
        """Resume due events from a committed checkpoint; never rerun worker policy."""
        with self.store.lock():
            self.state = self.store.load()
            self.store.recover(self.state)
            self._preflight()
            errors = self._drain_events()
            return {
                "state_revision": self.state.get("state_revision", 0),
                "pending_event_errors": [error for error in errors if not error["event_committed"]],
                "event_delivery_errors": [error for error in errors if error["event_committed"]],
                "pending_events": len(self.state["events"]),
            }

    def snapshot(self, destination):
        destination = Path(destination).resolve()
        if destination == self.store.root or self.store.root in destination.parents:
            raise WorldError("Snapshot must be outside the live world")
        with self.store.lock():
            if destination.exists():
                raise WorldError("Snapshot destination already exists")
            state = self.store.load()
            shutil.copytree(
                self.store.root, destination, ignore=shutil.ignore_patterns("world.lock")
            )
            metadata = WorldSnapshot(
                state["schema_version"],
                state["instance_id"],
                state["branch_id"],
                state["clock"],
                digest(json_bytes(state)),
            )
            atomic_write(destination / "snapshot.json", json_bytes(asdict(metadata)))
        return destination

    @classmethod
    def restore(cls, snapshot, destination, branch=True):
        snapshot, destination = Path(snapshot).resolve(), Path(destination).resolve()
        metadata = read_json(snapshot / "snapshot.json")
        state = read_json(snapshot / "control" / "state.json")
        if digest(json_bytes(state)) != metadata["state_sha256"]:
            raise WorldError("Snapshot checksum mismatch")
        if destination.exists() or snapshot == destination or snapshot in destination.parents:
            raise WorldError("Restore requires a new destination outside the snapshot")
        shutil.copytree(
            snapshot, destination, ignore=shutil.ignore_patterns("world.lock", "snapshot.json")
        )
        if branch:
            state["parent_branch_id"] = state["branch_id"]
            state["branch_id"] = uuid.uuid4().hex
            state["branch_start_action"] = len(state["interactions"])
            Store(destination).save(state)
        return cls(destination)
