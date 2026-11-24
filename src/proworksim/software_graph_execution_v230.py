"""CPU- and SDK-shared execution path for a branch using v230 context and graph control."""

from collections import OrderedDict
from copy import deepcopy

from .software_graph_controller_v228 import ControlledWorld, activate, menu
from .software_benchmark_world_v054 import _reference, _text_page
from .software_context_builder_v230 import compact, identity
from .storage import atomic_write, json_bytes
from .software_trajectory_v230 import ProjectedEndpoint, Trajectory


class World(ControlledWorld):
    def _action_read_file(
        self, actor, project_id, path, start_line=1, max_lines=180, patch_id=None, cursor=None
    ):
        artifact, version, bundle = self._bundle(actor, patch_id=patch_id)
        text = self._text_entry(bundle, path)
        if not 1 <= max_lines <= 180 or start_line < 1:
            raise ValueError("Use positive line positions and at most180 lines")
        reference = _reference(artifact, version)
        source = {"tool": "read_file", "path": path, "source_reference": reference}
        key = (
            actor,
            project_id,
            identity(source),
            artifact["versions"][version]["sha256"],
            start_line,
            max_lines,
            cursor,
        )
        if not hasattr(self, "_read_pages"):
            self._read_pages = OrderedDict()
            self.read_page_hits = 0
        page = self._read_pages.get(key)
        if page is None:
            position = (
                None if cursor else sum(map(len, text.splitlines(keepends=True)[: start_line - 1]))
            )
            page = _text_page(text, source, cursor, position=position, max_lines=max_lines)
            self._read_pages[key] = page
            if len(self._read_pages) > 64:
                self._read_pages.popitem(last=False)
        else:
            self.read_page_hits += 1
            self._read_pages.move_to_end(key)
        self._event(
            actor,
            "read",
            source_reference=reference,
            path=path,
            start_character=page["start_character"],
            end_character=page["end_character"],
        )
        return {"source_reference": reference, "path": path, **deepcopy(page)}


# Covers any allowed prompt plus the maximum output of a single native dispatch.
CALL_BOUND = 98_304 + 32_768


class Execution:
    def __init__(self, backend, folder, episode, branch, condition, *, controller_backend=None):
        self.trace = Trajectory(folder / "events.sqlite", episode, branch)
        self.worker = ProjectedEndpoint(backend, folder / "worker", self.trace, condition)
        self.osa = (
            ProjectedEndpoint(
                controller_backend, folder / "osa", self.trace, condition, controller=True
            )
            if controller_backend
            else None
        )
        self.runtime = None
        self.grants = []
        self.selected_phase = None
        self.folder = folder
        self.current = {}
        self.worker.state = lambda: dict(self.current)

    def bind_recorder(self, runtime):
        native_record = runtime.recorder.record

        def record(kind, payload, worker_id=None):
            result = native_record(kind, payload, worker_id=worker_id)
            try:
                index = len(runtime.recorder.events) - 1
                meta = payload if isinstance(payload, dict) else {}
                op = meta.get("opportunity_id")
                if kind == "organization_work_opportunity_v049" and meta["phase"] == "before":
                    self.current.update(opportunity=op, parent=self.trace.key("native", index))
                selected = {
                    "organization_work_opportunity_v049": 2,
                    "model_call": 2,
                    "model_response": 2,
                    "tool_call": 3,
                    "model_action_link": 4,
                    "run_boundary": 5,
                    "model_boundary_error": 2,
                }
                if kind in selected:
                    raw = self.folder / "native" / f"{index}.json"
                    atomic_write(
                        raw, json_bytes({"kind": kind, "worker_id": worker_id, "payload": payload})
                    )
                    parent = self.current.get("parent")
                    if self.trace.key("native", index) == parent:
                        parent = (
                            self.trace.key("activation", self.version)
                            if hasattr(self, "version")
                            else None
                        )
                    self.trace.observe(
                        "native",
                        index,
                        layer=selected[kind],
                        parent=parent,
                        agent=worker_id,
                        opportunity=op,
                        graph=self.current.get("graph"),
                        anomaly=self.current.get("anomaly"),
                        request=meta.get("call_id", meta.get("model_call_id")),
                        tool=meta.get("model_tool_call_id"),
                        ref=str(raw),
                        result=meta.get("outcome_status", (meta.get("response") or {}).get("ok")),
                        details={"kind": kind},
                    )
            except (OSError, KeyError, TypeError, ValueError) as exc:
                self.trace.fault(exc)
            return result

        runtime.recorder.record = record

    def attach(self, runtime):
        world = runtime.prepared.world
        if self.runtime is not None or not isinstance(world, ControlledWorld):
            raise ValueError("Attach to one branch after checkpoint restore and budget setup")
        if not hasattr(runtime.team_budget, "native_allocation"):
            raise ValueError("Set the native allocation including controller cost first")
        if world.protocol().get("graph_control", {}).get("versions"):
            raise ValueError("Attach at the predecision checkpoint")
        world.__class__ = World
        self.runtime = runtime
        self.native_limit = runtime.team_budget.native_allocation
        self.normal_select = runtime.select_next
        runtime.select_next = self.select_next
        self.bind_recorder(runtime)

    def controller_request(self, node, observer, *, max_tokens=2048):
        """Build one isolated OSA request from the observer's legally visible frozen menu."""
        if self.osa is None:
            raise ValueError("No isolated controller backend")
        world = self.runtime.prepared.world
        view = menu(world, node, observer)
        balance = self.runtime.team_budget.snapshot()["available_tokens"]
        options = view["options"]
        evidence = view["evidence"]
        schema = {
            "name": "activate_organization",
            "description": "Choose a legal local option and cite evidence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "option": {"type": "string", "enum": list(options)},
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(evidence)},
                        "minItems": 1,
                    },
                    "reason": {"type": "string", "maxLength": 1200},
                },
                "required": ["option", "evidence", "reason"],
                "additionalProperties": False,
            },
        }
        original = {**view, "remaining_team_tokens": balance}
        wire = {
            "model": "deepseek-flash",
            "thinking": {"type": "disabled"},
            "temperature": 1.0,
            "top_p": 1.0,
            "stream": False,
            "max_tokens": max_tokens,
            "tools": [{"type": "function", "function": schema}],
            "tool_choice": "auto",
            "messages": [
                {
                    "role": "system",
                    "content": "Select a listed change or KEEP. Cite the supplied evidence. A diagnosis gives a partner an evidence handoff duty; it leaves the implementation owner in place. Use activate_organization exactly once.",
                },
                {"role": "user", "content": compact(original)},
            ],
        }
        rid = "osa:" + identity(
            [self.trace.branch, view["anomaly_id"], view["base_version"], view["base_sha256"]]
        )
        self.osa.state = lambda: {"graph": view["base_version"], "anomaly": node["anomaly_id"]}
        payload = {
            "team_slot_id": self.trace.branch,
            "request_id": rid,
            "member_id": observer,
            "usage_id": "agent",
            "wire": wire,
        }
        estimate = self.osa.post("/tokenize", payload)["prompt_tokens"]
        if (
            not 0 < max_tokens <= 2048
            or estimate + max_tokens > balance
            or self.runtime.team_budget.snapshot()["held_tokens"]
        ):
            raise ValueError("Controller request outside the settled team allocation")
        response = self.osa.post("/chat/completions", payload)
        # Charge even a returned but invalid decision before any worker can be scheduled.
        usage = response["usage"]["total_tokens"]
        self.native_limit -= usage
        self.runtime.team_budget.native_allocation = self.native_limit
        return view, response

    def activate(self, node, observer, frozen, choice):
        rt = self.runtime
        if self.grants:
            raise ValueError("Previous activation has outstanding opportunities")
        budget = rt.team_budget.snapshot()
        if budget["held_tokens"]:
            raise ValueError("Graph activation requires a settled dispatch boundary")
        option = frozen["options"][choice["option"]]
        grants = []
        if option["op"] in ("diagnosis", "verify", "transfer_unstarted"):
            task = frozen["graph"]["work"][option["task"]]
            agent = option["assignee"]
            integrator = rt.fixed_spec["delivery_member"]
            verifier = (
                task["owner"]
                if option["op"] == "transfer_unstarted"
                else agent
                if option["op"] == "verify"
                else task["reviewer"] or agent
            )
            grants = [("new_duty", agent), ("verification", verifier), ("delivery", integrator)]
            unavailable = set(rt.stopped) | set(rt.work_ended)
            if (
                any(
                    a in unavailable or a not in rt.prepared.world.organization_active_members()
                    for _, a in grants
                )
                or budget["available_tokens"] < len(grants) * CALL_BOUND
            ):
                rejection = {
                    "activated": False,
                    "reason": "opportunities_unavailable",
                    "available": budget["available_tokens"],
                    "required": len(grants) * CALL_BOUND,
                    "graph_version": frozen["base_version"],
                }
                self.trace.observe(
                    "activation-rejected",
                    [frozen["base_version"], choice, budget["available_tokens"]],
                    layer=4,
                    graph=frozen["base_version"],
                    anomaly=node["anomaly_id"],
                    result=rejection["reason"],
                    details=rejection,
                )
                return rejection
        record = activate(rt.prepared.world, node, observer, frozen, choice, origin="osa")
        self.grants = grants
        self.version = record["version"]
        self.current.update(
            graph=self.version,
            anomaly=node["anomaly_id"],
            parent=self.trace.key("activation", self.version),
        )
        self.trace.observe(
            "activation",
            self.version,
            layer=4,
            graph=self.version,
            anomaly=node["anomaly_id"],
            result="activated",
            details={"decision": choice, "opportunities": grants, "record": record},
        )
        for actor in rt.labels:
            if actor not in rt.stopped and actor not in rt.work_ended:
                rt.policies[actor].conversation.send_message(
                    f"Organization version {self.version} is active. Inspect dynamic_status for current responsibilities. Active graph: "
                    + compact(record["after"])
                )
        if grants:
            self.wake(*grants[0])
        return record

    def wake(self, phase, actor):
        rt = self.runtime
        if actor in rt.work_ended or actor in rt.stopped:
            return False
        if actor in rt.waiting:
            rt.policies[actor].conversation.send_message(
                f"Active organization version {self.version}. Your {phase} opportunity is available. "
                "Inspect dynamic_status for the current task, evidence, and permitted next action."
            )
            rt.waiting.pop(actor, None)
            rt.roles[actor].update(status="ready", reason="Active organization responsibility")
        return True

    def select_next(self):
        rt = self.runtime
        rt.team_budget.native_allocation = self.native_limit
        if not self.grants:
            return self.normal_select()
        phase, actor = self.grants[0]
        # Ordinary work can spend only the unreserved balance. Near the floor,
        # route one opportunity to each closing role using the same SDK and quota.
        remaining = rt.team_budget.snapshot()["available_tokens"]
        preferred = phase == "new_duty" or remaining < (len(self.grants) + 1) * CALL_BOUND
        if not preferred:
            rt.team_budget.native_allocation -= len(self.grants) * CALL_BOUND
            choice = self.normal_select()
            if choice is not None:
                return choice
            rt.team_budget.native_allocation = self.native_limit
        if (
            not self.wake(phase, actor)
            or actor not in rt.prepared.world.organization_active_members()
        ):
            self.trace.observe(
                "grant-blocked",
                [self.version, phase],
                layer=2,
                agent=actor,
                graph=self.version,
                result="member_unavailable",
            )
            self.grants.pop(0)
            self.selected_phase = None
            return self.select_next()
        rt.team_budget.native_allocation -= (len(self.grants) - 1) * CALL_BOUND
        rt.sync_members()
        rt.organization_blocked = False
        rt._selected = rt.schedule.choose({actor})
        rt.cursor = rt.labels.index(actor)
        self.selected_phase = (phase, actor)
        return deepcopy(rt._selected)

    def post(self, route, payload):
        response = self.worker.post(route, payload)
        if (
            route == "/chat/completions"
            and self.selected_phase
            and payload.get("usage_id") == "agent"
            and payload["member_id"] == self.selected_phase[1]
        ):
            phase, actor = self.grants.pop(0)
            self.selected_phase = None
            self.trace.observe(
                "grant-dispatched",
                [self.version, phase],
                layer=2,
                graph=self.version,
                agent=actor,
                request=payload["request_id"],
                result="provider_returned",
                details={"response_id": response["id"]},
            )
        return response
