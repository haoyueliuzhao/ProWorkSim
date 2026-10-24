# v057 响应投影故障的共享终止保护

本修订处理实现审阅发现的错误路径，不修改原v056实验、旧响应或已结算账单，不重新运行旧模型回合。

## 为什么需要额外保护

新reasoning字段投影会对`reasoning`与`reasoning_content`冲突明确报错。普通Agent响应路径会让真实SDK抛出`ConversationRunError`，既有controller可将其记录为technical_unknown。

但是，OpenHands的`LLMSummarizingCondenser`会把任何摘要生成异常包装为`NoCondensationAvailableException`，SOFT摘要策略允许捕获该异常并返回原始历史。投影发生在原响应已经归档、用量已经结算之后，因此只检查账单完整性可能误认为可以继续生成或正常导出候选。

## 新的终止边界

`v057-exact-native-response-projection-r2-fault-guard`在新LLM工厂中绑定一个共享保护器。Agent及其`model_copy`得到的condenser共用这一保护器及原adapter／账本。

- 原响应仍先由原adapter完整归档并结算，再生成SDK投影。
- 任一投影、SDK转换或投影凭据写入发生异常，记录一次不可清除的故障状态。
- 后续`count`和`completion`在访问原adapter前拒绝，不产生新请求或重新计费。
- controller在认可closed、导出候选之前，另外检查同一故障状态；错误记录保留该状态。
- 不清零已消耗token，不重放失败请求，不放宽预算、时间、上下文或输出限额。

这使SDK即使对SOFT摘要采用回退策略，也不能掩盖本地响应适配错误。保护器本身不改变正常响应的字段映射或推理设置。

## 一次必要的真实SDK CPU控制

通过真实SDK构造90条合成历史，使用与生产相同的80事件／保留首4事件摘要配置。第一次摘要返回一份脚本化、已结算但reasoning双字段冲突的响应。

观察结果：SDK确实回退到了原历史；随后Agent尝试继续执行时，保护器阻止了新的模型访问，`Conversation.run`抛出`ConversationRunError`并进入ERROR。主动调用计数、completion及controller闭合检查也全部被拒绝。唯一脚本化响应仍记为1次condenser尝试、0次Agent决定、40个合成token单位，原始响应和已结算用量完整保留。实际模型、网络、GPU及官方评分调用均为0。

结果见[validation.json](../../artifacts/software-benchmark-v057/fault-guard-r2/validation.json)。此前正常路径CPU控制对应的normalizer/controller精确源码已归档至[control-source-r1索引](../../artifacts/software-benchmark-v057/revisions/control-source-r1/index.json)，原控制结果保留；本次未重复运行三个已经通过的正常路径场景，只新增该故障路径控制和针对性Ruff检查。
