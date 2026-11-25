"""Prompt-only clarification for the v240 three-graph controller."""

from .software_three_graph_v240 import request as original_request

ADDITION = (
    " Before returning current_obligations, check each item against the current receipt and version. "
    "Include outstanding commitments for the selected work package whose completion is UNSATISFIED or STALE, "
    "including commitments that are BLOCKED. Readiness tells you what can start first; it does not decide what is owed. "
    "Leave SATISFIED items out. Keep UNKNOWN items and checks that depend on a future artifact in the subsequent plan "
    "until a receipt establishes they are due. An evidence lookup can be the immediate action without making every possible "
    "outcome of that lookup a current obligation. Check both for missing commitments and for premature additions."
)


def request(row):
    wire = original_request(row)
    wire["messages"][0]["content"] += ADDITION
    return wire
