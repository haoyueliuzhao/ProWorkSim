"""Read-only evaluation boundaries, separate from worker and world authority.

A failed assessment is not necessarily a failed worker. ``status`` identifies
what was observed; ``passed`` is retained solely as a finite-contract predicate.
No assessment result grants a permission or changes an institutional decision.
"""

import copy

STATUSES = (
    "pass",
    "content_failure",
    "structure_failure",
    "source_unavailable",
    "unassessed",
    "evaluator_error",
)
# This precedence summarizes simultaneous findings, never erases component results.
PRECEDENCE = (
    "evaluator_error",
    "structure_failure",
    "content_failure",
    "source_unavailable",
    "unassessed",
    "pass",
)


class EvaluationInputError(ValueError):
    """A recognized input condition, classified where its origin is known."""

    def __init__(self, status, reason):
        if status not in STATUSES or status in {"pass", "evaluator_error"}:
            raise ValueError("Invalid evaluation input status")
        self.status = status
        super().__init__(reason)


def combined_status(statuses):
    values = set(statuses)
    return next((status for status in PRECEDENCE if status in values), "unassessed")


def evaluator_fault(exc, *, boundary):
    return {
        "status": "evaluator_error",
        "passed": False,
        "reason": str(exc),
        "exception_type": type(exc).__name__,
        "boundary": boundary,
        "attribution": "evaluation_implementation_or_unclassified_internal_failure",
    }


def evaluate_submission(store, state, item, submission):
    """Contain unforeseen implementation failures without blaming the worker.

    Recognized malformed deliveries and unavailable sources are returned by the
    input boundaries in the domain evaluator. Only this explicit outer boundary
    catches arbitrary Exception; process cancellation and system exits propagate.
    """
    from .domains import work_product

    context = {}
    try:
        return work_product.evaluate_submission(store, state, item, submission, _context=context)
    except Exception as exc:
        return {
            "submission_id": submission.get("submission_id"),
            "evaluator_version": work_product.EVALUATOR_VERSION,
            **evaluator_fault(exc, boundary="submission_evaluator"),
            "checks": copy.deepcopy(context.get("checks", [])),
            "errors": copy.deepcopy(context.get("errors", [])),
            "read_set": copy.deepcopy(context.get("read_set", [])),
            "interrupted_check": copy.deepcopy(context.get("active_check")),
            "scope": "finite_json_xlsx_content_contract",
            "institutional_review": copy.deepcopy(submission.get("review")),
        }
