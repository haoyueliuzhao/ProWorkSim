"""Only the new pre-execution classification gate; no SDK/model required."""
from types import SimpleNamespace

import pytest

from proworksim.harness_policy_v040 import _preexecution_rejection


@pytest.mark.parametrize("field,value", [("_executions", 1), ("_pending", {"name": "already-pending"}),
    ("_result", {"ok": True}), ("_last_body", None), ("_association", {})])
def test_untrusted_or_effectful_action_cannot_be_downgraded_to_format_feedback(field, value):
    events = []

    def fail(status, reason, **details):
        raise ValueError(status)

    worker = SimpleNamespace(_executions=0, _pending=None, _result=None,
        _last_body={"id": "original-response"}, _association={"call_id": "original-call"},
        _emit=lambda kind, payload: events.append(kind), _fail=fail)
    setattr(worker, field, value)
    with pytest.raises(ValueError, match="^execution_integrity_error$"):
        _preexecution_rejection(worker, "work_done")
    assert events == []
