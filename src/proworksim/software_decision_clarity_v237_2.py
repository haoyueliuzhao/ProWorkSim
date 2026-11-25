"""Receipt-first decision language and a graph-bound actor/delta projection."""

from copy import deepcopy
import json

from jsonschema import Draft202012Validator

from .software_structured_policy_v237 import change_plan, options

PROMPT = """You decide how two coding workers divide work. Use only the supplied receipts, package status, graph and budget. Keep permissions, authorship, task and independent review intact. Return one activate_organization call.

1. Read the latest receipt in sequence with the earlier ones. Classify the situation: A1 repeated failure across versions (cite both tests); A2 blocked dependency; A3 integration conflict or regression; A4 outstanding verification; A5 repeatedly ready on the same version without submission; STABLE routine progress; UNKNOWN insufficient evidence.
2. Pick the affected package. In obligations list what the receipts show is due NOW. Ask: could a worker address this at this boundary, or does it first require an unpublished artifact, a different version or a future decision? Put contingent steps in later_checks. List coexisting explicit readiness gaps when applicable. Use continue_progress for ordinary progress.
3. Compare keeping the current roles with the smallest available change for that same package. For each, state the next product, who could use it, the evidence that would verify it and the extra coordination. A needed work product and a benefit from changing roles are separate judgments. If another assignment adds nothing, use additional_product=none. For a diagnostic duty that adds value, the product is independent_diagnosis for the incumbent owner.
4. KEEP when current roles can handle the next step. CHANGE requires a cited obstacle and a distinct verifiable additional product within the remaining budget. ABSTAIN when a specific missing observation prevents that choice: name it and select inspect_evidence. For a decided case put missing_evidence=none and use reconsider_on for a later trigger. Assess the hypothetical alternative even when keeping the current roles."""

BOUND_FIELDS = {
    "keep": ("owner", "verifier"),
    "alternative": ("graph_dimensions", "assignee", "consumer"),
}


def request(row, previous_wire, *, bound):
    w = previous_wire(row)
    w["messages"][0]["content"] = PROMPT
    fields = w["tools"][0]["function"]["parameters"]["properties"]
    fields["work"]["properties"]["obligations"]["description"] = (
        "Present-tense obligations supported by receipts for this package."
    )
    fields["work"]["properties"]["later_checks"]["description"] = (
        "Steps that become due only after a prerequisite or version change."
    )
    if bound:
        for section, names in BOUND_FIELDS.items():
            for key in names:
                del fields[section]["properties"][key]
                fields[section]["required"].remove(key)
        w["messages"][0]["content"] += (
            " The controller fills the owner, verifier, assignee, recipient and changed dimensions from the chosen package and menu. Do not emit these fields."
        )
    else:
        w["messages"][0]["content"] += (
            " Copy the owner and verifier from the selected package, and the assignee and graph_delta from the selected menu entry. Exclude the separate scheduling effect. For NONE use none/empty for all alternative fields."
        )
    return w


def bind(row, proposal):
    p = deepcopy(proposal)
    package = p["work"]["package"]
    incumbent = row["graph"]["work"][package]
    p["keep"].update(owner=incumbent["owner"], verifier=incumbent["reviewer"] or "none")
    a = p["alternative"]
    if a["option"] == "NONE":
        a.update(assignee="none", consumer="none", graph_dimensions=[])
    else:
        op = options(row)[a["option"]]
        if op["task"] != package:
            raise ValueError("Alternative targets a different package")
        _, dims, _ = change_plan(row, a["option"])
        a.update(
            assignee=op["assignee"],
            graph_dimensions=dims,
            consumer=incumbent["owner"] if a["additional_product"] != "none" else "none",
        )
    return p


def evaluate(row, body, previous_wire, previous_validate, *, bound):
    calls = body["choices"][0]["message"].get("tool_calls") or []
    if len(calls) != 1 or calls[0]["function"]["name"] != "activate_organization":
        raise ValueError("Expected a single activate_organization call")
    raw = json.loads(calls[0]["function"]["arguments"])
    schema = request(row, previous_wire, bound=bound)["tools"][0]["function"]["parameters"]
    error = next(Draft202012Validator(schema).iter_errors(raw), None)
    if error:
        raise ValueError(f"schema: {error.json_path} {error.validator}")
    if not bound:
        return previous_validate(row, body)
    expanded = deepcopy(body)
    expanded["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = json.dumps(
        bind(row, raw)
    )
    return previous_validate(row, expanded)
