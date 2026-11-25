"""An opt-in commitment-versus-action prompt for the unchanged three-graph protocol."""

from .software_three_graph_v240 import request as original_request

COMMITMENT_GUIDANCE = (
    " Fill the fields separately. For route, choose what the worker should do first. "
    "For current_obligations, report the outcomes still owed in the chosen package. "
    "For each ID, check its own completion field and the receipt that establishes the debt: "
    "include UNSATISFIED or STALE commitments even if BLOCKED; leave SATISFIED and UNKNOWN candidates out. "
    "Ask what would still be owed immediately after a lookup. Put the lookup in route only when it serves that "
    "outcome; list it also as a commitment only if producing the evidence is itself explicitly owed. "
    "A ready route, a missing receipt, and an unchosen alternative do not by themselves establish another debt. "
    "Keep a shared failure at its evidenced scope; preserve the chosen package's recorded gaps. "
    "Copy probe_completion and probe_readiness literally from the node named by probed_obligation, even if the route uses another node."
)
SUBMISSION = (
    " Submit the arguments through exactly one activate_organization tool call. "
    "A JSON object written in the assistant message does not execute the plan."
)


def request(row):
    w = original_request(row)
    system = w["messages"][0]["content"]
    ending = " Return exactly one activate_organization call."
    if not system.endswith(ending):
        raise ValueError("Source contract changed")
    w["messages"][0]["content"] = system.removesuffix(ending) + COMMITMENT_GUIDANCE + SUBMISSION
    return w
