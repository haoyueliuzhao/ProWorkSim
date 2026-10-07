"""Read-only CPU budget for exact weighted-row reuse of the frozen P2 material.

Only the P2 freeze/material/common/profile are read. Development, selection and
confirmation outcomes are never opened. No model is constructed. The output is
a NEW JSON file; existing output paths are rejected, including empty files.
"""
from __future__ import annotations

import argparse
import gc
from pathlib import Path
import time

from proworksim.experience_allocation_v035 import bind_candidate, candidate_materialization
from proworksim.online_training import prepare_window, validate_actor_composition
from proworksim.software_learning_v029 import software_feature_function, software_recipe
from proworksim.software_learning_v036 import material_summary
from proworksim.storage import digest, json_bytes, read_json
from scripts.run_ne_v021 import checked, reference

VERSION = "exact-weight-cache-inventory-v0.37"
SOURCE = Path(__file__).resolve().parents[1]


def candidate_weights(allocation, prepared, candidate_id):
    """Pure materialization, retaining the original prepared decision order."""
    materialized = candidate_materialization(allocation, candidate_id)
    by_slot = {slot: xi for xi, support in allocation["supports_by_xi"].items() for slot in support["slot_ids"]}
    weights = []
    for row in prepared["decisions"]:
        member = materialized[by_slot[row["slot_id"]]]["members"][row["member_id"]]
        if not member["actor_mask"][row["slot_id"]]:
            raise ValueError("Original admitted row was excluded by frozen allocation")
        weights.append(member["weights"][row["slot_id"]])
    return weights


def count_inventory(allocation, prepared):
    """Count exact keys; formal weights stay unknown until future selection."""
    rows = prepared["decisions"]
    if not rows or not allocation["candidates"] or "B" not in allocation["candidates"]:
        raise ValueError("Require every admitted original row and the complete frozen candidate inventory")
    if len({(row["slot_id"], row["member_id"], row["call_id"]) for row in rows}) != len(rows):
        raise ValueError("Original admitted decision identities must be unique")
    row_hashes = [digest(json_bytes(row)) for row in rows]
    def keys(weights):
        return {(index, row_hashes[index], float(weight).hex()) for index, weight in enumerate(weights)}
    base_weights = candidate_weights(allocation, prepared, "B")
    if any(weight != 1 for weight in base_weights):
        raise ValueError("Shared B must retain unit weights on all original rows")
    baseline = keys(base_weights)
    union, nonbaseline, candidates = set(), set(), []
    per_row_hex = [set() for _ in rows]
    for candidate_id in allocation["candidates"]:
        weights = candidate_weights(allocation, prepared, candidate_id)
        exact = keys(weights)
        candidates.append({"candidate_id": candidate_id, "method": allocation["candidates"][candidate_id]["method"],
            "admitted_rows": len(rows), "weights": weights, "exact_weight_hex": [float(weight).hex() for weight in weights],
            "exact_keys_new_in_frozen_candidate_order": len(exact - union),
            "keys_already_in_shared_B": len(exact & baseline),
            "nonunit_weight_rows": sum(weight != 1 for weight in weights)})
        union.update(exact)
        if candidate_id != "B":
            nonbaseline.update(exact)
        for index, weight in enumerate(weights):
            per_row_hex[index].add(float(weight).hex())
    eligible = {(slot, member) for xi, member in allocation["eligible_blocks"]
                for slot in allocation["supports_by_xi"][xi]["blocks"][member]["eligible_slots"]}
    eligible_indices = [index for index, row in enumerate(rows) if (row["slot_id"], row["member_id"]) in eligible]
    varying_indices = [index for index, values in enumerate(per_row_hex) if len(values) > 1]
    if not set(varying_indices) <= set(eligible_indices):
        raise ValueError("A frozen candidate changed an ineligible residual/member row")
    count = len(rows)
    inventory = allocation["actual_inventory"]
    if inventory["unique_trial_updates"] != len(candidates) or inventory["formal_updates"] != 3:
        raise ValueError("Frozen trial/formal inventory does not match all materialized candidates")
    trials = {"trial_updates": len(candidates), "rows_per_update": count,
        "unoptimized_trial_row_backwards": count * len(candidates),
        "unique_exact_weighted_rows": len(union), "shared_B_unique_rows": len(baseline),
        "non_B_trial_updates": len(candidates) - 1,
        "non_B_unoptimized_row_backwards": count * (len(candidates) - 1),
        "non_B_unique_exact_weighted_rows_without_assuming_B": len(nonbaseline),
        "non_B_additional_exact_rows_after_B": len(nonbaseline - baseline),
        "shared_B_rows_also_required_by_non_B": len(nonbaseline & baseline),
        "fixed_residual_and_other_member_rows": count - len(eligible_indices),
        "eligible_selected_member_rows": len(eligible_indices),
        "rows_actually_varying_across_frozen_trials": len(varying_indices),
        "eliminated_row_backwards": count * len(candidates) - len(union),
        "row_backward_count_reduction_fraction": 1 - len(union) / (count * len(candidates)),
        "row_backward_count_ratio": count * len(candidates) / len(union)}
    formal = {"selection_read": False, "formal_weights_known": False,
        "assumption": "All frozen trials completed with their exact cache retained; no outcome-based candidate deletion.",
        "formal_B_original_rows": count, "formal_B_cached_rows": count, "formal_B_new_rows": 0,
        "formal_G_and_I_original_rows": 2 * count,
        "formal_G_and_I_new_exact_rows_lower_bound": 0,
        "formal_G_and_I_new_exact_rows_upper_bound": 2 * len(eligible_indices),
        "formal_all_original_rows": 3 * count,
        "formal_all_cache_hits_lower_bound": 3 * count - 2 * len(eligible_indices),
        "formal_all_cache_hits_upper_bound": 3 * count,
        "all_trials_and_formal_unoptimized_rows": count * (len(candidates) + 3),
        "all_trials_and_formal_unique_exact_rows_lower_bound": len(union),
        "all_trials_and_formal_unique_exact_rows_upper_bound": len(union) + 2 * len(eligible_indices),
        "bound_scope": "Worst case: each formal G/I contributes one previously unseen exact weight for every eligible row. "
                       "No formal weight, cache hit or utility is inferred from development feedback."}
    summaries = [{"index": index, "row_sha256": row_hashes[index],
                  **{name: row[name] for name in ("slot_id", "member_id", "call_id", "actor_denominator", "critic_denominator")},
                  "distinct_frozen_trial_weight_count": len(per_row_hex[index])}
                 for index, row in enumerate(rows)]
    return {"trials": trials, "formal_bounds": formal, "rows": summaries, "candidates": candidates,
        "unchanged_execution_inventory": inventory,
        "key_definition": "Budget key=(original row index, complete prepared-row SHA256, float(weight).hex()). "
                          "Actual runtime keys additionally bind the complete common, frozen advantage, source and recipe. "
                          "Those are constant across this planned candidate set, so they do not change key cardinality.",
        "scope": "Planned full original material from an empty new execution cache; excludes any discarded legacy work. "
                 "Counts assume successful nonzero-signal actor execution and passing probability gates. "
                 "These are row counts, not measured runtime speedups or model-utility evidence."}


def inspect(parent_root, output):
    root, output = Path(parent_root).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError("Inventory output must be a new JSON file")
    started = time.monotonic()
    freeze_path = root / "postcollection-freeze.json"
    freeze = read_json(freeze_path)
    if freeze.get("version") != "postcollection-freeze-v0.36":
        raise ValueError("Read only the original completed P2 postcollection freeze")
    allocation = freeze["allocation"]
    references = {"freeze": reference(freeze_path), **freeze["P2_material"],
                  "common": freeze["common"], "training_material_binding": freeze["training_material_binding"]}
    paths = {name: checked(value) for name, value in references.items()}
    entries, declaration, records = [read_json(paths[name]) for name in ("entries.json", "declaration.json", "records.json")]
    material = read_json(paths["training_material_binding"])
    actual = checked(freeze["P2_worker"]).parent
    owner_path, migration_path = actual / "resident/owner.json", actual / "software-critic-migration.json"
    owner, migration = read_json(owner_path), read_json(migration_path)
    recipe = software_recipe(owner["recipe"])
    if migration["original_recipe"] != owner["recipe"] or migration["software_recipe"] != recipe:
        raise ValueError("The retained owner and actual software-coordinate recipe disagree")
    common = read_json(paths["common"])
    if common["actor_identity"] != declaration["actor_identity"]:
        raise ValueError("Original P2 actor differs from its complete common")
    prepared = prepare_window(entries, declaration["actor_identity"], declaration["window_id"], recipe, software_feature_function)
    summary = material_summary(prepared)
    if (material["entries_sha256"] != digest(json_bytes(entries))
            or material["declaration_sha256"] != digest(json_bytes(declaration))
            or any(material[name] != summary[name] for name in ("original_slot_count", "admitted_decisions",
                "admitted_input_tokens", "admitted_own_output_tokens", "maximum_actual_sequence_tokens"))):
        raise ValueError("Fresh pure-CPU preparation differs from the actual frozen P2 binding")
    result = count_inventory(allocation, prepared)
    representative = next(name for name in allocation["candidates"] if name != "B")
    composition = bind_candidate(entries, declaration, records, allocation, representative)
    validated_weights, validation = validate_actor_composition(entries, prepared, composition)
    if validated_weights != candidate_weights(allocation, prepared, representative):
        raise ValueError("Direct frozen materialization differs from original learner admission")
    validation_summary = {"candidate_id": representative, "original_validation_passed": True,
                          "admitted_rows": len(validation["rows"]),
                          "original_normalization_preserved": validation["original_normalization_preserved"],
                          "full_validation_sha256": digest(json_bytes(validation))}
    del composition, validation, records, entries
    gc.collect()
    adapter_bytes = owner["inference_profile"]["actual_parameter_storage"]["counts"]["adapter"]["bytes"]
    result["nominal_dense_actor_gradient_storage"] = {
        "per_row_tensor_bytes": adapter_bytes,
        "frozen_trial_unique_rows_tensor_bytes": adapter_bytes * result["trials"]["unique_exact_weighted_rows"],
        "with_formal_lower_bound_tensor_bytes": adapter_bytes * result["formal_bounds"]["all_trials_and_formal_unique_exact_rows_lower_bound"],
        "with_formal_upper_bound_tensor_bytes": adapter_bytes * result["formal_bounds"]["all_trials_and_formal_unique_exact_rows_upper_bound"],
        "scope": "Dense adapter-storage-size accounting, not measured files. Assumes stored gradient dtype matches adapter FP32; "
                 "tensor serialization, metadata, probability receipts, checkpoints and panel artifacts are additional."}
    sources = [Path(__file__), SOURCE / "src/proworksim/experience_allocation_v035.py",
        SOURCE / "src/proworksim/experience_allocation_v027.py", SOURCE / "src/proworksim/online_training.py",
        SOURCE / "src/proworksim/software_learning_v029.py", SOURCE / "src/proworksim/software_learning_v036.py",
        SOURCE / "src/proworksim/gradient_bank_v037.py"]
    result.update(version=VERSION, parent_root=str(root), parent_references=references,
        owner=reference(owner_path), migration=reference(migration_path), source=[reference(path) for path in sources],
        prepared_sha256=digest(json_bytes(prepared)), actual_prepared_material=summary,
        representative_original_validation=validation_summary,
        model_constructed=False, target_model_calls=0, optimizer_steps=0, execution_device="cpu",
        development_outcomes_read=False, independent_outcomes_read=False, selection_read=False,
        elapsed_seconds=time.monotonic() - started)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation enforces the read-only audit's new-output contract.
    with output.open("xb") as stream:
        stream.write(json_bytes(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New JSON FILE; never overwritten")
    args = parser.parse_args()
    result = inspect(args.parent_root, args.output)
    print({"trials": result["trials"], "formal_bounds": result["formal_bounds"], "output": str(args.output)})


if __name__ == "__main__":
    main()
