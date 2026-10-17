"""Build the v050 final report from saved, read-only JSON analyses."""
from __future__ import annotations

from datetime import datetime
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REPORTS = HERE.parent
BRANCHES = ("S_star", "B", "Q_plus", "Q_minus")
LABELS = {"S_star": "S*（未更新）", "B": "B", "Q_plus": "Q+", "Q_minus": "Q−"}


def read(name):
    return json.loads((HERE / name).read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def reference(path):
    return {"path": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size}


def table(headers, rows):
    return "\n".join([
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(str(v) for v in row) + " |" for row in rows),
    ])


def fraction(value):
    return str(Fraction(value).limit_denominator(100000))


def guard_digest(mapping):
    values = {value for group in mapping.values() for value in group}
    if len(values) != 1 or any(len(group) != 1 for group in mapping.values()):
        raise ValueError("Recorded branch guard hashes must be singleton and equal")
    return next(iter(values))


def outcome(row):
    return "成功" if row["R_joint"] == 1 else "提交未全过" if row["submitted"] else "未提交"


def build():
    science, costs = read("scientific-results.json"), read("costs.json")
    provenance, method = read("provenance.json"), read("method.json")
    rows, metrics = science["rows"], science["metrics"]
    checks = []

    def check(name, condition):
        if not condition:
            raise ValueError(name)
        checks.append({"name": name, "passed": True})

    check("56 unique original slots", len(rows) == len({r["slot_id"] for r in rows}) == 56)
    check("24 current-policy training slots", sum(r["phase"] == "training" for r in rows) == 24)
    check("all formal outcomes closed and known", all(r["status"] == "closed" and
          r["R_joint"] in (0, 1) and r["Q_joint"] is not None for r in rows))
    check("no administrative censoring", not any(r["administrative_censoring"] for r in rows))
    check("all four per-slot guards", all(all(r["evaluation_guard"].values()) for r in rows))
    check("original evidence audit has no blocking finding", not provenance["blocking_findings"] and
          all(c["passed"] for c in provenance["checks"]))
    for branch in BRANCHES:
        panel = [r for r in rows if r["phase"] == "development" and r["branch"] == branch]
        check(branch + " exact eight-unit panel", len(panel) == 8 and
              len({r["unit_id"] for r in panel}) == 8)
        check(branch + " F from original denominator", sum(r["R_joint"] for r in panel) / 8 ==
              metrics["branches"][branch]["F"])
        check(branch + " quality from actual fixed submission", all(math.isclose(r["Q_joint"],
              r["private_checks_passed"] / r["private_checks_total"] if r["submitted"] else 0)
              for r in panel))
    generation = metrics["generation"]
    for key in ("complete_actual_tokens", "budget_charged_tokens", "prompt_tokens", "completion_tokens",
                "decisions", "complete_actual_calls", "public_member_tests"):
        check("unique generation sum " + key, sum(r["cost"][key] for r in rows) == generation[key])
    check("prompt plus own output equals billed generation", generation["prompt_tokens"] +
          generation["completion_tokens"] == generation["complete_actual_tokens"] ==
          generation["budget_charged_tokens"])
    check("all generation bills known", generation["uncertain_usage_attempts"] == 0)
    check("three independent updates from identical original state", all(method["same_start_and_frozen_inputs"].values()))
    check("three distinct resulting actors", len({x["after_actor_identity"]["adapter_sha256"]
          for x in method["branches"].values()}) == 3)
    check("critic and critic Adam are invariant across updated branches",
          bool(guard_digest(provenance["final_critic_hashes"])) and
          bool(guard_digest(provenance["final_critic_optimizer_hashes"])))
    check("successful updates each exactly one actor and critic step", all(
          b["actor_optimizer_steps"] == b["critic_optimizer_steps"] == 1 and
          b["actor_steps_total"] == b["critic_steps_total"] == 5 for b in method["branches"].values()))
    epsilon = Fraction(str(metrics["epsilon"]))
    fd = (Fraction(sum(metrics["branches"]["Q_plus"]["metrics"]["R_joint"]["values"]), 8) -
          Fraction(sum(metrics["branches"]["Q_minus"]["metrics"]["R_joint"]["values"]), 8)) / (2 * epsilon)
    check("predeclared finite difference", float(fd) == metrics["finite_difference"])
    check("worker seconds counted once", math.isclose(sum(p["owned_worker_seconds"] for p in costs["phases"]),
          costs["gpu_worker_accounting"]["seconds"], rel_tol=1e-12))
    check("training interval upper below amended total cap", costs["training_aggregate"][
          "compute_interval_seconds_upper"] <= costs["training_allocation"]["aggregate_compute_seconds_cap"])
    check("post-cap actual concurrency at most four", costs["concurrency"]["passed"])
    check("final host is completely closed", costs["completion"]["final_supervisor_status"] == "complete" and
          costs["completion"]["final_unfinished_owned_workers"] == 0)

    completed = costs["completion"]["final_completed_at_shanghai"]
    summary = {
        "planned_slots": 56, "closed_slots": 56, "technical_unknown_slots": 0,
        "administrative_censored_slots": 0, "training_successes": 19, "training_slots": 24,
        "development_successes": {b: science["groups"][b]["R_joint_sum"] for b in BRANCHES},
        "development_denominator_per_branch": 8,
        "F": {b: metrics["branches"][b]["F"] for b in BRANCHES},
        "Q": {b: metrics["branches"][b]["Q"] for b in BRANCHES},
        "contrasts": metrics["contrasts"], "epsilon": float(epsilon), "finite_difference": float(fd),
        "successful_independent_actor_optimizer_steps": 3,
        "successful_independent_critic_optimizer_steps": 3,
        "known_generation_tokens": generation["complete_actual_tokens"],
        "gpu_worker_hours_all_attempts": costs["gpu_worker_accounting"]["hours"],
        "training_interval_hours_upper": costs["training_aggregate"]["compute_interval_hours_upper"],
        "aggregate_positive_learning_gain_observed_on_this_panel": False,
    }
    deviations = [
        "Original first-slot export error was rematerialized read-only; its formal outcome was retained, not regenerated.",
        "Interrupted Q computations were discarded and explicitly reauthorized from the same full S_star; old unknown rows and costs remain.",
        "The original per-Q cumulative 48-hour limit was replaced by an amended allocation inside the unchanged total 144-hour training budget.",
        "GPU capacity and concurrency rules changed with explicit user authorization; original numerical H1, samples, direction and final evaluation contract were retained.",
        "A later GPU2-only proposal was cancelled before deployment; the restored final host used GPUs 0-7 with a four-resident cap.",
    ]
    result = {
        "version": "software-learning-v050-final-report-v1", "status": "complete",
        "generated_at_shanghai": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "completed_at_shanghai": completed, "summary": summary, "metrics": metrics,
        "rows": rows, "groups": science["groups"], "root_groups": science["root_groups"],
        "support_blocks": science["support_blocks"], "selected_direction": science["selected_direction"],
        "update_method": method, "cost_accounting": costs, "provenance": provenance,
        "feedback": science["feedback"], "test_pages": science["pages"],
        "protocol_amendments": deviations, "limitations": science["limitations"],
        "report_validation": checks, "evidence_directory": HERE.name,
        "read_only_analysis": {"new_model_calls": 0, "new_backward_calls": 0,
            "new_gpu_calls": 0, "new_checkpoint_tensor_reads": 0, "new_world_or_acceptance_runs": 0},
        "automatic_successors": [], "old_queues_remain_paused": True,
    }
    json_path = REPORTS / "software-learning-v050-final.json"
    write_json(json_path, result)

    text = [
        "# v050 最终实验报告：固定24经历的局部组成敏感性窗口",
        "本窗口于 **2026-10-17 16:59:03（北京时间）** 完成。原24条训练与四状态各8条开发共56个唯一槽全部闭合，正式结果和生成费用均已知，技术未知与行政删失均为0。三个成功更新分支各自从同一完整S*4/4执行一次H=1，actor/critic各一步到5/5。",
        "**本面板未观察到更新后整体完整交付成功率超过S*。** S*、B、Q+、Q−的F分别为0.625、0.500、0.500、0.625；B−S*=−0.125。唯一预定方向的有限差分为−0.625。机制链条完成与正向学习收益是两个结论，本轮只支持前者及这个有限面板上的具体差异。",
        "[最终机器报告](software-learning-v050-final.json)保存逐槽结果、配对指标、完整成本和来源；[方法与逐成员分母](software-learning-v050-final-method.md)、[逐槽附表](software-learning-v050-final-slots.md)、[科学结果证据](software-learning-v050-final-evidence/scientific-section.md)、[成本账本](software-learning-v050-final-evidence/costs.md)、[来源及修订审计](software-learning-v050-final-evidence/provenance.md)分别提供细节。",
        "## 1 研究问题、状态与材料",
        "本轮按[原协议](software-learning-v050-protocol.md)研究局部E2组成敏感性：固定24条新当前策略经历，先检查可靠多类支持，再观察实际B反向中第一个可行非零方向；在任何开发结果出现前冻结方向，独立训练B、Q+、Q−，与未更新S*在同一八单位面板比较。没有按收益增加seed、换题、换方向或调整epsilon。",
        "S*是v049完整B4/4，包含actor、critic、两个Adam、RNG和已有001/002坐标；不是更早的common3/3。LA/LB各12个新seed构成本轮训练，旧v049八条不进入材料池。训练是两个固定人工家族内的重复，不是24个独立新任务。DA/DB复用开发家族，DC原子库存与DD原始坐标文本补丁为本轮事前新增的人工业务；四root各两个新配对seed，不是外部基准或独立确认。",
        "Γ1严格同值引用、严格O1两成员、空任务板、自主分工、18432上下文/2048输出、3072字符正文页、原固定树验收保持。每槽128决定/attempt、500000token、32测试和90+10分钟时限不变。资源与累计更新时限后来有明确修订，见第7节，不能写成所有原始协议完全不变。",
        "## 2 24条训练、失败材料与支持",
        "训练19/24完整成功，5/24均为已提交但验收未全通过；LA为7/12，LB为12/12。历史阶段说明中“5未提交”的概称不准确，本报告使用实际提交与验收字段；原LA-r01合法固定提交通过10/12检查，R=0。没有补验未提交工作区或重跑这个首槽。",
        "全部48条成员轨迹、643条实际生成决定、175532个本人输出token进入原H=1。actor分母为48T、critic为48K；T为该成员轨迹全部本人输出，K为实际生成决定数。5个可信R0及其他未映射残余保留单位基础权重，未将缺席质量重新分配。实际优势有522条正、121条负，均非零。",
    ]
    support_rows = []
    for block, values in science["support_blocks"].items():
        support_rows.append([block, 12, values["n_by_class"]["local_lineage_delivery"],
            values["n_by_class"]["evidenced_peer_product_delivery"], 12-values["n_positive"],
            values["admitted_decision_count"]])
    text += [table(["块", "原重复M", "local", "peer", "残余", "实际生成决定"], support_rows),
        "共17条可靠联合交付路线（8 local、9 peer），另7条未映射（5个R0、2个R1）。联合路线分别投影到两成员，因此34条可靠成员投影不是34个独立episode。四块均具每类至少2例的原定支持；没有跨root拼例或降低Mapper门槛。",
        "## 3 唯一冻结方向与实际训练",
        "首个选定块为 **LA/member_001/local_lineage_delivery**。基线b=(local 4/7, peer 3/7)，d=(local +3/7, peer −3/7)，ρ=7/15，ε=0.1，实际混合梯度L2=0.007746008657106765。方向封存比第一条开发开始早121.255秒；梯度只读hook返回None，没有额外反向。",
        table(["处理", "local组成", "peer组成", "local actor权重", "peer actor权重"], [
            ["B", "4/7", "3/7", 1, 1], ["Q+", "43/70", "27/70", 1.075, .9],
            ["Q−", "37/70", "33/70", .925, 1.1]]),
        "只重加权该块7条可靠成员轨迹；同块5条残余、其他3个成员块和全部critic仍单位权重。正号增加的是这一局部块的local份额，不能概括为“增加合作”。原B梯度已含1/(48T)，没有再次按root或minibatch归一。",
        "B、Q+、Q−均独立恢复同一个S*4/4；各完成643条逐决定反向、1288次actor wrapper前向（643有梯度、645无梯度，其中2条固定后更新观测）、actor/critic各1次optimizer。三者都是5/5，不是从B继续到6/6或串行累积到7/7。H=1表示一次窗口积累，不是一次backward；wrapper计数不是GPU kernel数。",
    ]
    update_rows = []
    for branch in ("B", "Q_plus", "Q_minus"):
        v = method["branches"][branch]
        update_rows.append([LABELS[branch], "4/4→5/5", v["changed_actor_elements"],
            f'{v["gradient_norms"]["actor"]:.12f}', f'{v["gradient_norms"]["critic"]:.12f}',
            v["after_actor_identity"]["adapter_sha256"][:12]])
    text += [table(["分支", "完整状态步数", "变化actor元素", "actor梯度范数", "critic梯度范数", "最终actor摘要前缀"], update_rows),
        "三条最终actor及actor Adam摘要均不同；现有开发collection-guard记录证明三条最终critic与critic Adam摘要完全相同。运行时完整checkpoint重载及全部56条逐槽学习/RNG/身份/绑定守卫通过。本报告仅重读JSON凭据，没有重新加载张量或运行模型。",
        "原recipe为epochs1、actor LR1e−5、critic LR1e−3、PPO clip0.2、梯度L2 clip1、terminal MC、γ1、无优势标准化、critic系数0.5及原LoRA/Adam。实际旧critic的643个值均非零（0.014372778至0.020893708）；原报告模板的zero-initialized文字不代表本轮重新初始化，旧原文保留。",
        "## 4 四状态配对开发结果",
        "主指标F为四root×两seed的等权正式R_joint均值，分母固定8。Q为同单位最后合法固定交付的私有合同检查通过比例，未提交记0；本轮无行政删失，joint/token口径相等。跨训练与开发混合的37/56成功不是学习收益指标。",
    ]
    branch_rows = []
    for branch in BRANCHES:
        group = science["groups"][branch]
        branch_rows.append([LABELS[branch], f'{group["R_joint_sum"]}/8',
            group["outcomes"].get("submitted_incomplete", 0), group["outcomes"].get("unsubmitted", 0),
            f'{metrics["branches"][branch]["F"]:.3f}', f'{metrics["branches"][branch]["Q"]:.9f}',
            f'{group["generation"]["complete_actual_tokens"]:,}'])
    text += [table(["状态", "完整成功", "提交未全过", "未提交", "F", "平均Q", "生成token"], branch_rows)]
    paired_rows = []
    for row in metrics["paired_development"]:
        paired_rows.append([row["unit_id"].removeprefix("org50-dev-"), row["sampling_seed"],
            *(f'{row["R_joint"][b]} / ({fraction(row["Q_joint"][b])})' for b in BRANCHES)])
    text += [table(["单位", "seed", "S* R/Q", "B R/Q", "Q+ R/Q", "Q− R/Q"], paired_rows),
        "预定对比为 **B−S*=−0.125；Q+−B=0；Q−−B=+0.125**。有限差分为 `(0.500−0.625)/(2×0.1)=−0.625`。F的最小分辨率是0.125，Q±差异只相当于八单位净差一个成功槽；不是总体显著性结论、完整Contribution估计或一般协作因果效应。",
        "配对变化更具体：B相对S*在DA-s1变成功，在DC-s1、DD-s2失去成功。Q+相对B在DA-s2失去成功、DC-s2得到成功，均值持平；Q−相对B只在DC-s1多成功。Q−与S*均值相同，但成功集合不同（DA-s1得到成功、DD-s2失去成功）。DB在四状态的两个seed全部成功；新DC/DD四单位中S*成功2，B成功0，Q±各成功1。",
        "Q+平均Q=0.734375，高于Q−的0.625，但主指标F更低。Q+的DC-s1和DD-s2均通过15/16私有检查，仍为R0；部分质量与全项成功阈值给出不同排序。报告保留两项，不能择取更有利的Q替代预定F。",
        "保存的开发验收失败分别是S*/DA-s1的allocation-sixteen、B/DD-s2的patch-private-interior-insert、Q+/DC-s1的inventory-private-invalid-id、Q+/DD-s2的patch-private-endpoints。未提交槽未做追加验收，也不推断其工作区若继续会成功。",
        "## 5 生成、工具反馈与容量终止",
    ]
    generation_rows = []
    for group_name in ("training", *BRANCHES):
        g = science["groups"][group_name]["generation"]
        generation_rows.append(["训练" if group_name == "training" else LABELS[group_name],
            g["decisions"], g["complete_actual_calls"], f'{g["prompt_tokens"]:,}',
            f'{g["completion_tokens"]:,}', f'{g["complete_actual_tokens"]:,}', g["public_member_tests"]])
    generation_rows.append(["合计", generation["decisions"], generation["complete_actual_calls"],
        f'{generation["prompt_tokens"]:,}', f'{generation["completion_tokens"]:,}',
        f'{generation["complete_actual_tokens"]:,}', generation["public_member_tests"]])
    text += [table(["组", "决定", "实际调用", "输入token", "输出token", "合计token", "成员测试"], generation_rows),
        "全部实际生成费用已知，账本等于22,078,253 token，不确定预约0。比原28M总上限少5,921,747 token，不转移。1,566个决定中39次为执行前共享团队余额预约拒绝（训练7、四开发组各8），不产生生成或新世界动作。原56槽测量中真实硬context与成员fixed拒绝均为0。训练重放和反向另计，不能折作新增生成token。",
        "1,527条反馈均保存；1,415条有后续同成员实际生成，全部在首个实际后继呈现。112条无后继的原因为72次工作结束、1次无事件等待、39次团队余额终止。202份测试报告均存储核查通过，201份目录及至少一页实际呈现；7份历史累计完整呈现，30次主动read_test_result，232次页反馈返回。未呈现不等于已读，未全读也不是本轮失败判据。",
        "## 6 全部计算成本，包括中断与舍弃工作",
        f'32个唯一GPU worker合计 **{costs["gpu_worker_accounting"]["seconds"]:.9f}秒，即{costs["gpu_worker_accounting"]["hours"]:.9f} GPU worker小时**。这是进程占用计时，包含加载、收尾、预约和失败工作，不是GPU kernel忙时。原监督器重复观察外部worker不产生第二份GPU费用。',
    ]
    phase_rows = [[p["root"].removeprefix("software-learning-v050" ) or "原始",
        p["unique_owned_worker_count"], f'{p["owned_worker_seconds"]:.6f}'] for p in costs["phases"]]
    text += [table(["阶段后缀", "唯一worker", "worker秒"], phase_rows)]
    attempts = []
    for attempt in costs["training_attempts"]:
        attempts.append([attempt["root"].removeprefix("software-learning-v050-") + "/" + attempt["worker"],
            f'{attempt["native_forward_completed"]}/{attempt["native_forward_started"]}',
            f'{attempt["actor_backward_completed_lower"]}/{attempt["actor_backward_charged_upper"]}',
            f'{attempt["actor_optimizer_steps"]}/{attempt["critic_optimizer_steps"]}',
            f'{attempt["compute_interval_seconds_upper"] / 3600:.6f}' + ("（上界）" if not attempt["compute_interval_exact"] else "")])
    text += [table(["实际训练尝试", "前向返回/开始", "每侧反向确认/扣账上界", "actor/critic step", "训练区间小时"], attempts),
        "总前向6,377次开始、6,376次完整返回；旧Q+有一次返回未确证。actor、critic各确认2,510条反向，扣账上界2,513；其中成功分支实际使用1,929条，旧失败已完成至少581条、上界584条均未应用optimizer。不能把上界写成精确完成，也不能用最终成功覆盖旧未决行。",
        f'训练计算区间保守上界 **{costs["training_aggregate"]["compute_interval_hours_upper"]:.9f}小时**，低于修订后仍保持的144小时总边界。旧三次中断没有精确训练结束点，采用进程观察退出时刻作为上界，精确总训练时长仍为null。训练区间已经嵌套在GPU worker时间中，不再次相加。',
        "r4 Q+的106010.568376秒worker时间已包含同一PID的2013.543856秒预约前奏，不能再加预约目录全长。r4 Q−在真正模型loader前CUDA查询OOM，12.528383秒启动费用保留，前向/反向/optimizer及训练区间消费均为0。r3、旧r6及取消前r7均无新的自有GPU计算。",
        "实际并发峰值4；上限4生效后仍为4。Q+开发使用GPU2/6，八槽wall约68分49秒；Q−开发使用GPU1/4/5/7，八槽wall约48分30秒。并行wall time与GPU worker时间是不同量。最终训练Q+在GPU2、Q−在GPU1完成。",
        "## 7 修订历史、原未知与可解释范围",
        "原首槽训练已经完成固定交付与逐槽guard，但导出注册接缝令外层collector失败；r1以同源只读重物化恢复原槽的消费者记录，只运行余下23条。原首槽外层collection guard缺失不回填，首槽R0和费用不改写。",
        "旧Q−在r1和r2分别中断、旧Q+在r1中断；记录及未应用的部分梯度保留。后续由用户明确授权从同一完整S*重新计算，并非精确恢复中断梯度。原源码、失败停点与时间成本没有删除。具体故障归因及授权链见[来源审计](software-learning-v050-final-evidence/provenance.md)。",
        "**实际执行使用修订后的计算/资源协议。** 原每Q累计48小时限制在r3/r4被用户授权的144小时总预算内再分配替代：先计B和全部旧Q成本247437.884515秒，再给两个最终Q区间各135481秒。不能声称两Q始终满足原各自48小时规则或原协议一次通过。原材料、seed、方向、数值H=1和验收保持，但运行时限和计算尝试历史已改变。",
        "显存门后来改为装载前46080MiB空闲，缓存min(73728, free−1024)MiB、最低45056MiB；60秒稳定等待、共享6144MiB终止和自身56GiB上限已取消。随后用户将总并发设为4。GPU2单卡方案仅到草稿阶段即被用户取消，恢复GPU0—7与总并发4；旧r6零worker行政终态保留，r6-restored唯一执行原16条开发。",
        "各旧宿主的closed_with_unknowns含不同含义：历史真实训练中断、已移交未开始库存、行政退出都保留原状态。最终56条科学结果已知，不表示旧训练中断的每一行、外层guard或时间端点都已变为已知。旧v049 DA-s2、v046及旧26/3/48/缓存生产的未知/暂停也不因本轮完成而改变。",
        "单槽worker拆分和跨GPU调度改变了装载与资源竞争条件；源码和数值路径保持不等于逐token轨迹严格等价。GPU worker耗时差不能直接归因于学习，状态间结果属于实际执行条件下的有限配对观察。",
        "## 8 有限结论与结束",
        "本轮实现了24条当前策略经历提供多类支持、预先选择一个非零局部方向、三分支真实独立更新、四状态完整配对开发。实际actor与Adam变化、失败材料进入训练、critic未被组成重加权以及更新状态真正用于开发均有既有记录支持。",
        "结果未显示B、Q+或Q−在整体F上超过S*。B减少一个净成功单位；Q−恢复到S*均值，Q+与B均值相同；唯一方向有限差分为负。它支持报告这一个小面板上的具体组成敏感性，不支持泛化为协作无效、普遍负Contribution、精确梯度估计或统计显著学习退化。",
        "只有一个训练窗口、两个训练家族、四个人工开发root和每root两个seed；DA/DB还是复用家族，训练支持来自联合路线的成员投影。F与Q排序、成功集合、费用和运行器变化必须同时阅读。没有进行独立确认或完整I-P/I-S算法实验。所有猜测性解释只可作为后续假设，本轮没有据结果追加实验。",
        "本次报告生成仅读取既有JSON/协议并进行确定性汇总；来源审阅的503项JSON比较不是503条新增模型资格或pytest。另做报告分母、加总、来源和预算一致性校验，没有调用模型、加载权重、执行世界工具或重新验收。组件引用及输出SHA见[报告清单](software-learning-v050-final-evidence/report-manifest.json)。",
        "**本窗口结案，无自动后继。** 不追加方向、seed、更新或开发槽；旧暂停队列保持。任何下一窗口需新的明确授权。",
    ]
    main_path = REPORTS / "software-learning-v050-final.md"
    main_path.write_text("\n\n".join(text) + "\n")

    appendix = ["# v050 最终逐槽附表", "本表由原固定提交和实际账单生成，不包含新验收。全部56槽正式结果已知；R0按原提交状态区分。主结论见[最终报告](software-learning-v050-final.md)。"]
    for phase, branch in [("training", None), *(("development", b) for b in BRANCHES)]:
        panel = [r for r in rows if r["phase"] == phase and (branch is None or r["branch"] == branch)]
        appendix.append("## " + ("原24条训练" if phase == "training" else LABELS[branch] + "的8条开发"))
        appendix.append(table(["原槽", "seed", "R/Q", "结果", "决定", "调用", "token", "测试"], [
            [r["slot_id"], r["sampling_seed"], f'{r["R_joint"]} / ({fraction(r["Q_joint"])})', outcome(r),
             r["cost"]["decisions"], r["cost"]["complete_actual_calls"],
             f'{r["cost"]["complete_actual_tokens"]:,}', r["cost"]["public_member_tests"]] for r in panel]))
    slots_path = REPORTS / "software-learning-v050-final-slots.md"
    slots_path.write_text("\n\n".join(appendix) + "\n")

    method_text = ["# v050 最终方法与完整状态证据", "这是最终报告的方法附录。全部信息来自已保存的原生运行/逐槽/collection guard与JSON凭据，本次没有加载checkpoint张量或增加前向、反向、验收。",
        "## 本人目标与原分母", "实际新材料包含643条Γ1 native input（8,793,409输入token）及175,532个本人输出token；上下文不是本人目标。48条成员轨迹均保留，actor按48T、critic按48K归一，拒绝决定不计入K。各成员的输出与调用分母如下。"]
    denominators = []
    for row in rows[:24]:
        for member in row["members"]:
            usage = row["usage_by_member"][member]
            denominators.append([row["slot_id"], member, usage["completion_tokens"],
                usage["output_bearing_calls"], 48*usage["completion_tokens"], 48*usage["output_bearing_calls"]])
    method_text.append(table(["槽", "成员", "T本人输出", "K生成决定", "48T", "48K"], denominators))
    method_text += ["## 更新与critic", "原H=1函数和prepare_window code object保持同值，完整recipe、函数摘要、实际输入/目标和恢复声明见机器报告的update_method及provenance.branches。三分支的643个旧critic值、优势和reward逐项相同，actor组成变化不扩展到critic。",
        "原报告中的zero-initialized措辞是历史模板；实际继承的4/4 critic已有非零值，不能解释为本轮重置。共有121条负优势和522条正优势，没有只保留成功材料。",
        "现有collection-guard中的最终critic摘要为 `" + guard_digest(provenance["final_critic_hashes"]) +
        "`；critic Adam摘要为 `" + guard_digest(provenance["final_critic_optimizer_hashes"]) +
        "`，三分支完全同值。actor及其Adam分别不同。守卫摘要相等是既有运行时证据，本报告没有重做逐元素张量比较。",
        "## 完整状态摘要", "S*来自v049 B4/4，完整state_tensor_digest为`ff8c828bcc475132d6d6bbddad3a114da62ace9da9c905e560d7d7c5a3cefc39`。common-restore3/3只是模型构造中间步骤，实际更新前loaded-state明确恢复S*4/4。"]
    method_text.append(table(["分支", "最终actor SHA256", "完整state_tensor_digest", "重载精确"], [
        [LABELS[b], method["branches"][b]["after_actor_identity"]["adapter_sha256"],
         method["branches"][b]["checkpoint"]["state_tensor_digest"], "true"]
        for b in ("B", "Q_plus", "Q_minus")]))
    method_text += ["## 计算计数的范围", "成功分支各1288次wrapper前向和643条逐决定反向；整个窗口还包括旧失败尝试。总计算及下界/上界见主报告和costs.json。生成token只计算实际1527次生成调用，不将训练重复读取本人输出折成新生成费用。",
        "## 报告复核", f"本次构建执行{len(checks)}项确定性报告一致性断言；另有来源审阅503项JSON比较。二者属于只读分析，不增加pytest或模型资格数量。复现此文档构建可从仓库根执行 `.venv/bin/python docs/experiments/software-learning-v050-final-evidence/build-final-report.py`，它仅消费同目录保存的分析JSON；原件提取脚本亦保存在证据目录，执行它们需要对应runs原件。"]
    method_path = REPORTS / "software-learning-v050-final-method.md"
    method_path.write_text("\n\n".join(method_text) + "\n")
    validation = {"passed": True, "deterministic_report_checks": len(checks), "checks": checks,
                  "read_only": True, "new_model_calls": 0, "new_tensor_reads": 0}
    write_json(HERE / "report-validation.json", validation)
    components = [p for p in HERE.iterdir() if p.is_file() and p.name != "report-manifest.json"]
    manifest = {"version": "v050-final-report-artifact-manifest-v1",
                "components": [reference(p) for p in sorted(components)],
                "outputs": [reference(p) for p in (json_path, main_path, slots_path, method_path)],
                "original_experiment_records_rewritten": False}
    write_json(HERE / "report-manifest.json", manifest)
    print(json.dumps({"status": "complete", "report_checks": len(checks), "summary": summary}, ensure_ascii=False))


if __name__ == "__main__":
    build()
