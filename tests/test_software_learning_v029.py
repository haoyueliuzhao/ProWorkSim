"""Real tiny CPU LoRA/optimizer controls; no 9B work or allocation-effect claim."""

import copy
import math
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from proworksim.experience_allocation_v027 import (
    bind_candidate, candidate_materialization, freeze_allocation_plan,
)
from proworksim.online_support import declare_window
from proworksim.online_training import SharedActor, tensor_tree_digest
from proworksim.software_context_v028 import SoftwareContextTransport
from proworksim.software_learning_v029 import (
    CRITIC_MEMBERS, MEMBERS, PROTECTED_STATE, allocation_gate, migrate_software_owner,
    restore_common, software_feature_function, update_software_window, validate_training_entries,
)
from proworksim.storage import digest, json_bytes, read_json
from proworksim.team_rollout import work_validity
from test_experience_allocation_v027 import manifest
from test_online_support_v013 import declaration, rollout


def test_gate_preserves_original_eight_failure_and_unmapped_residuals():
    decl = declaration(active=MEMBERS, slots=8, xi="same-case::first=member_a")
    entries, records = [], []
    for index, slot in enumerate(decl["slots"]):
        row = rollout(decl, slot["slot_id"], valid=index != 6)
        category = ["A", "A", "A", "B", "B", "rare", None, None][index]
        mapping = {"rollout_id": row["rollout_id"], "spec_id": slot["mapping_spec_id"],
                   "status": "mapped" if category else "unmapped", "class_id": category}
        entries.append({"slot_id": slot["slot_id"], "rollout": row, "mapping": mapping,
                        "reward": row["reward_eligibility"], "active_members": list(MEMBERS)})
        records.append({"slot_id": slot["slot_id"], "status": "closed", "rollout": row, "mapping": mapping})
    gate = allocation_gate(entries, decl, records)
    xi = decl["slots"][0]["xi_id"]
    assert gate["eligible_blocks"] == [[xi, "member_a"]]
    assert gate["supports_by_xi"][xi]["blocks"]["member_a"]["M"] == 8
    plan = freeze_allocation_plan(gate["supports_by_xi"], eligible_blocks=gate["eligible_blocks"],
        development=manifest(), budget={"max_trial_updates_per_method": 20,
            "max_development_evaluations_per_method": 60, "formal_updates_per_method": 1})
    assert plan["methods"]["G"]["required_trial_updates"] == 9
    assert plan["methods"]["I"]["required_trial_updates"] == 3
    for candidate in plan["candidates"]:
        mat = candidate_materialization(plan, candidate)[xi]["members"]
        assert all(value == 1 for value in mat["member_b"]["weights"].values())
        assert all(mat["member_a"]["weights"][str(i)] == 1 for i in (5, 6, 7))
        assert mat["member_a"]["actor_mask"]["6"] is True
        assert sum(mat["member_a"]["weights"].values()) == pytest.approx(8)
    unknown = copy.deepcopy(records)
    unknown[0] = {"slot_id": "0", "status": "closed_unassessed"}
    assert allocation_gate(entries, decl, unknown)["status"] == "incomplete_keep_original_inventory"
    with pytest.raises(ValueError, match="eight raw slots"):
        allocation_gate(entries[:-1], decl, records)


def _owner(tmp_path, torch, name="owner"):
    class TinyLoRA(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.base_head = torch.nn.Linear(2, 11, bias=False)
            self.base_head.requires_grad_(False)
            self.lora_A = torch.nn.Parameter(torch.tensor([[0.1, 0.2], [0.3, -0.1]]))
            self.lora_B = torch.nn.Parameter(torch.zeros(11, 2))
            self.config = SimpleNamespace(attention_dropout=0, use_cache=False)
            self.generation_config = SimpleNamespace(eos_token_id=99)

        def gradient_checkpointing_enable(self, **kwargs):
            pass

        def logits(self):
            hidden = self.lora_A.new_tensor([1.0, 2.0])
            return self.base_head(hidden) + self.lora_B @ (self.lora_A @ hidden)

        def forward(self, input_ids, attention_mask, use_cache, logits_to_keep):
            return SimpleNamespace(logits=self.logits()[None, None, :].expand(1, logits_to_keep, -1))

        def generate(self, input_ids, logits_processor, max_new_tokens, **kwargs):
            ids = input_ids
            for _ in range(max_new_tokens):
                scores = logits_processor[0](ids, self.logits()[None, :])
                ids = torch.cat([ids, torch.multinomial(scores.softmax(-1), 1)], dim=1)
            return ids

    class Tokenizer:
        pad_token_id = 0

        def apply_chat_template(self, messages, *args, **kwargs):
            return "|".join(message.get("content", "") or "" for message in messages)

        def __call__(self, text, **kwargs):
            return {"input_ids": [ord(value) % 10 for value in text]}

        def decode(self, ids, **kwargs):
            return "actual tiny CPU output " + str(ids)

    return SharedActor(TinyLoRA(), Tokenizer(), output=tmp_path / name,
        base_identity={"manifest": {"sha256": digest(b"actual-tiny-cpu-fixture")}},
        inference_profile={"native_tool_prompt": "single_call", "fixture": True},
        recipe={"max_length": 64, "max_output_tokens": 2, "diagnostic_max_groups": 0,
                "post_update_max_decisions": 0}, device="cpu", torch_module=torch)


def _real_window(owner, tmp_path):
    identity = owner.begin_window("actual-cpu-window")
    policies = {member: {"implementation": "proworksim.model_policy.ModelPolicy", "config": {"weight_identity": identity,
        "model_revision": identity["policy_version"]}} for member in MEMBERS}
    decl = declare_window(owner.window_id, actor_identity=identity,
        gamma_identity={"explicit_tiny_CPU_control": True}, min_class_count=2,
        slot_specs=[{"slot_id": str(i), "xi_id": "same::first=member_a", "xi_fingerprint": digest(b"fixed"),
            "active_members": list(MEMBERS), "policies": policies, "mapping_spec_id": "synthetic-control"}
            for i in range(8)])
    transport = SoftwareContextTransport(owner, tmp_path / "contexts")
    request = {"messages": [{"role": "user", "content": "task"},
        {"role": "assistant", "content": "old" * 40,
         "tool_calls": [{"id": "old", "type": "function", "function": {"name": "f", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "old", "content": "old result"},
        {"role": "assistant", "content": "latest", "tool_calls": [
            {"id": "new", "type": "function", "function": {"name": "f", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "new", "content": "new result"}],
        "model": "tiny", "temperature": 0.7, "max_tokens": 2}
    entries, records = [], []
    for i, slot in enumerate(decl["slots"]):
        sid, events = slot["slot_id"], []
        def event(member, kind, payload):
            events.append({"sequence": len(events), "worker_id": member, "kind": kind, "payload": payload})
        for member in MEMBERS:
            call = sid + "-" + member
            response = transport.complete(request, timeout_seconds=5)
            assert response["http_status"] == 200
            event(member, "public_observation", {})
            event(member, "model_call", {"stage": "started", "call_id": call,
                                         "request_sha256": digest(json_bytes(request))})
            event(member, "model_attempt", {"stage": "finished", "status": "success",
                "call_id": call, "request": copy.deepcopy(request), "response": response})
            event(member, "model_response", {"call_id": call, "response": response["body"]})
        reward = {"eligible": True, "reward": 0.0 if i == 6 else 1.0,
                  "episode_id": "episode-" + sid, "manifest_sha256": "manifest-" + sid}
        result = {"rollout_id": reward["episode_id"], "manifest_sha256": reward["manifest_sha256"],
            "window": slot["window"], "members": {member: {"origin": "target_model"} for member in MEMBERS},
            "manifest": {"policies": copy.deepcopy(policies)}, "events": events, "reward_eligibility": reward,
            "work_validity": work_validity([{"dimension": dimension, "value": i != 6 or dimension == "record",
                "evidence": {"fixture": True}} for dimension in ("record", "permission", "basis", "delivery")], spec_id="cpu")}
        category = ["A", "A", "A", "B", "B", "B", None, None][i]
        mapping = {"rollout_id": result["rollout_id"], "spec_id": "synthetic-control",
                   "status": "mapped" if category else "unmapped", "class_id": category}
        entries.append({"slot_id": sid, "active_members": list(MEMBERS), "rollout": result,
                        "reward": reward, "mapping": mapping})
        records.append({"slot_id": sid, "status": "closed", "rollout": result, "mapping": mapping})
    return entries, decl, records


def test_real_cpu_lora_full_state_migration_restore_weighted_window_and_probability_gate(tmp_path):
    try:
        import torch
    except ModuleNotFoundError:
        # The project test venv intentionally omits Torch; use the existing
        # CPU-capable training interpreter without installing any package.
        project = Path(__file__).resolve().parents[1]
        interpreter = project / ".train-venv/bin/python"
        assert interpreter.is_file(), "Real CPU learner control needs the existing training interpreter"
        code = ("import sys; sys.path.extend(" + repr([path for path in sys.path if "site-packages" in path])
                + "); import pytest; raise SystemExit(pytest.main(" + repr([
                    str(Path(__file__).resolve()) + "::" + test_real_cpu_lora_full_state_migration_restore_weighted_window_and_probability_gate.__name__,
                    "-q", "--basetemp=" + str(tmp_path / "torch-control")]) + "))")
        result = subprocess.run([str(interpreter), "-c", code], cwd=project,
                                text=True, capture_output=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
        return
    torch.manual_seed(29)
    owner = _owner(tmp_path, torch)
    # Populate persistent optimizer moments to make preservation stronger than
    # comparing empty optimizer dictionaries at a newly initialized boundary.
    owner.actor_optimizer.zero_grad()
    owner.model.logits().sum().backward()
    owner.actor_optimizer.step()
    owner.critic_optimizer.zero_grad()
    owner.critic(torch.zeros(30)).sum().backward()
    owner.critic_optimizer.step()
    owner.actor_steps = owner.critic_steps = owner.policy_revision = 1
    owner.critic_has_nonzero_reward_history = True
    owner._identity = owner._make_identity()
    before = owner._state_bundle()
    migration = migrate_software_owner(owner, tmp_path / "migration.json", expected_steps=(1, 1))
    assert all(migration["protected_state_unchanged"].values())
    assert set(migration["protected_state_unchanged"]) == set(PROTECTED_STATE)
    assert owner.recipe["members"] == list(CRITIC_MEMBERS)
    common = tmp_path / "common"
    owner.save_checkpoint(common)
    entries, decl, records = _real_window(owner, tmp_path)
    proof = validate_training_entries(owner, entries, decl, request_evidence_root=tmp_path / "contexts")
    assert proof["admitted_decisions"] == 16
    assert all(row["omitted_sdk_message_count"] == 2 for row in proof["rows"])
    assert {row["actor_denominator"] for row in proof["rows"]} == {32}
    assert {row["critic_denominator"] for row in proof["rows"]} == {16}
    gate = allocation_gate(entries, decl, records)
    plan = freeze_allocation_plan(gate["supports_by_xi"], eligible_blocks=gate["eligible_blocks"],
        development=manifest(), budget={"max_trial_updates_per_method": 20,
            "max_development_evaluations_per_method": 60, "formal_updates_per_method": 1})
    candidate = next(key for key in plan["candidates"] if key.startswith("I-"))
    composition = bind_candidate(entries, decl, records, plan, candidate)
    old_values = {member: float(owner.critic(torch.tensor(software_feature_function(
        [], 0, member)[0])).squeeze().detach()) for member in MEMBERS}
    report = update_software_window(owner, entries, tmp_path / "weighted", declaration=decl,
                                   request_evidence_root=tmp_path / "contexts", composition=composition)
    assert report["status"] == "updated"
    assert report["backward_decisions_completed"] == 16
    assert report["actor_optimizer_steps"] == report["critic_optimizer_steps"] == 1
    assert report["behavior_probability_passed"] is True
    assert owner.actor_steps == owner.critic_steps == 2
    losses = read_json(tmp_path / "weighted/losses.json")
    xi = decl["slots"][0]["xi_id"]
    mat = candidate_materialization(plan, candidate)[xi]["members"]
    for row in losses:
        sid, member = row["slot_id"], row["member_id"]
        weight = mat[member]["weights"][sid]
        reward = entries[int(sid)]["reward"]["reward"]
        assert row["composition_weight"] == weight
        assert row["actor_loss"] == pytest.approx(-(reward - old_values[member]) / 16 * weight, abs=1e-6)
    assert tensor_tree_digest(before["actor"], torch) != tensor_tree_digest(owner.actor_state(), torch)
    actual = read_json(tmp_path / "weighted/software-consumption.json")
    assert actual["elapsed_seconds"] > 0 and actual["backward_decisions_completed"] == 16
    restored = restore_common(owner, common, decl["window_id"])
    assert restored["complete_state_exact"] is True
    assert owner.actor_steps == owner.critic_steps == 1
    for key in PROTECTED_STATE:
        if key not in {"last_window_id", "used_window_ids"}:
            assert tensor_tree_digest(owner._state_bundle()[key], torch) == tensor_tree_digest(before[key], torch)
    # Wrong sampled probabilities reach the original probability gate; this is
    # intentionally internally consistent evidence, not a format-gate test.
    corrupt = copy.deepcopy(entries)
    for event in corrupt[0]["rollout"]["events"]:
        response = (event["payload"].get("response", {}).get("body") if event["kind"] == "model_attempt"
                    else event["payload"].get("response") if event["kind"] == "model_response" else None)
        if response:
            trace = response["token_trace"]
            trace["behavior_logprobs"] = trace["raw_behavior_logprobs"] = [-9.0] * len(trace["output_ids"])
    # Bridge rejects archive drift before any learner execution.
    with pytest.raises(ValueError, match="sampled response differ"):
        validate_training_entries(owner, corrupt, decl, request_evidence_root=tmp_path / "contexts")
    # Separately exercise the inherited numeric gate with truthful token masks.
    mismatch = owner.update_window(corrupt, tmp_path / "probability-mismatch", feature_function=software_feature_function)
    assert mismatch["status"] == "zero_step_probability_mismatch"
    assert owner.actor_steps == owner.critic_steps == 1
    assert tensor_tree_digest(owner.actor_optimizer.state_dict(), torch) == tensor_tree_digest(before["actor_optimizer"], torch)
    assert tensor_tree_digest(owner.critic_optimizer.state_dict(), torch) == tensor_tree_digest(before["critic_optimizer"], torch)
    # This is the runner's independent worker bootstrap: original constructor,
    # explicit software binding, then the new common full-state restoration.
    torch.manual_seed(29)
    fresh = _owner(tmp_path, torch, "fresh-candidate-worker")
    migrate_software_owner(fresh, expected_steps=None)
    fresh_restore = restore_common(fresh, common, decl["window_id"])
    assert fresh_restore["state_sha256"] == restored["state_sha256"]
    assert fresh.actor_steps == fresh.critic_steps == 1


def test_critic_uses_strictly_past_two_members_and_inactive_zero_coordinate():
    events = [{"sequence": 0, "worker_id": "member_a", "kind": "tool_call",
               "payload": {"response": {"ok": True}}},
              {"sequence": 2, "worker_id": "member_b", "kind": "tool_call",
               "payload": {"response": {"ok": False}}}]
    features, proof = software_feature_function(events, 1, "member_a")
    assert len(features) == 30 and features[7] == 0.01
    assert features[18:27] == [0] * 9 and features[27:] == [1, 0, 0]
    assert math.isclose(sum(features), 1.01)
    assert proof["before_event_sequence"] == 1
    with pytest.raises(ValueError, match="inactive"):
        software_feature_function([{"worker_id": "software_inactive"}], 1, "member_a")
