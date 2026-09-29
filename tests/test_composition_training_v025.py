"""Real tiny CPU autograd, synthetic semantic labels; no model-work support claim."""

import copy

import pytest

from proworksim.composition_training_v025 import (
    baseline_configuration,
    configure_from_development,
    materialize_composition,
    probe_configuration,
    solve_two_class,
    validate_composition,
)
from proworksim.online_support import declare_window, expected_window
from proworksim.online_training import prepare_window, tensor_tree_digest
from proworksim.storage import digest, json_bytes, read_json
from proworksim.team_rollout import work_validity
from test_online_training_v13 import _owner, _sample_entry, _features


def features(events, sequence, member, members):
    return [0.0] * 30, {"explicit_CPU_fixture": True, "before_event_sequence": sequence}


@pytest.fixture(scope="module")
def actual_window(tmp_path_factory):
    torch = pytest.importorskip("torch")
    root = tmp_path_factory.mktemp("v025-real-cpu-autograd")
    base = {"manifest": {"sha256": digest(b"explicit_tiny_base")}}
    torch.manual_seed(25)
    collector = _owner(root, torch, "collector", base_identity=base)
    # Real persistent actor/critic optimizer history, analogous only in step
    # count to the selected v024 MC state; never load or claim a 9B checkpoint.
    for i in range(2):
        collector.begin_window("cpu-warm-" + str(i))
        collector.update_window(
            [_sample_entry(collector, reward=1)],
            root / f"warm-update-{i}",
            feature_function=_features,
        )
    collector.save_checkpoint(root / "origin")
    identity = collector.begin_window("cpu-composition-window")
    members = ["provider", "implementer"]
    policies = {
        m: {
            "implementation": "proworksim.model_policy.ModelPolicy",
            "config": {
                "weight_identity": identity,
                "model_revision": identity["policy_version"],
                "task": "Explicit CPU " + m,
            },
        }
        for m in members
    }
    specs = [
        {
            "slot_id": str(i),
            "xi_id": "CPU-A",
            "xi_fingerprint": digest(b"one_same_CPU_situation"),
            "active_members": members,
            "policies": policies,
            "mapping_spec_id": "CPU-semantic-labels-not-model-support",
        }
        for i in range(8)
    ]
    declaration = declare_window(
        collector.window_id,
        actor_identity=identity,
        gamma_identity={"purpose": "composition_training", "explicit_CPU_fixture": True},
        slot_specs=specs,
        min_class_count=2,
    )
    entries, records = [], []
    for i in range(8):
        events = []
        for m in members:
            request = {
                "messages": [{"role": "user", "content": f"CPU slot{i} member{m}"}],
                "model": "toy",
                "temperature": 0.7,
                "max_tokens": 2,
            }
            response = collector.transport.complete(request, timeout_seconds=10)["body"]
            call = f"cpu-{i}-{m}"
            for kind, payload in [
                (
                    "model_call",
                    {
                        "stage": "started",
                        "call_id": call,
                        "request_sha256": digest(json_bytes(request)),
                    },
                ),
                (
                    "model_attempt",
                    {
                        "stage": "finished",
                        "status": "success",
                        "call_id": call,
                        "request": request,
                        "response": {"body": response},
                    },
                ),
                ("model_response", {"call_id": call, "response": response}),
            ]:
                events.append(
                    {"sequence": len(events), "worker_id": m, "kind": kind, "payload": payload}
                )
        category = ["alpha", "alpha", "beta", "beta", "rare", None, "alpha", "beta"][i]
        valid = i < 6
        validity = work_validity(
            [
                {
                    "dimension": dimension,
                    "value": True if dimension == "record" else valid,
                    "evidence": {"explicit_synthetic_semantic_control": True},
                }
                for dimension in ("record", "permission", "basis", "delivery")
            ],
            spec_id="CPU-validity",
        )
        reward = {
            "episode_id": f"cpu-episode-{i}",
            "manifest_sha256": f"cpu-manifest-{i}",
            "eligible": True,
            "reward": [1.0, 1.0, 1.0, 1.0, 0.5, 0.5, 0.0, 0.0][i],
        }
        rollout = {
            "rollout_id": reward["episode_id"],
            "manifest_sha256": reward["manifest_sha256"],
            "window": expected_window(declaration, str(i)),
            "manifest": {"policies": copy.deepcopy(policies)},
            "members": {m: {"actor_id": m, "origin": "target_model"} for m in members},
            "events": events,
            "reward_eligibility": reward,
            "work_validity": validity,
        }
        mapping = {
            "rollout_id": rollout["rollout_id"],
            "spec_id": specs[i]["mapping_spec_id"],
            "status": "mapped" if category else "unmapped",
            "class_id": category,
        }
        entries.append(
            {
                "slot_id": str(i),
                "active_members": members,
                "rollout": rollout,
                "reward": reward,
                "mapping": mapping,
            }
        )
        records.append(
            {"slot_id": str(i), "status": "closed", "rollout": rollout, "mapping": mapping}
        )
    unit = materialize_composition(entries, declaration, records)
    selected = {
        "xi_id": "CPU-A",
        "member_id": "implementer",
        "class_order": ["alpha", "beta"],
        "task": "joint_a",
        "perturb_class_id": "alpha",
    }
    q = baseline_configuration(unit["supports_by_xi"])
    q["CPU-A"]["implementer"] = {"alpha": 0.6, "beta": 0.4}
    changed = materialize_composition(
        entries, declaration, records, q_by_xi=q, selected_block=selected
    )
    return {
        "root": root,
        "torch": torch,
        "base": base,
        "entries": entries,
        "records": records,
        "declaration": declaration,
        "identity": identity,
        "unit": unit,
        "changed": changed,
        "selected": selected,
        "recipe": collector.recipe,
        "collector": collector,
    }


def test_real_weighted_autograd_unit_restores_exact_update_and_critic_is_unchanged(actual_window):
    f = actual_window
    torch = f["torch"]
    outputs = {}
    before = None
    for name, composition in [
        ("baseline", None),
        ("explicit-unit", f["unit"]),
        ("changed", f["changed"]),
    ]:
        owner = _owner(f["root"], torch, name, base_identity=f["base"])
        owner.restore_checkpoint(f["root"] / "origin")
        snapshot = tensor_tree_digest(owner._state_bundle(), torch)
        before = snapshot if before is None else before
        assert snapshot == before and owner.actor_steps == owner.critic_steps == 2
        owner.begin_window(f["declaration"]["window_id"])
        folder = f["root"] / ("update-" + name)
        report = owner.update_window(
            f["entries"], folder, feature_function=features, composition=composition
        )
        assert report["status"] == "updated" and owner.actor_steps == owner.critic_steps == 3
        assert report["actor_optimizer_steps"] == report["critic_optimizer_steps"] == 1
        outputs[name] = {
            "state": owner._state_bundle(),
            "losses": read_json(folder / "losses.json"),
            "report": report,
            "gradients": torch.load(folder / "gradients-before-clip.pt", weights_only=True),
            "admission": read_json(folder / "admission.json"),
        }
    b, u, c = (outputs[k] for k in ("baseline", "explicit-unit", "changed"))
    assert tensor_tree_digest(b["state"], torch) == tensor_tree_digest(u["state"], torch)
    assert b["losses"] == u["losses"]
    assert tensor_tree_digest(b["gradients"], torch) == tensor_tree_digest(u["gradients"], torch)
    assert b["admission"] == u["admission"] == c["admission"]
    assert b["report"]["advantages"] == c["report"]["advantages"]
    assert tensor_tree_digest(b["gradients"]["actor"], torch) != tensor_tree_digest(
        c["gradients"]["actor"], torch
    )
    assert tensor_tree_digest(b["state"]["actor"], torch) != tensor_tree_digest(
        c["state"]["actor"], torch
    )
    for key in ("critic", "critic_optimizer"):
        assert tensor_tree_digest(b["state"][key], torch) == tensor_tree_digest(
            c["state"][key], torch
        )
    assert tensor_tree_digest(b["gradients"]["critic"], torch) == tensor_tree_digest(
        c["gradients"]["critic"], torch
    )
    for left, right in zip(b["losses"], c["losses"]):
        assert (
            left["critic_loss"] == right["critic_loss"]
            and left["ppo_ratio_range"] == right["ppo_ratio_range"]
        )
        assert right["actor_loss"] == pytest.approx(
            left["actor_loss"] * right["composition_weight"], rel=2e-7, abs=1e-9
        )
        if right["member_id"] == "provider" or right["slot_id"] in {"4", "5", "6", "7"}:
            assert right["composition_weight"] == 1
    mat = f["changed"]["materialized_by_xi"]["CPU-A"]
    assert mat["members"]["implementer"]["total_slot_weight"] == 8
    assert mat["members"]["implementer"]["eligible_branch_weight"] == 4
    assert mat["members"]["provider"]["weights"] == dict.fromkeys(map(str, range(8)), 1.0)


def test_original_member_tokens_support_and_residuals_cannot_be_reassigned(actual_window):
    f = actual_window
    prepared = prepare_window(
        f["entries"], f["identity"], f["declaration"]["window_id"], f["recipe"], features
    )
    weights, proof = validate_composition(f["entries"], prepared, f["changed"])
    assert len(weights) == 16 and proof["original_normalization_preserved"]
    block = f["unit"]["supports_by_xi"]["CPU-A"]["blocks"]["implementer"]
    assert block["candidate_counts_before_support"] == {"alpha": 2, "beta": 2, "rare": 1}
    assert block["b"] == {"alpha": 0.5, "beta": 0.5} and block["v"] == 0.5
    assert "below_frozen_class_support" in block["diagnostics"]["4"]
    assert all(block["base_actor_mask"].values())  # Trusted failures remain base RL.
    q = baseline_configuration(f["unit"]["supports_by_xi"])
    q["CPU-A"]["implementer"] = {"outside": 1.0}
    with pytest.raises(ValueError, match="unsupported"):
        materialize_composition(
            f["entries"], f["declaration"], f["records"], q_by_xi=q, selected_block=f["selected"]
        )
    q = baseline_configuration(f["unit"]["supports_by_xi"])
    q["CPU-A"]["provider"] = {"alpha": 0.6, "beta": 0.4}
    with pytest.raises(ValueError, match="single selected"):
        materialize_composition(
            f["entries"], f["declaration"], f["records"], q_by_xi=q, selected_block=f["selected"]
        )
    bad = copy.deepcopy(f["changed"])
    bad["materialized_by_xi"]["CPU-A"]["members"]["provider"]["weights"]["0"] = 1.2
    with pytest.raises(ValueError, match="canonical materialization"):
        validate_composition(f["entries"], prepared, bad)
    for key in ("member_id", "tokens", "actor_denominator", "critic_denominator"):
        bad = copy.deepcopy(prepared)
        if key == "member_id":
            bad["decisions"][0][key] = "reviewer"
        elif key == "tokens":
            bad["decisions"][0][key]["input_mask"][0] = 1
        else:
            bad["decisions"][0][key] += 1
        with pytest.raises(ValueError, match="members|tokens|normalization"):
            validate_composition(f["entries"], bad, f["changed"])
    duplicate = copy.deepcopy(prepared)
    duplicate["decisions"].append(copy.deepcopy(duplicate["decisions"][0]))
    with pytest.raises(ValueError, match="counted twice"):
        validate_composition(f["entries"], duplicate, f["changed"])
    wrong_task = {**f["selected"], "task": "joint_b"}
    with pytest.raises(ValueError, match="only for qualified task A"):
        materialize_composition(
            f["entries"], f["declaration"], f["records"], selected_block=wrong_task
        )
    bad = copy.deepcopy(f["changed"])
    bad["window_id"] = "another-window"
    with pytest.raises(ValueError, match="original window"):
        validate_composition(f["entries"], prepared, bad)


def test_single_direction_and_complete_constrained_dual_kl_solution(actual_window):
    f = actual_window
    s = f["unit"]["supports_by_xi"]
    selected = f["selected"]
    probe = probe_configuration(s, selected)
    assert probe["q_by_xi"]["CPU-A"]["implementer"] == {"alpha": 0.55, "beta": 0.45}
    assert probe["probed_class"] == "alpha" and probe["direction"] == {"alpha": 0.5, "beta": -0.5}
    for target, sign in [([True, False, False, False, False, False], 1), ([False] * 6, -1)]:
        base = [False] * 6 if sign > 0 else [True, False, False, False, False, False]
        result = configure_from_development(s, selected, base, target)
        assert result["changed"] and result["contribution_estimate"] * sign > 0
        assert result["directional_inner_product"] == pytest.approx(result["contribution_estimate"])
        assert result["q_by_xi"]["CPU-A"]["implementer"]["alpha"] == pytest.approx(0.5 + 0.1 * sign)
        assert result["solution"]["tv"] <= 0.1 + 1e-12
        assert all(0.5 <= v <= 2 for v in result["solution"]["ratios"].values())
    for base, probe in [([False] * 6, [False] * 6), ([False] * 6, [None] + [False] * 5)]:
        result = configure_from_development(s, selected, base, probe)
        assert not result["changed"] and result["q_by_xi"] == baseline_configuration(s)
    # The solver's interior stationary point and bound solutions maximize the
    # full two-KL objective, rather than an unchecked exponentiated heuristic.
    import math

    for b, c in [
        ({"alpha": 0.6, "beta": 0.4}, {"alpha": 0.1, "beta": 0.0}),
        ({"alpha": 0.25, "beta": 0.75}, {"alpha": -8.0, "beta": 0.0}),
        ({"alpha": 0.75, "beta": 0.25}, {"alpha": 8.0, "beta": 0.0}),
    ]:
        solved = solve_two_class(b, c, class_order=["alpha", "beta"])
        lo, hi = solved["feasible_coordinate_interval"]
        best = solved["objective"]
        for i in range(101):
            x = lo + (hi - lo) * i / 100
            q = {"alpha": x, "beta": 1 - x}
            objective = sum(
                q[k] * c[k] - q[k] * math.log(q[k] / b[k]) - q[k] * math.log(q[k] / 0.5) for k in q
            )
            assert objective <= best + 1e-12
    with pytest.raises(ValueError, match="epsilon"):
        probe_configuration(s, selected, epsilon=0.2)
