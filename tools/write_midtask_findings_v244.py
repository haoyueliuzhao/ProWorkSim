"""Write the compact paired-outcome report from reconciled official and billing receipts."""

from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_midtask_panel_v244 import PLAN, ROOT, ARMS, read_json
from report_midtask_panel_v244 import main as reconcile


def value(arm, key):
    return arm["scores"].get(key, {}).get("resolved")


def label(v):
    return {True: "通过", False: "未通过", None: "待定"}[v]


def percent(lo, hi, n):
    return f"{lo}/{n}（{100 * lo / n:.1f}%）" if lo == hi else f"{lo}–{hi}/{n}"


def disposition(arm):
    if "changed" not in arm:
        return "待定"
    if arm.get("validator") == "rejected":
        return "提案未通过校验，沿用原分工"
    if arm["changed"]:
        return "已调整"
    if arm.get("requested") == "ABSTAIN":
        return "暂缓"
    return "维持"


def render(r):
    rows = r["rows"]
    n = len(rows)
    code = r["endpoints"]["code"]
    sides = code["pass_count_bounds"]
    lo, hi = code["paired_difference_count_bounds"]
    money = sum(a.get("nanoyuan", 0) for a in r["total"].values()) / 1e9
    diff = (
        f"{100 * lo / n:+.1f} 个百分点"
        if lo == hi
        else f"{100 * lo / n:+.1f} 至 {100 * hi / n:+.1f} 个百分点"
    )
    lines = [
        "# 中途允许调整分工的 15 题对照结果",
        "",
        f"按事先固定的全部 {n} 题，最终代码通过官方评分：KEEP {percent(*sides['KEEP'], n)}，OSA {percent(*sides['OSA'], n)}。OSA 减 KEEP 的通过率差为 {diff}。独立 API 账本上限 190 元，已结算 {money:.2f} 元。",
        "",
        "KEEP 让两名成员继续按原分工工作。OSA 在同一保存点多一次组织决策，可以改变分工、维持或暂缓。两组都用 DeepSeek Flash 非思考、T1 上下文和项目受管接口；每支的 500 万 token 包括共同历史。OSA 的决策调用计入本支。任务来自历史开发题，覆盖 7 个仓库。",
        "",
        "| 终点 | 两组均通过 | 仅 KEEP | 仅 OSA | 两组均未通过 | 至少一侧待定 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, title in (("code", "最终代码正确"), ("delivery", "正确合法交付")):
        b = r["endpoints"][key]["cells"]
        lines.append(
            "| "
            + title
            + " | "
            + " | ".join(
                str(b.get(k, 0)) for k in ("both", "KEEP_only", "OSA_only", "neither", "unknown")
            )
            + " |"
        )
    if code["exact_mcnemar_two_sided_if_complete"] is not None:
        lines.extend(
            [
                "",
                f"代码端点使用同题配对的精确 McNemar 双侧检验，p = {code['exact_mcnemar_two_sided_if_complete']:.3g}。每题占 6.67 个百分点，同一保存点的两次生成各只运行一次。",
            ]
        )
    lines.extend(
        [
            "",
            "## 成本及组织决策",
            "",
            "| 组 | 已有付费调用的题数 | 实际输入 | 实际输出 | 每个付费续跑平均新增 token | 策略调用 token（已计入） | 已结算费用 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for a in ARMS:
        t = r["total"][a]
        k = sum(bool(row[a]["paid"].get("calls")) for row in rows)
        osa = sum(row[a].get("osa_tokens", 0) for row in rows)
        avg = f"{t.get('tokens', 0) / k:,.0f}" if k else "—"
        lines.append(
            f"| {a} | {k} | {t.get('input', 0):,} | {t.get('output', 0):,} | {avg} | {osa:,} | ¥{t.get('nanoyuan', 0) / 1e9:.2f} |"
        )
    ds = Counter(disposition(row["OSA"]) for row in rows)
    lines += [
        "",
        "OSA 决策记录："
        + "，".join(f"{key} {count} 题" for key, count in ds.items())
        + "。OSA 选择维持时也可能给原负责人提供下一步提示，分支差异还可能来自生成波动。",
        "",
        "## 逐题结果",
        "",
        "| 题目 | KEEP 代码／交付 | OSA 代码／交付 | OSA 决定 | KEEP／OSA 新增万 token |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for row in rows:
        pairs = ["／".join(label(value(row[a], k)) for k in ("code", "delivery")) for a in ARMS]
        costs = "／".join(
            f"{row[a]['paid'].get('tokens', 0) / 10000:.1f}" if row[a]["paid"].get("calls") else "—"
            for a in ARMS
        )
        lines.append(
            f"| {row['instance'].split('__')[-1]} | {pairs[0]} | {pairs[1]} | {disposition(row['OSA'])} | {costs} |"
        )
    discordant = [row for row in rows if {value(row[a], "code") for a in ARMS} == {False, True}]
    if discordant:
        lines += ["", "## 哪些题拉开了通过率", ""]
        for row in discordant:
            good = next(a for a in ARMS if value(row[a], "code"))
            bad = next(a for a in ARMS if a != good)
            failed = row[bad]["scores"]["code"].get("new_failures", [])
            action = row["OSA"].get("first_action") or {}
            what = (
                "；策略指定 "
                + "/".join(str(action.get(k, "")) for k in ("actor", "package", "action"))
                if action
                else ""
            )
            detail = (
                "。未过分支的官方目标失败用例包括 " + ", ".join(f"`{v}`" for v in failed[:3])
                if failed
                else ""
            )
            lines.append(
                f"- **{row['instance'].split('__')[-1]}** 仅 {good} 通过。OSA {disposition(row['OSA'])}{what}{detail}。"
            )
    lines += [
        "",
        "[方案与样本选择](v244-15-paired-midtask.md) · [配对结果、官方评分与计费汇总](../../artifacts/software-benchmark-v244/midtask15-r1/results.json)",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    reconcile()
    doc = ROOT / "docs/experiments/v244-15-paired-results.md"
    doc.write_text(render(read_json(PLAN / "results.json")))
