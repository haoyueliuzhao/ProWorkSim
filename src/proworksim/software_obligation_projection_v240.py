"""Preserve the OSA's complete plan, but only promote evidence-backed outstanding items."""

from . import software_three_graph_v240 as contract


def compile_decision(row, proposal):
    result = contract.compile_decision(row, proposal)
    _, nodes, _ = contract.build(row)
    reported = result["effective"]
    established = [k for k in reported if nodes[k]["completion"] in ("UNSATISFIED", "STALE")]
    unresolved = [k for k in reported if k not in established]
    # Do not change actor, route, patch, prerequisite graph or the completion evidence.
    return {
        **result,
        "previous_effective": reported,
        "effective": established,
        "conditional_or_unknown": unresolved,
    }
