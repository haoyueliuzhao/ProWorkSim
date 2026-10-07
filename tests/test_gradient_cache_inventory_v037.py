"""Finite independent enumeration; no model or development feedback involved."""
import math

from proworksim.experience_allocation_v035 import bind_candidate
from proworksim.online_training import validate_actor_composition
from scripts.inspect_gradient_cache_inventory_v037 import count_inventory
from test_experience_allocation_v035 import material, plan_for, prepared_for


def test_frozen_exact_weight_keys_and_unknown_formal_bounds_use_all_original_rows():
    entries, declaration, records = material()
    allocation = plan_for(entries, declaration, records)
    prepared = prepared_for(entries, declaration)
    result = count_inventory(allocation, prepared)
    naive, non_B, baseline = set(), set(), set()
    for candidate in allocation["candidates"]:
        # Independent full original admission route, not the inventory helper's mapping.
        weights, _ = validate_actor_composition(entries, prepared,
            bind_candidate(entries, declaration, records, allocation, candidate))
        keys = {(index, float(weight).hex()) for index, weight in enumerate(weights)}
        naive |= keys
        if candidate == "B":
            baseline = keys
        else:
            non_B |= keys
        observed = next(row for row in result["candidates"] if row["candidate_id"] == candidate)
        assert observed["weights"] == weights
        assert observed["exact_weight_hex"] == [float(weight).hex() for weight in weights]
    assert result["trials"]["unoptimized_trial_row_backwards"] == 13 * 32
    assert result["trials"]["unique_exact_weighted_rows"] == len(naive)
    assert result["trials"]["non_B_additional_exact_rows_after_B"] == len(non_B - baseline)
    assert result["trials"]["shared_B_rows_also_required_by_non_B"] == len(non_B & baseline)
    assert result["trials"]["eligible_selected_member_rows"] == 6
    assert result["trials"]["fixed_residual_and_other_member_rows"] == 26
    assert result["formal_bounds"]["formal_B_cached_rows"] == 32
    assert result["formal_bounds"]["formal_G_and_I_new_exact_rows_lower_bound"] == 0
    assert result["formal_bounds"]["formal_G_and_I_new_exact_rows_upper_bound"] == 12
    assert result["formal_bounds"]["all_trials_and_formal_unique_exact_rows_upper_bound"] == len(naive) + 12
    assert result["formal_bounds"]["selection_read"] is False
    assert result["formal_bounds"]["formal_weights_known"] is False
    # Float identity remains finer than decimal rounding or an FP32 conversion.
    assert float(1.0).hex() != math.nextafter(1.0, 2.0).hex()
