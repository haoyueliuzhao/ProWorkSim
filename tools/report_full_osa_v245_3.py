"""Reconcile the full OSA-only attempts against native receipts and the reused cash ledger."""

from collections import Counter
from contextlib import closing
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_full_osa_v245_3 import (
    ROOT,
    RUN,
    PLAN,
    AUTH,
    NS,
    LIMIT,
    save,
    read_json,
    reference,
)
from report_ordinary_successor_v243_2 import counts
from proworksim.software_benchmark_candidates_v054 import checked


def rate(values):
    low = sum(v is True for v in values)
    high = low + sum(v is None for v in values)
    n = len(values)
    return f"{low}/{n}（{100 * low / n:.1f}%）" if low == high else f"{low}–{high}/{n}"


def main():
    roster = read_json(PLAN / "roster.json")["roster"]
    rows = []
    usage = Counter()
    with closing(
        sqlite3.connect(Path(read_json(AUTH)["ledger"]).as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.execute("BEGIN")
        for task in roster:
            index = task["index"]
            base = RUN / str(index)
            job = base / "OSA"
            row = dict(
                instance=task["instance"],
                repo=task["repo"],
                fresh=None,
                prior=task["prior_failure"],
                code=None,
                delivery=None,
            )
            rows.append(row)
            paid = counts(db, f"{NS}:{index}:OSA")["paid"]
            usage.update(paid)
            row["paid"] = paid
            if not (job / "result.json").exists():
                continue
            result = read_json(job / "result.json")
            row.update(
                status=result["status"],
                termination=result.get("termination"),
                error=result.get("error"),
                started=result["started"],
                ended=result["finished"],
                generation_seconds=result["finished"] - result["started"],
            )
            if (job / "fresh-start.json").exists():
                f = read_json(job / "fresh-start.json")
                assert (
                    f["base_commit"] == task["base_commit"]
                    and f["instance"] == task["instance"]
                    and not f["history_restored"]
                )
                assert (
                    f["prior_patch_count"]
                    == f["initial_model_tokens"]
                    == f["initial_opportunities"]
                    == 0
                )
                row["fresh"] = reference(job / "fresh-start.json")
            if result["status"] == "closed":
                assert row["fresh"] and result["logical_tokens"] == paid["tokens"] <= LIMIT
            dec = job / "decision.json"
            if dec.exists():
                d = read_json(dec)
                choice = d["active"]["decision"]["option"]
                info = d["info"]
                inp = read_json(job / "decision-input.json")
                row["policy"] = dict(
                    changed=d["active"]["changed"],
                    option=choice,
                    requested=info.get("requested"),
                    validator=info["validator"],
                    assignment=inp["row"]["options"].get(choice)
                    or (info.get("orders") or {}).get(choice),
                    tokens=info["osa_tokens"],
                    opportunity=d["opportunity"],
                    first_action=info.get("first_action"),
                )
            for k in ("code", "delivery"):
                file = base / ("OSA-" + k) / "receipt.json"
                if not file.exists():
                    continue
                score = read_json(file)
                assert score["kind"] == k and score["instance_id"] == task["instance"]
                row[k] = score.get("resolved")
                row[k + "_status"] = score["status"]
                row[k + "_receipt"] = reference(file)
                if k == "code":
                    report = (score.get("official_result") or [None, {}])[1].get(
                        task["instance"], {}
                    )
                    tests = report.get("tests_status", {})
                    historical = read_json(checked(row["prior"]))["official_result"][1][
                        task["instance"]
                    ]["tests_status"]
                    target_now = set(tests.get("FAIL_TO_PASS", {}).get("failure", []))
                    target_before = set(historical.get("FAIL_TO_PASS", {}).get("failure", []))
                    row["recurring_failed_targets"] = sorted(target_now & target_before)
                    row["tests"] = {
                        g: {s: len(ids) for s, ids in groups.items()} for g, groups in tests.items()
                    }
                    row["failing_target_examples"] = tests.get("FAIL_TO_PASS", {}).get(
                        "failure", []
                    )[:3]
                    row["candidate_failure"] = score.get("failure_evidence")
            if (job / "boundary.json").exists():
                actions = read_json(job / "boundary.json")["outcomes"]
                row["submissions"] = [
                    dict(
                        step=j,
                        accepted=o["response"].get("ok"),
                        reason=(o["response"].get("error") or {}).get("message"),
                    )
                    for j, o in enumerate(actions, 1)
                    if (o.get("decision") or {}).get("action") == "submit_integration"
                ]
        cost = db.execute(
            "select coalesce(sum(cost),0) from requests where status='settled'"
        ).fetchone()[0]
        held = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
        held += db.execute(
            "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
        ).fetchone()[0]
        newcost = db.execute(
            "select coalesce(sum(cost),0) from requests where slot like 'v245.3:%' and status='settled'"
        ).fetchone()[0]
        assert usage["nanoyuan"] == newcost and cost + held <= 150_000_000_000
    state = dict(
        rows=rows,
        totals=dict(usage),
        cumulative_nanoyuan=cost,
        held_nanoyuan=held,
        available_nanoyuan=150_000_000_000 - cost - held,
        code=rate([r["code"] for r in rows]),
        delivery=rate([r["delivery"] for r in rows]),
    )
    save(PLAN / "results.json", state)
    policies = [r["policy"] for r in rows if "policy" in r]
    decisions = Counter(
        "调整"
        if x["changed"]
        else "回退维持"
        if x["validator"] == "rejected"
        else "暂缓"
        if x["requested"] == "ABSTAIN"
        else "维持"
        for x in policies
    )
    num = sum(r.get("status") == "closed" for r in rows)
    lines = [
        "# 12 道历史代码失败题的 OSA 完整任务测试",
        "",
        f"12 题中 {num} 题完成生成。最终代码通过官方验收 {state['code']}，正确合法交付 {state['delivery']}。每题从原始仓库、两名成员零历史开始，使用 DeepSeek Flash 非思考模式。本批仅运行 OSA。",
        "",
        "| 任务 | 最终代码 | 正确交付 | OSA 决策 | 输入＋输出（万 token） | 费用（元） |",
        "| --- | --- | --- | --- | ---: | ---: |",
    ]
    yes = {True: "通过", False: "未通过", None: "未定"}
    for r in rows:
        d = r.get("policy")
        op = (d.get("assignment") or {}).get("op") if d else None
        choice = (
            (
                "调整（" + str(op or d["option"]) + "）"
                if d["changed"]
                else "回退维持"
                if d["validator"] == "rejected"
                else "暂缓"
                if d["requested"] == "ABSTAIN"
                else "维持"
            )
            if d
            else "未调用"
        )
        lines.append(
            f"| {r['instance'].split('__')[-1]} | {yes[r['code']]} | {yes[r['delivery']]} | {choice} | {r['paid'].get('tokens', 0) / 10000:.2f} | {r['paid'].get('nanoyuan', 0) / 1e9:.2f} |"
        )
    only_failed = {r["instance"] for r in roster if r["known_passing_receipts"] == 0}
    sub = [r for r in rows if r["instance"] in only_failed]
    lines.extend(
        [
            "",
            f"其中，在核查范围内仅找到失败评分的 {len(sub)} 题，本轮代码通过 {rate([r['code'] for r in sub])}。",
        ]
    )
    submitted = [r for r in rows if any(x["accepted"] is True for x in r.get("submissions", []))]
    if submitted:
        lines.extend(
            [
                "",
                f"有 {len(submitted)} 题得到项目的正式提交回执，其中 {sum(r['delivery'] is True for r in submitted)} 份提交通过官方验收。",
            ]
        )
    if len(policies) == len(rows):
        lines.extend(
            ["", "| OSA 实际行为 | 题数 | 代码通过 | 正确交付 |", "| --- | ---: | ---: | ---: |"]
        )
        for change, label in [(True, "实际改组"), (False, "分工维持（含回退）")]:
            sub = [r for r in rows if r["policy"]["changed"] is change]
            if sub:
                lines.append(
                    f"| {label} | {len(sub)} | {sum(r['code'] is True for r in sub)} | {sum(r['delivery'] is True for r in sub)} |"
                )
        lines.extend(["", "分组取决于 OSA 当时的决定，两组数字仅描述本批实际行为。"])
    failed = [r for r in rows if r["code"] is False]
    if failed:
        lines += [
            "",
            "## 官方验收未通过的题",
            "",
            "| 题目 | 目标用例通过／失败 | 原有回归通过／失败 | 首个失败目标用例或回执 |",
            "| --- | ---: | ---: | --- |",
        ]
        for r in failed:
            tests = r.get("tests", {})

            def test_counts(key):
                v = tests.get(key)
                return "—" if v is None else f"{v.get('success', 0)}／{v.get('failure', 0)}"

            sample = next(iter(r.get("failing_target_examples", [])), r["code_status"])
            lines.append(
                f"| {r['instance'].split('__')[-1]} | {test_counts('FAIL_TO_PASS')} | {test_counts('PASS_TO_PASS')} | {sample.replace('|', '／')} |"
            )
    if failed:
        both = sum(bool(r.get("recurring_failed_targets")) for r in failed)
        intact = sum(
            bool(r.get("tests", {}).get("PASS_TO_PASS", {}).get("success"))
            and not r["tests"]["PASS_TO_PASS"].get("failure")
            for r in failed
        )
        lines.extend(
            [
                "",
                f"这 {len(failed)} 题中，{both} 题再次未通过至少一个与历史回执同名的目标用例；{intact} 题通过了本次评分器执行的全部原有回归用例。",
            ]
        )
    code_only = [r for r in rows if r["code"] is True and r["delivery"] is False]
    if code_only:
        lines.extend(
            [
                "",
                "代码通过但没有形成正确合法交付的任务为 "
                + "、".join(r["instance"].split("__")[-1] for r in code_only)
                + "。",
            ]
        )
    k = sum(bool(r["paid"].get("calls")) for r in rows)
    lines.extend(
        [
            "",
            f"共 {usage['calls']} 次已结算请求，输入 {usage['input']:,}、输出 {usage['output']:,} token，平均每个已调用回合 {usage['tokens'] / max(k, 1) / 10000:.2f} 万。含 {len(policies)} 次已记录的 OSA 决策，共 {sum(x['tokens'] for x in policies):,} token。决策分布为 "
            + "、".join(f"{g} {m} 次" for g, m in decisions.items())
            + "。",
            f"本批结算 {newcost / 1e9:.2f} 元；原账本累计 {cost / 1e9:.2f} 元，上限 150 元，扣除预约后可用 {state['available_nanoyuan'] / 1e9:.2f} 元。",
            "",
            "三题的最近失败记录是历史准备阶段候选的官方评分，其余九题为后续执行分支或普通任务。本轮十二题均从原始仓库完整执行。Django-15916 在核查范围内另有通过记录，其余 11 题在该范围内未查到通过回执。历史回合与本次运行条件可不同，单组重新通过数不能用于估计 OSA 相对其他组织方式的提升。",
            "",
            "[冻结方案与选题范围](v245-3-full-task-osa.md) · [原评分、运行决策与用量](../../artifacts/software-benchmark-v245-3/full-osa12-r1/results.json)",
        ]
    )
    (ROOT / "docs/experiments/v245-3-full-task-osa-results.md").write_text("\n".join(lines) + "\n")
    print(state["code"], state["delivery"], num, dict(usage))


if __name__ == "__main__":
    main()
