"""Small synthetic records exercise the reporter, not model/world performance."""

import copy
import json
import shutil

from proworksim.storage import digest, json_bytes
from scripts.build_harness_study_v017 import SELECTION
from scripts.harness_report_v017 import (
    CANDIDATES,
    Reader,
    behavior,
    build_report,
    select_combination,
)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(data))


def study(tmp_path):
    runs, launches = {}, {}
    tasks = ["implement", "implement", "review", "review", "pair", "chain"]
    for ci, candidate in enumerate(CANDIDATES):
        run = tmp_path / candidate
        runs[candidate] = run
        launch = tmp_path / (candidate + "-launch.json")
        launches[candidate] = launch
        identity = {
            "policy_version": "fixture-policy-" + candidate,
            "adapter_sha256": "fixture-adapter",
            "base_manifest_sha256": "fixture-base",
            "inference_profile_sha256": "fixture-profile",
        }
        windows = []
        records = []
        for wi, (harness, repeat) in enumerate(
            [("native_v15", 0), ("openhands_v16", 0), ("openhands_v16", 1), ("native_v15", 1)]
        ):
            slots = [
                {
                    "slot_id": f"{candidate}-{wi}-{si}",
                    "case_id": f"fixture-{si}-{task}",
                    "task": task,
                    "fact_position": si,
                    "repeat": repeat,
                    "sampling_seed": 100 + si * 10 + repeat,
                    "role_decision_limits": {"implementer": 10},
                }
                for si, task in enumerate(tasks)
            ]
            windows.append(
                {"window_id": str(wi), "harness": harness, "mode": "evaluate", "slots": slots}
            )
            summaries = []
            for si, slot in enumerate(slots):
                folder = run / f"online/window-{wi}/collection/slot-{si}"
                reward = {"eligible": True, "reward": 0.0, "completed": False, "components": []}
                manifest = {"status": "closed", "episode_id": slot["slot_id"]}
                events = [
                    {
                        "sequence": 0,
                        "kind": "model_response",
                        "worker_id": "implementer",
                        "payload": {
                            "call_id": slot["slot_id"],
                            "response": {"actor_identity": identity},
                        },
                    }
                ]
                rollout = {
                    "manifest_sha256": digest(json_bytes(manifest)),
                    "events": events,
                    "reward_eligibility": reward,
                    "work_validity": {
                        "components": {"record": {"value": True}, "permission": {"value": True}}
                    },
                }
                write(folder / "episode/manifest.json", manifest)
                write(folder / "episode/experience.json", {"events": events})
                write(folder / "team-rollout.json", rollout)
                write(folder / "runtime.json", {"roles": {}})
                start = 1 + wi * 60 + si * 10
                summaries.append(
                    {
                        "slot_id": slot["slot_id"],
                        "reward": reward,
                        "started_at": start,
                        "ended_at": start + 2 + ci,
                    }
                )
            write(
                run / f"online/window-{wi}/collection/summary.json",
                {"actor_identity": identity, "slots": summaries},
            )
            records.append(
                {
                    "window_id": str(wi),
                    "mode": "evaluate",
                    "status": "complete",
                    "before_actor_identity": identity,
                    "after_actor_identity": identity,
                    "evaluation_guard": {
                        "learning_unchanged": True,
                        "rng_restored_exactly": True,
                        "learning_before_sha256": {"actor": "same"},
                        "learning_after_sha256": {"actor": "same"},
                        "rng_before_sha256": "rng",
                        "rng_after_restore_sha256": "rng",
                    },
                    "update": {"actor_optimizer_steps": 0, "critic_optimizer_steps": 0},
                }
            )
        protocol = {
            "candidate_id": candidate,
            "combination_selection": copy.deepcopy(SELECTION),
            "runtime": {"profile": {"devices": 2 + 2 * ci}},
            "initialization": {
                "kind": "fresh_public_base",
                "same_resident_actor_for_all_four_windows": True,
                "restore_checkpoint_permitted": False,
            },
            "windows": windows,
        }
        write(run / "launch-protocol.json", protocol)
        write(run / "online/protocol.json", protocol)
        write(
            run / "online/report.json",
            {
                "mode": "evaluate",
                "status": "complete",
                "protocol_sha256": digest(json_bytes(protocol)),
                "actor_steps_total": 0,
                "critic_steps_total": 0,
                "final_actor_identity": identity,
                "windows": records,
            },
        )
        write(run / "resident/owner.json", {"initial_actor_identity": identity})
        source = {
            "code_commit": "fixture-source",
            "code_dirty": False,
            "source_tree_sha256": "source",
        }
        write(run / "source-before.json", source)
        write(run / "source-after.json", source)
        write(run / "source-comparison.json", {"unchanged": True})
        write(
            launch,
            {
                "command": ["python", "run", "--output", str(run)],
                "CUDA_VISIBLE_DEVICES": "0,1" if ci == 0 else "2,3,4,5",
                "start": 0,
                "end": 300,
                "elapsed": 300,
                "exit_code": 0,
            },
        )
    return runs, launches


def change_reward(run, window, slot, reward):
    folder = run / f"online/window-{window}/collection"
    p = folder / f"slot-{slot}/team-rollout.json"
    d = json.loads(p.read_text())
    d["reward_eligibility"] = reward
    write(p, d)
    p = folder / "summary.json"
    d = json.loads(p.read_text())
    d["slots"][slot]["reward"] = reward
    write(p, d)


def test_complete_fixture_selection_uses_frozen_priority_and_loading_once(tmp_path):
    runs, launches = study(tmp_path)
    report = build_report(runs, launches)
    assert report["selection"]["status"] == "selected"
    selected = report["selection"]["selected"]
    assert (selected["candidate_id"], selected["harness"]) == ("qwen35-9b", "native_v15")
    assert selected["run_root"] == str(runs["qwen35-9b"]) and selected["protocol_ref"]["sha256"]
    assert selected["allocated_device_seconds"] == 48
    assert report["models"][0]["whole_process_allocated_device_seconds_including_loading"] == 600
    assert sum(a["allocated_device_seconds"] for a in report["models"][0]["arms"]) == 96
    # Primary responsibility outranks cheaper allocation; SDK has no privileged tie rule.
    change_reward(
        runs["qwen38-27b"],
        1,
        0,
        {"eligible": True, "reward": 1.0, "completed": True, "components": []},
    )
    chosen = build_report(runs, launches)["selection"]["selected"]
    assert (chosen["candidate_id"], chosen["harness"]) == ("qwen38-27b", "openhands_v16")
    # Higher team completions cannot override a lower primary completion count.
    models = copy.deepcopy(report["models"])
    models[0]["arms"][0].update(complete_implement_review=1, complete_pair_chain=0)
    models[0]["arms"][1].update(complete_implement_review=0, complete_pair_chain=4)
    assert select_combination(models)["selected"]["harness"] == "native_v15"


def test_unknown_retains_denominator_and_source_guard_blocks_only_eligibility(tmp_path):
    runs, launches = study(tmp_path)
    change_reward(
        runs["qwen35-9b"],
        1,
        0,
        {
            "eligible": False,
            "reward": None,
            "completed": None,
            "exclusions": ["fixture service failure"],
        },
    )
    source = json.loads((runs["qwen38-27b"] / "source-after.json").read_text())
    source["code_dirty"] = True
    write(runs["qwen38-27b"] / "source-after.json", source)
    report = build_report(runs, launches)
    arm = report["models"][0]["arms"][1]
    assert arm["metrics"]["planned"] == 12 and arm["metrics"]["known"] == 11
    assert arm["metrics"]["raw_mean"] is None and not arm["eligible"]
    assert report["models"][0]["paired"]["known_pairs"] == 11
    assert report["models"][0]["paired"]["paired_raw_delta"] is None
    assert report["models"][0]["paired"]["task_deltas"]["review"] == 0
    assert report["models"][1]["arms"][0]["metrics"]["known"] == 12
    assert all(not a["eligible"] for a in report["models"][1]["arms"])
    assert report["selection"]["selected"]["harness"] == "native_v15"


def test_partial_running_preserves_all_slots_and_never_selects(tmp_path):
    runs, launches = study(tmp_path)
    launch = json.loads(launches["qwen38-27b"].read_text())
    launch.pop("end")
    launch.pop("exit_code")
    launch.pop("elapsed")
    write(launches["qwen38-27b"], launch)
    shutil.rmtree(runs["qwen38-27b"] / "online/window-2")
    shutil.rmtree(runs["qwen38-27b"] / "online/window-3")
    report = build_report(runs, launches)
    assert sum(len(m["rows"]) for m in report["models"]) == 48
    assert sum(row["state"] == "not_started" for row in report["models"][1]["rows"]) == 12
    assert report["selection"]["status"] == "waiting_for_both_models_to_end"
    assert report["selection"]["selected"] is None
    assert report["models"][1]["whole_process_allocated_device_seconds_including_loading"] is None


def test_behavior_uses_actual_inputs_and_saved_build_evidence_without_double_count(tmp_path):
    result = {"ok": False, "error": {"message": "fixture refusal"}}
    message = {"role": "tool", "tool_call_id": "t1", "content": json.dumps(result)}
    body1 = {"id": "r1", "token_trace": {"input_ids": [1, 2, 3], "output_ids": [4, 5]}}
    body2 = {"id": "r2", "token_trace": {"input_ids": [1, 2, 3, 4], "output_ids": [5, 6]}}
    events = [
        {
            "sequence": 0,
            "kind": "model_attempt",
            "worker_id": "provider",
            "payload": {
                "stage": "finished",
                "call_id": "a",
                "decision_index": 1,
                "request": {"messages": []},
                "response": {"body": body1},
            },
        },
        {
            "sequence": 1,
            "kind": "model_response",
            "worker_id": "provider",
            "payload": {"call_id": "a", "response": body1},
        },
        {
            "sequence": 2,
            "kind": "policy_decision",
            "worker_id": "provider",
            "payload": {
                "decision": {
                    "kind": "act",
                    "action": "work_note",
                    "model_call_id": "a",
                    "arguments": {},
                }
            },
        },
        {
            "sequence": 3,
            "kind": "tool_call",
            "worker_id": "provider",
            "payload": {
                "action": "read_alias",
                "model_call_id": "a",
                "model_tool_call_id": "t1",
                "arguments": {"work_id": "TEAM::build"},
                "response": result,
            },
        },
        {
            "sequence": 4,
            "kind": "model_attempt",
            "worker_id": "provider",
            "payload": {
                "stage": "finished",
                "call_id": "b",
                "decision_index": 2,
                "request": {
                    "messages": [
                        message,
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "observation": {
                                        "conditions": {
                                            "c": {
                                                "providers": ["provider"],
                                                "status": "open",
                                                "work_item_id": "TEAM::build",
                                                "request_id": "req",
                                            }
                                        }
                                    }
                                }
                            ),
                        },
                    ]
                },
                "response": {"body": body2},
            },
        },
        {
            "sequence": 5,
            "kind": "policy_decision",
            "worker_id": "provider",
            "payload": {
                "decision": {
                    "kind": "act",
                    "action": "sql_build",
                    "model_call_id": "b",
                    "arguments": {"work_id": "TEAM::build"},
                }
            },
        },
        {
            "sequence": 6,
            "kind": "tool_call",
            "worker_id": "provider",
            "payload": {
                "action": "sql_build",
                "model_call_id": "b",
                "arguments": {"work_id": "TEAM::build"},
                "response": {
                    "ok": True,
                    "result": {
                        "execution_status": "success",
                        "reference": {"object_id": "obj", "version_id": "v2"},
                    },
                },
            },
        },
        {
            "sequence": 7,
            "kind": "policy_decision",
            "worker_id": "provider",
            "payload": {
                "decision": {
                    "kind": "done",
                    "action": "staff_done",
                    "model_call_id": "c",
                    "arguments": {},
                }
            },
        },
    ]
    events.append(
        {
            "sequence": 8,
            "kind": "tool_call",
            "worker_id": "provider",
            "payload": {
                "action": "read_messages",
                "model_call_id": "c",
                "arguments": {},
                "response": {"ok": True, "result": []},
            },
        }
    )
    write(
        tmp_path / "resident/calls/r2.json",
        {"actual_prompt_messages": [message], "rendered_prompt": message["content"]},
    )
    reward = {
        "components": [
            {
                "term_id": "correct_actual_build",
                "achieved": True,
                "evidence": {"action_sequence": 6},
            }
        ]
    }
    report = behavior(events, reward, {"provider": 6}, reader=Reader(), run_root=tmp_path)
    assert report["first_actual_build"]["decision_index"] == 2
    assert report["saved_independent_correct_build"]["remaining_role_decisions"] == 4
    assert report["submit_attempts"] == [] and report["staff_done_count"] == 1
    assert report["auxiliary_opportunities"] == 1 and report["auxiliary_output_tokens"] == 2
    assert report["errors_and_next_inputs"][0]["next_native_prompt_contains_exact_result"] is True
    assert report["errors_and_next_inputs"][0]["next_action"]["same_explicit_work_id"] is True
    assert report["provider_obligation_actions"][0]["chosen_action"] == "sql_build"
    assert report["causal_failure_explanation"] is None

    missing = copy.deepcopy(events)
    missing[4]["payload"]["response"]["body"].pop("token_trace")
    unknown = behavior(missing, reward, {"provider": 6}, reader=Reader(), run_root=tmp_path)
    assert unknown["input_tokens"] is None and unknown["output_tokens"] is None
    assert unknown["attempts_missing_original_token_counts"] == 1
    assert unknown["measured_input_tokens"] == 3


def boolean_rejection_fixture(folder, sql="SELECT NOT (false) AS x"):
    code = {"models": [{"name": "metrics", "sql": sql}]}
    code_ref = {"object_id": "code", "version_id": "v2"}
    result_ref = {"object_id": "result", "version_id": "v1"}
    error = {
        "phase": "model:metrics",
        "type": "ValueError",
        "message": "SQL function is outside the declared allowlist: not",
    }
    result = {
        "engine": "managed-duckdb-v0.11",
        "status": "execution_error",
        "error": error,
        "execution": {"kind": "sql_build", "code_reference": code_ref},
    }
    artifacts = {}
    for reference, data in [(code_ref, code), (result_ref, result)]:
        object_id, version_id = reference["object_id"], reference["version_id"]
        write(folder / "world/control/versions" / object_id / version_id / "data.json", data)
        artifacts[object_id] = {
            "filename": "data.json",
            "versions": {version_id: {"sha256": digest(json_bytes(data))}},
        }
    # A newer version must never be substituted for the failed build's exact v2.
    artifacts["code"]["versions"]["v3"] = {"sha256": "irrelevant-newer-version"}
    write(folder / "world/control/state.json", {"artifacts": artifacts})
    return {
        "sequence": 10,
        "kind": "tool_call",
        "worker_id": "implementer",
        "payload": {
            "action": "sql_build",
            "model_call_id": "fixture-rejected",
            "arguments": {"work_id": "TEAM::build"},
            "response": {
                "ok": True,
                "result": {
                    "reference": result_ref,
                    "execution_status": "execution_error",
                    "error": error,
                },
            },
        },
    }


def test_boolean_exposure_counts_calls_and_episodes_without_changing_ranking(tmp_path):
    runs, launches = study(tmp_path)
    original = build_report(runs, launches)
    folder = runs["qwen35-9b"] / "online/window-0/collection/slot-0"
    event = boolean_rejection_fixture(folder)
    duplicate = copy.deepcopy(event)
    duplicate["sequence"] = 11
    duplicate["payload"]["model_call_id"] = "fixture-rejected-again"
    for filename in ("episode/experience.json", "team-rollout.json"):
        data = json.loads((folder / filename).read_text())
        data["events"].extend([event, duplicate])
        write(folder / filename, data)
    result = build_report(runs, launches)
    original_arm, arm = original["models"][0]["arms"][0], result["models"][0]["arms"][0]
    exposure = arm["executor_boolean_false_rejection_exposure"]
    assert exposure["confirmed_affected_episodes"] == 1
    assert exposure["confirmed_rejection_calls"] == 2
    assert exposure["unconfirmed_rejection_calls"] == 0
    assert arm["metrics"] == original_arm["metrics"]
    assert arm["eligibility_checks"] == original_arm["eligibility_checks"]
    assert result["models"][0]["paired"] == original["models"][0]["paired"]
    for field in ("candidate_id", "harness", "allocated_device_seconds", "complete_implement_review", "complete_pair_chain"):
        assert result["selection"]["selected"][field] == original["selection"]["selected"][field]
    row = result["models"][0]["rows"][0]["executor_boolean_false_rejection_exposure"]["calls"][0]
    assert row["code_reference"]["version_id"] == "v2"
    assert row["code_ref"]["sha256"] and row["result_ref"]["sha256"]
    assert row["experience_ref"]["sha256"] and row["not_parenthesis_locations"]


def test_boolean_exposure_missing_code_and_quoted_text_stay_unconfirmed(tmp_path):
    from scripts.harness_report_v017 import executor_boolean_exposure

    event = boolean_rejection_fixture(tmp_path, "SELECT 'NOT (false)' AS x /* NOT(true) */")
    write(tmp_path / "episode/experience.json", {"events": [event]})
    result = executor_boolean_exposure(
        [{"kind": "public_observation", "payload": []}, event], reader=Reader(), folder=tmp_path
    )
    assert not result["confirmed_affected"] and result["unconfirmed_rejection_calls"] == 1
    assert result["calls"][0]["reason"] == "no_unquoted_not_parenthesis_in_exact_failed_statement"
    (tmp_path / "world/control/versions/code/v2/data.json").unlink()
    missing = executor_boolean_exposure([event], reader=Reader(), folder=tmp_path)
    assert missing["calls"][0]["status"] == "unconfirmed"
    assert missing["calls"][0]["reason"] == "missing_or_unverified_exact_code_version"
