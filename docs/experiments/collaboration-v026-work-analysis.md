# v0.26 C1 真实模型业务与协作轨迹附录

本附录读取 R2 原实验、R3 恢复实验和既有评分归档，不重新运行模型、SQL、历史重放或评分，不做参数更新。结论是：**16 个恢复后逻辑槽全部已取得可评分终态，完整职责为 0/16；这不等于没有真实动作，也不能解释为只差最后审批。** 源端实际执行成功过 6 次 SQL，但没有一次成为保存评分认定的当前合格源交付；消费端只尝试执行过 1 次 SQL，返回执行错误，没有消费端提交或审批。

对应机器可读证据：[collaboration-v026-work-analysis.json](collaboration-v026-work-analysis.json)。其中保存每个尝试的原始 `runtime.json`、`joint-experience.json`、`assessment.json` 路径及 SHA-256，完整拒绝信息分组、代表动作参数、SQL 回执、固定提交版本，以及代表模型请求的 SHA-256。下文 `#N` 表示所指原始轨迹 `experience.events[].sequence=N`，不是全文行号；角色决策编号来自同次 `model_call.decision_index`。

## 1. 分母与取证范围

| 口径 | 已启动尝试 | known | unknown | 含义 |
|---|---:|---:|---:|---|
| R2 原始实际运行 | 12 | 11 | 1 | 另 4 个原计划槽未启动；中断槽仍为 unknown |
| R3 恢复实际运行 | 5 | 5 | 0 | 4 个原未启动槽与 1 个中断槽的新尝试 |
| 全部实际运行 | 17 | 16 | 1 | R2 与 R3 相加，保留重复槽的两个实际尝试 |
| 恢复后逻辑槽 | 16 | 16 | 0 | 用恢复尝试描述中断槽的逻辑结果，不覆盖原尝试 |

原 `R2/c1-02-single_pass-0` 具有保存下来的 44 次工具事件、源端执行和提交记录，但没有终态评分，不能补记为成功或失败。`R3/c1-02-single_pass-0` 是另一次真实运行；其评分不能反向赋给原尝试。本附录不拼接两次运行的局部动作来构造完整职责。

| 调用口径 | 模型请求 | 模型响应 | 工具调用 | 外层工具拒绝 | context limit | prompt tokens | completion tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| 恢复后 16 逻辑槽 | 760 | 754 | 751 | 247 | 6 | 7,916,598 | 140,419 |
| 全部 17 实际尝试 | 806 | 799 | 795 | 259 | 6 | 8,406,926 | 148,655 |

请求和 token 数取自已有 [R2](collaboration-v026-c1-r2.json)、[R3](collaboration-v026-c1-r3.json)、[recovered](collaboration-v026-c1-recovered.json) 调用归档。实际口径是 R2+R3，逻辑口径剔除原中断尝试。工具事件另由 17 份 runtime 逐项归集；两种口径一致。资源成本仍应保留全部真实消耗，不能以逻辑槽调用数代替实际成本口径。

## 2. 两种通信条件实际推进到哪里

下表均为恢复后逻辑槽，各条件 8 个；动作次数不是成功率。`SQL success` 专指已有工具返回的 `execution_status=success`，不是业务评分通过。

| 指标 | normal：8 槽 | single_pass：8 槽 |
|---|---:|---:|
| 工具调用 / 外层拒绝 | 377 / 113 | 374 / 134 |
| 读取类调用（含失败；alias/version/messages） | 181 | 239 |
| 成功 request_information | 11 | 0 |
| 成功 handoff_information / 被拒 handoff | 10 / 8 | 8 / 21 |
| maintainer 尝试过构建的槽 | 8 | 6 |
| maintainer sql_build 次数 | 19 | 10 |
| 其中：外层拒绝 / 内层执行错误 / SQL success | 2 / 13 / 4 | 2 / 6 / 2 |
| maintainer 成功 submit / 被拒 submit | 4 / 4 | 3 / 0 |
| consumer sql_build / SQL success | 0 / 0 | 1 / 0 |
| consumer submit | 0 | 0 |
| 完整职责；平均 reward | 0/8；0 | 0/8；0 |

全部实际 17 次尝试则包括 8 个 normal、9 个 single_pass。额外的原中断 single_pass 尝试贡献 44 次工具调用、12 次拒绝、1 次成功 SQL、1 次成功源提交；这些计入成本和行为描述，不能再算一个独立已评分任务。

maintainer 的真实工作包括读取 raw/source_contract、等待或请求 demand、读取并采用精确版本、写 m_code、构建 m_result，以及部分固定提交。consumer 的真实工作以读取 demand/原始材料/源产物、发送 demand、检查源提交和采用 m_result 为主。16 个逻辑槽中 consumer 仅在 2 槽写过自己的 c_code：`R2/c1-01-single_pass-0` 写 1 次，`R2/c1-03-normal-1` 写 2 次；后者没有执行。全部 17 次尝试中没有 `preflight_submission`、`approve`、`raise_issue`、`respond_issue`、`decide_issue` 调用，没有成功 SQL query；9 次 `sql_query` 均在外层被拒。

这说明至少有三个不同的停滞位置：尚在获得有效交接/引用；已经写构建但输入和 SQL 格式不匹配；已经产出可读源表却没有完成消费构建和提交。把这些都压成“沟通失败”或“最后未审批”会丢失实际差异。

## 3. 可访问、进入请求、采用、执行消费是四件不同的事

公开观察列出了对象、路由、当前工作、SQL 专属 alias、提交状态和读写权限范围；对象 ID 在观察里出现，不代表该精确版本已经共享，更不代表内容已进入当前模型请求。实际成功 `read_alias/read_version` 有返回内容；后续 `model_attempt.request.messages` 能证明选择进入模型的材料。`adopt` 绑定的是某个 work 的精确版本，既不代替读取，也不自动令 SQL 使用该表。

本轮可见具体反例：

- `R2/c1-00-normal-0` 的 maintainer 在 #99 尝试读取尚未交接的 demand，得到 `Exact object version is not shared with this actor and project`；之后 consumer 的 #248 合法交接才提供材料。先前知道 ID 不能算已经读到 demand。
- `R2/c1-01-single_pass-0`，写 m_code 的请求 #323（maintainer 决策 15，对应工具 #328）明确包含三份实际工具返回：raw、`source_meta=[pence]`、`demand_meta` 中 `invoice_mode=net_signed`。模型输出也复述了 `net_signed`，但写出的 SQL 使用 `Quantity>0` 和排除 C 开头发票。因此这里不能用“模型从未收到正确需求”解释具体错误。
- `R3/c1-02-single_pass-0` 的请求 #325（maintainer 决策 15，对应写代码 #330）同样含 raw、`sales_only` demand、`GBP` source_contract。#376 构建参数列入三份采用输入，但 `invoice_view` 的 SQL 只从 retail 取数，日期、模式和单位由常量/固定写法表达，未建立公开合同要求的 `retail+demand_meta+source_meta` 执行关系。**读过并采用三份材料，不等于三个输入表均被该导出消费。**
- consumer 可在正式源提交前读到当前草稿 m_result，例如恢复槽 #387 读取 v2、源端 #399 才提交。公开契约允许正常管理对象的读取，但要求消费固定提交时仍应识别固定版本；提前读草稿本身不能替代提交后检查。

上述请求的实际入模读回执、请求哈希、响应序号保存在派生 JSON 的 `selected_request_evidence`。这不是用权限或全文日志反推模型“应该知道”。

## 4. 六次成功 SQL：确有源表，仍未成为合格源交付

六次均导出 `invoice_view(CustomerID, InvoiceNo, amount)`、`customers(CustomerID)`、`interface_meta(amount_unit)` 这三个表名；其中一次 interface_meta 是空表。下表只描述已有返回与可直接读取的 SQL，不追加业务重评分。

| 尝试与 build 序号 | 实际产物 | 固定提交 / consumer 后续 | 保存证据显示的阻断点 |
|---|---|---|---|
| R2 `c1-02-normal-0` #422 | m_result v5；4 条发票行、2 客户、空 interface_meta；amount 为 DECIMAL | #445 提交 m_code v6+m_result v5；consumer #456/#502 检查，#479 读 v5，#521 采用 v5 | 构建只传 raw；提交采用快照缺 source_contract；interface_meta 为 `FROM retail LIMIT 0`，缺实际单位元数据 |
| R2 `c1-01-single_pass-0` #351 | m_result v2；4 发票行、2 客户、pence；amount 为 INTEGER | #374 提交两个 v2；consumer #385/#408 检查，#431 读 v2，#453 以 `m_result_adopted` 采用 | 入模需求为 net_signed，SQL 却排除负数量/取消发票；invoice_view 未引用 demand_meta/source_meta；消费构建另失败 |
| R2 `c1-03-normal-0` #468 | m_result v2；4 发票行、2 客户、pence；amount 为 DECIMAL | #491 提交两个 v2；consumer #502 检查、#525 读结果、#548 采用；没有消费构建 | SQL 将原 GBP 的 `SUM(Quantity*UnitPrice)` 直接标为 pence，未乘 100；invoice_view 未引用 demand_meta/source_meta |
| R2 `c1-03-normal-1` #353 | m_result v2；10 个明细行、2 客户、pence；amount 为 DOUBLE | #376/#445 源提交被拒；consumer #433 读草稿、#479 采用；写 c_code 未构建 | 同发票没有分组聚合，金额仍为 GBP，且未完成被请求信息的正式响应；无固定源提交 |
| R3 `c1-00-normal-1` #422 | m_result v3；4 发票行、2 客户、pence；amount 为 DECIMAL | #468 提交 m_code v4+m_result v3；consumer #456 先读结果、#479 检查固定提交、#498 更新采用、#511 读固定代码 | 已有有内容的源产物，但 invoice_view 从 retail+硬编码日期/乘数构造，未引用 demand_meta/source_meta；没有消费代码构建 |
| R3 `c1-02-single_pass-0` #376 | m_result v2；4 发票行、2 客户、GBP；amount 为 DECIMAL | #399 提交两个 v2；consumer #410 更新采用、#479 检查、#502/#524 读固定代码/结果 | 有内容的源产物，但 invoice_view 未引用 demand_meta/source_meta；消费端始终没有写代码/构建/提交 |

SQL 成功与来源正确、当前固定版本正确、业务数值正确、依赖关系正确不是同一判据。六次中五次后来成功固定提交；另两次成功源提交分别固定了执行错误结果（`R2/c1-01-normal-1`）和未实际构建的初始 m_result v1（`R2/c1-03-single_pass-0`）。所以“源提交成功 7 次”不能写成“源产品正确 7 次”。

其中 `R3/c1-00-normal-1` 和 `R3/c1-02-single_pass-0` 的返回确有分组发票、全部客户及单位表。第 8 节新增的独立内容诊断确认，两条源产物的表列名、行值和单位均与固定事实一致；原始评分仍为 0。直接保存的代码显示所有六次成功构建都没有让 invoice_view 同时引用 demand_meta 与 source_meta，因此不满足本次公开的显式关系依赖合同；**缺少关系引用不能自动推出没有利用已经读到的信息**，读入的日期、业务规则和单位可以被编码为 SQL 常量。对于四次 DECIMAL 及一次 INTEGER 输出，还存在公开 source_contract 要求 amount 为 DOUBLE 的类型偏差；不能仅凭此断言这是旧评分返回零的首个失败分支。

## 5. 四条代表轨迹

### 5.1 正常通信下，角色方向错置与只传 raw 的构建

原始：[R2 worker-0 / c1-00-normal-0 / runtime](../../runs/domain-v026-c1-r2/worker-0/actual/c1-00-normal-0/runtime.json)。

maintainer 决策 3 的 #53 正确请求 demand，返回 `request_id=mail-1` 且 `automatic_reply_scheduled=false`。下一次决策 4 的响应 #73 声称要向 consumer 提供 demand；对应 #76 调用却由 maintainer 自己在 demand route 执行 handoff，参数中包含 `request_id=mail-1`，因此被拒。路由公开 provider 是 consumer。它随后又发出两个请求（#122/#191），增加了实际待响应事项。

consumer #248 对 mail-1 提供了真实 demand v1；#456 重用同一个 handoff_key 响应 mail-2，被拒；#502 换 key 后交接成功。这些都是真实协作尝试，但没有自动补足 SQL 输入。maintainer 决策 18 的 #399 构建只有 `input_aliases=["raw"]`，代码却读 source_meta；外层 `ok=true`，内层返回 `execution_error/CatalogException`，没有 source_meta。决策 23 的 #515 再构建仍失败，这次为代码顶层含非 `models/tests/config` 字段。该槽未提交源，也没有消费构建，双方最后用尽 24 次决策。

### 5.2 需求已入模，但实现仍沿用 sales_only；消费端遇到代码结构错误

原始：[R2 worker-1 / c1-01-single_pass-0 / runtime](../../runs/domain-v026-c1-r2/worker-1/actual/c1-01-single_pass-0/runtime.json)。

consumer #110 完成规范 demand v1 单次交接。maintainer 在 #323 请求确实得到 net_signed，决策 15 的输出 #325 也写出该需求；#328 的代码却按正销售过滤。#351 执行成功，#374 固定提交，不能因此认定满足 net_signed 业务。

consumer 在检查、读取 m_result 后，#498 写 c_code（决策 22），其中 `models` 是 `{"metrics.sql":"SELECT ..."}` 映射，公开工具要求的是 `models[{name,sql}]` 列表。#530（决策 24）是本轮唯一消费 SQL 构建，外层保存结果成功，内层明确报 `ValueError: Code needs one to eight models`，阶段 `load_inputs`。其输入也仅列 `m_result_adopted`，没有按合同采用 demand。最终没有 c_result 成功 SQL、没有 consumer 提交，没有 maintainer 审批。可观察到读取/采用/写代码，但不足以形成一个消费交付。

### 5.3 恢复尝试已有源产物及固定读取，仍没有消费执行

原始：[R3 recovery / c1-02-single_pass-0 / runtime](../../runs/domain-v026-c1-r3/recovery/actual/c1-02-single_pass-0/runtime.json)。

#87 单次交接成功；maintainer 在 #146/#169/#238 采用 raw/demand/source_contract，#330 写代码。其模型请求包含三份具体内容；#376 实际 SQL 返回四条发票：`15400/556053=112.7`、`15400/562259=85.2`、`16133/562966=424.08`、`16133/564096=309.5`，单位表写 GBP，客户表有 15400 和 16133。这些是保存结果值，未在本附录重算为新评分。

#399 提交源代码和结果 v2。consumer #410 采用 v2，#479 检查真实固定提交，#502（决策 22）读 m_code v2，#524（决策 23）再次读 m_result v2。它的输出一直在描述需要构建指标，真实动作却没有进入写代码和构建。consumer #543 触发 `context_length_exceeded`，maintainer #548 达到决策上限。即使忽略源 SQL 的依赖缺项，也没有消费成果可供提交或复核。

原 R2 同名槽另存为 unknown，其保存前段包含相似动作。这里只描述恢复尝试的独立完整归档，绝不将原槽中断后的步骤由恢复轨迹“补齐”。

### 5.4 SQL 成功但交付被信息请求状态阻塞

原始：[R2 worker-1 / c1-03-normal-1 / runtime](../../runs/domain-v026-c1-r2/worker-1/actual/c1-03-normal-1/runtime.json)。

maintainer #53 请求 demand 生成 `mail-1`；consumer #64 发送 demand，但 handoff 参数没有 `request_id`。文档可读性因此得到推进，正式请求没有被对应响应解除。maintainer #353 构建实际成功，但结果是 10 个明细行、未聚合到发票，金额仍按 GBP 计算而表头标 pence。#368 的公开观察已列出 `status=blocked`、`condition_ids=[TEAM::condition-mail-1]`、`enabled_actions=[]`；接着 #376 提交得到 `Work is not open for submission by this actor`，#445 再次相同拒绝。

R3 `c1-02-normal-1` 同样存在 #53 请求、#64 无 request_id 的 handoff，#307/#445 两次提交拒绝；它的 SQL 也没有成功。这四次拒绝与冻结状态机的手工请求闭环一致，不能被当作偶发服务崩溃。另一方面，**“材料已交接，但正式请求仍阻塞交付”是本载体正常通信条件的实际交互负担**，应作为机制解释保留，不能用这些数据把零分完全归因于模型通用业务能力。

## 6. 拒绝类型：generic code 不是服务未知，执行错误另计

逻辑 16 的 247 次外层拒绝中，225 次被记录为 `ValueError / category=unknown / code=unclassified_exception`，21 次为 `ToolRejection / single_pass_communication`，1 次为 `ToolRejection / public_argument_schema`。实际 17 次则为 235、22、2。逐类读取冻结实现后，225 次都对应主动的可见引用/权限/状态/输入验证路径；没有从这些回执中发现内部 traceback、不可恢复服务崩溃或不明返回。**这仅限本次拒绝归档，不是对整个实现无缺陷的证明。**

| 逻辑 16 中 ValueError message | 次数 | 参数或状态含义 |
|---|---:|---|
| `Exact object version is not shared with this actor and project` | 98 | 内容/版本尚未向角色共享；ID 出现不提供内容权限 |
| `Issue reference must name an actual submission of this work` | 75 | 使用尚不存在、错误工作或猜测的 submission_id |
| `This exact work already has an adoption; use its version update` | 18 | 已有 adoption 仍重复新建 |
| `SQL code/output alias is outside this work's declared execution scope` | 8 | 选择了公开 work.sql_project 以外的输出 alias |
| `Handoff requires the declared manual provider and exact work lineage` | 7 | provider/工作方向不符 |
| `Unknown object` | 5 | 不存在的对象 ID |
| `Fixed adoption requires a new work declaration` | 4 | 尝试更新 fixed adoption |
| `Work is not open for submission by this actor` | 4 | 已公开 blocked 状态，未关闭的手工请求条件 |
| `SQL input requires this work's exact adoption: source_contract` | 3 | 构建时该 work 尚缺相应 adoption |
| `Handoff identity cannot be reused for different evidence or recipients` | 1 | 同 handoff key 对应声明改变 |
| `SQL source must expose explicit typed tables` | 1 | 把代码对象 m_code 作为数据输入 |
| `Only the exact work owner may execute its SQL query` | 1 | consumer 尝试在 maintainer 工作运行 query |

三个代表参数保留如下，其完整 error 对象和源码路径也在派生 JSON 中：

```json
{"attempt":"R2/c1-00-normal-0","sequence":133,"role":"consumer","action":"inspect_submission","arguments":{"work_id":"TEAM::consume","submission_id":"submission-1","include_contract":true},"error_type":"ValueError","error_message":"Issue reference must name an actual submission of this work"}
{"attempt":"R2/c1-00-single_pass-0","sequence":238,"role":"maintainer","action":"sql_query","arguments":{"work_id":"TEAM::prepare_source","source_alias":"raw","sql":"SELECT name FROM sqlite_master WHERE type='table'","output_alias":"tables_check"},"error_type":"ValueError","error_message":"SQL code/output alias is outside this work's declared execution scope"}
{"attempt":"R2/c1-01-normal-1","sequence":238,"role":"maintainer","action":"sql_build","arguments":{"code_alias":"m_code","work_id":"TEAM::prepare_source","output_alias":"m_result","input_aliases":["m_code"]},"error_type":"ValueError","error_message":"SQL source must expose explicit typed tables"}
```

这些调用可以满足 JSON 参数形状，但仍违反公开语义/状态约束；“schema 合法”不等于“动作前置条件满足”。初始公开工具写明 inspect 必须针对真实提交，公开观察列出每项 work 的 `sql_project.query_alias`；maintainer 应写 `m_query`、consumer 应写 `c_query`，而非任意 `tables_check/m_check/m_retail_sample`。现有 generic 分类没有细分可恢复语义错误，是诊断粒度限制，应保留具体 message，不能把它们统称环境故障或一概抹成格式错误。

另有 20 次**内层** `execution_error`（maintainer 19、consumer 1），其外层调用成功保存了真实失败结果，不能再次算作上述 247 次拒绝：

| 内层 SQL 错误 | 次数 |
|---|---:|
| `Code declares only models/tests/config` | 7 |
| `Table with name source_meta does not exist` | 6 |
| `Exports must select actual model names` | 2 |
| `raw.retail` 中不存在 schema raw | 2 |
| `Table with name raw does not exist` | 1 |
| `Code needs one to eight models` | 1 |
| `Model name duplicates an input or model` | 1 |

实际 17 次中此 20 次内层错误不变，因为额外中断尝试保存的是一次成功源构建。没有通过修写 SQL、替换模型动作、放宽输入关系或重新评分来改变这些结果。

## 7. 零分的边界与可支持结论

16 份已保存 assessment 的 `maintainer_current_fixed_build`、`consumer_current_fixed_build`、`consumer_fixed_inspection`、`maintainer_revalidation` 均为 null。这些字段是合同合取条件，不是“没有调用过 build/inspect”的动作计数：例如 consumer 确实检查过源提交，但没有同时合格的源/消费构建，`consumer_fixed_inspection` 仍不会成立。

冻结判据要求当前固定代码/结果、成功实际执行、准确输入采用与执行来源、结果内容匹配、被要求的 SQL 输入关系、实际入模读取，随后还要求消费固定检查与维护者复核。保存轨迹已提供零分的具体足够原因：没有合格源交付；消费端没有一次成功 SQL 或一次提交；没有审批复核。不能把有内容源表加上另一槽的消费计划拼为成功，也不能把程序控制组的可达性算成本轮真实模型完成能力。

终态的 32 个角色停止中，26 个为 `max_decisions`，6 个为 `context_length_exceeded`。它们解释了模型为何没有继续获得机会，但不是“延长 GPU 预算即可完成”的因果证据：GPU 队列/资源预算、每角色 24 次决策预算和 16k 上下文上限是不同边界；恢复资源不会自动修复 SQL、解除手工请求或扩大每槽模型上下文。

normal 与 single_pass 的最终评分差均为 0，只能说明这组冻结案例和当前运行配置没有得到完整成果；不能证明通信条件等价，也不能估计协作方法、训练或参数学习收益。本轮没有更新参数。重复读取、错误引用、公开接口要求、手工请求状态、模型业务实现和上下文停止共同构成所测系统；本附录不将全部失败单归于模型能力，也没有发现足以从现有拒绝回执认定整个载体运行失效的证据。

后续可调查的假设包括：更清晰的 alias/提交引用表示能减少无效调用；更准确的结构化 SQL 生成能提高有效执行占比；有限上下文中的材料选择可能影响剩余业务动作。它们均未在本轮做干预对照，不能当作已证实改进，也不构成本报告授权之外的追加实验。

## 8. 追加内容诊断：数值正确与原合同合格分开判断

本节是报告阶段新增的**只读内容诊断**，不属于原 reward，不回填任何 assessment。仅用 Python 标准库与 Decimal 对六次成功 SQL 的归档结果逐表比较：从同一尝试中实际读回的 raw v1 原始行出发，应用该 case 固定的半开日期区间、缺失客户/非正价格过滤，以及 sales_only 或 net_signed 规则；保留源重复行，按客户+发票累加精确十进制金额，再依据原 source_meta 的 GBP/pence 选择缩放。所有 supplied customer 均保留。比较表名、列名与行多重集，忽略行顺序；数值比较与输出声明类型单独报告。没有调用 WorldCore、DuckDB、SQL 执行器、assess_episode 或模型。

六份源产物的所有表名、列名均正确，customers 的客户集合也全部正确；差异如下：

| 尝试（build 序号） | invoice_view 值/粒度 | interface_meta 值 | 全部表列名、值与单位符合固定期望 | 声明 amount 类型符合公开 DOUBLE |
|---|---|---|---|---|
| R2 c1-02-normal-0（#422） | 正确：4 条按发票聚合的 GBP 金额 | 错误：空表，缺 GBP 一行 | 否 | 否：DECIMAL(38,2) |
| R2 c1-01-single_pass-0（#351） | 错误：只输出 4 条正销售；net_signed 应有 6 条 | 正确：pence | 否 | 否：INTEGER |
| R2 c1-03-normal-0（#468） | 错误：4 条金额均以 GBP 表示，比要求的 pence 小 100 倍 | 正确：pence | 否 | 否：DECIMAL(38,2) |
| R2 c1-03-normal-1（#353） | 错误：10 个原明细金额未聚合为 4 张发票，且仍为 GBP | 正确：pence | 否 | 是：DOUBLE |
| R3 c1-00-normal-1（#422） | 正确：4 条按发票聚合的 pence 金额 | 正确：pence | **是** | 否：DECIMAL(38,2) |
| R3 c1-02-single_pass-0（#376） | 正确：4 条按发票聚合的 GBP 金额 | 正确：GBP | **是** | 否：DECIMAL(38,2) |

其中 net_signed 槽具体漏掉 `16684 / C544184 / -15264 pence` 和 `17315 / C539402 / -4990 pence` 两张取消发票；其余四个正销售发票行与本节算术期望一致。R2 c1-03-normal-0 中例如 `15400 / 556053` 返回 112.7，而公开单位为 pence 时应是 11270。这些明确的数值/粒度错误与关系引用要求无关。

两条全部内容正确的源结果，也分别具有真实采用三份原输入、构建时传入三份输入和成功固定提交的回执；写代码时的模型请求确实含原 raw、demand 和 source_contract：R3 c1-00-normal-1 的请求 #371 对应代码 #376，R3 c1-02-single_pass-0 的请求 #325 对应代码 #330。这排除了“从未读取需求却恰好被当作已读”的描述。它们仍缺本次合同所要求的 invoice_view 对 demand_meta/source_meta 的显式表关系引用，且输出声明类型偏离 DOUBLE；这与表内容算术正确可以同时成立。显式关系引用在本轮是公开合同条件，而非判断一切真实业务程序是否使用需求的通用标准。

因此，原 `correct_current_source_delivery=0/16` 应解释为**没有满足整套冻结源交付合同的提交**，不应改写为“16 槽所有源端数值都错”或“模型没有使用读到的需求”。本节得到的 2/6 是对六次源 SQL 成功产物的内容诊断比例，不能替代完整职责分母、不得写成 2/16 业务成功，也不构成方法支持。消费端仍然是独立事实：成功 SQL 0 次、提交 0 次，故没有完整的双向交付与复核。原全部 reward、完整职责 0/16、中断 unknown、零参数更新均保持原记录。

派生 JSON 的 `additional_content_diagnostic` 保存本节规则、六份精确实际/期望行、差异行、读取来源序号和原始材料身份；期望中的 Decimal 以十进制字符串保存以避免 JSON 浮点舍入。
