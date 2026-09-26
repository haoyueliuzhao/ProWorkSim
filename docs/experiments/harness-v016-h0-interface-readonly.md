# v0.16 H0 首条真实接口校准只读核对

核对对象是 `runs/harness-v016-h0-qwen35-sdk` 的首个已闭合 `h0-public-interface` episode（`785cddfa-764d-4aad-bc55-37c7ec59a2f6`）。实际执行来源为干净冻结提交 `7914e05381897b3cb8504287d7f31054a3a51032`，Qwen3.5-9B 使用 GPU 7。此检查只读取已闭合的 slot-0、其 resident 调用记录及世界文件；没有修改运行配置、重启模型、重算奖励或重演世界。

这是公开指定步骤的**接口兼容校准**：按要求读不存在的 alias，再读 code、仅修改说明字段、保存私有笔记、停止。它不是自主发现并完成真实业务任务的成功样本，也不是此前 9 项确定性 CPU 夹具的重复命名。

## 实際观测

共 5 次真实模型生成、5 个 SDK `ActionEvent`、5 个 `ObservationEvent` 和5次暂停，没有重试。动作依次为：

1. `read_alias(__harness_missing__)`：收到真实世界拒绝；回执 apply_delta 为空。
2. `read_alias(code)`：读取实际 v1；下一次模型请求确实包含前次拒绝的原始 JSON。
3. `work_replace_text`：受管网关唯一调用 `write_object`，创建 code v2。
4. `work_note`：只修改角色私有笔记。
5. `staff_done`：只停止工作人员。

模型生成的原工具名/参数、SDK Action、网关调用和 SDK Observation 内容均匹配。3条正式世界调用各自对应一个唯一 `command_id` 及实际 WorldCore提交回执，没有重复执行证据。code 的版本只有 v1/v2；文件逐项比较确认只变更 `config.description`，SQL、测试及其余字段不变。没有固定提交，校准所沿用的业务奖励为 **R=0、completed=false**，不将它重判为业务成功。

5个模型请求及完整响应包络分别与 resident owner记录一致；439个生成 token及其行为概率逐项等于原始记录，没有裁尾或重分词。每条生成均在原生EOS处结束，末尾之前没有EOS；概率长度一致且有限。温度0.7、top_p=1、top_k=0。此项是**记录保真核对**，没有重新前向复算概率或反向传播。

合计实际输入32,608 token、输出439 token，5次决策/5次调用，均在声明的10次决策/调用及token/context预算内。没有未知usage、格式拒绝或预算停止。旧公开观测确实按登记索引移除；第5次调用之前最多只有4个完整工具回合，因此本episode尚未实际触发“移除第5个历史工具回合”。本episode也没有生成格式错误，格式反馈继续的实际模型证据不能由此推断。

## 独立列出的表示缺陷

首条世界拒绝的 JSON 为 `ok:false`，但原 SDK `GatewayObservation.is_error` 为 `false`。这是包装层默认标记没有映射到世界结果的表示缺陷。错误文本原样出现在实际后续模型输入；世界拒绝回执、奖励与实际业务效果没有被改成成功。

这一原始记录保持不变。后继新 harness 可将已知 `ok:false` 映射为 SDK错误标记，但应另记版本与 Γ；不能修改本次冻结源码、旧事件或评分。`GatewayObservation.to_llm_content` 已显式直接返回原内容，因此可以单独修正事件标记，并验证不增加SDK默认错误前缀、不改变给模型的JSON。

完整13项只读检查、逐调用信息与证据SHA见 [JSON记录](harness-v016-h0-interface-readonly.json)。全部列出的只读检查通过，仅支持此一接口校准episode的有限结论；不代表全部H0、H1、跨角色隔离或在线学习试验已经完成。
