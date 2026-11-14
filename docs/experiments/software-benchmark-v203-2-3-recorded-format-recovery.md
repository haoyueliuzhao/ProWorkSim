# 真实格式反馈后的上下文来源错位与 r3 修订

主体 r2 的九个正式回合均在 SDK 集成层终止。此次检查只读原 controller 归档、账本和源码，没有覆盖原轨迹、修改已封存 r2 或把旧失败改判为完成。财务结算与新恢复范围由独立执行回执负责；本文不把 CPU 回放算作新的模型调用或原会话续接。

## 原始证据与根因

对九个 `controller-output.tar.zst` 使用项目的 `open_verified_archive`，核对压缩档 SHA256 并完整排空、验证原始 tar 流的字节数与 SHA256，读取其中原件 `managed-runtime/experience.jsonl`。九个回合的 `interface_error` 均为 `ConversationRunError`，内部消息一致：`Candidate lacks the actual worker presentation registration`。发生前均已有格式反馈。逐回合原始错误与反馈保存在 [sdk-format-recovery-diagnosis-r1](../../artifacts/software-benchmark-v203-2-3/sdk-format-recovery-diagnosis-r1/summary.json)。

真实调用顺序是：原 v044 格式反馈投影先移除已经历史化的反馈消息，再由 v117 对历史 observation 做静态字段引用。v117 的 `rewritten_observations[].message_index` 属于**格式反馈投影之后**的消息坐标；旧角色 adapter 却直接用它索引投影之前的 `request.messages`。一旦前面移除了反馈消息，索引就可能指向反馈/工具/另一条消息，因此“不是当前 worker 注册过的 observation”检查正确拒绝了错误来源，但该异常又使整个 SDK 机会终止。

2032300 的真实 provider 响应中，member_002 第二次返回了两个 `search_repository` tool calls，按既有规则被拒绝；随后一次合法 `send_message` 使反馈历史化。用这些真实响应原样回放时，旧 adapter 在第八步精确复现失败：被移除的反馈原索引为 5，v117 投影后索引 5 实际应回到原索引 6。此前 25 个全部合法的编写动作控制没有覆盖这条真实格式拒绝→合法恢复→反馈移除的路径。

## 新修订的明确边界

新增 `software_role_context_runtime_v203_2_3_r3.py`，旧源码不变：

- K0 在原 Harness 返回 baseline 后直接返回 baseline，不再进行候选提取；候选追踪不能改变 K0 请求或引发此类终止。
- K1/K2 经原格式反馈返回的 `selected_indices` 将投影后索引映射到当前输入中的原索引，并验证单调唯一映射、user observation 注册、原文 SHA256 与 v117 marker 一致。
- condenser 改变过的当前输入也使用这份当次映射，不按历史全局索引猜测，不把已被 summary 替换而缺席的旧原件重新注入模型。
- 原来源缺失、映射不成立或 SHA 不符时，拒绝本次角色投影，原样返回原 v117 baseline，并记录明确的 `admitted=false`、原因和 `safe_fallback=original_v117_baseline`。这不是无损恢复或纯条件成功，后续分析必须记录这种处理偏离；本次正向诊断要求 fallback 为零。

角色排序、候选字段集合、4096 预算、原摘要算法和正式 provider counter 没有借本次修订改变。

## 实际 SDK 上的录制响应回放

新 `RecordedProviderReplay` 使用 [录制数据](../../config/v203-2-3-recorded-format-replay.json)，来自上述回合两位成员各自的 4/3 份真实 provider 返回；每份 JSON body 与原模型账本文件 SHA256 相同，包含真实的两个 tool calls 格式违规。没有手写一个“类似的错误”替代它，也没有修改原 body/usage。

CPU 回放在原始公开 `astropy/timeseries` 文件子集、真实固定 OpenHands SDK、真实世界及工具执行层进行。它不是原完整基准环境，不据此判断代码得分。七份录制响应用尽后，每位成员各一个明确标注的编写 `staff_wait` 仅用于结束诊断；这两个返回不是 provider 观测。

历史 usage 描述的是历史输入，不能伪称它是当前诊断输入的实际使用量。因此仅诊断 reservation 采用 `max(当前官方 recipe 本地计数, 该成员录制数据的最大历史 prompt_tokens)`，明确记录诊断 method、两个组成量和非当前 provider 计费。正式 counter 不变、团队上限不变，也没有新的现金扣费。首次 CPU 尝试暴露并保留了“历史 usage 大于较短新输入预约”的诊断会计问题；没有篡改历史 usage 来绕过它。

最终回放证据：[recorded-format-sdk-replay-r3-r2/summary.json](../../artifacts/software-benchmark-v203-2-3/recorded-format-sdk-replay-r3-r2/summary.json)。

| 路径 | SDK 机会数 | 原始真实响应 | 编写收尾响应 | 结果 |
|---|---:|---:|---:|---|
| 旧 K0 adapter | 8 | 7 | 0 | 精确复现已知来源注册失败，作为负控制 |
| 新 K0 | 9 | 7 | 2 | baseline 恒等，格式恢复后继续 |
| 新 K1 | 9 | 7 | 2 | 两次恢复投影使用真实重映射，fallback=0 |
| 新 K2 | 9 | 7 | 2 | 两次恢复投影使用真实重映射，fallback=0 |

另外八个必要局部控制通过：移除反馈后的索引映射、summary 后仅使用当前 literal 原件、缺失注册/错误映射/错误 SHA 的拒绝，以及三条件遇到候选来源缺失时的明确行为。这些控制不替代真实 SDK 回放。

全部回放为零网络、零新 provider 调用、零新现金费用；旧 provider 返回中的 usage 仍作为历史值保存。正式恢复前还需新 controller 的真实容器诊断走同一录制响应/SDK 路径。录制数据只允许在 diagnostic 配置中装入控制目录，正式配置不能携带或启用它，不能把此次 CPU 通过写成真实任务已经修复或已得分。
