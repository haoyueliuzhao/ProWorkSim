"""Compare the two OSA presentations on the same twelve tasks using locked endpoint receipts."""

from collections import Counter
from contextlib import closing
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_osa_retest_v245_4 import AUTH, NS, PLAN, ROOT, RUN, old, read_json
from report_ordinary_successor_v243_2 import counts


def comparison():
    spec = read_json(PLAN / "protocol.json")
    prior = {r["instance"]: r for r in read_json(old.checked(spec["old_results"]))["rows"]}
    cases = read_json(old.checked(spec["roster"]))["roster"]
    rows = []
    with closing(
        sqlite3.connect(Path(read_json(AUTH)["ledger"]).as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.execute("BEGIN")
        for case in cases:
            i = case["index"]
            root = RUN / str(i)
            previous = prior[case["instance"]]
            end = root / "completed.json"
            outcome = read_json(end) if end.exists() else {}
            row = dict(
                index=i,
                instance=case["instance"],
                old_code=previous["code"],
                old_delivery=previous["delivery"],
                old_changed=previous["policy"]["changed"],
                old_paid=previous["paid"],
                status=outcome.get("status", "pending"),
                error=outcome.get("error"),
                usage=counts(db, f"{NS}:{i}:OSA"),
                code=None,
                delivery=None,
                changed=None,
            )
            for kind in ("code", "delivery"):
                file = root / ("OSA-" + kind) / "receipt.json"
                if file.is_file():
                    score = read_json(file)
                    assert score["kind"] == kind and score["instance_id"] == case["instance"]
                    row[kind] = score["resolved"]
                    row[kind + "_status"] = score["status"]
            decision = root / "OSA/decision.json"
            if decision.exists():
                d = read_json(decision)
                row.update(
                    changed=d["active"]["changed"],
                    option=d["active"]["decision"]["option"],
                    validator=d["info"]["validator"],
                    requested=d["info"].get("requested"),
                )
            if outcome.get("status") == "closed":
                start = read_json(root / "OSA/fresh-start.json")
                result = read_json(root / "OSA/result.json")
                assert start["base_commit"] == case["base_commit"] and not start["history_restored"]
                assert (
                    start["prior_patch_count"]
                    == start["initial_model_tokens"]
                    == start["initial_opportunities"]
                    == 0
                )
                assert row["usage"]["paid"]["tokens"] == result["logical_tokens"] <= old.LIMIT
                row["cleanup_errors"] = result.get("cleanup_errors", [])
            rows.append(row)
    return rows


def main():
    rows = comparison()
    plan = len(rows)
    pause_file = RUN / "pause.json"
    pause = read_json(pause_file) if pause_file.exists() else {"paused": []}
    for row in rows:
        if row["index"] in pause["paused"]:
            if row["status"] != "pending" or row["usage"]["states"]:
                raise ValueError("Paused task has an attempt")
            row["status"] = "paused_unstarted"
    planned_rows = rows
    rows = [r for r in rows if r["status"] != "paused_unstarted"]
    usage = Counter()
    prior = Counter()
    for row in rows:
        usage.update(row["usage"]["paid"])
        prior.update(row["old_paid"])
    closed = sum(r["status"] == "closed" for r in rows)
    pending = sum(r["status"] == "pending" for r in rows)
    print(
        f"planned={plan} closed={closed} pending={pending} tokens={usage['tokens']} paid_CNY={usage['nanoyuan'] / 1e9:.2f}",
        flush=True,
    )
    if pending and not (RUN / "cash-boundary.json").exists():
        return
    old.save(
        PLAN / "results.json",
        dict(
            rows=planned_rows,
            planned=plan,
            paused_unstarted=pause["paused"],
            generated=closed,
            usage=dict(usage),
        ),
    )
    labels = {True: "通过", False: "未通过", None: "未定"}
    lines = [
        "# 新版 OSA 提示词的同题重测",
        "",
        "## 实验条件",
        "",
        "沿用上一轮 6 个仓库的 12 题，每题都从原始仓库和两个空白成员会话开始。使用 DeepSeek Flash 非思考模式，团队共享 500 万 token。两轮 OSA 均从第 12 次行动机会开始判断是否调整分工。这次启用新版组织决策提示词、可执行方案展示和逐工作包复核状态。每题每版各跑一次。",
        "",
        f"计划 {plan} 题，按用户要求暂停未启动题 {len(pause['paused'])} 道，正常完成生成 {closed} 题。下表两轮均取本批执行范围内的相同 {len(rows)} 题。旧账本累计上限 230 元，本批新增实际费用 {usage['nanoyuan'] / 1e9:.2f} 元。",
        "",
        "| 指标 | 上轮 | 本轮 |",
        "| --- | ---: | ---: |",
    ]
    for kind, label in (("code", "最终代码通过"), ("delivery", "正确交付")):
        yes = sum(r[kind] is True for r in rows)
        unknown = sum(r[kind] is None for r in rows)
        improved = sum(r["old_" + kind] is False and r[kind] is True for r in rows)
        lost = sum(r["old_" + kind] is True and r[kind] is False for r in rows)
        original = sum(r["old_" + kind] is True for r in rows)
        lines.append(
            f"| {label} | {original}/{len(rows)} | 已通过 {yes}，未定 {unknown}；逐题新增 {improved}、失去 {lost} |"
        )
    for key, label in (
        ("input", "实际输入 token"),
        ("output", "实际输出 token"),
        ("tokens", "输入＋输出 token"),
    ):
        lines.append(f"| {label} | {prior[key]:,} | {usage[key]:,} |")
    lines.extend(
        [
            f"| 实际调整分工的题数 | {sum(r['old_changed'] for r in rows)} | {sum(r['changed'] is True for r in rows)} |",
            "",
            "| 任务 | 上轮代码 → 本轮 | 上轮交付 → 本轮 | 本轮 OSA | 本轮 token |",
            "| --- | --- | --- | --- | ---: |",
        ]
    )
    for r in rows:
        decision = r.get("option", "未取得决策")
        if r.get("validator") == "rejected":
            decision += "（校验回退）"
        lines.append(
            f"| {r['instance']} | {labels[r['old_code']]} → {labels[r['code']]} | {labels[r['old_delivery']]} → {labels[r['delivery']]} | {decision} | {r['usage']['paid'].get('tokens', 0):,} |"
        )
    lines += [
        "",
        "逐题变化同时受独立生成波动影响。这 12 题依据历史失败记录选取，结果仅描述本批；单次重测无法单独估计提示词对成功率的因果影响。",
    ]
    (ROOT / "docs/experiments/v245-4-osa-retest-results.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
