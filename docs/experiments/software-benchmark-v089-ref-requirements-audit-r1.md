# v089：Qwen REF 提示与运行要求审计

本次只读核对冻结的 v066 原生运行包、实际 REF 请求和已闭合的 slot329，不修改正在运行的实验，不调用模型或 Docker。项目侧相关源码 SHA 与冻结包清单一致。证据见 [静态审计](../../artifacts/software-benchmark-v089/ref-requirements-audit-r1/audit.json) 和 [空动作反馈路径](../../artifacts/software-benchmark-v089/ref-requirements-audit-r1/sdk-empty-response-path.json)。

**REF 没有混入 PROJECT 的多成员、固定补丁或正式提交要求。更具体的低效风险是：长思考触及输出上限后没有形成动作，原生 SDK 追加通用纠正，而截断的思考不会进入下一次 Qwen 输入。** 这一流程可恢复，不能据此称为永久死循环，也尚不能估计它造成的总时间或分数损失。

## 实际用了什么规则

| 部分 | 已核实的行为 | 对慢任务的解释边界 |
| --- | --- | --- |
| 原生系统提示 | slot329 首次 system 与 v054 冻结原生提示逐字相同。默认要求充分探索、重视质量、验证真实路径和边界条件 | 存在较强核验倾向；不能只凭文字推断耗时因果 |
| v062 附加流程 | 原题后增加需求清单、独立预期、聚焦复现和完成前核验提示 | 与默认系统提示有语义重复，但没有要求整个仓库测试全部通过 |
| 工具与交付 | `terminal`、`file_editor`、`task_tracker`、`finish`、`think`；无 MCP、浏览器、子 Agent；`delivery_endpoint=null` | 没有 PROJECT 的成员通信、`fix_patch`、`submit_integration`、同版本交付门。任务跟踪工具不等于团队任务板 |
| 卡住后的续接 | 最多两次，原会话、工作区、预算不重置；明确要求不要无依据重复读文件、命令或思考 | 可能延长一次已停滞的会话，但不是无限自动重试 |
| 完成后的自检 | 最多一次；已有充分证据可直接引用，不必重跑同一测试 | slot329 实际为零次，不能用这一规则解释该题长耗时 |
| 终端格式 | 原生解析器可拒绝裸的多条独立命令；允许明确拼接的命令或脚本 | v062 仅追加解释，不拆命令、不改写、不自动重试；这是原生工具约束 |
| 历史摘要 | 同一模型、共用原 token 账本；80 事件、保留最初4事件；还根据模型实际输入阈值触发压缩 | `max_tokens=null` 不表示没有输入门槛。摘要费用和摘要质量需要分别看 |

因此，准确描述应是：**原生 OpenHands 工具与冻结默认 system，加上本项目事前固定的修复核验和有限续接层。** 不能把整个 REF 执行流程写成完全未改的官方默认流程。

## 长思考后空动作的具体路径

冻结 SDK 先按响应是否有工具调用、可见正文或仅思考分类；仅思考／空响应都会被保存，然后追加“上一条没有函数调用或消息，请使用工具”的用户角色反馈。该分支没有区分 `finish_reason=length`，也不受 v062“最多两次 stuck 续接”的计数限制。

v057 已把供应商的思考正确保存在 SDK 事件中。但随后输入仍走 SDK 的原生序列化：Qwen 的模型名称不在 `send_reasoning_content` 白名单内，因此原始思考字段不回传。**“日志保留思考”与“下一次模型能看到思考”是两件事。** 当一次响应全部花在思考且被 32,768 输出上限截断，下一次看到的是原有可见历史、空 assistant 和通用纠正，而不是被截断思考的续写。

并行轨迹核查的 slot325 第201次响应为 32,768 个完成 token，全部计为 reasoning，结束原因为 `length`；第202次请求体现上述空动作纠正路径，但随后已恢复工具调用，见[实际轨迹结构](../../artifacts/software-benchmark-v089/qwen-performance-r1/slot325-trajectory-structure.json)。这说明它是会消耗预算的无动作路径，**不证明所有后续调用都被困住**。当前保留历史中的纠正次数也不能当作全程次数，旧历史可能已压缩。

这比“工具太多”或“强制反复审计”的笼统解释更具体，但本次没有验证改法。直接回传全部思考、扩大输出或更改纠正提示都会改变模型输入条件；不能热改后混入原冻结组。

## 一个已闭合任务的交叉核对

slot329 是 `django__django-12273`、QWEN_REF_B10000K：413次模型调用，其中397次 Agent 决定；累计 **9,952,186 token** 后因下一次完整输入与输出预约不足闭合，没有原生 `finish`。

- v062 追加过1次 stuck 纠正，0次完成自检。
- 摘要共84,213 token，占总量 **0.846%**；这是 token 比例，不是时间比例。
- 共10次原生多命令格式拒绝，全部无自动改写或重试。
- 首次 system 为15,180字符、user为3,393字符；长度仅用于核对输入，不能直接换算成性能损失。

以上是一个任务的证据，不代表全体 REF。默认提示与额外清单重复强调核验、展示仓库级测试入口可能影响测试选择，均仍属于待消融解释；未发现“必须全套测试通过才能结束”的规则。

## 源码定位

- 原生工具、默认 system、无子 Agent 及摘要参数：[native_v054.py](../../src/proworksim/software_benchmark_native_v054.py#L13)；RPC 保留原生 schema：[native_binding_v054.py](../../src/proworksim/software_benchmark_native_binding_v054.py#L135)。
- 自定义清单与有限续接：[native_control_v062.py](../../src/proworksim/software_benchmark_native_control_v062.py#L21)，实际触发判断在182–208行；REF 实际接入：[run_ref_controller_v066.py](../../tools/run_ref_controller_v066.py#L233)。
- 聚焦测试选择与原生拒绝提示：[public_context_v062.py](../../src/proworksim/software_benchmark_public_context_v062.py#L112)，反馈只追加说明见179–207行。
- SDK 冻结包内 `agent/response_dispatch.py:263–284,343–368` 为逐次空动作纠正；`agent/agent.py:812–834` 为响应分类入口；`llm/llm.py:2965–2984`、`llm/message.py:325–327`、`llm/utils/model_features.py:219–231` 为思考回传条件。具体文件路径、SHA和行号均见上述 JSON。

本审计没有变更运行配置，没有启动新实验，也没有把候选评分或隐藏测试材料提供给模型。
