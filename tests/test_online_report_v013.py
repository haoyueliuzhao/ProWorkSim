"""Pure aggregation fixtures: no model, world execution, reward/V rerun or GPU."""

import hashlib
import json
from pathlib import Path

from scripts.online_report_v013 import build_report, summarize_events


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def event(seq, kind, payload, member="provider"):
    return {"sequence": seq, "kind": kind, "payload": payload, "worker_id": member}


def completion(seq, cid, request, *, started=False, response_id=None):
    p = {
        "call_id": cid,
        "attempt_id": cid + "-1",
        "backend_id": "resident_direct",
        "endpoint": "http://127.0.0.1:1/v1/chat/completions",
        "request": request,
        "stage": "started" if started else "finished",
    }
    if not started:
        p.update(
            status="success",
            accounting={
                "reported_usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}
            },
            response={
                "http_status": 200,
                "body": {
                    "id": response_id or cid,
                    "choices": [{"message": {"role": "assistant", "content": "fixture"}}],
                    "token_trace": {"input_ids": [1, 2], "output_ids": [3]},
                    "service_record": {
                        "transport_kind": "resident_direct",
                        "seconds": 0.5,
                        "peak_gpu_bytes": 123,
                        "resource": {"rss_bytes": 456, "rss_peak_bytes": 789},
                    },
                },
            },
        )
    return event(seq, "model_attempt", p)


def history(feedback=True):
    message = {
        "role": "tool",
        "tool_call_id": "tool-c1",
        "content": "Actual invalid reference error",
    }
    request = {"messages": [message] if feedback else []}
    return [
        completion(0, "c1", {"messages": []}, started=True),
        completion(1, "c1", {"messages": []}),
        event(
            2,
            "tool_call",
            {
                "action": "read_alias",
                "arguments": {"alias": "wrong"},
                "model_call_id": "c1",
                "response": {
                    "ok": False,
                    "error": {
                        "rejection": {"code": "unknown_alias", "category": "business_constraint"}
                    },
                },
            },
        ),
        event(3, "model_tool_result", {"call_id": "c1", "message": message}),
        completion(4, "c2", request, started=True),
        completion(5, "c2", request),
        event(
            6,
            "tool_call",
            {
                "action": "read_alias",
                "arguments": {"alias": "basis"},
                "model_call_id": "c2",
                "response": {
                    "ok": True,
                    "result": {"reference": {"object_id": "basis", "version_id": "v1"}},
                },
            },
        ),
    ]


def test_direct_attempts_are_not_http_and_feedback_adjustment_is_observed():
    summary = summarize_events(history())
    assert summary["totals"]["resident_direct_attempts_started"] == 2
    assert summary["totals"].get("network_http_attempts_started", 0) == 0
    assert summary["totals"]["returned_generations"] == 2
    assert summary["totals"]["reported_total_tokens"] == 6
    row = summary["rejection_followups"]["rows"][0]
    assert row["feedback"] == "present_in_actual_request"
    assert row["adjustment"] == "changed_arguments_same_tool"
    assert row["next_response_ok"] is True
    assert summary["resources"]["generation_seconds_sum"] == 1
    assert summary["resources"]["max_gpu_allocated_peak_bytes"] == 123


def test_missing_feedback_is_not_inferred_from_saved_response_and_sql_ok_is_separate():
    events = history(feedback=False)
    events += [
        event(
            7,
            "tool_call",
            {
                "action": "sql_build",
                "arguments": {},
                "response": {"ok": True, "result": {"execution_status": "error"}},
            },
        ),
        event(
            8,
            "tool_call",
            {
                "action": "sql_build",
                "arguments": {},
                "response": {"ok": False, "error": {"type": "ValueError"}},
            },
        ),
    ]
    summary = summarize_events(events)
    assert summary["rejection_followups"]["rows"][0]["feedback"] == "absent_from_actual_request"
    assert summary["tools"]["sql_build"] == {
        "ok": 1,
        "sql:error": 1,
        "rejected": 1,
        "rejection:ValueError": 1,
        "sql:pre_execution_rejected": 1,
    }
    assert summary["rejection_followups"]["rows"][-1]["feedback"] == "no_next_generation"


def test_list_tool_result_is_successful_and_followup_does_not_infer_sql_status():
    events = history()
    events[-1]["payload"].update(
        action="read_messages",
        arguments={},
        response={"ok": True, "result": [{"message_id": "actual-message"}]},
    )
    summary = summarize_events(events)
    assert summary["tools"]["read_messages"] == {"ok": 1}
    assert summary["tool_returns"][-1]["sql_execution_status"] is None
    followup = summary["rejection_followups"]["rows"][0]
    assert followup["feedback"] == "present_in_actual_request"
    assert followup["adjustment"] == "different_tool"
    assert followup["next_response_ok"] is True
    assert followup["next_sql_execution_status"] is None


def test_closed_and_unstarted_slots_keep_original_reward_validity_and_probability_facts(tmp_path):
    root = tmp_path / "run"
    col = root / "online/window-0/collection"
    identity = {"policy_version": "fixture-current"}
    declaration = {
        "version": "online-window-support-v0.13",
        "window_id": "fixture-window",
        "actor_identity": identity,
        "gamma_identity": {"transport_kind": "resident_direct", "interface_version": "fixture-v13"},
        "slots": [
            {
                "slot_id": "first",
                "xi_id": "first-xi",
                "xi_fingerprint": "a",
                "active_members": ["provider"],
            },
            {
                "slot_id": "not-started",
                "xi_id": "second-xi",
                "xi_fingerprint": "b",
                "active_members": ["provider"],
            },
        ],
    }
    write(col / "declaration.json", declaration)
    events = history()
    experience_hash = write(col / "slot-0/episode/experience.json", {"events": events})
    write(
        col / "slot-0/episode/manifest.json",
        {
            "status": "closed",
            "episode_id": "fixture-episode",
            "experience": {
                "path": "experience.json",
                "sha256": experience_hash,
                "start": 0,
                "end": len(events),
            },
            "experience_start": {"event_count": 0},
        },
    )
    reward = {
        "eligible": True,
        "reward": 0.25,
        "scope": "handoff",
        "components": [{"term_id": "read", "weight": 0.25, "achieved": True, "score": 0.25}],
    }
    write(
        col / "slot-0/team-rollout.json",
        {
            "reward_eligibility": reward,
            "work_validity": {
                "value": False,
                "components": {"basis": {"value": True}, "delivery": {"value": False}},
            },
        },
    )
    write(
        col / "slot-0/preparation.json",
        {
            "credited_to_current_actor": False,
            "experience": {"events": [event(0, "preparation_tool_call", {})]},
        },
    )
    write(
        col / "support.json",
        {
            "groups": [
                {
                    "window": {"xi_id": "first-xi"},
                    "planned": 1,
                    "not_started": 0,
                    "support": {"slot_ids": ["first"], "blocks": {}},
                }
            ]
        },
    )
    update = root / "online/window-0/update"
    write(
        update / "report.json",
        {
            "status": "zero_step_probability_mismatch",
            "training_happened": False,
            "actor_optimizer_steps": 0,
            "before_actor_identity": identity,
            "after_actor_identity": identity,
        },
    )
    write(
        update / "behavior-probability-check.json",
        [{"call_id": "c1", "max_abs_delta": 0.03, "mean_abs_delta": 0.004, "passed": False}],
    )
    write(
        update / "admission.json",
        {
            "slot_count": 2,
            "slots": [
                {"slot_id": "first", "exclusions": []},
                {"slot_id": "not-started", "exclusions": ["not_closed"]},
            ],
            "decisions": [
                {
                    "slot_id": "first",
                    "member_id": "provider",
                    "call_id": "c1",
                    "tokens": {"output_ids": [1, 2]},
                    "actor_denominator": 4,
                    "critic_denominator": 2,
                }
            ],
        },
    )
    before = {str(p): p.read_bytes() for p in root.rglob("*.json")}
    result = build_report([root])
    assert {str(p): p.read_bytes() for p in root.rglob("*.json")} == before
    w = result["windows"][0]
    assert len(w["slots"]) == 2
    assert w["slots"][0]["reward"]["reward"] == 0.25
    assert w["slots"][0]["validity"]["value"] is False
    assert w["slots"][1]["actual"] is None and w["slots"][1]["reward"] is None
    assert w["update"]["behavior_probability"]["max_observed_absolute_difference"] == 0.03
    assert w["update"]["gradient_probability"]["passed"] is None
    assert w["update"]["admission"]["decision_count"] == 1
    assert w["update"]["admission"]["output_token_positions"] == 2
    assert "tokens" not in w["update"]["admission"]["decisions"][0]
    assert w["support"]["groups"][0]["window"]["xi_id"] == "first-xi"
    assert w["support"]["groups"][0]["planned"] == 1
    assert w["support"]["groups"][0]["not_started"] == 0
    assert w["support"]["groups"][0]["slot_ids"] == ["first"]
    assert result["actual_network_http_attempts_observed"] == 0
    assert result["observed_generation_resources"]["max_gpu_allocated_peak_bytes"] == 123


def test_confirmed_pre_generation_refusal_is_not_unknown_sampling():
    events = [
        completion(0, "too-long", {"messages": []}, started=True),
        event(
            1,
            "model_attempt",
            {
                "call_id": "too-long",
                "attempt_id": "too-long-1",
                "backend_id": "resident_direct",
                "stage": "finished",
                "status": "failed",
                "accounting": {"unknown_usage": True},
                "response": {
                    "http_status": 400,
                    "body": {
                        "generation_started": False,
                        "error": {"code": "context_length_exceeded", "prompt_tokens": 9000},
                    },
                },
            },
        ),
    ]
    totals = summarize_events(events)["totals"]
    assert totals["resident_direct_attempts_started"] == 1
    assert totals.get("returned_generations", 0) == 0
    assert totals["finished_unknown_usage_attempts"] == 1
    assert totals["confirmed_pre_generation_rejections"] == 1
    assert totals.get("finished_unknown_sampling_usage_attempts", 0) == 0
    assert totals["pre_generation_tokenized_prompt_positions"] == 9000


def test_preparation_failure_keeps_all_planned_slots_and_real_preparation_footprints(tmp_path):
    root = tmp_path / "failed"
    (root / "resident/calls").mkdir(parents=True)
    write(
        root / "online/protocol.json",
        {
            "windows": [
                {"window_id": "w0", "slots": [{"slot_id": "x"}, {"slot_id": "y"}]},
                {"window_id": "w1", "slots": [{"slot_id": "z"}]},
            ]
        },
    )
    write(
        root / "online/report.json",
        {
            "status": "error",
            "error": {"message": "Declared preparation SQL execution failed"},
            "windows": [{"window_id": "w0", "status": "collecting"}],
        },
    )
    (root / "online/window-0/collection/slot-0/world").mkdir(parents=True)
    write(root / "online/window-0/collection/slot-0/preparation.json", {"status": "ready"})
    run = build_report([root])["input_runs"][0]
    assert run["boundary_status"] == "preparation_failed_before_collection"
    assert run["planned_slots"] == 3
    assert run["zero_recorded_generations_before_collection"] is True
    slots = [s for w in run["planned_windows"] for s in w["slots"]]
    assert all(s["actor_status"] == "not_started_actor" for s in slots)
    assert [s["preparation_record_exists"] for s in slots] == [True, False, False]
    assert all(s["episode_manifest_ref"] is None for s in slots)


def test_intervention_overrides_stale_running_report_and_keeps_later_plan(tmp_path):
    root = tmp_path / "interrupted"
    col = root / "online/window-0/collection"
    write(
        col / "declaration.json",
        {
            "version": "online-window-support-v0.13",
            "window_id": "w0",
            "actor_identity": {},
            "slots": [],
        },
    )
    write(
        root / "online/protocol.json",
        {
            "windows": [
                {"window_id": "w0", "slots": []},
                {"window_id": "w1", "slots": [{"slot_id": "later"}]},
            ]
        },
    )
    write(root / "online/report.json", {"status": "running"})
    launch = tmp_path / "launch/o1"
    write(
        Path(str(launch) + ".launch.json"),
        {"command": ["python", "driver.py", "--output", str(root)], "pid": 13, "exit_code": 130},
    )
    write(
        Path(str(launch) + ".intervention.json"),
        {"action": "SIGINT", "reason": "Saved bounded stop"},
    )
    result = build_report([root], launch_prefixes=[launch])
    run = result["input_runs"][0]
    assert run["boundary_status"] == "interrupted_with_recorded_collection"
    assert run["stored_runner_status"] == "running"
    assert run["planned_windows"][1]["slots"][0]["actor_status"] == "not_started_actor"
    assert result["launches"][0]["intervention"]["action"] == "SIGINT"


def test_checkpoint_startup_failure_preserves_plan_and_actual_zero_collections(tmp_path):
    root = tmp_path / "failed"
    (root / "resident/calls").mkdir(parents=True)
    write(
        root / "online/protocol.json",
        {"windows": [{"window_id": "planned", "slots": [{"slot_id": "x"}]}]},
    )
    write(
        root / "resident-startup-resource.json",
        {"status": "ready", "startup_peak_allocated_bytes": 100},
    )
    launch = tmp_path / "launch/o0"
    write(
        Path(str(launch) + ".launch.json"),
        {"command": ["python", "driver.py", "--output", str(root)], "pid": 13, "exit_code": 1},
    )
    Path(str(launch) + ".log").write_text("initial checkpoint safe reload failed: TorchVersion\n")
    result = build_report([root], launch_prefixes=[launch])
    assert result["windows"] == []
    run = result["input_runs"][0]
    assert run["boundary_status"] == "startup_failed_before_collection"
    assert run["planned_slots"] == 1 and run["zero_recorded_generations_before_collection"] is True
    assert (
        run["startup_resource"]["status"] == "ready"
    )  # Weight loading and experiment startup differ.
    assert result["resident_direct_attempts_observed"] == 0
    assert result["actual_network_http_attempts_observed"] == 0
