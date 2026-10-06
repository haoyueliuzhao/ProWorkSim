"""Publish a read-only detailed v035 report from immutable run evidence and analyses.

No model, verifier, mapper, tokenizer, gradient or worker is executed here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

BJT = dt.timezone(dt.timedelta(hours=8))


def read(path):
    return json.loads(Path(path).read_text())


def reference(path, root):
    path = Path(path)
    return {"path": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


def wilson(k, n):
    z, p = 1.959963984540054, k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return {"numerator": k, "denominator": n, "proportion": p,
            "wilson_95": [center - half, center + half],
            "assumption": "Predeclared seeds treated as independent repeats in this exact situation; independence and transfer to other roots are not established here."}


def build(root, analyses, destination):
    root, analyses, destination = map(lambda p: Path(p).resolve(), (root, analyses, destination))
    run = root / "runs/software-support-v035"
    actual = run / "qwen3.5-9b/actual"
    original = read(root / "docs/experiments/software-support-v035.json")
    plan, supervisor = read(run / "plan.json"), read(run / "supervisor.json")
    finish = read(root / "runs/software-support-v035-finish.json")
    gate = read(actual / "support-gate.json")
    accounting, methods, delivery = [read(analyses / (name + ".json")) for name in ("accounting", "methods", "delivery")]
    assert original["status"] == supervisor["status"] == "complete"
    assert original["known_results"] == accounting["summary"]["closed_known_results"] == 16
    assert original["complete_successes"] == delivery["summary"]["R1_over_all_slots"]["passed"] == methods["summary"]["complete_successes"] == 15
    assert original["sampling_usage"]["charged_tokens"] == accounting["summary"]["total_charged_tokens"] == 7286778
    assert original["sampling_usage"]["attempts"] == accounting["summary"]["sampled_calls"] == 701
    assert accounting["actual_usage_conservation"]["passed"]
    assert accounting["common_and_guards"]["all_16_slot_guards_passed"]
    assert gate["status"] == "no_configurable_support" and gate["selected_block"] is None
    assert methods["original_scores_changed"] is methods["original_mapping_changed"] is False
    assert delivery["new_acceptance_executions"] == accounting["new_verifier_executions"] == 0
    assert len(accounting["slots"]) == len(methods["episodes"]) == len(delivery["slots"]) == 16
    for a, m, d in zip(accounting["slots"], methods["episodes"], delivery["slots"]):
        assert a["slot_id"] == m["slot_id"] == d["slot_id"]
        assert a["R"] == m["original_R"] == d["assessment"]["R"]
    summary = accounting["summary"]
    derived = {"input_fraction": summary["input_tokens"] / summary["total_charged_tokens"],
        "mean_actual_total_tokens_per_call": summary["total_charged_tokens"] / summary["sampled_calls"],
        "mean_actual_input_tokens_per_call": summary["input_tokens"] / summary["sampled_calls"],
        "mean_own_output_tokens_per_call": summary["own_output_target_tokens"] / summary["sampled_calls"],
        "mean_actual_tokens_per_episode": summary["total_charged_tokens"] / 16,
        "mean_fraction_of_episode_token_limit": summary["total_charged_tokens"] / 8000000,
        "post_first_accepted_submit_calls": sum(row["post_submission_activity"]["after_first_accepted_fixed_submission"]["later_actual_calls"] for row in accounting["slots"] if row["submitted"]),
        "post_first_accepted_submit_tokens": sum(row["post_submission_activity"]["after_first_accepted_fixed_submission"]["later_tokens"] for row in accounting["slots"] if row["submitted"])}
    assert derived["post_first_accepted_submit_calls"] == 264
    assert derived["post_first_accepted_submit_tokens"] == 2996533
    # Keep critical per-version/acceptance references without duplicating full
    # expected/observed fixtures and raw source text into the repository report.
    delivery_compact = []
    for row in delivery["slots"]:
        compact = {key: row[key] for key in ("slot_index", "slot_id", "assessment", "assessment_source",
            "world_snapshot_source", "source_revision", "actors", "successful_world_event_counts",
            "task_count_at_end", "fixed_patch_count", "successful_submit_event_count", "acceptance_counts")}
        if "final_assessed_delivery" in row:
            compact["final_assessed_delivery"] = {key: value for key, value in row["final_assessed_delivery"].items()
                if key not in {"fixed_application_sources", "fixed_member_test_source", "message"}}
            compact["dimension_checks"] = row["dimension_checks"]
        else:
            compact["last_archived_public_failures"] = row["last_archived_public_failures"]
            compact["no_additional_assessment"] = row["no_additional_assessment"]
        delivery_compact.append(compact)
    sources = {name: reference(path, root) for name, path in {
        "original_automatic_report": root / "docs/experiments/software-support-v035.json",
        "plan": run / "plan.json", "supervisor": run / "supervisor.json",
        "finish": root / "runs/software-support-v035-finish.json",
        "worker": actual / "report.json", "support_gate": actual / "support-gate.json",
        "training_material_binding": actual / "training-material-binding.json",
        "protocol": root / "docs/experiments/software-support-v035-protocol.md",
        "preparation": root / "docs/experiments/software-support-v035-preparation.json",
        **{name + "_analysis": analyses / (name + ".json") for name in ("accounting", "methods", "delivery")},
        "generator": Path(__file__).resolve(),
    }.items()}
    result = {"version": "software-support-detailed-report-v0.35", "generated_at_bjt": dt.datetime.now(BJT).isoformat(),
        "source_execution": plan["source"], "original_result_commit": finish["report_commit"],
        "new_model_calls": 0, "new_verifier_executions": 0, "new_mapper_executions": 0,
        "new_probability_or_gradient_computations": 0, "new_tokenizations": 0,
        "historical_scores_or_mapping_changed": False, "report_consistency_checks_passed": True,
        "summary": summary, "derived_arithmetic": derived,
        "conditional_uncertainty": {"complete_delivery": wilson(15, 16), "mapped_support_yield": wilson(10, 16)},
        "resources": accounting["resources"], "actual_usage_conservation": accounting["actual_usage_conservation"],
        "training_material": accounting["training_material"], "common_and_guards": accounting["common_and_guards"],
        "per_slot_accounting": accounting["slots"], "method_analysis": methods,
        "delivery_analysis": {"summary": delivery["summary"], "source_contract": delivery["source_contract"],
            "slots": delivery_compact, "member_script_early_exit_inference": delivery["member_script_early_exit_inference"]},
        "support_gate": {key: gate[key] for key in ("status", "selected_block", "member_support_states", "original_slot_count", "gradient_or_update_identifiability_checked")},
        "stages_not_executed": ["postcollection_P3_probe_freeze", "common_B_trial", "G_raw_trials", "I_P_trials",
            "formal_updates", "contribution_development", "independent_confirmation"],
        "effectiveness_deltas": {"I_minus_B": None, "I_minus_G_raw": None},
        "sources": sources,
        "scope": "Read-only detailed closure of one sixteen-seed exact-context current-policy collection. Finite work success, conservative observable method support, static original-token admission and unexecuted learning effects remain separate. No broad absence-of-collaboration inference, score changes or retrospective P3 admission."}
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "software-support-v035-final.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--analyses", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build(args.data_root, args.analyses or args.data_root / "runs/v035-report-analysis",
                   args.output or args.data_root / "docs/experiments")
    print(json.dumps({"version": result["version"], "report_consistency_checks_passed": True,
                      "new_model_calls": 0, "complete_successes": result["summary"]["complete_successes"]}))


if __name__ == "__main__":
    main()
