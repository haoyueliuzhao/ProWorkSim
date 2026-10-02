"""Real tiny CPU autograd with synthetic semantic labels/development signals.

These mechanical controls are not 9B model work, software-task success, or
allocation effectiveness. No GPU or external development/test data is used.
"""

import pytest

from proworksim.experience_allocation_v027 import (
    bind_allocation,
    bind_candidate,
    candidate_materialization,
    development_receipt,
    freeze_allocation_plan,
    select_allocation,
    supports_from_entries,
)
from proworksim.online_training import tensor_tree_digest
from proworksim.storage import digest, json_bytes, read_json
from test_composition_training_v025 import actual_window as actual_window
from test_composition_training_v025 import features
from test_online_training_v13 import _owner


def test_v027_trials_and_formal_B_G_I_reach_original_cpu_actor_loss(actual_window):
    f, torch = actual_window, actual_window["torch"]
    origin = torch.load(f["root"] / "origin" / "shared-state.pt", weights_only=True)
    initial_digest = tensor_tree_digest(origin, torch)
    supports, _ = supports_from_entries(f["entries"], f["declaration"], f["records"])
    plan = freeze_allocation_plan(
        supports,
        eligible_blocks=[["CPU-A", "implementer"]],
        development={
            "purpose": "contribution_development",
            "dataset_id": "explicit-synthetic-v027-cpu-signal",
            "split_manifest_sha256": digest(json_bytes({"synthetic_cpu_control": True})),
            "initial_state_sha256": initial_digest,
            "training_rng_sha256": tensor_tree_digest(
                {"cpu": origin["rng_cpu"], "cuda": origin["rng_cuda"]}, torch
            ),
            "units": [{"unit_id": f"synthetic-dev-{i}", "seed": 2700 + i, "weight": 1.0}
                      for i in range(3)],
            "independent_unit_ids": ["reserved-synthetic-confirmation-never-used"],
            "provenance": "synthetic_cpu_control",
        },
        budget={"max_trial_updates_per_method": 7,
                "max_development_evaluations_per_method": 21,
                "formal_updates_per_method": 1},
    )
    assert plan["methods"]["G"]["required_trial_updates"] == 7
    assert plan["methods"]["I"]["required_trial_updates"] == 3
    assert len(plan["candidates"]) == 9  # One physically shared B + six G + two I trials.

    def execute(name, composition):
        owner = _owner(f["root"], torch, "v027-" + name, base_identity=f["base"])
        assert owner.device == "cpu"
        owner.restore_checkpoint(f["root"] / "origin")
        before = owner._state_bundle()
        # Includes actor/critic, both optimizers, step counters and actual Torch RNG.
        assert tensor_tree_digest(before, torch) == initial_digest
        assert owner.actor_steps == owner.critic_steps == 2
        assert tensor_tree_digest({"cpu": before["rng_cpu"], "cuda": before["rng_cuda"]}, torch) == (
            plan["development"]["training_rng_sha256"]
        )
        assert owner.begin_window(f["declaration"]["window_id"]) == f["identity"]
        output = f["root"] / ("v027-update-" + name)
        report = owner.update_window(
            f["entries"], output, feature_function=features, composition=composition
        )
        assert report["status"] == "updated"
        assert owner.actor_steps == owner.critic_steps == 3
        assert report["actor_optimizer_steps"] == report["critic_optimizer_steps"] == 1
        return {
            "state": owner._state_bundle(),
            "losses": read_json(output / "losses.json"),
            "admission": read_json(output / "admission.json"),
            "report": report,
            "gradients": torch.load(output / "gradients-before-clip.pt", weights_only=True),
            "composition_admission": read_json(output / "composition-admission.json")
            if composition is not None else None,
        }

    # Real trial autograd is executed before any development receipt/selection exists.
    # Outcome utilities below remain a synthetic oracle, never measured software performance.
    receipts = []
    for candidate_id in plan["candidates"]:
        trial = bind_candidate(f["entries"], f["declaration"], f["records"], plan, candidate_id)
        result = execute("trial-" + candidate_id, trial)
        assert result["composition_admission"]["Q_equals_B"] is (candidate_id == "B")
        mat = candidate_materialization(plan, candidate_id)
        weights = mat["CPU-A"]["members"]["implementer"]["weights"]
        synthetic_utility = sum(weights[str(i)] * signal / 4
                                for i, signal in enumerate([4.0, 2.0, -1.0, -3.0]))
        receipts.append(development_receipt(
            plan, candidate_id, [synthetic_utility + offset for offset in (0.0, 0.1, -0.1)],
            provenance="synthetic_cpu_control",
        ))
    selection = select_allocation(plan, receipts)
    assert selection["effectiveness_evidence"] is False
    assert selection["provenance"] == "synthetic_cpu_control"
    assert not selection["selections"]["G"]["Q_equals_B"]
    assert not selection["selections"]["I"]["Q_equals_B"]

    outputs = {"implicit": execute("formal-implicit", None)}
    for method in ("B", "G", "I"):
        composition = bind_allocation(
            f["entries"], f["declaration"], f["records"], plan, selection, method=method
        )
        outputs[method] = execute("formal-" + method, composition)
        for member, materialized in composition["materialized_by_xi"]["CPU-A"]["members"].items():
            assert materialized["total_slot_weight"] == pytest.approx(8)
            assert materialized["eligible_branch_weight"] == pytest.approx(4)
            for sid in ("4", "5", "6", "7"):
                assert materialized["weights"][sid] == 1
            if member == "provider":
                assert all(value == 1 for value in materialized["weights"].values())

    implicit, baseline = outputs["implicit"], outputs["B"]
    assert tensor_tree_digest(implicit["state"], torch) == tensor_tree_digest(baseline["state"], torch)
    assert tensor_tree_digest(implicit["gradients"], torch) == tensor_tree_digest(baseline["gradients"], torch)
    assert implicit["losses"] == baseline["losses"]
    assert implicit["admission"] == baseline["admission"]
    assert baseline["composition_admission"]["Q_equals_B"]

    for method in ("G", "I"):
        changed = outputs[method]
        assert changed["composition_admission"]["changed_blocks"] == [
            {"xi_id": "CPU-A", "member_id": "implementer"}
        ]
        assert changed["composition_admission"]["original_normalization_preserved"]
        assert changed["admission"] == baseline["admission"]
        assert changed["report"]["advantages"] == baseline["report"]["advantages"]
        assert tensor_tree_digest(changed["gradients"]["actor"], torch) != tensor_tree_digest(
            baseline["gradients"]["actor"], torch
        )
        assert tensor_tree_digest(changed["state"]["actor"], torch) != tensor_tree_digest(
            baseline["state"]["actor"], torch
        )
        for field in ("critic", "critic_optimizer"):
            assert tensor_tree_digest(changed["state"][field], torch) == tensor_tree_digest(
                baseline["state"][field], torch
            )
        assert tensor_tree_digest(changed["gradients"]["critic"], torch) == tensor_tree_digest(
            baseline["gradients"]["critic"], torch
        )
        for original, weighted in zip(baseline["losses"], changed["losses"]):
            assert original["critic_loss"] == weighted["critic_loss"]
            assert original["ppo_ratio_range"] == weighted["ppo_ratio_range"]
            assert weighted["actor_loss"] == pytest.approx(
                original["actor_loss"] * weighted["composition_weight"], rel=2e-7, abs=1e-9
            )
            if weighted["member_id"] == "provider" or weighted["slot_id"] in {"4", "5", "6", "7"}:
                assert weighted["composition_weight"] == 1
        for row in changed["composition_admission"]["rows"]:
            assert row["actor_denominator"] == 8 * 2 * 2  # Raw slots, members, original own tokens.
            assert row["critic_denominator"] == 8 * 2 * 1
