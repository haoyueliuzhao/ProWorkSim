"""Organization control with a single checked-T1 worker interface and an isolated strategy endpoint."""

import json
import time
from .software_context_v232 import checked_context, source_estimates
from .software_context_builder_v230 import compact, identity, object_text
from .software_graph_execution_v230 import Execution
from .storage import atomic_write, json_bytes, digest


def visibility(wire, events):
    """External index. Separate explicit event identities, operation receipts and successful reads."""
    seqs = {e["sequence"] for e in events}
    by_command = {}
    for e in events:
        if e.get("operation_id"):
            by_command.setdefault(e["operation_id"], []).append(e["sequence"])
    mentions = set()
    ops = set()
    readbacks = []
    calls = {}
    for i, m in enumerate(wire["messages"]):
        for c in m.get("tool_calls") or []:
            calls[c["id"]] = c["function"]["name"]
        text = m.get("content") or ""
        d = object_text(text)
        if not d and isinstance(text, str) and text.startswith("Work observation: "):
            d = object_text(text.removeprefix("Work observation: "))
        if not d:
            continue
        stack = [d]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack.extend(x)
            if not isinstance(x, dict):
                continue
            for k, v in x.items():
                if k in ("command_id", "operation_id") and isinstance(v, str) and v in by_command:
                    ops.update(by_command[v])
                if k in ("event_sequence", "test_event_sequence") or (
                    k == "sequence" and "kind" in x and "actor_id" in x
                ):
                    if type(v) is int and v in seqs:
                        mentions.add(v)
                if isinstance(v, (dict, list)):
                    stack.append(v)
        name = calls.get(m.get("tool_call_id"))
        r = d.get("result") or {}
        if (
            m["role"] == "tool"
            and d.get("ok") is True
            and name in ("read_work_event", "read_test_result")
            and isinstance(r, dict)
        ):
            readbacks.append(
                {
                    "message_index": i,
                    "tool": name,
                    "call": m["tool_call_id"],
                    "result_hash": identity(r),
                    "report_id": r.get("report_id"),
                    "sequence": r.get("sequence"),
                    "report_event": r.get("report_event"),
                }
            )
    return {
        "explicit_event_sequences": sorted(mentions),
        "operation_linked_sequences": sorted(ops),
        "without_direct_identifier": sorted(seqs - mentions - ops),
        "successful_readbacks_present": readbacks,
    }


class Endpoint:
    def __init__(self, backend, owner, controller=False):
        self.backend, self.owner, self.controller = backend, owner, controller
        self.state = lambda: dict(owner.current)

    def post(self, route, payload):
        actor = payload["member_id"]
        branch = self.owner.trace.branch
        if payload["team_slot_id"] != branch:
            raise ValueError("Wrong branch binding")
        original = payload["wire"]
        role = "osa" if self.controller else "worker" if original.get("tools") else "condenser"
        current = self.state()
        version = current.get("graph", 0)
        world = self.owner.runtime.prepared.world if self.owner.runtime else None
        control = (world.protocol().get("graph_control") or {}) if world else {}
        history = [
            {"version": r["version"], "option": r["decision"]["option"]}
            for r in control.get("versions", ())
        ]
        shown, manifest = checked_context(original, actor, role, version, history)
        events = world.state["software_events"] if world else []
        if role == "worker" and manifest["snapshots"]:
            duties = {
                tid: d
                for tid, d in control.get("duties", {}).items()
                if d.get("owner") == actor and d.get("status") == "pending"
            }
            if duties:
                eligible = world.diagnosis_evidence(actor)
                i = manifest["snapshots"][-1]["index"]
                v = object_text(shown["messages"][i]["content"])
                v["pending_diagnosis"] = {
                    "tasks": {k: d["recipient"] for k, d in duties.items()},
                    "own_eligible_event_sequences": eligible[-3:],
                    "handoff": "After examining evidence, use send_message for the listed task and recipient. Start body with DIAG <own event number> followed by a space and your concrete finding.",
                }
                shown["messages"][i]["content"] = compact(v)
                manifest["items"][i]["shown_hash"] = identity(shown["messages"][i])
        manifest["shown_wire"] = identity(shown)
        adapted = {**payload, "wire": shown}
        if route in ("/tokenize", "/tokenize-prefix"):
            result = self.backend(route, adapted)
            if result["request_sha256"] != digest(json_bytes(shown)):
                raise ValueError("Wrong counted wire")
            return {
                **result,
                "projected_request_sha256": result["request_sha256"],
                "request_sha256": digest(json_bytes(original)),
            }
        if route != "/chat/completions":
            raise ValueError("Unsupported provider route")
        rid = payload["request_id"]
        target = self.owner.folder / role / identity([branch, actor, rid])
        target.mkdir(parents=True, exist_ok=False)
        count = self.backend("/tokenize", adapted)
        if count["request_sha256"] != digest(json_bytes(shown)):
            raise ValueError("Final count mismatch")
        manifest.update(
            episode_id=self.owner.trace.episode,
            branch=branch,
            request_id=rid,
            org_graph_version=version,
            anomaly_id=current.get("anomaly"),
            opportunity=current.get("opportunity"),
            visibility=visibility(shown, events),
            source_estimates=source_estimates(shown, role, self.owner.content_counter),
            local_input=count.get("local_encoded_prompt_tokens"),
            estimated_input_tokens=count["prompt_tokens"],
            reserved_output_tokens=shown["max_tokens"],
        )
        if manifest["local_input"] is not None:
            manifest["template_and_segmentation_residual"] = manifest["local_input"] - sum(
                manifest["source_estimates"].values()
            )
        for name, obj in [("original", original), ("shown", shown), ("manifest", manifest)]:
            atomic_write(target / (name + ".json"), json_bytes(obj))
        parent = self.owner.trace.event(
            "dispatch",
            rid,
            layer=2,
            parent=current.get("parent"),
            graph=version,
            anomaly=current.get("anomaly"),
            opportunity=current.get("opportunity"),
            request=rid,
            agent=actor,
            ref=str(target / "manifest.json"),
            timestamp=time.time(),
            result="prepared",
        )
        body = self.backend(route, adapted)
        self.owner.trace.observe(
            "response",
            body["id"],
            layer=5,
            parent=parent,
            request=rid,
            agent=actor,
            graph=version,
            opportunity=current.get("opportunity"),
            timestamp=time.time(),
            result="returned",
            details=body.get("usage"),
        )
        return body


class OrganizationExecution(Execution):
    def __init__(
        self, backend, folder, episode, branch, *, content_counter, controller_backend=None
    ):
        super().__init__(
            backend, folder, episode, branch, "T1", controller_backend=controller_backend
        )
        self.content_counter = content_counter
        self.worker = Endpoint(backend, self)
        self.osa = Endpoint(controller_backend, self, True) if controller_backend else None
        self.current.update(graph=0)

    def activate(self, node, observer, frozen, choice):
        options = frozen["options"]
        target = options[choice["option"]]
        if target["op"] != "keep":
            graph = frozen["graph"]
            task = target["task"]
            agent = target["assignee"]
            if task not in node["affected_work"] or agent not in graph["members"]:
                raise ValueError("Target outside the anomaly scope or current membership")
            work = graph["work"]
            visited = set()

            def visit(key, ancestors):
                if key in ancestors or key not in work:
                    raise ValueError("Invalid work dependency")
                if key in visited:
                    return
                row = work[key]
                if row["owner"] not in graph["members"] or (
                    row["reviewer"] is not None and row["reviewer"] not in graph["members"]
                ):
                    raise ValueError("Unbound owner or reviewer")
                for dep in row["depends_on"]:
                    visit(dep, ancestors | {key})
                visited.add(key)

            visit(task, set())
        return super().activate(node, observer, frozen, choice)

    def decide(self, node, observer, frozen, arm):
        base = {
            "option": "K",
            "evidence": [next(iter(frozen["evidence"]))],
            "reason": "Maintain current work allocation",
        }
        choice = base
        info = {
            "arm": arm,
            "source": "fixed_keep",
            "proposal": None,
            "validator": "accepted",
            "osa_tokens": 0,
        }
        if arm == "OSA":
            view, resp = self.controller_request(node, observer)
            if view != frozen:
                raise ValueError("Decision boundary moved")
            info.update(
                source="independent_osa",
                controller_response=resp["id"],
                osa_tokens=resp["usage"]["total_tokens"],
            )
            try:
                calls = resp["choices"][0]["message"].get("tool_calls") or []
                if len(calls) != 1 or calls[0]["function"]["name"] != "activate_organization":
                    raise ValueError("Expected one organization decision")
                choice = json.loads(calls[0]["function"]["arguments"])
                info["proposal"] = choice
                if not isinstance(choice, dict) or choice.get("option") not in frozen["options"]:
                    raise ValueError("Unlisted choice")
            except (TypeError, KeyError, ValueError) as exc:
                info.update(validator="rejected", reason=str(exc))
                choice = base
        elif arm != "KEEP":
            raise ValueError("Unknown condition")
        try:
            record = self.activate(node, observer, frozen, choice)
        except (ValueError, KeyError, TypeError) as exc:
            if choice == base or self.runtime.prepared.world.protocol().get(
                "graph_control", {}
            ).get("versions"):
                raise
            info.update(validator="rejected", reason=str(exc))
            record = self.activate(node, observer, frozen, base)
        if record.get("activated") is False:
            info.update(validator="rejected", reason=record)
            record = self.activate(node, observer, frozen, base)
        return record, info
