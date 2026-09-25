"""Synthetic admission fixtures, not observed model success or team support."""

import copy
import importlib.util
from pathlib import Path

import pytest

from proworksim.storage import digest, json_bytes, read_json

_SPEC = importlib.util.spec_from_file_location(
    "multiturn_ppo_v012", Path(__file__).parents[1] / "scripts/multiturn_ppo_v012.py"
)
ppo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ppo)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))
    return digest(path.read_bytes())


def inventory_fixture(tmp_path, rewards=(0.0, 1.0, 0.0, 1.0)):
    """Every response/token below is explicitly synthetic offline fixture data."""
    weight = tmp_path / "base-manifest.json"
    weightsha = write(weight, {"declared_hf_revision": "synthetic-base"})
    gate = tmp_path / "d0-gate.json"
    gatesha = write(gate, {"synthetic_independent_gate": True})
    profile = {
        "dtype": "float32",
        "actual_parameter_dtype": "torch.float32",
        "max_batch": 1,
        "attention": "sdpa",
    }
    profile_sha = digest(json_bytes(profile))
    service = tmp_path / "service.json"
    servicesha = write(
        service,
        {
            "adapter": None,
            "policy_version": "synthetic-base",
            "inference_profile": profile,
            "inference_profile_sha256": profile_sha,
        },
    )
    service_records = tmp_path / "service-records"
    slots = []
    for slot_index, reward in enumerate(rewards):
        root = tmp_path / f"synthetic-slot-{slot_index}"
        events = []

        def event(member, kind, payload):
            events.append(
                {"sequence": len(events), "worker_id": member, "kind": kind, "payload": payload}
            )

        policies = {}
        for member in ppo.MEMBERS:
            policies[member] = {
                "implementation": "proworksim.model_policy.ModelPolicy",
                "config": {
                    "backend_id": "local-qwen-http",
                    "model_revision": "synthetic-base",
                    "weight_identity": {"manifest": str(weight), "manifest_sha256": weightsha},
                },
            }
            event(
                member,
                "public_observation",
                {
                    "work_items": {"work": {"status": "open"}},
                    "workspaces": {"TEAM": {"source": "obj"}},
                },
            )
            for number in range(2):
                cid = f"synthetic-{slot_index}-{member}-{number}"
                request = {
                    "model": "synthetic-model",
                    "messages": [{"role": "user", "content": f"public-input-{member}"}],
                }
                trace = {
                    "input_ids": [1, 2],
                    "output_ids": [3, 4],
                    "input_mask": [0, 0],
                    "output_mask": [1, 1],
                    "behavior_logprobs": [-0.3, -0.4],
                    "sampling_temperature": 0.3,
                    "sampling_top_p": 1.0,
                    "sampling_top_k": 0,
                    "source": "actual generation token IDs and sampling logits, not retokenized text",
                }
                response = {
                    "id": cid,
                    "system_fingerprint": "synthetic-base",
                    "token_trace": trace,
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "synthetic raw output"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
                    "inference_profile": profile,
                    "inference_profile_sha256": profile_sha,
                    "service_record": {"batch_size": 1},
                    "effective_generation": {
                        "do_sample": True,
                        "temperature": 1.0,
                        "top_p": 1.0,
                        "top_k": 0,
                        "repetition_penalty": 1.0,
                    },
                }
                write(service_records / (cid + ".json"), {"request": request, "response": response})
                event(
                    member,
                    "model_call",
                    {
                        "stage": "started",
                        "call_id": cid,
                        "decision_index": number + 1,
                        "opportunity_id": cid + "-op",
                        "request_sha256": digest(json_bytes(request)),
                    },
                )
                event(
                    member,
                    "model_attempt",
                    {
                        "stage": "finished",
                        "call_id": cid,
                        "status": "success",
                        "request": request,
                        "response": {"body": response},
                    },
                )
                event(member, "model_response", {"call_id": cid, "response": response})
        hsha = write(root / "experience.json", {"events": events})
        source = {
            "code_commit": "synthetic-offline",
            "code_dirty": False,
            "source_tree_sha256": "synthetic-source",
        }
        manifest = {
            "policies": policies,
            "source_start": source,
            "source_end": source,
            "experience": {
                "path": "experience.json",
                "sha256": hsha,
                "start": 0,
                "end": len(events),
            },
        }
        msha = write(root / "manifest.json", manifest)
        rollout = {
            "version": "team-rollout-v0.12",
            "rollout_id": root.name,
            "episode_path": str(root),
            "manifest": manifest,
            "manifest_sha256": msha,
            "members": {m: {"origin": "target_model", "actor_id": m} for m in ppo.MEMBERS},
            "events": events,
            "reward_eligibility": {"eligible": True, "reward": reward},
            "work_validity": {
                "components": {
                    "record": {"value": True},
                    "permission": {"value": False},
                    "basis": {"value": False},
                    "delivery": {"value": False},
                }
            },
            "window": {
                "window_id": "synthetic-collection",
                "xi_id": f"xi-{slot_index}",
                "xi_fingerprint": f"xi-fp-{slot_index}",
                "gamma_fingerprint": "same-gamma",
                "team_policy_fingerprint": "same-policy",
            },
        }
        tpath = root / "team-rollout.json"
        tsha = write(tpath, rollout)
        slots.append(
            {"slot_id": root.name, "team_rollout": str(tpath), "team_rollout_sha256": tsha}
        )
    inventory = {
        "version": "multiturn-ppo-inventory-v0.12",
        "member_ids": ppo.MEMBERS,
        "slots": slots,
        "expected_policy": {
            "system_fingerprint": "synthetic-base",
            "weight_manifest_sha256": weightsha,
            "inference_profile_sha256": profile_sha,
            "service_manifest_sha256": servicesha,
        },
        "service_manifest": str(service),
        "service_records": str(service_records),
        "d0_gate": {
            "path": str(gate),
            "sha256": gatesha,
            "field_path": ["synthetic_independent_gate"],
        },
    }
    path = tmp_path / "inventory.json"
    write(path, inventory)
    return path


def test_full_four_slot_all_member_all_decision_admission_and_fixed_denominators(tmp_path):
    path = inventory_fixture(tmp_path)
    prepared = ppo.prepare_inventory(path)
    assert prepared["all_pre_gpu_gates_passed"], prepared["errors"]
    assert len(prepared["slots"]) == 4 and len(prepared["decisions"]) == 24
    assert all(row["actor_denominator"] == 4 * 3 * 4 for row in prepared["decisions"])
    assert all(row["critic_denominator"] == 4 * 3 * 2 for row in prepared["decisions"])
    assert all(
        row["loss_mask"] == [0, 0, 1, 1] and row["labels"] == [-100, -100, 3, 4]
        for row in prepared["decisions"]
    )
    assert {row["reward"] for row in prepared["decisions"]} == {0.0, 1.0}
    assert all(row["composition_weight"] == 1.0 for row in prepared["decisions"])


def test_equal_zero_rewards_are_retained_and_do_not_pass_learning_signal_gate(tmp_path):
    prepared = ppo.prepare_inventory(inventory_fixture(tmp_path, rewards=(0.0, 0.0, 0.0, 0.0)))
    assert prepared["status"] == "not_run_data_or_learning_signal_gate"
    assert prepared["gates"]["all_four_complete_trusted_slots"]
    assert not prepared["gates"]["credible_return_differences"]
    assert len(prepared["decisions"]) == 24


def test_missing_slot_does_not_shrink_inventory_or_enable_training(tmp_path):
    path = inventory_fixture(tmp_path)
    inventory = read_json(path)
    Path(inventory["slots"][1]["team_rollout"]).unlink()
    prepared = ppo.prepare_inventory(path)
    assert len(prepared["slots"]) == 4 and len(prepared["fixed_slot_ids"]) == 4
    assert prepared["slots"][1]["errors"] and not prepared["all_pre_gpu_gates_passed"]
    assert all(row["actor_denominator"] == 48 for row in prepared["decisions"])


def test_d0_gate_is_read_from_exact_original_report_not_hand_filled(tmp_path):
    path = inventory_fixture(tmp_path)
    inventory = read_json(path)
    write(Path(inventory["d0_gate"]["path"]), {"synthetic_independent_gate": False})
    prepared = ppo.prepare_inventory(path)
    assert not prepared["gates"]["independent_d0_passed"]
    assert not prepared["all_pre_gpu_gates_passed"]


def test_tampered_service_response_is_not_recovered_by_retokenization(tmp_path):
    path = inventory_fixture(tmp_path)
    inventory = read_json(path)
    ledger = next(Path(inventory["service_records"]).glob("*.json"))
    data = read_json(ledger)
    data["response"]["token_trace"]["output_ids"][0] = 999
    write(ledger, data)
    prepared = ppo.prepare_inventory(path)
    assert not prepared["all_pre_gpu_gates_passed"]
    assert any("ledger differs" in row["error"] for row in prepared["errors"])


def test_past_critic_features_ignore_future_reward_text_and_later_observation():
    events = [
        {
            "sequence": 0,
            "worker_id": "provider",
            "kind": "public_observation",
            "payload": {"work_items": {"w": {"status": "open"}}, "secret_business_number": 999},
        },
        {
            "sequence": 1,
            "worker_id": "provider",
            "kind": "tool_call",
            "payload": {"response": {"ok": True}},
        },
        {
            "sequence": 2,
            "worker_id": "implementer",
            "kind": "model_call",
            "payload": {"stage": "started"},
        },
        {
            "sequence": 3,
            "worker_id": "provider",
            "kind": "public_observation",
            "payload": {"work_items": {"w": {"status": "accepted"}}, "reward": 1},
        },
    ]
    first = ppo.past_features(events, 2, "implementer", ppo.MEMBERS)
    changed = copy.deepcopy(events)
    changed[0]["payload"]["secret_business_number"] = -5
    changed[3]["payload"] = {"work_items": {"future-new": {"status": "blocked"}}, "reward": 0}
    assert first == ppo.past_features(changed, 2, "implementer", ppo.MEMBERS)
    assert len(first[0]) == 30
    assert first[1]["latest_observation_sequences"] == {"provider": 0}


def test_new_probability_thresholds_are_fixed_and_full_length():
    assert ppo.probability_check([-0.3, -0.4], [-0.3, -0.4])["passed"]
    assert not ppo.probability_check([-0.321, -0.4], [-0.3, -0.4])["passed"]
    assert ppo.RECIPE["max_length"] == 16384
    with pytest.raises(ValueError):
        ppo.probability_check([-0.3], [-0.3, -0.4])


def test_actual_torch_full_q_equals_b_update_identity():
    pytest.importorskip("torch")
    result = ppo.cpu_self_check()
    assert result["all_passed"] and not result["cuda_initialized"]
