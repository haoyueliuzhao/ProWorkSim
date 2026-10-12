"""One frozen Gamma1 candidate on exactly 21 original v047 requests, CPU only.

The historical Gamma0 hashes/counts must all reproduce before Gamma1 is measured.
No source world, business test, acceptance, resident owner or model is executed.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import copy
import json
import os
from pathlib import Path
import time

from proworksim.storage import atomic_write, digest, json_bytes

VERSION = "software-context-replay-v0.48"
ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_SHA256 = "dec0b1cdbd0197be473f093341cb075c9f15cb3c8dc211980623aa113f631e29"
EXPECTED = {"unique_requests": 21, "hard_context_rejected": 10,
            "final_fixed_submit": 11, "targeted_LA_LB_P4": 8, "other_rejections": 2}
CONTEXT, OUTPUT = 18432, 2048
CAPACITY_BINDING_PATH = ROOT / "runs/software-organization-v047/stage-A-r0/actual/capacity-binding.json"
CAPACITY_BINDING_SHA256 = "43c5914f008a18a683b1ff5d085383cfee7775f18a7b934cfe921d21d0907472"
_MEASUREMENT = None
_CANDIDATE = None


def require(value, message):
    if not value:
        raise ValueError(message)


def reference(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {"path": str(path), "sha256": digest(data), "bytes": len(data)}


def checked_json(ref):
    path = Path(ref["path"])
    data = path.read_bytes()
    require(digest(data) == ref["sha256"], "Source changed: " + str(path))
    return json.loads(data)


def write(path, value):
    path = Path(path)
    require(not path.exists(), "CPU replay never overwrites an existing artifact: " + str(path))
    atomic_write(path, json_bytes(value))
    return reference(path)


def source_files():
    paths = [p for folder in ("src", "scripts", "tests")
             for p in (ROOT / folder).rglob("*.py")]
    paths += [p for p in (ROOT / "examples/software-organization-v045").rglob("*")
              if p.is_file() and "__pycache__" not in p.parts]
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sorted(paths)}


def inventory_counts(rows):
    hard = [r for r in rows if r.get("kind") == "hard_context_rejected"]
    submits = [r for r in rows if r.get("kind") == "final_fixed_submit"]
    targets = [r for r in hard if r.get("targeted_LA_LB_P4") is True]
    return {"unique_requests": len({r["call_id"] for r in rows}),
            "hard_context_rejected": len(hard), "final_fixed_submit": len(submits),
            "targeted_LA_LB_P4": len(targets), "other_rejections": len(hard) - len(targets)}


def validate_inventory(value):
    rows = value["requests"]
    require(len(rows) == 21 and inventory_counts(rows) == EXPECTED, "Require the predeclared unique 21-request inventory")
    require(len({(r["slot_id"], r["call_id"]) for r in rows}) == 21, "Duplicate original request identity")
    for row in rows:
        expected_target = (row["kind"] == "hard_context_rejected"
                           and row["root_id"] in {"LA", "LB"} and row["condition"] == "P4")
        require(row["targeted_LA_LB_P4"] is expected_target, "Target set differs from frozen LA/LB P4 eight")
        prep = row["historical_preparation"]
        require(prep["context_limit"] == CONTEXT and prep["reserved_output_tokens"] == OUTPUT,
                "Historical capacity or output reservation differs")
        if row["kind"] == "final_fixed_submit":
            require(row["historical_generated"] is True
                    and row["final_fixed_submission"]["call_id"] == row["call_id"],
                    "Final fixed submit must bind its actual submitting call")
    return rows


def bind_native_recipe(source_recipe, source_profile, binding):
    """Apply only the recorded software-member metadata migration and capacity."""
    original = binding["original_recipe"]
    capacity = binding["capacity_recipe"]
    migrated = {**source_recipe, "members": ["member_a", "member_b", "software_inactive"]}
    require(source_recipe.get("members") == ["provider", "implementer", "reviewer"]
            and source_recipe.get("max_length") == 16384
            and source_recipe.get("max_output_tokens") == OUTPUT,
            "Unexpected native owner recipe before the recorded migration")
    require(json_bytes(original) == json_bytes(migrated),
            "Historical original recipe differs beyond the recorded members migration")
    require(json_bytes(capacity) == json_bytes({**original, "max_length": CONTEXT})
            and digest(json_bytes(capacity)) == binding["capacity_recipe_sha256"],
            "Historical capacity recipe differs beyond the fixed capacity")
    require(json_bytes(binding["original_inference_profile"]) == json_bytes(source_profile)
            and json_bytes(binding["capacity_inference_profile"]) == json_bytes({**source_profile, "max_context_tokens": CONTEXT}),
            "Historical native inference profile changed beyond capacity metadata")
    require(binding.get("passed") is True and all(binding["protected_components_unchanged"].values()),
            "Original capacity binding is not passed and parameter-preserving")
    return copy.deepcopy(capacity)


def _initialize(plan_path, candidate, capacity_binding_ref):
    global _MEASUREMENT, _CANDIDATE
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    from scripts.software_context_replay_v044 import load_cpu_measurement
    _MEASUREMENT = load_cpu_measurement(plan_path)
    _MEASUREMENT.recipe = bind_native_recipe(_MEASUREMENT.recipe, _MEASUREMENT.inference_profile,
        checked_json(capacity_binding_ref))
    _CANDIDATE = candidate


def _encoding(request):
    from proworksim.software_context_replay_v041 import encode_request
    return encode_request(request, _MEASUREMENT)


def _save_encoding(folder, name, request, encoding, projection=None):
    folder = Path(folder)
    files = {"request": write(folder / (name + "-request.json"), request),
             "input_ids": write(folder / (name + "-input-ids.json"), encoding["input_ids"])}
    prompt_path = folder / (name + "-native-prompt.txt")
    require(not prompt_path.exists(), "Never overwrite CPU prompt")
    atomic_write(prompt_path, encoding["rendered_prompt"].encode())
    files["rendered_prompt"] = reference(prompt_path)
    metadata = {key: value for key, value in encoding.items()
                if key not in {"rendered_prompt", "input_ids", "native_messages"}}
    files["encoding"] = write(folder / (name + "-encoding.json"), metadata)
    if projection is not None:
        files["projection"] = write(folder / (name + "-projection.json"), projection)
    return {**metadata, "request_sha256": digest(json_bytes(request)), "artifacts": files}


def _input(row):
    original = checked_json(row["artifacts"]["original"])
    lifecycle = checked_json(row["artifacts"]["feedback_lifecycle_before"])
    require(digest(json_bytes(original)) == row["historical_preparation"]["original_request_sha256"],
            "Original upstream is not the whole historical transport request")
    require(original["max_tokens"] == OUTPUT, "Output reservation differs")
    require(digest(json_bytes(_MEASUREMENT.recipe)) == row["historical_preparation"]["recipe_sha256"],
            "CPU native recipe differs from the historical C18432 recipe")
    return original, lifecycle


def _old(row, folder):
    from proworksim.software_context_v044 import project_software_request, protected_software_request
    original, lifecycle = _input(row)
    options = {"render": _MEASUREMENT.render, "tokenizer": _MEASUREMENT.tokenizer,
               "context_limit": CONTEXT, "ledger": lifecycle, "member_id": row["member"]}
    selected, projection = project_software_request(original, **options)
    protected, protected_projection = protected_software_request(original, ledger=lifecycle, member_id=row["member"])
    selected_encoding, protected_encoding = _encoding(selected), _encoding(protected)
    prep = row["historical_preparation"]
    checks = {"original_request": digest(json_bytes(original)) == prep["original_request_sha256"],
              "selected_request": digest(json_bytes(selected)) == prep["selected_request_sha256"],
              "prompt_tokens": selected_encoding["prompt_tokens"] == prep["prompt_tokens"],
              "rendered_prompt": selected_encoding["rendered_prompt_sha256"] == prep["rendered_prompt_sha256"],
              "input_ids": selected_encoding["input_ids_sha256"] == prep["input_ids_sha256"],
              "fits": selected_encoding["fits"] is prep["fits"],
              "capacity": selected_encoding["context_limit"] == prep["context_limit"] == CONTEXT,
              "output_reservation": selected_encoding["reserved_output_tokens"] == prep["reserved_output_tokens"] == OUTPUT,
              "selected_projection_tokens": projection["selected_prompt_tokens"] == selected_encoding["prompt_tokens"],
              "protected_projection_tokens": projection["protected_prompt_tokens"] == protected_encoding["prompt_tokens"]}
    if row["kind"] == "final_fixed_submit":
        checks["saved_selected_bytes"] = json_bytes(selected) == json_bytes(checked_json(row["artifacts"]["selected"]))
        old_projection = checked_json(row["artifacts"]["projection"])
        checks["saved_protected_ids"] = protected_encoding["input_ids_sha256"] == old_projection["protected_input_ids_sha256"]
        checks["saved_original_prompt_tokens"] = projection["original_prompt_tokens"] == old_projection["original_prompt_tokens"]
    return {"original_reproduction_checks": checks,
            "gamma0": {"selected": _save_encoding(folder, "gamma0-selected", selected, selected_encoding, projection),
                       "protected": _save_encoding(folder, "gamma0-protected", protected, protected_encoding, protected_projection),
                       "selected_indices": projection["selected_indices"],
                       "protected_indices": projection["protected_selected_indices"],
                       "original_prompt_tokens": projection["original_prompt_tokens"]},
            "passed": all(checks.values())}


def _new(row, old, folder):
    from proworksim.software_context_v041 import deduplicate_static_snapshots
    from proworksim.software_context_v048 import (project_software_request, protected_software_request,
        reference_equal_fields, validate_reference_projection)
    from proworksim.software_feedback_v044 import project_format_feedback
    original, lifecycle = _input(row)
    options = {"render": _MEASUREMENT.render, "tokenizer": _MEASUREMENT.tokenizer,
               "context_limit": CONTEXT, "ledger": lifecycle, "member_id": row["member"]}
    selected, projection = project_software_request(original, **options)
    protected, protected_projection = protected_software_request(original, ledger=lifecycle, member_id=row["member"])
    selected_encoding, protected_encoding = _encoding(selected), _encoding(protected)
    formatted, feedback = project_format_feedback(original, ledger=lifecycle, member_id=row["member"])
    before_reference, _ = deduplicate_static_snapshots(formatted)
    referenced, evidence = reference_equal_fields(before_reference, source_request=formatted, member_id=row["member"])
    original_to_formatted = {original_i: i for i, original_i in enumerate(feedback["selected_indices"])}
    selected_indices = [original_to_formatted[i] for i in projection["selected_indices"]]
    protected_indices = [original_to_formatted[i] for i in projection["protected_selected_indices"]]
    selected_validation = validate_reference_projection(selected, before_reference=before_reference,
                                                       selected_indices=selected_indices, evidence=evidence)
    protected_validation = validate_reference_projection(protected, before_reference=before_reference,
                                                        selected_indices=protected_indices, evidence=evidence)
    same_indices = [original_to_formatted[i] for i in old["gamma0"]["selected_indices"]]
    same_rounds = copy.deepcopy(referenced)
    same_rounds["messages"] = [copy.deepcopy(referenced["messages"][i]) for i in same_indices]
    same_validation = validate_reference_projection(same_rounds, before_reference=before_reference,
                                                   selected_indices=same_indices, evidence=evidence)
    same_encoding = _encoding(same_rounds)
    old_selected = checked_json(old["gamma0"]["selected"]["artifacts"]["request"])
    checks = {"selected_restores_exact_pre_reference": selected_validation["passed"] is True,
              "protected_restores_exact_pre_reference": protected_validation["passed"] is True,
              "same_gamma0_indices_restore": same_validation["passed"] is True,
              "selected_projection_tokens": selected_encoding["prompt_tokens"] == projection["selected_prompt_tokens"],
              "protected_projection_tokens": protected_encoding["prompt_tokens"] == projection["protected_prompt_tokens"],
              "system_schema_and_settings_unchanged": all(json_bytes(original.get(k)) == json_bytes(selected.get(k))
                 for k in set(original) | set(selected) if k != "messages"),
              "original_gamma0_selected_mapping": json_bytes(old_selected) == json_bytes({**before_reference,
                  "messages": [before_reference["messages"][i] for i in same_indices]}),
              "precapacity_reference_evidence": json_bytes(evidence) == json_bytes(projection["same_input_references"])}
    refs = {"selected": write(folder / "gamma1-selected-reference-validation.json", selected_validation),
            "protected": write(folder / "gamma1-protected-reference-validation.json", protected_validation),
            "same_gamma0_indices": write(folder / "gamma1-same-gamma0-indices-reference-validation.json", same_validation)}
    g0 = old["gamma0"]["selected"]["prompt_tokens"]
    return {"reference_integrity_checks": checks,
            "gamma1": {"selected": _save_encoding(folder, "gamma1-selected", selected, selected_encoding, projection),
                       "protected": _save_encoding(folder, "gamma1-protected", protected, protected_encoding, protected_projection),
                       "selected_indices": projection["selected_indices"],
                       "protected_indices": projection["protected_selected_indices"],
                       "reference_validation": refs,
                       "same_input_reference_evidence": evidence},
            "same_gamma0_retained_rounds_diagnostic": {
                "encoding": _save_encoding(folder, "gamma1-same-gamma0-indices", same_rounds, same_encoding),
                "original_indices": old["gamma0"]["selected_indices"],
                "prompt_tokens_saved_by_references_at_same_indices": g0 - same_encoding["prompt_tokens"],
                "actual_selected_prompt_change_gamma1_minus_gamma0": selected_encoding["prompt_tokens"] - g0,
                "gamma1_retained_indices_not_in_gamma0": sorted(set(projection["selected_indices"]) - set(old["gamma0"]["selected_indices"])),
                "gamma0_retained_indices_not_in_gamma1": sorted(set(old["gamma0"]["selected_indices"]) - set(projection["selected_indices"])),
                "scope": "Same candidate, diagnostic only. Actual capacity selection can retain more old complete rounds after references; this is not an alternative Gamma or an admission margin."},
            "passed": old["passed"] and all(checks.values())}


def _task(phase, row, old, output):
    before = copy.deepcopy(_MEASUREMENT.statistics)
    folder = Path(output) / "requests" / row["slot_id"] / row["call_id"]
    folder.mkdir(parents=True, exist_ok=True)
    try:
        result = _old(row, folder) if phase == "gamma0" else _new(row, old, folder)
    except Exception as error:
        result = {"passed": False, "error": {"type": type(error).__name__, "message": str(error)}}
    result.update(call_id=row["call_id"], phase=phase,
        native_measurement_identity={**_MEASUREMENT.identity, "measured_context_limit": CONTEXT,
            "measured_reserved_output_tokens": OUTPUT, "recipe_sha256": digest(json_bytes(_MEASUREMENT.recipe))},
        measurement_statistics={key: _MEASUREMENT.statistics[key] - before[key] for key in before})
    result["receipt"] = write(folder / (phase + "-receipt.json"), result)
    return result


def result_checks(rows, *, originals_complete, mechanical_passed):
    targets = [r for r in rows if r["targeted_LA_LB_P4"]]
    submits = [r for r in rows if r["kind"] == "final_fixed_submit"]
    return {"finite_inventory_exact": len(rows) == 21 and inventory_counts(rows) == EXPECTED,
            "original_all_bindings_reproduced": originals_complete,
            "all_reference_integrity_passed": all(r.get("reference_integrity_checks")
                and all(r["reference_integrity_checks"].values()) for r in rows),
            "targeted_eight_hard_fit": len(targets) == 8 and all(r.get("gamma1", {}).get("selected", {}).get("fits") is True for r in targets),
            "final_submit_eleven_hard_fit": len(submits) == 11 and all(r.get("gamma1", {}).get("selected", {}).get("fits") is True for r in submits),
            "mechanical_controls_passed": mechanical_passed}


def replay(inventory_path, candidate_path, controls_path, output, workers=3):
    output = Path(output).resolve()
    require(not output.exists(), "New CPU replay destination must not exist")
    candidate_ref, inventory_ref, controls_ref = map(reference, (candidate_path, inventory_path, controls_path))
    require(candidate_ref["sha256"] == CANDIDATE_SHA256, "Only the predeclared candidate1 is authorized")
    candidate, inventory, controls = (checked_json(r) for r in (candidate_ref, inventory_ref, controls_ref))
    rows = validate_inventory(inventory)
    capacity_binding_ref = reference(CAPACITY_BINDING_PATH)
    require(capacity_binding_ref["sha256"] == CAPACITY_BINDING_SHA256, "Original v047 capacity binding changed")
    capacity_binding = checked_json(capacity_binding_ref)
    require(all(row["historical_preparation"]["recipe_sha256"] == capacity_binding["capacity_recipe_sha256"] for row in rows),
            "The 21 historical requests do not share the bound original capacity recipe")
    require(controls.get("passed") is True, "Finite mechanical controls must pass before actual tokenizer replay")
    require(type(workers) is int and 1 <= workers <= 3, "Use one to three CPU-only workers")
    output.mkdir(parents=True, exist_ok=False)
    before_sources = source_files()
    started = time.time()
    outputs = []
    with ProcessPoolExecutor(max_workers=workers, initializer=_initialize,
            initargs=(inventory["native_cpu_measurement"]["plan"]["path"], candidate, capacity_binding_ref)) as pool:
        original_futures = [pool.submit(_task, "gamma0", row, None, str(output)) for row in rows]
        originals = [future.result() for future in original_futures]
        outputs.extend(originals)
        originals_complete = all(r["passed"] and all(r["original_reproduction_checks"].values()) for r in originals)
        write(output / "gamma0-phase.json", {"all_original_bindings_reproduced": originals_complete,
            "requests": originals, "new_gamma1_measurements_started": False})
        if originals_complete:
            new_futures = [pool.submit(_task, "gamma1", row, old, str(output)) for row, old in zip(rows, originals)]
            revised = [future.result() for future in new_futures]
            outputs.extend(revised)
        else:
            revised = [{"passed": False, "gamma1_not_measured": "Original Gamma0 reproduction did not pass for all 21 sources"} for _ in rows]
    final_rows = []
    for row, old, new in zip(rows, originals, revised):
        final_rows.append({**{k: copy.deepcopy(row[k]) for k in ("kind", "slot_id", "root_id", "condition",
            "pilot_stage", "stage_id", "worker", "member", "call_id", "sampling_seed", "team_token_budget", "targeted_LA_LB_P4")},
            "historical_source": copy.deepcopy(row),
            **{k: v for k, v in old.items() if k not in {"native_measurement_identity", "measurement_statistics", "phase"}},
            **{k: v for k, v in new.items() if k not in {"native_measurement_identity", "measurement_statistics", "phase", "receipt"}},
            "gamma0_receipt": old["receipt"], "gamma1_receipt": new.get("receipt")})
    after_sources = source_files()
    checks = result_checks(final_rows, originals_complete=originals_complete, mechanical_passed=controls["passed"])
    checks.update(candidate_predeclared_exact=reference(candidate_path) == candidate_ref,
        input_source_hashes_unchanged=reference(inventory_path) == inventory_ref and reference(controls_path) == controls_ref,
        source_files_unchanged=after_sources == before_sources, cpu_only=True)
    tokens = sum(result["measurement_statistics"]["native_tokenizer_calls"] for result in outputs)
    renders = sum(result["measurement_statistics"]["native_render_calls"] for result in outputs)
    value = {"version": VERSION, "passed": all(checks.values()), "checks": checks,
        "candidate": candidate_ref, "source_inventory": inventory_ref, "mechanical_controls": controls_ref,
        "historical_capacity_binding": capacity_binding_ref,
        "initialization_revision": "Original v047 full capacity recipe; only recorded software-members metadata migration from source native owner. Prior zero-encoding failure is preserved separately.",
        "inventory": inventory_counts(rows), "rows": final_rows, "source_files": before_sources,
        "native_measurement_identity": outputs[0]["native_measurement_identity"] if outputs else None,
        "native_measurement_identity_consistent": all(r["native_measurement_identity"] == outputs[0]["native_measurement_identity"] for r in outputs),
        "new_tokenizer_calls": tokens, "new_native_render_calls": renders,
        "tokenizer_call_scope": "Actual calls counted by the exact-complete-prompt cache in each CPU process. Original selected/protected, unique Gamma1 selected/protected and same-Gamma0-indices diagnostic may require several encodings per historical request; no segment arithmetic.",
        "cpu_workers": workers, "wall_seconds": time.time() - started, "cpu_core_seconds": None,
        "new_model_calls": 0, "new_world_actions": 0, "new_tests_or_acceptance_calls": 0,
        "new_gpu_operations": 0, "model_weights_loaded": False, "new_parameter_updates": 0,
        "new_backward_calls": 0, "new_model_qualification_calls": 0,
        "automatic_successors": [], "original_results_or_costs_rewritten": False,
        "scope": "Only one predeclared exact-field reference candidate and 21 original-source requests. Eight LA/LB P4 hard rejects plus eleven final submits must fit; HA/P4 and HA/S1 are reported without a fit gate. Gamma0 must first reproduce all original whole-request, selected, render, native-ID and P bindings. No margin gate, alternate candidate, model/world execution or old-result rewrite."}
    require(value["native_measurement_identity_consistent"], "CPU native identity differs across workers/phases")
    value["report_source"] = reference(__file__)
    write(output / "report.json", value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", default=str(ROOT / "runs/v048-controls/source-inventory.json"))
    parser.add_argument("--candidate", default=str(ROOT / "docs/experiments/software-organization-v048-candidate.json"))
    parser.add_argument("--mechanical-controls", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    value = replay(args.inventory, args.candidate, args.mechanical_controls, args.output, args.workers)
    print(json.dumps({"passed": value["passed"], "checks": value["checks"],
                      "new_tokenizer_calls": value["new_tokenizer_calls"], "report": str(Path(args.output).resolve() / "report.json")}, indent=2))


if __name__ == "__main__":
    main()
