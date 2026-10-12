"""Finite CPU controls for actual Γ1 targets and the unchanged H=1 update code."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from proworksim.online_support import declare_window
from proworksim.online_training import prepare_window, tensor_tree_digest
from proworksim.software_context_v048 import CANDIDATE_SHA256, SoftwareContextTransport, VERSION as CONTEXT_VERSION
from proworksim.software_learning_v029 import migrate_software_owner
from proworksim.software_learning_v049 import (
    VERSION, CRITIC_MEMBERS, MEMBERS, bind_composition, migrate_o1_owner, save_s0_checkpoint, software_feature_function,
    update_software_window, validate_composition, validate_selected_trace, validate_training_entries,
)
from proworksim.storage import digest, json_bytes, read_json
from proworksim.team_rollout import work_validity
from test_software_context_v048 import request as gamma_request
from test_software_learning_v029 import _owner


def _window(owner, folder, s0):
    identity = owner.begin_window("v049-cpu-shared-logical-window")
    policies = {member: {"implementation": "proworksim.model_policy.ModelPolicy", "config": {
        "weight_identity": identity, "model_revision": identity["policy_version"]}} for member in MEMBERS}
    declaration = declare_window(owner.window_id, actor_identity=identity,
        gamma_identity={"source_usage": "policy_training", "optimizer_update_allowed": True,
            "presentation_version": CONTEXT_VERSION, "learning_bridge_version": VERSION,
            "presentation_identity": {"candidate_sha256": CANDIDATE_SHA256, "presentation_version": CONTEXT_VERSION},
            "s0": s0,
            "design_sha256": digest(b"tiny-frozen-design"), "mapper_spec_sha256": digest(b"tiny-frozen-mapper")},
        slot_specs=[{"slot_id": str(index), "xi_id": "LA" if index < 4 else "LB",
            "xi_fingerprint": digest(b"tiny-fixed-root" + str(index // 4).encode()),
            "active_members": list(MEMBERS), "policies": policies, "mapping_spec_id": "tiny-CPU-v049"}
            for index in range(8)])
    transport = SoftwareContextTransport(owner, folder / "contexts", evidence_kind="cpu_programmed_fixture")
    entries = []
    for index, slot in enumerate(declaration["slots"]):
        events = []
        def event(member, kind, payload):
            events.append({"sequence": len(events), "worker_id": member, "kind": kind, "payload": payload})
        for member in MEMBERS:
            call = slot["slot_id"] + "-" + member
            request = json.loads(json.dumps(gamma_request()).replace("member_001", member))
            request.update(model="tiny-cpu", temperature=.7, max_tokens=2)
            for message in request["messages"]:
                for tool_call in message.get("tool_calls", []):
                    tool_call.setdefault("type", "function")
                    tool_call["function"].setdefault("arguments", "{}")
            association = {"worker_id": member, "call_id": call, "decision_index": index + 1}
            transport.bind_turn(member, association)
            prepared = transport.prepare_for_budget(request)
            assert prepared["fits"]
            response = transport.complete(request, timeout_seconds=5)
            transport.unbind_turn(member, association)
            assert response["http_status"] == 200
            event(member, "public_observation", {"work_items": {}, "workspaces": {}})
            event(member, "model_call", {"stage": "started", "call_id": call,
                "request_sha256": digest(json_bytes(request))})
            event(member, "model_attempt", {"stage": "finished", "status": "success", "call_id": call,
                "request": copy.deepcopy(request), "response": response})
            event(member, "model_response", {"call_id": call, "response": response["body"]})
        reward = {"eligible": True, "reward": 0.0 if index == 6 else 1.0,
            "episode_id": "tiny-episode-" + str(index), "manifest_sha256": "tiny-manifest-" + str(index)}
        rollout = {"rollout_id": reward["episode_id"], "manifest_sha256": reward["manifest_sha256"],
            "window": slot["window"], "members": {member: {"origin": "target_model"} for member in MEMBERS},
            "manifest": {"policies": policies}, "events": events, "reward_eligibility": reward,
            "online_scope": {"purpose": "policy_training", "source_training_admission": True, "optimizer_update_allowed": True},
            "work_validity": work_validity([{"dimension": dimension,
                "value": index != 6 or dimension in {"record", "permission", "basis"},
                "evidence": {"explicit_cpu_fixture": True}} for dimension in ("record", "permission", "basis", "delivery")],
                spec_id="tiny-cpu-v049")}
        entries.append({"slot_id": slot["slot_id"], "active_members": list(MEMBERS), "rollout": rollout,
            "reward": reward, "mapping": {"status": "unmapped" if index == 7 else "mapped"}, "training_eligible": True})
    return entries, declaration


def _binding(declaration, *, direction=False):
    return {"declaration_sha256": digest(json_bytes(declaration)),
        "design_sha256": declaration["gamma_identity"]["design_sha256"],
        "mapper_spec_sha256": declaration["gamma_identity"]["mapper_spec_sha256"],
        "support_artifact_sha256": digest(b"tiny-support"),
        "selected_direction_artifact_sha256": digest(b"tiny-direction") if direction else None}


def test_cpu_gamma1_full_state_unit_composition_observer_and_updated_reload(tmp_path):
    try:
        import torch
    except ModuleNotFoundError:
        project = Path(__file__).resolve().parents[1]
        code = ("import sys; sys.path.extend(" + repr([path for path in sys.path if "site-packages" in path])
            + "); import pytest; raise SystemExit(pytest.main(" + repr([
                str(Path(__file__).resolve()) + "::test_cpu_gamma1_full_state_unit_composition_observer_and_updated_reload",
                "-q", "--basetemp=" + str(tmp_path / "torch-control")]) + "))")
        result = subprocess.run([str(project / ".train-venv/bin/python"), "-c", code], cwd=project,
            text=True, capture_output=True, timeout=180, env={**os.environ, "CUDA_VISIBLE_DEVICES": ""})
        assert result.returncode == 0, result.stdout + result.stderr
        return
    assert not torch.cuda.is_initialized()
    torch.manual_seed(49)
    owner = _owner(tmp_path, torch)
    owner.recipe["max_length"] = 12000
    migrate_software_owner(owner, expected_steps=(0, 0))
    # Nonempty existing Adam moments, explicit toy CPU fixture only.
    sum(parameter.square().sum() + parameter.sum() for parameter in owner.actor_parameters.values()).backward()
    owner.actor_optimizer.step()
    sum(parameter.square().sum() + parameter.sum() for parameter in owner.critic.parameters()).backward()
    owner.critic_optimizer.step()
    owner.actor_optimizer.zero_grad(set_to_none=True)
    owner.critic_optimizer.zero_grad(set_to_none=True)
    owner.actor_steps = owner.critic_steps = owner.policy_revision = 1
    owner.critic_has_nonzero_reward_history = True
    owner._identity = owner._make_identity()
    before = owner._state_bundle()
    migration = migrate_o1_owner(owner)
    assert all(migration["protected_state_unchanged"].values())
    assert owner.recipe["members"] == list(CRITIC_MEMBERS)
    assert tensor_tree_digest(before["critic_optimizer"], torch) == tensor_tree_digest(owner.critic_optimizer.state_dict(), torch)
    with pytest.raises(ValueError, match="original software"):
        migrate_o1_owner(owner)
    old_events = [{"sequence": 0, "worker_id": "member_a", "kind": "public_observation",
        "payload": {"work_items": {"w": {"status": "accepted"}}, "workspaces": {}}}]
    new_events = copy.deepcopy(old_events)
    new_events[0]["worker_id"] = MEMBERS[0]
    from proworksim.software_learning_v029 import software_feature_function as old_features
    assert software_feature_function(new_events, 1, MEMBERS[0])[0] == old_features(old_events, 1, "member_a")[0]
    origin = tmp_path / "S0"
    s0 = save_s0_checkpoint(owner, origin)
    initial_rng = {"cpu": torch.get_rng_state().clone(), "cuda": []}
    entries, declaration = _window(owner, tmp_path, s0)
    # The production collector restores only RNG after each frozen episode.
    torch.set_rng_state(initial_rng["cpu"])
    proof = validate_training_entries(owner, entries, declaration, request_evidence_root=tmp_path / "contexts")
    assert proof["original_slot_count"] == 8 and proof["admitted_decisions"] == 16
    assert {row["actor_denominator"] for row in proof["rows"]} == {32}
    assert {row["critic_denominator"] for row in proof["rows"]} == {16}
    assert all(row["same_input_reference_count"] == 5 for row in proof["rows"])
    assert {row["slot_id"] for row in proof["rows"]} == {str(index) for index in range(8)}
    folder = tmp_path / "contexts/request-00001"
    original, selected = read_json(folder / "original-request.json"), read_json(folder / "selected-request.json")
    assert selected != original and "$same_input_ref" in json.dumps(selected)
    response = read_json(folder / "response.json")["body"]
    bad = copy.deepcopy(response)
    bad["token_trace"]["input_ids"] = owner.tokenizer(owner.prepare_request(original)[0])["input_ids"]
    with pytest.raises(ValueError, match="original/native response"):
        validate_selected_trace(owner, original=original, actual=bad, folder=folder, member_id=MEMBERS[0], call_id="0-" + MEMBERS[0])
    with pytest.raises(ValueError, match="runner/member/call"):
        validate_selected_trace(owner, original=original, actual=response, folder=folder, member_id=MEMBERS[1], call_id="0-" + MEMBERS[0])
    invalid = copy.deepcopy(declaration)
    invalid["gamma_identity"]["source_usage"] = "policy_development"
    with pytest.raises(ValueError, match="policy-training"):
        validate_training_entries(owner, entries, invalid, request_evidence_root=tmp_path / "contexts")
    invalid_entries = copy.deepcopy(entries)
    invalid_entries[0]["rollout"]["online_scope"]["purpose"] = "policy_development"
    with pytest.raises(ValueError, match="Development"):
        validate_training_entries(owner, invalid_entries, declaration, request_evidence_root=tmp_path / "contexts")
    unit_weights = {entry["slot_id"]: dict.fromkeys(MEMBERS, 1.0) for entry in entries}
    unit = bind_composition(entries, declaration, unit_weights, binding=_binding(declaration))
    weighted_values = copy.deepcopy(unit_weights)
    for sid in ("0", "1"):
        weighted_values[sid][MEMBERS[0]] = 1.1
    for sid in ("2", "3"):
        weighted_values[sid][MEMBERS[0]] = .9
    weighted = bind_composition(entries, declaration, weighted_values, binding=_binding(declaration, direction=True))
    prepared = prepare_window(entries, owner.freeze_identity(), declaration["window_id"], owner.recipe, software_feature_function)
    tampered = copy.deepcopy(prepared)
    tampered["decisions"][0]["actor_denominator"] //= 2
    with pytest.raises(ValueError, match="fixed base denominators"):
        validate_composition(entries, tampered, unit)
    tampered = copy.deepcopy(prepared)
    tampered["decisions"].reverse()
    with pytest.raises(ValueError, match="accumulation order"):
        validate_composition(entries, tampered, unit)
    changed_seal = copy.deepcopy(unit)
    changed_seal["weights_by_slot"]["0"][MEMBERS[0]] = 1.1
    with pytest.raises(ValueError, match="block mass"):
        validate_composition(entries, prepared, changed_seal)
    owner.finish_evaluation([], tmp_path / "collection-close")
    outcomes = {}
    for name, composition, observer in (("original", None, False), ("unit", unit, False),
                                         ("observer", unit, True), ("weighted", weighted, False)):
        owner.restore_checkpoint(origin)
        owner.begin_window(declaration["window_id"])
        output = tmp_path / ("update-" + name)
        if name == "original":
            report = owner.update_window(entries, output, feature_function=software_feature_function)
        else:
            report = update_software_window(owner, entries, output, declaration=declaration,
                request_evidence_root=tmp_path / "contexts", composition=composition, observe_support_gradients=observer)
        assert report["status"] == "updated"
        assert report["actor_optimizer_steps"] == report["critic_optimizer_steps"] == 1
        assert report["backward_decisions_completed"] == 16
        outcomes[name] = {"state": owner._state_bundle(), "report": report,
            "gradients": torch.load(output / "gradients-before-clip.pt", weights_only=True),
            "losses": read_json(output / "losses.json")}
    baseline = outcomes["original"]
    for name in ("unit", "observer"):
        assert tensor_tree_digest(outcomes[name]["state"], torch) == tensor_tree_digest(baseline["state"], torch)
        assert tensor_tree_digest(outcomes[name]["gradients"], torch) == tensor_tree_digest(baseline["gradients"], torch)
        assert outcomes[name]["losses"] == baseline["losses"]
    changed = outcomes["weighted"]
    assert changed["report"]["advantages"] == baseline["report"]["advantages"]
    assert tensor_tree_digest(changed["gradients"]["actor"], torch) != tensor_tree_digest(baseline["gradients"]["actor"], torch)
    assert tensor_tree_digest(changed["state"]["actor"], torch) != tensor_tree_digest(baseline["state"]["actor"], torch)
    for key in ("critic", "critic_optimizer"):
        assert tensor_tree_digest(changed["state"][key], torch) == tensor_tree_digest(baseline["state"][key], torch)
    assert all(row["composition_weight"] == 1 for row in changed["losses"] if row["slot_id"] in ("6", "7"))
    observed = read_json(tmp_path / "update-observer/support-gradients.json")
    assert len(observed["groups"]) == 16 and observed["additional_actor_backwards"] == 0
    assert all(row["parameters"] == len(owner.actor_parameters) for row in observed["groups"])
    consumption = read_json(tmp_path / "update-observer/software-consumption.json")
    assert consumption["actor_forwards_completed"] == 32
    assert consumption["actor_backward_decisions_completed"] == consumption["critic_backward_decisions_completed"] == 16
    receipt = read_json(tmp_path / "update-observer-original-updater-binding.json")
    assert receipt["code_object_identical"] and receipt["closure_identical"] and receipt["defaults_identical"]
    assert receipt["private_global_overrides"] == ["validate_actor_composition", "GroupGradientCapture"]
    checkpoint = owner.save_checkpoint(tmp_path / "updated-state")
    owner.restore_checkpoint(origin)
    assert owner.freeze_identity() != checkpoint["actor_identity"]
    owner.restore_checkpoint(tmp_path / "updated-state")
    assert owner.freeze_identity() == checkpoint["actor_identity"]
    guard = owner.capture_evaluation_state()
    owner.begin_window("v049-new-development-state")
    owner.finish_evaluation([], tmp_path / "development-close")
    result = owner.finish_evaluation_guard(guard)
    assert result["learning_unchanged"] and result["rng_restored_exactly"]
    assert not torch.cuda.is_initialized()


@pytest.mark.parametrize("member,order", [("member_a", CRITIC_MEMBERS), (MEMBERS[0], ("member_a", "member_b", "software_inactive"))])
def test_critic_rejects_implicit_coordinate_aliases(member, order):
    with pytest.raises(ValueError, match="explicitly frozen"):
        software_feature_function([], 0, member, order)


def test_inactive_coordinate_cannot_receive_actions():
    with pytest.raises(ValueError, match="Inactive critic"):
        software_feature_function([{"worker_id": "software_inactive"}], 0, MEMBERS[0])
