# v0.16 OpenHands 受管工作人员适配

本开发线使用真实 OpenHands Software Agent SDK，固定 `openhands-sdk==1.49.6`，上游 tag `v1.49.6` 对应提交 `fcc102a697874d54a357e36004e02c95040dbdc0`。代码来源是 [官方软件代理 SDK](https://github.com/OpenHands/software-agent-sdk/tree/fcc102a697874d54a357e36004e02c95040dbdc0)，自定义工具结构参照该提交的 [官方例程](https://github.com/OpenHands/software-agent-sdk/blob/fcc102a697874d54a357e36004e02c95040dbdc0/examples/01_standalone_sdk/02_custom_tools.py)。上游源身份、安装环境和实际控制的证据分别归档；不以框架名称替代执行证据。

## 接口与边界

`harness_sdk.HarnessWorker` 为每个角色创建独立 SDK `Agent`、`Conversation`、私有事件和目录。`Conversation.run()` 实际调用上游 `Agent.step()`，模型通过 SDK `LLM.completion` 扩展点调用已有 transport。真实返回由上游构建 `ActionEvent`，自定义 `ToolExecutor` 唯一调用受管 `execute(name, raw_arguments, association)`，再通过实际 `ObservationEvent` 回写会话。收到 Observation 后调用 `Conversation.pause()`，将调度权交还世界运行时；下一角色可以继续。每次调度恰好一个模型生成和一个受管工具调用。执行后的动作不能再次交给旧 StaffRuntime 重复执行。

`association` 保留 `model_call_id`、`model_tool_call_id`、`decision_id`、角色、机会、模型和权重身份。模型请求、完整 transport 包络、响应中的原始 `token_trace` 直接进入既有 `model_call`、`model_attempt`、`model_response` 事件。SDK 事件是附加证据，不是训练 token 的来源。SDK 实际输入文本由它的会话事件产生，但原始生成 token 只接受实际模型 owner 的记录，不重新分词补造。

工具只来自角色 port 提供的公开 schema，再增加 `staff_wait`、`staff_done` 控制。默认 Finish/Think、终端、文件编辑、MCP、插件、condensation、后台 critic、自动重试均关闭。`Workspace` 仅保存该角色 SDK 会话，不充当业务访问授权。业务文件修改、查询、构建和提交仍经过世界网关；没有通用 Bash 或主机文件工具。

上游 Agent 会规范化工具别名和某些错误参数。为防止其成为隐式修复器，本适配先对**原始**工具名、单调用数量、严格 JSON、公开 JSON Schema 和保留字段做校验；Executor 再核对类型化 Action 与原参数相同。无法通过的输出完整归档并产生协议错误，不调用世界，不替换采样。`format_feedback_continue` 保留原规则：总错误 4 次或连续错误 2 次达到阈值后停角色；阈值前 SDK 会话收到带原响应 ID/SHA 的公开拒绝反馈，下一轮转机会才重新生成。原错误 assistant 只留在完整模型 ledger，不伪装成已修复 SDK 动作。`staff_done` 只停止本角色；普通无工具最终文本不隐式表示完成。原接口允许的精确 JSON `{"kind":"wait"|"done","reason":"..."}` 仍是显式控制：上游实际生成 `MessageEvent` 后，适配器通过 SDK 公开 `execute_tool` 调用对应的受管控制 Executor。此路径不伪造原生 `ActionEvent`、模型工具调用或后续 tool 响应；单独记录 `harness_explicit_json_control` 来源，业务世界没有变化。

## 明确的上下文选择

开发默认固定 `latest_observation_last4_tool_rounds`：保留 system、最新已登记的角色公开观测（含任务、角色私有 notes/todos）和最近 4 对完整 assistant/tool 回合。旧观察通过发送时的确切文本登记，而非猜测内容字段；历史配对按实际调用 ID 核对。未知来源的用户消息保守保留。每次记录完整与选择后 request SHA、消息 SHA、保留/移除索引和原因。SDK 全量事件仍保留；早期内容需要通过明确的局部历史检索工具取回。

上游 SDK 的 ActionEvent 序列化会规范化参数 JSON 的空白。后续实际请求中的 assistant 历史按调用 ID 恢复为已归档的原 assistant 消息，避免将 SDK 重写的表示误当模型原始输出。SDK 会合并连续 user 事件；桥接按原 TextContent 块恢复反馈/观察的消息边界，并记录原 SDK 消息索引与块索引，不改块文本。显式无工具控制保留为原 assistant 消息，不附加虚构工具返回。没有自动摘要、提示式答案、隐藏评价反馈或成功重采。此上下文支持属于整个 harness 组合，不能将组合结果归因为 SDK 的某个单项功能。

`refresh_transport` 只允许在机会之间更新 owner 引用与权重身份，并将新的 `identity.policy_version` 同步到 `config.model_revision`、下一次模型事件和快照，生成缓存和 SDK KV 缓存均不存在；历史工作记录保留，下一次必然重新调用 transport。`snapshot()` 保存角色会话 ID、完整事件与指纹、计量、权重身份和刷新序号；当前接口不宣称已支持跨进程自动重载 SDK 动态工具类。

## 独立环境与控制解释

旧筛选与已部署在线执行图不受此适配修改。SDK 环境位于 `runs/v016-sdk/`；真实模型兼容环境从原 `runs/v015-runtime/venv` 独立复制，维持 Torch 2.6.0+cu124、Transformers 5.17.0、PEFT 0.18.1、DuckDB 1.5.5，以及原 tokenizer/HF Hub 等数值栈版本。OpenHands 和其依赖只安装到新环境。

`tests/test_harness_sdk_v016.py` 使用明确的 CPU 确定性 transport 夹具，实际调用 SDK 会话、Agent、事件和 Executor。夹具检查角色私有性、单步暂停、真实错误反馈、权重刷新后的新调用、原包络不变、多调用拒绝、未授权工具拒绝、参数不自动修复，上下文完整配对、拒绝反馈后的下一机会恢复、连续格式错误停止，以及精确 JSON wait 控制。9 项控制全部通过；最初在只有 SDK 依赖的环境中收集测试时缺少项目 `openpyxl`，没有执行 SDK 控制，随后在包含项目依赖的独立 resident 副本中完成。日志和分项结果见 `docs/experiments/harness-v016-sdk-controls.json`；SDK wheel 内全部 295 个 Python 文件均与固定官方提交字节一致。夹具 token 是故意标明的哨兵，不能作为真实模型能力、训练数值准入或世界业务成功证据。真实世界和少量模型兼容检查另记。

建议运行时显式设置 `LITELLM_LOCAL_MODEL_COST_MAP=true`，使用已安装的模型元数据，不触发 LiteLLM 元数据远程查询。真实生成不经过 LiteLLM 网络客户端，而是调用传入的 resident/API transport；没有新增外部模型服务。
