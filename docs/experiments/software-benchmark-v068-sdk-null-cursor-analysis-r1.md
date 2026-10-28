# PROJECT `read_file` 的 SDK 参数投影错误：只读分析

## 已确认的原因

Qwen 的 slot 27（`scikit-learn__scikit-learn-11310`，PROJECT，750 万 token）在第 20 次调用时返回：

```json
{"cursor": null, "path": "sklearn/model_selection/_search.py"}
```

这符合实际发送给模型的公开 schema：`cursor` 明确允许 string 或 null，工具说明也允许省略、null 或空字符串表示第一页。项目底层 `_action_read_file(..., cursor=None)` 和 `_position()` 同样支持这一语义。

OpenHands SDK 1.49.6 的 `agent.utils._normalize_arguments` 会删除所有值为 `None` 的顶层字段。因此，SDK 解析后的参数以及 Action 的实际投影都变为：

```json
{"path": "sklearn/model_selection/_search.py"}
```

项目 `harness_sdk._GatewayExecutor` 将这一投影与保留原始参数的 `pending["arguments"]` 严格比较，不相等即抛出 `SDK transformed arguments; managed gateway was not invoked`。异常继而成为 `execution_integrity_error`，终止整个 episode。这次没有调用受管读文件入口，也没有世界状态变更。

该回合实际完成 20 次模型调用、消耗 1,248,225 个输入加输出 token，预算上限 7,500,000，账单完整且没有在途预约。此次终止由接口一致性判断触发，不能归因为 token 用尽，也不是模型违反公开参数 schema。

## 频数及统计边界

统计依据是 v068 恢复前冻结的合并 inventory，包含原 v064、R3 的有效 Qwen 记录和 v067 的 API 记录；不包含正在运行的 v068 新结果。按不同 episode 去重，同一错误在 boundary、终态和 outcome 中重复出现不重复计数。

| 项目 | Qwen PROJECT | DeepSeek PROJECT |
| --- | ---: | ---: |
| 冻结快照中的技术未知 | 6 | 85 |
| 有完整 controller-result 可检查 | 1 | 1 |
| 明确出现本错误的 episode | 1 | 0 |

Qwen 已确认的 1 项占其 6 项 PROJECT 技术未知的 16.7%。其余 5 项没有完整 controller 终态，不能据此排除所有潜在的类似问题。

DeepSeek 的 85 项中，80 项没有实际 API 请求，是环境创建后的 guard／取消问题；剩余 5 项有 API 请求，其中只有 1 项有完整 controller-result，该项记录的是 `ManagedTransferError`，不是本次参数投影错误。因此只能说“未确证 DeepSeek 出现本错误”，不能把 0 解释为该接口对 DeepSeek 已验证无风险。

## 后续最小修订方向

优先考虑接受**已证明仅由 SDK 删除顶层 None 字段造成的投影差异**，同时仍将完整原始参数传给受管 gateway：原始模型 response、`pending`、工具调用 ID、实际 usage 和世界执行参数都保持不变。不能泛化为接受任意参数变化，也不能关闭执行身份检查。

候选接受条件应包括：原始参数通过公开 schema；被删除的每个字段确实为 None，且 schema 明确允许 null；SDK 投影恰好等于原始参数删除这些字段后的字典；没有新增、重命名、类型转换或其他值变化。该工具的省略／null 语义需要独立验证。当前 `read_file.cursor` 的源码和公开约定符合这一候选方向，但不能据此自动扩展到所有工具。

另一种办法是将差异改成局部反馈、允许后续机会纠正，但这会让模型为一个公开允许的参数额外支付行动成本。因此不优先采用对合法 `cursor:null` 的拒绝反馈；对于尚未证明可接受的参数变化，仍应拒绝，真实来源或执行身份异常继续保留硬边界。

实现需要新的 managed worker／gateway 适配模块、选择新 worker 的 PROJECT controller，以及明确的新 SDK bundle 与部署 revision。旧 `harness_sdk.py`、已冻结 bundle 和旧结果不得热改。模型、预算、官方评分器无需因此改变；新的接口版本须单独记录，不把旧失败工作区补记为成功。

## 本次验证及未做事项

已在正式私有 Python／实际 OpenHands SDK 中，用保存的原始 request 和 response 只读重现：原始参数通过 JSON Schema，SDK 删除 `cursor:null`，Action 投影只剩 path。此检查没有 Conversation、gateway 执行、模型、API、Docker 或 GPU 操作。

这只是故障机制重现，不是新接受规则的验收。后续还需要真实 SDK 的程序化控制，验证合法 null、正常省略、其他参数篡改、多次执行和记录归属等边界，并确认 gateway 获得原始参数。本次未实现接受或拒绝新规则，未重新打包，也未更改当前运行。

精确原件、源码路径及计数见 `artifacts/software-benchmark-v068/sdk-null-cursor-analysis-r1/evidence.json`。
