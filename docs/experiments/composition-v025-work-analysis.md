# v0.25 R2 业务成果与协作过程详析

**12 例确认均有原始可评分记录，完整职责完成 2/12；2 例后继交互完成 0/2。两个成功分别是“核准已经正确的初稿”和“新政策下确认原数值仍正确并保留”，均不能写成新修复或学习收益。** 本文补充逐槽业务过程，保留各项原评分，不重新运行模型、世界或评分器。

材料来自 [R2 原自动报告](composition-pilot-v025-r2.md)、[原自动报告 JSON](composition-pilot-v025-r2.json) 及运行目录中的原始 `assessment/projection/runtime/episode`。本旁注的 [结构化数据](composition-v025-work-analysis.json) 保存来源 SHA-256、原判定、完整工具参数、结果摘要及原事件序号；不复制模型所有历史输入。所有 `#序号` 均指对应 `runtime.json` 的 `experience.events[].sequence`，不是工具 action_id 或世界 logical_time。`runs/` 原件为本机归档，未纳入 Git 的原件链接需要在实验服务器查看。

## 结论及解释边界

- 确认的原标量 R 合计 3.1，描述性均值 0.2583；A 为 0/4，B 为 1/4，维护为 1/4。后继 A/B 分别 R=0.2/0，均未完整完成。标量 R 是预定有限职责分项之和，不能替代完整职责成功率。
- 两个业务成功均继承已有正确固定成果；确认中没有当前模型创建且最终完整交付的新固定正确修复。A 的一次当前正确构建只获得部分分，仍被请求状态和提交环节阻断。
- 看到一次有证据的真实错误定位和相应代码编辑，未看到其后构建、固定提交、问题处置及最终复核闭合。
- 同一更新后端点上的少量不同材料/采样观察只能描述表现。R2 没有对应的更新前评价，本分析也未进行组合经验与均匀经验的并列训练；不据此给出参数学习收益或主对照点估计。

## 全部 14 槽结果

| 槽位 | 材料 / 初始状态 | seed | 原 R | 完整职责 | 实际过程要点 |
|---|---|---:|---:|---|---|
| [confirm-00-0](#confirm-00-0) | v025-material-08 / 无预制提交 | 202610022000 | 0.5 | 否 | A：交接后有正确构建，未形成固定提交 |
| [confirm-02-0](#confirm-02-0) | v025-material-10 / correct | 202610022020 | 0.0 | 否 | B：正确初稿被提出无效问题 |
| [confirm-04-0](#confirm-04-0) | v025-material-12 / 需数值变化 | 202610022040 | 0.0 | 否 | 维护：结果确需变化，误核准旧结果 |
| [confirm-01-0](#confirm-01-0) | v025-material-09 / 无预制提交 | 202610022010 | 0.2 | 否 | A：读取与交接后触发格式错误上限 |
| [confirm-03-0](#confirm-03-0) | v025-material-11 / wrong_count | 202610022030 | 0.0 | 否 | B：定位真实计数错误并改代码，修复链未闭合 |
| [confirm-05-0](#confirm-05-0) | v025-material-13 / 数值不变 | 202610022050 | 0.0 | 否 | 维护：数值应保留，证据链不完整的核准 |
| [confirm-00-1](#confirm-00-1) | v025-material-08 / 无预制提交 | 202610022001 | 0.2 | 否 | A：交接完成，SQL 执行失败 |
| [confirm-02-1](#confirm-02-1) | v025-material-10 / correct | 202610022021 | 1.0 | 是 | B：正确初稿经独立核准，完成职责 |
| [confirm-04-1](#confirm-04-1) | v025-material-12 / 需数值变化 | 202610022041 | 0.0 | 否 | 维护：已采用新政策，未重建亦未正式判断 |
| [confirm-01-1](#confirm-01-1) | v025-material-09 / 无预制提交 | 202610022011 | 0.2 | 否 | A：先交接被拒，再构建与代码格式失效 |
| [confirm-03-1](#confirm-03-1) | v025-material-11 / wrong_count | 202610022031 | 0.0 | 否 | B：错误初稿重跑后撤回，没有有效复核 |
| [confirm-05-1](#confirm-05-1) | v025-material-13 / 数值不变 | 202610022051 | 1.0 | 是 | 维护：核查新政策并保留原正确数值，完成职责 |
| [continue-00-0](#continue-00-0) | v025-material-14 / 无预制提交 | 202610023000 | 0.2 | 否 | 后继 A：预检通过，交接请求未闭合且提交失败 |
| [continue-01-0](#continue-01-0) | v025-material-15 / wrong_count | 202610023010 | 0.0 | 否 | 后继 B：问题与代码修改未形成有效修复 |

确认是 6 种情境 × 2 个预定采样 seed；同情境两次不是两个独立来源材料。表格中的后继两槽属于不同阶段，不并入确认 12 例分母。

## 工具成功、业务有效性与终止分别计数

| 统计项 | 确认 12 例 | 后继 2 例 |
|---|---:|---:|
| 世界工具调用 | 191 | 40 |
| 外层 `ok=true` / 被拒 | 165 / 26 | 31 / 9 |
| `approve` 成功写入 | 4 | 0 |
| 其中独立 valid / invalid | 2 / 2 | 0 / 0 |
| `raise_issue` 成功写入 | 2 | 1 |
| 其中独立 valid / invalid | 1 / 1 | 0 / 1 |
| 角色终止总数 | 24 | 4 |
| 后端上下文限制 | 15 | 2 |
| 固定决定轮次上限 | 5 | 2 |
| 冻结格式错误上限 | 1 | 0 |
| 主动 `completed` | 3 | 0 |

确认 4 次 approve 的 2 次无效核准均缺完整 `read_evidence`；其中一次发生在确需数值变更的维护材料，一次发生在数值原本无需变化的材料。因此“无效核准”与“批准了错误数值”不是同义项。确认和后继各 1 次无效 issue 也均为 `read_evidence=null`；原 valid 字段无法单独拆出错误内容、错误位置与缺证据的各自因果贡献，本报告不另外分配失败原因分数。

确认 8 例有 reviewer 职责，其中 2 例没有成功写入任何正式 approve/raise_issue（confirm-03-1、confirm-04-1）；这表示缺正式判断，不表示没做阅读。错误 B confirm-03-0 虽有有效初始问题，也没有最终 approve。两例完整成功均在完成有效核准后到达上下文限制，故不能把 `model_budget_exhausted` 直接当成业务失败。相反，confirm-04-0 的 reviewer 主动 `completed` 也未满足独立业务判定。

确认共 6 次 sql_build 外层均 ok=true，内部 4 次 execution_status=success、2 次 execution_error；后继共 1 次 sql_build，内部 success。执行器成功、可编辑唯一性测试通过，以及结构预检 structurally_ready，均不替代业务内容检查。确认只有 confirm-00-0 原判定保存当前正确构建证据；其余缺该证据处不新增“纯内容正确/错误”重判。

## 逐槽证据与协作断点

<a id="confirm-00-0"></a>

### confirm-00-0：A：交接后有正确构建，未形成固定提交

情境 `retail-v25-f7dc142787741388`；seed `202610022000`；原 R=0.5；完整职责=否。末态 `blocked`；角色终止：provider=completed；implementer=model_budget_exhausted。

provider 在 #8 读取 basis v1；implementer 在 #18 建立 mail-1 请求，provider 在 #30 交接该精确版本，但交接的 request_id 为 null。implementer 完成 basis/data 采用、写入 code v2，并在 #155 构建 result v2；原判定明确保存 current_correct_build，结果为客户 12949 的 3860 pence / 1 张发票、13094 的 42942 pence / 2 张发票。此后 #194 再写 code v3，未再构建；#207 submit 被拒，原消息为 Work is not open for submission by this actor。终态工作 status=blocked，mail-1 仍 pending，submissions 为空。原 R=0.5 是交接和实际使用两项之和，不能写为“已交付正确成果”。未闭合请求是直接可见的流程断点；修改后的 code v3 是否另有问题，本报告未执行判定。

原分项：`applicable_basis_delivered`=达成（0.2/0.2）；`delivered_basis_used_in_build`=达成（0.3/0.3）；`correct_fixed_delivery`=未达成（0.0/0.5）。

复核：[原评价](../../runs/domain-v025-r2/confirm_base/actual/confirm-00-0/assessment.json) · [原时间线](../../runs/domain-v025-r2/confirm_base/actual/confirm-00-0/runtime.json) · [终态世界](../../runs/domain-v025-r2/confirm_base/actual/confirm-00-0/episode/end/control/state.json) · [情境与冻结合同](../../runs/domain-v025-r2/confirm_base/actual/confirm-00-0/episode/manifest.json)。关键事件：#18、#30、#77、#116、#142、#155、#194、#207。

<a id="confirm-02-0"></a>

### confirm-02-0：B：正确初稿被提出无效问题

情境 `retail-v25-ecbc95c34ed0941e`；seed `202610022020`；原 R=0.0；完整职责=否。末态 `in_review`；角色终止：implementer=model_budget_exhausted；reviewer=model_budget_exhausted。

初始固定提交本来正确，并非本轮模型产物。reviewer #18 inspect，#41 读取 data，#64 尝试读取不共享的 basis 被拒，#87 读取 audit_basis，#110 读取 result；此前没有成功读取固定 code。#133 raise_issue 工具 ok=true，但原独立评价 valid=false、read_evidence=null。implementer #122 重新执行了已有代码，但未创建新固定提交；末尾原正确固定提交仍存在，缺少有效最终复核，三项职责均未达成，R=0。问题有效性失败不能仅凭 valid=false 归因为“数值算错”，因为完整证据读取也未成立。

原分项：`independent_final_review`=未达成（0.0/0.4）；`correct_fixed_final_product`=未达成（0.0/0.3）；`valid_review_and_repair_path`=未达成（0.0/0.3）。

复核：[原评价](../../runs/domain-v025-r2/confirm_base/actual/confirm-02-0/assessment.json) · [原时间线](../../runs/domain-v025-r2/confirm_base/actual/confirm-02-0/runtime.json) · [终态世界](../../runs/domain-v025-r2/confirm_base/actual/confirm-02-0/episode/end/control/state.json) · [情境与冻结合同](../../runs/domain-v025-r2/confirm_base/actual/confirm-02-0/episode/manifest.json)。关键事件：#18、#41、#64、#87、#110、#122、#133、#145、#173。

<a id="confirm-04-0"></a>

### confirm-04-0：维护：结果确需变化，误核准旧结果

情境 `retail-v25-8af50a90ebc7148d`；seed `202610022040`；原 R=0.0；完整职责=否。末态 `accepted`；角色终止：implementer=model_budget_exhausted；reviewer=completed。

真实政策重发已在开始前执行；该材料从旧口径转为 net_signed 后确实要求数值变化。implementer #76 成功 adopt_version basis v2，但没有 write_object、sql_build、withdraw 或 submit；原 current_repair_build=null。reviewer 三次尝试访问不共享的 basis（#41/#64/#110）被拒，#133 读取 audit_basis v2，#175 approve 工具成功，但原判断 valid=false、read_evidence=null；此前 reviewer 没有成功读取 data。implementer #145 的最后一次 result 读取后没有成功的后续模型请求消费该返回，因此原 implementer_current_inspection=false（原判定还要求本角色实际消费）。旧结果获工具层 accepted 不等于满足新口径，R=0。

原分项：`independent_current_policy_review`=未达成（0.0/0.4）；`correct_current_policy_fixed_product`=未达成（0.0/0.3）；`valid_maintenance_response`=未达成（0.0/0.3）。

复核：[原评价](../../runs/domain-v025-r2/confirm_base/actual/confirm-04-0/assessment.json) · [原时间线](../../runs/domain-v025-r2/confirm_base/actual/confirm-04-0/runtime.json) · [终态世界](../../runs/domain-v025-r2/confirm_base/actual/confirm-04-0/episode/end/control/state.json) · [情境与冻结合同](../../runs/domain-v025-r2/confirm_base/actual/confirm-04-0/episode/manifest.json)。关键事件：#8、#18、#30、#41、#64、#76、#99、#110、#133、#145、#165、#175。

<a id="confirm-01-0"></a>

### confirm-01-0：A：读取与交接后触发格式错误上限

情境 `retail-v25-ac454ec3588acd62`；seed `202610022010`；原 R=0.2；完整职责=否。末态 `blocked`；角色终止：implementer=model_format_error；provider=model_budget_exhausted。

#30 已完成适用依据交接，implementer 读取 basis、data、code；没有 adopt、write_object、sql_build 或 submit 世界动作。implementer 在 #132 达到冻结的格式错误上限；provider 在 #137 达到固定决定轮次上限。原评分仅认可交接 R=0.2。该例的终止类别不能归成全部上下文不足。

原分项：`applicable_basis_delivered`=达成（0.2/0.2）；`delivered_basis_used_in_build`=未达成（0.0/0.3）；`correct_fixed_delivery`=未达成（0.0/0.5）。

复核：[原评价](../../runs/domain-v025-r2/confirm_base/actual/confirm-01-0/assessment.json) · [原时间线](../../runs/domain-v025-r2/confirm_base/actual/confirm-01-0/runtime.json) · [终态世界](../../runs/domain-v025-r2/confirm_base/actual/confirm-01-0/episode/end/control/state.json) · [情境与冻结合同](../../runs/domain-v025-r2/confirm_base/actual/confirm-01-0/episode/manifest.json)。关键事件：#18、#30、#42、#65、#88、#132、#137。

<a id="confirm-03-0"></a>

### confirm-03-0：B：定位真实计数错误并改代码，修复链未闭合

情境 `retail-v25-0a00faea6532187f`；seed `202610022030`；原 R=0.0；完整职责=否。末态 `in_progress`；角色终止：implementer=model_budget_exhausted；reviewer=model_budget_exhausted。

初稿为 wrong_count。reviewer #133 在固定 result v2 的 [tables,metrics,rows,0,2] 提出阻塞问题，证据包含 data v1 与 audit_basis v1；原评价 valid=true。问题指出 CustomerID 14110 的发票数为 3、应为 2，并指出 COUNT(DISTINCT InvoiceNo)+1。implementer #145 撤回原提交，#168 写 code v3，原 SQL 文本确已去掉该 +1。随后 #188 上下文上限停止；本轮没有 sql_build、submit、respond_issue 或 approve。reviewer #250 尝试经 audit_basis 路由交接 code v3 被拒。可以报告“有效定位＋代码局部修改”，不能报告“已执行验证的修复”或最终复核完成；原 R=0、treatment=[null]、current_repair_build=null。

原分项：`independent_final_review`=未达成（0.0/0.4）；`correct_fixed_final_product`=未达成（0.0/0.3）；`valid_review_and_repair_path`=未达成（0.0/0.3）。

复核：[原评价](../../runs/domain-v025-r2/confirm_base/actual/confirm-03-0/assessment.json) · [原时间线](../../runs/domain-v025-r2/confirm_base/actual/confirm-03-0/runtime.json) · [终态世界](../../runs/domain-v025-r2/confirm_base/actual/confirm-03-0/episode/end/control/state.json) · [情境与冻结合同](../../runs/domain-v025-r2/confirm_base/actual/confirm-03-0/episode/manifest.json)。关键事件：#18、#41、#64、#87、#99、#110、#133、#145、#168、#188、#250。

<a id="confirm-05-0"></a>

### confirm-05-0：维护：数值应保留，证据链不完整的核准

情境 `retail-v25-db6ed5a08bcdcc1f`；seed `202610022050`；原 R=0.0；完整职责=否。末态 `accepted`；角色终止：implementer=model_budget_exhausted；reviewer=model_budget_exhausted。

本例政策重发后原数值仍正确，理应检查后保留。implementer #145 采用 basis v2，#168 读 result 后即到上下文上限，原 implementer_current_inspection=false。reviewer 多次访问 basis 被拒，并在 #179 使用错误 data 对象 ID；#198 改成正确 data v1 后 #211 approve 工具成功，但原评价 valid=false、read_evidence=null，reviewer 在本轮未成功读取固定 code。此处不能写“误批了错误数值”：原材料无需数值变化，失败主要表现为所需证据/检查不完整；缺少完整证据时，不另断言模型内部计算是否正确。

原分项：`independent_current_policy_review`=未达成（0.0/0.4）；`correct_current_policy_fixed_product`=未达成（0.0/0.3）；`valid_maintenance_response`=未达成（0.0/0.3）。

复核：[原评价](../../runs/domain-v025-r2/confirm_base/actual/confirm-05-0/assessment.json) · [原时间线](../../runs/domain-v025-r2/confirm_base/actual/confirm-05-0/runtime.json) · [终态世界](../../runs/domain-v025-r2/confirm_base/actual/confirm-05-0/episode/end/control/state.json) · [情境与冻结合同](../../runs/domain-v025-r2/confirm_base/actual/confirm-05-0/episode/manifest.json)。关键事件：#8、#53、#87、#99、#110、#122、#145、#156、#168、#179、#198、#211。

<a id="confirm-00-1"></a>

### confirm-00-1：A：交接完成，SQL 执行失败

情境 `retail-v25-f7dc142787741388`；seed `202610022001`；原 R=0.2；完整职责=否。末态 `blocked`；角色终止：provider=completed；implementer=model_budget_exhausted。

#18 请求、#30 未绑定请求的交接均记录，随后采用 data 和 basis；#127 写 code。#140 的 sql_build 外层 ok=true，但内层 execution_status=execution_error：引用 data.customers，执行器没有 data schema。未产生原判定认可的正确构建，也没有 submit 动作；结束于 implementer 固定决定轮次上限。后续读取/采用代码不构成执行修复。

原分项：`applicable_basis_delivered`=达成（0.2/0.2）；`delivered_basis_used_in_build`=未达成（0.0/0.3）；`correct_fixed_delivery`=未达成（0.0/0.5）。

复核：[原评价](../../runs/domain-v025-r2/confirm_base/actual/confirm-00-1/assessment.json) · [原时间线](../../runs/domain-v025-r2/confirm_base/actual/confirm-00-1/runtime.json) · [终态世界](../../runs/domain-v025-r2/confirm_base/actual/confirm-00-1/episode/end/control/state.json) · [情境与冻结合同](../../runs/domain-v025-r2/confirm_base/actual/confirm-00-1/episode/manifest.json)。关键事件：#18、#30、#90、#103、#127、#140、#201、#227。

<a id="confirm-02-1"></a>

### confirm-02-1：B：正确初稿经独立核准，完成职责

情境 `retail-v25-ecbc95c34ed0941e`；seed `202610022021`；原 R=1.0；完整职责=是。末态 `accepted`；角色终止：reviewer=model_budget_exhausted；implementer=model_budget_exhausted。

本例继承 correct 初稿。reviewer 在 #18 inspect 固定提交，#41 读 data v1、#64 读 audit_basis v1、#87 读 code v2、#110 读 result v2，#133 approve 工具成功且原独立评价 valid=true。固定结果为 14088：50220 pence / 2，17230：21830 pence / 2；终态 accepted，仍是 submission-1。原 final_fixed_build.current_actor_build=false，current_correct_build/current_repair_build 均为空，不能称新修复成功。值得保留的负面事实：implementer 随后在 #145 声称客户 17230 的金额应为 19490，尝试 withdraw；工具以 Work is not awaiting review 拒绝，未改变已核准交付。这说明完整职责终局达成并不代表每个后续判断都正确。两角色最终因上下文上限停止，仍保留 R=1 的业务判定。

原分项：`independent_final_review`=达成（0.4/0.4）；`correct_fixed_final_product`=达成（0.3/0.3）；`valid_review_and_repair_path`=达成（0.3/0.3）。

复核：[原评价](../../runs/domain-v025-r2/confirm_base/actual/confirm-02-1/assessment.json) · [原时间线](../../runs/domain-v025-r2/confirm_base/actual/confirm-02-1/runtime.json) · [终态世界](../../runs/domain-v025-r2/confirm_base/actual/confirm-02-1/episode/end/control/state.json) · [情境与冻结合同](../../runs/domain-v025-r2/confirm_base/actual/confirm-02-1/episode/manifest.json)。关键事件：#18、#30、#41、#53、#64、#76、#87、#99、#110、#122、#133、#145。

<a id="confirm-04-1"></a>

### confirm-04-1：维护：已采用新政策，未重建亦未正式判断

情境 `retail-v25-8af50a90ebc7148d`；seed `202610022041`；原 R=0.0；完整职责=否。末态 `in_review`；角色终止：implementer=model_budget_exhausted；reviewer=model_budget_exhausted。

与 confirm-04-0 同一需变更材料、不同采样 seed。implementer #76 采用 basis v2，双方多次读取精确版本，但没有 code 写入、重建、撤回或提交；reviewer 也没有成功的 approve/raise_issue。implementer #191 最后读取 data 后下一请求即受上下文限制，原 implementer_current_inspection=false，不能把“工具已返回”直接当作“后续推理已收到”。两角色因上下文上限停止，原三项职责均为 false。

原分项：`independent_current_policy_review`=未达成（0.0/0.4）；`correct_current_policy_fixed_product`=未达成（0.0/0.3）；`valid_maintenance_response`=未达成（0.0/0.3）。

复核：[原评价](../../runs/domain-v025-r2/confirm_base/actual/confirm-04-1/assessment.json) · [原时间线](../../runs/domain-v025-r2/confirm_base/actual/confirm-04-1/runtime.json) · [终态世界](../../runs/domain-v025-r2/confirm_base/actual/confirm-04-1/episode/end/control/state.json) · [情境与冻结合同](../../runs/domain-v025-r2/confirm_base/actual/confirm-04-1/episode/manifest.json)。关键事件：#8、#18、#53、#64、#76、#87、#99、#122、#145、#156、#168、#179、#191。

<a id="confirm-01-1"></a>

### confirm-01-1：A：先交接被拒，再构建与代码格式失效

情境 `retail-v25-ac454ec3588acd62`；seed `202610022011`；原 R=0.2；完整职责=否。末态 `blocked`；角色终止：provider=model_budget_exhausted；implementer=model_budget_exhausted。

provider #8 未读取证据就交接，被工具拒绝；#30 读取后在 #53 成功交接。implementer #148/#161 采用 data/basis，#174 执行初始代码，外层和 SQL 执行均成功，但原评价没有 current_correct_build；该工具输出不能当成内容正确性证明。#235 改写 code 后，#248 的 sql_build 外层 ok=true、内层 execution_error，原因 Code declares only models/tests/config。没有 submit；两角色最终达到各自决定轮次上限。

原分项：`applicable_basis_delivered`=达成（0.2/0.2）；`delivered_basis_used_in_build`=未达成（0.0/0.3）；`correct_fixed_delivery`=未达成（0.0/0.5）。

复核：[原评价](../../runs/domain-v025-r2/confirm_base/actual/confirm-01-1/assessment.json) · [原时间线](../../runs/domain-v025-r2/confirm_base/actual/confirm-01-1/runtime.json) · [终态世界](../../runs/domain-v025-r2/confirm_base/actual/confirm-01-1/episode/end/control/state.json) · [情境与冻结合同](../../runs/domain-v025-r2/confirm_base/actual/confirm-01-1/episode/manifest.json)。关键事件：#8、#30、#41、#53、#148、#161、#174、#235、#248。

<a id="confirm-03-1"></a>

### confirm-03-1：B：错误初稿重跑后撤回，没有有效复核

情境 `retail-v25-0a00faea6532187f`；seed `202610022031`；原 R=0.0；完整职责=否。末态 `in_progress`；角色终止：reviewer=model_budget_exhausted；implementer=model_budget_exhausted。

双方读取固定初稿；reviewer 访问 basis、implementer 访问 audit_basis 分别被拒。#145 执行现有代码，返回两客户 14110/15189 的 invoice_count 仍为 3；外层 ok=true 且唯一性测试通过，但原评价没有正确构建。#167 submit 在旧提交未撤回时被拒，#185 才 withdraw；没有之后的新构建或固定提交。reviewer 未发出成功 approve/raise_issue，两角色最终均因上下文上限停止。原 repair_path 字符串虽含 independent_review，也不能视为已发生最终复核。

原分项：`independent_final_review`=未达成（0.0/0.4）；`correct_fixed_final_product`=未达成（0.0/0.3）；`valid_review_and_repair_path`=未达成（0.0/0.3）。

复核：[原评价](../../runs/domain-v025-r2/confirm_base/actual/confirm-03-1/assessment.json) · [原时间线](../../runs/domain-v025-r2/confirm_base/actual/confirm-03-1/runtime.json) · [终态世界](../../runs/domain-v025-r2/confirm_base/actual/confirm-03-1/episode/end/control/state.json) · [情境与冻结合同](../../runs/domain-v025-r2/confirm_base/actual/confirm-03-1/episode/manifest.json)。关键事件：#18、#41、#64、#87、#99、#110、#133、#145、#167、#185。

<a id="confirm-05-1"></a>

### confirm-05-1：维护：核查新政策并保留原正确数值，完成职责

情境 `retail-v25-db6ed5a08bcdcc1f`；seed `202610022051`；原 R=1.0；完整职责=是。末态 `accepted`；角色终止：implementer=model_budget_exhausted；reviewer=model_budget_exhausted。

implementer #30 inspect，#53 读 basis v2、#76 读 data v1、#99/#122 读旧固定 code/result v2；原评价 implementer_current_inspection=true。reviewer 在两次 basis 越权读取被拒后，#87/#133 读 audit_basis v2、#110 读 data、#156/#175 读 code/result，#188 approve 工具成功且 valid=true。固定结果为 13777：43758 pence / 2，16626：20310 pence / 2；终态 accepted，保留 submission-1。actual_result_change_required=false，无 write_object/sql_build/submit/withdraw 成功变更，原 current_repair_build=null。这是有证据的无须改数值维护，不是新修复；implementer #145 对未声明输出 alias verify_sales 的 sql_query 被拒亦保留。

原分项：`independent_current_policy_review`=达成（0.4/0.4）；`correct_current_policy_fixed_product`=达成（0.3/0.3）；`valid_maintenance_response`=达成（0.3/0.3）。

复核：[原评价](../../runs/domain-v025-r2/confirm_base/actual/confirm-05-1/assessment.json) · [原时间线](../../runs/domain-v025-r2/confirm_base/actual/confirm-05-1/runtime.json) · [终态世界](../../runs/domain-v025-r2/confirm_base/actual/confirm-05-1/episode/end/control/state.json) · [情境与冻结合同](../../runs/domain-v025-r2/confirm_base/actual/confirm-05-1/episode/manifest.json)。关键事件：#8、#18、#30、#41、#53、#64、#76、#87、#99、#110、#122、#133、#145、#156、#175、#188。

<a id="continue-00-0"></a>

### continue-00-0：后继 A：预检通过，交接请求未闭合且提交失败

情境 `retail-v25-a51f035b4df2514b`；seed `202610023000`；原 R=0.2；完整职责=否。末态 `blocked`；角色终止：provider=model_budget_exhausted；implementer=model_budget_exhausted。

provider #8 反向请求依据被拒；#30 读取后 #53 合法交接，但未绑定 implementer #41 的 mail-1。implementer #111/#134 采用依据和数据，#176 sql_build 执行成功，#189 preflight_submission 返回 structurally_ready=true。预检明确只检查文件/引用/依赖结构、不评价业务值，原 current_correct_build=null。#215/#267 submit 均被拒，#202 把 pending 当实际提交 ID，#241 把 condition-mail-1 当 issue，亦被拒；终态 mail-1 pending、工作 blocked、无提交。此例不能把预检成功写为业务正确或完整交付。

原分项：`applicable_basis_delivered`=达成（0.2/0.2）；`delivered_basis_used_in_build`=未达成（0.0/0.3）；`correct_fixed_delivery`=未达成（0.0/0.5）。

复核：[原评价](../../runs/domain-v025-r2/next_base/actual/collection/continue-00-0/projection.json) · [原时间线](../../runs/domain-v025-r2/next_base/actual/collection/continue-00-0/runtime.json) · [终态世界](../../runs/domain-v025-r2/next_base/actual/collection/continue-00-0/episode/end/control/state.json) · [情境与冻结合同](../../runs/domain-v025-r2/next_base/actual/collection/continue-00-0/episode/manifest.json)。关键事件：#8、#30、#41、#53、#111、#134、#163、#176、#189、#202、#215、#228、#241、#267。

<a id="continue-01-0"></a>

### continue-01-0：后继 B：问题与代码修改未形成有效修复

情境 `retail-v25-5dd3be535c71bffe`；seed `202610023010`；原 R=0.0；完整职责=否。末态 `in_review`；角色终止：implementer=model_budget_exhausted；reviewer=model_budget_exhausted。

初稿为 wrong_count。reviewer #110 raise_issue 工具成功，但原评价 valid=false、read_evidence=null；其此前读取 result/audit/data，却没有读取固定 code。问题文字还声称 invoice_count 应为“1 distinct InvoiceNo + 1”，这只是模型原话，不能当正确标准。implementer #145 改 code：新增 SELECT DISTINCT r.*，且 COUNT(DISTINCT InvoiceNo)+1 仍保留，随后因上下文上限停止，没有 build 或固定新提交。reviewer #133/#156/#175 用未对应实际问题响应的 response_id 执行 decide_issue 均被拒；无有效 issue 响应和最终 approve。原 R=0，不把改了文件等同修复成功。

原分项：`independent_final_review`=未达成（0.0/0.4）；`correct_fixed_final_product`=未达成（0.0/0.3）；`valid_review_and_repair_path`=未达成（0.0/0.3）。

复核：[原评价](../../runs/domain-v025-r2/next_base/actual/collection/continue-01-0/projection.json) · [原时间线](../../runs/domain-v025-r2/next_base/actual/collection/continue-01-0/runtime.json) · [终态世界](../../runs/domain-v025-r2/next_base/actual/collection/continue-01-0/episode/end/control/state.json) · [情境与冻结合同](../../runs/domain-v025-r2/next_base/actual/collection/continue-01-0/episode/manifest.json)。关键事件：#18、#41、#53、#64、#76、#87、#99、#110、#122、#133、#145、#156、#175、#212。

## 对后续实验的有限启示

以下是基于本批轨迹的设计建议，不是已经验证的改进结论。可以优先区分三种可观察闭合要求：请求交接是否带回原 request_id 并解除 pending 条件；修订代码后是否实际构建、固定提交和复核；每个角色是否在作判断前由成功后续请求消费其应读证据。当前记录已经能指出这些具体断点，下一实验若修改界面提示、上下文策略或终止规则，应另起条件、保留冻结对照，不能将本轮事后修订后的分数倒填为原结果。

本报告只汇编原事实。`repair_path` 为路径分支描述，必须与分项布尔值、实际构建/提交/复核事件共同阅读；`current_repair_build=null`、无固定提交、或缺最终有效 approve 时，都不能仅凭路径名称宣称闭环完成。维护的 `implementer_current_inspection` 还要求工具返回进入该角色后续成功请求：有读取工具调用但下一次请求在上下文门前停止时，不能认定该返回已被实际消费。该语义来自 [v0.25 既有评分实现](../../src/proworksim/templates/retail_collaboration_v025.py)，本次没有改变或重跑此判定。
