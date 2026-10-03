"""Read-only software-development status, original trajectory index and counts.

Never reruns worlds, models, tests or grading. Missing, interrupted and unknown
episodes remain separate from observed business failures. The index is retained
even when no model card was admitted.
"""

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from proworksim.storage import atomic_write, digest, json_bytes, read_json

VERSION = "software-development-report-v0.28"
BEIJING = ZoneInfo("Asia/Shanghai")


def _read(path, default=None):
    return read_json(path) if path.exists() else default


def _reference(path):
    return {"path": str(path.resolve()), "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}


def _events(folder):
    path = folder / "slot-0/experience.jsonl"
    events, truncated = [], None
    if path.exists():
        for number, line in enumerate(path.read_text().splitlines(), 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                truncated = {"line": number, "reason": "incomplete original JSONL tail retained on disk"}
                break
            if event.get("sequence") != len(events):
                raise ValueError("Original event stream is not consecutive")
            events.append(event)
    return events, truncated


def _attempt(slot, worker, folder, row, source, revision, context_policy, attempt_index):
    """Read one original attempt; never merge or overwrite its outcome."""
    events, truncated = _events(folder)
    counts, actions, stops = Counter(), Counter(), Counter()
    calls = []
    for event in events:
        payload = event["payload"]
        if event["kind"] == "model_call" and payload.get("stage") == "started":
            counts["model_requests"] += 1
        elif event["kind"] == "model_response":
            counts["model_responses"] += 1
            usage = payload.get("response", {}).get("usage", {})
            counts["prompt_tokens"] += usage.get("prompt_tokens", 0)
            counts["completion_tokens"] += usage.get("completion_tokens", 0)
        elif event["kind"] == "tool_call":
            counts["world_tool_calls"] += 1
            response = payload.get("response", {})
            action = payload["action"]
            actions[action + (":ok" if response.get("ok") else ":rejected")] += 1
            if response.get("ok") is False:
                counts["world_tool_refusals"] += 1
            if action in {"send_message", "claim_task", "delegate_task", "return_task",
                          "integrate_patch", "run_tests", "submit_integration"}:
                calls.append({"sequence": event["sequence"], "member": event.get("worker_id"),
                              "action": action, "ok": response.get("ok"),
                              "arguments": payload.get("arguments"),
                              "result": response.get("result"), "error": response.get("error")})
        elif event["kind"] == "role_reactivated":
            counts["reactivations"] += 1
        elif event["kind"] == "run_boundary":
            stops.update(payload.get("role_stops", {}).values())
    raw_requests = sorted((folder / "raw-transport").glob("*.started.json"))
    raw_returns = sorted((folder / "raw-transport").glob("*.finished.json"))
    counts["durable_request_ledgers"] = len(raw_requests)
    counts["durable_return_ledgers"] = len(raw_returns)
    entry = _read(folder / "slot-0/entry.json")
    assessment = _read(folder / "slot-0/assessment.json")
    status = row.get("status") if row else "not_started"
    known = bool(status == "closed" and entry and entry["reward"].get("eligible") is True
                 and row.get("evaluation_guard", {}).get("learning_unchanged") is True)
    current = {**slot, "worker": worker, "status": status, "known": known,
               "complete": bool(entry["reward"]["completed"]) if known else None,
               "reward": entry["reward"]["reward"] if known else None,
               "raw_assessment": assessment, "calls": dict(counts), "actions": dict(actions),
               "role_stops": dict(stops), "selected_actual_calls": calls,
               "stream_tail_problem": truncated, "trajectory_directory": str(folder),
               "mapping": entry.get("mapping") if entry else None,
               "row": row}
    current.update(attempt_index=attempt_index, source=source, interface_revision=revision, context_policy=context_policy,
                   started=row is not None and row.get("status") != "not_started")
    current["evidence"] = {name: _reference(path) for name, path in (
        ("entry", folder / "slot-0/entry.json"), ("assessment", folder / "slot-0/assessment.json"),
        ("raw_independent_assessment", folder / "slot-0/raw-independent-assessment.json"),
        ("evaluation_guard", folder / "evaluation-guard.json")) if path.exists()}
    return current


def _attempt_summary(attempt):
    return {key: value for key, value in attempt.items()
            if key not in {"selected_actual_calls", "actions", "mapping"}}


def report(root):
    root = Path(root).resolve()
    plan = read_json(root / "plan.json")
    supervisor = _read(root / "supervisor.json", {})
    recovery = plan.get("recovery")
    if recovery:
        from scripts.software_development_v028 import validate_recovery
        validate_recovery(plan)
    revision = plan.get("interface_revision", "software-collaboration-v0.28")
    context_policy = plan.get("context_policy", "latest_observation_last4_tool_rounds")
    episodes, trajectory_files = [], []
    total_counts = Counter()
    for worker, slots in plan["assignments"].items():
        worker_report = _read(root / worker / "actual/report.json", {})
        progress = _read(root / worker / "actual/progress.json", worker_report.get("rows", []))
        byslot = {row["slot_id"]: row for row in progress}
        for slot in slots:
            sid = slot["slot_id"]
            attempts = []
            if recovery:
                previous = recovery["prior_slots"][sid]
                attempts.append(_attempt(slot, worker, Path(previous["trajectory_directory"]), previous["row"],
                                         recovery["prior_source"], recovery["prior_interface_revision"],
                                         recovery["prior_context_policy"], 0))
            retained = recovery is not None and sid in recovery["retained_closed_slot_ids"]
            if not retained:
                attempts.append(_attempt(slot, worker, root / worker / "actual" / sid, byslot.get(sid),
                                         plan["source"], revision, context_policy, 1 if recovery else 0))
            # An unstarted recovery does not erase a real earlier unknown attempt.
            selected = next((attempt for attempt in reversed(attempts) if attempt["started"]), attempts[-1])
            current = {**selected, "attempts": [_attempt_summary(attempt) for attempt in attempts],
                       "retained_closed": retained,
                       "recovery_status": attempts[-1]["status"] if recovery and not retained else None}
            episodes.append(current)
            for attempt in attempts:
                total_counts.update(attempt["calls"])
                folder = Path(attempt["trajectory_directory"])
                if folder.exists():
                    for path in sorted(folder.rglob("*")):
                        if path.is_file():
                            trajectory_files.append({"slot_id": sid, "attempt_index": attempt["attempt_index"],
                                                     "source": attempt["source"], **_reference(path)})
        roots = [(root, 1 if recovery else 0, plan["source"])]
        if recovery:
            roots.insert(0, (Path(recovery["prior_run_root"]), 0, recovery["prior_source"]))
        for run_root, attempt_index, source in roots:
            for path in sorted((run_root / worker / "actual/resident/calls").glob("*.json")):
                trajectory_files.append({"slot_id": None, "worker": worker, "attempt_index": attempt_index,
                                         "source": source, "kind": "resident_original_generation_ledger", **_reference(path)})
    known = [episode for episode in episodes if episode["known"]]
    complete = sum(episode["complete"] for episode in known)
    started = sum(any(attempt["started"] for attempt in episode["attempts"]) for episode in episodes)
    by_first = {}
    for first in ("member_a", "member_b"):
        selected = [episode for episode in episodes if episode["first_member"] == first]
        observed = [episode for episode in selected if episode["known"]]
        by_first[first] = {"scheduled": len(selected), "known": len(observed),
                           "complete": sum(episode["complete"] for episode in observed),
                           "complete_rate_all": sum(episode["complete"] for episode in observed) / len(selected)
                           if len(observed) == len(selected) else None}
    index = {"version": VERSION, "run_root": str(root), "files": trajectory_files,
             "scope": "All original attempts, including prior unknowns; no imputation, deletion or replay."}
    index_path = root / "trajectory-index.json"
    atomic_write(index_path, json_bytes(index))
    prior_supervisor = read_json(Path(recovery["prior_supervisor"]["path"])) if recovery else {}
    current_gpu = supervisor.get("terminated_gpu_seconds", 0) + supervisor.get("running_gpu_seconds", 0)
    prior_gpu = prior_supervisor.get("terminated_gpu_seconds", 0) + prior_supervisor.get("running_gpu_seconds", 0)
    reservation = _read(root / "reservation-handoff.json", {})
    return {"version": VERSION, "generated_at_beijing": datetime.now(BEIJING).isoformat(),
            "run_status": supervisor.get("status", "unknown"),
            "terminal": supervisor.get("status") in {"complete", "closed_with_missing_or_interrupted", "supervisor_interrupted"},
            "plan": _reference(root / "plan.json"), "source": plan["source"], "interface_revision": revision,
            "context_policy": context_policy,
            "recovery": recovery, "same_protocol_statistics_allowed": recovery is None,
            "statistics_scope": (recovery["statistics_scope"] if recovery else "One declared interface revision; development outcomes only"),
            "report_prefix": "software-development-v028-recovery" if recovery else "software-development-v028",
            "gpu_preference": plan["gpu_preference"], "queue_deadline_at": plan["queue_deadline_at"],
            "queue_deadline_beijing": datetime.fromtimestamp(plan["queue_deadline_at"], BEIJING).isoformat(),
            "total_gpu_seconds": plan["total_gpu_seconds"], "worker_gpu_seconds": plan["worker_gpu_seconds"],
            "wall_deadline_at": plan["wall_deadline_at"],
            "max_parallel_model_instances": plan["limits"]["max_parallel_model_instances"],
            "overall": {"scheduled": len(episodes), "started": started, "known": len(known),
                        "unknown_started": started - len(known), "not_started": len(episodes) - started,
                        "complete": complete, "complete_rate_all": complete / len(episodes) if len(known) == len(episodes) else None},
            "by_first_member": by_first, "call_counts": dict(total_counts), "episodes": episodes,
            "gpu_seconds": current_gpu + prior_gpu, "current_run_gpu_seconds": current_gpu, "prior_run_gpu_seconds": prior_gpu,
            "reservation_handoff": reservation, "reservation_held_seconds": reservation.get("reservation_held_seconds", 0),
            "gpu_seconds_are_final": not supervisor.get("running_gpu_seconds", 0) and bool(supervisor.get("ended_at")),
            "supervisor": supervisor, "trajectory_index": _reference(index_path),
            "trajectory_files": len(trajectory_files), "model_api_calls": 0, "optimizer_updates": 0,
            "scope": "Eight-slot status ledger with original attempts; not B/G/I, learning benefit or a pooled interface-effect estimate.",
            "manual_per_episode_review": "pending until actual trajectories are available for contextual reading"}


def markdown(data):
    overall = data["overall"]
    gpu_range = "/".join(str(gpu) for gpu in data["gpu_preference"])
    queue_deadline = datetime.fromtimestamp(data["queue_deadline_at"], BEIJING).strftime("%Y-%m-%d %H:%M")
    total_budget = "不设" if data["total_gpu_seconds"] is None else f"{data['total_gpu_seconds']/3600:g} GPU小时"
    worker_budgets = "不设" if all(value is None for value in data["worker_gpu_seconds"].values()) else "、".join(
        f"{worker}=" + ("不设" if seconds is None else f"{seconds/3600:g}小时")
        for worker, seconds in data["worker_gpu_seconds"].items())
    wall_deadline = "不设" if data["wall_deadline_at"] is None else (
        "北京时间" + datetime.fromtimestamp(data["wall_deadline_at"], BEIJING).strftime("%Y-%m-%d %H:%M"))
    lines = ["# v0.28 真实软件开发运行记录", "", f"更新时间：{data['generated_at_beijing']}（北京时间）。",
             "", f"本轮接口修订：`{data['interface_revision']}`；上下文策略：`{data['context_policy']}`；"
             f"源码：`{data['source'].get('code_commit', 'unknown')}`。",
             "", ("本报告为显式授权恢复的八槽状态总账：保留全部已闭合结果（含失败），原未知尝试单独保留。"
                   "新旧接口结果可以汇总完成状态，但不能混同为相同协议的效果统计。"
                   if data.get("recovery") else "本报告记录本轮接口下的原始尝试。"),
             "", f"监督状态：`{data['run_status']}`。计划8条，已启动{overall['started']}条，可评{overall['known']}条；"
             f"启动后未知{overall['unknown_started']}条、未启动{overall['not_started']}条。",
             "", f"已知完整职责{overall['complete']}/{overall['known']}；完整原分母比率："
             + (str(overall["complete_rate_all"]) if overall["complete_rate_all"] is not None else "未知，不能把未启动/中断补零") + "。",
             "", "这是2个开发情境×2种先手×2个固定seed的冻结参数运行，零更新。旧Marshmallow仅作接口开发，"
             "不是正式训练支持、独立算法确认或B/G/I效果实验。", "",
             "| 槽 | 先手 | 状态 | 已知完整职责 | 结果来源 | 原始轨迹 |", "| --- | --- | --- | --- | --- | --- |"]
    for row in data["episodes"]:
        result = "未知" if row["complete"] is None else str(int(row["complete"]))
        origin = f"attempt{row['attempt_index']} / {row['interface_revision']} / {row['context_policy']}"
        lines.append(f"| {row['slot_id']} | {row['first_member']} | {row['status']} | {result} | {origin} | `{row['trajectory_directory']}` |")
    if data.get("recovery"):
        lines += ["", "尝试历史（not_started仅表示该轮计划，未发生模型尝试）：", "",
                  "| 槽 | 尝试轮 | 原状态 | 来源提交 | 原始轨迹 |", "| --- | --- | --- | --- | --- |"]
        for row in data["episodes"]:
            for attempt in row["attempts"]:
                lines.append(f"| {row['slot_id']} | attempt{attempt['attempt_index']} | {attempt['status']} | "
                             f"`{attempt['source'].get('code_commit', 'unknown')}` | `{attempt['trajectory_directory']}` |")
    lines += ["", f"GPU累计占用 {data['gpu_seconds']/3600:.6f} 小时"
              + ("（终态）。" if data["gpu_seconds_are_final"] else "（最近监督快照，含进行中占用；不是最终费用）。"),
              "", f"累计GPU时长上限：{total_budget}；每worker GPU时长上限：{worker_budgets}；全局墙钟截止：{wall_deadline}。"
              f"最多{data['max_parallel_model_instances']}个模型实例；每成员48次决策，context16384/output2048。"
              f"在GPU{gpu_range}等待空卡，等卡截止北京时间{queue_deadline}；未沿用旧v0.26预算或期限。", "",
              f"已登记原始轨迹文件 {data['trajectory_files']} 份。索引：`{data['trajectory_index']['path']}`。",
              "", f"另计GPU预留占用 {data['reservation_held_seconds']/3600:.6f} 小时；与上述模型worker占用分列，预留期间模型调用为0。",
              "", "归档包含生成前请求、原始响应和token、SDK事件流、实际工具返回、世界版本/结束快照、"
              "独立验收、Mapper证据与冻结状态guard。中断时已产生的记录保留；没有返回的生成不补文本或token。",
              "", "同名JSON保存逐槽实际调用及原始结果。逐条协商/责任/代码关系的人工审阅尚待实际轨迹产生后完成；"
              "自动消息数、领取数或测试数不代表协作质量、因果贡献或学习效果。", "",
              "[新协议](../software-allocation-v028-plan.md) · [实际SWE-smith来源资格](software-sources-v028.md) · "
              f"[机器记录]({data['report_prefix']}.json)"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-prefix")
    args = parser.parse_args()
    data = report(args.run_root)
    prefix = args.output_prefix or data["report_prefix"]
    if Path(prefix).name != prefix or prefix in {"", ".", ".."}:
        parser.error("output-prefix must be one filename prefix")
    data["report_prefix"] = prefix
    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(args.output_dir / (prefix + ".json"), json_bytes(data))
    atomic_write(args.output_dir / (prefix + ".md"), markdown(data).encode())
    print(json.dumps({"status": data["run_status"], "overall": data["overall"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
