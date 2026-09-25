# v0.12：ID-VTDO 联合经历与基础学习预检

本轮于 2026-09-25 启动，最后本地采集在 UTC 2026-09-25 16:31:36（北京时间 2026-09-26 00:31:36）结束。各批次独立冻结并保留失败；不同运行协议的数据不合并为一个成功率。

## 1. 主要结果与阶段判断

本轮已把工作重点从“模型接口能调用、首个决定能反向传播”转到“当前团队产生了什么联合经历，以及哪些成员能够使用这些经历学习”。三角色的信息不对称 SQL 工作、真实成员交接、联合轨迹归档、成员局部投影、三值有效性、有限方法归类和固定分母权重物化均已接通；**可重复的接口门槛、同情境多类可训练支持和真实多轮学习收益尚未建立。**

本轮主要结果如下：

- **D0 正式 16 段比较完成，但两个后端门槛均未通过。**DeepSeek 在报告任务有两条独立正确完成，其中新接口候选一条；SQL 起点没有独立正确完成。Qwen 没有完整正确交付，原生接口组还遇到真实本地服务错误。不能把接口组合变化称为算法增益。
- **D1 程序机制验证完成：13 条见证、73/73 项检查通过。**12 条完成，1 条必要资料不可得且有效性保持 unknown。四个精确情境的主动交接、请求后交接都具备相同初始状态、相同场景与角色说明；这是程序可行性，不是模型方法支持。
- **DeepSeek 的固定 16 条联合模型普查及 D2 物化完成。**制度完成 6 条，独立正确且制度完成 5 条；奖励为 1 的共有 7 条。严格工作有效性为 true/false/unknown = **3/11/2**。三条有效语义经历分属三个不同情境，不能合并成同情境多类支持。全部 API 输出缺实际 token trace，**所有成员的可训练支持仍为 0**。
- **原 Qwen D1 计划没有完成。**固定 16 槽中仅 2 条闭合、1 条仍 open、13 条未开始；旧 FP32/GQA 注意力资源问题导致本项目操作终止。未开始槽不是失败轨迹，原窗口不估计经验分布或支持频率。
- **数值与显存工程候选有独立证据。**小张量实际 profiler 确认原 FP32 native-GQA 默认走 math；显式 KV 展开后的 efficient kernel 可用。3 条固定历史响应在完整模型 teacher forcing 下的 `highest`、`high` 两组概率检查均通过原阈值，按预声明规则选择 `high`。这些结果没有产生新 rollout、训练更新或自回归加速测量。
- **新 Qwen 独立16槽完整采集。**共952次真实响应、9,676,429已报告tokens，全部为可评零奖励、V=false、unmapped；三名成员的全轮动作均能恢复；14次SQL实际执行成功，但未形成有效交付，可重配正支持为0。
- **D3 当前归档证据是实现、准入和 CPU 算术验证。**真实 Torch 小张量验证了 Q=B 的损失、梯度、规定更新与优化器状态等式。新 Qwen 的固定四槽共240次真实生成完整可恢复，但 D0 未通过且四个回报均为0；准入如实停止，模型 actor/critic 均0次更新。D4、D5 未执行。

| 阶段 | 已完成 | 未通过或尚未完成 | 当前允许结论 |
|---|---|---|---|
| D0 固定工作接口 | 两个接口组合、两起点、两后端、两重复，共 16 段；真实公开结构预检和输入选择留痕 | DeepSeek、Qwen 的正式门槛均 false | 新接口能进入部分实质工作，但不能称固定接口已可靠 |
| D1 三成员团队 | 手工成员交接与 SQL/复核链；13 条规则见证；DeepSeek 16 条全部保留 | 原 Qwen 16 槽中断；新 profile 完成16槽但无有效交付 | 世界机制和部分真实团队工作可行，不等于学习支持充分 |
| D2 联合经历与支持 | TeamRollout、MemberView、实际信息关系图、Mapper、V、成员支持、Q=B 权重；完整 DeepSeek及新Qwen普查 | 没有同情境多类可训练正支持 | API有3条有效语义联合经历；新本地有完整失败动作，但没有有效方法支持 |
| D3 基础多轮 PPO | 完整多轮输入/损失/准入实现；CPU 算术与恢复控制 | 固定四槽完整恢复；D0和回报差异门槛未过，未执行真实模型更新或fresh工作检查 | 算术和工程接口证据，不是基础 MARL 学习成立 |
| D4 Contribution | 研究设计、共同起点与强基线要求已明确 | 未执行配对试训与开发效用测量 | 不报告贡献估计或组成优化收益 |
| D5 联合交互/在线闭环 | 设计要求明确 | 未执行四分支交互与在线再采集 | 不报告交互收益、泛化或同总预算优越性 |

上述判断以各批冻结协议为准，不以最终成功覆盖过程错误。新本地的全量材料与D3门槛见[独立归档](v012-idvtdo-support-qwen-efficient-r1.json)。详细原件摘要分别见 [D0](v012-idvtdo-model-d0.json)、[机制](v012-idvtdo-mechanisms.json)、[DeepSeek 支持](v012-idvtdo-support-deepseek.json)、[原 Qwen 中断](v012-idvtdo-qwen-interrupted.json)和[数值诊断](v012-idvtdo-numerics.json)。

## 2. 研究目标与保留的阶段基线

本轮依据 [v0.11 审计](../reference/id-vtdo-audit-v011.md)、[ID-VTDO 研究设计](../research/id-vtdo.md)和[预声明计划](../id-vtdo-v012-plan.md)。v0.11 已建立的真实工具调用、受限可执行项目群、历史 episode 评价与有限首决策训练仍成立；原 46 段模型实验及三条零奖励首决策训练均未重写、补来源或追加训练来改变原结论。

本轮没有照搬旧的 144/256 次规模建议。首先固定接口并检查目标团队经历，分别回答：

1. 是否存在真实、可解释的团队工作记录？
2. 工作有效性 V 是否满足记录、权限、依据及交付合同？
3. 同一精确情境 ξ、运行协议 Γ、团队策略和收集窗口中，有哪些可靠方法类别？
4. 每名成员的全部实际动作是否可恢复，是否有足够支持用于训练或重配？
5. 在这些前提下，基础多轮学习能否改善更新后的工作行为？

奖励资格、V 与可重配资格分别保存。可信零奖励仍可作为基础 RL 的失败材料；但 `reward_eligible=true` 不能充当有效工作正类，`reward=1` 也不自动保证已完成真实复核或完整记录。反之，缺失商业 API token trace 不等于其语义工作不可能，只意味着不能据此恢复所需的 actor 训练轨迹。

D4 的 Contribution 是改变训练组成之后的团队开发效用，不是当前执行功劳或轨迹 reward。D5 的成员交互需要共同起点四分支比较，后续在线阶段还要重新采集。当前没有满足这些实验前提，不以平台模块数量、调用次数或一次参数变化替代算法证据。

## 3. 源码、协议与分母边界

| 批次/材料 | 源码或身份 | 边界 |
|---|---|---|
| 初始审计基线 | `412e093bcb4c359db9b1efd79a17051610a0701e` | 原 v0.11 结果保持 |
| 两条 D0 pilot | dirty `8bc32a5…`，开发期间摘要有变化 | 仅开发诊断及资源记账，不补正式成功槽 |
| D0 正式 16 段、完整回归 | clean `17b5698542afe28790ac16290ee9647d4dd28da3` | 独立工作树；起止源码与输入身份检查 |
| D1 规则见证、原 DeepSeek/Qwen 协议、D2/D3 初始实现 | clean `09e45d9d0d15db0fd98e02565d4f69da888c314c` | 32 个原计划联合槽，两后端各 16；按后端分队列 |
| 独立 kernel/teacher-forcing 探针 | dirty `09e45d9…`，各探针自身起止摘要一致 | 单独工程材料，不能重标为旧 clean D1 的 Γ |
| 数值与公开结构修订 | `5cb5dab33f54c1213b56f1e87cae8026a05fcaa0` | 新服务来自 `/tmp/proworksim-v012-efficient-service` 的该 clean 身份 |
| 新协议首次准入失败 | clean `026e3e0cd4c372f58a69975712a89a3156232419` | 场景摘要不符，0 世界、0 HTTP；不算模型执行 |
| 新 Qwen efficient-r1 正式协议 | `8ff75ea9d6d7cfc0aa88f4664f2b64a00881c061` | 修正准入环境预算元数据；独立新批16槽全部封闭 |
| 四情境D3准入 | clean `f9762242ced5e6790e79845d01fb156c9670e053` | 独立只读prepare-only；修正跨情境窗口对接，不改变采集 |

D0 在独立 detached 工作树运行，主树并行开发 D1；运行子进程显式使用对应工作树的 Python 源，避免读取正在修改的 editable 主树。D1 的 DeepSeek 队列可与 D0 本地队列并行；原 Qwen 队列在 D0 本地结束后启动。每段都有实际请求、工具返回、资源与预算记录，不能根据完成时间推断随机执行顺序。

正式 D0 是 `2 起点 × 2 重复 × 2 后端 × 2 接口组合 = 16`。初始 D1 是 `2 构造数据实例 × 2 信息布局 × 4 重复 × 2 后端 = 32` 个预定联合槽。两后端、两信息布局、不同数值 profile、修改后的公开结构合同及不同预算都不合并成一个同 Γ 支持窗口。程序见证与模型样本也不混池。

## 4. D0：接口机制落地，但正式门槛未过

新增原生工具或单 JSON 的明确动作协议、格式反馈续行、当前观察选择记录及本地推理 profile 身份。格式错误整条拒绝，不抽取其中一个工具调用执行；实际失败消耗决策与调用预算，下一次角色机会才能继续。格式反馈不提供业务答案或自动补来源。

`latest_observation` 将本次模型输入与完整档案分开：删除旧公开观察时保存选择记录，真实 assistant 输出、工具返回和必要反馈按固定规则保留。公开只读预检检查文件、来源引用、采用、依赖与实际执行输入事实，不替模型选择或采用正确材料，也不评价隐藏业务值。

两条 dirty pilot 中，DeepSeek 完成一条报告，Qwen 两次合法调用后等待。pilot 不能替正式批补一条成功。D0每段只将一名目标角色交给模型，其余协作者或准备前缀单列为规则执行，不进入D1当前团队支持。随后正式比较均使用相同工作起点、公开业务要求和预算：每角色最多 40 决策、60 HTTP attempts、500,000 tokens、4096 单次输出，环境最多 240 机会。单 JSON/即停与原生工具/反馈续行是**组合比较**，不能分别识别包装协议、反馈和交互机会各自的因果作用。

| 后端与接口组合 | 固定槽数 | 制度完成 | 格式停止 | 预算停止 | 服务错误 | 等待停止 | 独立正确完成：报告 / SQL |
|---|---:|---:|---:|---:|---:|---:|---:|
| DeepSeek JSON/即停 | 4 | 1 | 2 | 1 | 0 | 0 | 1 / 0 |
| DeepSeek 原生/反馈 | 4 | 1 | 2 | 1 | 0 | 0 | 1 / 0 |
| Qwen JSON/即停 | 4 | 0 | 4 | 0 | 0 | 0 | 0 / 0 |
| Qwen 原生/反馈 | 4 | 0 | 0 | 0 | 3 | 1 | 0 / 0 |

门槛事先要求原生反馈候选在报告、SQL 两个起点各至少一条独立正确完整交付，合计至少两条。**DeepSeek=false，Qwen=false**。DeepSeek 的 JSON 组成功不转移给候选组；Qwen 的服务错误不改写为模型业务失败。16 段中 13 段奖励可信，另 3 段服务错误保持不可训练/null。

计划允许在 D0 未通过时进行小型 D1 支持普查以定位缺口，但不因此宣称接口可靠，更不能进入 D4/D5。原 D0 全部结果保留，新 profile 的任何表现也不回填这个门槛。

## 5. D1：真实成员交接及规则见证

新任务只有一个 `TEAM` 项目、一个 `TEAM::build` 节点，三个决策角色是 provider、implementer、reviewer。operator 负责初始安装与材料声明，不是第四个学习成员。两组事实各含 6 条交易和 3 名客户，是复用既有 Jaffle 式 SQL 接口的**研究构造合成实例**，不是上游 seeds 切片，不新增独立公开来源。

| 精确信息布局 | 业务 basis | 独立 audit_basis |
|---|---|---|
| split_a | provider 持有，需交给 implementer | reviewer 自持 |
| split_b | reviewer 持有，需交给 implementer | provider 持有，需交给 reviewer |

资料对象的写权属于 operator，持有者仅有读权和限定对象/用途/工作节点的 provide 权力。manual route 的 request 只建立真实请求及等待条件，不代替提供者选择正确版本。提供者必须真实读过所选精确证据，才能调用 `handoff_information`；环境负责延迟和权限内送达，不自动采用、提交或批准。主动交接与请求后交接使用同一份场景、角色提示与信息条件。

实现者真实读/采用 data、basis，编辑受管 SQL，交给 DuckDB build，提交确切 code/result 版本。Reviewer 真实读取固定提交和当期 audit_basis，进行问题定位、回应处理或批准。独立 Python 内容评价与成员策略分离。

程序见证覆盖八条基础双路径，以及迟到、旧版并存、不可得、全信息和一次真实审阅修订，共 13 条。正式结果为 **73/73 判据**：13 条各 5 项检查，四组同 ξ 对照各 2 项一致性检查。12 条 completed；不可得一条真实 unavailable，V 保持 unknown，不进入正类。修订控制实际保留错误 SQL 提交，经过定位问题、撤回、重建、新提交、回应、`accept_fix` 和批准，不由最终成功抹去历史。

开发期还封住了一个真实旁路：通用 `request(provider, reference, …)` 曾能为 manual 对象排入自动 provider 回复，原例 provider read=0、handoffs={}。**原私有读取仍被拒绝，不能将此写成已证实 ACL 泄漏。**修订后该通用请求按工作节点/对象拒绝，正式 manual 回归验证没有伪造请求、事件或回复。旧 automatic 服务仍可作回归，但其动作不记为学习成员选择。

完整判据、原 before 世界、补修测试、开发驱动错误及缺失临时证据的限制，见 [机制归档](v012-idvtdo-mechanisms.json)。规则见证只证明两种方式在世界内可行，不计目标模型的任何方法频数。

## 6. DeepSeek：完整 16 条联合普查及严格有效性

三个角色均由实际 DeepSeek API 决策，角色提示不要求选择主动或被动路径。冻结为四个精确情境各四次，所有 16 槽均保留。云模型别名及观察到的版本信息原样记录，但没有独立验证供应商权重不可变。

终点分类为 completed 6、预算停止 3、格式停止 3、等待停止 2、world_blocked 2。所有 16 段均有可信 RewardSpec 回报：7 个 1、9 个 0。它们与 V 并不相同：

| 实例/布局/重复 | 原运行终点 | Reward | V | 有限 Mapper |
|---|---|---:|---|---|
| orders_a / split_a / 1 | model_format_error | 0 | false | proactive |
| orders_a / split_a / 2 | completed | 1 | unknown | proactive |
| orders_a / split_a / 3 | model_format_error | 0 | false | unmapped |
| orders_a / split_a / 4 | model_budget_exhausted | 1 | false | proactive |
| orders_a / split_b / 1 | model_budget_exhausted | 0 | false | unmapped |
| orders_a / split_b / 2 | completed | 1 | true | requested |
| orders_a / split_b / 3 | world_blocked | 0 | false | unmapped |
| orders_a / split_b / 4 | model_format_error | 0 | false | unmapped |
| orders_b / split_a / 1 | worker_waiting | 0 | false | proactive |
| orders_b / split_a / 2 | worker_waiting | 1 | false | proactive |
| orders_b / split_a / 3 | completed | 0 | false | proactive |
| orders_b / split_a / 4 | completed | 1 | true | proactive |
| orders_b / split_b / 1 | model_budget_exhausted | 0 | false | unmapped |
| orders_b / split_b / 2 | completed | 1 | true | requested |
| orders_b / split_b / 3 | world_blocked | 0 | false | unmapped |
| orders_b / split_b / 4 | completed | 1 | unknown | requested |

V 按开始前合同从实际捕获、世界正式提交、精确读/采用、手动选择及送达、复核读证据与最终交付推导，不手填四个 true。记录不完整为 unknown，已观察合同失败为 false；unknown 不强制变成 reward 0 或 V=false。两条 V=unknown 都已完成且内容通过，但发生过真实断连与重试，冻结记录合同保守地不能认证全部行为抽样。另有两条 V=false 同时存在 record=unknown，由独立的依据/交付失败优先决定整体 false。

三个例子说明分层必要性：

- `orders_b/split_a/2` 的固定内容正确、reward=1，但截止仍待审，没有实际批准，因此 delivery=false。basis=true 只认证已发生的交接/提交义务，不声称尚未执行的审阅已经发生。
- `orders_b/split_a/3` 获得真实批准，但输出表名是 `customer_metrics`，冻结评价要求 `metrics`。其三行数值与原采用事实一致：`[1,1000,1]、[2,800,2]、[3,0,0]`。这是命名/公开结构表达及预检覆盖问题，不能描述成算错金额或输出物理空表；原 content_failure/reward=0 保留。
- `orders_a/split_a/2` 与 `orders_b/split_b/4` 虽然独立正确且完成，记录维度仍因不可充分恢复的传输经历保持 unknown，不用终局正确洗掉记录缺口。

第二例 reviewer 确实读取固定 code/result、audit_basis、data，再 inspect 后批准；它另一次 SQL query 被 owner 权限真实拒绝。这不是 reviewer 被隐藏评价器自动告知答案。表名案例的只读诊断与原字段摘要见 [机制归档的 selected_model_diagnostic](v012-idvtdo-mechanisms.json)。后来的公开结构修订属于新版本；旧模型交付与原评分没有补写或重新命名。

## 7. D2：有效语义经历不等于可训练支持

`TeamRollout` 固定联合 episode、ξ、Γ、团队策略和原槽清单；`MemberView` 从真实 HTTP 请求/响应恢复各成员每轮局部输入和本人输出归属。信息图只记录可观察的 read、request、handoff、delivery、adoption、检查和修订关联，不将项目结构图或时间先后当作因果识别。

当前 Mapper 仅声明 basis 路由的 `proactive_handoff`、`requested_handoff` 两类。话术、随机 ID、等待时长不造新类；无法确定唯一真实 handoff 的轨迹保留 unmapped。DeepSeek 共 10 条可靠映射（7 proactive、3 requested）、6 条 unmapped，**映射不保证 V=true**。

| 独立情境窗口 | 原始 M | V true / false / unknown | 有效语义方法及条数 | 每成员可训练 n / v / b |
|---|---:|---:|---|---|
| orders_a / split_a | 4 | 0 / 3 / 1 | 无 | 0 / 0 / 空 |
| orders_a / split_b | 4 | 1 / 3 / 0 | requested：1 | 0 / 0 / 空 |
| orders_b / split_a | 4 | 1 / 3 / 0 | proactive：1 | 0 / 0 / 空 |
| orders_b / split_b | 4 | 1 / 2 / 1 | requested：1 | 0 / 0 / 空 |

每类最低两条是本轮事先固定的有限支持门槛，不是 Contribution 估计的充分样本量。三条 V=true 产生 9 个有效成员语义投影，**仍然只有 3 条联合经历**；分别位于不同 ξ，不能把两个 requested 或规则见证跨情境拼成同情境支持。每个有语义正例的窗口只有一个该类例子，未达到类频数门槛，也没有多个类别的组成自由度。

API 总共返回 620 个真实 completion：provider 131、implementer 246、reviewer 243。完整语义成员 episode 数分别为 15、13、14；这描述请求/响应可恢复性，不是有效工作成功数。实际 token trace 可用数为 0，因此全部成员完整 actor 轨迹为 false；不能重新分词输出、猜测概率或借本地模型为云输出补造 actor 数据。

每个窗口仍物化原 M=4 的全部槽：b 为空、v=0、Q=B 时原槽权重均为 1，actor mask 为 0。不能把失败删除后重算分母，也不把缺失质量转给其他成员。这是**支持与权重层**的正确保留，不是 API 材料上的 PPO loss/梯度/更新等价实证；后者只在 D3 的独立 CPU 算术控制中验证。

完整 16 槽、逐成员排除原因、实际 graph/view/transport 引用与费用见 [DeepSeek 支持归档](v012-idvtdo-support-deepseek.json)。

## 8. 原 Qwen 中断、数值修订及独立新批

### 8.1 原 16 槽没有形成完整普查

原 Qwen D1 使用 clean `09e45d9` 的 FP32 SDPA profile。操作停止时只有：

| 原计划槽的实际状态 | 数量 | 处理 |
|---|---:|---|
| 已闭合 | 2 | 两条均 model_service_error，eligible=false、reward=null；局部结构失败不替代可信终局回报 |
| 已开始但 episode 仍 open | 1 | 保留原开口边界，不事后伪造 finish |
| 未开始 | 13 | 不是 rollout，也不是观察到的失败 |
| 原计划总数 | 16 | 未完成，不作为经验 M 估计 b、v 或成功率 |

本项目停止的是已确认命令与 PID 的自身旧服务，没有终止其他项目进程。共享 GPU 竞争存在且已记录；旧 GPU4 OOM 原文主要显示**本进程**约 74.87 GiB，并非证据支持“只是别人抢显存”。不能把新 profile 的成功或失败填回这 13 个旧空槽。见[原 Qwen 中断归档](v012-idvtdo-qwen-interrupted.json)。

原中断批的[单独资源账](v012-idvtdo-qwen-interrupted-resources.json)按实际客户端与服务记录区分：两条 closed 合计 121 次 HTTP attempt，117 次成功返回、4 次未知用量 503，已报告 1,154,208 tokens；open 一条有 20 次请求开始、19 次客户端完成，已计量 151,618 tokens。另一次客户端未完成调用能唯一对应服务端的 9,867 tokens：服务生成于 UTC 14:23:08，晚于采集进程在 14:23:04.719977 的操作停止。它只计实际服务资源，不补为客户端收到、世界执行或 episode 封闭。

因此该旧 D1 共发生 141 次 attempt，确认 137 次服务生成、1,315,693 个已知 tokens；4 次失败的真实用量仍未知。客户端已记账的 1,607,114 tokens 含 301,288 个未知预留，另一个未完成请求的原预留 59,925 单列，不能冒充已确认费用。原服务其余 69 次成功生成准确归属于 pilot 2 次与正式 D0 67 次；没有将全部 206 个服务响应都混记为 D1。

### 8.2 数值和资源诊断只支持工程候选准入

安装源码与小尺寸实际 profiler 支持以下解释：FP32、28 query heads/4 KV heads 的原 native-GQA 在该环境走 math，长 prefill 有 N² 中间量。新候选只在 attention 调用内按原分组展开 KV，强制 efficient kernel，保留原 mask 与 grouped cache 语义，不静默回退 math、CPU 或较低权重 dtype。

三条固定旧响应按顺序/最长已成功输入选择，不按 reward 筛选。完整模型 teacher forcing 的 `highest` 和 `high` 都通过最大逐 token 概率差 ≤0.02 nat、平均差 ≤0.002 nat。`high` 的最坏值分别是 0.009119719、0.000448126 nat；allocated 峰值 29.784–32.052 GiB。第二条的序列差之和 −0.020154219 nat 仍保留，门槛不是序列和。由此按协议选择 `high`，没有发生新生成或模型训练。

另一次 GPU5 完整模型加载失败，原日志显示另一进程 60.47 GiB、本进程 18.63 GiB，是不同于旧 GPU4 自身计算高峰的资源竞争事件；该次 0 数值检查。新 allocated 峰值与旧整进程 OOM 占用也不是同一测量口径，不能直接宣称固定比例的显存或自回归速度收益。详见[技术说明](v012-numerics.md)与[原始数值归档](v012-idvtdo-numerics.json)。

### 8.3 首次新协议在准入前失败

`026e3e0` 的 `runs/id-vtdo-v12-d1-qwen-efficient/` 保存 16 个槽的 `experiment_error`，原因是实际配置后的场景摘要与预声明 identity 不同。拒绝发生于创建工作世界和发 HTTP 之前：**0 世界、0 HTTP**。它是协议配置错误，不是 16 次模型工作失败，也不占新模型经验支持分母。`8ff75ea` 修正环境预算元数据后，以全新目录重新冻结。原错误记录及[独立核对](v012-idvtdo-qwen-efficient-prestart.json)保留。

### 8.4 新 efficient-r1 批次：16槽完整，但没有有效工作支持

该批是独立的16个预声明联合槽，四个精确情境各四次；采集源为 clean `8ff75ea`，服务源为 clean `5cb5dab`。采用显式KV的efficient attention、`matmul-precision=high`（允许TF32）、新的公开结构声明、每成员20决策。原D1为每成员40决策；这些差异属于新Γ，不是同协议重试或单因素消融，更不是ID-VTDO算法改进。

采集UTC 14:51:51–16:31:36，实测5984.90秒（约99.75分钟）。全部16槽为 `model_budget_exhausted`，奖励资格均true、reward均0。952次决策对应952次HTTP/成功服务返回，没有未知usage；已报告输入9,620,150、输出56,279、合计9,676,429 tokens。没有为任何失败补采。

D2完整物化16槽，无不可用档案。每条 `V=(record=true, permission=true, basis=false, delivery=false)`，因此整体false；全部unmapped。允许的工具拒绝不自动破坏权限维度，记录完整也不替代依据和交付。四个独立窗口各M=4，每个成员的 `n_positive=0, v=0, b={}`，无组成自由度。独立来源簇/世界家族在本D1载体中仍各1；业务事实实例2、布局2，原与修订协议各登记4个情境指纹，不能因此声称8个独立问题来源。此次16个联合rollout产生48个成员episode投影，而不是48个独立团队结果。

| 成员 | 真实生成轮次 | 自身输出tokens | 完整语义/actor轨迹 | 基础actor资格 | 方法重配正支持 |
|---|---:|---:|---:|---:|---:|
| provider | 320 | 23,199 | 16/16 | 16 | 0 |
| implementer | 312 | 15,881 | 16/16 | 16 | 0 |
| reviewer | 320 | 17,199 | 16/16 | 16 | 0 |

952次生成中有82次合法staff_wait、2次staff_done；这84次控制决定不执行世界工具，其余868次为实际世界工具调用，外层ok=true为118、拒绝750。provider为319次工具调用（2成功/317拒绝），implementer为243次（87/156），reviewer为306次（29/277）。所有868次仍留在记录中，不能将952次生成均称为成功工具动作。

其中SQL build共17次：14次实际 `execution_status=success`，均生成metrics三行三列；另外3次在执行前被拒（1次缺basis确切采用、2次非工作owner），不是DuckDB引擎报错。另有8次submit成功、5次inspect_submission成功，但没有成功read_object或handoff_information，也没有approve。实际执行成功和提交存在不等于数值/依据正确，原16条奖励均0。由此不能将以下首例的“没有执行SQL”泛化到整个批次。

这些材料保留可信基础失败分支及权重1；并不表示本轮实际执行了训练。没有完整交接链，Mapper不会从话术或工具数量补一个类。API的三条有效语义经历、规则见证和原本地片段均不补此队列的支持。

按事先随机入队的**首例**做诊断，不按reward挑例：`d1e1-qwen-orders_a-split_b-1` 有61个机会、60次真实生成/工具调用，7次工具成功、53次拒绝。provider前12次重复同时传alias与object_id的读取；implementer后17次重复使用错误引用结构的通用request；reviewer最长9次重复歧义读取。检查的51条拒绝后续转移全部实际收到原错误反馈，其中38次随后仍用完全相同参数。其终点只有data采用和两次待回复audit请求，没有成功read、handoff、文件写入、SQL build、提交或批准；3次preflight调用返回结构不就绪。这一例停在工具参数与交接阶段，不能据此断言模型一般SQL能力为0。其他案例的逐项事实留在完整归档，不用此例替代全批统计。

新服务实际952次生成均关联本批；按真实batch group统计资源，不将单响应元数据重复相加。952个generation group合计5609.640秒，queue+generation合计5728.677秒；这些是所记录区间的墙钟时长，不是硬件活动时间积分。generation allocated峰36,184,238,080 bytes（33.699 GiB），相对当次基线的额外allocated峰5,713,023,488 bytes（5.321 GiB），reserved峰35.016 GiB。启动阶段7.915秒，预约/allocated峰34 GiB；从startup marker到停止共6266.285秒，含启动、准备、等待和服务工作，不与纯生成相加。预约、缓存reserved及实际计算峰分别报告。服务已在全部槽封闭后停止，确认本项目PID不再存在；没有停止其他进程。详见[新本地完整支持与资源归档](v012-idvtdo-support-qwen-efficient-r1.json)。

## 9. D3：完整多轮材料已接通，但训练按门槛未执行

新的训练入口使用完整多轮成员轨迹，而不是 v0.11 的三条首决策。基础配方是只读 Qwen base 加共享 LoRA actor、独立中央 critic；actor 只看到当时实际局部 token，critic 的结构特征只来自调用前的真实公开观察/动作前缀。工具返回、同事消息和输入位置不成为本人输出目标；模型实际生成的格式错误仍是本人动作。

固定槽、固定成员、该成员全部输出 token 的归一化保持不变。PPO 策略比与 q/b 组成权重分别处理；组成权重只作用 actor，失败残余权重为 1，无本人动作贡献零 actor 梯度，critic 不随 q 改写。CPU 检查从共同的小张量 AdamW 状态验证 Q=B 下完整损失、梯度、参数及优化器更新一致，也验证基础加残余形式和 mask 边界。`runs/multiturn-ppo-v012-cpu-final/report.json` 为 clean `09e45d9`，状态明确 `cpu_arithmetic_only`、模型 actor/critic optimizer steps 均 0、learning_gain_measured=false。

D3 还修复了一处静态对接缺陷：D2 为各 ξ 使用独立 `window_id`，原训练入口却要求四个情境 ID 相同。`f976224` 保留原窗口，以实际冻结采样协议、注册表、完整批报告、采样源、共同 Γ/团队策略和协议中的四个 repeat1 名单证明同批。没有改写 D2，也没有把该开发缺陷计为模型失败。

真实模型训练另外要求固定四槽的完整动作与可信回报、至少两个成员有多轮行为、实际回报差异及非退化优势、精确权重/profile 身份、输入长度和更新前概率门槛。无支持不自动禁止可信基础 RL；但没有真实 token、可靠回报或学习信号时不得用更新次数替代门槛。三条独立历史概率探针不等于这四槽已通过训练准入。

原协议在采集前固定四个repeat1：orders_a/split_a、orders_a/split_b、orders_b/split_a、orders_b/split_b，全部三角色、全部真实轮次。正式只读准入输出 `not_run_data_or_learning_signal_gate`、`errors=[]`，共恢复240次生成、14,669个自身输出目标token；最大完整input+output长度14,224，未裁剪（预设上限16,384）。通过的检查为：冻结服务身份、四槽可信完整记录、四情境同Γ/团队策略、至少两成员多轮行为、共享未改写base。未通过的是原独立D0门槛与可信回报差异（四个reward均0）。

因此实际 `training_happened=false`，actor/critic optimizer steps均0，`learning_gain_measured=false`。没有加载GPU执行该窗口的概率复算、梯度前向、优势计算或优化更新，也没有训练后fresh工作试验；这些项目保持未执行，不把三条历史概率探针或CPU合成算术记作已通过。预声明长度和概率阈值没有放宽。D3原始inventory、prepared材料、门槛报告及hash见新本地归档。

D4/D5 本轮均未执行。它们仍需足够的同情境支持、基础学习信号、共同 actor/critic/optimizer 起点、配对开发执行和通用成员—轨迹元重加权等强基线。不能仅优于均匀权重就宣称 ID-VTDO 的结构贡献。

## 10. 成本、分母与共享资源

以下按独立资源块记账；不同材料只加资源，不合并能力分母。金额按冻结单价形成估计上界，不是供应商账单，本地 GPU/CPU 成本未货币化。

| 已知材料块 | 段数 | HTTP attempts | 已报告 tokens | 未知用量 attempts | 已报告用量价格上界 / USD | 含保守预留的预算计费 / USD |
|---|---:|---:|---:|---:|---:|---:|
| dirty 开发 pilot | 2 | 11 | 73,342 | 0 | 0.008743776 | 0.008743776 |
| 正式 D0，两后端 | 16 | 186 | 2,240,612 | 7 | 0.221222208 | 0.240942108 |
| 正式 D1 DeepSeek | 16 | 627 | 6,585,116 | 7 | 0.654262368 | 0.818762868 |
| 以上三块资源合计 | 34 | 824 | 8,899,070 | 14 | 0.884228352 | 1.068448752 |

D1 DeepSeek 的 627 attempts 为 620 个完成返回加 7 个失败 attempt；623 decisions 还包括 3 次发请求前的预算边界，二者不能混作相同计数。未知用量不是零；仅此云批的未知保守预留为 462,319 tokens、0.1645005 USD。以上三块之外，旧Qwen D1共141 attempts、1,315,693个服务端可确认tokens（含一个未被客户端接收的9,867-token响应），4次失败真实用量未知；新Qwen共952 attempts、9,676,429个已报告tokens、未知0。只为资源加总时，本轮共1917次HTTP，已知采样用量19,891,192 tokens，其中9,867来自service-only记录；未知用量18次另列，不设为0。对应52个封闭episode和1个开放episode，另有0-world/0-HTTP准备错误及独立数值探针，不把它们构造成额外工作样本。

全部付费API仍是前三块：已报告用量的价格估计0.884228352 USD，加入未知保守预留为1.068448752 USD；不是账单。旧/新本地采集、两次加载失败、kernel与完整模型概率探针、CPU验证和D2/D3数据处理没有货币化，不能将API金额当作整个研究的总成本。没有正式模型更新、Contribution试训、探测开发执行、外层优化或独立泛化测试费用；相应实验未进行。

付费预算和有限调用上限在采样前声明，未知用量保留预算。用户授权共享 GPU；记录显存、利用率、进程和服务身份不意味着其他项目没有受到竞争影响。本项目只管理自身启动的进程，原 base 权重不覆盖。[保留核验](v012-idvtdo-preservation.json)在新采集进行中逐字节确认11个模型文件SHA256与原清单一致、80个旧实验JSON不变；采集结束并停止服务后，又核对11文件尺寸/mtime仍与原清单一致。后者是元数据核对，不冒称第二次完整字节hash。

## 11. 必要验证与尚存局限

验证按不同冻结和问题分别报告，不把重叠测试机械相加成“唯一测试总数”：

| 验证 | 已记录结果 | 实际范围 |
|---|---|---|
| D0 `17b5698` 全量回归 | 720 passed、3 skipped；Ruff 通过 | 当时冻结代码的完整回归 |
| D1 `09e45d9` 定向集成 | 71 passed、1 skipped；Ruff 通过 | 团队、有效性、多轮算术、manual 和相关 JSON 回归；含 10 个 manual 测试 |
| 正式 D1 程序矩阵 | 13 条、73/73 判据 | 实际世界、SQL、两路径和边界；不是模型采样 |
| 注意力/启动资源定向检查 | 18 passed、3 skipped | 新数值 adapter、mask/分组、资源生命周期及拒绝边界 |
| 公开结构定向检查 | 7 passed | 显式输出表结构与只读预检，不调用隐藏业务答案 |
| D3 跨情境同批准入 | 11 passed、1 skipped；Ruff 通过 | 保留各 ξ 窗口，以原采样协议和实际记录核验共同批次；损失实现未变 |
| 数值工程 probe | 2 个 tiny 长度；3 历史响应 × 2 模式通过 | 实际 profiler/概率/资源测量，不是工作成功率或训练 |

开发期失败与修复保留：manual 不可得回复的对象范围授权、通用 request 的自动回复旁路、规则驱动误用 issue 决策枚举、模型表名诊断、GPU5 加载竞争以及新协议摘要准入错误。部分早期 pytest 临时世界已清理，其开发观察在归档中明确不充当仍可复验的原始 before 证据；不虚构缺失文件。

仍有以下实质限制：

- 这是单个构造 SQL 工作家族和两种信息布局，不能宣称独立公开来源泛化或真实企业流程。
- 成员真实收到过材料与实际工具关系可验证，不证明内部推理质量或依赖的因果必要性。
- 当前 Mapper 只支持两个有限 handoff 结构，遇到更复杂或不唯一路径保持 ambiguous/unmapped，不运行后扩类收纳成功。
- D0 未通过、同 ξ 有效语义样本稀少和 API actor 轨迹缺失是不同阻塞，不能用一个 aggregate reward 遮蔽。
- 原 Qwen incomplete 配额不能伪造成完整 16 样本窗口；新 Γ 不能回填旧分母。
- 当前没有 Contribution、交互校正、在线闭环或工作能力学习收益证据。

## 12. 证据导航及复验入口

主文不复制巨大的 prompt、世界状态、SQL 版本树、token arrays 或权重。JSON 归档记录路径、SHA256、源身份和遗漏说明；原始运行目录继续保留，`/tmp` 证据可能过期，适用限制已经单列。

- [研究计划](../id-vtdo-v012-plan.md)、[D0 接口合同](../model-interface-v012.md)、[公开预检](../public-preflight-v012.md)。
- [三角色机制](../decision-team-v012.md)、[联合经历/有效性/支持](../team-rollouts-v012.md)、[多轮 PPO 合同](../multiturn-ppo-v012.md)。
- [D0 全部原槽与费用](v012-idvtdo-model-d0.json)、[机制判据与补修证据](v012-idvtdo-mechanisms.json)。
- [DeepSeek 完整普查](v012-idvtdo-support-deepseek.json)、[原 Qwen 中断分母](v012-idvtdo-qwen-interrupted.json)、[中断批资源账](v012-idvtdo-qwen-interrupted-resources.json)。
- [新协议采集前错误](v012-idvtdo-qwen-efficient-prestart.json)、[模型文件与历史 JSON 保留核验](v012-idvtdo-preservation.json)。
- [数值与资源归档](v012-idvtdo-numerics.json)、[数值技术说明](v012-numerics.md)。
- [新Qwen全16支持、真实多轮材料与D3准入](v012-idvtdo-support-qwen-efficient-r1.json)。

CPU 机制复验必须使用新输出目录，并结合归档中的冻结源码身份：

```bash
.venv/bin/python scripts/decision_team_experiment.py --output runs/decision-team-v12-recheck --jobs 4
CUDA_VISIBLE_DEVICES='' PYTHONPATH=src .train-venv/bin/python scripts/multiturn_ppo_v012.py --cpu-self-check --output runs/multiturn-ppo-v012-recheck
```

这些命令不应被当作重新采集模型支持的快捷替代。本轮最明确的变化是：已能恢复多名目标成员的完整真实动作，并将它与工作有效性、方法支持和实际学习门槛区分；当前尚不能利用这些结果宣称基础MARL学习或ID-VTDO算法收益。下一轮先解决开发池中的公开工具选择/引用合同与训练模型可用性，必要时进行各方法共用的格式冷启动，再重新采集当前策略材料。不得继续旧三条首决策训练或通过扩大同类失败配额替代该门槛。
