"""Immutable, branch-scoped causal records for the v230 offline and SDK runners."""

from contextlib import closing
from pathlib import Path
import sqlite3
import time

from .storage import digest, json_bytes
from .software_context_builder_v230 import compact, identity


class Trajectory:
    def __init__(self, path, episode, branch):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.episode, self.branch = episode, branch
        self.errors = []
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("create table if not exists events(id text primary key, body text not null)")
            db.commit()

    def key(self, kind, native_id):
        return identity([self.episode, self.branch, kind, native_id])

    def event(
        self,
        kind,
        native_id,
        *,
        layer,
        parent=None,
        agent=None,
        request=None,
        tool=None,
        opportunity=None,
        graph=None,
        anomaly=None,
        work=None,
        timestamp=None,
        result=None,
        ref=None,
        details=None,
    ):
        eid = self.key(kind, native_id)
        row = dict(
            episode_id=self.episode,
            branch_id=self.branch,
            kind=kind,
            native_id=native_id,
            event_id=eid,
            parent_event_id=parent,
            layer=layer,
            agent_id=agent,
            request_id=request,
            tool_call_id=tool,
            dispatch_opportunity_id=opportunity,
            org_graph_version=graph,
            anomaly_id=anomaly,
            work_package_id=work,
            timestamp=timestamp,
            result=result,
            payload_ref=ref,
            details=details,
        )
        body = compact(row)
        with closing(sqlite3.connect(self.path)) as db, db:
            old = db.execute("select body from events where id=?", (eid,)).fetchone()
            if old and old[0] != body:
                raise ValueError(f"Conflicting immutable {kind} record")
            db.execute("insert or ignore into events values (?, ?)", (eid, body))
        return eid

    def observe(self, *args, **kwargs):
        """After a side effect, preserve the actual result even if observation fails."""
        try:
            return self.event(*args, **kwargs)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.fault(exc)
            return None

    def fault(self, exc):
        from .storage import atomic_write

        self.errors.append(str(exc))
        try:
            atomic_write(
                self.path.with_suffix(".incomplete.json"), json_bytes({"errors": self.errors})
            )
        except OSError:
            pass  # Keep the in-memory flag available if storage itself is unavailable.


class ProjectedEndpoint:
    """Wrap the native member-bound post callback before counting and dispatch."""

    def __init__(self, backend, folder, trajectory, condition, *, controller=False):
        from threading import Lock

        self.backend, self.folder, self.trace = backend, Path(folder), trajectory
        self.condition, self.controller = condition, controller
        self.lock = Lock()
        self.state = lambda: {}
        self.measurements = {}

    def post(self, route, payload):
        from .software_context_builder_v230 import build
        from .storage import atomic_write

        if route not in ("/chat/completions", "/tokenize", "/tokenize-prefix"):
            raise ValueError("Unsupported model route")
        actor, original = payload["member_id"], payload["wire"]
        if payload["team_slot_id"] != self.trace.branch:
            raise ValueError("Invalid branch binding")
        role = "osa" if self.controller else "worker" if original.get("tools") else "condenser"
        shown, manifest = build(
            original, actor=actor, role=role, condition=self.condition, scope=self.trace.branch
        )
        if route != "/chat/completions":
            counted = self.backend(route, {**payload, "wire": shown})
            if counted["request_sha256"] != digest(json_bytes(shown)):
                raise ValueError("Count bound to wrong projected wire")
            if route == "/tokenize":
                self.measurements[actor] = (manifest["shown_wire"], counted["prompt_tokens"])
            return {
                **counted,
                "projected_request_sha256": counted["request_sha256"],
                "request_sha256": digest(json_bytes(original)),
            }
        rid = payload["request_id"]
        attempt = self.folder / identity([self.trace.branch, actor, rid])
        # mkdir is an atomic and durable single-use claim, including after a lost reply.
        with self.lock:
            attempt.mkdir(parents=True, exist_ok=False)
            measured = self.measurements.get(actor)
            if not measured or measured[0] != manifest["shown_wire"]:
                counted = self.backend("/tokenize", {**payload, "wire": shown})
                if counted["request_sha256"] != digest(json_bytes(shown)):
                    raise ValueError("Projected count mismatch at dispatch")
                measured = (manifest["shown_wire"], counted["prompt_tokens"])
            state = self.state()
            manifest.update(
                episode_id=self.trace.episode,
                request_id=rid,
                org_graph_version=state.get("graph"),
                anomaly_id=state.get("anomaly"),
                dispatch_opportunity_id=state.get("opportunity"),
                estimated_input_tokens=measured[1],
                reserved_output_tokens=shown.get("max_tokens"),
            )
            for name, obj in [("original", original), ("manifest", manifest), ("shown", shown)]:
                atomic_write(attempt / (name + ".json"), json_bytes(obj))
            parent = self.trace.event(
                "dispatch",
                rid,
                layer=2,
                request=rid,
                agent=actor,
                parent=state.get("parent"),
                graph=state.get("graph"),
                anomaly=state.get("anomaly"),
                opportunity=state.get("opportunity"),
                ref=str(attempt / "manifest.json"),
                timestamp=time.time(),
                result="prepared",
            )
            response = self.backend(route, {**payload, "wire": shown})
            self.trace.observe(
                "response",
                response["id"],
                layer=5,
                parent=parent,
                request=rid,
                agent=actor,
                timestamp=time.time(),
                result="returned",
                details=response.get("usage"),
            )
            return response
