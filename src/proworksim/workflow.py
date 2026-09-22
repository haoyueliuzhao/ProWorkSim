"""Declarative work nodes and guarded event releases; no numeric domain answers."""

from dataclasses import asdict, dataclass

from .lifecycle import current_id, current_item, current_work_items


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
    return WorkflowSpec(
        "chain" if topology == "coordination" else topology,
        nodes,
        (EventRule("next-release", guards, effects, "second"),),
    )


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
            (current_item(state, dep) or {}).get("status") != "accepted"
            for dep in node["dependencies"]
        ):
            continue
        item = work_item(spec, node["requirement_version"], origin)
        item.update(
            work_item_id=node["node_id"],
            node_id=node["node_id"],
            applicability="current",
            activated_at=state["clock"],
            source_period=spec["facts"][node["source_stage"]]["period"],
            basis_requirement_version=node["scenario_revision"],
            required_basis=state.get("basis_by_scenario", {}).get(str(node["scenario_revision"])),
            dependencies=[current_id(state, dep) for dep in node["dependencies"]],
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
        for dep in item["dependencies"]:
            prior = state["work_items"][dep]
            if (
                prior.get("scenario_revision") == node["scenario_revision"]
                and prior.get("source_stage") == node["source_stage"]
            ):
                item["requirement_version"] = max(
                    item["requirement_version"], prior["requirement_version"]
                )
                if prior.get("required_basis"):
                    item["required_basis"] = prior["required_basis"]
                    item["basis_requirement_version"] = prior.get(
                        "basis_requirement_version", prior["requirement_version"]
                    )
        item["required_credentials"] = (
            [dict(item["required_basis"])]
            if item.get("required_basis") and list(node["deliverables"]) != ["answer"] else []
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
                "note 绑定 model/brief 的实际版本，包含股价、敏感性结果和当前 brief 要求的 audience_content；写入 dependencies 后提交。",
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
    # Work-specific applicability is known only after activation has finished.
    from .freshness import refresh_freshness
    from .core.projections import rebuild_projections

    rebuild_projections(state)
    refresh_freshness(state)


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
            (current_item(world.state, node) or {}).get("status") == "accepted"
            for node in rule["after_accepted"]
        ):
            world.state["fired_rules"].append(rule["rule_id"])
            world._event("apply_rule", {"rule_id": rule["rule_id"]}, rule["delay"])


def is_complete(state):
    expected = {n["node_id"] for n in state.get("workflow", {}).get("nodes", [])}
    return (
        expected <= set(state["work_items"])
        and not state["events"]
        and all(w["status"] == "accepted" for w in current_work_items(state))
    )


def _reachable_workflow(nodes, rules):
    """Optimistic closure: every available work item can be accepted.

    Work prerequisites are conjunctive; independent producers of the same
    release are alternatives. This does not prove professional solvability
    or success under every possible schedule.
    """
    accepted, fired, released = set(), set(), {"initial"}
    while True:
        next_work = {
            node["node_id"]
            for node in nodes
            if node["release"] in released and set(node["dependencies"]) <= accepted
        }
        next_rules = {rule["rule_id"] for rule in rules if set(rule["after_accepted"]) <= accepted}
        if next_work <= accepted and next_rules <= fired:
            return accepted, fired, released
        accepted |= next_work
        fired |= next_rules
        released |= {rule["release"] for rule in rules if rule["rule_id"] in fired}


def validate_workflow(workflow):
    nodes = workflow["nodes"]
    rules = workflow["event_rules"]
    ids = {node["node_id"] for node in nodes}
    if not nodes or len(ids) != len(nodes):
        raise ValueError("Workflow nodes must have unique IDs")
    releases = {"initial"} | {r["release"] for r in rules}
    rule_ids = [r["rule_id"] for r in rules]
    if len(set(rule_ids)) != len(rule_ids):
        raise ValueError("Event rules must have unique IDs")
    for node in nodes:
        unknown = set(node["dependencies"]) - ids
        if unknown:
            raise ValueError(f"Work {node['node_id']} has unknown dependencies: {sorted(unknown)}")
        if node["release"] not in releases:
            raise ValueError(
                f"Work {node['node_id']} requires release {node['release']!r} with no producer"
            )
        if not set(node["deliverables"]) <= {"model", "memo", "note", "answer"}:
            raise ValueError("Unsupported artifact role in this domain template")
    for rule in rules:
        unknown = set(rule["after_accepted"]) - ids
        if unknown:
            raise ValueError(
                f"Event {rule['rule_id']} has unknown accepted-work guards: {sorted(unknown)}"
            )
        if not isinstance(rule["delay"], int) or not 1 <= rule["delay"] <= 100:
            raise ValueError(f"Invalid event delay for {rule['rule_id']}: expected 1..100")
        if any(
            effect["kind"] not in {"publish_disclosure", "publish_scope", "revise_brief"}
            for effect in rule["effects"]
        ):
            raise ValueError("Unsupported event effect")

    accepted, fired, released = _reachable_workflow(nodes, rules)
    if accepted == ids and fired == set(rule_ids):
        return
    reasons = []
    for node in nodes:
        if node["node_id"] in accepted:
            continue
        waiting = []
        if node["release"] not in released:
            producers = sorted(
                rule["rule_id"] for rule in rules if rule["release"] == node["release"]
            )
            waiting.append(f"release {node['release']!r} from events {producers}")
        missing = set(node["dependencies"]) - accepted
        if missing:
            waiting.append(f"accepted dependencies {sorted(missing)}")
        reasons.append(f"work {node['node_id']}: waiting for {' and '.join(waiting)}")
    for rule in rules:
        if rule["rule_id"] not in fired:
            missing = sorted(set(rule["after_accepted"]) - accepted)
            reasons.append(f"event {rule['rule_id']}: waiting for accepted work {missing}")
    raise ValueError(
        "Unreachable workflow from initial (Cyclic dependencies or release deadlock): "
        + "; ".join(reasons)
    )
