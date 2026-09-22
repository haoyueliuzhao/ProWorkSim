"""Declarative work nodes and guarded event releases; no numeric domain answers."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class WorkNode:
    node_id: str
    deliverables: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    release: str = "initial"
    requirement_version: int = 1
    scenario_revision: int = 1
    source_stage: str = "current"
    source_version: str = "v2"
    protected_artifacts: tuple[str, ...] = ()
    owner_role: str = "analyst"


@dataclass(frozen=True)
class EventRule:
    rule_id: str
    after_accepted: tuple[str, ...]
    effects: tuple[dict, ...]
    release: str
    delay: int = 2


@dataclass(frozen=True)
class WorkflowSpec:
    topology_id: str
    nodes: tuple[WorkNode, ...]
    event_rules: tuple[EventRule, ...]

    def public_spec(self):
        return asdict(self)


def make_workflow(delivery, topology="chain"):
    if topology not in ("chain", "fork", "selective", "coordination"):
        raise ValueError("Unknown topology")
    if delivery != "continuous":
        if topology != "chain":
            raise ValueError("Additional topologies require continuous delivery")
        outputs = ("answer",) if delivery == "short" else ("model",)
        return WorkflowSpec(topology, (WorkNode("work-1", outputs),), ())
    effects = (
        {"kind": "publish_disclosure", "stage": "future"},
        {"kind": "publish_scope", "revision": 2},
    )
    if topology in ("chain", "coordination"):
        nodes = (
            WorkNode("work-1", ("model", "memo")),
            WorkNode("work-2", ("model", "memo"), ("work-1",), "second", 2, 2, "future", "v3"),
        )
        guards = ("work-1",)
    else:
        nodes = (
            WorkNode("model-1", ("model",)),
            WorkNode("memo-1", ("memo",), ("model-1",)),
            WorkNode("note-1", ("note",), ("model-1",)),
        )
        guards = ("memo-1", "note-1")
        if topology == "selective":
            effects = ({"kind": "revise_brief", "audience": "external_client"},)
            nodes += (
                WorkNode(
                    "note-2", ("note",), guards, "second", 2, 1, "current", "v2", ("model", "memo")
                ),
            )
        else:
            nodes += (
                WorkNode("model-2", ("model",), guards, "second", 2, 2, "future", "v3"),
                WorkNode("memo-2", ("memo",), ("model-2",), "second", 2, 2, "future", "v3"),
                WorkNode("note-2", ("note",), ("model-2",), "second", 2, 2, "future", "v3"),
            )
    return WorkflowSpec(topology, nodes, (EventRule("next-release", guards, effects, "second"),))


def configure(state, spec):
    state["workflow"] = (
        spec.get("workflow") or make_workflow(spec["project"]["delivery"]).public_spec()
    )
    validate_workflow(state["workflow"])
    state.setdefault("released_groups", ["initial"])
    state.setdefault("fired_rules", [])


def activate_ready(state, spec, origin):
    from .compiler import work_item

    for node in state["workflow"]["nodes"]:
        if (
            node["node_id"] in state["work_items"]
            or node["release"] not in state["released_groups"]
        ):
            continue
        if any(
            state["work_items"].get(dep, {}).get("status") != "accepted"
            for dep in node["dependencies"]
        ):
            continue
        item = work_item(spec, node["requirement_version"], origin)
        item.update(
            work_item_id=node["node_id"],
            dependencies=node["dependencies"],
            deliverables=node["deliverables"],
            owner_role=node["owner_role"],
            scenario_revision=node["scenario_revision"],
            source_stage=node["source_stage"],
            source_version=node["source_version"],
            protected_versions={
                aid: state["artifacts"][aid]["current_version"]
                for aid in node["protected_artifacts"]
            },
        )
        if list(node["deliverables"]) == ["memo"]:
            item["goal"] = "将研究备忘录同步到已提交模型，维护实际依赖和证据引用。"
            item["visible_requirements"] = [
                "阅读 guide、financials 和已更新 model，只提交 memo。",
                "memo 的 source_versions 和写入 dependencies 必须绑定实际使用的 financials/model 版本。",
            ]
        elif list(node["deliverables"]) == ["note"]:
            item["goal"] = "按 brief 的当前受众要求同步情景说明 note。"
            item["visible_requirements"] = [
                "阅读 guide 的 note_schema、brief、model。",
                "note 绑定 model/brief 的实际版本，包含股价与敏感性结果；写入 dependencies 后提交。",
            ]
        elif list(node["deliverables"]) == ["model"]:
            item["visible_requirements"] = [
                r for r in item["visible_requirements"] if "memo" not in r and "备忘录" not in r
            ]
            item["goal"] = (
                "更新 model，保持公式可重算并完成增长率×利润率敏感性分析；本项仅提交模型。"
            )
        if node["protected_artifacts"]:
            item["visible_requirements"].append(
                "本次只改 note；model 和 memo 不受此次受众变化影响，须保留其版本和内容。"
            )
        state["work_items"][node["node_id"]] = item


def on_accept(world):
    from .storage import read_json

    spec = read_json(world.store.control / "spec.json")
    if "workflow" not in world.state:
        configure(world.state, spec)
    activate_ready(world.state, spec, "predecessor-accepted")
    for rule in world.state["workflow"]["event_rules"]:
        if rule["rule_id"] in world.state["fired_rules"]:
            continue
        if all(
            world.state["work_items"].get(node, {}).get("status") == "accepted"
            for node in rule["after_accepted"]
        ):
            world.state["fired_rules"].append(rule["rule_id"])
            world._event("apply_rule", {"rule_id": rule["rule_id"]}, rule["delay"])


def is_complete(state):
    expected = {n["node_id"] for n in state.get("workflow", {}).get("nodes", [])}
    return (
        expected <= set(state["work_items"])
        and not state["events"]
        and all(w["status"] == "accepted" for w in state["work_items"].values())
    )


def validate_workflow(workflow):
    nodes = workflow["nodes"]
    ids = {node["node_id"] for node in nodes}
    if not nodes or len(ids) != len(nodes):
        raise ValueError("Workflow nodes must have unique IDs")
    releases = {"initial"} | {r["release"] for r in workflow["event_rules"]}
    rule_ids = [r["rule_id"] for r in workflow["event_rules"]]
    if len(set(rule_ids)) != len(rule_ids):
        raise ValueError("Event rules must have unique IDs")
    for node in nodes:
        if not set(node["dependencies"]) <= ids or node["release"] not in releases:
            raise ValueError("Unresolvable work dependency or release")
        if not set(node["deliverables"]) <= {"model", "memo", "note", "answer"}:
            raise ValueError("Unsupported artifact role in this domain template")
    ready = set()
    while True:
        added = {node["node_id"] for node in nodes if set(node["dependencies"]) <= ready} - ready
        if not added:
            break
        ready |= added
    if ready != ids:
        raise ValueError("Cyclic work dependencies")
    for rule in workflow["event_rules"]:
        if not set(rule["after_accepted"]) <= ids or not 1 <= rule["delay"] <= 100:
            raise ValueError("Invalid event guard or delay")
        if any(
            effect["kind"] not in {"publish_disclosure", "publish_scope", "revise_brief"}
            for effect in rule["effects"]
        ):
            raise ValueError("Unsupported event effect")
