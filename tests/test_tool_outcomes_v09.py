"""A rejection is a fact; attribution needs a declared semantic boundary."""

import pytest

from proworksim.continuous_worker import ContinuousWorker
from proworksim.tool_outcomes import (
    ToolRejection,
    classify_tool_result,
    port_exception,
    rejection_error,
)


@pytest.mark.parametrize(
    "error",
    [
        {"type": "ValueError", "message": "World is paused; resume before new work"},
        {"type": "EnvironmentError", "message": "An environment error occurred"},
        {"type": "PermissionError", "message": "Actor lacks project power"},
    ],
)
def test_legacy_error_text_never_invents_attribution(error):
    response = {"ok": False, "error": error, "command_committed": True}
    result = classify_tool_result(response)
    assert result["status"] == "unattributed_tool_rejection"
    assert result["rejection"]["category"] == "unknown"
    assert result["tool_error"] == response
    result["tool_error"]["error"]["message"] = "changed copy"
    assert response["error"]["message"] == error["message"]


@pytest.mark.parametrize(
    "category,code",
    [
        ("policy_error", "invalid_arguments"),
        ("business_constraint", "world_paused"),
        ("capability_gap", "tool_not_enabled"),
        ("environment_error", "implementation_exception"),
        ("unknown", "unclassified_exception"),
    ],
)
def test_declared_boundary_facts_survive_serialization(category, code):
    error = rejection_error(
        ToolRejection(
            "Concrete refusal",
            category=category,
            code=code,
            context={"work_id": "A::w1"},
        ),
        context={"action": "submit", "actor": "alice"},
    )
    result = classify_tool_result({"ok": False, "error": error})
    assert result["status"] == (
        category if category != "unknown" else "unattributed_tool_rejection"
    )
    assert result["rejection"]["code"] == code
    assert result["rejection"]["context"] == {
        "work_id": "A::w1",
        "action": "submit",
        "actor": "alice",
    }
    assert result["rejection"]["type"] == "ToolRejection"


def test_bare_internal_exception_stays_unknown_without_explicit_boundary():
    error = rejection_error(KeyError("unexpected internal key"))
    assert error["rejection"]["category"] == "unknown"
    escaped = port_exception(KeyError("unexpected internal key"), operation="call")
    assert classify_tool_result(escaped)["status"] == "environment_error"
    assert escaped["error"]["rejection"]["context"]["boundary"] == "opaque_public_port"


@pytest.mark.parametrize(
    "attribution",
    [
        {
            "version": "future",
            "code": "world_paused",
            "category": "business_constraint",
            "context": {},
        },
        {
            "version": "tool-rejection-v0.9",
            "code": "world_paused",
            "category": "made_up",
            "context": {},
        },
        {
            "version": "tool-rejection-v0.9",
            "code": "",
            "category": "business_constraint",
            "context": {},
        },
    ],
)
def test_malformed_attribution_does_not_become_a_valid_category(attribution):
    result = classify_tool_result({"ok": False, "error": {"rejection": attribution}})
    assert result["status"] == "unattributed_tool_rejection"


@pytest.mark.parametrize(
    "category", ["policy_error", "business_constraint", "capability_gap", "unknown"]
)
def test_worker_consumes_explicit_classification_without_rewriting_tool_return(category):
    response = {
        "ok": False,
        "error": rejection_error(
            ToolRejection(
                "Actual test port rejection",
                category=category,
                code="test_boundary",
            )
        ),
    }

    class Port:
        def call(self, action, **kwargs):
            return response

    worker = ContinuousWorker({"A": Port()}, run_id="rejection-unit")
    task = {"port": "A", "work_id": "A::w1"}
    value, outcome = worker._call("A", task, [{"name": "submit"}], "submit", work_id="A::w1")
    assert value is None
    assert outcome["status"] == (
        category if category != "unknown" else "unattributed_tool_rejection"
    )
    assert outcome["action_performed"] is True
    assert worker.transcript[-1]["value"]["response"] == response


def test_real_pause_is_a_resumable_business_constraint(tmp_path):
    from proworksim.core.world import WorldSpec
    from proworksim.world_core import WorldCore
    from scripts.continuous_worker_experiment import package, public_port

    world = WorldCore.create(tmp_path / "world", WorldSpec(
        "resumable-pause", {"alice": {}, "manager": {}},
        bootstrap_grants=[{"actor_id": "manager", "scope": "world", "power": power}
                          for power in ("install_project", "pause_world")],
    ))
    manager = world.session("manager")
    assert manager.call("install_project", package=package("A"))["ok"]
    captured, fired = [], []

    def pause_first_call(action):
        if not fired:
            fired.append(action)
            assert manager.call("pause")["ok"]

    port = public_port(world.session("alice", "A"), "A", captured, pause_first_call)
    worker = ContinuousWorker({"A": port}, run_id="resumable-pause")
    stopped = worker.run()
    assert stopped["status"] == "business_constraint"
    assert stopped["steps"][-1]["rejection"]["code"] == "world_paused"
    first_call = next(item for item in worker.transcript if item["kind"] == "tool_call")
    assert first_call["value"]["response"]["ok"] is False
    assert manager.call("resume")["ok"]
    resumed = worker.run()
    assert resumed["status"] == "completed"
    assert next(item for item in worker.transcript if item["kind"] == "tool_call") == first_call
    assert world.store.load()["work_items"]["A::work-1"]["status"] == "accepted"
