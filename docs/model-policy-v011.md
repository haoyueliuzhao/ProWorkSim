# v0.11 模型策略薄适配合同

`ModelPolicy(config, transport=None, audit_dir=None)` 接收统一运行器给出的当前角色真实公开工具、观察和自身上次动作/返回。它没有 WorldCore、存储、领域评价器、业务答案、其他角色记忆或未来事件表；不调用规则策略补齐模型行动。角色 task 来自公开配置。可信 Python 接口不等于恶意代码沙箱。

## 两个明确协议

`action_protocol=native_tools` 将真实工具定义和两个适配器控制工具交给 API。一次响应至多一项原生调用；多调用整次拒绝，原始响应全部保留，不挑第一个，不重采样替换。`staff_wait(reason)` 只暂停当前工作人员，不推进世界时钟；`staff_done(reason)` 是工作人员停止声明，不代表已提交、批准或正确。done 在角色 memory 中保持，后续机会不再请求 API。

首次真实 native pilot 出现多调用后，另立 `single_decision_json` 协议，并在新 pilot/主批开始前声明。单 JSON 协议不发送原生 tools/tool_choice；角色的完整真实工具定义随公开观察进入 user 消息。响应只可为一个 `{kind:"act",action:"工具名",arguments:{...}}`，或者 `{kind:"wait"|"done",reason:"..."}`。实际 JSON 必须合法，不允许数组、多决策、额外键、重复键或原生调用混入。未知但语法有效的世界工具仍实际调用并保存真实拒绝；适配器不在幕后改成可成功动作。

DeepSeek 的官方 JSON 模式请求为 `response_format={"type":"json_object"}`，并要求提示中说明 JSON 格式；它不保证业务正确或符合本项目的决策字段。[官方 JSON 输出说明](https://api-docs.deepseek.com/guides/json_mode/)。本地 Qwen 仅按同样公开协议生成，没有声称受约束解码保证。

没有把未证实的 `parallel_tool_calls=false` 当作单调用保证。当前 Chat Completions 参数表未列出该开关；Responses 指南明确将其列为 ignored，但该事实不能外推成对 Chat Completions 私有参数行为的测量。[Chat Completions 参数](https://api-docs.deepseek.com/api/create-chat-completion/)，[Responses 参数兼容表](https://api-docs.deepseek.com/guides/responses_api/)。旧 native 失败不能替换或合并进新协议成功数。

## 对话、调用记录和恢复

模型不重新生成整份 memory。适配器追加发生过的 user observation、原 assistant message 和真实世界结果。原生协议用 tool_call_id 回应，JSON 协议用后续 user 消息中的 public_tool_result 回应，不伪造供应商原生 tool call。完整 assistant reasoning_content 原样保留；DeepSeek 工具调用会要求后续回传该字段，不能凭旧版本经验删掉。[官方 thinking/tool calls 说明](https://api-docs.deepseek.com/guides/thinking_mode/)。

每个机会有 opportunity_id，每个模型决策有 call_id/decision_id，每次 HTTP 有独立 attempt_id。model_attempt 保留完整请求、原始正文、解析后的响应、usage、状态、时间和重试依据；model_response 保留原完成体及供应商模型/完成标识；model_action_link 对齐实际世界动作、command ID 与原始返回。独立 audit_dir 可在尝试开始/结束时写入内容寻址记录；模型上下文不含日志目录。

checkpoint 保留角色真实对话、预算计数、待回应工具关联，以及运行器上次原始返回。一次世界动作刚完成时，该返回可能尚未追加到模型 messages，但已由运行器固定保存；继续时精确接入，不能从最终状态猜回结果。只承诺完整 step 返回后的继续，不承诺任意崩溃点下无重复计费或策略 exactly-once。

API key 从指定环境变量读取，不进入可序列化 config、memory 或请求日志。只记录变量名，拒绝嵌入 URL 的凭据及非法变量名。HTTP Authorization 不保存；供应商若在响应中反射凭据则明确标记遮蔽。明确 loopback 服务绕过环境代理；外部服务保持正常网络配置。

## 错误与固定预算

| 情况 | 保存和处理 |
| --- | --- |
| HTTP 超时、连接失败、限流或服务错误 | 原 attempt 保留；仅按冻结的状态/次数/退避重试相同 payload，耗尽为 model_service_error |
| 成功 HTTP 但 usage 缺失或不可用 | 保留原值，不猜实际用量；按准入预留保守记账并停止为 model_service_error |
| 格式错误、多个调用、不完整输出 | model_format_error，零世界动作，后续不隐式重新抽样 |
| 有效但错误的世界动作 | 真实执行一次，沿用世界真实拒绝分类；下次决策可看实际返回 |
| 固定决策、HTTP、token、金额、请求字节上限；后端明确 context_length_exceeded | model_budget_exhausted；不静默裁剪、摘要或续增预算 |
| 其他规则策略/适配代码异常 | 仍是 policy_error；不因使用模型就把全部异常包装成服务失败 |

固定配置包括模型/修订元数据、公开任务、温度、thinking、单次输出、超时、重试、价格和所有上限。thinking=None 代表不发送供应商参数。API 返回的模型别名不会被误称不可变权重身份。配置参与 checkpoint 身份比较。

reported token 计数来自实际 usage；缺失时保留 unknown 次数。下一调用的准入使用请求 UTF-8 字节数加明确消息/工具开销的保守估算，不声称精确 tokenizer 计数或数学证明。固定价格计算 cost_upper_bound，未知 attempt 用预留计入预算；这不是供应商账单。已计用量超过约定上限则在执行该返回动作前停止，并保留其真实响应。模型声称 done、工作人员等待、服务失败、预算截止、世界接受和内容正确是不同事实。

本轮 A0 使用明确模拟 transport 检查上述接口，不能记成真实模型表现。裸 TimeoutError 从替代 transport 逸出曾被误记 policy_error；开发反例与旧源码保留在 `runs/model-policy-v11-dev1`，现由传输边界保留事实、固定重试并归类为服务失败。正式模型批次、资源竞争和费用须另列实际结果。
