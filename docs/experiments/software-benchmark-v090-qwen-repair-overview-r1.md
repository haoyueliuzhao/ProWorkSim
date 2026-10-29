# v090：Qwen 暂停、数据保存与修复准备

按用户要求，四卡 Qwen 队列已暂停，4 个专属模型服务及其显存预约已释放。原运行使用 GPU 2／4／0／5；只停止本项目已核实身份的服务，没有操作其他用户进程、GPU reset 或共享服务器配置。Qwen 不自动恢复。

## 已保存的数据

340、341、351 是此次行政暂停；345 在暂停信号之前已因 SDK 参数变换失败，不能归于暂停。四项完整 controller 归档、中间工作树、模型请求与返回、实际用量均保留；原导出回执通过完整往返检查。合计已知用量 14,639,072 token，340 另有 59,188 token 未决预约，未当作零消耗。部分未生成的终态文件已逐项列出，保存的轨迹不冒充可精确续跑检查点，中间工作树不计入正式正确率。详见[留存与 GPU 释放报告](software-benchmark-v090-qwen-pause-retention-r1.md)。

## 并行完成的修订

| 问题 | 本轮实现 | 目前证据与限制 |
| --- | --- | --- |
| 达到32,768输出上限，只有思考而没有动作；SDK随后再提示工具调用 | 独立识别已经完整结算的截断响应，保留原件并局部终止，阻止继续通用空响应纠正 | 19项 CPU 检查；这是止损策略，可能放弃后续可恢复的任务，不保证正确率提升 |
| 项目附加核验说明重复，搜索／测试反复给出同样结果 | 精简附加提示；相同可见结果只提示一次；明确区分失败、无效入口、零测试及管道退出状态不明 | 6项控制、167条历史公开 RPC 离线回放；没有禁止合理复测，不把公开测试当官方评分 |
| 上述修订仅有 helper，尚未进入真实 SDK 调用链 | 新 REF controller-session 工厂串接原计费／期限门、新反馈、新提示及截断处理 | 3项集成检查、4种真实 SDK 脚本场景通过；未接生产 PID1，仍需原宿主静止证明后才能导出和评分 |
| PROJECT 的合法 `cursor:null` 被 SDK 删掉后误判为参数改变 | 只在新受管 worker 的4个既有分页工具恢复明确允许的 null，继续原严格网关检查 | 40个 CPU 控制，包括真实 SDK 缺陷复现和执行链；未知键、缺少必需键及其他变换继续拒绝 |

所有修订均为独立新代码，没有热改旧运行源码，没有重跑旧题、加载模型或启动 Qwen。原生 OpenHands 和受管 PROJECT 的边界保持明确；这些修订不能被称为已经测得提速或得分增长。

细节：[截断策略](software-benchmark-v090-qwen-truncation-policy-r1.md)、[公开反馈与精简提示](software-benchmark-v090-public-feedback-r1.md)、[REF 接入](software-benchmark-v090-ref-controller-integration-r1.md)、[PROJECT cursor 修复](software-benchmark-v090-nullable-cursor-repair-r1.md)。

## 更直接的截断修复候选：为动作留下输出空间

vLLM 官方支持 `thinking_token_budget`：到达思考预算时生成思考结束标记，随后仍可在总输出上限内生成正文／工具动作；没有设置时，思考通常只受总输出上限约束。[官方说明](https://docs.vllm.ai/en/latest/features/reasoning_outputs/#thinking-budget-control)

本地固定 vLLM 0.32.0 的请求模型及状态机确有此实现。一次 CPU 控制使用本地 Qwen tokenizer 的真实思考边界 token、3-token 合成预算：预算前未请求结束标记、达到预算时请求结束标记、消费结束标记后解除强制状态；请求 schema 接受 `thinking_token_budget=24576` 与原 `max_tokens=32768`。该候选名义上为后续输出留下约8,192 token，不增加累计任务预算，也不保证一定产出有效工具调用。24,576 是待评估的工程候选，不是已经确定的最佳值。

这次没有测试 GPU logits 掩码、模型生成或端到端服务。最初直接使用安装包的 logits 方法时，其 pinned-memory 路径要求 GPU；该控制未通过，因此改为只核验官方 CPU 状态迁移，明确不作 GPU 资格结论。更早一次 SDK 环境缺少 vLLM 搜索路径，随后显式使用本地固定安装目录；这两次准备失败均未产生模型调用或 GPU 模型加载。[CPU 证据](../../artifacts/software-benchmark-v090/thinking-budget-CPU-validation-r1/result.json)

另一处边界也必须保留：当前 Qwen 模板会按最后用户消息裁剪历史思考。仅打开“回传 reasoning”开关，仍不等于能够在 SDK 追加用户纠正后续接原思考。因此本轮没有盲目注入思考文本，也没有把首截断终止包装成完整续写修复。

后续恢复前需单独冻结采用的策略、构建新运行包，并在限定真实验证通过后再讨论正式执行。用户当前要求暂停，以上工作到 CPU 实现与审阅材料为止。
