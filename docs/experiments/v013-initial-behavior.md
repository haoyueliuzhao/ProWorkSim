# v0.13 初始 O2：八段实际行为的只读诊断

本批呈现的是**局部交接已能完成，SQL 业务实现、来源采用和有据复核仍有明确缺口，同时准备后的工具返回体积会提前耗尽上下文**。不能由 `R=0` 推断“不会执行 SQL”：两个实现短段都真正完成了 DuckDB build 和固定提交；也不能将一次 `approve` 当成有据复核成功。

范围为 `runs/online-eval-v013-initial-r1` 的初始 actor 冻结评测。运行源码 `aa1102eac72dc75be8801298cccf058fbb3a3c0b`，起止 clean、source tree 相同；actor adapter SHA256 为 `3af882e8ac653fb5c59fdc47d0fe0e43fda5d45e4499f9e4ebdd558fce0f2a78`。两窗均保存 `evaluation_only_no_learning_computation`，actor/critic step 为 0、无训练概率重算。这是训练前行为基线，不用于判断后续学习效果。8 段为一个合成开发家族内预先锁定的事实变体，不是独立来源泛化。

证据为原始 episode/experience、preparation、team-rollout 和真实 model_attempt.request/response。本次仅读取和计数，没有调用模型、SQL、奖励或 V 评估器。下文事件号均为相应 `experience.json` 的 `sequence`。原 V 标签原样保留；其中上下文停止导致的旧 `record=null` 判定由另一项修订处理，这里不静默替换。

## 实际结果与工具边界

| 段 | 实际生成 / 直接尝试 | 工具成功 / 拒绝 | 关键工作事实 | 原 R / V |
|---|---:|---:|---|---|
| w0 handoff | 4 / 4 | 2 / 0 | read_alias 1、正确 handoff 1 | 1 / true |
| w0 implement | 4 / 5 | 4 / 0 | read_alias、write_object、sql_build、submit 各 1；build success | 0 / false（record=null） |
| w0 review | 5 / 6 | 3 / 2 | read_version、inspect、approve 成功；handoff、decide_issue 被拒绝 | 0 / false（record=null） |
| w0 chain | 18 / 18 | 10 / 8 | 有正确交接；2 次 build 均执行前拒绝；无提交 | .2 / false |
| w1 handoff | 4 / 4 | 2 / 0 | read_alias 1、正确 handoff 1 | 1 / true |
| w1 implement | 4 / 5 | 4 / 0 | read_alias、write_object、sql_build、submit 各 1；build success | 0 / false（record=null） |
| w1 review | 4 / 5 | 3 / 1 | read_version 1、inspect 2；handoff 被拒绝；无批准/有效 issue | 0 / false（record=null） |
| w1 chain | 18 / 18 | 11 / 7 | 有正确交接；5 次 build 均执行前拒绝；无提交 | .2 / false |

合计 **65 次 resident direct 尝试、61 次真实生成、0 次网络 HTTP**；57 次世界工具调用中 39 次 `ok=true`、18 次拒绝。另有 3 次 wait、1 次 done，它们属于真实生成，但不是世界工具动作。61 次生成报告 315,568 prompt tokens、3,867 output tokens，共 **319,435 tokens**。另外 4 次为明确未开始生成的 context400；框架原记录的 missing-usage/charged reservation 不能当成额外已生成 tokens。

两个 handoff 的读取和交接分别位于事件 8、20，均为当前 actor 的真实动作；对应 episode 为 `77681770-2236-4ce9-ad09-b674bfa4ef2b`、`4f536088-c039-4d6a-a3cf-bdaea3ba4310`。[w0 交接事件][E00]、[w1 交接事件][E10]

chain 的具体工具计数为：w0 读取成功 5、request 成功 1/拒绝 4、adopt 成功 1、handoff 成功 2/拒绝 1、write 成功 1、build 拒绝 2、inspect 拒绝 1；w1 读取成功 8、request 成功 1/拒绝 2、adopt 成功 1、handoff 成功 1、build 拒绝 5。`read`、`adopt`、执行成功、业务正确和审阅依据是不同事实。

## SQL 实现：执行通路成功，业务修改与当前证据读取不足

两个 implement 短段均已有真实准备交接与 data/basis adoption，当前 actor 仍需自己读取确切输入并实现业务 SQL。实际顺序同为 `8 read_alias(data) → 20 write_object(result) → 32 sql_build → 44 submit`；没有当前读取 basis，也没有写入 code。提交固定的是 **code v1、result v3**，不是手写 result v2。[w0 实现事件][E01]、[w1 实现事件][E11]与各自 [准备记录][P01]、[准备记录][P11]可复核。

`sql_build` 返回 `execution_status=success`，可编辑的 `unique_customer` 测试通过。实际输出分别是 `[(1,1600,2),(2,1500,2),(3,2000,2)]` 与 `[(1,800,2),(2,2000,2),(3,1700,2)]`；调用分别为 `model-1c262cc19ef03740c6c5076e`、`model-4599f10d68f60ea9985fe4b2`。这证明执行器跑过真实 SQL，不能归类为 SQL 工具故障。

起始 code v1 按 transactions 全量汇总、`COUNT(*)`，没有按已批准 basis 筛选期间/状态、应用 amount_factor 或按 order_id 去重。两个 implement 的已准备 basis 都要求倍数 2，且客户 3 的记录分别属于 pending 当期或 completed 次期；实际输出仍给客户 3 非零值。这里的业务缺口是对公开材料的只读核对，不是补跑评分。原奖励中 `read_exact_inputs`、`correct_actual_build`、`correct_fixed_submission` 三项均为 false；原 R 保持 0。手写 result 后再 build 的动作真实存在，但不能代替修改 SQL，也不能用结构测试通过代替独立业务结果。

## 复核：读取旧版本、遗漏依据与无效流程引用

w0/w1 review 的初始固定提交都是 code v2、result v2；两名当前 reviewer 的第一个动作却是事件 8 读取 **code v1**。事件 20 的 `inspect_submission` 已返回固定版本映射，但此后没有读取该固定 code/result，也未读取 data 和适用 audit_basis。[w0 复核事件][E02]、[w1 复核事件][E12]保存了这一差异。

w0 准备段确实 build 并提交了正确 SQL（准备 build 事件 8，结果 `[(1,2300,1),(2,400,1),(3,0,0)]`）；当前 reviewer 事件 32 误用 basis route 被拒绝，44 又引用不存在的 issue/response 被拒绝，56 最终真实批准成功，调用为 `model-38663e53def6a2a269b030f3`。**批准对象碰巧正确，但批准前证据义务未完成**，所以原独立 review 奖励仍为 0。[w0 准备记录][P02]

w1 准备的真实 SQL 使用 `COUNT(order_id)` 而非 `COUNT(DISTINCT order_id)`，客户 1 输出 `(1100,2)`，该数据中重复行属于同一个 order_id。当前 reviewer 事件 32 误用 basis route 被拒绝，44 只重复 inspect；没有报告该真实错误位置，也没有批准，之后遇到 context400。这里同时存在未完成复核义务和实际服务边界，不能把终止后的潜在行为补成一次错误批准或成功纠错。[w1 准备记录][P12]

## 完整链：交接有效，但未把收到资料转成精确采用

两条链都在事件 74 由 provider 成功交接适用 basis，原奖励各得到 .2。implementer 采用了 data，但没有采用 basis；因此所有 build 均返回 `SQL input requires this work's exact adoption: basis`，属于**执行前拒绝**，不是 DuckDB 执行错误。[w0 链事件][E03]、[w1 链事件][E13]

w0 build 拒绝在 120、172；actor 在 213 才读取 basis，随后预算结束，未发生 basis adoption、成功 build 或提交。w1 在事件 86 首次被拒后，于 120 成功读取 basis，却仍未 adopt；147、171、195、212 继续同参数 build 被拒绝。两个 reviewer 读取了尚未成为提交的 result v1；w0 事件 159 还以 `TEAM::build::result` 充当 submission_id 被拒。两个 chain 都没有真实提交，也没有可算作完整链完成的复核。

角色路由也存在混淆：provider 向自己持有的 basis route 发 request 被拒，其他角色向不属于其接收范围的 audit_basis route 发 request 被拒。正确交接与这些失败同时保留，不能只按链的低奖励抹掉前者。

## 拒绝反馈实际进入后续输入，但不总转成修复

以“同一成员下一次真实返回的生成”为边界，18 次工具拒绝中，15 次有后续生成，且对应的原 `model_tool_result.message` 均确实在该生成的 `model_attempt.request.messages` 内；其余 3 次无后续生成，不能记作忽略反馈。15 次中 12 次换工具，3 次同工具同参数，**0 次同工具改参数**。换工具仅表示行为变化，不自动等于完成修复。

可复核例子：

- w0 review：拒绝 32 → `model-62b46096fbe4873675fafa63` / 44 decide_issue（仍拒绝）；拒绝 44 → `model-38663e53def6a2a269b030f3` / 56 approve。两次均真实看到反馈，但后一动作仍缺审阅依据。
- w0 chain：build 拒绝 120 → `model-c79a0d01f6785e7bee373779` / 148 request（拒绝）；再到 172 重用原 build 参数。下一步换工具并未解决缺 adoption。
- w1 chain：147 → `model-81c51347c3a807f2967f1c59` / 171；171 → `model-529a98e68bd3cb35e8daf35a` / 195；195 → `model-76f07b0e9b44171924eacc97` / 212，均是**已见明确错误后的同参数 build 重试**。事件 212 无下一生成。

这里只判断实际请求是否包含反馈，不声称能读取模型内部是否理解反馈。

## 上下文终止与准备后的可见体积

4 个 context400 全部保存 `generation_started=false`、请求输出 512、context_limit 8192；服务明确拒绝整段输入且没有裁剪。本地 direct 的响应仍使用 `http_status:400` 字段，**这不代表发生网络 HTTP**。

| 段 | 停止事件 / call_id | 已分词 prompt + 请求输出 | 停止前已发生工作 |
|---|---|---:|---|
| w0 implement | 52 / `model-fdbee240d4cd23a39a5c1114` | 7851 + 512 | 已真实 build、submit |
| w1 implement | 52 / `model-53e4fa032bfe34a3093b920e` | 7852 + 512 | 已真实 build、submit |
| w0 review | 64 / `model-dba75d598e68d9596d6f4309` | 8249 + 512 | 已真实 approve，但依据不全 |
| w1 review | 52 / `model-41cb028b960d58e2a88b7812` | 8109 + 512 | 已两次 inspect，无有效复核决定 |

两个 chain 没有 context400，是各角色用完声明决策预算；w1 handoff 虽未主动 done，也已取得交接奖励 1。这些终止种类不能仅从统称 `model_budget_exhausted` 推断。

准备段事件数按 handoff/implement/review/chain 为 **0/7/10/0**，两个窗口相同；其中 implement 为 6 次准备工具动作加 1 次环境事件，review 再加真实 code 写入/build/submit。它们没有进入当前 actor 经验区间（各 episode 初始经验事件数 0），没有被计成当前 actor 动作或 token。观察到的体积差如下，prompt tokens 来自实际响应，未重新 tokenize：

| 角色/范围 | w0 首次 prompt tokens | w1 首次 prompt tokens |
|---|---:|---:|
| provider / handoff，未执行准备动作 | 3396 | 3398 |
| implementer / 已准备 implement | 4940 | 4945 |
| reviewer / 已准备 review | 4363 | 4360 |
| implementer / chain，首次轮到本角色 | 4399 | 4405 |
| reviewer / chain，首次轮到本角色 | 4344 | 4259 |

implement 相对同角色 chain 的首次输入多 541/540 tokens；review 多 19/101 tokens。**这只是观测差，不是准备前缀的因果消融**：任务合同、工具集合、当前世界状态和首次轮到该角色前的同事动作也不同。准备越多并不必然使所有角色首轮输入等比例增长。

更直接的增量来自当前真实返回：implement 的 submit 对应 `model_tool_result` 事件 49，保存消息 JSON 长度均为 6185 字符，之后 prompt 由 6258/6260 升到 7851/7852；review 的 inspect 返回事件 25 长 6066 字符，w0 approve 返回事件 61 长 6147 字符，w1 第二次 inspect 返回事件 49 再长 6066 字符。JSON 字符长度采用 `json.dumps(message, ensure_ascii=False)`，不是 token 数。这些返回包括固定提交合同/版本快照，和真实上下文增长相邻出现，支持将**必要业务返回的呈现体积**列为后续可测改进方向；本诊断没有删除原返回、重新运行或追认未来修复收益。

## 可据此表述的边界

已观察到确切证据读取与合法交接、真实 SQL 执行、固定提交、机构批准，以及获得真实错误后仍重复无效参数。主要未完成项集中在：使用当前适用依据修改 SQL、把通信所得资料转成工作采用、读取固定提交的正确版本、以及在有限上下文内完成审阅义务。该结论仅针对这 8 段；不推出模型一般 SQL 能力、训练无效或独立来源泛化结论。后续训练评测必须保持本批原始结果与服务停止记录可见。

原始索引：每个段目录同时保存 `episode/manifest.json`（episode_id、边界）、`episode/experience.json`（事件与实际模型输入/返回）、`preparation.json`、`public-capture.json` 与 `team-rollout.json`（原奖励和 V）。下列链接指向原文件，不是重新生成的轨迹。

[E00]: ../../runs/online-eval-v013-initial-r1/online/window-0/collection/slot-0/episode/experience.json
[E01]: ../../runs/online-eval-v013-initial-r1/online/window-0/collection/slot-1/episode/experience.json
[E02]: ../../runs/online-eval-v013-initial-r1/online/window-0/collection/slot-2/episode/experience.json
[E03]: ../../runs/online-eval-v013-initial-r1/online/window-0/collection/slot-3/episode/experience.json
[E10]: ../../runs/online-eval-v013-initial-r1/online/window-1/collection/slot-0/episode/experience.json
[E11]: ../../runs/online-eval-v013-initial-r1/online/window-1/collection/slot-1/episode/experience.json
[E12]: ../../runs/online-eval-v013-initial-r1/online/window-1/collection/slot-2/episode/experience.json
[E13]: ../../runs/online-eval-v013-initial-r1/online/window-1/collection/slot-3/episode/experience.json
[P01]: ../../runs/online-eval-v013-initial-r1/online/window-0/collection/slot-1/preparation.json
[P11]: ../../runs/online-eval-v013-initial-r1/online/window-1/collection/slot-1/preparation.json
[P02]: ../../runs/online-eval-v013-initial-r1/online/window-0/collection/slot-2/preparation.json
[P12]: ../../runs/online-eval-v013-initial-r1/online/window-1/collection/slot-2/preparation.json
