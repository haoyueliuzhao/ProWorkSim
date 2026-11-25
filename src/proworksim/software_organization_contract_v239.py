"""A version-bound organization patch and a separate receipt-driven action graph."""

from copy import deepcopy
import hashlib
import json

from jsonschema import Draft202012Validator

from .software_context_builder_v230 import compact
from .software_stage_response_v236 import enum, options, reservation
from .software_structured_policy_v237 import arr, change_plan, obj

DIMENSIONS = dict(
    D0="membership",
    D1="roles",
    D2="work ownership",
    D3="collaboration",
    D4="dependency coordination",
    D5="verification",
    D6="integration and delivery",
    D7="resources and scheduling",
)
OPERATIONS = {
    "D0": ("ADD_MEMBER", "RETIRE_MEMBER"),
    "D1": ("ASSIGN_ROLE", "REVOKE_ROLE"),
    "D2": ("TRANSFER_OWNER", "ASSIGN_WORK", "SPLIT", "MERGE"),
    "D3": ("ADD_COLLABORATION", "REMOVE_COLLABORATION"),
    "D4": ("ADD_COORDINATION", "CHANGE_ORDER"),
    "D5": ("ASSIGN_VERIFIER",),
    "D6": ("ASSIGN_INTEGRATOR", "CHANGE_DELIVERY_OWNER"),
    "D7": ("RESERVE_BUDGET", "SET_PRIORITY"),
}
PRODUCTS = {
    "diagnosis": "independent_diagnosis",
    "verify": "independent_review",
    "transfer_unstarted": "owned_patch",
    "release_diagnosis": "released_capacity",
}
STAGES = ("OPEN", "READY", "BLOCKED", "IN_PROGRESS", "DONE", "STALE", "UNKNOWN")


def identity(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def organization(graph):
    """Stable node/edge projection; project dependencies stay in the project graph."""
    nodes = [["Member", m] for m in graph["members"]]
    edges = []

    def role(actor, label, pkg):
        if actor:
            nodes.append(["Role", label])
            edges.append(["HAS_ROLE", actor, label, pkg])

    for pkg, w in graph["work"].items():
        nodes.append(["WorkPackage", pkg])
        role(w["owner"], "owner", pkg)
        edges.append(["OWNS", w["owner"], pkg])
        if w["reviewer"]:
            role(w["reviewer"], "verifier", pkg)
            edges.append(["VERIFIES", w["reviewer"], pkg])
    for pkg, duty in graph["duties"].items():
        role(duty["owner"], "diagnostician", pkg)
        edges.extend(
            [
                ["CONTRIBUTES_TO", duty["owner"], pkg],
                ["HANDOFF", duty["owner"], duty["recipient"], pkg],
            ]
        )
    edges.extend(["COLLABORATES_WITH", a, b, p] for p, a, b in graph["collaboration"])
    return {
        "version": identity(graph),
        "nodes": sorted(set(map(tuple, nodes))),
        "edges": sorted(edges),
        "constraints": {
            "worker_count": 2,
            "independent_review": True,
            "execution_dimensions": list(DIMENSIONS),
        },
    }


def make_patch(row, key):
    graph = row["graph"]
    native, _, scheduling = change_plan(row, key)
    ops = []
    if key != "K":
        op = options(row)[key]
        p = op["task"]
        old, new = graph["work"][p], native["work"][p]
        if old["owner"] != new["owner"]:
            ops.append(["D2", "TRANSFER_OWNER", p, new["owner"]])
        if old["reviewer"] != new["reviewer"]:
            ops.append(["D5", "ASSIGN_VERIFIER", p, new["reviewer"]])
        if graph["duties"] != native["duties"]:
            if p in native["duties"]:
                ops.append(["D1", "ASSIGN_ROLE", p, deepcopy(native["duties"][p])])
            else:
                ops.append(["D1", "REVOKE_ROLE", p])
        ops.extend(
            ["D3", "ADD_COLLABORATION", *edge]
            for edge in native["collaboration"]
            if edge not in graph["collaboration"]
        )
    return {
        "base_graph_version": identity(graph),
        "option": key,
        "operations": ops,
        "capacity": reservation(options(row)[key]["op"]) if scheduling else {},
        "scheduling_effect": scheduling,
        "target_version": identity(native),
    }


def apply_patch(row, patch):
    if patch != make_patch(row, patch["option"]):
        raise ValueError("Patch is stale, unsupported, or differs from the authorized menu")
    g = deepcopy(row["graph"])
    for dim, op, p, *args in patch["operations"]:
        if op == "TRANSFER_OWNER":
            g["work"][p]["owner"] = args[0]
        elif op == "ASSIGN_VERIFIER":
            g["work"][p]["reviewer"] = args[0]
        elif op == "ASSIGN_ROLE":
            g["duties"][p] = deepcopy(args[0])
        elif op == "REVOKE_ROLE":
            del g["duties"][p]
        elif op == "ADD_COLLABORATION":
            g["collaboration"].append([p, *args])
        else:
            raise ValueError(f"Unsupported operation {dim}/{op}")
    if identity(g) != patch["target_version"] or len(g["members"]) != 2:
        raise ValueError("Invalid resulting graph")
    return g


def state(row):
    """Compile only evidence actually exposed to this observer; later receipts supersede earlier ones."""
    refs = row["evidence"]
    eid, last = list(refs.items())[-1]
    tasks = {}

    def put(p, action, status, requires=(), *, package=None, actor=None):
        key = f"{p}/{action}"
        tasks[key] = dict(
            action=action,
            package=package or p,
            status=status,
            requires=list(requires),
            evidence=[eid],
            actor=actor or "owner",
        )
        return key

    for p in row["targets"]:

        def node(action, status, requires=(), **kwargs):
            return put(p, action, status, requires, **kwargs)

        def chain(previous, *later):
            for action in later:
                actor = "reviewer" if action == "independent_review" else "owner"
                previous = node(action, "BLOCKED", [previous], actor=actor)

        if last["operation"] == "delivery_readiness":
            package = next((x for x in last.get("packages", []) if x["task_id"] == p), None)
            if not package:
                node("gather_evidence", "READY")
                continue
            gaps = package["missing"]
            done = node(
                "complete_package",
                "READY" if "complete_current_code_or_evidence" in gaps else "DONE",
            )
            stale = "evidence_version_differs_from_final_tree_revalidate" in gaps
            if stale:
                done = node("verify_integrated_version", "STALE", [done])
            review = node(
                "independent_review",
                ("OPEN" if tasks[done]["status"] == "DONE" else "BLOCKED")
                if "independent_current_review" in gaps
                else "DONE",
                [done],
                actor="reviewer",
            )
            fixed = node("fix_tree", "DONE" if last.get("fixed") else "BLOCKED", [review])
            node("submit", "READY" if last.get("ready") else "BLOCKED", [fixed])
        elif last.get("gaps"):
            for gap in last["gaps"]:
                dep = gap.get("task_id")
                if gap["kind"] == "upstream_not_current" and dep in row["graph"]["work"]:
                    released = node("release_upstream", "READY", package=dep)
                    chain(released, "adopt_upstream", "continue_progress")
                elif gap["kind"] == "upstream_patch_not_adopted":
                    adopted = node("adopt_upstream", "READY")
                    chain(adopted, "continue_progress")
            if not any(k.startswith(p + "/") for k in tasks):
                node("gather_evidence", "READY")
        elif last.get("conflicts"):
            merge = node("resolve_conflict", "READY", actor=row["observer"])
            chain(merge, "verify_integrated_version")
        elif last.get("executed") and last.get("passed") is False:
            diagnosis = node("diagnose_failure", "READY", actor="diagnostician_or_owner")
            tasks[diagnosis]["evidence"] = [
                k for k, v in refs.items() if v.get("executed") and v.get("passed") is False
            ]
            chain(diagnosis, "repair_target", "verify_integrated_version")
        elif last.get("executed") and last.get("passed") is True:
            node("verify_integrated_version", "DONE")
            node("continue_progress", "IN_PROGRESS")
        else:
            node("continue_progress", "UNKNOWN")
            node("gather_evidence", "READY")
    return tasks


def ready(tasks, k):
    v = tasks[k]
    return v["status"] in ("READY", "OPEN", "IN_PROGRESS", "STALE") and all(
        tasks[x]["status"] == "DONE" for x in v["requires"]
    )


def request(row):
    tasks = state(row)
    menu = {k: make_patch(row, k) for k in options(row)}
    executable = [k for k in tasks if ready(tasks, k)]
    fields = obj(
        {
            "choice": enum([*menu, "WAIT"]),
            "current_obligations": arr(list(tasks), 1),
            "immediate": enum(executable),
            "basis": arr(list(row["evidence"]), 1),
            "added_product": enum(["none", *PRODUCTS.values()]),
            "reason": {"type": "string", "minLength": 1, "maxLength": 650},
            "reconsider_after": {"type": "string", "minLength": 1, "maxLength": 240},
        }
    )
    view = {
        "organization": organization(row["graph"]),
        "receipts": row["evidence"],
        "task_graph": tasks,
        "budget": row["available_tokens"],
        "patches": menu,
        "diagnosis_recipient": "existing package owner",
    }
    return dict(
        model="deepseek-flash",
        thinking={"type": "disabled"},
        temperature=1.0,
        top_p=1.0,
        stream=False,
        max_tokens=2048,
        tool_choice="auto",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "activate_organization",
                    "description": "Select a versioned delta and one ready action",
                    "parameters": fields,
                },
            }
        ],
        messages=[
            {
                "role": "system",
                "content": "You are the organization controller. Identify the unmet obligations evidenced now for the affected package. Choose exactly one action whose prerequisites are satisfied. Compare the incumbent path with legal patches. Choose K to keep assignments, WAIT to obtain missing evidence, or one offered patch if it adds a feasible product needed beyond ordinary work. Give the reason, evidence IDs and reevaluation trigger. Use none for added_product on K/WAIT. A diagnostic role produces independent_diagnosis. A changed schedule alone does not require a changed organization. The controller resolves actors from roles after patching and waits for fresh receipts before releasing successors. Return exactly one tool call.",
            },
            {"role": "user", "content": compact(view)},
        ],
    )


def parse(row, body):
    calls = body["choices"][0]["message"].get("tool_calls") or []
    if len(calls) != 1 or calls[0]["function"]["name"] != "activate_organization":
        raise ValueError("Expected one organization decision")
    d = json.loads(calls[0]["function"]["arguments"])
    Draft202012Validator(request(row)["tools"][0]["function"]["parameters"]).validate(d)
    return d


def compile_decision(row, d):
    tasks = state(row)
    key = d["choice"]
    patch = make_patch(row, "K" if key == "WAIT" else key)
    g = apply_patch(row, patch)
    immediate = d["immediate"]
    if not ready(tasks, immediate):
        raise ValueError("Prerequisites unsatisfied")
    action = tasks[immediate]
    name = action["action"]
    if name == "gather_evidence" and key not in ("WAIT", "K"):
        raise ValueError("Insufficient evidence for activation")
    if key == "WAIT" and name != "gather_evidence":
        raise ValueError("Missing evidence request")
    if key in ("K", "WAIT"):
        if d["added_product"] != "none":
            raise ValueError("Unexpected incremental product")
    else:
        op = options(row)[key]
        if op["task"] != immediate.split("/")[0] or d["added_product"] != PRODUCTS[op["op"]]:
            raise ValueError("Change targets wrong work or product")
        if op["op"] == "diagnosis" and name != "diagnose_failure":
            raise ValueError("New diagnostic duty lacks a ready diagnosis")
    p = action["package"]
    w = g["work"][p]
    role = action["actor"]
    if role == "diagnostician_or_owner":
        actor = g["duties"].get(p, {}).get("owner", w["owner"])
    elif role in ("owner", "reviewer"):
        actor = w[role]
    else:
        actor = role
    if actor not in g["members"]:
        raise ValueError("Missing responsible member")
    if name == "independent_review" and actor in row["work_status"].get(p, {}).get("authors", []):
        raise ValueError("Self review")
    if any(tasks[k]["status"] in ("DONE", "UNKNOWN") for k in d["current_obligations"]):
        raise ValueError("Unsupported obligation status")
    return {
        "patch": patch,
        "graph_version": identity(g),
        "disposition": {"K": "KEEP", "WAIT": "ABSTAIN"}.get(key, "CHANGE"),
        "execution": {
            "action": immediate,
            "actor": actor,
            "package": p,
            "product": d["added_product"],
            "dependency_graph": tasks,
            "observation_version": identity(row["evidence"]),
            "reconsider_after": d["reconsider_after"],
        },
    }


def dispatch(row, compiled, live_graph, action):
    """Release only the single registered action against the unchanged, visible decision boundary."""
    plan = compiled["execution"]
    if (
        identity(live_graph) != compiled["graph_version"]
        or identity(row["evidence"]) != plan["observation_version"]
    ):
        raise ValueError("Graph or observation changed; reanalyze before dispatch")
    tasks = state(row)
    if (
        tasks != plan["dependency_graph"]
        or action != plan["action"]
        or not ready(tasks, action)
        or plan["actor"] not in live_graph["members"]
        or tuple(row["graph"]["members"]) != tuple(live_graph["members"])
    ):
        raise ValueError("Action not released")
    return {"actor": plan["actor"], "package": plan["package"], "action": tasks[action]["action"]}
