"""Version-bound role and scheduling orders for evidence-backed dependencies, integration and review."""

from copy import deepcopy
import json
from jsonschema import Draft202012Validator, ValidationError

from . import software_three_graph_v240 as contract
from .software_commitment_prompt_v240_4 import request as baseline_request
from .software_multitype_execution_v242 import Execution as Original
from .software_handoff_evidence_v232_6 import ReplyAwareWorld
from .software_graph_controller_v228 import menu, PROJECT
from .software_graph_execution_v230 import CALL_BOUND
from .software_event_harness_v243 import artifact_state, work_budget


def orders(row):
    graph = row["graph"]["work"]
    result = {}
    for eid, e in row["evidence"].items():
        for pkg in e.get("packages", []):
            t = pkg["task_id"]
            if t not in row["targets"] or t not in graph:
                continue
            reviewer = graph[t]["reviewer"]
            if (
                "independent_current_review" in pkg["missing"]
                and reviewer
                and reviewer != pkg["owner"]
                and len(e.get("fixed", [])) == 1
                and e.get("final_version")
            ):
                result["review:" + t] = dict(
                    dimension="D5",
                    task=t,
                    actor=reviewer,
                    recipient=pkg["owner"],
                    artifact=e["fixed"][0],
                    version=e["final_version"],
                    evidence=eid,
                    product="Independent verdict on the identified patch, with public review evidence; give the owner the verdict.",
                )
        t = e.get("task")
        for gap in e.get("gaps", []):
            upstream = gap.get("task_id")
            if t not in row["targets"] or upstream not in graph.get(t, {}).get("depends_on", []):
                continue
            producer, consumer = graph[upstream]["owner"], graph[t]["owner"]
            if producer == consumer:
                continue
            result["handoff:" + upstream + ":" + t] = dict(
                dimension="D4",
                task=t,
                actor=producer,
                recipient=consumer,
                upstream=upstream,
                artifact=gap.get("patch_id") or gap.get("evidence_id"),
                state=artifact_state(gap),
                evidence=eid,
                product="Establish the current upstream version and deliver its usable artifact; the consumer inspects and records adoption or rejection.",
            )
        if e.get("operation") == "integrate_patch" and e.get("accepted") and e.get("conflicts"):
            for t in row["targets"]:
                owner = graph[t]["owner"]
                result["integrate:" + t] = dict(
                    dimension="D6",
                    task=t,
                    actor=owner,
                    recipient=graph[t]["reviewer"]
                    or next(m for m in row["graph"]["members"] if m != owner),
                    artifact=e.get("patch"),
                    version=e.get("reference"),
                    evidence=eid,
                    product="Resolve the identified package integration conflict and publish the integrated version for independent regression verification.",
                )
    return result


def wire(row, choices):
    w = baseline_request(row)
    data = json.loads(w["messages"][-1]["content"])
    data["optional_execution_orders"] = choices
    w["messages"][-1]["content"] = json.dumps(data, ensure_ascii=False)
    w["messages"][0]["content"] += (
        " Compare keeping the present division with assigning one listed version-bound order. "
        "Use 'none' to leave the proposed route unchanged, or 'abstain' to defer. "
        "Combine an order only with a KEEP route on its package and cite the order's evidence. "
        "An order binds a responsible person, an expected product and protected execution turns. "
        "A missing upstream completion alone leaves artifact existence unknown."
    )
    schema = w["tools"][0]["function"]["parameters"]
    schema["properties"]["work_order"] = {"type": "string", "enum": ["none", "abstain", *choices]}
    schema["required"].append("work_order")
    return w


class OrderedWorld(ReplyAwareWorld):
    def _action_dynamic_status(self, actor, project_id):
        result = super()._action_dynamic_status(actor, project_id)
        ctrl = self.protocol().get("graph_control", {})
        if ctrl.get("execution_orders"):
            result["execution_orders"] = deepcopy(ctrl["execution_orders"])
        return result


class Execution(Original):
    def attach(self, runtime):
        super().attach(runtime)
        runtime.prepared.world.__class__ = OrderedWorld

    def apply_order(self, node, observer, frozen, choice, key, order):
        rt = self.runtime
        w = rt.prepared.world
        delivery = rt.fixed_spec["delivery_member"]
        actor = order["actor"]
        recipient = order["recipient"]
        verifier = frozen["graph"]["work"][order["task"]]["reviewer"] or recipient
        implementer = frozen["graph"]["work"][order["task"]]["owner"]
        grants = [
            ("new_duty", actor),
            ("publish_artifact", actor),
            ("inspect_handoff", recipient),
            ("record_disposition", recipient),
            ("implementation", implementer),
            ("verification", verifier),
            ("fix_current_tree", delivery),
            ("delivery", delivery),
        ]
        b = rt.team_budget.snapshot()
        if (
            self.grants
            or b["held_tokens"]
            or min(b["remaining_attempts"], b["remaining_decisions"]) < len(grants)
            or b["available_tokens"] < len(grants) * CALL_BOUND
        ):
            raise ValueError("Incomplete action or token reserve")
        available = set(w.organization_active_members()) - set(rt.work_ended) - set(rt.stopped)
        if not all(a in available for _, a in grants):
            raise ValueError("Assigned member is unavailable")
        with w.store.lock():
            w.state = w.store.load()
            if (
                w.protocol()["terminal"]
                or menu(w, node, observer) != frozen
                or key not in orders(self.record)
            ):
                raise ValueError("Stale or terminal organization")
            ctrl = w.protocol().setdefault(
                "graph_control", dict(versions=[], duties={}, blockers=[])
            )
            before = deepcopy(frozen["graph"])
            if ctrl.get("execution_orders"):
                raise ValueError("Outstanding prior order")
            ctrl["execution_orders"] = {key: deepcopy(order)}
            after = {**before, "execution_orders": deepcopy(ctrl["execution_orders"])}
            active = dict(
                version=frozen["base_version"] + 1,
                before=before,
                after=after,
                changed=True,
                decision={**choice, "option": key},
                after_event=len(w.state["software_events"]),
                world_clock=w.state["clock"],
                evidence_refs=[frozen["evidence"][s] for s in choice["evidence"]],
            )
            ctrl["versions"].append(active)
            w.store.save(w.state)
        self.grants = grants
        self.version = active["version"]
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
            details=dict(record=active, opportunities=grants),
        )
        for m in rt.labels:
            if m in available:
                rt.policies[m].conversation.send_message(
                    "Active organization order: "
                    + json.dumps(order)
                    + ". Work within your role and permissions. Report any blocker or contrary evidence."
                )
        self.wake(*grants[0])
        return active

    def decide(self, node, observer, frozen, arm):
        row = self.record
        if arm == "KEEP":
            return super().decide(node, observer, frozen, arm)
        if (
            frozen["graph"] != row["graph"]
            or frozen["options"] != row["options"]
            or observer != row["observer"]
            or self.runtime.team_budget.snapshot()["available_tokens"] != row["available_tokens"]
        ):
            raise ValueError("Decision boundary mismatch")
        choices = orders(row)
        w = wire(row, choices)
        payload = dict(
            team_slot_id=self.trace.branch,
            request_id=self.trace.branch + ":osa",
            member_id=observer,
            usage_id="agent",
            wire=w,
        )
        api = self.osa.backend
        if api("/tokenize", payload)["prompt_tokens"] + w["max_tokens"] > 8192:
            raise ValueError("OSA exceeds registered reserve")
        body = api("/chat/completions", payload)
        used = body["usage"]["total_tokens"]
        self.native_limit -= used
        self.runtime.team_budget.native_allocation = self.native_limit
        keep = dict(
            option="K",
            evidence=[next(iter(frozen["evidence"]))],
            reason="Maintain current work allocation",
        )
        info = dict(
            source="live_v243",
            validator="accepted",
            osa_tokens=used,
            response=body["id"],
            orders=choices,
            proposal=None,
            first_action=None,
            validation_checks=[],
        )
        try:
            calls = body["choices"][0]["message"].get("tool_calls") or []
            if len(calls) != 1 or calls[0]["function"]["name"] != "activate_organization":
                raise ValueError("Expected one activation call")
            d = json.loads(calls[0]["function"]["arguments"])
            Draft202012Validator(w["tools"][0]["function"]["parameters"]).validate(d)
            info["proposal"] = d
            c = contract.compile_decision(row, d)
            key = d["work_order"]
            cmd = dict(zip(row["evidence"], row["provenance"]["commands"], strict=True))
            refs = {v["command_id"]: k for k, v in frozen["evidence"].items()}
            choice = dict(
                option=c["patch"]["option"],
                evidence=[refs[cmd[k]] for k in d["basis"]],
                reason=d["reason"][:1200],
            )
            if not choice["evidence"]:
                raise ValueError("No cited evidence")
            info.update(
                requested="ABSTAIN"
                if key == "abstain"
                else "CHANGE"
                if key in choices
                else c["disposition"],
                graph_patch=c["patch"],
                obligations=c["effective"],
            )
            if key in choices:
                order = choices[key]
                if (
                    choice["option"] != "K"
                    or c["execution"]["package"] != order["task"]
                    or order["evidence"] not in d["basis"]
                ):
                    raise ValueError("Order lacks a compatible scoped route or basis")
                info["graph_patch"] = {
                    **c["patch"],
                    "option": key,
                    "operations": [
                        [order["dimension"], "ASSIGN_EXECUTION_ORDER", order["task"], order],
                        ["D7", "RESERVE_EXECUTION", order["task"], order["actor"]],
                    ],
                    "target_version": contract.base.identity(
                        {**frozen["graph"], "execution_orders": {key: order}}
                    ),
                }
                active = self.apply_order(node, observer, frozen, choice, key, order)
                binding = dict(actor=order["actor"], action=key, package=order["task"])
            else:
                if key == "abstain" and choice["option"] != "K":
                    raise ValueError("Abstention requires incumbent graph")
                op = frozen["options"][choice["option"]]["op"]
                b = self.runtime.team_budget.snapshot()
                capacity = work_budget(
                    "A1" if op == "diagnosis" else "A4",
                    b["available_tokens"] + used,
                    b["remaining_attempts"],
                    b["remaining_decisions"],
                )
                if op != "keep" and not capacity["enough"]:
                    raise ValueError("Insufficient closure reserve")
                active = self.activate(node, observer, frozen, choice)
                if active.get("activated") is False:
                    raise ValueError(str(active))
                if active["changed"]:
                    actor = frozen["options"][choice["option"]]["assignee"]
                    owner = active["after"]["work"][frozen["options"][choice["option"]]["task"]][
                        "owner"
                    ]
                    if op != "diagnosis":
                        self.grants[1:1] = [
                            ("publish_artifact", actor),
                            ("inspect_handoff", owner),
                            ("record_disposition", owner),
                        ]
                    self.grants.insert(-2, ("implementation", owner))
                    self.grants.insert(
                        -1, ("fix_current_tree", self.runtime.fixed_spec["delivery_member"])
                    )
                binding = contract.dispatch(row, c, active["after"])
                if key != "abstain":
                    self.runtime.policies[binding["actor"]].conversation.send_message(
                        "Current organization plan: "
                        + json.dumps(binding)
                        + ". Outstanding obligations: "
                        + json.dumps(c["effective"])
                    )
            info.update(
                first_action=binding if key != "abstain" else None,
                planned_grants=list(self.grants),
                expected_graph=active["after"],
                validation_checks=[
                    "settled_boundary",
                    "current_graph",
                    "member_scope",
                    "evidence",
                    "allocation",
                ],
            )
        except (ValueError, ValidationError, TypeError, KeyError) as exc:
            # A post-commit execution fault must never be relabelled as a rejected proposal.
            if (
                len(
                    self.runtime.prepared.world.protocol()
                    .get("graph_control", {})
                    .get("versions", [])
                )
                != frozen["base_version"]
            ):
                raise
            info.update(validator="rejected", error=str(exc)[:600])
            active = self.activate(node, observer, frozen, keep)
        return active, info
