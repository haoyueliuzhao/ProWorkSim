"""Evidence-bound comparison of complete plans. Only the existing native menu can mutate the graph."""

from copy import deepcopy
import json
from jsonschema import Draft202012Validator
from .software_context_builder_v230 import compact
from .software_intervention_prompt_v236_2 import INTERVENTION_PROMPT
from .software_stage_response_v236 import options, reservation, enum, PHASES, STEPS

DIMENSIONS = {
    "D1": "work ownership and partition",
    "D2": "functional duties",
    "D3": "communication edges",
    "D4": "package dependencies",
    "D5": "independent reviewer",
    "D6": "integration and delivery authority",
    "D7": "budget and scheduled opportunities",
}
OBLIGATIONS = [
    "diagnose_failure",
    "repair_target",
    "release_upstream",
    "adopt_upstream",
    "resolve_conflict",
    "verify_integrated_version",
    "complete_package",
    "independent_review",
    "fix_tree",
    "submit",
    "continue_progress",
    "gather_evidence",
]
PRODUCTS = [
    "none",
    "independent_diagnosis",
    "review_evidence",
    "implemented_patch",
    "upstream_artifact",
    "resolved_merge",
    "fixed_candidate",
    "legal_delivery",
    "observed_progress",
    "new_evidence",
]
CHECKS = [
    "inspect_evidence",
    "public_test",
    "dependency_receipt",
    "conflict_retest",
    "independent_patch_review",
    "submission_receipt",
]


def obj(fields):
    return {
        "type": "object",
        "properties": fields,
        "required": list(fields),
        "additionalProperties": False,
    }


def arr(values, minimum=0):
    return {"type": "array", "items": enum(values), "minItems": minimum, "uniqueItems": True}


def change_plan(row, option):
    graph = deepcopy(row["graph"])
    op = options(row)[option]
    if op["op"] == "keep":
        return graph, [], []
    task = op["task"]
    w = graph["work"][task]
    before = w.copy()
    peer = op["assignee"]
    owner = w["owner"]
    if row["work_status"][task]["completed"] or peer not in graph["members"] or owner == peer:
        raise ValueError("Ineligible responsibility change")
    if op["op"] == "diagnosis":
        graph["duties"][task] = {
            "owner": peer,
            "recipient": owner,
            "status": "pending",
            "scope": "independent diagnosis and evidence handoff",
        }
    elif op["op"] == "transfer_unstarted":
        if row["work_status"][task]["authors"]:
            raise ValueError("Authored work cannot transfer")
        w["owner"], w["reviewer"] = peer, owner
    elif op["op"] == "verify":
        if peer in row["work_status"][task]["authors"]:
            raise ValueError("Self review")
        w["reviewer"] = peer
    elif op["op"] == "release_diagnosis":
        del graph["duties"][task]
    else:
        raise ValueError("Unsupported native transition")
    for edge in ([task, owner, peer], [task, peer, owner]):
        if edge not in graph["collaboration"]:
            graph["collaboration"].append(edge)
    changed = []
    if before["owner"] != w["owner"]:
        changed.append("D1")
    if graph["duties"] != row["graph"]["duties"]:
        changed.append("D2")
    if graph["collaboration"] != row["graph"]["collaboration"]:
        changed.append("D3")
    if before["reviewer"] != w["reviewer"]:
        changed.append("D5")
    # D7 is a prospective scheduling effect; worker receipts measure realization separately.
    return (
        graph,
        changed,
        ["D7"] if op["op"] in ("diagnosis", "verify", "transfer_unstarted") else [],
    )


def wire(row):
    opts = options(row)
    alternatives = [k for k in opts if k != "K"]
    refs = list(row["evidence"])
    advertised = {}
    for key, op in opts.items():
        _, dims, sched = change_plan(row, key)
        advertised[key] = {
            **op,
            "graph_delta": dims,
            "scheduling_effect": sched,
            "capacity_reserve": reservation(op["op"]) if key != "K" else {"controller": 6144},
        }
    members = row["graph"]["members"]
    fields = obj(
        {
            "assessment": obj(
                {
                    "situation": enum(["A1", "A2", "A3", "A4", "A5", "STABLE", "UNKNOWN"]),
                    "status": enum(["open", "progressing", "uncertain"]),
                    "stage": enum(PHASES),
                    "evidence": arr(refs, 1),
                }
            ),
            "work": obj({"package": enum(row["targets"]), "obligations": arr(OBLIGATIONS, 1)}),
            "keep": obj(
                {
                    "owner": enum(members),
                    "verifier": enum(members + ["none"]),
                    "next_step": enum(STEPS + ["inspect_evidence"]),
                    "product": enum(PRODUCTS[1:]),
                    "verification": enum(CHECKS),
                    "feasible": {"type": "boolean"},
                    "progress": arr(refs),
                    "blockers": arr(refs),
                    "risk": enum(
                        ["delay", "repeat_failure", "coordination", "unverified", "low", "unknown"]
                    ),
                    "worker_turns": {"type": "integer", "minimum": 0, "maximum": 512},
                    "token_estimate": enum(["under_100k", "100k_to_500k", "over_500k", "unknown"]),
                }
            ),
            "alternative": obj(
                {
                    "option": enum(alternatives or ["NONE"]),
                    "graph_dimensions": arr(list(DIMENSIONS)),
                    "assignee": enum(members + ["none"]),
                    "additional_product": enum(PRODUCTS),
                    "consumer": enum(members + ["none"]),
                    "handoff": enum(["none", "one", "multiple"]),
                    "verification": enum(CHECKS + ["none"]),
                    "cost": enum(["low", "medium", "high", "unknown", "none"]),
                    "risk": enum(
                        [
                            "delay",
                            "repeat_failure",
                            "coordination",
                            "unverified",
                            "low",
                            "unknown",
                            "none",
                        ]
                    ),
                }
            ),
            "decision": obj(
                {
                    "result": enum(["KEEP", "CHANGE", "ABSTAIN"]),
                    "basis": arr(refs, 1),
                    "next_step": enum(STEPS + ["inspect_evidence"]),
                    "reconsider_on": enum(
                        [
                            "new_test_result",
                            "upstream_version",
                            "merge_result",
                            "review_receipt",
                            "delivery_receipt",
                            "new_owner_evidence",
                        ]
                    ),
                    "missing_evidence": enum(
                        [
                            "none",
                            "current_test",
                            "work_status",
                            "dependency_receipt",
                            "review_receipt",
                            "delivery_readiness",
                            "diagnostic_finding",
                        ]
                    ),
                }
            ),
        }
    )
    instructions = (
        "You control organization, not code or scoring. Two workers, immutable task, identity, authorship, history, permissions, independent review and team budget. "
        "Read evidence, identify phase and unmet work, assess the existing owner path, construct the smallest legal alternative, compare and decide. "
        "A1 repeated failure on versions; A2 dependency blocked; A3 merge conflict/regression; A4 outstanding verification; A5 delivery repeatedly ready on the same version with no submission; STABLE ordinary progress. "
        "Use KEEP when the existing assignment fits, CHANGE for a feasible additional verifiable product and concrete obstacle, ABSTAIN only when specific information is missing. For ABSTAIN gather evidence and give a trigger. "
        "Complete both plan records even if you choose KEEP. Where no alternative is offered use NONE/none and empty dimensions. Copy only actual graph_delta into graph_dimensions; scheduling_effect is separate. "
        "Bind owner/verifier to the named package; compare capacity reservations with remaining tokens and estimate actual work separately. Emit exactly one function call, no prose."
        + INTERVENTION_PROMPT
    )
    view = dict(
        graph=row["graph"],
        package_status=row["work_status"],
        observations=row["evidence"],
        team_tokens_remaining=row["available_tokens"],
        dimensions=DIMENSIONS,
        legal_options=advertised,
    )
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
                    "description": "Compare and select a whole bounded organization plan",
                    "parameters": fields,
                },
            }
        ],
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": compact(view)},
        ],
    )


def validate(row, body):
    calls = body["choices"][0]["message"].get("tool_calls") or []
    if len(calls) != 1 or calls[0]["function"]["name"] != "activate_organization":
        raise ValueError("expected one controller call")
    proposal = json.loads(calls[0]["function"]["arguments"])
    err = next(
        Draft202012Validator(wire(row)["tools"][0]["function"]["parameters"]).iter_errors(proposal),
        None,
    )
    if err:
        raise ValueError("schema: " + err.json_path + " " + err.validator)
    a = proposal["alternative"]
    d = proposal["decision"]
    keep = proposal["keep"]
    pkg = proposal["work"]["package"]
    w = row["graph"]["work"][pkg]
    if keep["owner"] != w["owner"] or keep["verifier"] != (w["reviewer"] or "none"):
        raise ValueError("wrong incumbent roles")
    if a["option"] == "NONE":
        if a["graph_dimensions"] or any(
            a[k] != "none"
            for k in (
                "assignee",
                "consumer",
                "additional_product",
                "handoff",
                "verification",
                "cost",
                "risk",
            )
        ):
            raise ValueError("phantom alternative")
        alt_graph = row["graph"]
        dims = []
        sched = []
    else:
        op = options(row)[a["option"]]
        alt_graph, dims, sched = change_plan(row, a["option"])
        if (
            op["task"] != pkg
            or a["assignee"] != op["assignee"]
            or set(a["graph_dimensions"]) != set(dims)
        ):
            raise ValueError("alternative does not match legal graph")
        if (
            a["additional_product"] == "none"
            or a["consumer"] == "none"
            or a["verification"] == "none"
        ):
            raise ValueError("missing verifiable additional product")
        if op["op"] == "diagnosis" and (
            a["additional_product"] != "independent_diagnosis"
            or a["consumer"] != w["owner"]
            or a["handoff"] == "none"
        ):
            raise ValueError("diagnostic handoff identity")
    if d["result"] == "CHANGE" and (a["option"] == "NONE" or not keep["blockers"]):
        raise ValueError("change lacks alternative or blocking evidence")
    if d["result"] == "ABSTAIN" and (
        d["missing_evidence"] == "none"
        or d["next_step"] != "inspect_evidence"
        and d["next_step"] != "report_blocker"
        and d["next_step"] != "investigate_failure"
    ):
        raise ValueError("abstention lacks evidence acquisition")
    if d["result"] != "ABSTAIN" and d["missing_evidence"] != "none":
        raise ValueError("unresolved evidence outside abstention")
    return proposal, dict(
        graph=alt_graph if d["result"] == "CHANGE" else row["graph"],
        dimensions=dims if d["result"] == "CHANGE" else [],
        schedule=sched if d["result"] == "CHANGE" else [],
        option=a["option"] if d["result"] == "CHANGE" else "K",
        disposition=d["result"],
    )
