"""Keep package requirements with their receipts, independently of the first executable action."""

import json
from jsonschema import Draft202012Validator
from . import software_obligation_boundary_v239_2 as old
from .software_context_builder_v230 import compact
from .software_stage_response_v236 import enum
from .software_structured_policy_v237 import arr


def snapshot(row):
    tasks = old.snapshot(row)
    eid, last = list(row["evidence"].items())[-1]
    for p in row["targets"]:

        def add_check():
            tasks[p + "/gather_evidence"] = dict(
                package=p,
                action="gather_evidence",
                status="READY",
                requires=[],
                evidence=[eid],
                actor="owner",
                source="inspect_reference",
            )

        if any(g["kind"] == "upstream_not_current" for g in last.get("gaps", [])):
            add_check()
        if last.get("executed") and last.get("passed") is False and not last.get("failed_cases"):
            add_check()
            tasks[p + "/repair_target"]["source"] = "conditional_on_failure_details"
        test = last.get("public_test") or {}
        if (
            test.get("executed")
            and test.get("passed") is False
            and test.get("source_reference")
            and test["source_reference"] == last.get("final_version")
            and p + "/diagnose_failure" in tasks
        ):
            # Failure in a shared tree cannot locate the guilty package. Retain its
            # completion obligation, but claiming completion needs package-specific support.
            gap = tasks.get(p + "/complete_package")
            if (
                gap
                and gap["status"] != "DONE"
                and not row["work_status"].get(p, {}).get("completed")
            ):
                gap.update(status="BLOCKED", requires=[p + "/diagnose_failure"])
            tasks[p + "/repair_target"]["source"] = "conditional_on_failure_localization"
    return tasks


def required(row, tasks, focus):
    """Only enforce explicit package gaps or concrete version-specific failures."""
    last = list(row["evidence"].values())[-1]
    keys = {
        k
        for k, t in tasks.items()
        if k.partition("/")[0] == focus
        and t["source"] in ("explicit_contract_gap", "unvalidated_conflicted_merge")
    }
    if (
        last.get("executed")
        and last.get("passed") is False
        and last.get("failed_cases")
        and last.get("reference")
    ):
        keys.add(focus + "/repair_target")
    return keys


def request(row):
    tasks = snapshot(row)
    routes = old.routes(row, tasks)
    w = old.request(row)
    props = w["tools"][0]["function"]["parameters"]["properties"]
    props["route"] = enum(list(routes))
    props["current_obligations"] = arr(old.obligation_choices(tasks), 1)
    w["messages"][0]["content"] += (
        " Select one work package through your route. Report its outstanding commitments even if another action must run first. "
        "Contract gaps, named failed tests and conflicted versions carry receipt-backed requirements; the ledger retains them through this decision. "
        "When a dependency revision is not current and its publication or inclusion is unclear, you can inspect its reference. "
        "Keep a shared test failure at tree scope until evidence identifies a responsible package."
    )
    w["messages"][1]["content"] = compact(
        dict(
            receipts=row["evidence"],
            organization=old.base.organization(row["graph"]),
            obligations=tasks,
            required_by_package={p: sorted(required(row, tasks, p)) for p in row["targets"]},
            routes=routes,
            patches={k: old.base.make_patch(row, k) for k in old.options(row)},
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
    tasks = snapshot(row)
    route = old.routes(row, tasks)[d["route"]]
    key = route["option"]
    patch = old.base.make_patch(row, "K" if key == "WAIT" else key)
    graph = old.base.apply_patch(row, patch)
    focus = route["immediate"].partition("/")[0]
    raw = set(d["current_obligations"])
    kept = {k for k in raw if k.partition("/")[0] == focus}
    mandatory = required(row, tasks, focus)
    return dict(
        option=patch["option"],
        patch=patch,
        graph_version=old.base.identity(graph),
        disposition={"K": "KEEP", "WAIT": "ABSTAIN"}.get(key, "CHANGE"),
        obligations=sorted(mandatory | kept),
        required_added=sorted(mandatory - kept),
        outside_focus=sorted(raw - kept),
        execution={
            **route,
            "receipt_version": old.base.identity(row["evidence"]),
            "status_version": old.base.identity(row["work_status"]),
            "reconsider_after": d["reconsider_after"],
            "reason": d["reason"],
        },
    )


def dispatch(row, compiled, live_graph):
    task = compiled["execution"]
    k = task["option"] + "|" + task["immediate"]
    active = old.routes(row, snapshot(row)).get(k)
    if (
        not active
        or any(task[f] != v for f, v in active.items())
        or old.base.identity(row["evidence"]) != task["receipt_version"]
        or old.base.identity(row["work_status"]) != task["status_version"]
        or old.base.identity(live_graph) != compiled["graph_version"]
        or old.base.apply_patch(row, compiled["patch"]) != live_graph
    ):
        raise ValueError("Dispatched action differs from the accepted live decision")
    return {f: task[f] for f in ("actor", "package", "action")}
