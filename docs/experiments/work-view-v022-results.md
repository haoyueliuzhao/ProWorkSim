# v0.22 W1：原历史与紧凑工作视图的真实比较

**12 个预定 episode 全部关闭，两臂完整职责完成数均为 0。**紧凑臂增加了实际生成和工具动作，部分终止由上下文不足移到了原定决策上限，但本次没有观察到正确构建、有据复核或联合 A/B 责任闭合改善。不能把更多动作、个别轨迹较短或少两次上下文拒绝解释为工作能力提升。

本报告保留全部原分数，另按启动前声明计算只读中间产物里程碑。机器记录为 [work-view-v022-results.json](work-view-v022-results.json)，来源、合同和 CPU 准备见 [work-view-v022-preflight.md](work-view-v022-preflight.md)。没有重新生成模型轨迹、执行 SQL、修复原 episode 或改写终态评分。

## 1. 执行边界与可比较性

执行源 `db0cb293dc243ccdeefb23ba0d1f1599b9ab50e3`，固定源码保存在 `runs/frozen-v022-w1/`，真实输出在 `runs/domain-v022/W1/actual/`。六个情境使用新选的同源 UCI 客户／完整发票，非旧 f0/f1/f2 换名。两个呈现臂共同使用新的公开 result target、零基 locator 与 data/audit 精确引用合同，以及当前固定材料结果表职责。

每对实际采样种子一致，准备后业务状态 hash 一致，原/紧凑顺序按 case index 奇偶交错。角色机会、模型、工具、16,384 总长度和 2,048 输出上限没有临时放大。每次完整 prompt 还须为输出留出 2,048 token，因此输入准入上限是 14,336 token。监督使用物理 GPU 3，完整进程区间 **2,066.3955 秒**，exit code 0；这包含加载和工作执行开销，不是纯生成时间。

所有 12 例学习状态不变、RNG 按原协议恢复；初末 actor identity 相同、source 不变。actor/critic 参数未更新，网络模型 API 调用为 0，但有下表所列的真实本地模型生成。所有原评分均为 known、eligible，没有丢弃低分或改成未知，也没有未开始案例。

## 2. 原分数和实际断点

O 表示 `original_history`，C 表示 `compact_work`。分数只适用于各自冻结责任，不是任务通用能力百分比。

| 情境 | O 原分数 | C 原分数 | O 实际断点 | C 实际断点 |
|---|---:|---:|---|---|
| 新实现 0 | 0 | 0 | 运行初始错误 SQL 后写 code v2；尚未重建即上下文拒绝 | 编辑后用 `data.customers` 限定名导致真实 SQL CatalogException；最终用尽决策 |
| 新实现 1 | 0 | 0 | 一次多调用格式拒绝、一次 build 参数错误；仅执行初始 SQL，后续截断／上下文拒绝 | 执行并正式提交了初始错误 SQL 结果，随后上下文拒绝 |
| 正确初稿复核 | 0 | 0 | inspect 后读 result/data/audit，未读代码或作出判断 | 实际批准了正确初稿，但未读固定代码；批准不满足证据合同 |
| 错计数初稿复核 | 0.25 | 0 | 完成 inspect 和 code/result/data/audit 读取，尚未 issue 即上下文拒绝 | 完成部分读取后尝试未知 object_id；未读代码、未作判断 |
| 联合 A | 0.2 | 0.2 | 实际交接和采用成立；新 SQL 内容仍错，另有未解决请求阻断提交 | 实际交接成立；多次 route/采用错误后执行未改初始 SQL，请求仍阻断提交，最后用尽决策 |
| 联合 B | 0 | 0 | 只发生 inspect 和读取，含一次未知对象拒绝；无修复或正式复核 | 只发生 inspect 和读取，含复核者一次越权读取；无修复或正式复核 |

这张表不能与 v0.21 E 的六例做直接初末能力比较：W1 材料和公开合同都改变了，模型参数没有更新。尤其不能据新实现例的 0 分否定旧固定实例中确实发生过的正确交付。

### 单岗位：动作推进不等于业务闭合

紧凑臂的新实现 1（slot 2）实际调用了 submit，固定 code v1 与 result v2。独立内容仍错，原评分保持 0。它是“真实提交发生”的证据，不能当作“正确交付发生”。

紧凑臂正确初稿复核（slot 5）在 experience sequence 68 实际 approve；其前只读了 result/data/audit，且一条拼错的对象引用被拒，没有读取固定 code v2。因此有据判断谓词不成立。正确产品属于真实准备前缀，记录中的 `current_actor_build=False` 保留，未计为本轮模型实现功劳。

错计数原臂（slot 7）的 0.25 只对应完成必要读取，终止前没有 issue/approve。本例没有重现旧 E 中“正确指出 +1 但定位合同表达不足”的那条行为；新版定位规则已在共同公开合同中明确，不能用旧问题替代本次实际断点解释。

### 联合 A：请求关系与业务内容分别失败

原历史臂 provider 在 sequence 30 主动送达 basis；implementer 在 sequence 42 **随后**发起新请求 mail-2。该新请求仍 pending，work 为 blocked，sequence 155 的 submit 被真实拒绝。与此同时，模型确实修改了 SQL、做了新 build，但仍遗漏 7 月 1 日截止过滤，独立内容谓词为 false。因此它同时存在产品错误与正式请求未闭合，不能只归因为提交被挡住。

紧凑臂 implementer 先请求 mail-1，provider 后续 handoff 未填写对应 request_id。依据虽实际送达，正式请求没有被关联解决；之后又发生不存在的 data route 交接、错误 audit route 请求、漏采用 basis 导致 build 拒绝。补采用后执行的仍是未修改初始 SQL，业务错误。两次 submit 均因请求状态被拒，末尾又建立新 basis 请求 mail-3。该臂用完 implementer 的 16 次决策，没有上下文 400，但责任没有闭合。

两臂 0.2 对应真实交接，不能翻译成“只有一条消息”；也不能把读入、采用和一次成功执行自动翻译为正确使用业务依据。原始 handoff 均没有合法请求关联，Mapper 的 `requested=False` 不会仅因出现过请求就改成 true。

### 联合 B：尚未到修复

两臂都从真实、排除计功的错金额固定初稿开始。紧凑臂 11 次 world 调用、原历史臂 10 次，均限于 inspect、读取及读取拒绝；没有 withdraw、write、build、submit、issue 或 approve。两角色分别到达各自上下文边界。

原评分中的 `features.repair_path` 是评分器检查的候选分支名，`class_id=null`、`eligible=false`；本轮不能据这个字符串声称自检修复或独立复核已经发生。

## 3. 预声明里程碑：检查所有中间版本

新增只读报告器 [report_work_view_v022.py](../../scripts/report_work_view_v022.py) 在冻结 `db0cb29` 的 `PYTHONPATH` 下运行，核对闭合开始/终态文件及原命令回执。它逐个检查**当前 episode 的实际 sql_build 结果版本**，使用原 Decimal 内容谓词和该产物自己的准确 source 引用，选取最早通过者；没有以末次构建或最终分数替代“首次”。准备期 build/submit 排除。

每个里程碑保存 experience sequence、world action ID／逻辑时间、真实 model_call_id、对应角色已消耗 decision_index、剩余原定决策和此前实际生成次数。末次纯预算 flush 不计新生成。

| slot／条件 | 首次正确 build | 首次实际固定 submit | 首次正确固定 submit | 首次有据正式判断 |
|---|---|---|---|---|
| 0／实现0 O | null | null | null | null |
| 1／实现0 C | null | null | null | null |
| 2／实现1 C | null | seq 80；action-20；逻辑时刻 20 | null | null |
| 3／实现1 O | null | null | null | null |
| 4／正确复核 O | null | null | null | null |
| 5／正确复核 C | null | null | null | null |
| 6／错计数复核 C | null | null | null | null |
| 7／错计数复核 O | null | null | null | null |
| 8／A O | null | null | null | null |
| 9／A C | null | null | null | null |
| 10／B C | null | null | null | null |
| 11／B O | null | null | null | null |

唯一实际 submit（slot 2）发生在 implementer 第 **7** 次模型决策，原 cap 12、剩 **5**，此前实际生成 **7** 次；固定 code v1/result v2 的内容判为错误。slot 5 虽实际批准，却不是有据判断，所以相应里程碑为 null。null 表示该已知闭合历史中未发生符合条件的事件，不表示评分未知。

全部逐次构建诊断、提交与正式判断记录见 `runs/domain-v022/W1/milestones-final.json`，亦嵌入机器归档。该项是预声明的 **CPU 后验固定指标**，不是新增模型样本、SQL执行或原分数重算。

## 4. 模型请求、终止和成本

| 指标 | 原历史 O | 紧凑 C |
|---|---:|---:|
| 实际 episode | 6 | 6 |
| 完整职责完成 | 0 | 0 |
| resident 请求尝试 | 59 | 70 |
| 真实生成 | 52 | 65 |
| 生成前本地上下文 400 | 7 | 5 |
| world 工具调用／其中拒绝 | 45／5 | 60／9 |
| 格式反馈 | 6 | 4 |
| 实际累计输入 token | 516,768 | 621,247 |
| 实际累计输出 token | 22,656 | 18,395 |
| 各 episode 时段之和，秒 | 1,092.041 | 934.692 |

原臂格式反馈为 5 次输出达到上限、1 次多工具调用；紧凑臂为 2 次输出达到上限、2 次 JSON 解析失败。所有原输出、真实拒绝和后续动作保留。上下文 400 来自同步 resident 适配器的长度准入，未产生模型输出，不是远程 HTTP 服务故障。

有上下文终止的 episode 为 O 6/6、C 4/6；B 的两角色可分别产生一次 400，不能把请求数直接当 episode 数。C 的 slot 1 和 slot 9 用满决策后各有一次不生成的尾部 flush；这两次不在 117 次真实生成中，也不是额外模型样本。机会在格式失败或本地拒绝时可被消耗，故报告将“角色 decision_index”和“实际生成次数”分开。

紧凑臂累计输入反而更多，因为实际生成次数和走过的轨迹改变了。两臂执行时段也包含不同输出长度和动作路径，不能把时段差称为固定工作负载吞吐提升。这个小型开发比较没有显示责任闭合收益，亦不足以估计一般效应或作显著性判断。

## 5. 结论边界与后继

本次支持两个有限事实：明确公开定位合同已经落到实际输入；确定性视图能改变可执行轨迹和终止位置，但这组预定新实例中没有带来完整实现、有据复核或 A/B 闭合。读取、采用、精确对象引用、请求应答关联、正确 SQL 和固定交付仍是不同条件，不能用其中一个替代其余条件。

应保留原分数和实际行为，不因结果不理想补采或延长。若后续修改观察组织、工具语法说明、正式请求使用规则或预算，须另冻 Γ，不能回填本轮。条件 B1 的短训练片段另有预算、真实 token 投影和学习资格，它与 W1 的完整职责比较分开；任何一次参数更新也不能由本轮结果自动推出学习收益。

主要证据的原路径与 SHA 已收录在 [机器归档](work-view-v022-results.json)：原 `actual/report.json`、`progress.json`、12 份 `assessment.json`、固定 episode，以及新增只读里程碑报告。初末身份／source 守卫和每例学习／RNG 守卫全部通过，原终态文件均未修改。
