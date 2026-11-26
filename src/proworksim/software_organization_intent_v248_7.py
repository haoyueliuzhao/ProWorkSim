"""P2.1 OSA request builder and execution interface for the next experiment."""

from . import software_organization_intent_v248_6 as p2
from .software_organization_intent_v248_6 import apply, compile_intent, public_state, snapshot

__all__ = ["apply", "compile_intent", "public_state", "snapshot", "wire"]

DIMENSION_GUIDE = """When comparing the offered candidates with KEEP, use the dimensions relevant to the observed problem. A candidate may combine several.
D0 — Team membership: who is active, joins, pauses, resumes or retires.
D1 — Role: what duty a member takes on, such as diagnosing a failure.
D2 — Work allocation: who owns a specific work package and how packages are split or merged.
D3 — Collaboration: who shares which findings or artifacts with whom.
D4 — Dependencies: which work package needs a result from another before it can proceed.
D5 — Verification: who independently checks a particular result or patch version.
D6 — Integration and delivery: who brings accepted changes together and who is responsible for delivery under the current contract.
D7 — Scheduling and resources: which member acts next and how work is prioritized within the shared budget.
Use these distinctions to explain the relevant effect of your choice in the existing reason field. A dimension-by-dimension report is unnecessary."""


def wire(state):
    request = p2.wire(state)
    request["messages"][0]["content"] += "\n\n" + DIMENSION_GUIDE
    return request
