"""Receipt-only decision surface and dry-run validation for existing local graph transforms."""

from copy import deepcopy
import json
from .software_graph_execution_v230 import CALL_BOUND
from .software_context_builder_v230 import compact

CATEGORIES = ["A1", "A2", "A3", "A4", "STABLE", "UNKNOWN"]
PHASES = ["localization", "implementation", "diagnosis", "integration", "verification", "delivery"]
STEPS = [
    "investigate_failure",
    "finish_upstream",
    "adopt_upstream",
    "resolve_merge",
    "retest_integrated_tree",
    "complete_package",
    "review_current_version",
    "fix_and_submit",
    "continue_current_work",
    "report_blocker",
]
DESCRIPTION = {
    "keep": "Existing owner and reviewer continue their duties, including tests, review and delivery. No new handoff.",
    "diagnosis": "Add an independent evidence-gathering and handoff duty; current owner and reviewer keep their existing work.",
    "verify": "Designate the specified independent reviewer for the remaining package.",
    "transfer_unstarted": "Move unstarted implementation to the assignee; previous owner takes review.",
    "release_diagnosis": "Remove the existing extra diagnostic duty.",
}


def reservation(op):
    # Shared envelope, conditional capacity, not predicted use. Four diagnosis turns
    # plus the three ordinary work phases cover the v232.7 seven-turn admission.
    return {
        "controller": 6144,
        "diagnosis": 4 * CALL_BOUND if op == "diagnosis" else 0,
        "implementation": CALL_BOUND,
        "verification": CALL_BOUND,
        "delivery": CALL_BOUND,
    }


def options(row):
    return {
        k: v
        for k, v in row["options"].items()
        if k == "K" or sum(reservation(v["op"]).values()) <= row["available_tokens"]
    }


def enum(values):
    return {"type": "string", "enum": values}


def wire(row, condition):
    choices = options(row)
    props = {
        "situation": enum(CATEGORIES),
        "stage": enum(PHASES),
        "needs_new_responsibility": {"type": "boolean"},
        "option": enum(list(choices)),
        "package": enum(row["targets"]),
        "next_step": enum(STEPS),
        "evidence": {"type": "array", "items": enum(list(row["evidence"])), "minItems": 1},
        "reason": {"type": "string", "maxLength": 1200},
        "cost_and_check": {"type": "string", "maxLength": 700},
    }
    system = (
        "You are the organization controller for two coding workers. Assess only the attached member-visible evidence. "
        "A1 = same repair repeatedly fails; A2 = upstream dependency blocks work; A3 = merge conflict or post-integration regression; A4 = outstanding verification or review; STABLE = normal progress; UNKNOWN = insufficient evidence. "
        "Return one activate_organization call. Name the remaining package, a feasible next operation, all observations needed to support the classification (cite both runs for repeated failure), and what the next verification and coordination will cost. An uncollected or absent test is not a pass."
    )
    if condition == "staged":
        system += (
            " First identify the situation and phase. Then identify the concrete outstanding obligation and whether the current roles already cover it. "
            "Finally decide whether new responsibility is needed. Bind any change to this unfinished package and the extra work, handoff and verification it requires. Evaluate continuing under the current assignments on equal terms."
        )
    view = {
        "organization": row["graph"],
        "package_status": row["work_status"],
        "observed": row["evidence"],
        "remaining_team_tokens": row["available_tokens"],
        "options": {
            k: {
                **v,
                "effect": DESCRIPTION[v["op"]],
                "activation_reserve": reservation(v["op"]) if k != "K" else {"controller": 6144},
            }
            for k, v in choices.items()
        },
    }
    return {
        "model": "deepseek-flash",
        "thinking": {"type": "disabled"},
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": 1024,
        "stream": False,
        "tool_choice": "auto",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "activate_organization",
                    "description": "Return one evidence-bound organization decision.",
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": list(props),
                        "additionalProperties": False,
                    },
                },
            }
        ],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": compact(view)},
        ],
    }


def validate(row, body):
    calls = body["choices"][0]["message"].get("tool_calls") or []
    if len(calls) != 1 or calls[0]["function"]["name"] != "activate_organization":
        raise ValueError("Expected one decision")
    d = json.loads(calls[0]["function"]["arguments"])
    props = wire(row, "direct")["tools"][0]["function"]["parameters"]["properties"]
    if not isinstance(d, dict) or set(d) != set(props):
        raise ValueError("Invalid decision fields")
    for k, p in props.items():
        if "enum" in p and d[k] not in p["enum"]:
            raise ValueError("Unknown " + k)
    if type(d["needs_new_responsibility"]) is not bool or d["needs_new_responsibility"] != (
        d["option"] != "K"
    ):
        raise ValueError("Action and change judgement disagree")
    if (
        not isinstance(d["evidence"], list)
        or not d["evidence"]
        or any(x not in row["evidence"] for x in d["evidence"])
    ):
        raise ValueError("Unknown evidence")
    for k in ("reason", "cost_and_check"):
        if not isinstance(d[k], str) or not 0 < len(d[k].strip()) <= props[k]["maxLength"]:
            raise ValueError("Invalid explanation")
    graph = deepcopy(row["graph"])
    op = options(row)[d["option"]]
    if op["op"] != "keep":
        tid = op["task"]
        peer = op["assignee"]
        task = graph["work"][tid]
        owner = task["owner"]
        if tid != d["package"] or peer not in graph["members"] or peer == owner:
            raise ValueError("Invalid work binding")
        if op["op"] == "diagnosis":
            graph["duties"][tid] = {
                "owner": peer,
                "recipient": owner,
                "status": "pending",
                "scope": "independent diagnosis and evidence handoff",
            }
        elif op["op"] == "transfer_unstarted":
            task["owner"], task["reviewer"] = peer, owner
        elif op["op"] == "verify":
            task["reviewer"] = peer
        elif op["op"] == "release_diagnosis":
            del graph["duties"][tid]
        else:
            raise ValueError("Unimplemented operation")
        for edge in ([tid, owner, peer], [tid, peer, owner]):
            if edge not in graph["collaboration"]:
                graph["collaboration"].append(edge)
    return d, graph


# Pre-run reference. A4 and stable are the reviewed no-change denominator.
# Multiple actions/stages can be appropriate; A1 does not mandate intervention.
RULES = {
    "A1": (
        ["diagnosis", "localization", "implementation"],
        ["investigate_failure", "report_blocker"],
    ),
    "A2": (
        ["implementation", "integration"],
        ["finish_upstream", "adopt_upstream", "report_blocker"],
    ),
    "A3": (["integration"], ["resolve_merge", "retest_integrated_tree"]),
    "A4": (
        ["verification", "delivery"],
        ["complete_package", "review_current_version", "fix_and_submit"],
    ),
    "STABLE": (
        ["implementation", "integration", "verification", "delivery"],
        ["continue_current_work", "review_current_version", "fix_and_submit", "complete_package"],
    ),
}


def grade(row, d):
    kind = row["reference_type"]
    phases, steps = RULES[kind]
    op = options(row)[d["option"]]["op"]
    allowed = {
        "A1": {"keep", "diagnosis"},
        "A2": {"keep", "transfer_unstarted"},
        "A3": {"keep"},
        "A4": {"keep"},
        "STABLE": {"keep"},
    }
    cited = [row["evidence"][key] for key in set(d["evidence"])]
    if kind == "A1":
        failures = [e for e in cited if e.get("failed_cases") and e.get("reference")]
        warranted = any(
            a["reference"] != b["reference"] and set(a["failed_cases"]) & set(b["failed_cases"])
            for a in failures
            for b in failures
        )
    elif kind == "A2":
        warranted = any(e.get("gaps") for e in cited)
    elif kind == "A3":
        warranted = any(e.get("conflicts") for e in cited)
    elif kind == "A4":
        warranted = any(
            "independent_current_review" in p["missing"]
            for e in cited
            for p in e.get("packages", [])
        )
    else:
        warranted = any(e.get("passed") is True and e.get("executed") is True for e in cited)
    return dict(
        supported_identification=bool(warranted and d["situation"] == kind),
        correct_situation=d["situation"] == kind,
        correct_phase=d["stage"] in phases,
        appropriate_action=op in allowed[kind] and d["next_step"] in steps,
        unnecessary_change=op != "keep" if kind in ("A4", "STABLE") else None,
    )
