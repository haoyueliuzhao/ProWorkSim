# v090：Qwen REF 无动作输出截断的局部终止

当前为实现及 CPU 验证，**未部署、未启动模型、容器或服务**。此修订不修改已冻结的 v064／v066 等源码，也不改变已经运行的回合。

## 问题与本次选择

[v089 审计](software-benchmark-v089-ref-requirements-audit-r1.md)确认了一条具体路径：Qwen 一次生成耗尽 32,768 输出 token，但全部停留在思考中，没有工具调用或可见正文。原生 SDK 随后追加通用空动作纠正，而这段思考不会进入下一次模型输入。实际后续有恢复动作的例子，因此不能将其称为永久死循环；但它可能继续消耗大量时间和预算。

本次采用保守、可观测的处理：**首次确认此类响应后，保留完整原响应和实际费用，局部结束该回合；不继续进入通用纠正循环。** 新状态为 `qwen_reasoning_output_limit_without_action`，不伪造原生 `finish`，也不将它记成已完成任务。

这不是已证实更优的解题策略。提前结束可能牺牲原本可在下一次调用恢复的任务；未来结果必须作为独立执行版本记录，不能混入原 REF 组后声称同一配置提速或分数提升。恢复截断思考的续写方案尚未验证；本实现不盲目回传全部思考、不改变输出长度或采样、不重置额度。

## 触发与保留的边界

只有以下条件同时成立，才允许作为已知局部边界闭合：

1. 原生响应明确为 `finish_reason=length`，有非空思考，没有工具调用或非空可见正文。
2. 请求输出上限仍为32,768，实际完成 token 达到该上限。
3. 原响应已经由原适配器归档并结算；最后一条账本的响应哈希、响应身份、用途及用量精确对应这一响应，调用／决定数各增加1，总费用变化一致。
4. 没有在途调用、未知费用或账本矛盾；局部终止证据已持久化。

普通空响应、未截断的仅思考响应、具有正文或工具调用的截断响应仍保留原流程。摘要器也保持原流程。字段冲突、账本不确定、证据写入失败均保持技术异常，不能伪装成正常结束。

新适配器从干净会话起绑定一次，并在第一次确认的截断后禁止进一步计数和生成。即使已有另一调用排队，也不能越过这个边界。记录包含同一工作区身份、前后已观察工具 RPC 数和响应原件引用；**工具计数相同不等于证明文件树未变化**，因为此前启动的进程仍可能写文件。

最终候选仍须经原有可信静止检查后导出最后工作树，评分仍使用原官方评分器。是否具备可评分候选由原导出和评分流程判定；新边界本身不声明正确或错误，也不触发模型重跑。

## 接入接口

模块：[software_benchmark_qwen_truncation_v090.py](../../src/proworksim/software_benchmark_qwen_truncation_v090.py)。新控制器须显式选择此版本；不要替换旧模块的全局绑定。

```python
adapter = ReasoningTruncationAdapter(
    original_guarded_adapter,
    folder=output / "qwen-truncation",
    workspace_id=config["slot_id"],
    progress_snapshot=lambda: {"tool_rpc_count": len(rpc.transcript)},
)
# 将 adapter 交给原 v057 build_llm／ProjectionGuard。
# 原响应先由 delegate 落盘并结算；新边界发生在 SDK 处理空动作之前。
```

捕获 SDK 运行异常时，先调用 `unwrap_local_boundary(error, adapter)`。它只接受本适配器真实抛出的同一个异常实例（或 SDK 保持原 cause 的包装），并再次核对账本未变化、证据未丢失或被改写。返回空值则继续按原异常／资源边界处理。将返回值、`adapter.truncation_snapshot()` 和新部署版本写入结果；保持 `native_finished=false`，继续原静止、候选导出和独立评分路径。

仅包装 Qwen REF；DeepSeek 和 PROJECT 不受此模块影响。原权重、工具 schema、系统提示、种子、上下文、输入／输出限制、采样、总预算和实际计费不变。**改变的是已确认无动作输出截断后的生命周期规则。**

## 必要验证

[测试](../../tests/test_qwen_truncation_v090.py)覆盖响应分类、原件与完整费用保留、重复或排队调用被阻断、普通输出与摘要不变、未知账单及绑定不一致、冲突思考字段、证据失败／丢失、伪造异常及停止后账本变化。

[SDK 控制](../../tools/check_qwen_truncation_v090.py)使用现有冻结 OpenHands SDK 和一条预制响应，验证真实 `ConversationRunError` 包装能够识别、v057 投影健康检查保持通过、没有通用纠正或第二次生成。其 token 数是合成 CPU 测试单位，不是模型实测消耗；网络、模型权重、GPU 和仓库工具访问均受阻断审计。

最终19项检查通过，耗时9.94秒，Ruff通过；[验证记录](../../artifacts/software-benchmark-v090/qwen-truncation-CPU-validation-r1/validation.json)封存源码身份及实际 SDK 控制结果。

这组检查证明局部终止机制可用，不证明它改善正确率、降低平均费用或消除其他重复测试。性能和能力影响需要以后单独测量。
