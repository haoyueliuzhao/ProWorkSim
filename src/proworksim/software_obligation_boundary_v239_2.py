"""Bind a single executable route while keeping observed requirements separate from future checks."""

import json
from jsonschema import Draft202012Validator
from . import software_organization_contract_v239 as base
from .software_context_builder_v230 import compact
from .software_stage_response_v236 import enum, options
from .software_structured_policy_v237 import arr, obj

READINESS_GAPS = {
    "complete_current_code_or_evidence": "complete_package",
    "independent_current_review": "independent_review",
    "evidence_version_differs_from_final_tree_revalidate": "verify_integrated_version",
    "assign_verification": "assign_verifier",
}


def snapshot(row):
    tasks = base.state(row)
    eid, last = list(row["evidence"].items())[-1]
    for key, task in tasks.items():
        task["source"] = "workflow_successor"
        if task["status"] == "DONE":
            task["source"] = "satisfied"
        elif task["status"] == "UNKNOWN":
            task["source"] = "unobserved"
        elif base.ready(tasks, key):
            task["source"] = "present_work"
    for p in row["targets"]:

        def mark(action, source, actor="owner"):
            k = p + "/" + action
            if k not in tasks:
                tasks[k] = dict(
                    action=action,
                    package=p,
                    status="OPEN",
                    requires=[],
                    evidence=[eid],
                    actor=actor,
                )
            tasks[k]["source"] = source

        if last["operation"] == "delivery_readiness":
            pkg = next((v for v in last.get("packages", []) if v["task_id"] == p), {})
            for gap in pkg.get("missing", []):
                if gap in READINESS_GAPS:
                    mark(READINESS_GAPS[gap], "explicit_contract_gap")
            test = last.get("public_test") or {}
            if (
                test.get("source_reference")
                and test["source_reference"] == last.get("final_version")
                and test.get("executed")
                and test.get("passed") is False
            ):
                # A failed shared tree does not identify the guilty package. Permit inspection
                # of its failure and preserve all existing package-specific receipt gaps.
                mark("diagnose_failure", "failed_shared_tree", "diagnostician_or_owner")
                mark("repair_target", "failed_shared_tree")
                tasks[p + "/repair_target"].update(
                    status="BLOCKED", requires=[p + "/diagnose_failure"]
                )
        elif last.get("executed") and last.get("passed") is False:
            mark("repair_target", "observed_failing_target")
        elif last.get("conflicts"):
            mark("verify_integrated_version", "unvalidated_conflicted_merge")
    return tasks


def routes(row, tasks):
    table = {}
    for k, t in tasks.items():
        if t["action"] == "assign_verifier" or not base.ready(tasks, k):
            continue
        p = k.split("/")[0]
        for key, op in options(row).items():
            if key != "K":
                if op["task"] != p or t["action"] == "gather_evidence":
                    continue
                if op["op"] == "diagnosis" and t["action"] != "diagnose_failure":
                    continue
            patch = base.make_patch(row, key)
            graph = base.apply_patch(row, patch)
            role = t["actor"]
            work = graph["work"][t["package"]]
            if role == "diagnostician_or_owner":
                actor = graph["duties"].get(t["package"], {}).get("owner", work["owner"])
            elif role in ("owner", "reviewer"):
                actor = work[role]
            else:
                actor = role
            if actor not in graph["members"]:
                continue
            if t["action"] == "independent_review" and actor in row["work_status"].get(
                t["package"], {}
            ).get("authors", []):
                continue
            code = key + "|" + k
            table[code] = dict(
                option=key,
                immediate=k,
                actor=actor,
                package=t["package"],
                action=t["action"],
                added_product=base.PRODUCTS[op["op"]] if key != "K" else "none",
            )
            if key == "K" and t["action"] == "gather_evidence":
                table["WAIT|" + k] = {**table[code], "option": "WAIT"}
    return table


def obligation_choices(tasks):
    return [k for k, t in tasks.items() if t["status"] not in ("DONE", "UNKNOWN")]


def request(row):
    tasks = snapshot(row)
    menu = routes(row, tasks)
    wire = base.request(row)
    wire["tools"][0]["function"]["parameters"] = obj(
        dict(
            route=enum(list(menu)),
            current_obligations=arr(obligation_choices(tasks), 1),
            basis=arr(list(row["evidence"]), 1),
            reason={"type": "string", "minLength": 1},
            reconsider_after={"type": "string", "minLength": 1},
        )
    )
    view = dict(
        organization=base.organization(row["graph"]),
        available_tokens=row["available_tokens"],
        receipts=row["evidence"],
        obligations=tasks,
        routes=menu,
        patches={k: base.make_patch(row, k) for k in options(row)},
    )
    wire["messages"][0]["content"] = (
        "Choose one feasible organization and first-action route. Compare keeping current responsibilities with the additional artifact, recipient and cost of each change. "
        "Report the work already owed at this boundary, including an established requirement that must wait for another. A workflow successor alone does not establish a present obligation. "
        "The shared-tree test alone does not locate a defect in a particular package. Cite the receipts that support your choice and identify when to reconsider. "
        "The controller binds the actor and product to your route. WAIT requests a missing observation. Emit one activate_organization call."
    )
    wire["messages"][1]["content"] = compact(view)
    return wire


def parse(row, body):
    calls = body["choices"][0]["message"].get("tool_calls") or []
    if len(calls) != 1 or calls[0]["function"]["name"] != "activate_organization":
        raise ValueError("Expected one organization call")
    d = json.loads(calls[0]["function"]["arguments"])
    Draft202012Validator(request(row)["tools"][0]["function"]["parameters"]).validate(d)
    return d


def compile_decision(row, d):
    tasks = snapshot(row)
    route = routes(row, tasks)[d["route"]]
    key = route["option"]
    patch = base.make_patch(row, "K" if key == "WAIT" else key)
    graph = base.apply_patch(row, patch)
    return dict(
        option=patch["option"],
        patch=patch,
        graph_version=base.identity(graph),
        disposition={"K": "KEEP", "WAIT": "ABSTAIN"}.get(key, "CHANGE"),
        execution={
            **route,
            "expected_delta": d["reason"],
            "receipt_version": base.identity(row["evidence"]),
            "status_version": base.identity(row["work_status"]),
            "reconsider_after": d["reconsider_after"],
        },
    )


def dispatch(row, compiled, live_graph):
    plan = compiled["execution"]
    if (
        base.identity(live_graph) != compiled["graph_version"]
        or base.identity(row["evidence"]) != plan["receipt_version"]
        or base.identity(row["work_status"]) != plan["status_version"]
    ):
        raise ValueError("Decision boundary changed")
    expected = routes(row, snapshot(row)).get(plan["option"] + "|" + plan["immediate"])
    if (
        not expected
        or any(plan[k] != v for k, v in expected.items())
        or base.apply_patch(row, compiled["patch"]) != live_graph
    ):
        raise ValueError("Unsupported work dispatch")
    return {k: plan[k] for k in ("action", "actor", "package")}
