"""Account for recorded worker/reservation intervals per GPU, without GPU access."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


UTC = timezone.utc
BJT = timezone(timedelta(hours=8))
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def timestamp_us(value: str) -> int:
    """Require an explicit timezone; retain input precision without float timestamps."""
    if not isinstance(value, str):
        raise ValueError(f"invalid timestamp: {value!r}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    delta = parsed.astimezone(UTC) - EPOCH
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def iso_bjt(value: int) -> str:
    return (EPOCH + timedelta(microseconds=value)).astimezone(BJT).isoformat()


@dataclass(frozen=True)
class GpuInterval:
    gpu: int
    start_us: int
    end_us: int

    def __post_init__(self) -> None:
        if type(self.gpu) is not int or self.gpu < 0:
            raise ValueError("GPU must be a nonnegative integer index")
        if type(self.start_us) is not int or type(self.end_us) is not int:
            raise ValueError("interval boundaries must be integer microseconds")
        if self.end_us < self.start_us:
            raise ValueError("negative interval duration")


def merge_intervals(intervals: list[GpuInterval]) -> dict[int, list[tuple[int, int]]]:
    """Merge duplicates, overlaps and adjacent intervals, independently per GPU."""
    grouped: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for interval in intervals:
        grouped[interval.gpu].append((interval.start_us, interval.end_us))
    merged: dict[int, list[tuple[int, int]]] = {}
    for gpu, spans in sorted(grouped.items()):
        result: list[tuple[int, int]] = []
        for start, end in sorted(spans):
            if start == end:
                continue
            if result and start <= result[-1][1]:
                result[-1] = (result[-1][0], max(result[-1][1], end))
            else:
                result.append((start, end))
        merged[gpu] = result
    return merged


def intersect_intervals(
    left: list[tuple[int, int]], right: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Intersect two already merged sorted sets of intervals on the same GPU."""
    result: list[tuple[int, int]] = []
    i = j = 0
    while i < len(left) and j < len(right):
        start, end = max(left[i][0], right[j][0]), min(left[i][1], right[j][1])
        if start < end:
            result.append((start, end))
        if left[i][1] <= right[j][1]:
            i += 1
        else:
            j += 1
    return result


def serialize_spans(spans: list[tuple[int, int]]) -> dict[str, Any]:
    duration_us = sum(end - start for start, end in spans)
    return {
        "gpu_seconds": duration_us / 1_000_000,
        "gpu_hours": duration_us / 3_600_000_000,
        "intervals": [
            {"start_at_bjt": iso_bjt(start), "end_at_bjt": iso_bjt(end),
             "seconds": (end - start) / 1_000_000}
            for start, end in spans
        ],
    }


def interval_accounting(
    workers: list[GpuInterval], reservations: list[GpuInterval],
) -> dict[str, Any]:
    worker_union = merge_intervals(workers)
    reservation_union = merge_intervals(reservations)
    combined_union = merge_intervals(workers + reservations)
    per_gpu = []
    total_us: dict[str, int] = defaultdict(int)
    for gpu in sorted(combined_union):
        worker = worker_union.get(gpu, [])
        reservation = reservation_union.get(gpu, [])
        overlap = intersect_intervals(worker, reservation)
        spans = {
            "worker_union": worker, "reservation_union": reservation,
            "worker_reservation_overlap": overlap, "combined_union": combined_union[gpu],
        }
        durations = {key: sum(end - start for start, end in value)
                     for key, value in spans.items()}
        durations["reservation_only"] = (
            durations["reservation_union"] - durations["worker_reservation_overlap"]
        )
        assert durations["combined_union"] == (
            durations["worker_union"] + durations["reservation_only"]
        )
        row = {"gpu": gpu, **{key: serialize_spans(value) for key, value in spans.items()}}
        row["reservation_only"] = {
            "gpu_seconds": durations["reservation_only"] / 1_000_000,
            "gpu_hours": durations["reservation_only"] / 3_600_000_000,
        }
        per_gpu.append(row)
        for key, value in durations.items():
            total_us[key] += value
    return {
        "per_gpu": per_gpu,
        "totals": {
            key: {"gpu_seconds": total_us[key] / 1_000_000,
                  "gpu_hours": total_us[key] / 3_600_000_000}
            for key in ("worker_union", "reservation_union", "worker_reservation_overlap",
                        "combined_union", "reservation_only")
        },
    }


def build_report(costs: dict[str, Any]) -> dict[str, Any]:
    workers, reservations, included, excluded = [], [], [], []
    for index, attempt in enumerate(costs["attempts"]):
        interval = GpuInterval(attempt["gpu"], timestamp_us(attempt["worker_assigned_at_bjt"]),
                               timestamp_us(attempt["worker_ended_at_bjt"]))
        workers.append(interval)
        included.append({"kind": "worker", "source_pointer": f"/attempts/{index}",
                         "stage": attempt.get("stage"), "candidate_id": attempt.get("candidate_id"),
                         "gpu": interval.gpu, "start_at_bjt": iso_bjt(interval.start_us),
                         "end_at_bjt": iso_bjt(interval.end_us)})
    for group_index, group in enumerate(costs["reservations"]):
        for index, attempt in enumerate(group["attempts"]):
            ready, end = attempt.get("allocation_ready_at_bjt"), attempt.get("ended_at_bjt")
            # Validate supplied boundaries even if the other boundary is missing.
            start_us = timestamp_us(ready) if ready is not None else None
            end_us = timestamp_us(end) if end is not None else None
            metadata = {
                "kind": "reservation", "source_pointer": f"/reservations/{group_index}/attempts/{index}",
                "directory": group.get("directory"), "gpu": attempt["gpu"],
                "pid": attempt.get("pid"), "start_ticks": attempt.get("start_ticks"),
                "status": attempt.get("status"), "evidence": attempt.get("evidence"),
            }
            if type(attempt["gpu"]) is not int or attempt["gpu"] < 0:
                raise ValueError("GPU must be a nonnegative integer index")
            if start_us is None or end_us is None:
                excluded.append({**metadata, "allocation_ready_at_bjt": ready, "ended_at_bjt": end,
                                 "child_body_wall_seconds": attempt.get("child_body_wall_seconds"),
                                 "reason": "incomplete_allocation_ready_to_end_interval",
                                 "recorded_occupancy_gpu_seconds": None})
                continue
            interval = GpuInterval(attempt["gpu"], start_us, end_us)
            reservations.append(interval)
            included.append({**metadata, "start_at_bjt": iso_bjt(start_us),
                             "end_at_bjt": iso_bjt(end_us)})
    report = interval_accounting(workers, reservations)
    report.update({
        "version": "gpu-occupancy-union-v033",
        "generated_at_bjt": datetime.now(BJT).isoformat(),
        "scope": "Recorded single-GPU worker assigned-to-end and reservation ready-to-end intervals, v030 through v032; no new GPU or model work.",
        "method": "Use timezone-aware timestamps at microsecond resolution; merge duplicates, nested, overlapping and adjacent intervals per GPU; intersect merged worker and reservation sets; sum per-GPU unions, never merge across GPUs.",
        "worker_interval_count": len(workers),
        "reservation_interval_count": len(reservations),
        "excluded_reservation_count": len(excluded),
        "recorded_input_intervals": included,
        "excluded_reservations": excluded,
        "historical_worker_cost_separate": {
            "gpu_seconds": costs["totals"]["unique_worker_gpu_seconds"],
            "gpu_hours": costs["totals"]["unique_worker_gpu_hours"],
            "definition": costs["cost_definition"],
            "timestamp_union_minus_historical_seconds": (
                report["totals"]["worker_union"]["gpu_seconds"]
                - costs["totals"]["unique_worker_gpu_seconds"]
            ),
        },
        "limitations": [
            "This measures recorded interval coverage, not utilization-weighted GPU computation, exact physical allocation time or proof of exclusive occupancy.",
            "Unknown pre-ready allocation time and reservations without both boundaries are not imputed as zero and are not added to the union.",
            "A failed reservation with recorded ready and end boundaries is included regardless of exit status.",
            "Watcher lifetimes, handoff metadata and repeated state/result references are not extra intervals; supplied source already deduplicated reservation children.",
            "Parallel time on different GPUs counts independently; combined GPU-hours are not global elapsed wall hours.",
            "The historical worker-only cost remains independent for model-worker cost comparison; this amendment does not alter outcome, sampling or optimizer counts.",
        ],
    })
    return report


def render_markdown(report: dict[str, Any]) -> str:
    totals = report["totals"]
    labels = [
        ("worker_union", "worker 区间并集"),
        ("reservation_union", "reservation 区间并集"),
        ("worker_reservation_overlap", "两类区间交集"),
        ("combined_union", "总体已记录占卡区间并集"),
        ("reservation_only", "仅预约、无 worker 覆盖"),
    ]
    lines = [
        "# v030–v032 GPU 区间并集记账修订", "",
        f"生成时间：{report['generated_at_bjt']}（北京时间）。", "",
        "本修订按每张 GPU 对已记录的 worker 与 reservation 时间区间重新求并集、交集；未调用模型、GPU 或重新评分。",
        f"输入为 `{report['input']['path']}`，SHA-256 为 `{report['input']['sha256']}`。", "",
        f"共读入 {report['worker_interval_count']} 个 worker 区间、{report['reservation_interval_count']} 个完整 reservation 区间；另有 {report['excluded_reservation_count']} 个预约 child 因缺少完整边界单列为未知。",
        "worker 边界采用 assigned→ended；预约边界采用 allocation_ready→ended。先在同一卡上合并相交、包含、相邻和重复区间，再计算交集与两类区间并集，最后跨卡相加。跨卡并行时间分别计入 GPU 小时，不作为全局墙钟时间。", "",
        "| 口径 | GPU 秒 | GPU 小时 |", "|---|---:|---:|",
    ]
    for key, label in labels:
        value = totals[key]
        lines.append(f"| {label} | {value['gpu_seconds']:.6f} | {value['gpu_hours']:.9f} |")
    lines += ["", "| GPU | worker 并集秒 | reservation 并集秒 | 交集秒 | 总体并集秒 | 仅预约秒 |",
              "|---|---:|---:|---:|---:|---:|"]
    for row in report["per_gpu"]:
        values = " | ".join(f"{row[key]['gpu_seconds']:.6f}" for key, _ in labels)
        lines.append(f"| {row['gpu']} | {values} |")
    overlap = totals["worker_reservation_overlap"]["gpu_seconds"]
    if overlap == 0:
        lines += ["", "实算各卡两类区间的交集均为 0 秒。因此本次已记录总体区间并集在数值上等于两个并集之和；这一结论来自逐区间计算，并非直接将旧报告的两个四舍五入小时数相加。"]
    else:
        lines += ["", f"实算两类区间交集为 {overlap:.6f} GPU 秒，总体并集已扣除该重复覆盖。"]
    historical = report["historical_worker_cost_separate"]
    lines += ["", f"历史 worker-only 成本仍独立保留：{historical['gpu_seconds']:.9f} 秒（{historical['gpu_hours']:.12f} GPU 小时）。区间时间戳复算与旧浮点时长的差为 {historical['timestamp_union_minus_historical_seconds']:.12f} 秒，属于记录精度差异；不改写旧 worker 成本，也不将预约成本混入模型筛选排名。",
              "", "## 未纳入并集的未知预约", ""]
    for item in report["excluded_reservations"]:
        lines += [f"- GPU{item['gpu']}，PID {item['pid']}，`{item['directory']}`，状态 `{item['status']}`：没有完整 allocation_ready→ended 边界，实际分配持续时间未知。记录 child body 墙钟时间为 {item['child_body_wall_seconds']} 秒；它不能替代 GPU 占用时间，也不能被解释为已证明占用 0 秒。"]
    lines += ["", "## 边界与解释", "",
              "这份统计只覆盖日志已记录的区间。worker 生命周期包含加载、诊断、筛选、退出及失败，并不意味着全程高利用率；reservation ready→end 也不是精确 GPU 计算时间，更不能证明最后心跳后始终独占。尚未 ready 的分配过程、缺边界的失败预约和记录外活动没有被猜测填补。",
              "", "已 ready 但失败的预约仍按完整已记录区间纳入。watcher 等待、handoff 元数据、同一 child 的重复 state/result 引用均不另加。原 36 槽结果、模型调用、参数更新和技术准入结果完全不由本项成本修订改变。",
              "", "## 可复算方法", "", "```bash",
              ".venv/bin/python scripts/gpu_occupancy_accounting.py \\",
              "  --input runs/v032-final-analysis/costs.json \\",
              "  --json-output docs/experiments/gpu-occupancy-v030-v032.json \\",
              "  --markdown-output docs/experiments/gpu-occupancy-v030-v032.md", "```", "",
              "机器记录保存所有输入区间及源 JSON pointer、各卡合并后区间、交集和汇总。必要 CPU controls 覆盖相交、包含、相邻、重复、多卡独立与负值/无效边界拒绝；执行回执见 `runs/v033-controls/occupancy/checks.json`。", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    source = args.input.read_bytes()
    report = build_report(json.loads(source))
    report["input"] = {"path": str(args.input), "sha256": hashlib.sha256(source).hexdigest()}
    for path in (args.json_output, args.markdown_output):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    args.markdown_output.write_text(render_markdown(report))
    print(json.dumps(report["totals"], ensure_ascii=False))


if __name__ == "__main__":
    main()
