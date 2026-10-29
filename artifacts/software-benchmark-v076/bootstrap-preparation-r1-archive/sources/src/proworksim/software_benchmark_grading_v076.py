"""Apply the same v076 actual-capacity gate to official grading dispatch."""
from __future__ import annotations

from .software_benchmark_grading_v075 import factory as prior_factory


def factory(guard, *, primary_policy, authorization_ref=None):
    # A concrete shared v076 policy is mandatory; never silently fall back to
    # the superseded v075 quota-sum admission.
    if primary_policy.CONSTRAINTS.get("quota_sum_is_hard_concurrency_gate") is not False:
        raise ValueError("The v076 grading adapter requires actual-capacity admission")

    def authorize(operation, **identity):
        return guard("v076.run", **identity)

    return prior_factory(authorize, authorization_ref=authorization_ref,
                         primary_policy=primary_policy)
