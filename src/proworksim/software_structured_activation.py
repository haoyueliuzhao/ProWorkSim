"""Activation boundary for an OSA proposal when the only observations are unexecuted tests."""

from copy import deepcopy


def executable_decision(row, proposal, target):
    if target["disposition"] != "CHANGE":
        return proposal, target, None
    receipts = row["evidence"].values()
    only_unexecuted_tests = bool(receipts) and all(
        r.get("operation") in ("run_tests", "run_patch_review_tests")
        and r.get("executed") is False
        and r.get("passed") is None
        and not r.get("counts")
        and not r.get("failed_cases")
        for r in receipts
    )
    status_known = any(
        s.get("completed") is not None or s.get("authors") for s in row["work_status"].values()
    )
    if not only_unexecuted_tests or status_known:
        return proposal, target, None
    effective = deepcopy(proposal)
    effective["decision"].update(
        result="ABSTAIN",
        next_step="inspect_evidence",
        missing_evidence="current_test",
        reconsider_on="new_test_result",
    )
    return (
        effective,
        dict(graph=row["graph"], dimensions=[], schedule=[], option="K", disposition="ABSTAIN"),
        "test_not_executed_and_work_status_unknown",
    )
