"""Explicit tool rejection facts and bounded attribution.

An unsuccessful tool result is an observation, not an explanation. Only the
runtime boundary that knows the violated contract assigns a category. Consumers
never infer a category from exception names or human-readable message text.
"""

import copy

REJECTION_VERSION = "tool-rejection-v0.9"
CATEGORIES = frozenset(
    {
        "policy_error",
        "business_constraint",
        "capability_gap",
        "environment_error",
        "unknown",
    }
)


class ToolRejection(ValueError):
    """A rejected operation with attribution declared at its validating boundary."""

    def __init__(self, message, *, code, category, context=None):
        super().__init__(message)
        if category not in CATEGORIES or not isinstance(code, str) or not code:
            raise ValueError("A rejection requires a known category and a nonempty code")
        if context is not None and not isinstance(context, dict):
            raise TypeError("Rejection context must be an object")
        self.rejection = {
            "version": REJECTION_VERSION,
            "code": code,
            "category": category,
            "context": copy.deepcopy(context or {}),
        }


def rejection_error(exc, *, context=None, category=None, code=None):
    """Preserve error facts and explicit attribution; bare errors stay unknown.

    A caller may assign a category/code only when it owns the relevant boundary,
    for example signature binding or a genuinely uncaught port implementation error.
    """
    declared = copy.deepcopy(getattr(exc, "rejection", {}))
    category = category if category is not None else declared.get("category", "unknown")
    code = code if code is not None else declared.get("code", "unclassified_exception")
    merged = {**(context or {}), **declared.get("context", {})}
    structured = ToolRejection(str(exc), code=code, category=category, context=merged)
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "rejection": structured.rejection,
    }


def classify_tool_result(response):
    """Separate a rejected response's preserved facts from supported attribution."""
    if not isinstance(response, dict) or response.get("ok") is not False:
        raise ValueError("Classification requires an explicit unsuccessful tool response")
    error = response.get("error")
    error = error if isinstance(error, dict) else {}
    attribution = error.get("rejection")
    valid = (
        isinstance(attribution, dict)
        and attribution.get("version") == REJECTION_VERSION
        and isinstance(attribution.get("category"), str)
        and attribution["category"] in CATEGORIES
        and isinstance(attribution.get("code"), str)
        and bool(attribution["code"])
        and isinstance(attribution.get("context"), dict)
    )
    if not valid:
        attribution = {
            "version": REJECTION_VERSION,
            "code": "unattributed_tool_rejection",
            "category": "unknown",
            "context": {},
        }
    else:
        attribution = copy.deepcopy(attribution)
    category = attribution["category"]
    return {
        "status": "unattributed_tool_rejection" if category == "unknown" else category,
        "rejection": {"type": error.get("type"), "message": error.get("message"), **attribution},
        "tool_error": copy.deepcopy(response),
    }


def port_exception(exc, *, operation, context=None):
    """Record an actual exception escaping an opaque interface implementation."""
    return {
        "ok": False,
        "error": rejection_error(
            exc,
            category="environment_error",
            code="public_" + operation + "_exception",
            context={"boundary": "opaque_public_port", "operation": operation, **(context or {})},
        ),
    }
