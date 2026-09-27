"""Read-only terminal N/E accounting; no scoring rerun or model calls."""

import argparse
from pathlib import Path

from proworksim.storage import atomic_write, digest, json_bytes, read_json


def read(path):
    return read_json(path) if path.exists() else None


def reference(path):
    return {"path": str(path.resolve()), "sha256": digest(path.read_bytes())}


def _conjunction(checks):
    """Three-valued evidence: missing evidence is not a failed observation."""
    if any(check is False for check in checks):
        return False
    return True if all(check is True for check in checks) else None


def _global_frozen_evidence(report, terminal):
    if not terminal:
        return None
    return _conjunction([
        report.get("final_identity_matches_initial"), report.get("source_unchanged"),
        *(report[name] == 0 if report.get(name) is not None else None
          for name in ("actor_steps", "critic_steps")),
    ])


def _slot_frozen_evidence(row, guard, global_valid, terminal):
    if not terminal:
        return None
    return _conjunction([row.get("status") == "closed", global_valid,
                         guard.get("learning_unchanged"), guard.get("rng_restored_exactly")])


def summarize(root, output=None):
    root = Path(root).resolve()
    output = Path(output).resolve() if output is not None else root
    state = read_json(root / "state.json")
    jobs = state["jobs"]
    result = {"version": "N-E-terminal-accounting-v0.21.1", "supervisor_status": state["status"],
              "source": state["source"], "jobs": jobs, "N": None, "E": None,
              "reporter_script": reference(Path(__file__)), "input_run": str(root),
              "parameter_updates_authorized": 0, "training_started": False,
              "scope": "Saved observations only. No model/learner work, score recomputation, retries or old-P1 backfill performed by reporting."}
    n = read(root / "N/report.json")
    if n:
        data = n.get("paths") or read(root / "N/paths.json") or {}
        result["N"] = {"status": n["status"], "report": reference(root / "N/report.json"),
                       "direction": data.get("direction"), "cached_gradient_path": data.get("cached_gradient_path"),
                       "source_unchanged": n.get("source_unchanged"),
                       "actor_unchanged": data.get("actor_unchanged"), "paths": {}}
        for name, path in data.get("paths", {}).items():
            check = path.get("comparison_to_original_sampling", {})
            result["N"]["paths"][name] = {
                "status": path.get("status"), "elapsed_seconds": path.get("elapsed_seconds"),
                "max_abs_delta": check.get("max_abs_delta"), "mean_abs_delta": check.get("mean_abs_delta"),
                "original_gate_passed": check.get("passed"),
                "branch_counts": path.get("branch_counts"),
                "gradient_execution": path.get("gradient_execution"),
                "peak_gpu_allocated_bytes": path.get("peak_gpu_allocated_bytes")}
    e = read(root / "E/report.json")
    if e:
        # A completed slot during a live run has no final whole-run identity
        # evidence yet. An interrupted line can still retain earlier known work.
        job_status = jobs.get("E", {}).get("status", "")
        terminal = (state["status"] in {"closed", "supervisor_stopped"}
                    and (job_status in {"complete", "stopped"}
                         or job_status.startswith("not_started_")))
        global_valid = _global_frozen_evidence(e, terminal)
        rows = []
        for row in e.get("rows", read(root / "E/progress.json") or []):
            assessment = row.get("assessment", {})
            guard = row.get("evaluation_guard")
            if guard is None and type(row.get("slot")) is int and row["slot"] >= 0:
                guard = read(root / "E" / f"slot-{row['slot']}" / "evaluation-guard.json")
            guard = guard or {}
            rows.append({"case_id": row["case_id"], "status": row["status"],
                         "eligible": assessment.get("eligible"), "reward": assessment.get("reward"),
                         "completed": assessment.get("completed"), "components": assessment.get("components"),
                         "record_trust": assessment.get("record_trust"),
                         "independent_assessability": assessment.get("independent_assessability"),
                         "mapper": assessment.get("mapper"), "error": row.get("error"),
                         "evaluation_guard": guard,
                         "frozen_policy_evidence_valid": _slot_frozen_evidence(row, guard, global_valid, terminal)})
        result["E"] = {"status": e["status"], "report": reference(root / "E/report.json"),
                       "planned": e.get("planned_episodes"), "started": len(rows),
                       "known": sum(x["eligible"] is True and x["reward"] is not None for x in rows),
                       "complete_responsibilities": sum(x["completed"] is True for x in rows),
                       "rows": rows, "source_unchanged": e.get("source_unchanged"),
                       "evidence_terminal": terminal,
                       "global_frozen_policy_evidence_valid": global_valid,
                       "frozen_policy_evidence_valid_count": sum(x["frozen_policy_evidence_valid"] is True for x in rows),
                       "frozen_policy_evidence_unknown_count": sum(x["frozen_policy_evidence_valid"] is None for x in rows),
                       "frozen_policy_known": sum(x["frozen_policy_evidence_valid"] is True and x["eligible"] is True
                                                  and x["reward"] is not None for x in rows),
                       "frozen_policy_complete_responsibilities": sum(x["frozen_policy_evidence_valid"] is True
                                                                      and x["completed"] is True for x in rows),
                       "initial_actor_identity": e.get("initial_actor_identity"),
                       "final_actor_identity": e.get("final_actor_identity"),
                       "final_identity_matches_initial": e.get("final_identity_matches_initial"),
                       "identity_check_error": e.get("identity_check_error"),
                       "source_before": e.get("source_before"), "source_after": e.get("source_after"),
                       "source_check_error": e.get("source_check_error"),
                       "actor_steps": e.get("actor_steps"), "critic_steps": e.get("critic_steps"),
                       "scope": "Known work outcomes remain known even when frozen-policy guards fail or are unavailable. Frozen-policy evidence requires terminal whole-run identity/source/zero-step guards and a closed slot with both evaluation guards. Six development situations, not population success or learning gain."}
    elapsed = [j.get("elapsed_gpu_seconds") for j in jobs.values() if j.get("attempted")]
    result["gpu_seconds"] = sum(elapsed) if all(isinstance(x, (int, float)) for x in elapsed) else None
    lines = ["# v0.21 N/E 实际终态", "", "本文件自动只读汇总保存记录；不重算评分、不启动模型或训练。", "",
             f"监督状态：{state['status']}；已记录模型进程设备秒：{result['gpu_seconds']}。", "",
             "## N：固定原 token 数值诊断", ""]
    if result["N"]:
        lines += [f"状态：{result['N']['status']}。", "", "| 路径 | 最大差 | 平均差 | 原门 |",
                  "|---|---:|---:|---|"]
        for name, row in result["N"]["paths"].items():
            lines.append(f"| {name} | {row['max_abs_delta']} | {row['mean_abs_delta']} | {row['original_gate_passed']} |")
        lines += ["", str(result["N"].get("direction")), "",
                  "梯度前向不等于反向通过；cache 重放不等于已建立可微缓存训练路径。"]
    else:
        lines += ["尚无可读N报告；查看state/日志区分未开始、执行错误或中断，不能填成通过。"]
    lines += ["", "## E：独立冻结参数工作", ""]
    if result["E"]:
        summary = result["E"]
        lines += [f"状态：{summary['status']}；计划{summary['planned']}，已开始{summary['started']}，已知{summary['known']}，完整责任{summary['complete_responsibilities']}。", "",
                  f"严格冻结证据有效{summary['frozen_policy_evidence_valid_count']}，未知{summary['frozen_policy_evidence_unknown_count']}；其中已知业务分{summary['frozen_policy_known']}，完整责任{summary['frozen_policy_complete_responsibilities']}。", "",
                  f"末身份一致：{summary['final_identity_matches_initial']}；actor/critic步数：{summary['actor_steps']}/{summary['critic_steps']}；源一致：{summary['source_unchanged']}。", "",
                  "已知业务后果与冻结策略资格分别保留；运行未终态时冻结资格为未知，不将其当成业务失败。", "",
                  "| 情境 | 状态 | 分数 | 完整责任 | 冻结策略证据 |", "|---|---|---:|---|---|"]
        for row in summary["rows"]:
            valid = row["frozen_policy_evidence_valid"]
            label = "未知" if valid is None else "通过" if valid else "未通过"
            lines.append(f"| {row['case_id']} | {row['status']} | {row['reward']} | {row['completed']} | {label} |")
    else:
        lines += ["尚无可读E报告；未执行不作为0分。"]
    lines += ["", "N与E不互相回填。E不提供参数学习变化；144例P2、Contribution及外部模型评价没有由本监督启动。", ""]
    output.mkdir(parents=True, exist_ok=True)
    atomic_write(output / "summary.json", json_bytes(result))
    atomic_write(output / "summary.md", "\n".join(lines).encode())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Separate reporting directory; defaults to --run")
    args = parser.parse_args()
    summarize(args.run, output=args.output)


if __name__ == "__main__":
    main()
