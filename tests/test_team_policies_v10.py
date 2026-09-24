"""Business policies use actual public inputs and retain local-repair semantics."""

import json

import pytest

from proworksim.core.world import WorldSpec
from proworksim.experience import capture_port
from proworksim.staff_runtime import StaffRuntime
from proworksim.templates.research_review import package
from proworksim.workers.team_policies import ReportAuthorPolicy, ReviewerPolicy
from proworksim.world_core import WorldCore
from scripts.staff_runtime_experiment import run_case


@pytest.mark.parametrize("case", ["correct", "two_partial", "rebuttal", "reconciliation"])
def test_real_roles_preserve_controlled_semantics_and_independent_truth(tmp_path, case):
    result = run_case(case, tmp_path / case)
    assert result["error"] is None, result["error"]
    assert result["passed"], [c for c in result["checks"] if not c["passed"]]


def test_renamed_roles_new_source_values_unknown_and_checkpoint(tmp_path):
    world = WorldCore.create(
        tmp_path / "world",
        WorldSpec(
            world_id="novel-public-input",
            actors={"setup": {}, "writer": {}, "editor": {}},
            bootstrap_grants=[{"actor_id": "setup", "scope": "world", "power": "install_project"}],
        ),
    )
    spec = package("J", author="writer", reviewer="editor", source_alias="observed-material")
    spec["objects"][0]["data"]["metrics"]["revenue"] = {"value": 233, "previous": 280}
    spec["objects"][0]["data"]["metrics"]["cost"] = {"value": None, "previous": 15}
    assert world.session("setup").call("install_project", package=spec)["ok"]
    captured = []
    ports = {
        label: capture_port(world.session(actor, "J"), captured)
        for label, actor in (("writer-port", "writer"), ("editor-port", "editor"))
    }
    policies = {
        "writer-port": ReportAuthorPolicy(style="compact", split=True),
        "editor-port": ReviewerPolicy(),
    }
    runtime = StaffRuntime(ports, policies, run_id="changed-input")
    first = runtime.run(max_actions=4, max_opportunities=20)
    assert first["status"] == "budget_exhausted"
    snapshot = runtime.snapshot()
    resumed = StaffRuntime(ports, policies, checkpoint=json.loads(json.dumps(snapshot)))
    result = resumed.run(max_actions=80, max_opportunities=200)
    assert result["status"] == "worker_waiting", [
        o.get("error") for o in result["outcomes"] if o["status"] == "policy_error"
    ]
    state = world.store.load()
    work = state["work_items"]["J::research"]
    assert len(work["submissions"]) == 1
    sub = work["submissions"][0]
    assert sub["review"]["decision"] == "accepted"
    assert len(sub["artifact_versions"]) == 2
    docs = {}
    for oid, vid in sub["artifact_versions"].items():
        docs.update(json.loads(world.store.version_path(state["artifacts"][oid], vid).read_text()))
    actual = {s["section_id"]: s for s in docs["report"]["sections"]}
    assert (
        actual["revenue"]["body"]
        == "2026H1: Revenue = 233 (down) [observed-material:metrics.revenue.value]."
    )
    assert (
        actual["cost"]["body"]
        == "2026H1: Cost = unknown (unknown) [observed-material:metrics.cost.value]."
    )
    assert actual["cost"]["claims"][0]["value"] is None
    with pytest.raises(ValueError, match="configuration"):
        StaffRuntime(
            ports,
            {
                "writer-port": ReportAuthorPolicy(style="prose", split=True),
                "editor-port": ReviewerPolicy(),
            },
            checkpoint=snapshot,
        )
