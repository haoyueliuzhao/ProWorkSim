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
    # A real-shaped pinned collection fixture, separate from the per-xi windows.
    registry = {
        "version": "situation-registry-v0.12",
        "sources": {"fixture-source": {}},
        "situations": [],
    }
    declarations, actual_cases = [], []
    for index, slot in enumerate(slots):
        case_root = Path(slot["team_rollout"]).parent
        scenario_sha = write(case_root / "scenario.json", {"synthetic": index})
        situation = {
            "scenario_id": "xi-" + str(index),
            "source_cluster_id": "fixture-source",
            "world_family_id": "fixture-family",
            "base_project_id": "project-" + str(index),
            "information_layout_id": "layout-" + str(index),
            "split": "development",
            "generator_version": "fixture-generator",
            "validator_version": "fixture-validator",
            "template_family_id": "fixture-template",
            "scenario_file": str(case_root / "scenario.json"),
            "scenario_sha256": scenario_sha,
        }
        registry["situations"].append(situation)
        declarations.append(
            {
                "episode_name": slot["slot_id"],
                "repeat": 1,
                "backend": "qwen",
                "target_roles": ppo.MEMBERS,
                "situation_registry_id": situation["scenario_id"],
                "expected_scenario_sha256": scenario_sha,
            }
        )
        actual_cases.append(
            {
                "episode_name": slot["slot_id"],
                "episode_id": slot["slot_id"],
                "source_before": source,
                "source_after": source,
                "scenario_sha256": scenario_sha,
            }
        )
    registry_path = tmp_path / "registry.json"
    registry_sha = write(registry_path, registry)
    protocol = {
        "fixed_training_slot_selection": {"episode_names": [slot["slot_id"] for slot in slots]},
        "episodes": declarations,
        "backends": {"qwen": {"backend_id": "local-qwen-http"}},
        "situation_registry": {"path": str(registry_path), "sha256": registry_sha},
    }
    protocol_path = tmp_path / "collection-protocol.json"
    protocol_sha = write(protocol_path, protocol)
    report_path = tmp_path / "collection-report.json"
    report_sha = write(
        report_path,
        {
            "protocol_sha256": protocol_sha,
            "source_before": source,
            "source_after": source,
            "cases": actual_cases,
        },
    )
    gamma = digest(
        json_bytes(
            {
                "frozen_protocol": protocol_sha,
                "runtime_source_tree": source["source_tree_sha256"],
                "service_protocol": protocol["backends"]["qwen"],
            }
        )
    )
    for index, slot in enumerate(slots):
        rollout_path = Path(slot["team_rollout"])
        rollout = read_json(rollout_path)
        manifest = rollout["manifest"]
        manifest["episode_id"] = slot["slot_id"]
        manifest["scenario"] = {"sha256": declarations[index]["expected_scenario_sha256"]}
        rollout["manifest_sha256"] = write(rollout_path.parent / "manifest.json", manifest)
        rollout["window"] = {
            "window_id": "independent-window-" + str(index),
            "xi_id": registry["situations"][index]["scenario_id"],
            "xi_fingerprint": ppo.situation_fingerprint(registry["situations"][index]),
            "gamma_fingerprint": gamma,
            "team_policy_fingerprint": digest(json_bytes(manifest["policies"])),
        }
        slot["expected_window"] = copy.deepcopy(rollout["window"])
        slot["team_rollout_sha256"] = write(rollout_path, rollout)
    inventory.update(
        collection_protocol={"path": str(protocol_path), "sha256": protocol_sha},
        collection_report={"path": str(report_path), "sha256": report_sha},
        situation_registry={"path": str(registry_path), "sha256": registry_sha},
    )
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


def test_distinct_situation_windows_use_pinned_collection_not_one_fabricated_window(tmp_path):
    prepared = ppo.prepare_inventory(inventory_fixture(tmp_path))
    assert prepared["gates"]["four_exact_situations_same_gamma_policy"]
    windows = [row["window"] for row in prepared["collection_cohort"]["expected_slots"].values()]
    assert len({window["window_id"] for window in windows}) == 4
    assert len({window["gamma_fingerprint"] for window in windows}) == 1


def test_training_slot_cannot_be_replaced_by_undeclared_repeat(tmp_path):
    path = inventory_fixture(tmp_path)
    inventory = read_json(path)
    inventory["slots"][0]["slot_id"] = "reward-picked-repeat2"
    write(path, inventory)
    with pytest.raises(ValueError, match="four fixed training slots"):
        ppo.prepare_inventory(path)


def test_same_handwritten_cohort_label_cannot_hide_other_sampling_source(tmp_path):
    path = inventory_fixture(tmp_path)
    inventory = read_json(path)
    report_path = Path(inventory["collection_report"]["path"])
    report = read_json(report_path)
    report["source_before"]["source_tree_sha256"] = "other-frozen-source"
    report["source_after"] = copy.deepcopy(report["source_before"])
    inventory["collection_report"]["sha256"] = write(report_path, report)
    inventory["cohort_label"] = "same-label-is-not-evidence"
    write(path, inventory)
    with pytest.raises(ValueError, match="actual collection/situation"):
        ppo.prepare_inventory(path)


def test_selected_repeat_must_be_one_even_if_names_and_cohort_label_match(tmp_path):
    path = inventory_fixture(tmp_path)
    inventory = read_json(path)
    protocol_path = Path(inventory["collection_protocol"]["path"])
    protocol = read_json(protocol_path)
    protocol["episodes"][0]["repeat"] = 2
    inventory["collection_protocol"]["sha256"] = write(protocol_path, protocol)
    report_path = Path(inventory["collection_report"]["path"])
    report = read_json(report_path)
    report["protocol_sha256"] = inventory["collection_protocol"]["sha256"]
    inventory["collection_report"]["sha256"] = write(report_path, report)
    write(path, inventory)
    with pytest.raises(ValueError, match="Qwen repeat1"):
        ppo.prepare_inventory(path)
