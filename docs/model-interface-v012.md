# v0.12 模型工作接口开发合同（D0）

v0.11 的终止式协议及全部失败记录保留。v0.12 新增可显式选择的格式反馈续行协议，并冻结推理精度、注意力实现和本地提示投影的身份。这些是运行协议 Γ 的改动，不是训练或 ID-VTDO 调权收益。本文件描述实现与离线机制验证；实际模型结果须另按冻结批次报告。

## 1. 一次失败决策与一次真实世界动作分开

`ModelPolicy` 配置增加：

```json
{
  "action_protocol": "single_decision_json",
  "context_policy": "latest_observation",
  "format_error_policy": "format_feedback_continue",
  "format_limits": {"max_total": 4, "max_consecutive": 2}
}
```

默认 `format_error_policy="stop"` 仍在首个格式失败后终止。只有显式的 `format_feedback_continue` 启用新行为，两种动作协议（原生工具、单 JSON）均支持。累计和连续上限均为正整数；**达到任一上限的那次失败即停止**，例如连续上限 2 允许第一次错误后得到一次新的角色机会，第二次连续错误终止。一个格式正确的决定重置连续计数，不重置累计计数；真正的工具拒绝不算包装格式错误。

模型输出必须整体通过原有格式校验。多工具调用、坏 JSON、重复键、错误包装、输出长度截断等，均不取其中一部分执行，也不把 `kind=adopt` 自动改成 `kind=act`。实际响应和所有已发生的 HTTP attempt 原样记录。每次错误消耗一次模型决策及其实际 attempt/token/费用预算；续行仍受同一固定的模型与场景机会预算约束。没有本次 `decide()` 内的重采样。

可续行失败追加一条公开 `public_format_feedback` 用户消息，只含格式错误、当前协议、语法合同、计数和上限；不含隐藏正确数值、应选择的业务来源或下一步动作。策略返回 `protocol_rejection`，运行器记录 `model_format_feedback`、`decision_consumed=true`、`action_performed=false`。这不是世界工具调用，不前移世界时钟，不生成世界工具结果。角色轮转照常推进，模型只能在自己的下一次机会观察并决定；此状态不会被一次完整 idle sweep 误认为所有成员均在等待。

服务失败、未知用量、预算用尽、坏响应 envelope、缺失真实 assistant，以及 pending tool 与实际返回身份不匹配，不借此变成可重试的普通模型输出错误。它们继续使用已声明的终止边界。默认终止协议与可续行协议必须分别记入配置身份，checkpoint 不允许悄然换协议。

## 2. 原生工具错误历史的显式输入投影

原生响应如果携带多个调用或坏调用结构，既不能执行部分调用，也不能伪造 `role=tool` 的“执行结果”。直接把悬空 `tool_calls` 放回下一请求，还可能使 API 拒绝整个对话。

新协议保留 memory 中完整原 assistant 消息，同时登记其索引和 SHA256。仅在之后 HTTP 输入中，将这类**已经拒绝**的 assistant 消息投影为普通 assistant 文本：内容是包含完整原消息的 `rejected_assistant_response` JSON。这是一种公开记录的历史呈现，不是修改原始模型输出，也不是将其转换成正确世界动作。普通坏 JSON 文本无需这种投影，保持原文。

`context_selection` 对每条历史消息同时保存原索引、原 SHA256、是否进入请求、实际 wire SHA256 和 `projection`（`unchanged` 或 `rejected_assistant_as_data`）。请求体与服务实际 input token 仍另行保存。训练原错误决定时使用其当时实际 output IDs；未来决定的 input 使用其当时真正收到的投影后的 prompt IDs，不能用归档原文猜测当前输入。

## 3. 完整档案与模型当前上下文分开

已有 `full_history` 与 `latest_observation` 保持为明确配置。后者只移除此前已登记的公开观察消息；最新公开观察、角色任务、当前完整工具定义、所有真实 assistant 输出、工具返回和格式反馈仍按规则进入请求。完整历史留在 memory，原观察索引及移除理由留痕，不通过内容关键词猜测哪些消息“像观察”，不暗中摘要或裁剪输出。

D0 成组比较必须冻结上下文策略、输出上限与格式上限，并同时报告实际决策数、模型输入 token、保守预算预留和最终边界。名义允许 120 次决策不保证实际发生 120 次调用；`max_output_tokens=8192` 也不是唯一可用配置。若开发选择更小的输出上限，应在采样前声明，不能对产生截断的失败临时补发更大额度。

## 4. 本地服务的可冻结计算与提示配置

本地服务新增三个选项，默认保持 v0.11 的原选择：

```text
--dtype bfloat16|float32                 默认 bfloat16
--attention sdpa|eager                 默认 sdpa
--native-tool-prompt template_default|single_call
                                      默认 template_default
```

既有 `--max-batch` 继续显式记录，必须为正数。未来稳定概率复算可以在新批次预先选择 `float32`、单 batch；本修改没有执行 GPU，也没有声称该选择已经通过多轮 PPO 概率核验。

`single_call` 仅在请求实际包含原生工具定义时追加固定的公开语法提示，要求每个决定一个 `<tool_call>`、保留控制操作、不得发明工具结果。单 JSON 请求不受影响。服务保存原 HTTP request、实际归一化后的 prompt messages、实际 rendered prompt 及逐层摘要，故额外提示不会成为未记录的隐藏条件。

服务 manifest 和每次真实响应同时给出 `inference_profile` 与其 SHA256，含声明/实际 dtype、声明/实际 attention、提示选择、max batch、context limit 和 seed。`token_trace` 继续来自实际生成 IDs、实际采样 logits、温度、top-p/top-k；保留 EOS、完整输出、原 batch group/row/prefix width，不从文本重建。权重/adapter 身份与推理协议身份分别记录，不能只以模型别名判断两次行为分布相同。

## 5. 当前离线核验与实际实验边界

离线测试使用明确的模拟模型响应与真实 WorldCore 公开端口。验证覆盖：失败计费且无世界动作、下一机会与 checkpoint 续行、累计/连续双限、模型预算优先停止、格式正确但业务错误的真实拒绝、全部原生调用整体拒绝与可重建 wire 投影、输出截断、真实场景 idle sweep、私有角色材料隔离，以及本地推理选项和提示来源。旧模型接口/上下文/运行器/服务相关 54 项通过，新 D0 与服务配置 20 项通过；这是机制证据，不是模型工作成功率。

后续 D0 应在相同起点、模型与业务要求下，按预先固定的顺序随机化协议配置，保留所有格式、预算和业务失败。先检查多个实例上能否重复形成合法完整交付，再固定 Γ 采联合支持材料；不能边调提示边把成功池当作当前团队支持。公开来源/交付结构预检由世界接口另行提供，模型适配器不导入评价器，也不替工作人员补采用或依赖。

D3 将另建完整多轮、成员归属明确的训练材料和基础 PPO 合同，不继续训练 v0.11 的三条零奖励首决策。格式失败的自身生成 token 是真实动作记录；同事消息、工具返回、先前输出作为后来 prompt 的部分，均不成为当前输出目标。奖励可训练性、有效工作 V、可靠 Mapper 与可重配支持资格继续分开。
