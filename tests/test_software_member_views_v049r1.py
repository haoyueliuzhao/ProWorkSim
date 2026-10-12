"""Bounded original-record identity controls; no model or tokenizer execution."""
import copy
import json
from pathlib import Path

import pytest

from proworksim import member_views as original
from proworksim import online_training
from proworksim.software_member_views_v049r1 import (
    adaptation_spec, member_view, member_view_from_episode, prepare_window,
)
from proworksim.storage import atomic_write, digest, json_bytes, read_json
from test_member_shared_admission_v033r1 import fixture as old_fixture, reseal


MEMBER, PEER = "member_001", "member_002"


def _write_archive(rollout, folder):
    episode = folder / "episode"
    manifest = rollout["manifest"]
    for index, event in enumerate(rollout["events"]):
        event["sequence"] = index
    manifest["termination"] = copy.deepcopy(rollout["events"][-1]["payload"])
    history = {"events": rollout["events"]}
    atomic_write(episode / "experience.json", json_bytes(history))
    manifest["experience"] = {"path": "experience.json", "sha256": digest(json_bytes(history)),
        "start": 0, "end": len(rollout["events"])}
    atomic_write(episode / "manifest.json", json_bytes(manifest))
    rollout.update(episode_path=str(episode.resolve()), manifest_sha256=digest(json_bytes(manifest)))
    rollout["reward_eligibility"].update(episode_id=rollout["rollout_id"], manifest_sha256=rollout["manifest_sha256"])
    scope = manifest["scenario"]["variation"]["organization_runtime"]
    wrapper = manifest["termination"]["team_budget"]
    result = {"version": scope["version"], "status": "closed", "slot_id": folder.name,
        "case_id": scope["case"]["case_id"], "condition": "O1", "purpose": "policy_training", "training_eligible": True,
        "online_window_id": rollout["window"]["window_id"], "actor_identity": scope["actor_identity"],
        "learning_binding": scope["learning_binding"], "episode_start_steps": scope["episode_start_steps"],
        "team_budget": wrapper, "episode_manifest": str((episode / "manifest.json").resolve()),
        "raw_transport_path": str((folder / "raw-transport").resolve()), "boundary": manifest["termination"]}
    atomic_write(folder / "slot-result.json", json_bytes(result))
    atomic_write(folder / "team-budget.json", json_bytes(wrapper))
    atomic_write(folder / "organization-evidence.json", json_bytes({"team_budget": wrapper}))


def fixture(tmp_path, kind="tokens"):
    rollout = json.loads(json.dumps(old_fixture(kind)).replace("provider", MEMBER).replace("consumer", PEER))
    folder = tmp_path / ("org49-fixture-" + kind)
    actor = rollout["manifest"]["policies"][MEMBER]["config"]["weight_identity"]
    for event in rollout["events"]:
        if event["kind"] not in {"model_attempt", "model_response"}:
            continue
        body = event["payload"]["response"]
        body = body["body"] if event["kind"] == "model_attempt" else body
        body["token_trace"].update(sampling_temperature=.7, sampling_top_p=1, sampling_top_k=0)
    responses = {event["payload"]["call_id"]: event["payload"]["response"]
        for event in rollout["events"] if event["kind"] == "model_response"}
    boundary, final = rollout["events"][-2:]
    for ledger in (boundary["payload"]["team_budget"], final["payload"]["team_budget"]["model"]):
        for call_id, row in ledger["records"].items():
            if row.get("status") == "settled":
                row["charge"]["response_body_sha256"] = digest(json_bytes(responses[call_id]))
        reseal(ledger, "state_sha256")
    final["payload"]["team_budget"].pop("world_instance_id")
    final["payload"]["team_budget"]["slot_id"] = folder.name
    manifest = rollout["manifest"]
    manifest["identity"] = {"world_id": "software-organization-v049", "instance_id": "fixture-instance", "branch_id": "fixture-branch"}
    manifest["episode_id"] = rollout["rollout_id"]
    case = {"purpose": "policy_training", "usage": "policy_training", "training_eligible": True, "condition": "O1", "active_roles": [MEMBER, PEER],
        "training_window_id": rollout["window"]["window_id"], "case_id": "explicit_cpu_identity_fixture"}
    runtime = {"version": "software-organization-runtime-v0.49", "slot_id": folder.name,
        "purpose": "policy_training", "training_eligible": True, "online_window_id": rollout["window"]["window_id"],
        "case": case, "actor_identity": actor, "learning_binding": {"explicit_cpu_fixture": True},
        "episode_start_steps": {"actor_steps": 3, "critic_steps": 3, "policy_revision": 3}}
    manifest["scenario"] = {"variation": {"organization_runtime": runtime, "software_case": case}}
    rollout["online_scope"] = {"purpose": "policy_training", "source_training_admission": True, "optimizer_update_allowed": True}
    for name in ("start", "end"):
        state = {**manifest["identity"], "projects": {"p": {"software": {"case": case}}}}
        atomic_write(folder / "episode" / name / "control/state.json", json_bytes(state))
        manifest[name] = {"path": name, "identity": copy.deepcopy(manifest["identity"]),
            "state": {"path": "control/state.json", "sha256": digest(json_bytes(state))}}
    rollout["window"]["team_policy_fingerprint"] = digest(json_bytes(manifest["policies"]))
    _write_archive(rollout, folder)
    return rollout, folder


@pytest.mark.parametrize("kind", ["tokens", "context"])
def test_source_bound_zero_generation_preserves_original_calls_tokens_and_files(tmp_path, kind):
    rollout, folder = fixture(tmp_path, kind)
    before = {str(path): digest(path.read_bytes()) for path in folder.rglob("*") if path.is_file()}
    old, new = original.member_view(rollout, MEMBER), member_view(rollout, MEMBER)
    assert not old["complete_actor_trajectory"] and new["complete_actor_trajectory"] and new["complete_semantic_trajectory"]
    assert old["decisions"][:-1] == new["decisions"][:-1]
    assert old["own_action_count"] == new["own_action_count"] == 1
    assert old["own_action_tokens"] == new["own_action_tokens"] == 1
    stop = new["decisions"][-1]
    assert stop["actor_required"] is False and stop["generation_status"] == "not_started_shared_admission_rejection"
    assert stop["actual_input"] is stop["actual_response"] is stop["tokens"] is None
    assert stop["non_generation_evidence"]["limits"] == ["team_max_total_tokens" if kind == "tokens" else "context_capacity"]
    assert stop["non_generation_evidence"]["world_identity_attribution"]["original_wrapper_field_absent"]
    assert all(digest(Path(path).read_bytes()) == sha for path, sha in before.items())
    assert "world_instance_id" not in rollout["manifest"]["termination"]["team_budget"]
    thin = {key: value for key, value in rollout.items() if key not in {"episode_path", "manifest_sha256"}}
    assert member_view_from_episode(folder / "episode", thin, MEMBER) == new
    assert "episode_path" not in thin


@pytest.mark.parametrize("change", ["forged_world", "missing_start", "inflight", "tampered_ledger", "cross_episode", "present_wrong_field"])
def test_missing_forged_or_attempted_sources_remain_required_unknown(tmp_path, change):
    rollout, folder = fixture(tmp_path)
    if change == "forged_world":
        path = folder / "episode/start/control/state.json"
        state = read_json(path)
        state["instance_id"] = "other-world"
        atomic_write(path, json_bytes(state))
        rollout["manifest"]["start"]["state"]["sha256"] = digest(json_bytes(state))
        _write_archive(rollout, folder)
    elif change == "missing_start":
        (folder / "episode/start/control/state.json").unlink()
    elif change == "inflight":
        call = rollout["events"][-3]["payload"]["call_id"]
        rollout["events"].insert(-2, {"kind": "model_attempt", "worker_id": MEMBER,
            "payload": {"stage": "started", "call_id": call}})
        _write_archive(rollout, folder)
    elif change == "tampered_ledger":
        for ledger in (rollout["events"][-2]["payload"]["team_budget"], rollout["events"][-1]["payload"]["team_budget"]["model"]):
            ledger["charged_tokens"] += 1
            reseal(ledger, "state_sha256")
        _write_archive(rollout, folder)
    elif change == "cross_episode":
        other, other_folder = fixture(tmp_path / "other")
        other["manifest"]["episode_id"] = other["rollout_id"] = "different-episode"
        _write_archive(other, other_folder)
        rollout["episode_path"] = str(other_folder / "episode")
    elif change == "present_wrong_field":
        rollout["events"][-1]["payload"]["team_budget"]["world_instance_id"] = "wrong-explicit-world"
        _write_archive(rollout, folder)
    view = member_view(rollout, MEMBER)
    assert not view["complete_actor_trajectory"]
    assert view["decisions"][-1]["actor_required"] is True
    assert view["decisions"][-1]["generation_status"] == "unknown_or_missing"


def test_prepare_window_keeps_original_code_and_target_denominators(tmp_path):
    rollout, _ = fixture(tmp_path)
    entry = {"slot_id": "fixture", "active_members": [MEMBER, PEER], "rollout": rollout,
             "reward": rollout["reward_eligibility"]}
    actor = rollout["manifest"]["policies"][MEMBER]["config"]["weight_identity"]
    recipe = {"members": [MEMBER, PEER, "software_inactive"], "max_length": 100,
              "temperature": .7, "credit_assignment": "terminal_mc"}
    old = online_training.prepare_window([entry], actor, rollout["window"]["window_id"], recipe)
    new = prepare_window([entry], actor, rollout["window"]["window_id"], recipe)
    assert len(old["decisions"]) == 1 and len(new["decisions"]) == 2
    assert all(row["actor_denominator"] == row["critic_denominator"] == 2 for row in new["decisions"])
    assert all(row["tokens"]["input_ids"] == [1, 2] and row["tokens"]["output_ids"] == [3] for row in new["decisions"])
    proof = adaptation_spec()
    assert proof["replaced_AST_predicates"] == 1 and proof["all_other_original_AST_nodes_retained"]
    assert proof["member_view_code_object_identical"] and proof["prepare_window_code_object_identical"]
    assert not proof["original_module_globals_modified"] and not proof["mask_criterion_changed"]
