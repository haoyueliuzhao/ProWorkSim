"""Real tiny CPU updater integration; no 9B, GPU or allocation-benefit claim."""
import copy
import os
from pathlib import Path
import subprocess

import pytest

from proworksim import gradient_bank_v037, software_learning_v037
from proworksim.experience_allocation_v035 import allocation_gate, bind_candidate, freeze_allocation_plan
from proworksim.online_training import prepare_window, reference, tensor_tree_digest, validate_actor_composition
from proworksim.software_learning_v029 import migrate_software_owner, restore_common, software_feature_function
from proworksim.storage import atomic_write, digest, json_bytes, read_json
from test_software_learning_v029 import _owner
from test_software_learning_v036 import tiny_window


def _warm_real_optimizers(owner):
    """Synthetic, real autograd steps populate nonzero persistent Adam moments.

    This is explicitly fixture preparation, not an admitted production update.
    All tested production updates below run through the real original-token path.
    """
    torch = owner.torch
    features = torch.linspace(-0.25, 0.75, len(owner.recipe["members"]) * 10)
    for index in range(3):
        owner.actor_optimizer.zero_grad(set_to_none=True)
        owner.critic_optimizer.zero_grad(set_to_none=True)
        (-owner.model.logits().log_softmax(-1)[index + 1]).backward()
        torch.nn.utils.clip_grad_norm_(list(owner.actor_parameters.values()), owner.recipe["gradient_clip"])
        owner.actor_optimizer.step()
        (0.5 * (owner.critic(features).squeeze() - 0.7).square()).backward()
        torch.nn.utils.clip_grad_norm_(owner.critic.parameters(), owner.recipe["gradient_clip"])
        owner.critic_optimizer.step()
        owner.actor_steps += 1
        owner.critic_steps += 1
        owner.policy_revision += 1
    owner.critic_has_nonzero_reward_history = True
    owner._identity = owner._make_identity()
    assert owner.actor_optimizer.state and owner.critic_optimizer.state


def _allocation(entries, declaration, records, common):
    gate = allocation_gate(entries, declaration, records)
    development = {"purpose": "contribution_development", "split_manifest_sha256": digest(b"CPU separate panels"),
        "initial_state_sha256": common["state_tensor_digest"], "training_rng_sha256": digest(b"CPU declared panel RNG"),
        "units": [{"unit_id": "dev-" + str(index), "root_id": "dev-" + str(index), "seed": index, "weight": 1.0}
                  for index in range(2)],
        "independent_units": [{"unit_id": "test-" + str(index), "root_id": "test-" + str(index), "seed": index, "weight": 1.0}
                              for index in range(2)], "provenance": "synthetic_cpu_control"}
    return freeze_allocation_plan(gate["supports_by_xi"], eligible_blocks=gate["eligible_blocks"],
        development=development, budget={"max_unique_trial_updates": 33, "max_development_episodes": 66,
            "formal_updates_per_method": 1, "independent_episodes_per_method": 2})


def test_actual_updater_same_common_baseline_weighted_cache_hits_and_misses(tmp_path):
    try:
        import torch
    except ModuleNotFoundError:
        project = Path(__file__).resolve().parents[1]
        interpreter = project / "runs/v016-sdk/resident-venv/bin/python"
        if not interpreter.is_file():
            pytest.skip("Real tiny autograd integration requires the existing PyTorch training environment")
        result = subprocess.run([str(interpreter), "-m", "pytest", "-q",
            str(Path(__file__).resolve()) + "::test_actual_updater_same_common_baseline_weighted_cache_hits_and_misses",
            "--basetemp=" + str(tmp_path / "torch-control")], cwd=project,
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
        assert result.returncode == 0, result.stdout + result.stderr
        return

    output = Path(os.environ.get("PROWORKSIM_V037_INTEGRATION_RUN", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    assert not torch.cuda.is_initialized()
    torch.manual_seed(37037)
    sources = [Path(software_learning_v037.__file__), Path(gradient_bank_v037.__file__), Path(__file__)]
    source_before = [reference(path) for path in sources]
    owner = _owner(output, torch)
    owner.recipe["max_length"] = 512
    assert owner.device == "cpu" and owner.recipe["diagnostic_max_groups"] == 0
    migrate_software_owner(owner, expected_steps=(0, 0))
    _warm_real_optimizers(owner)
    common = owner.save_checkpoint(output / "common")
    entries, declaration, records = tiny_window(owner, output)
    owner.finish_evaluation(entries, output / "collection-closed")
    allocation = _allocation(entries, declaration, records, common)
    baseline = bind_candidate(entries, declaration, records, allocation, "B")
    candidate = allocation["methods"]["G-raw"]["directions"][0]["plus_id"]
    weighted = bind_candidate(entries, declaration, records, allocation, candidate)
    binding = {"common": common, "source": source_before,
               "purpose": "synthetic_cpu_updater_integration_only"}
    complete_states, gradients, reports, before_states = {}, {}, {}, {}

    def run(name, composition, *, cached):
        restored = restore_common(owner, output / "common", window_id=declaration["window_id"])
        assert restored["complete_state_exact"]
        assert (owner.actor_steps, owner.critic_steps) == (3, 3)
        before_states[name] = tensor_tree_digest(owner._state_bundle(), torch)
        kwargs = {"feature_function": software_feature_function, "composition": composition}
        if cached:
            report = software_learning_v037.update_window(owner, entries, output / name,
                cache_root=output / "exact-cache", binding=binding, **kwargs)
        else:
            report = owner.update_window(entries, output / name, **kwargs)
        assert report["status"] == "updated" and report["behavior_probability_passed"] is True
        assert report["actor_optimizer_steps"] == report["critic_optimizer_steps"] == 1
        assert report["actor_steps_total"] == report["critic_steps_total"] == 4
        assert report["admitted_decisions"] == 32 and report["admitted_output_tokens"] == 64
        assert report["scheduled_slots"] == 16
        gradients[name] = torch.load(output / name / "gradients-before-clip.pt", map_location="cpu", weights_only=True)
        complete_states[name] = copy.deepcopy(owner._state_bundle())
        reports[name] = report
        return report

    legacy_b = run("legacy-B", baseline, cached=False)
    cold_b = run("cached-B-cold", baseline, cached=True)
    hot_b = run("cached-B-hot", baseline, cached=True)
    run("legacy-weighted", weighted, cached=False)
    mixed = run("cached-weighted-mixed", weighted, cached=True)
    weighted_hot = run("cached-weighted-hot", weighted, cached=True)
    assert len(set(before_states.values())) == 1

    comparisons = []
    for expected, actual in (("legacy-B", "cached-B-cold"), ("legacy-B", "cached-B-hot"),
                             ("legacy-weighted", "cached-weighted-mixed"), ("legacy-weighted", "cached-weighted-hot")):
        assert tensor_tree_digest(gradients[expected], torch) == tensor_tree_digest(gradients[actual], torch)
        assert tensor_tree_digest(complete_states[expected], torch) == tensor_tree_digest(complete_states[actual], torch)
        for key in ("actor", "critic", "actor_optimizer", "critic_optimizer", "rng_cpu", "rng_cuda"):
            assert tensor_tree_digest(complete_states[expected][key], torch) == tensor_tree_digest(complete_states[actual][key], torch)
        assert read_json(output / expected / "losses.json") == read_json(output / actual / "losses.json")
        comparisons.append({"original": expected, "cached": actual, "gradient_before_clip_bitwise_equal": True,
                            "complete_state_including_adam_critic_rng_bitwise_equal": True})
    assert legacy_b["backward_decisions_completed"] == 32
    assert cold_b["cache_actual_backward_decisions"] == cold_b["cache_applied_decisions"] == 32
    assert cold_b["cache_hit_decisions"] == cold_b["behavior_cache_hits"] == 0
    assert cold_b["actual_behavior_forward_decisions"] == 32
    assert hot_b["cache_actual_backward_decisions"] == hot_b["backward_decisions_completed"] == 0
    assert hot_b["cache_hit_decisions"] == hot_b["cache_applied_decisions"] == hot_b["behavior_cache_hits"] == 32
    assert hot_b["actual_behavior_forward_decisions"] == 0

    # The first raw Helmert direction changes exactly two member_a slots.
    prepared = prepare_window(entries, declaration["actor_identity"], declaration["window_id"],
                              owner.recipe, software_feature_function)
    weights, _ = validate_actor_composition(entries, prepared, weighted)
    changed = sum(weight != 1 for weight in weights)
    assert changed == 2
    assert mixed["cache_actual_backward_decisions"] == mixed["backward_decisions_completed"] == changed
    assert mixed["cache_hit_decisions"] == len(weights) - changed
    assert mixed["behavior_cache_hits"] == 32 and mixed["actual_behavior_forward_decisions"] == 0
    assert weighted_hot["cache_actual_backward_decisions"] == weighted_hot["backward_decisions_completed"] == 0
    assert weighted_hot["cache_hit_decisions"] == weighted_hot["behavior_cache_hits"] == 32
    assert cold_b["cache_binding_sha256"] == mixed["cache_binding_sha256"] == weighted_hot["cache_binding_sha256"]
    assert [reference(path) for path in sources] == source_before
    assert not torch.cuda.is_initialized()

    proof = {"version": "exact-cache-real-updater-cpu-control-v0.37", "passed": True,
        "source": source_before, "execution_device": "cpu", "model": "synthetic_tiny_lora",
        "gpu_model_execution": False, "target_9b_model_calls": 0,
        "synthetic_sampling_calls": 32, "warmup_actual_actor_steps": 3, "warmup_actual_critic_steps": 3,
        "all_initial_complete_common_states_equal": True, "initial_complete_state_sha256": next(iter(before_states.values())),
        "rows": 32, "own_output_tokens": 64, "original_denominator_and_all_slots_retained": True,
        "comparisons": comparisons,
        "actual_reuse": {name: {key: report[key] for key in ("cache_actual_backward_decisions",
            "cache_hit_decisions", "cache_applied_decisions", "behavior_cache_hits", "actual_behavior_forward_decisions")}
            for name, report in reports.items() if name.startswith("cached-")},
        "scope": "Real CPU autograd through SharedActor original-token PPO, LoRA, nonlinear clipping and persistent Adam/critic. "
                 "The complete v037 updater is compared to the inherited updater. This does not qualify GPU kernel determinism, "
                 "9B numerics, runtime speed or model/allocation utility."}
    atomic_write(output / "proof.json", json_bytes(proof))
