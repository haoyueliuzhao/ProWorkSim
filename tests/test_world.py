import io
import json

import pytest
from openpyxl import load_workbook

from proworksim.baseline import run_baseline
from proworksim.kernel import World, WorldError
from proworksim.storage import read_json
from proworksim.validation import evaluate


def call(session, action, **kwargs):
    result = session.call(action, **kwargs)
    assert result["ok"], result
    return result["result"]


class BeforeSubmission(Exception):
    pass


class PreparationSession:
    def __init__(self, session):
        self.session = session

    def observe(self):
        return self.session.observe()

    def call(self, action, **kwargs):
        if action == "submit":
            raise BeforeSubmission
        return self.session.call(action, **kwargs)


def prepare(world):
    with pytest.raises(BeforeSubmission):
        run_baseline(PreparationSession(world.session()))


@pytest.mark.parametrize("delivery", ["short", "file", "continuous"])
@pytest.mark.parametrize("information", ["mail", "clarification"])
def test_feasible_granularities_with_no_forced_rework(world_factory, delivery, information):
    world = world_factory(delivery, information)
    result = run_baseline(world.session())
    assert result["complete"]
    records = evaluate(world.store.root)
    assert all(r["passed"] for r in records)
    state = world.store.load()
    assert len(state["work_items"]) == (2 if delivery == "continuous" else 1)
    assert all(len(item["submissions"]) == 1 for item in state["work_items"].values())
    assert all(
        row["actor_id"] != "analyst" for row in state["interactions"] if row["action"] == "review"
    )


def test_real_stale_memo_feedback_then_revision(world_factory):
    world = world_factory()
    assert run_baseline(world.session(), inject_stale_memo=True)["complete"]
    records = evaluate(world.store.root)
    first, revised, second_requirement = records
    assert not first["passed"] and revised["passed"] and second_requirement["passed"]
    submissions = world.store.load()["work_items"]["work-1"]["submissions"]
    assert submissions[0]["review"]["decision"] == "revision_required"
    assert any("备忘录" in d for d in submissions[0]["review"]["defects"])
    assert submissions[0]["artifact_versions"] != submissions[1]["artifact_versions"]


def test_acl_future_materials_and_local_knowledge(world_factory):
    world = world_factory(information="clarification")
    analyst = world.session()
    public = json.dumps(analyst.observe(), ensure_ascii=False)
    assert "acceptance_spec_ref" not in public and "FY2025-restated" not in public
    for aid in ("scope", "../control/spec.json", "/etc/passwd", "future"):
        assert not analyst.call("read_file", artifact_id=aid)["ok"]
    assert not (world.store.workspace / "private/manager_scope.json").exists()
    assert call(analyst, "search", query="FY2025-restated") == []
    assert world.store.load()["knowledge"]["analyst"]["read_artifacts"] == []
    headers = call(analyst, "mail_list")
    assert world.store.load()["knowledge"]["analyst"]["read_messages"] == []
    call(analyst, "mail_read", message_id=headers[0]["message_id"])
    assert world.store.load()["knowledge"]["analyst"]["read_messages"] == [headers[0]["message_id"]]
    assert not analyst.call("approve", work_item_id="work-1", submission_id="invented")["ok"]
    assert not analyst.call("write_file", artifact_id="financials", content="fiction")["ok"]
    assert not analyst.call("calculate", expression="__import__('os').listdir('/')")["ok"]
    assert not analyst.call("read_file", actor="manager", artifact_id="scope")["ok"]


def test_pending_clarification_survives_snapshot_and_branch(world_factory, tmp_path):
    world = world_factory(information="clarification")
    blocked = call(
        world.session(),
        "block_work",
        work_item_id="work-1",
        reason="本轮假设尚未确认",
        kind="scope",
        requested_role="manager",
        required_scope_version=1,
    )
    call(
        world.session(),
        "mail_send",
        to="manager",
        topic="scope",
        body="请确认口径",
        work_item_id="work-1",
        blocker_id=blocked["blocker_id"],
    )
    snapshot = world.snapshot(tmp_path / "snapshot")
    branch = World.restore(snapshot, tmp_path / "branch")
    resumed = World.restore(snapshot, tmp_path / "resumed", branch=False)
    assert branch.store.load()["branch_id"] != world.store.load()["branch_id"]
    assert resumed.store.load()["branch_id"] == world.store.load()["branch_id"]
    call(branch.session(), "wait", ticks=2)
    state = branch.store.load()
    assert state["work_items"]["work-1"]["status"] == "open"
    assert any(
        isinstance(m["body"], dict) and "assumptions" in m["body"] for m in state["messages"]
    )
    assert len(world.store.load()["messages"]) < len(state["messages"])
    with pytest.raises(WorldError):
        world.snapshot(world.store.root / "nested")
    raw = read_json(snapshot / "control/state.json")
    raw["clock"] += 1
    (snapshot / "control/state.json").write_text(json.dumps(raw))
    with pytest.raises(WorldError, match="checksum"):
        World.restore(snapshot, tmp_path / "tampered")


def test_failed_edit_is_atomic_and_actual_xlsx_cache_is_persisted(world_factory):
    world = world_factory("file")
    session = world.session()
    version = call(session, "sheet_read")["version_id"]
    result = session.call("sheet_update", cells={"Inputs!B2": 999, "Invalid": 1})
    assert not result["ok"]
    assert call(session, "sheet_read")["version_id"] == version
    changed = call(session, "sheet_update", cells={"Inputs!B2": 2000})
    assert changed["version_id"] != version
    metadata = world.store.load()["artifacts"]["model"]
    data = world.store.content(metadata)
    cached = load_workbook(io.BytesIO(data), data_only=True)["Outputs"]["B2"].value
    actual = call(session, "sheet_read")["sheets"]["Outputs"]["B2"]["value"]
    assert cached == actual == 2040
    assert world.store.load()["artifacts"]["memo"]["possibly_stale"]
    assert world.store.load()["artifacts"]["memo"]["current_version"] == "v1"


def test_wrong_formula_is_allowed_but_independent_verification_rejects(world_factory):
    world = world_factory("file")
    prepare(world)
    session = world.session()
    call(session, "sheet_update", cells={"Outputs!B6": "=1+1"})
    bad_version = call(session, "sheet_read")["version_id"]
    call(session, "submit", work_item_id="work-1")
    call(session, "wait", ticks=2)
    assert world.store.load()["work_items"]["work-1"]["status"] == "accepted"
    record = evaluate(world.store.root)[0]
    assert not record["passed"]
    assert any(c["category"] == "calculation" and not c["passed"] for c in record["checks"])
    assert call(session, "sheet_read")["version_id"] == bad_version
    assert call(session, "sheet_read")["sheets"]["Outputs"]["B6"]["value"] == 2


def test_perturbation_rejects_correct_hardcoded_outputs(world_factory):
    world = world_factory("file")
    prepare(world)
    session = world.session()
    book = call(session, "sheet_read")["sheets"]
    hardcoded = {
        f"{sheet}!{cell}": content["value"]
        for sheet in ("Outputs", "Sensitivity")
        for cell, content in book[sheet].items()
        if isinstance(content["raw"], str) and content["raw"].startswith("=")
    }
    call(session, "sheet_update", cells=hardcoded)
    call(session, "submit", work_item_id="work-1")
    call(session, "wait", ticks=2)
    record = evaluate(world.store.root)[0]
    assert all(c["passed"] for c in record["checks"] if c["category"] == "calculation")
    assert not record["passed"]
    assert all(not c["passed"] for c in record["checks"] if c["category"] == "recalculability")


def test_edit_invalidates_pending_approval_and_idempotent_retry(world_factory):
    world = world_factory("file")
    prepare(world)
    session = world.session()
    sub = call(session, "submit", work_item_id="work-1")
    first = world.act(
        "analyst", "sheet_update", {"cells": {"Inputs!B2": 1000}}, request_key="call-unique"
    )
    second = world.act(
        "analyst", "sheet_update", {"cells": {"Inputs!B2": 1000}}, request_key="call-unique"
    )
    assert first == second
    assert world.store.load()["work_items"]["work-1"]["status"] == "in_progress"
    assert not world.act(
        "reviewer", "approve", {"work_item_id": "work-1", "submission_id": sub["submission_id"]}
    )["ok"]


def test_memo_source_versions_satisfy_model_binding_without_extra_citation(world_factory):
    world = world_factory()
    prepare(world)
    session = world.session()
    memo = json.loads(call(session, "read_file", artifact_id="memo")["content"])
    memo["citations"] = [c for c in memo["citations"] if c["artifact_id"] == "financials"]
    call(session, "write_file", artifact_id="memo", content=json.dumps(memo))
    call(session, "submit", work_item_id="work-1")
    call(session, "wait", ticks=1)
    assert evaluate(world.store.root, "work-1")[0]["passed"]


def test_short_answer_requires_the_specified_locations(world_factory):
    world = world_factory("short")
    prepare(world)
    session = world.session()
    model = call(session, "sheet_read")
    source = call(session, "read_file", artifact_id="financials")
    pe = round(
        model["sheets"]["Outputs"]["B6"]["value"]
        / json.loads(source["content"])["values"]["diluted_eps"],
        2,
    )
    call(
        session,
        "submit",
        work_item_id="work-1",
        answer={
            "pe": pe,
            "citations": [
                {"artifact_id": "model", "version_id": "v1", "location": "Outputs!B2"},
                {"artifact_id": "financials", "version_id": "v2", "location": "values.revenue"},
            ],
        },
    )
    call(session, "wait")
    record = evaluate(world.store.root)[0]
    assert not next(c for c in record["checks"] if c["name"] == "answer_citations")["passed"]


def test_nonfinite_input_is_a_recorded_error_not_a_broken_world(world_factory):
    world = world_factory("file")
    session = world.session()
    result = session.call("sheet_update", cells={"Inputs!B2": float("nan")})
    assert not result["ok"]
    assert "invalid_input" in world.store.load()["interactions"][-1]["inputs"]
    assert session.call("sheet_read")["ok"]
