# v0.21 D 线：真实联合 A/B 合同与 CPU 控制

本轮把联合 A/B 绑定到现有 UCI 开发材料、真实准备前缀、世界工具、固定提交、独立评价及描述性 Mapper。**13 条联合正负程序路径符合预期，另 4 条单岗位合同程序见证通过。**这些都是 CPU 机制控制；没有 GPU、API、目标模型、参数更新或方法频数，本报告不预测 N/E 线结果。

机器归档：[retail-collaboration-v021.json](retail-collaboration-v021.json)。原始世界、每次工具返回、准备前缀及只读 episode 在 `runs/retail-collaboration-v021-cpu/`。报告同时保留一次测试失败和一次临时见证脚本错误，未改写为成功运行。

## 1. 来源和六例目录

来源仍是 `uci-online-retail-352`，使用原 v0.15 固定的 **development-f0/f1/f2** 客户与完整发票切片。原始 XLSX 和切片 SHA 沿用现有加载器核验，不重新生成交易行、不接触 train/locked 切片。UCI 数值行是真实来源，业务政策、角色和工作关系是显式模拟。该材料已用于接口开发，本轮不称新独立来源或未接触外测。

目录版本 `retail-collaboration-v0.21`，静态清单为 [catalog.json](../../examples/retail-collaboration-v21/catalog.json)。六例在查看本轮模型结果前固定，无按成绩补采或换题。

| 顺序 | 工作 | 开发事实 | host 准备条件 | 实际角色决策上限 |
|---|---|---|---|---|
| 1 | 实现 | f0 | 合法交接、读入并采用 data/basis，未构建提交 | implementer 12 |
| 2 | 实现 | f1 | 同上，采用该例政策 | implementer 12 |
| 3 | 独立复核 | f0 | 正确的真实固定提交 | reviewer 12 |
| 4 | 独立复核 | f0 | 错计数的真实固定提交 | reviewer 12 |
| 5 | 联合 A | f2 | 无交接、构建或提交前缀 | provider 6；implementer 16 |
| 6 | 联合 B | f0 | 错金额的真实固定提交 | implementer 24；reviewer 28 |

共 122 次目标角色决策上限，wait/done 按既有运行时预算计入；外部时间上限由 E 线启动协议另行约束。目录不是学习协议，`model_training_eligible=False`，没有自动启动入口。CPU 为 B 另建正确／错计数／错金额三条件交叉；它们不是追加的 E 样本，更不能混成同一精确初态的不同模型方法。

## 2. 合同 A：取得依据并实际使用

提供者初始独占合法适用的 `basis`；实现者拥有真实零售数据及代码、构建与提交权限，起初不能读取该私有政策。主动通过 `basis` route 交接或先由实现者请求均合法，环境只交付选定的准确版本，不替实现者选择、计算或填结果。

完成条件同时要求：提供者本轮实际读了适用依据，合法 handoff 的送达事件真实应用；实现者本轮取得并读入最终采用的精确 data/basis；真实 `sql_build` 使用该交接版本；正确 code/result 固定在新的提交中。评分分别为送达 0.2、送达依据用于正确构建 0.3、正确固定交付 0.5。只有消息、只有发送，或未消费依据都不能算联合完成。

这里的“使用”有可核对的操作定义：实际读取、准确采用、执行源引用与交接引用一致、独立业务结果正确；它不是对模型内部推理或信息因果贡献的测量。

## 3. 合同 B：独立复核与真实修复

B 的 f0 数据、政策、独立 audit facts、角色任务和公开评分合同保持相同，交叉三种实际提交内容：正确、错计数、错金额。准备通过现有工具真实执行 provider 交接、implementer 读入和采用、写代码、执行 SQL、固定提交；没有伪造 result 或直接插入成功标签。准备调用及其世界变化保存在 `preparation.json`，开始目标 episode 后不算当前角色动作。

复核者可读取自己的适用 `audit_basis` 和数据；audit facts 仅说明日期、取消发票、数量、价格、重复行、GBP 和发票粒度规则，没有期望数值表。实现者可检查原固定提交、按已交接政策自检；复核者也可先找到有依据的问题。两种路径都允许，不强制先出错再修复。

对错误初稿，真实过程可以是：检查固定旧版本 → withdraw → 编辑并重新 build → 新固定提交；若已产生有效 issue，还须 implementer 对实际新提交 respond，reviewer 实际读取新固定 code/result 并 decide_issue，再最终 approve。新文件、口头“已修复”和直接改标签都不能替代这条已有世界关系。对正确初稿，有据的直接批准即能完成，完全不需要制造返工。

B 的终态分项是独立最终复核 0.4、正确固定最终产品 0.3、有效复核／修复路径 0.3。正确产品项不能只靠准备状态获得：需要当前真实正确新构建／提交，或当前有据批准；**正确前缀加零动作得 0**。继承的正确代码仍明确标记 `current_actor_build=False`，不算本轮实现功劳。对本轮所有实际批准和 issue 都检查正确性与先前证据，后来的读材料或正确批准不能擦掉早先错误／无据判断。

## 4. 实现与评价边界

实现入口为 `proworksim.templates.retail_collaboration_v021`：

```python
registry()['situations']                  # 恰好预定 E6
case_spec(case_id)
build_case(case_or_id, root, assets_root=None)  # 标准 PreparedOnlineCase
assess_episode(episode_path, spec=None)    # 仅从已关闭只读历史评价
cpu_variant('correct')                  # 仅用于 B 交叉 CPU 控制
```

`build_case` 复用 retail_balanced 的声明与 retail_work 的实际准备流程、WorldCore 及原 SQL 工具；没有新引擎、没有修改核心生命周期。prepared 可供现有 harness `_runtime` 和 `run_fragment` 使用。E 线可直接 begin/finish episode 后调用该独立评分器，不必伪装成已有 RL rollout。

评价版本 `retail-collaboration-outcomes-v0.21`。评分检查冻结 case/合同、episode 开始和结束文件、命令回执、绑定角色和实际版本谱系；数值正确性仍由已有独立 Decimal evaluator 根据原行与采用政策重算，不以可编辑 tests、review 标签或 SQL 自报成功作为真值。复核 issue 必须准确定位真实错误行／列，并具有实际读到的 data/audit 证据。

返回值分开 `termination`、`record_trust`、`independent_assessability`、`eligible/reward/completed`。格式终止本身不清除已知业务后果；可信零动作是已知 0，已完成工作仍可为已知 1。真实服务、身份、接口或关键历史证据问题返回未准入及 null，具体原因保留。这里不从业务成绩反推身份或模型支持；E 外层仍须保存并验证其模型身份、原始调用和计算配置。

Mapper `retail-collaboration-observed-path-v0.21` 只描述真实观察到的主动／请求式交接、正确初稿直接复核、实施者自检后独立复核、有据反馈后定向修复。请求式交接要求实际 handoff 的 request_id 与同 route/work 且更早的成功请求吻合，出现一条无关请求不够。只有完整责任成立才给可用 class_id；没有因果成员贡献、当前模型频数或训练投影声明。跨准备质量的 class_id 不能自动合并为同一 xi 的支持。

## 5. CPU 实际结果

| 控制 | 分数 | 完整责任 | 实际含义 |
|---|---:|---|---|
| A 主动交接并使用 | 1 | 是 | 合法送达、读入采用、真实构建和固定提交 |
| A 请求后交接并使用 | 1 | 是 | 实际 request_id 与送达链相连 |
| A 依据已送达但未用 | 0.2 | 否 | 送达成立；没有把消息当完成 |
| B 正确初稿直接复核 | 1 | 是 | 不需修复 |
| B 正确初稿、没有动作 | 0 | 否 | 准备不记本轮功劳 |
| B 错计数、反馈修复 | 1 | 是 | 有据 issue、新构建提交及最终复核 |
| B 错金额、反馈修复 | 1 | 是 | 同一业务口径的另一真实缺陷 |
| B 错金额、自检修复 | 1 | 是 | 不要求复核者先发现问题 |
| B 批准错误初稿 | 0 | 否 | 错误判断保留 |
| B 正确初稿、未读证据即批准 | 0 | 否 | 结果碰巧正确不等于有据复核 |
| B 问题位置错误 | 0 | 否 | 有 issue 对象也不自动有效 |
| B 问题缺少 data/audit 证据 | 0 | 否 | 实际复核证据不可省略 |
| B 修复后仍错误却批准 | 0 | 否 | 新版本和处理标签不能替代内容正确 |

其中 A 未使用控制关闭旧 episode 后，继续 live world 完成了正确交付；再次评估旧 episode，结果仍完全相同的 0.2，没有后续回填。B 正确初稿控制明确区分继承构建和当前复核；错误前缀的原固定版本保留，修复以新版本和新提交证明。

额外 4 条单岗位新合同 CPU 见证（f0/f1 实现及 f0 正确／错计数复核）均为 1；复核错计数时取得的是“有据指出错误”的职责完成，原错误业务产品没有变成正确。这 4 条只是新评分入口控制，不是 E 模型样本。

三个 B 准备质量的 data/basis/audit 字节 SHA、公开 reward_spec 和角色任务全部相等；公开观察没有 `prepared_submission`、`wrong_count`、`wrong_amount` 等 host 标签。代码与结果中的真实错误当然仍可被工作人员检查，这是工作内容，不是标签泄漏。

## 6. 失败保留与必要测试

初次定向测试为 **2 passed、2 failed，5.99 秒**。两项真实 StaffRuntime 加显式假 policy 的边界控制发现：`public_tools` 事件 payload 是 list，评分器初稿对所有 payload 调用 `.get`，抛出了 AttributeError。修复仅增加 dict 类型判断，没有改分数、旧门或业务合同。原失败 JUnit 保留；仅重跑失败的两项，**2 passed、2 deselected，1.52 秒**。它们证明两个角色都获得原预算内机会，格式边界保持已知 0，服务边界保持 null。

另有一个真实 StaffRuntime 控制，显式 CPU 程序先完成 A 的实际工作，再以模拟格式边界退出，结果仍为已知 1：**1 passed、4 deselected，1.26 秒**。它是运行时加假 policy 控制，不是实际 HTTP 200、SDK 或真实模型实验。共 5 个不同定向测试在上述有界调用中通过；没有为了汇总单一数字再重复全文件或全库。三个新增 Python 文件 Ruff 通过。

单岗位额外检查的一次临时脚本错误也保留：它把 A 的“先 adopt”程序复用于已经由前缀 adopt 的实现任务，世界正确拒绝重复采用。原 open episode、世界与 `witness-failure.json` 留在 `E-scope-retail-v21-fc930eb08da0d524/`；没有补造分数。随后用独立新世界，读取并复用已经存在的精确采用关系，完成四项单岗位控制；未改核心。

## 7. 未完成范围

本轮 D 线完成的是具体开发合同、独立评分与 CPU 可执行性。尚不证明任何目标模型会选择这些路径，也没有取得联合方法的样本支持、训练容量或学习收益。全部情况仍属于同一已开发 UCI 家族；SQLite P0、外部 TeamBench 或其他来源不因本次内部合同成功而自动准入。

E 的六例冻结参数模型评价、N 的数值诊断及资源授权由各自协议报告。D 的 CPU 成功不放行训练概率门，也不要求等待 N 成功才保留 E 的可独立评价业务结果。未来如要训练，需另行完成奖励到实际当前策略经历的投影、训练资格与资源准入，不能直接把这批 host 程序调用作为 SFT 或策略训练数据。
