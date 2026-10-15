"""Assemble the organization report from already extracted, read-only evidence."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path

ASSETS = Path(__file__).resolve().parent
DOCS = ASSETS.parent
REPO = ASSETS.parents[2]
BASENAME = "software-organization-strategies-comparison-20261015"

def load(name):
    return json.loads((ASSETS / name).read_text())

def fmt(value, digits=1):
    if value is None:
        return "—"
    if isinstance(value, int) or float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.{digits}f}"

def table(headers, rows):
    def cell(value):
        return str(value).replace("|", r"\|").replace("\n", " ")
    return "\n".join(["| " + " | ".join(map(cell, headers)) + " |",
                       "| " + " | ".join("---" for _ in headers) + " |",
                       *["| " + " | ".join(map(cell, row)) + " |" for row in rows]])

def rate(row):
    return f"{row['R']['known_sum']}/{row['fixed_denominator']}"

def participant_range(rows):
    values = sorted({r.get("actual_call_members") for r in rows if r.get("actual_call_members") is not None})
    return "/".join(map(str, values)) if values else "—"

def main():
    data, history = load("comparison-data.json"), load("historical-context.json")
    a45, a47, a48 = (data[v]["aggregates"] for v in ("v045", "v047", "v048"))
    l45 = {r["condition"]: r for r in a45}
    l47 = {(r["condition"], r["team_token_budget"]): r for r in a47}
    l48 = {(r["condition"], r["representation"]): r for r in a48}
    checks = []
    for version, n, total in (("v045", 24, 8296556), ("v047", 44, 12239903), ("v048", 8, 2039108)):
        rows = data[version]["rows"]
        if version in ("v045", "v047"):
            assert {r["root_id"] for r in rows} == {"LA", "HA", "LB", "HB"}
        assert len(rows) == len({r["slot_id"] for r in rows}) == n
        assert sum(r["complete_actual_tokens"] for r in rows) == total
        checks.append({"version": version, "unique_slots": n, "complete_tokens": total, "passed": True})
    assert len(history["v038"]["per_slot_plot_rows"]) == 24
    assert [l45[k]["R"]["known_sum"] for k in ("S1", "F2", "O3")] == [4, 4, 4]
    assert len(l47) == 11 and all((k, 500000) not in l47 for k in ("D2", "I2", "P2"))
    assert [l48[(k, g)]["R"]["known_sum"] for k, g in (("S1","Gamma0"),("S1","Gamma1"),("P4","Gamma0"),("P4","Gamma1"))] == [1, 2, 0, 2]
    assert len(data["v048"]["context_rejections"]) == 6
    order = ("S1", "D2", "D4", "I2", "I4", "P2", "P4")
    values = {}
    values["OVERVIEW_TABLE"] = table(["组内比较", "成功数与成本结果", "可解释范围"], [
        ["v038 固定2人与固定4人", "固定2人3/8；固定4人1/8；初始2人可扩编3/8", "旧呈现协议下的八配对；可扩编组实际没有增员"],
        ["v045 S1/F2/O3", "全部4/8；双人/可扩编组费用为S1的1.468/1.541倍", "同规格同seed结果一致；不代表所有任务制度等效"],
        ["v047 七架构与两预算", "250k下S1/D2/D4/I2/P2均1/4，I4/P4为0/4；500k下D4为2/4、I4为1/4", "D2/D4实际单人；500k仅预锁四配置"],
        ["v048 S1/P4 × Γ0/Γ1", "P4由0/2变为2/2；Γ1下S1也2/2，P4平均费用约2.99倍", "两个既有root的机制对照；表示修订与人数效应分开"],
        ["v044 信息布局与工作说明", "split+team为3/4，其余三条件均2/4", "人数保持；包含输入容量、取证和行为路径的综合结果"],
    ])
    values["STAGE_TABLE"] = table(["策略/阶段", "执行成员", "token份额", "决定/attempt", "测试上限", "代码和交付职责"], [
        ["P2 实现", "001", "60%", "76/76", "20", "可编辑、测试、固定候选；不正式提交"],
        ["P2 复核修订提交", "002", "40%", "52/52", "12", "显式取得成果，可复核、编辑/整合、测试、固定并提交"],
        ["P4 实现", "001", "35%", "44/44", "8", "可编辑、测试、固定候选；不正式提交"],
        ["P4 独立复核", "002", "20%", "26/26", "8", "可读取、采用、测试和反馈；禁止编辑/合并，不正式提交"],
        ["P4 修订整合", "003", "25%", "32/32", "8", "可编辑/整合并测试、固定修订候选；不正式提交"],
        ["P4 验证提交", "004", "20%", "26/26", "8", "禁止编辑/合并；本人同树测试、固定并提交"],
    ])
    values["V038_TABLE"] = table(["条件", "实际有输出成员/槽", "成功/8", "平均完整token", "实际调用合计", "硬context拒绝"], [
        [r["condition"] + {"O1":" 固定双人","O2":"固定四人","O3":"可扩编双人"}[r["condition"]], r["actual_output_members_per_episode"], f"{r['successes']}/8", fmt(r["mean_tokens_per_episode"]), r["calls"], r["hard_context_rejections"]]
        for r in history["v038"]["conditions"]])
    values["V045_TABLE"] = table(["制度", "成功/8", "完整token合计", "平均完整token", "实际调用", "成员测试", "相对S1费用"], [
        [k, rate(l45[k]), fmt(l45[k]["complete_actual_tokens"]), fmt(l45[k]["mean_complete_actual_tokens"]), l45[k]["actual_calls"], l45[k]["member_tests"], f"{l45[k]['mean_complete_cost_ratio_to_same_setting_S1']:.3f}倍"] for k in ("S1", "F2", "O3")])
    values["V045_ROOT_TABLE"] = table(["root", "S1成功/2", "F2成功/2", "O3成功/2"], [
        [root, *[str(sum(r["R"] for r in data["v045"]["rows"] if r["root_id"] == root and r["condition"] == k)) + "/2" for k in ("S1","F2","O3")]] for root in ("LA","HA","LB","HB")])
    values["V047_MATRIX"] = table(["架构", "250k成功/4", "500k成功/4", "实际有输出人数"], [
        [k, rate(l47[(k,250000)]), rate(l47[(k,500000)]) if (k,500000) in l47 else "未设置", participant_range([r for r in data["v047"]["rows"] if r["condition"] == k])] for k in order])
    values["V047_COST_TABLE"] = table(["团队预算", "架构", "成功/4", "Q均值", "平均完整token", "实际调用合计", "相对同预算S1费用"], [
        [f"{budget//1000}k", k, rate(r), f"{r['Q']['mean']:.3f}", fmt(r["mean_complete_actual_tokens"]), r["actual_calls"], f"{r['mean_complete_cost_ratio_to_same_setting_S1']:.3f}倍"]
        for budget in (250000,500000) for k in order if (r:=l47.get((k,budget)))])
    values["V047_BUDGET_TABLE"] = table(["架构", "成功率差 500k−250k", "Q均值差", "每槽平均token增加", "实际人数变化"], [
        [r["condition"], f"{r['mean_deltas']['R']*100:+.0f}个百分点", f"{r['mean_deltas']['Q']:+.3f}", fmt(r["mean_deltas"]["complete_actual_tokens"]), fmt(r["mean_deltas"]["actual_call_members"])] for r in data["v047"]["budget_pairs"]])
    values["V048_TABLE"] = table(["架构", "表示", "成功/2", "Q均值", "平均完整token", "调用/测试", "硬context拒绝"], [
        [k, g.replace("Gamma","Γ"), rate(r), f"{r['Q']['mean']:.3f}", fmt(r["mean_complete_actual_tokens"]), f"{r['actual_calls']}/{r['member_tests']}", sum(s["hard_context_rejections"] for s in data["v048"]["rows"] if s["condition"]==k and s["representation"]==g)]
        for k in ("S1","P4") for g in ("Gamma0","Gamma1") for r in [l48[(k,g)]]])
    values["V048_ROOT_TABLE"] = table(["root", "架构/表示", "R", "Q", "完整token", "首次提交token", "首次提交后token"], [
        [r["root_id"], r["condition"]+"/"+r["representation"].replace("Gamma","Γ"), r["R"], f"{r['Q']:.3f}", fmt(r["complete_actual_tokens"]), fmt(r["first_fixed_submit_tokens"]), fmt(r["after_first_submit_tokens"])] for r in data["v048"]["rows"]])
    info=history["v044"]["information_definition"]
    values["V044_EXPLANATION"] = ("**shared**："+info["shared"]+"。**split**："+info["split"]+"。后来出生成员不自动继承初始诊断。\n\n"
        +"**base**："+history["v044"]["base_definition"]+"\n\n**team**额外说明："+history["v044"]["team_translation"]+"\n\n"
        +"team明确提示共同交付与可选协作，但不给任务分解、岗位、顺序或正确代码，也不强制首轮通信。")
    values["V044_TABLE"] = table(["条件", "初始信息", "工作说明", "成功/4", "平均完整token", "实际调用", "新增出生"], [
        [r["condition"],r["information"],r["framing"],f"{r['successes']}/4",fmt(r["mean_tokens_per_episode"]),r["calls"],r["actual_new_births"]] for r in history["v044"]["conditions"]])
    tables=[]
    tables.append("### B1 v038 八个配对块\n\n"+table(["业务root", "seed尾号", "固定2人O1", "固定4人O2", "可扩编O3"], [
        [r["case_id"].removeprefix("sc-").replace("-v035-orgdev-v038","").replace("-v036-orgdev-v038",""),str(r["sampling_seed"])[-3:],*[r["R"][k] for k in ("O1","O2","O3")]] for r in history["v038"]["paired_units"]]))
    tables.append("### B2 v045 八个配对块\n\n"+table(["root", "完整seed", "S1 R", "F2 R", "O3 R"], [
        [r["root_label"],r["sampling_seed"],*[r["R"][k] for k in ("S1","F2","O3")]] for r in data["v045"]["paired_blocks"]]))
    for budget in (250000,500000):
        rows=sorted([r for r in data["v047"]["rows"] if r["team_token_budget"]==budget], key=lambda r:(("LA","HA","LB","HB").index(r["root_id"]),order.index(r["condition"])))
        tables.append(f"### B{3 if budget==250000 else 4} v047 {budget//1000}k逐槽\n\n"+table(["root","架构","R","Q","输出成员数","完整token","首次提交token"],[
            [r["root_id"],r["condition"],r["R"],f"{r['Q']:.3f}",r["actual_call_members"],fmt(r["complete_actual_tokens"]),fmt(r["first_fixed_submit_tokens"])] for r in rows]))
    tables.append("v048全部八槽已列于第7节。首次提交token的横线表示无提交或该字段未提供，不能按0计。完整逐槽数据还包括v038和v045的全部费用，见附件CSV/JSON。")
    values["SLOT_TABLES"]="\n\n".join(tables)
    source_rows=[]
    specs=[("v038人数对照","software-organization-v038-final","software-organization-v038-protocol.md"),
      ("v039外生出生补充","software-organization-v039-final","software-organization-v039-protocol.md"),
      ("v040容量反例","software-organization-v040-final","software-organization-v040-protocol.md"),
      ("v044信息与说明","software-organization-v044-completion-final","software-organization-v044-protocol.md"),
      ("v045人数制度","software-organization-v045-completion-final","software-organization-v045-protocol.md"),
      ("v047架构预算","software-organization-v047-final","software-organization-v047-protocol.md"),
      ("v048表示对照","software-organization-v048-final","software-organization-v048-protocol.md"),
      ("v046未完容量诊断","software-organization-v046-final","software-organization-v046-protocol.md"),
      ("严格O1语义","software-learning-v049-final","software-learning-v049-protocol.md")]
    source_manifest=[]
    for label,base,protocol in specs:
        source_rows.append([label,f"[报告]({base}.md) / [机器结果]({base}.json)",f"[协议]({protocol})"])
        for filename in (base+".md",base+".json",protocol):
            path=DOCS/filename
            raw=path.read_bytes()
            source_manifest.append({"path":str(path.relative_to(REPO)),"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)})
    values["SOURCE_INDEX"]=table(["主题","结果来源","策略来源"],source_rows)+"\n\n逐条策略事实的源码行和协议定位见[strategy-catalog.json](software-organization-strategies-comparison-20261015-assets/strategy-catalog.json)；历史范围见[historical-context.json](software-organization-strategies-comparison-20261015-assets/historical-context.json)。"
    text=(ASSETS/"report-template.md").read_text()
    for key,value in values.items():
        marker="{{"+key+"}}"
        assert marker in text,key
        text=text.replace(marker,value)
    assert "{{" not in text and "}}" not in text
    output=DOCS/(BASENAME+".md")
    output.write_text(text)
    # Flat exports preserve version boundaries and never add an overall rank.
    configuration_rows=[]
    for r in history["v038"]["conditions"]:
        configuration_rows.append({"version":"v038","strategy":r["condition"],"team_budget":500000,"representation":"v038_original","status":"scheduled","n":r["scheduled"],"successes":r["successes"],"R_mean":r["mean_R"],"Q_mean":None,"total_tokens":r["total_tokens"],"mean_tokens":r["mean_tokens_per_episode"]})
    for version in ("v045","v047","v048"):
        for r in data[version]["aggregates"]:
            configuration_rows.append({"version":version,"strategy":r["condition"],"team_budget":r.get("team_token_budget",500000),"representation":r.get("representation",version+"_original"),"status":"scheduled","n":r["fixed_denominator"],"successes":r["R"]["known_sum"],"R_mean":r["R"]["mean"],"Q_mean":r["Q"]["mean"],"total_tokens":r["complete_actual_tokens"],"mean_tokens":r["mean_complete_actual_tokens"]})
    for k in ("D2","I2","P2"):
        configuration_rows.append({"version":"v047","strategy":k,"team_budget":500000,"representation":"v047_original","status":"not_scheduled","n":None,"successes":None,"R_mean":None,"Q_mean":None,"total_tokens":None,"mean_tokens":None})
    for r in history["v044"]["conditions"]:
        configuration_rows.append({"version":"v044","strategy":r["condition"],"team_budget":500000,"representation":"v044_original","status":"scheduled","n":r["scheduled"],"successes":r["successes"],"R_mean":r["mean_R"],"Q_mean":None,"total_tokens":r["total_tokens"],"mean_tokens":r["mean_tokens_per_episode"]})
    with (ASSETS/"comparison-configurations.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(configuration_rows[0]));w.writeheader();w.writerows(configuration_rows)
    slot_rows=[]
    for r in history["v038"]["per_slot_plot_rows"]:
        slot_rows.append({"version":"v038","slot_id":r["slot_id"],"root_id":r["case_id"],"strategy":r["condition"],"seed":r["sampling_seed"],"team_budget":500000,"representation":"v038_original","R":r["R"],"Q":None,"actual_tokens":r["usage"]["total_tokens"],"actual_calls":r["usage"]["attempts"],"member_tests":r["run_tests_calls"],"first_submit_tokens":None})
    for version in ("v045","v047","v048"):
        for r in data[version]["rows"]:
            slot_rows.append({"version":version,"slot_id":r["slot_id"],"root_id":r["root_id"],"strategy":r["condition"],"seed":r["sampling_seed"],"team_budget":r.get("team_token_budget",500000),"representation":r.get("representation",version+"_original"),"R":r["R"],"Q":r["Q"],"actual_tokens":r["complete_actual_tokens"],"actual_calls":r["actual_calls"],"member_tests":r["member_tests"],"first_submit_tokens":r.get("first_fixed_submit_tokens")})
    assert len(slot_rows)==100 and len({(r['version'],r['slot_id']) for r in slot_rows})==100
    with (ASSETS/"comparison-slots.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(slot_rows[0]));w.writeheader();w.writerows(slot_rows)
    (ASSETS/"assembly-checks.json").write_text(json.dumps({"version":"organization-strategy-report-assembly-v1","passed":True,"checks":checks,"v038_rows":24,"csv_unique_rows":100,"not_scheduled_500k":["D2","I2","P2"],"technical_unknown_R_in_core_panels":0,"Q_missing_v045":"Metric not reported in source; not technical unknown outcomes and not zero Q.","first_submit_missing":"Absent/not reported, not a zero cost.","data_sources":source_manifest,"new_model_calls":0,"new_tests_or_acceptances":0,"new_parameter_updates":0},ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"markdown":str(output),"characters":len(text),"csv_rows":100,"checks_passed":True},ensure_ascii=False))

if __name__=="__main__":
    main()
