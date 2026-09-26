"""Offline diagnostic fixtures: observed repair needs exact sources and feedback."""

import copy
import json

import pytest

from scripts.learning_work_diagnostics_v014 import diagnose_episode, diagnose_events


def world_states():
    start = {"workspaces": {"TEAM": {"code": "code", "result": "result", "data": "data", "basis": "basis"}},
             "artifacts": {oid: {"current_version": "v1", "versions": {"v1": {"sha256": oid + "-old"}}} for oid in ["code", "result", "data", "basis"]},
             "work_items": {"TEAM::build": {"requirements": {"reporting_period": "2025-01", "input_policies": {"data": "fixed", "basis": "fixed"}}, "submissions": []}}}
    end = copy.deepcopy(start)
    return start, end


def call(sequence, action, result=None, error=None, **arguments):
    return {"sequence": sequence, "worker_id": "implementer", "kind": "tool_call", "payload": {
        "action": action, "arguments": arguments, "model_call_id": "call-" + str(sequence),
        "response": {"ok": error is None, "result": result} if error is None else {"ok": False, "error": {"message": error}}}}


def feedback(events, earlier, later, *, retained=True):
    message = {"role": "tool", "content": json.dumps(earlier["payload"]["response"])}
    events.extend([
        {"sequence": earlier["sequence"] + 1, "worker_id": "implementer", "kind": "model_tool_result", "payload": {"call_id": earlier["payload"]["model_call_id"], "message": message}},
        {"sequence": later["sequence"] - 1, "worker_id": "implementer", "kind": "model_attempt", "payload": {"stage": "finished", "status": "success", "call_id": later["payload"]["model_call_id"], "request": {"messages": [message] if retained else []}}},
    ])


@pytest.mark.parametrize("same_source,retained,expected", [(True, True, True), (False, True, False), (True, False, False)])
def test_adoption_repair_requires_exact_actual_build_input_and_consumed_feedback(same_source, retained, expected):
    start, end = world_states()
    rejected = call(1, "sql_build", error="SQL input requires this work's exact adoption: basis", work_id="build")
    adopted_ref = {"object_id": "basis", "version_id": "v1"}
    adoption = call(5, "adopt", result={**adopted_ref, "alias": "basis", "work_id": "TEAM::build"}, alias="basis", work_ids=["build"])
    built = call(9, "sql_build", result={"reference": {"object_id": "result", "version_id": "v2"}, "execution_status": "success"}, work_id="build")
    end["artifacts"]["result"]["versions"]["v2"] = {"sha256": "built", "execution_provenance": {
        "kind": "sql_build", "work_id": "TEAM::build", "status": "success",
        "code_reference": {"object_id": "code", "version_id": "v1"},
        "source_references": {"basis": adopted_ref if same_source else {"object_id": "basis", "version_id": "v2"}},
    }}
    events = [rejected, adoption, built]
    feedback(events, rejected, adoption, retained=retained)
    feedback(events, rejected, built, retained=retained)
    row = diagnose_events(sorted(events, key=lambda event: event["sequence"]), start, end, None)
    assert bool(row["feedback_obligation_repairs"][0]["repairs"]) is expected
    assert row["summary"]["correct_build_original_term"] is None
    assert row["summary"]["correct_fixed_submission_original_term"] is None


def test_manual_result_write_followed_by_original_code_build_is_not_code_repair():
    start, end = world_states()
    written = call(1, "write_object", result={"object_id": "result", "version_id": "v2"}, alias="result", data={"tables": {}})
    built = call(5, "sql_build", result={"reference": {"object_id": "result", "version_id": "v3"}, "execution_status": "success"}, work_id="build")
    end["artifacts"]["result"]["versions"].update({
        "v2": {"sha256": "manual"},
        "v3": {"sha256": "built", "execution_provenance": {"kind": "sql_build", "work_id": "TEAM::build", "status": "success", "code_reference": {"object_id": "code", "version_id": "v1"}, "source_references": {}}},
    })
    row = diagnose_events([written, built], start, end, {"components": [{"term_id": "correct_actual_build", "achieved": False, "evidence": None}]})
    assert row["summary"]["manual_result_write"] is True
    assert row["summary"]["changed_code"] is False
    assert row["builds"][0]["executed_current_code"] is True
    assert row["builds"][0]["executed_current_episode_code_edit"] is False
    assert row["summary"]["correct_build_original_term"] is False


def test_unclosed_episode_and_missing_episode_are_unknown_not_failure(tmp_path):
    episode = tmp_path / "episode"
    episode.mkdir()
    (episode / "manifest.json").write_text(json.dumps({"status": "open", "episode_id": "fixture-open"}))
    row = diagnose_episode(episode)
    assert row["status"] == "unknown" and row["reason"] == "episode_not_closed"
    assert "work" not in row and "original_reward" not in row
    missing = diagnose_episode(tmp_path / "missing")
    assert missing["status"] == "unknown" and "FileNotFoundError" in missing["reason"]


@pytest.mark.parametrize("new_sql,expected", [("SELECT 1", False), ("SELECT 2", True)])
def test_sql_text_change_is_distinct_from_code_metadata_change(new_sql, expected):
    start, end = world_states()
    end["artifacts"]["code"]["versions"]["v2"] = {"sha256": "new-code-bytes"}
    event = call(1, "write_object", result={"object_id": "code", "version_id": "v2"}, alias="code")
    documents = {"v1": {"models": [{"name": "metrics", "sql": "SELECT 1"}], "config": {"note": "old"}},
                 "v2": {"models": [{"name": "metrics", "sql": new_sql}], "config": {"note": "new"}}}
    row = diagnose_events([event], start, end, None, document=lambda reference: documents[reference["version_id"]])
    assert row["summary"]["changed_code"] is True
    assert row["summary"]["changed_sql_program"] is expected
    assert row["summary"]["correct_build_original_term"] is None
