# v0.16：真实 SDK 工作人员、独立开发世界与 H0 模型实验

日期：2026-09-27（Asia/Shanghai）。依据 [v0.15 审计](../reference/learning-audit-v015-harness.md)与[实施计划](../harness-v016-plan.md)。本轮完成真实 OpenHands Software Agent SDK 接入、独立六情境和四项目世界、3 个真实 9B H0 episode。原 S1 与原后继执行图继续使用各自冻结源；H1 配对与 H2 学习尚未执行。

**阶段结论：SDK 会话、受管工具后果与原始模型记录已在实际模型调用中接通；尚无新 harness 提升完整工作能力的比较证据，也没有新 SDK 下的参数学习或 ID-VTDO 增量结果。**H0 中正确构建未提交与未完成交接均保留，不因接口运行成功就改判业务完成。

## 审计要求与本轮对应

| 要求 | 实际落实 | 边界 |
|---|---|---|
| 原筛选及 N0/N1 不热修改 | S1 源 `1757373`、后继源 `14d3179` 保持，观察器继续运行 | 原 229 个后继 episode 仍是计划量 |
| selected 只表示相对排序 | 理论/计划/H1 manifest 保留岗位、事实、重复与成本；不追加业务通过率门槛 | 不据部分 S1 排名或认证能力 |
| 真正复用 SDK | 固定 SDK 1.49.6；实际 Conversation、Agent、Action、Observation、Executor | 未迁移整个 OpenHands 产品或训练器 |
| 工具受管且角色局部 | 唯一网关、角色私有 notes/todo/已获取历史、精确版本编辑 | 私有笔记不是正式事实或新的读凭据 |
| 实际 token 与当前权重身份 | resident 原包络/token/logp 保留；SDK 当前 actor 资格单独登记 | H0 无更新；刷新测试是 CPU 控制 |
| 独立 H0/H1 | 新开发实体；H0 三例已结束；H1 固定 48 例规划 | 原 S1 全部收口前不启动 H1 |
| 真实四项目消费 | P0→P1/P2→P3，两版合同、实际 SQL 和混合版本负例 | 程序见证，非模型成功率或已注册四项目奖励 |

研究设计同步明确：首先测量固定权重下的运行组合效应，再冻结 `(θ₀, Γ)` 测参数学习；ID-VTDO 配置增量还需同初始化、同预算的基础 RL 与通用重加权对照。旧 Γ₀ 窗口不能并入新 SDK Γ 的类别支持或训练效果。详见[研究目标与理论设计](../research/id-vtdo.md)。

## SDK、环境及接口

上游为 [OpenHands Software Agent SDK](https://github.com/OpenHands/software-agent-sdk)，版本 `1.49.6`，官方 tag commit `fcc102a697874d54a357e36004e02c95040dbdc0`。下载 wheel 的 295 个 Python 文件与固定官方源码逐文件相同，缺失和差异均为 0；[来源证据](harness-v016-sdk-source.json)保留逐文件 SHA。这是代码来源核对，不是上游完整功能或安全认证。

独立环境 `runs/v016-sdk/resident-venv` 保持 Torch 2.6.0+cu124、Transformers 5.17.0、PEFT 0.18.1、DuckDB 1.5.5、HF Hub 1.32.0 与 tokenizers 0.23.2。增加 SDK 依赖后 `pip check` 通过，原筛选环境未被更新。固定依赖见 [requirements](harness-v016-sdk-requirements.txt)。设置 `LITELLM_LOCAL_MODEL_COST_MAP=true`；实际模型计算经进程内 resident_direct，H0 网络 HTTP 模型调用为 0。

每个角色有独立真实 Conversation，一次机会至多执行一个模型工具决定。SDK Executor 是唯一执行入口，随后暂停角色并交还原轮转调度。实际世界动作仍经过 WorldCore；读取、采用、写入、SQL、固定提交和复核的后果不由 SDK 自行构造。没有默认 Bash、FileEditor、MCP、子代理、隐形规划/critic、语言模型摘要或自动业务修复。工具参数严格按原输出检查，不接受 SDK 隐式别名和参数补齐作为模型原动作。

新增工作辅助：有界私有 note/todo、仅搜索本角色实际获取的历史、对已读取且仍为当前版本的 JSON 字符串叶做显式替换。模型必须指定 alias、确切 reference、locator、文本和依赖；编辑经普通 `write_object` 形成真实新版本。编辑前机械版本查询单独记录且不冒充模型已看到的输入。固定提交浏览与真实错误沿用已有受管工具。

全部 SDK 事件保留；实际模型上下文固定取 system、最新角色观察、最近 4 个完整工具回合，并保留格式反馈。窗口之外的旧内容需显式历史查询，不让模型免费读取完整归档。实际输入投影保存索引及 SHA；原 resident 的 token IDs、行为概率和停止记录不重分词、不裁尾。SDK 工作支持同时改变上下文与工具组合，H1 不能把组合差异单独归因于“记忆”或“计划”。

实现说明见 [SDK 设计](../design/harness-sdk-v016.md)，[网关 CPU 控制](harness-gateway-v016-controls.json)。当前没有跨进程 SDK Conversation 恢复的验证，不扩大为任意中断恢复保证。

## 新开发世界和程序见证

固定 UCI 原来源另选 **12 客户、36 张完整发票、164 行**，与原 train/development/locked 的全部客户/发票互斥。六情境为实现 2、复核 2、pair 1、chain 1，仍使用原有限零售奖励。六条正例均 R=1；三条负例分别 R=0.2/0.25/0.25，共 9 个 CPU episode、79 次规则决策。它们只证明世界有可行和可区分的工作路径。

独立四项目运行有 97 次真实工具调用、7 次 SQL、5 条维护影响。初始合同下 P1/P2 均可开始，P3 实际消费双方结果；P2 改为半年净额合同后，维护义务产生但采用/代码/结果不自动更新。混合新指标与旧分析确实产生 `tests_failed`；显式更新和重新消费后恢复一致。客户 14834 从 49,705 便士/2 发票变为 −1,445 便士/1 发票。四项目准备及失败尝试完整保留。

详细数据偏好、源码和限制见[世界实验报告](retail-harness-v016.md)。这不是独立来源泛化，所选客户完整历史没有建立。四项目的 P2/P3 独立核验目前在报告中，尚未注册训练奖励，也没有共享模型自主四项目实验。

## H0：实际冻结、预算及结果

实际源提交 `7914e05381897b3cb8504287d7f31054a3a51032`，独立 worktree `runs/frozen-v016-h0`；协议 [h0-qwen35-sdk.json](../../examples/harness-v16/h0-qwen35-sdk.json)。固定 Qwen3.5-9B 修正 EOS 接口、FP32/highest、temperature 0.7、上下文 16,384、输出 2,048、原 full-attention q/v LoRA 范围。基座 HF revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a`，base manifest SHA `030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6`。

在 GPU 7 完成一次进程，退出码 0。三个 slot 事先指定，未成功重采或追加机会，actor/critic 更新均为 **0**；评价 guard 显示学习状态未变、Torch RNG 精确恢复，源前后相同。完整结果及证据 SHA 见 [H0 JSON](harness-v016-h0.json)。

| slot | 性质 | 实际生成 | 输入 / 输出 token | R | 实际成果与不足 |
|---|---|---:|---:|---:|---|
| public-interface | 公开指定步骤的接口校准 | 5 | 32,608 / 439 | 0 | 读不存在 alias 收到错误→读 code→仅改说明生成 v2→私有笔记→done |
| real-implementation | 有限真实实现任务 | 10 | 93,014 / 2,419 | 0.5 | 读取确切输入、正确实际构建；没有完成固定提交 |
| real-pair | 有限双成员工作 | 18 | 123,968 / 3,496 | 0 | provider 没有交接；implementer 反复请求/读取未共享依据，无构建与提交 |

总计 **33 次真实生成、249,590 输入 token、6,354 输出 token**。三例 record/permission 均为 true，但都未满足各自沿用的完整业务责任；第一例任务本来只为接口校准，不将“三例未完成”当作可比较业务完成率。SDK 实际给模型的原包络、token、概率及工具动作由闭合记录核对。完整令牌核对不等于重新进行概率前向复算或反向验证。

真实实现任务出现 1 次格式错误，原输出与解析诊断保留，未执行该建议动作；后续 6 次真实模型输入都保留公开格式反馈。双成员 18 次均可解析：provider 使用 6 次机会，implementer 使用 12 次；8 次真实世界拒绝均在同角色下一次请求、原生模板消息和渲染提示中找到同一错误 JSON。provider 工具集合始终含 `handoff_information`，但没有调用。因而当前记录不支持“格式反馈或最近世界错误被上下文投影丢失”这一失败解释，不为此重跑或改判。见[首例核对](harness-v016-h0-interface-readonly.md)与[双成员/反馈核对](harness-v016-h0-pair-readonly.md)。

H0 用时 **548.42 秒**，分配设备时间同为 548.42 device-seconds。15 秒采样共 37 次，自身 GPU 显存峰值 73,482 MiB、主机 RSS 峰值 1,866,560 KiB；GPU 7 同卡其他进程采样为 0。其他卡同时存在本项目原 9B/27B 筛选或校准进程，资源表保留 PID，但不能把“未登记在此 launcher 目录”直接归为另一个项目。采样峰值可能漏掉瞬态；分配设备时间不是 kernel 时间或 FLOPs。没有原生对照，不能据耗时声称 SDK 更快或更省。

加载时实际可训练参数 **1,114,112**，16 个 full-attention q/v LoRA 模块、32 个 A/B 张量；包含 adapter 的加载总参数 8,954,917,376。逐张量 shape/numel/dtype/device 已保存。DeltaNet 冻结，本轮无更新；同 rank 不代表跨架构相同适配容量。

### H0 元数据勘误与后继修订

冻结 H0 协议从原 S1 复制后，四个非执行说明字段遗漏更新：`budget_scope` 仍写 36 个筛选槽，`experiment_id` 仍为 `screen-chatstop-qwen35-9b`，`paired_original_protocol` 仍指旧筛选，`change_scope` 仍称 EOS-only。**这些描述不准确。实际执行的是明确 H0 stage 下声明的 3 个 slot，而非 36 个 S1 episode，也不是只改 EOS。**原文件、SHA、实际输出和评分不修改；[H0 摘要](harness-v016-h0.json)逐字保存勘误字段。新 H1 生成器从最小字段构造协议，避免继承旧描述。

首例还暴露一个真实包装缺陷：`ok:false` 世界返回对应的 SDK `GatewayObservation.is_error` 沿用默认 false。错误 JSON 原样到达模型，世界拒绝没有变成成功。后继 `openhands-managed-worker-v0.16.1` 将这个事件标记与 `ok:false` 对齐，CPU 控制确认给模型的 JSON 不增前缀、不变内容；**该修订未用于本次 H0，没有回写事件，也没有再做模型重采。**版本变更与核验见[SDK 控制](harness-v016-sdk-controls.json)。

开发控制中出现的依赖缺失、public payload 类型处理、测试 helper 参数冲突、SDK 最小 context 夹具和原 online policy 白名单问题均在开发阶段修订；不是正式模型零奖励。真实 SDK 的单步/暂停、角色隔离、格式继续、权重刷新和原始 token 控制，与真实 WorldCore 的版本/私有记忆控制分别记录。最终默认全库测试为 958 通过、24 个可选依赖跳过；独立 SDK 环境两文件 11 通过。之后 H1 生成/门禁定向 2 项通过，真实 CLI 确认规划协议在加载模型前被拒绝；Ruff 通过。分组有重叠，不相加冒称独立测试数。具体范围见 [验证记录](harness-v016-validation.json)。

## 原线状态、H1 与下一步

01:39（UTC+8）只读快照：原 7B 36/36；修正 9B 34/36 闭合；27B 3/36 闭合。27B 全部 18 个分片、55,563,006,776 weight bytes 已校验，S0 原生停止、有限概率复算、反向与保存重载通过，原队列已启动其 S1。S0 是短准入，不是计划规模训练稳定性或能力证明。原 continuation 仍 `waiting_screen`，N0/N1 和软件模型评价尚未产生本轮完成结果。时间绑定、源身份、部分成绩与 GPU 占用见[原线快照](v016-original-screen-snapshot.json)；后续更新另存，不覆盖这一观察时点。

H1 规划 **2 模型×2 harness×6 新开发情境×2 固定种子=48 episode**，每模型 24 例/最多 356 角色决策机会，native→SDK→SDK→native 四个窗口，纯评价、fresh 公共基座、0 更新。SDK 辅助工具同样消耗原有限机会。两 harness 保持业务目标、世界、奖励、精度、LoRA 与角色预算，测量运行支持组合效应。H0 已使用其中开发情境，H1 不能称未参与开发的锁定测试。

[H1 生成说明](../design/harness-study-v016.md)和[计划文件](../../examples/harness-v16/h1-plan/study.json)保留明确 `planning_only` 身份。正式启动门禁要求原三条筛选线收口、两新候选各 36 个闭合已知样本及匹配原报告/协议、H0 有限兼容审阅、最终源与模型身份绑定。缺证据时在依赖/模型加载前拒绝；本轮不自动把“27B 尚未完成”改称“只有一个候选可用”。资源另据实际占用安排，不驱逐其他项目，不热改原并行 lane。

H1 当前 **0/48 已执行**，未部署自动 H1 队列。完成原 S1 后，先保存完整分项报告并生成正式 admission，再在可用 GPU 上执行固定 H1；48 例比较收口后才能确定新 `(θ₀, Γ)` 并冻结 H2。H2 暂不扩大 LoRA、变更奖励、精度或训练后端。旧 Γ₀ 的 N0/N1 继续独立完成或按原门准确停止；其结果不合并成新 SDK 学习收益。
