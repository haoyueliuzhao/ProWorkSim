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


def assignment(arm):
    if not arm.get("changed"):
        return disposition(arm)
    op = arm.get("assignment", {})
    names = {
        "verify": "承担独立复核",
        "diagnosis": "承担诊断",
        "transfer_unstarted": "接手尚未开工的工作包",
        "release_diagnosis": "解除诊断职责",
        "D4": "执行交接",
        "D5": "按指定版本复核",
        "D6": "负责集成",
    }
    who = op.get("assignee") or op.get("actor") or ""
    return f"{who.removeprefix('member_')} {names.get(op.get('op') or op.get('dimension'), '执行新安排')} {op.get('task', '')}".strip()


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
    rerun = next(
        (row for row in rows if row["OSA"]["scores"].get("code", {}).get("environment_revision")),
        None,
    )
    if rerun:
        lines.extend(
            [
                "",
                f"Sphinx-8595 首轮评分为 KEEP 通过、OSA 未定。候选与官方测试均新增同名测试文件，导致官方测试补丁无法安装。采用既有 v217.3 评分侧修订，用相同镜像、分别锁定的原补丁和新的评分标识复测两组，结果为 KEEP {label(value(rerun['KEEP'], 'code'))}、OSA {label(value(rerun['OSA'], 'code'))}。表中采用这次同口径结果；补评新增模型调用为零。",
            ]
        )
    delivery = r["endpoints"]["delivery"]
    d = delivery["pass_count_bounds"]
    lines.extend(
        [
            "",
            f"正确合法交付率为 KEEP {percent(*d['KEEP'], n)}、OSA {percent(*d['OSA'], n)}。合法交付要求模型实际提交一个符合项目流程、且通过官方验收的版本。",
        ]
    )
    if (
        code["exact_mcnemar_two_sided_if_complete"] is not None
        and delivery["exact_mcnemar_two_sided_if_complete"] is not None
    ):
        lines.extend(
            [
                "",
                f"代码端点使用同题配对的精确 McNemar 双侧检验，p = {code['exact_mcnemar_two_sided_if_complete']:.3g}。正确合法交付端点 p = {delivery['exact_mcnemar_two_sided_if_complete']:.3g}。每题占 6.67 个百分点，同一保存点的两次生成各只运行一次。",
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
    lines.extend(
        [
            "",
            "表中用量取自供应商返回的输入和输出 token，金额是项目按缓存命中、未命中及输出的登记费率计入本批账本的人民币金额。",
        ]
    )
    if all(row[a].get("status") == "closed" for row in rows for a in ARMS):
        delta = sum(row["KEEP"]["paid"]["tokens"] - row["OSA"]["paid"]["tokens"] for row in rows)
        improved = [
            row
            for row in rows
            if value(row["OSA"], "delivery") and not value(row["KEEP"], "delivery")
        ]
        elsewhere = delta - sum(
            row["KEEP"]["paid"]["tokens"] - row["OSA"]["paid"]["tokens"] for row in improved
        )
        ended = sum("budget" in str(row["KEEP"].get("ending", "")) for row in improved)
        direction = "少用" if delta >= 0 else "多用"
        lines.extend(
            [
                "",
                f"计入组织决策后，OSA 全组新增 token 合计比 KEEP {direction} {abs(delta):,}（{abs(delta) / r['total']['KEEP']['tokens']:.1%}）。在只有 OSA 正确交付的 {len(improved)} 题上，KEEP 减 OSA 的用量差合计 {delta - elsewhere:+,} token，其中 {ended} 题的 KEEP 支到预算边界才结束；其余题合计差 {elsewhere:+,} token。该分解反映本批成本集中在哪里，仍受每题仅一次生成的影响。",
            ]
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
    lines.extend(
        [
            "",
            "## 实际改组与维持分工的题",
            "",
            "| OSA 实际行为 | 题数 | KEEP／OSA 代码通过 | KEEP／OSA 正确交付 | KEEP／OSA 平均新增万 token |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for flag, title in [(True, "改组生效"), (False, "组织图维持")]:
        sub = [row for row in rows if row["OSA"].get("changed") is flag]
        if not sub:
            continue
        vals = [
            "／".join(
                percent(
                    sum(value(row[a], ep) is True for row in sub),
                    sum(value(row[a], ep) is not False for row in sub),
                    len(sub),
                )
                for a in ARMS
            )
            for ep in ("code", "delivery")
        ]
        tks = "／".join(
            f"{sum(row[a]['paid'].get('tokens', 0) for row in sub) / len(sub) / 10000:.1f}"
            for a in ARMS
        )
        lines.append(f"| {title} | {len(sub)} | {vals[0]} | {vals[1]} | {tks} |")
    lines.append("")
    lines.append(
        "这些小组由 OSA 看到现场后自行选择，适合解释实际行为。全体 15 题的同题比较才是事前设定的主结果。"
    )
    comparable = [row for row in rows if all(row[a].get("final_tree") for a in ARMS)]
    same = sum(row["KEEP"]["final_tree"] == row["OSA"]["final_tree"] for row in comparable)
    inherited = [
        row["instance"].split("__")[-1]
        for row in rows
        if any(row[a].get("code_same_as_prefix") and value(row[a], "code") is True for a in ARMS)
    ]
    lines.extend(
        ["", f"核对已锁定的完整代码树：{len(comparable)} 对可比，{same} 对最终树完全一致。"]
    )
    if inherited:
        lines.append(
            "有 "
            + str(len(inherited))
            + " 题至少一支的最终文件及文件元数据与共同起点完全一致，且通过官方验收。因此这些题在分支前就已有可通过的代码："
            + "、".join(inherited)
            + "。"
        )
    lines.append("其余题若最终代码发生变化，仅凭最终评分还无法判断起点代码能否通过。")
    lines.extend(["", "## 代码通过后，能否完成交付", ""])
    for a in ARMS:
        gaps = [
            row
            for row in rows
            if value(row[a], "code") is True and value(row[a], "delivery") is False
        ]
        budget = sum("budget" in str(row[a].get("ending", "")) for row in gaps)
        unsubmitted = sum(not row[a].get("submit_receipts") for row in gaps)
        lines.append(
            f"- {a} 有 {len(gaps)} 题最终代码通过，未取得正确合法交付。其中 {budget} 题在预算边界结束，{unsubmitted} 题在本次续跑中未发起正式提交。这两个计数可以重叠。"
        )
    delivery_only = [
        row for row in rows if {value(row[a], "delivery") for a in ARMS} == {False, True}
    ]
    if delivery_only:
        lines.extend(
            [
                "",
                "下列同题交付结果不同。复核和提交次数仅计分支开始后的调用。",
                "",
                "| 任务 | 成功交付的一组 | OSA 生效安排 | KEEP／OSA 复核次数 | KEEP／OSA 提交尝试 |",
                "| --- | --- | --- | ---: | ---: |",
            ]
        )
        for row in delivery_only:
            success = next(a for a in ARMS if value(row[a], "delivery"))
            term = assignment(row["OSA"])
            reviews = "／".join(
                str(row[a].get("operations", {}).get("org_review_patch", 0)) for a in ARMS
            )
            nsubs = "／".join(str(len(row[a].get("submit_receipts", []))) for a in ARMS)
            lines.append(
                f"| {row['instance'].split('__')[-1]} | {success} | {term} | {reviews} | {nsubs} |"
            )
    shared_failure = {
        row["instance"] for row in rows if all(value(row[a], "code") is False for a in ARMS)
    }
    examples = {
        "astropy__astropy-14598": "Astropy-14598 的两支都通过 175 项原有回归，唯一目标用例都因长 FITS 字符串的单引号数量不符而失败。KEEP 修改写入时的切分，OSA 修改读取时的解析并增加测试；这两种修法都遗漏了官方覆盖的边界。",
        "django__django-12663": "Django-12663 的两支都通过 135 项原有回归，但在同一延迟对象子查询测试中失败。KEEP 分支在需要数字 ID 时交给字段一个 Manager 对象；OSA 分支交给字段的仍是包装后的 SimpleLazyObject。两份候选都没有修通目标行为。",
    }
    if shared_failure.intersection(examples):
        lines.extend(["", "## 两组都失败的具体例子", ""])
        lines.extend("- " + msg for iid, msg in examples.items() if iid in shared_failure)
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
            failure = row[bad]["scores"]["code"].get("candidate_failure") or {}
            if failure.get("classification") == "unresolved_candidate_merge_conflict":
                detail = f"。{bad} 锁定的最终代码在 {failure['path']} 第 {failure['line']} 行留有未解决的合并标记，补丁已应用，评分程序因语法错误退出；该错误已在锁定代码上复现"
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
