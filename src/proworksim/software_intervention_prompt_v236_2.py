"""Candidate addition to the staged OSA system prompt."""

INTERVENTION_PROMPT = (
    " Compare two concrete paths before choosing. Under the current assignments, who can take the next "
    "useful action, and what evidence shows that path is working or stalled? Under a change, what "
    "additional work would the assigned member produce, who needs it, and what handoff would it add? "
    "An unfinished step can be normal progress. If the current people can complete it and no observed "
    "obstacle calls for another responsibility, keep their assignments and select the next step. "
    "If the current path is demonstrably stuck and a listed change offers a distinct feasible way forward, "
    "choose that change. Count only coordination added by the change."
)
