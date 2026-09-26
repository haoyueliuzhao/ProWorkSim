"""Read-only, per-window learning signals; never pool policies or evaluator rows.

This imports no model, optimizer, environment or training implementation. Missing
measurements stay unknown, including a group omitted by a diagnostic cap.
"""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

VERSION = "learning-signal-summary-v0.14"
POST_SCOPE = (
    "Old logps are the pre-update full-sequence recomputation, not original cached sampling logps. "
    "Their agreement has a separate numerical gate. The fixed capped selection gives conditional "
    "chosen-token probability proxies; sampled k3 is neither full KL nor an unbiased KL claim."
)


class Records:
    def __init__(self):
        self.references = {}

    def read(self, path, *, required=False):
        path = Path(path).resolve()
        if not path.exists() and not required:
            return None
        data = path.read_bytes()
        self.references[str(path)] = {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        return json.loads(data)


def key(row):
    stage = row.get("stage")
    return row.get("task"), row.get("member_id"), stage.get("label") if isinstance(stage, dict) else stage


def unknown(reason):
    return {"status": "unknown", "reason": reason}


def probability_summary(values, recipe):
    if values is None:
        return unknown("No saved probability measurement for this window")
    if not values:
        return unknown("Saved check list is empty; no probability comparison was measured")
    deltas = [value for row in values for value in row["signed_delta"]]
    if not deltas or any(not math.isfinite(v) for v in deltas):
        raise ValueError("Probability diagnostics require finite original saved deltas")
    return {
        "status": "measured", "decisions": len(values), "sampled_output_tokens": len(deltas),
        "all_saved_checks_passed": all(row["passed"] for row in values),
        "failed_call_ids": [row["call_id"] for row in values if not row["passed"]],
        "max_abs_delta": max(abs(value) for value in deltas),
        "mean_abs_delta_token_weighted": math.fsum(abs(value) for value in deltas) / len(deltas),
        "max_per_decision_mean_abs_delta": max(row["mean_abs_delta"] for row in values),
        "max_tolerance": recipe.get("logprob_max_atol"), "mean_tolerance": recipe.get("logprob_mean_atol"),
        "scope": "Behavior-vs-recomputation numerical agreement; not update magnitude or work quality",
    }



def numerical_failure_details(values, admission, recipe):
    """Locate saved failed gates without tokenization or a new model forward."""
    if values is None:
        return unknown("Probability check was not recorded")
    admitted = {row["call_id"]: row for row in (admission or {}).get("decisions", [])}
    failures = []
    for check in values:
        if check["passed"]:
            continue
        row = admitted.get(check["call_id"])
        trace = (row or {}).get("tokens", {})
        delta = check["signed_delta"]
        output_ids = trace.get("output_ids")
        if output_ids is not None and len(output_ids) != len(delta):
            raise ValueError("Failed gate token positions differ from the original admission")
        behavior = check.get("actual_behavior_logprobs", [None] * len(delta))
        recomputed = check.get("recomputed_logprobs", [None] * len(delta))
        offending = [{"output_index": index, "actual_token_id": output_ids[index] if output_ids else None,
                      "behavior_logprob": behavior[index], "recomputed_logprob": recomputed[index],
                      "signed_logprob_delta": value}
                     for index, value in enumerate(delta) if abs(value) > recipe["logprob_max_atol"]]
        input_count = len(trace["input_ids"]) if isinstance(trace.get("input_ids"), list) else None
        output_count = len(output_ids) if output_ids is not None else None
        failures.append({"call_id": check["call_id"], "slot_id": (row or {}).get("slot_id"),
                         "task": (row or {}).get("task"), "member_id": (row or {}).get("member_id"),
                         "stage": copy.deepcopy((row or {}).get("stage")),
                         "input_tokens": input_count, "output_tokens": output_count,
                         "full_sequence_tokens": input_count + output_count if input_count is not None and output_count is not None else None,
                         "max_abs_delta": check.get("max_abs_delta", max(map(abs, delta))),
                         "mean_abs_delta": check["mean_abs_delta"],
                         "maximum_gate_failed": max(map(abs, delta)) > recipe["logprob_max_atol"],
                         "mean_gate_failed": check["mean_abs_delta"] > recipe["logprob_mean_atol"],
                         "tokens_exceeding_maximum_gate": offending,
                         "tokens_exceeding_maximum_gate_count": len(offending),
                         "scope": "Positions/IDs and probabilities come only from original saved traces; no decoding or probability recomputation was performed."})
    return {"status": "recorded", "failed_calls": failures, "failed_call_count": len(failures),
            "maximum_exceeding_token_count": sum(r["tokens_exceeding_maximum_gate_count"] for r in failures)}


def post_summary(records):
    if not records:
        return unknown("No post-update sample saved for this group; fixed cap, no update, or incomplete recording")
    deltas = [delta for row in records for delta in row["new_minus_old_logprob"]]
    if not deltas or any(not math.isfinite(value) for value in deltas):
        raise ValueError("Post-update record has no finite actual chosen-token deltas")
    ratios = [math.exp(value) for value in deltas]
    return {
        "status": "measured", "sampled_decisions": len(records), "sampled_output_tokens": len(deltas),
        "call_ids": [row["call_id"] for row in records],
        "max_abs_logp_delta": max(abs(value) for value in deltas),
        "mean_abs_logp_delta": math.fsum(abs(value) for value in deltas) / len(deltas),
        "sampled_ratio_range": [min(ratios), max(ratios)],
        "sampled_old_to_new_logratio_mean": -math.fsum(deltas) / len(deltas),
        "sampled_k3_proxy_mean": math.fsum(math.expm1(value) - value for value in deltas) / len(deltas),
        "saved_samples": copy.deepcopy(records), "scope": POST_SCOPE,
    }


def learning_window(directory, spec, index, recorded, metadata, recipe, files):
    directory = Path(directory)
    update = files.read(directory / "update/report.json")
    admission = files.read(directory / "update/admission.json")
    signal = files.read(directory / "update/signal-diagnostics.json")
    post = files.read(directory / "update/post-update-sampled-policy.json")
    behavior = files.read(directory / "update/behavior-probability-check.json")
    backward = files.read(directory / "update/gradient-probability-check.json")
    losses = files.read(directory / "update/losses.json")
    present = recorded is not None or directory.exists()
    result = {
        **metadata, "window_index": index, "window_id": spec["window_id"], "mode": "online",
        "planned_slots": len(spec["slots"]),
        "status": update.get("status") if update else (recorded or {}).get("status", "not_started" if not present else "incomplete_record"),
        "before_actor_identity": (update or recorded or {}).get("before_actor_identity"),
        "after_actor_identity": (update or recorded or {}).get("after_actor_identity"),
        "credit_assignment": recipe.get("credit_assignment", "terminal_mc"),
        "actual_optimizer_steps": {"status": "recorded", "actor": update["actor_optimizer_steps"],
                                   "critic": update["critic_optimizer_steps"]} if update else unknown("Update report absent; do not infer zero steps"),
        "behavior_probability": probability_summary(behavior, recipe),
        "backward_probability": probability_summary(backward, recipe),
        "numerical_failure_details": {"behavior": numerical_failure_details(behavior, admission, recipe),
                                      "backward": numerical_failure_details(backward, admission, recipe)},
        "backward_decisions_completed": (update or {}).get("backward_decisions_completed"),
        "saved_gradients_before_clip_present": (directory / "update/gradients-before-clip.pt").exists(),
        "update_stage": (update or {}).get("stage"),
        "admitted_decisions": len(admission["decisions"]) if admission else None,
        "admitted_output_tokens": sum(len(r["tokens"]["output_ids"]) for r in admission["decisions"]) if admission else None,
        "composition": (update or {}).get("composition"),
        "saved_composition_weights": sorted({row["composition_weight"] for row in losses}) if losses else None,
        "no_composition_pooling": "Stored weights describe this exact actor/window only; no b or method-support averaging across theta",
        "rows": [],
    }
    if signal is None:
        result["signal_status"] = unknown("No saved group diagnostics; no retrospective stage or gradient reconstruction")
        result["post_update"] = post_summary(post.get("decisions", []) if post else [])
        return result
    result["signal_status"] = {"status": "recorded"}
    capture = signal.get("gradient_capture", {})
    result["gradient_capture"] = copy.deepcopy(capture)
    groups = {key(group): group for group in capture.get("groups", [])}
    if len(groups) != len(capture.get("groups", [])):
        raise ValueError("Duplicate stored gradient group")
    total_norm = capture.get("total_gradient_l2_norm")
    total_tokens = result["admitted_output_tokens"]
    admitted = {row["call_id"]: row for row in admission["decisions"]} if admission else {}
    post_rows = post.get("decisions", []) if post else []
    result["post_update"] = {**post_summary(post_rows),
        "maximum_decisions": (post or {}).get("maximum_decisions"),
        "old_probability_source": (post or {}).get("old_probability_source", "unknown: metadata absent"),
        "new_probability_source": (post or {}).get("new_probability_source", "unknown: metadata absent")}
    if post and admission:
        selected, seen = [], set()
        for row in admission["decisions"]:
            group_key = key(row)
            if group_key not in seen and len(selected) < post["maximum_decisions"]:
                selected.append(row["call_id"])
            seen.add(group_key)
        result["post_update"]["matches_predeclared_first_group_selection"] = selected == [row["call_id"] for row in post_rows]
    for group in signal["groups"]:
        group_key = key(group)
        rows = [admitted[call] for call in group["call_ids"] if call in admitted]
        if rows and (len(rows) != len(group["call_ids"]) or any(key(row) != group_key for row in rows)):
            raise ValueError("Saved signal group does not bind its actual admission rows")
        gradient = groups.get(group_key)
        omitted = list(group_key) in capture.get("omitted_groups", [])
        norm = gradient.get("gradient_l2_norm") if gradient else None
        dot = gradient.get("dot_with_total_gradient") if gradient else None
        gradient_record = ({"status": "measured", **copy.deepcopy(gradient)} if gradient else
                           unknown("Omitted by frozen group cap" if omitted else "No actual group gradient saved"))
        normalization = {
            "member_token_surrogate_mass": math.fsum(len(row["tokens"]["output_ids"]) / row["actor_denominator"] for row in rows) if len(rows) == len(group["call_ids"]) else None,
            "raw_output_token_fraction_in_window": group["output_tokens"] / total_tokens if total_tokens else None,
            "gradient_norm_ratio_nonadditive": norm / total_norm if norm is not None and total_norm else None,
            "signed_dot_fraction_of_total_squared_norm": dot / total_norm**2 if dot is not None and total_norm else None,
            "scope": "Token fraction and surrogate mass differ. Norm ratios are not additive shares. Signed dot fractions can be negative or exceed 1; they measure alignment in this actual update, not causal work benefit.",
        }
        result["rows"].append({**metadata, "window_id": spec["window_id"], "window_index": index,
                               "actor_identity": result["before_actor_identity"], **copy.deepcopy(group),
                               "actual_group_gradient": gradient_record, "normalization": normalization,
                               "post_update": post_summary([row for row in post_rows if key(row) == group_key])})
    return result


def summarize_study(study_path, project, source=None):
    files = Records()
    project = Path(project).resolve()
    study = files.read(study_path, required=True)
    manifest = study.get("manifest", study)
    source = Path(source or study.get("source") or project).resolve()
    jobs = []
    for job in manifest["jobs"]:
        root = project / job["run"]
        protocol_path = root / "online/protocol.json"
        if not protocol_path.exists():
            protocol_path = source / job["protocol"]
        protocol = files.read(protocol_path, required=True)
        online = files.read(root / "online/report.json")
        records = {row["window_id"]: row for row in (online or {}).get("windows", [])}
        metadata = {"job": job["name"], "condition": protocol.get("condition"),
                    "replicate_index": protocol.get("replicate_index"), "training_seed": protocol["recipe"]["seed"]}
        item = {**metadata, "run": str(root), "status": (online or {}).get("status", "not_started"),
                "source_before": files.read(root / "source-before.json"),
                "source_comparison": files.read(root / "source-comparison.json"),
                "actual_steps_total": {"actor": online.get("actor_steps_total"), "critic": online.get("critic_steps_total")} if online else None,
                "training_windows": [], "evaluation_windows_excluded": []}
        for index, spec in enumerate(protocol["windows"]):
            mode = spec.get("mode", protocol.get("mode", "online"))
            recorded = records.get(spec["window_id"])
            if mode not in {"online", "evaluate"} or recorded and recorded.get("mode", mode) != mode:
                raise ValueError("Stored or declared window mode mismatch")
            directory = root / "online" / ("window-" + str(index))
            if mode == "evaluate":
                evaluation = files.read(directory / "evaluation/report.json")
                item["evaluation_windows_excluded"].append({
                    "window_index": index, "window_id": spec["window_id"], "mode": mode,
                    "planned_slots": len(spec["slots"]), "status": (recorded or {}).get("status", "not_started"),
                    "saved_optimizer_steps": {"actor": evaluation.get("actor_optimizer_steps"), "critic": evaluation.get("critic_optimizer_steps")} if evaluation else None,
                    "guard": files.read(directory / "evaluation-guard.json"),
                    "scope": "Never included in learning signal rows or training normalization",
                })
            else:
                item["training_windows"].append(learning_window(directory, spec, index, recorded, metadata, protocol["recipe"], files))
        jobs.append(item)
    return {"version": VERSION, "jobs": jobs, "source_files": list(files.references.values()),
            "original_files_changed": False, "additional_model_forwards": 0,
            "aggregation_scope": "Every row retains condition/seed/window/actual actor identity/task/member/saved public stage. No theta pooling, no evaluation-to-training pooling, no imputed missing gradients or post-update samples.",
            "post_probability_scope": POST_SCOPE,
            "snapshot_scope": "Read-only file snapshot; a running or interrupted window can have incomplete measurements. Unknown is not measured zero."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True, help="Frozen study manifest or actual scheduler.json")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, help="Frozen protocol source root; scheduler source is used by default")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Use a new report path; no existing record is overwritten")
    result = summarize_study(args.study, args.project, args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "jobs": len(result["jobs"]),
                      "training_windows": sum(len(job["training_windows"]) for job in result["jobs"]),
                      "additional_model_forwards": 0}))


if __name__ == "__main__":
    main()
