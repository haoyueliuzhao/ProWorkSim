"""Only the explicit trusted direct pre-generation rejection is unsampled."""

import copy

import pytest

from proworksim.member_views import member_view
from proworksim.storage import digest, json_bytes
from test_online_support_v013 import declaration, rollout


def fixture():
    decl = declaration(slots=1)
    result = rollout(decl, "0")
    events = result["events"]
    cid = "second-context-limited"
    request = {"messages": [{"role": "user", "content": "actual request"}]}
    body = {
        "error": {
            "code": "context_length_exceeded",
            "prompt_tokens": 90,
            "requested_output": 20,
            "context_limit": 100,
        },
        "transport_kind": "resident_direct",
        "generation_started": False,
        "actor_identity": decl["actor_identity"],
        "online_window_id": decl["window_id"],
    }
    for kind, payload in [
        (
            "model_call",
            {"stage": "started", "call_id": cid, "request_sha256": digest(json_bytes(request))},
        ),
        (
            "model_attempt",
            {
                "stage": "finished",
                "status": "backend_context_limit",
                "call_id": cid,
                "request": request,
                "response": {"http_status": 400, "body": body},
            },
        ),
        (
            "model_boundary_error",
            {
                "status": "model_budget_exhausted",
                "model_call_id": cid,
                "backend_error": {"code": "context_length_exceeded", "http_status": 400},
            },
        ),
    ]:
        events.append(
            {"sequence": len(events), "kind": kind, "worker_id": "provider", "payload": payload}
        )
    return result


def test_direct_known_no_generation_keeps_previous_full_trajectory():
    result = fixture()
    original = copy.deepcopy(result)
    view = member_view(result, "provider")
    assert result == original
    assert view["own_action_count"] == 1 and view["complete_actor_trajectory"]
    last = view["decisions"][-1]
    assert last["actor_required"] is False
    assert last["generation_status"] == "not_started_direct_context_limit"
    assert last["actual_input"] and last["non_generation_response"]
    assert last["actual_response"] is None and last["tokens"] is None


@pytest.mark.parametrize(
    "change", ["transport", "generated", "actor", "window", "boundary", "retry", "length"]
)
def test_ordinary_or_ambiguous_context_failure_never_claims_no_generation(change):
    result = fixture()
    attempt = result["events"][-2]
    body = attempt["payload"]["response"]["body"]
    if change == "transport":
        body["transport_kind"] = "ordinary_http"
    elif change == "generated":
        body["generation_started"] = True
    elif change == "actor":
        body["actor_identity"] = {"version": "old"}
    elif change == "window":
        body["online_window_id"] = "previous-window"
    elif change == "boundary":
        result["events"].pop()
    elif change == "retry":
        extra = copy.deepcopy(attempt)
        extra["sequence"] = len(result["events"])
        result["events"].append(extra)
    else:
        body["error"]["context_limit"] = 1000
    view = member_view(result, "provider")
    assert view["decisions"][-1]["actor_required"] is True
    assert not view["complete_actor_trajectory"]
