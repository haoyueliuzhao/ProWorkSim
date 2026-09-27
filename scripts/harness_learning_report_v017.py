"""Read-only online H2 outcomes; never infer missing final work or rescore worlds."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def reference(path):
    return (
        {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        if path.exists()
        else None
    )


def measures(rows, task_weights=None):
    known = [r for r in rows if r["state"] == "closed_known"]
    complete = len(known) == len(rows) and bool(rows)
    result = {
        "planned": len(rows),
        "states": dict(Counter(r["state"] for r in rows)),
        "known": len(known),
        "observed_reward_sum": sum(r["reward"] for r in known),
        "observed_completed": sum(r["completed"] is True for r in known),
        "mean_reward": sum(r["reward"] for r in known) / len(rows) if complete else None,
        "completion_rate": sum(r["completed"] is True for r in known) / len(rows)
        if complete
        else None,
        "missing_rule": "Unknown/unstarted observations stay in the declared denominator; no imputation.",
    }
    tasks = {}
    for task in task_weights or sorted({r["task"] for r in rows}):
        own = [r for r in rows if r["task"] == task]
        all_known = bool(own) and all(r["state"] == "closed_known" for r in own)
        tasks[task] = {
            "planned": len(own),
            "mean_reward": sum(r["reward"] for r in own) / len(own) if all_known else None,
            "completion_rate": sum(r["completed"] is True for r in own) / len(own)
            if all_known
            else None,
        }
    result["tasks"] = tasks
    if task_weights:
        if abs(sum(task_weights.values()) - 1) > 1e-12:
            raise ValueError("Primary task weights must sum to one")
        ready = all(tasks[t]["mean_reward"] is not None for t in task_weights)
        result.update(
            primary_measure="task_macro_mean",
            primary_task_weights=task_weights,
            primary_mean_reward=sum(task_weights[t] * tasks[t]["mean_reward"] for t in task_weights)
            if ready
            else None,
            primary_completion_rate=sum(
                task_weights[t] * tasks[t]["completion_rate"] for t in task_weights
            )
            if ready
            else None,
        )
    else:
        result.update(
            primary_measure="raw_episode_mean",
            primary_mean_reward=result["mean_reward"],
            primary_completion_rate=result["completion_rate"],
        )
    return result


def lightweight_advantages(admission, update, decisions, slot_rows):
    values, advantages = update.get("old_critic_values"), update.get("advantages")
    targets = admission.get("decisions", [])
    if (
        not isinstance(values, list)
        or not isinstance(advantages, list)
        or len(values) != len(advantages)
        or len(values) != len(targets)
    ):
        return {
            "status": "unavailable",
            "reason": "Complete saved advantages/current target rows not present",
        }
    slots = {r["slot_id"]: r for r in slot_rows}
    groups = {}
    for target, value, advantage in zip(targets, values, advantages):
        slot = slots.get(target["slot_id"], {})
        outcome = (
            "complete"
            if slot.get("completed") is True
            else "partial"
            if (slot.get("reward") or 0) > 0
            else "zero_or_unknown"
        )
        action = decisions.get((target["member_id"], target["call_id"]), "unmapped_decision")
        key = (target.get("task"), target["member_id"], action, outcome)
        groups.setdefault(key, []).append((value, advantage, len(target["tokens"]["output_ids"])))
    return {
        "status": "measured_saved_values",
        "groups": [
            {
                "task": k[0],
                "member": k[1],
                "action": k[2],
                "episode_outcome": k[3],
                "decisions": len(v),
                "output_tokens": sum(x[2] for x in v),
                "mean_old_critic": sum(x[0] for x in v) / len(v),
                "mean_advantage": sum(x[1] for x in v) / len(v),
                "positive_advantage_decisions": sum(x[1] > 0 for x in v),
            }
            for k, v in groups.items()
        ],
        "scope": "Read-only saved role/action/outcome association; no extra forward, gradient decomposition or causal credit claim. Terminal MC may credit later ineffective actions after partial outcomes.",
    }


def build_report(run):
    run = Path(run).resolve()
    protocol = read(run / "launch-protocol.json")
    if not protocol or protocol.get("stage") not in {"H2", "H2_v018", "ID_support_v018"}:
        raise ValueError("An actual declared H2 run is required")
    online = read(run / "online/report.json", {})
    records = {w["window_id"]: w for w in online.get("windows", [])}
    windows = []
    for index, spec in enumerate(protocol["windows"]):
        folder = run / f"online/window-{index}"
        summary = read(folder / "collection/summary.json", {})
        progress = summary.get("slots") or read(folder / "collection/progress.json", [])
        by_id = {r["slot_id"]: r for r in progress}
        rows = []
        for j, s in enumerate(spec["slots"]):
            original = by_id.get(s["slot_id"], {})
            manifest_path = folder / f"collection/slot-{j}/episode/manifest.json"
            manifest = read(manifest_path, {})
            reward = original.get("reward", {})
            known = (
                manifest.get("status") == "closed"
                and reward.get("eligible") is True
                and type(reward.get("reward")) in (int, float)
            )
            state = (
                "closed_known"
                if known
                else "closed_unknown"
                if manifest.get("status") == "closed"
                else "open"
                if manifest
                else "not_started"
            )
            rows.append(
                {
                    **s,
                    "state": state,
                    "reward": reward.get("reward") if known else None,
                    "completed": reward.get("completed") if known else None,
                    "components": reward.get("components"),
                    "exclusions": reward.get("exclusions"),
                    "record_validity": original.get("work_validity", {})
                    .get("components", {})
                    .get("record", {})
                    .get("value"),
                    "manifest": reference(manifest_path),
                }
            )
        record = records.get(spec["window_id"], {})
        update = record.get("update") or read(folder / "update/report.json", {})
        admission = read(folder / "update/admission.json", {})
        target_ids = [(r["member_id"], r["call_id"]) for r in admission.get("decisions", [])]
        decisions = {}
        for j in range(len(spec["slots"])):
            runtime = read(folder / f"collection/slot-{j}/runtime.json", {})
            for event in runtime.get("experience", {}).get("events", []):
                p = event.get("payload", {})
                if event["kind"] == "policy_decision":
                    decision = p.get("decision", p)
                    call = decision.get("model_call_id") or p.get("model_call_id")
                    if call:
                        decisions[(event.get("worker_id"), call)] = decision.get(
                            "action"
                        ) or decision.get("kind")
        action_counts = Counter(decisions.get(key, "unmapped_decision") for key in target_ids)
        windows.append(
            {
                "window_id": spec["window_id"],
                "mode": spec["mode"],
                "phase": spec["phase"],
                "status": record.get("status", "not_started"),
                "metrics": measures(
                    rows, protocol.get("primary_evaluation", {}).get("task_weights")
                ),
                "rows": rows,
                "before_actor_identity": record.get("before_actor_identity"),
                "after_actor_identity": record.get("after_actor_identity"),
                "evaluation_guard": record.get("evaluation_guard"),
                "update": {
                    k: update.get(k)
                    for k in [
                        "status",
                        "actor_optimizer_steps",
                        "critic_optimizer_steps",
                        "training_happened",
                        "admitted_decisions",
                        "admitted_output_tokens",
                        "behavior_probability_passed",
                        "backward_decisions_completed",
                        "changed_actor_elements",
                        "gradient_norms",
                        "zero_signal_window",
                        "interruption",
                        "error",
                    ]
                },
                "lightweight_advantage_diagnostics": lightweight_advantages(
                    admission, update, decisions, rows
                ),
                "actual_actor_targets_by_action": dict(action_counts),
                "actor_targets_unique": len(target_ids) == len(set(target_ids)),
                "target_input_rule": "Original input_ids/output_ids from current-window member completions; tool and colleague content is input-only.",
                "references": {
                    "collection": reference(folder / "collection/summary.json"),
                    "update": reference(folder / "update/report.json"),
                    "actor_admission": reference(folder / "update/admission.json"),
                    "behavior_checks": reference(folder / "update/behavior-probability-check.json"),
                    "gradient_checks": reference(folder / "update/gradient-probability-check.json"),
                },
            }
        )
    initial = next((w for w in windows if w["phase"] == "initial"), None)
    final = next((w for w in windows if w["phase"] == "final"), None)
    delta = None
    comparison_checks = {
        "run_complete": online.get("status") == "complete",
        "source_unchanged": (read(run / "source-comparison.json", {}) or {}).get("unchanged")
        is True,
        "evaluation_guards": bool(initial and final)
        and all(
            (w.get("evaluation_guard") or {}).get("learning_unchanged") is True
            and (w.get("evaluation_guard") or {}).get("rng_restored_exactly") is True
            for w in (initial, final)
            if w is not None
        ),
        "all_initial_and_final_known": bool(initial and final)
        and initial["metrics"]["primary_mean_reward"] is not None
        and final["metrics"]["primary_mean_reward"] is not None,
    }
    if all(comparison_checks.values()):
        pairs = {}
        for row in initial["rows"]:
            pairs[row["case_id"], row["sampling_seed"]] = row
        if set(pairs) != {(r["case_id"], r["sampling_seed"]) for r in final["rows"]}:
            raise ValueError("Frozen initial/final inventory differs")
        delta = {
            "primary_measure": final["metrics"]["primary_measure"],
            "mean_reward": final["metrics"]["primary_mean_reward"]
            - initial["metrics"]["primary_mean_reward"],
            "secondary_raw_episode_mean_difference": final["metrics"]["mean_reward"]
            - initial["metrics"]["mean_reward"],
            "completion_rate": final["metrics"]["primary_completion_rate"]
            - initial["metrics"]["primary_completion_rate"],
            "paired": [
                {
                    "case_id": r["case_id"],
                    "seed": r["sampling_seed"],
                    "before": pairs[r["case_id"], r["sampling_seed"]]["reward"],
                    "after": r["reward"],
                }
                for r in final["rows"]
            ],
            "scope": "One finite training seed/dose and same-source locked facts; no MC/RTG or ID-VTDO causal comparison.",
        }
    return {
        "version": "harness-learning-readonly-v0.18",
        "run_root": str(run),
        "status": online.get("status", "not_started"),
        "experiment_id": protocol["experiment_id"],
        "candidate_id": protocol["candidate_id"],
        "harness": protocol["harness"],
        "selection": protocol["selection"],
        "protocol": reference(run / "launch-protocol.json"),
        "source_before": read(run / "source-before.json"),
        "source_after": read(run / "source-after.json"),
        "source_comparison": read(run / "source-comparison.json"),
        "windows": windows,
        "actor_steps_total": online.get("actor_steps_total"),
        "critic_steps_total": online.get("critic_steps_total"),
        "comparison_checks": comparison_checks,
        "fixed_harness_learning_delta": delta,
        "scope": "Saved records only, no world/evaluator/model execution. Migration is separate and not pooled into pilot learning.",
    }


def markdown(d):
    lines = [
        "# H2 实际记录（保留协议与主效用口径）",
        "",
        f"状态：{d['status']}；组合：{d['candidate_id']} / {d['harness']}。",
        "",
        "| 窗口 | 类型 | 已知/计划 | 主效用均值 | actor/critic步数 |",
        "|---|---|---:|---:|---|",
    ]
    for w in d["windows"]:
        m = w["metrics"]
        u = w["update"]
        lines.append(
            f"|{w['window_id']}|{w['mode']}|{m['known']}/{m['planned']}|{m['primary_mean_reward']}|{u['actor_optimizer_steps']}/{u['critic_optimizer_steps']}|"
        )
    lines += [
        "",
        "未知和未启动不计零，不据部分窗口宣布学习收益。",
        "",
        "固定harness初末差：" + json.dumps(d["fixed_harness_learning_delta"], ensure_ascii=False),
    ]
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError("New report directory required")
    d = build_report(a.run)
    a.output.mkdir(parents=True)
    (a.output / "report.json").write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    (a.output / "report.md").write_text(markdown(d))
    print(
        json.dumps(
            {"status": d["status"], "actor_steps": d["actor_steps_total"], "output": str(a.output)}
        )
    )


if __name__ == "__main__":
    main()
