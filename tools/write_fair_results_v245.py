"""Render the matched regression endpoints, old comparison, actions and cash from receipts."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_fair_pairs_v245 import PLAN, ROOT, ARMS, read_json
from report_fair_pairs_v245 import main as reconcile


def mark(v):
    return {True: "通过", False: "未通过", None: "待定"}[v]


def result(row, a, k):
    return row[a]["scores"].get(k, {}).get("resolved")


def ratio(values):
    known = [v for v in values if v is not None]
    return (
        f"{sum(known)}/{len(values)}"
        if len(known) == len(values)
        else f"{sum(known)} 至 {sum(known) + len(values) - len(known)}/{len(values)}"
    )


def write_report():
    d = read_json(PLAN / "results.json")
    rows = d["rows"]
    ready = [
        r
        for r in rows
        if all(result(r, a, k) is not None for a in ARMS for k in ("code", "delivery"))
    ]
    spent = sum(v["nanoyuan"] for v in d["totals"].values()) / 1e9
    doc = [
        "# v245.1 六题同题回归结果",
        "",
        f"计划 6 道不同任务，共 12 条续跑。已有 {len(ready)} 道题取得两组完整评分。独立账本 150 元，按真实 API 用量结算 {spent:.2f} 元。",
        "",
        "KEEP 继续原分工，OSA 在同一保存点额外获得一次组织决策机会。两组使用同一新版交付合同。普通工作包凭作者、版本、产物与证据完成；两名成员都编写代码时，保留独立复核和受管补派。数据来自已知开发题的再次生成。",
        "",
        "| 同一组 6 题 | KEEP 代码正确 | OSA 代码正确 | KEEP 正确交付 | OSA 正确交付 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for old in [True, False]:
        data = [
            ratio([r["v244"][a][k] if old else result(r, a, k) for r in rows])
            for k in ("code", "delivery")
            for a in ARMS
        ]
        doc.append(
            "| " + ("v244 原合同" if old else "v245.1 新合同") + " | " + " | ".join(data) + " |"
        )
    doc += [
        "",
        "| 题目 | KEEP 代码／交付 | OSA 代码／交付 | OSA 实际决定 | 新增万 token（KEEP／OSA） |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for r in rows:
        arms = ["／".join(mark(result(r, a, k)) for k in ("code", "delivery")) for a in ARMS]
        m = r["OSA"].get("mechanism", {})
        action = (
            "待定"
            if not m
            else "调整 " + str(m.get("operation"))
            if m["changed"]
            else "提案被拒，维持"
            if m["validator"] != "accepted"
            else "暂缓"
            if m["requested"] == "ABSTAIN"
            else "维持"
        )
        tok = "／".join(f"{r[a]['paid'].get('tokens', 0) / 10000:.2f}" for a in ARMS)
        doc.append(
            f"| {r['instance'].split('__')[-1]} | {arms[0]} | {arms[1]} | {action} | {tok} |"
        )
    doc += [
        "",
        "## 成本、时间和返工",
        "",
        "| 条件 | 新增输入／输出 token | 平均新增／含历史万 token | 平均生成时间 | 明确重开工作包的分支 | 同一人同版本同选择重复测试／可比测试 | 账本费用 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for a in ARMS:
        t = d["totals"][a]
        z = [r[a] for r in rows if "logical_tokens" in r[a]]
        if not z:
            continue
        n = len(z)
        m = [x["mechanism"] for x in z]
        doc.append(
            f"| {a} | {t['input']:,}／{t['output']:,} | {sum(x['paid']['tokens'] for x in z) / n / 10000:.2f}／{sum(x['logical_tokens'] for x in z) / n / 10000:.2f} | {sum(x['generation_seconds'] for x in z) / n / 60:.1f} 分钟 | {sum(bool(v['reopens']) for v in m)}/{n} | {sum(v['repeated_public_tests'] for v in m)}/{sum(v['comparable_public_tests'] for v in m)} | ¥{t['nanoyuan'] / 1e9:.2f} |"
        )
    z = [r[a] for r in rows for a in ARMS if "end_wall" in r[a]]
    if z:
        doc += [
            "",
            f"首个分支启动至最后一个评分回执约 {(max(x['end_wall'] for x in z) - min(x['started'] for x in z)) / 60:.1f} 分钟。OSA 调用 {sum(r['OSA'].get('policy_tokens', 0) for r in rows):,} token，已含在本组新增用量内。完整预算按每支计入共同历史；账本只对新增请求计费。",
        ]
    doc += ["", "## 分工有没有真正改变", ""]
    for name, k in [
        ("产生预期成果的调整／已激活调整", "additional"),
        ("确认被下游采用／实际新增成果", "adoption_confirmed"),
        ("确认解除／可判定的初始异常", "resolution"),
    ]:
        x, n = d["rates"][k]
        doc.append(f"- {name}：{x}/{n}" + ("，无适用分母。" if not n else "。"))
    oldrows = {
        r["instance"]: r
        for r in read_json(ROOT / "artifacts/software-benchmark-v244/midtask15-r1/results.json")[
            "rows"
        ]
    }
    if len(ready) == len(rows):
        oldcost = (
            sum(oldrows[r["instance"]][a]["paid"]["nanoyuan"] for r in rows for a in ARMS) / 1e9
        )
        oldtok = sum(oldrows[r["instance"]][a]["paid"]["tokens"] for r in rows for a in ARMS)
        newtok = sum(t["tokens"] for t in d["totals"].values())
        dos = sum(bool(r["OSA"]["mechanism"]["changed"]) for r in rows)
        disps = [r["OSA"]["mechanism"] for r in rows]
        noassigned = sum(bool(r[a]["missing_reviewer_at_start"]) for r in rows for a in ARMS)
        rejects = sum(
            x["code"] == "graph_authority"
            for r in rows
            for a in ARMS
            for x in r[a]["reviewer_calls"]
        )
        doc.extend(
            [
                "",
                f"这六题在旧实验共消耗 {oldtok:,} 个新增 token、{oldcost:.2f} 元；本次为 {newtok:,} 个、{spent:.2f} 元。分支起点仍保留原人员配置，新交付清单中有逐包派人硬缺口的分支共 {noassigned}/12；成员补派复核人遭组织权限拒绝 {rejects} 次。",
                f"六次策略决策中实际改组 {dos} 次，提案被拒 {sum(v['validator'] != 'accepted' for v in disps)} 次。旧配置下这六题曾有三次改组。比较两轮时应一并考虑规则、权限和模型重新生成带来的差异。",
            ]
        )
    blocked = [
        r[a]
        for r in rows
        for a in ARMS
        if any(x["code"] == "graph_authority" for x in r[a].get("reviewer_calls", []))
    ]
    if blocked:
        delivered = sum(x["scores"].get("delivery", {}).get("resolved") is True for x in blocked)
        doc += [
            "",
            f"上述拒绝涉及 {len(blocked)} 条分支，其中 {delivered} 条后来仍正确交付。逐条核对，尝试补派的工作包在终态均无需强制复核。仍有成员把可选的复核安排当作下一步，额外消耗了行动机会；仅凭这些拒绝回执无法区分旧会话提示和成员自行判断各占多少。",
        ]
    if len(ready) == len(rows) and all(not r["OSA"]["mechanism"]["changed"] for r in rows):
        doc += [
            "",
            "六次 OSA 都沿用原组织图。它仍为原责任人指定了下一步工作（完成工作包或诊断失败），两支之后各自生成，因此结果与成本可以不同。这里比较的是提供一次策略决策机会的效果，实际改组的净贡献尚无样本。",
        ]
    for r in ready:
        m = r["OSA"]["mechanism"]
        if m["changed"]:
            doc.append(
                f"- {r['instance']}：{m['operation']}，工作包 {m['task']}。新责任成员实际行动 {len(m['actual'])} 次，预期成果 {len(m['products'])} 项，确认采用 {len(m['confirmed_adopted'])} 项。"
            )
    doc += [
        "",
        "本阶段在固定进度决定分支，未对初始异常做独立抽样。策略对当前状态的自报分类不充当异常解除证据。单次生成和按旧结果选题都限制跨任务外推。明确重开工作包仅覆盖可查返工。",
        "",
        "## 正确代码未交付时，还欠什么",
        "",
    ]
    for r in rows:
        for a in ARMS:
            if result(r, a, "code") is True and result(r, a, "delivery") is False:
                v = r[a]["final_check"]
                g = [k for p in v["packages"] for k in p["missing"]] + [
                    p["kind"] for p in v["gaps"] if "kind" in p
                ]
                g = [
                    "工作包尚未登记当前版本的代码或证据"
                    if k == "complete_current_code_or_evidence"
                    else k
                    for k in g
                ]
                doc.append(
                    f"- {r['instance'].split('__')[-1]} {a}：最终缺项 {', '.join(dict.fromkeys(g)) or '已就绪，仍需显式提交'}；正式提交尝试 {len(r[a]['submissions'])} 次。"
                )
    if len(ready) == len(rows):
        cells = d["endpoints"]["delivery"]["cells"]
        doc += [
            "",
            f"新合同下有 {cells.get('both', 0)} 题两组均正确交付，{cells.get('KEEP_only', 0)} 题仅 KEEP 交付，{cells.get('OSA_only', 0)} 题仅 OSA 交付。两组交付数量还需和具体题目一起看。",
            "",
            "独立账本余额为 %.2f 元。12 个生成环境均有移除回执，本批没有在途或待分配预约。"
            % (150 - spent),
            "",
            "## 研究边界",
            "",
            "这六题依照旧结果预选，每个条件只跑一次。新合同下 KEEP 能否独立完成交付，可由正式提交直接核实；两次生成在代码、测试顺序和结束时间上仍会波动。前瞻性阶段另行记账，四类自然异常分别保留空缺，本批未将历史新增交付用于 C/N 更新。",
        ]
    doc += [
        "",
        "[设计、权限和零调用验收](v245-fair-delivery-regression.md) · [逐分支评分、行动、版本及费用](../../artifacts/software-benchmark-v245/fair-regression-r1/results.json)",
    ]
    (ROOT / "docs/experiments/v245-fair-delivery-results.md").write_text("\n".join(doc) + "\n")


if __name__ == "__main__":
    reconcile()
    write_report()
