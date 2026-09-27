"""Read-only terminal N/E accounting; no scoring rerun or model calls."""

import argparse
from pathlib import Path

from proworksim.storage import atomic_write, digest, json_bytes, read_json


def read(path):
    return read_json(path) if path.exists() else None


def reference(path):
    return {"path": str(path.resolve()), "sha256": digest(path.read_bytes())}


def summarize(root):
    root = Path(root).resolve()
    state = read_json(root / "state.json")
    jobs = state["jobs"]
    result = {"version": "N-E-terminal-accounting-v0.21", "supervisor_status": state["status"],
              "source": state["source"], "jobs": jobs, "N": None, "E": None,
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
        rows = []
        for row in e.get("rows", read(root / "E/progress.json") or []):
            assessment = row.get("assessment", {})
            rows.append({"case_id": row["case_id"], "status": row["status"],
                         "eligible": assessment.get("eligible"), "reward": assessment.get("reward"),
                         "completed": assessment.get("completed"), "components": assessment.get("components"),
                         "record_trust": assessment.get("record_trust"),
                         "independent_assessability": assessment.get("independent_assessability"),
                         "mapper": assessment.get("mapper"), "error": row.get("error")})
        result["E"] = {"status": e["status"], "report": reference(root / "E/report.json"),
                       "planned": e.get("planned_episodes"), "started": len(rows),
                       "known": sum(x["eligible"] is True and x["reward"] is not None for x in rows),
                       "complete_responsibilities": sum(x["completed"] is True for x in rows),
                       "rows": rows, "source_unchanged": e.get("source_unchanged"),
                       "actor_steps": e.get("actor_steps"), "critic_steps": e.get("critic_steps"),
                       "scope": "Six development situations with zero planned updates, not population success or learning gain."}
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
                  "| 情境 | 状态 | 分数 | 完整责任 |", "|---|---|---:|---|"]
        for row in summary["rows"]:
            lines.append(f"| {row['case_id']} | {row['status']} | {row['reward']} | {row['completed']} |")
    else:
        lines += ["尚无可读E报告；未执行不作为0分。"]
    lines += ["", "N与E不互相回填。E不提供参数学习变化；144例P2、Contribution及外部模型评价没有由本监督启动。", ""]
    atomic_write(root / "summary.json", json_bytes(result))
    atomic_write(root / "summary.md", "\n".join(lines).encode())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    summarize(args.run)


if __name__ == "__main__":
    main()
