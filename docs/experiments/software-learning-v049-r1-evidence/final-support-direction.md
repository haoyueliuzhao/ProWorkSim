# v049 正式 B 支持与无 I 方向结案说明

本说明只读已闭合 `runs/software-learning-v049-resume-r1/support.json`、`direction.json`、B report 与梯度 JSON。正式更新后支持实际保存在 run 根的 `support.json`，由 direction 绑定；`support-before-update.json` 仍是早先快照。未读取开发结果或 `.pt`，未启动 forward、模型、GPU、测试、验收、导出或资格检查。

B 已按原路径完成206条原决定，actor/critic各1 optimizer step，总步数由3/3到4/4；全部51328本人输出目标保留。B原生actor梯度范数为 0.0500310845673084，critic为 0.627356112003326，实际actor变化元素数为 1114091。这是实际更新事实，不是开发收益结论。

正式方向为 `selected=false`、`reliable_base_material=true`、`no_admissible_I_direction_B_only`，且 `frozen_before_any_development=true`。按LA/001→LA/002→LB/001→LB/002的原顺序，四块都因 `single_qualified_category` 被排除；不是因优势为零、基础actor梯度为零、optimizer没有变化或开发表现而排除。

| root/member | M / 基础轨迹 | 门前local/peer | 可靠类别 / 支持数 | v / b(local) | 实际B决定 | I自由度 / G-raw类内 |
|---|---:|---|---|---|---:|---|
| LA/member_001 | 4/4 | 3 / 1 | local / 3 | .75 / 1 | 38 | 0 / 2 |
| LA/member_002 | 4/4 | 3 / 1 | local / 3 | .75 / 1 | 61 | 0 / 2 |
| LB/member_001 | 4/4 | 3 / 1 | local / 3 | .75 / 1 | 53 | 0 / 2 |
| LB/member_002 | 4/4 | 3 / 1 | local / 3 | .75 / 1 | 54 | 0 / 2 |

每类事前最低支持为2。各块peer只出现1次，因此可靠组成只剩local；在单元素概率单纯形上，I的非零组成方向不存在，故保持q=b。每块3条可靠local原轨迹内仍有2个G-raw自由度，本轮G-raw未执行。ρ、ε、Q±权重和有限差分均无选定结果，保持null；不能写成已测Contribution=0或G-raw没有自由度。

以下范数直接取正式 `update-B/actual/update/support-gradients.json`；它们是B原有逐决定leaf梯度依原顺序在slot/member内累加、共享裁剪前的范数，已经包含原基础分母。16组全部非零。表内r1—r4均指对应root的原四重复。

| root/member | r1 | r2 | r3 | r4 |
|---|---:|---:|---:|---:|
| LA/member_001 | 0.0127513431228 | 0.0129161932173 | 0.0134527317177 | 0.0111417151826 |
| LA/member_002 | 0.0121740966818 | 0.0037929492267 | 0.0147796648201 | 0.00917990742958 |
| LB/member_001 | 0.0127643617887 | 0.0110485822552 | 0.0198147352281 | 0.0112526015782 |
| LB/member_002 | 0.0078595116152 | 0.0110706724613 | 0.0150086660237 | 0.0122552586456 |

这些范数不能相加当作root/member块向量和的范数。原JSON没有提供该块聚合范数，本说明不读取张量补算，也不把缺项写成0。signal诊断另存总范数0.05003108470413243，B原生report保存上面的0.050031084567308426；两者按各自原记录保留，不强改成同一数值。无I候选时没有实际混合方向范数；nonzero基础梯度不代替I可行性。

LA r4和LB r3的peer虽然各未过可靠类别两例门，两个slot的四条成员轨迹仍全部进入B：共52条原决定、12136本人输出，baseline权重均1，原base mask均true。整个B仍为8个联合episode、16成员轨迹、206条completion与51328目标，不把v=.75解释为删去25%训练目标，不跨root拼peer支持，不将两成员投射当成同一块两次独立重复。

只读hook的凭据记录额外actor forward/backward及optimizer均0，hook返回None；观察记录并不替代Q的原生更新，也不证明梯度对齐、优化器敏感性或因果工作价值。

与原 `training-eight-work-support.json` 的有限一致性核对结果：True。四块除原快照待定的优势字段外，全部既有支持字段逐值一致；8槽R、类别、Validity、最终固定交付链及16成员的原目标数、B实际梯度行数、分母和单位权重均一致。正式support和direction引用的B报告/梯度JSON摘要也对应同一闭合产物。

209宿主决定、206真实completion/反向行与critic的K需要分列。首次摘要核对曾直接比较`original_admission.members.all_decisions`与旧报告的`actual_completions`，在以下三条成员轨迹返回false；这是本次分析比较字段口径不同，不是原材料变化、实验失败或新增资格失败。原B admission中的真实`decisions`列表共206行，正好对应观察反向行。

| 原槽/成员 | all_decisions | 真实completion/反向行 | 无生成共享拒绝 | critic K | 原critic分母 |
|---|---:|---:|---:|---:|---:|
| LA r2/002 | 30 | 29 | 1 | 29 | 464=16×29 |
| LB r1/001 | 18 | 17 | 1 | 17 | 272=16×17 |
| LB r1/002 | 18 | 17 | 1 | 17 | 272=16×17 |

其余13条成员轨迹两种计数相同；合计209宿主决定、206生成/反向行、3次已知无生成共享预约拒绝。数值绑定`src/proworksim/software_learning_v049.py:271-272`明确使用`sum(item["actor_required"] for item in view["decisions"])`构成16K。已存B admission逐行的critic分母与旧八槽报告全16条既定分母一致，K不包含这3次拒绝。它们没有被补成训练目标，也没有引发分母或原对象修改。JSON保留首次跨口径比较false的原数值及这一解释。

原八槽事实报告保持原样：其中优势/梯度待定及等待B的语句描述当时快照；本说明补上已完成后的正式记录，不回写历史。这里没有重做工作链分析、重验旧交付，或根据开发成绩改类别、样本、方向和剂量。开发完成情况与F/Q不在本说明范围内。
