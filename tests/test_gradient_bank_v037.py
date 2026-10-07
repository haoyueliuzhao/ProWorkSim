"""Small CPU numerical/integrity controls; no claim of real-model utility."""
import copy
import json
import math

import pytest

from proworksim.gradient_bank_v037 import (
    GradientBankWriter, WeightedGradientCache, assign_gradients, load_gradient_bank,
)

torch = pytest.importorskip("torch")


def material():
    binding = {"common_state_sha256": "a" * 64, "training_rng_sha256": "b" * 64,
               "recipe_sha256": "c" * 64, "original_material_sha256": "d" * 64,
               "numerical_source_sha256": "e" * 64}
    rows = [{"index": index, "slot_id": str(index), "member_id": "member_a",
             "call_id": "call-" + str(index), "tokens_sha256": str(index) * 64,
             "actor_denominator": 16 * 2 * (index + 1), "critic_denominator": 32,
             "advantage": float(index - 1)} for index in range(3)]
    parameters = {"adapter": torch.nn.Parameter(torch.tensor([0.3, -0.2])),
                  "unused": torch.nn.Parameter(torch.tensor([0.7]))}
    gradients = [torch.tensor([10.0, 1.0]), torch.tensor([-8.0, 6.0]), torch.tensor([2.0, -3.0])]
    return binding, rows, parameters, gradients


def make_bank(path):
    binding, rows, parameters, gradients = material()
    writer = GradientBankWriter(path, torch=torch, binding=binding, rows=rows, actor_parameters=parameters)
    for index, gradient in enumerate(gradients):
        writer.append_actor(index, {"adapter": gradient})
    manifest = writer.finalize({"critic": torch.tensor([0.25])}, metadata={"real_model_run": False})
    bank = load_gradient_bank(path, torch=torch, expected_binding=binding, expected_rows=rows,
                              expected_manifest_sha256=manifest["manifest_sha256"])
    return bank, parameters, gradients, binding, rows


def test_unit_bank_preserves_order_baseline_and_positive_composition(tmp_path):
    bank, parameters, gradients, _, _ = make_bank(tmp_path / "bank")
    rng = torch.get_rng_state().clone()
    for weights in ([1.0] * 3, [0.37, 1.4, 0.9]):
        parameters["adapter"].grad = None
        for gradient, weight in zip(gradients, weights):
            (parameters["adapter"].dot(gradient) * weight).backward()
        expected = parameters["adapter"].grad.clone()
        result = bank.compose_actor(weights)
        if all(weight == 1 for weight in weights):
            assert torch.equal(result["adapter"], expected)
        else:
            torch.testing.assert_close(result["adapter"], expected, rtol=1e-6, atol=1e-6)
        assert "unused" not in result
        assert torch.equal(bank.critic_gradients()["critic"], torch.tensor([0.25]))
    assert torch.equal(torch.get_rng_state(), rng)
    for bad in ([1, 2], [1, 0, 1], [1, math.inf, 1], [1, True, 1]):
        with pytest.raises(ValueError, match="finite positive"):
            bank.compose_actor(bad)


def test_full_sum_then_global_clip_and_independent_restored_adam(tmp_path):
    bank, parameters, gradients, _, _ = make_bank(tmp_path / "bank")
    parameter = parameters["adapter"]
    optimizer = torch.optim.AdamW([parameter], lr=0.15, weight_decay=0)
    for _ in range(3):
        parameter.grad = torch.tensor([0.4, -0.1])
        optimizer.step()
    common_parameter, common_optimizer = parameter.detach().clone(), copy.deepcopy(optimizer.state_dict())

    def run(weights, cached, clip_each=False):
        value = torch.nn.Parameter(common_parameter.clone())
        current = torch.optim.AdamW([value], lr=0.15, weight_decay=0)
        current.load_state_dict(copy.deepcopy(common_optimizer))
        if cached:
            assign_gradients({"adapter": value}, bank.compose_actor(weights), torch=torch)
        elif clip_each:
            accumulated = torch.zeros_like(value)
            for gradient, weight in zip(gradients, weights):
                value.grad = gradient * weight
                torch.nn.utils.clip_grad_norm_([value], 1.0)
                accumulated.add_(value.grad)
            value.grad = accumulated
        else:
            for gradient, weight in zip(gradients, weights):
                (value.dot(gradient) * weight).backward()
        torch.nn.utils.clip_grad_norm_([value], 1.0)
        current.step()
        return value.detach().clone(), copy.deepcopy(current.state_dict())

    weights = [0.37, 1.4, 0.9]
    expected, state = run(weights, False)
    actual, actual_state = run(weights, True)
    torch.testing.assert_close(actual, expected, atol=1e-7, rtol=1e-6)
    for name, tensor in state["state"][0].items():
        torch.testing.assert_close(tensor, actual_state["state"][0][name], atol=1e-7, rtol=1e-6)
    assert actual_state["state"][0]["step"] == 4
    # A second candidate never inherits the previous candidate's moments.
    baseline, _ = run([1.0] * 3, True)
    baseline_again, _ = run([1.0] * 3, False)
    assert torch.equal(baseline, baseline_again)
    assert not torch.allclose(run(weights, False, clip_each=True)[0], expected, atol=1e-4)


def test_bank_rejects_changed_common_rows_order_and_payload(tmp_path):
    bank, _, _, binding, rows = make_bank(tmp_path / "bank")
    changed = {**binding, "common_state_sha256": "f" * 64}
    with pytest.raises(ValueError, match="expected full common"):
        load_gradient_bank(bank.path, torch=torch, expected_binding=changed, expected_rows=rows)
    changed_rows = copy.deepcopy(rows)
    changed_rows[0]["actor_denominator"] = 1
    with pytest.raises(ValueError, match="ordered original rows"):
        load_gradient_bank(bank.path, torch=torch, expected_binding=binding, expected_rows=changed_rows)
    with pytest.raises(ValueError, match="ordered original rows"):
        load_gradient_bank(bank.path, torch=torch, expected_binding=binding, expected_rows=rows[::-1])
    path = bank.path / "actor-000000.pt"
    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    path.write_bytes(data)
    with pytest.raises(ValueError, match="payload integrity"):
        bank.compose_actor([1.0] * 3)


def test_incomplete_writer_and_parameter_assignment_fail_before_mutation(tmp_path):
    binding, rows, parameters, _ = material()
    writer = GradientBankWriter(tmp_path / "partial", torch=torch, binding=binding, rows=rows,
                                actor_parameters=parameters)
    with pytest.raises(ValueError, match="frozen order"):
        writer.append_actor(1, {})
    with pytest.raises(ValueError, match="complete bank"):
        writer.finalize({})
    assert not (writer.path / "manifest.json").exists()
    for invalid in ({"wrong": torch.zeros(2)}, {"adapter": torch.zeros(3)},
                    {"adapter": torch.zeros(2, dtype=torch.float64)},
                    {"adapter": torch.tensor([float("nan"), 0.0])}):
        with pytest.raises(ValueError):
            writer.append_actor(0, invalid)
    parameters["adapter"].grad = torch.ones(2)
    parameters["unused"].grad = torch.ones(1)
    with pytest.raises(ValueError, match="dtype"):
        assign_gradients(parameters, {"adapter": torch.zeros(2, dtype=torch.float64)}, torch=torch)
    assert torch.equal(parameters["adapter"].grad, torch.ones(2))
    assert parameters["unused"].grad is not None
    assign_gradients(parameters, {"adapter": torch.zeros(2)}, torch=torch)
    assert parameters["unused"].grad is None
    assert torch.equal(parameters["adapter"].grad, torch.zeros(2))


def test_exact_weight_cache_replays_weighted_backward_without_rescaling(tmp_path):
    binding, rows, parameters, gradients = material()
    cache = WeightedGradientCache(tmp_path / "exact", torch=torch, binding=binding, rows=rows,
                                  actor_parameters=parameters)
    weights = [0.37, 1.4, 0.9]
    expected = torch.zeros(2)
    for index, (gradient, weight) in enumerate(zip(gradients, weights)):
        parameters["adapter"].grad = None
        (parameters["adapter"].dot(gradient) * weight).backward()
        actual_contribution = parameters["adapter"].grad.clone()
        expected.add_(actual_contribution)
        assert cache.get(index, weight) is None
        receipt = cache.put(index, weight, {"adapter": actual_contribution},
                            metadata={"actor_loss": 1.25, "probability_check": {"passed": True}})
        assert receipt["key"]["weight_hex"] == float(weight).hex()
        loaded = cache.get(index, weight)
        assert torch.equal(loaded["gradients"]["adapter"], actual_contribution)
        assert loaded["metadata"]["probability_check"]["passed"]
        # A nearby representable float is a new key, even with identical FP32 cast.
        assert cache.get(index, math.nextafter(weight, math.inf)) is None
        with pytest.raises(FileExistsError):
            cache.put(index, weight, {"adapter": actual_contribution})
    reopened = WeightedGradientCache(cache.path, torch=torch, binding=binding, rows=rows,
                                     actor_parameters=parameters)
    assert torch.equal(reopened.compose_actor(weights)["adapter"], expected)
    with pytest.raises(ValueError, match="not been computed"):
        reopened.compose_actor([1.0] * 3)


def test_exact_weight_cache_rejects_tampering_and_incomplete_entries(tmp_path):
    binding, rows, parameters, gradients = material()
    cache = WeightedGradientCache(tmp_path / "exact", torch=torch, binding=binding, rows=rows,
                                  actor_parameters=parameters)
    receipt = cache.put(0, 1.0, {"adapter": gradients[0]})
    with pytest.raises(ValueError, match="exact common"):
        WeightedGradientCache(cache.path, torch=torch, binding={**binding, "rng": "changed"},
                              rows=rows, actor_parameters=parameters)
    directory = cache.path / receipt["key_sha256"]
    altered = copy.deepcopy(receipt)
    altered["metadata"]["actor_loss"] = 999
    (directory / "receipt.json").write_text(json.dumps(altered))
    with pytest.raises(ValueError, match="receipt seal"):
        cache.get(0, 1.0)
    (directory / "receipt.json").unlink()
    with pytest.raises(ValueError, match="incomplete"):
        cache.get(0, 1.0)
    with pytest.raises(FileExistsError):
        cache.put(0, 1.0, {"adapter": gradients[0]})
