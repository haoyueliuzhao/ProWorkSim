"""Project facts -> obligation status and readiness -> versioned organization/dispatch."""

from copy import deepcopy
import json
from jsonschema import Draft202012Validator

from . import software_scoped_obligations_v239_3 as baseline
from .software_context_builder_v230 import compact
from .software_stage_response_v236 import enum
from .software_structured_policy_v237 import arr, obj

old = baseline.old
base = old.base
COMPLETION = ("UNSATISFIED", "SATISFIED", "STALE", "UNKNOWN")
READINESS = ("READY", "BLOCKED", "CONDITIONAL", "NOT_APPLICABLE")
ACTIONS = {
    "CHECK_UPSTREAM_STATUS": "gather_evidence",
    "INSPECT_UPSTREAM_ARTIFACT": "gather_evidence",
    "VALIDATE_UPSTREAM_ARTIFACT": "verify_integrated_version",
    "EXECUTE_UPSTREAM_WORK": "release_upstream",
    "ADOPT_UPSTREAM_ARTIFACT": "adopt_upstream",
    "PROCEED_DOWNSTREAM": "continue_progress",
}
DEP_READY = {
    "unknown": ("CHECK_UPSTREAM_STATUS", "INSPECT_UPSTREAM_ARTIFACT"),
    "absent": ("EXECUTE_UPSTREAM_WORK",),
    "present": ("VALIDATE_UPSTREAM_ARTIFACT",),
    "validated": ("ADOPT_UPSTREAM_ARTIFACT",),
    "adopted": ("PROCEED_DOWNSTREAM",),
}


def project_graph(row):
    facts = {}
    deps = {}
    for evidence_id, ev in row["evidence"].items():
        rid = base.identity([row["instance"], row["observer"], evidence_id, ev])
        facts[evidence_id] = {"fact_id": rid, "receipt": ev}
        if ev.get("operation") == "dependency_artifact_observation":
            edge = (ev.get("downstream"), ev.get("upstream"))
            previous = deps.get(edge)
            if not previous or not ev.get("accepted") or ev.get("observer") != row["observer"]:
                continue
            state = ev.get("artifact_state")
            if state not in DEP_READY or ev.get("edge_version") != previous["edge_version"]:
                continue
            if state in ("present", "validated", "adopted") and not ev.get("artifact_id"):
                continue
            if state in ("validated", "adopted") and not ev.get("valid_for_edge"):
                continue
            if state == "adopted" and ev.get("consumer") != row["graph"]["work"][edge[0]]["owner"]:
                continue
            previous.update(
                artifact_state=state, artifact_id=ev.get("artifact_id"), latest=evidence_id
            )
            continue
        if (
            ev.get("operation") in ("work_readiness", "begin_work")
            and "gaps" in ev
            and ev.get("task")
        ):
            deps = {k: v for k, v in deps.items() if k[0] != ev["task"]}
        for gap in ev.get("gaps", []):
            consumer, producer = ev.get("task"), gap.get("task_id")
            if (
                consumer not in row["graph"]["work"]
                or producer not in row["graph"]["work"][consumer]["depends_on"]
            ):
                continue
            kind = gap.get("kind")
            artifact = gap.get("patch_id") or gap.get("evidence_id")
            if kind not in (
                "upstream_not_current",
                "upstream_patch_not_adopted",
                "upstream_evidence_version_not_adopted",
            ):
                continue
            # The native readiness contract emits the not-adopted gap only after the upstream
            # completion and dependency revision are current. This certifies handoff eligibility.
            eligible = kind != "upstream_not_current" and bool(artifact)
            deps[consumer, producer] = dict(
                consumer=consumer,
                producer=producer,
                edge_version=rid,
                latest=evidence_id,
                artifact_state="validated" if eligible else "unknown",
                artifact_id=artifact,
                completion_record="current" if eligible else "missing_or_stale",
            )
    return {
        "observer": row["observer"],
        "facts": facts,
        "dependencies": list(deps.values()),
        "packages": row["work_status"],
    }


def dual(t, tasks, k):
    status = t["status"]
    if status == "DONE":
        return "SATISFIED", "NOT_APPLICABLE"
    if status == "UNKNOWN":
        return "UNKNOWN", "NOT_APPLICABLE"
    if status == "STALE":
        return "STALE", "READY" if base.ready(tasks, k) else "BLOCKED"
    if t["source"] in (
        "workflow_successor",
        "conditional_on_failure_localization",
        "conditional_on_failure_details",
    ):
        return "UNKNOWN", "CONDITIONAL"
    return "UNSATISFIED", "READY" if base.ready(tasks, k) else "BLOCKED"


def build(row):
    project = project_graph(row)
    # Supplementary inspection receipts relate to a prior readiness event; keep that
    # package contract as the task source while applying newer artifact observations.
    events = {
        k: v
        for k, v in row["evidence"].items()
        if v.get("operation") != "dependency_artifact_observation"
    }
    task_row = {**row, "evidence": events}
    tasks = baseline.snapshot(task_row)
    nodes = {}
    catalog = old.routes(task_row, tasks)
    for k, t in tasks.items():
        completion, readiness = dual(t, tasks, k)
        nodes[k] = dict(
            package=t["package"],
            label=t["action"],
            completion=completion,
            readiness=readiness,
            requires=t["requires"],
            evidence=t["evidence"],
            completion_evidence="fresh receipt for " + t["action"],
            source=t["source"],
        )
    for edge in project["dependencies"]:
        p, u = edge["consumer"], edge["producer"]
        # All unadopted parents must be resolved before downstream work can resume.
        for k, t in list(nodes.items()):
            if k.startswith(p + "/") and t["label"] in (
                "release_upstream",
                "adopt_upstream",
                "continue_progress",
                "gather_evidence",
            ):
                del nodes[k]
        catalog = {
            k: v
            for k, v in catalog.items()
            if not (v["immediate"].startswith(p + "/") and v["immediate"] not in nodes)
        }
    for edge in project["dependencies"]:
        p, u = edge["consumer"], edge["producer"]
        handoff_id = f"{p}/dependency/{u}/CURRENT_HANDOFF"
        nodes[handoff_id] = dict(
            package=u,
            label="release_upstream",
            completion="UNSATISFIED"
            if edge["completion_record"] == "missing_or_stale"
            else "SATISFIED",
            readiness="CONDITIONAL"
            if edge["completion_record"] == "missing_or_stale"
            else "NOT_APPLICABLE",
            requires=[],
            condition="establish a usable handoff reference; inspect before assuming production is needed",
            completion_evidence="registered current handoff",
            evidence=[edge["latest"]],
            source="handoff_registration",
        )
        allowed = DEP_READY[edge["artifact_state"]]
        for kind, label in ACTIONS.items():
            k = f"{p}/dependency/{u}/{kind}"
            package = u if kind == "EXECUTE_UPSTREAM_WORK" else p
            downstream_blocked = kind == "PROCEED_DOWNSTREAM" and any(
                e["artifact_state"] != "adopted"
                for e in project["dependencies"]
                if e["consumer"] == p
            )
            ready = kind in allowed and not downstream_blocked
            # A missing registration leaves upstream production unresolved. Preserve the
            # delivery obligation while leaving the existence of a usable artifact unknown.
            satisfaction = (
                "UNKNOWN"
                if edge["artifact_state"] == "unknown"
                else "UNSATISFIED"
                if ready
                else "UNKNOWN"
            )
            if kind == "ADOPT_UPSTREAM_ARTIFACT" and edge["artifact_state"] == "adopted":
                satisfaction = "SATISFIED"
            nodes[k] = dict(
                package=package,
                label=label,
                completion=satisfaction,
                readiness="READY"
                if ready
                else "NOT_APPLICABLE"
                if satisfaction == "SATISFIED"
                else "BLOCKED"
                if downstream_blocked
                else "CONDITIONAL",
                requires=[],
                condition=f"artifact_state in {[s for s, a in DEP_READY.items() if kind in a]}",
                completion_evidence=f"scoped {kind} receipt for {u} -> {p}",
                evidence=[edge["latest"]],
                source="dependency_contract",
            )
            if ready:
                catalog["K|" + k] = dict(
                    option="K",
                    immediate=k,
                    actor=row["graph"]["work"][package]["owner"],
                    package=package,
                    action=label,
                    dependency_action=kind,
                    added_product="none",
                )
    catalog = {k: v for k, v in catalog.items() if nodes[v["immediate"]]["readiness"] == "READY"}
    return project, nodes, catalog


def request(row):
    project, nodes, menu = build(row)
    w = baseline.request(row)
    fields = w["tools"][0]["function"]["parameters"]["properties"]
    fields["route"] = enum(list(menu))
    fields["current_obligations"] = arr(
        [k for k, n in nodes.items() if n["completion"] != "SATISFIED"], 1
    )
    fields["anomaly"] = enum(["A1", "A2", "A3", "A4", "A5", "STABLE", "UNKNOWN"])
    fields["probe_completion"] = enum(COMPLETION)
    fields["probe_readiness"] = enum(READINESS)
    w["tools"][0]["function"]["parameters"]["required"] = list(fields)
    w["messages"][0]["content"] = (
        "You are the organization strategy agent. Assess the project facts and cite receipts. State the two independent statuses for the probed obligation. "
        "Select all commitments owed for your package, including blocked work. Choose one feasible route and its organizational change only if it adds a distinct product. "
        "An unresolved upstream delivery obligation remains even when an inspection must come first. Distinguish sustained repair failure A1, dependency A2, conflict A3, verification A4, delivery stall A5, stable progress and insufficient evidence. "
        "Report your reason and reevaluation trigger. Return exactly one activate_organization call."
    )
    w["messages"][1]["content"] = compact(
        dict(
            project_graph=project,
            obligation_graph=nodes,
            organization_graph=base.organization(row["graph"]),
            routes=menu,
            patches={k: base.make_patch(row, k) for k in old.options(row)},
            probed_obligation=row["probe_id"],
            available_tokens=row["available_tokens"],
        )
    )
    return w


def parse(row, body):
    calls = body["choices"][0]["message"].get("tool_calls") or []
    if len(calls) != 1 or calls[0]["function"]["name"] != "activate_organization":
        raise ValueError("Expected one organization call")
    d = json.loads(calls[0]["function"]["arguments"])
    Draft202012Validator(request(row)["tools"][0]["function"]["parameters"]).validate(d)
    return d


def compile_decision(row, d):
    project, nodes, routes = build(row)
    route = routes[d["route"]]
    focus = route["immediate"].split("/")[0]
    key = route["option"]
    patch = base.make_patch(row, "K" if key == "WAIT" else key)
    graph = base.apply_patch(row, patch)
    here = {k for k in nodes if k.startswith(focus + "/")}
    required = {
        k
        for k in here
        if nodes[k]["source"]
        in ("explicit_contract_gap", "observed_failing_target", "unvalidated_conflicted_merge")
        and nodes[k]["completion"] in ("UNSATISFIED", "STALE")
    }
    for e in project["dependencies"]:
        if e["consumer"] != focus:
            continue
        if (
            e["artifact_state"] in ("unknown", "absent")
            and e["completion_record"] == "missing_or_stale"
        ):
            required.add(f"{focus}/dependency/{e['producer']}/CURRENT_HANDOFF")
        elif e["artifact_state"] == "validated":
            required.add(f"{focus}/dependency/{e['producer']}/ADOPT_UPSTREAM_ARTIFACT")
    raw = set(d["current_obligations"])
    # Information gathering alone does not replace the open handoff obligation.
    effective = (raw & here) | required
    effect_links = []
    for operation in patch["operations"]:
        if operation[2] != focus:
            raise ValueError("Patch operation lacks an affected obligation")
        link = route["immediate"]
        if operation[0] == "D5":
            link = focus + "/independent_review"
        if link not in nodes:
            raise ValueError("Missing obligation for role change")
        effect_links.append({"operation": operation, "obligation": link})
    return dict(
        patch=patch,
        patch_links=effect_links,
        disposition={"K": "KEEP", "WAIT": "ABSTAIN"}.get(key, "CHANGE"),
        raw=sorted(raw),
        added=sorted(required - raw),
        effective=sorted(effective),
        graph_version=base.identity(graph),
        facts_version=base.identity(project),
        execution={
            **route,
            "subsequent": [
                dict(id=k, **nodes[k])
                for k in sorted(here - {route["immediate"]})
                if nodes[k]["completion"] != "SATISFIED"
            ],
            "completion_evidence": nodes[route["immediate"]]["completion_evidence"],
            "trigger": d["reconsider_after"],
        },
    )


def dispatch(row, compiled, live_graph):
    project, nodes, menu = build(row)
    r = compiled["execution"]
    k = r["option"] + "|" + r["immediate"]
    if (
        base.identity(project) != compiled["facts_version"]
        or base.identity(live_graph) != compiled["graph_version"]
        or base.apply_patch(row, compiled["patch"]) != live_graph
        or k not in menu
        or any(r[f] != v for f, v in menu[k].items())
        or nodes[r["immediate"]]["readiness"] != "READY"
    ):
        raise ValueError("Stale or unsupported action")
    return {f: r[f] for f in ("actor", "action", "package")}


def membership_patch(graph, op, member, *, fixed_size=True, successor=None):
    """Offline D0 schema. Activation and role reassignment have distinct operation names."""
    if op not in ("ADD_MEMBER", "RETIRE_MEMBER", "ACTIVATE_MEMBER"):
        raise ValueError("Not a membership operation")
    g = deepcopy(graph)
    roster = g["members"]
    if op == "ACTIVATE_MEMBER":
        if member not in roster:
            raise ValueError("Missing existing member")
        g.setdefault("inactive_members", []).remove(member)
        return g
    if fixed_size:
        raise ValueError("Two-worker deployment")
    if op == "ADD_MEMBER":
        if not member or member in roster or member in g.get("retired_members", []):
            raise ValueError("Member identity already used")
        roster.append(member)
    else:
        if member not in roster or successor == member or successor not in roster:
            raise ValueError("No eligible succession")
        for w in g["work"].values():
            owner = successor if w["owner"] == member else w["owner"]
            reviewer = successor if w["reviewer"] == member else w["reviewer"]
            if reviewer == owner:
                raise ValueError("Succession would break independent review")
            w.update(owner=owner, reviewer=reviewer)
        if any(member in (d["owner"], d["recipient"]) for d in g["duties"].values()):
            raise ValueError("Open duty needs explicit reassignment")
        g["collaboration"] = [edge for edge in g["collaboration"] if member not in edge[1:]]
        if member in g.get("inactive_members", []):
            g["inactive_members"].remove(member)
        roster.remove(member)
        g.setdefault("retired_members", []).append(member)
    return g
