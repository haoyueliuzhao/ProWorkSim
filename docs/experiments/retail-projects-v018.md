# v0.18 四项目可评性修复与 E4 机制控制

本轮已经把审计指出的覆盖问题推进到真实 WorldCore、原采集器、明确人工模型返回上的复现，并修订了汇总。完整记录的格式失败可保持已知 0/1；真正服务或身份缺口仍为 unknown。静态与一次变更的阶段报告已接入原四槽模型入口。此处所有新执行都是 CPU 机制控制，SDK 控制也使用人工 transport，没有新的真实模型采样或训练结果。

可机读结果、实际文件路径和 SHA256 保存在 [retail-projects-v018-controls.json](retail-projects-v018-controls.json)。原始 episode、响应、世界版本和首次失败夹具仍保存在仓库本机 `runs/retail-projects-v018-*`，没有重写为修订后的成功结果。

## 修订前的精确复现

审计依据为 7c03af875…。实际读取当前原函数后确认，覆盖集合确实含有 literal `model_format_error`，并非只经过 `policy_error` 间接触发。修改采集器前保存其 SHA256 为 `8f1ac2877019aad742f47fc78c4d1446b84addf763bdbd06c6e0dcc95dc1c1c5`。

主复现使用真实 WorldCore 和原 native ModelPolicy：P0 收到两次完整但协议格式无效的 HTTP200 返回，P1/P2/P3 各收到一次明确 done。5 份响应的原始正文均保留，实际返回中的 actor 身份全部与 fixture owner 相同。P0 以 `model_format_error` 停止；四项目真实固定终态未完成，独立 `assess_project_episode` 给出 eligible=true、R=0，原采集器随后覆盖成 eligible=false、R=null。该结果保存在 `runs/retail-projects-v018-before-fix-identity-bound/reproduction.json`。

这不是已观察到的真实模型失败，也不是只截取 if 分支运行的条件夹具：它运行了真实世界、策略解析、采集和闭合历史评价，模型返回则被明确替换为人工内容。主复现时整个工作树因新增测试及并行改动为 dirty；被测 collector 文件字节仍与上面的原版 SHA 相同。更早的 clean-tree 探针也复现了覆盖，但响应 body 未提供 actor_identity，故只作为较窄先行记录保留，完整身份绑定主复现才用于本次结论。

## 修复后的有界结果

| 控制 | 实际执行与结果 | 解释边界 |
|---|---|---|
| 四个原定槽均遇 P0 格式失败 | static-r0 / change-r0 / change-r1 / static-r1 全部完成采集，独立与研究 R 均为 0，记录可信；20 份人工响应，P0 共 8 次、其他角色各 4 次 | 其他角色与后续固定案例均继续，没有“未知即停”选择性减少这些已知失败 |
| 已完成世界之后再遇格式失败 | 真实 CPU 见证先建立正式完成世界；新 episode 后续 P0 格式失败，独立与研究 R 都保持 1 | 初始固定成果明确 inherited；不能归因为本次模型自主完成 |
| 服务无可用返回 | 独立终态仍可读为 0，记录存在实际服务缺口，研究 R=null | 没有把环境不确定性填成 0；其余角色仍得到自身机会 |
| 实际响应缺 actor 身份 | 独立 R=0，记录不可归属，研究 R=null | 请求里写了身份不能替代实际返回身份 |
| 准确世界拒绝 | P0 实际读取不存在的别名被内核拒绝，1 个真实回执匹配，最终已知 0 | 工具拒绝是已记录行为；不自动作为系统未知 |
| 复制的核验输入缺一次世界捕获 | 同一不被改写的原 episode，复制 capture 删除唯一实际调用后，记录核验失败，研究 unknown | 校验实际证据缺口；没有篡改保存的原始记录 |

两次未完成首版的 change 槽均报告 `triggered=false`、`handling_measured=false`、`initial_delivery_not_completed_change_not_entered`。它们的终局 R=0 保留，但不叫作“处理变更失败”。

独立业务评价与采集可信性被分别保存：`termination`、`record_trust`、`independent_assessability`、`independent_assessment`、`assessment`。这些输出的合同见 [设计补充](../design/retail-projects-v018.md)。原正式 P1/P2/P3 检查、隐藏真值边界和案例预算未变。

## 实际 SDK 的变更收件控制

另在 resident SDK 环境禁用可见 GPU，真实创建四个 SDK Conversation，执行真实 WorldCore 与明确人工 transport。为了控制“先 done、后收到新义务”的时间关系，沿用既有 CPU 见证的实际成果，再通过真实世界创建一项 P3 待交付责任并实际构建正确结果；人工响应只做该次明确 submit。P0/P1/P2 第一轮先 done，P3 的真实提交使四项目首版全部接受，随后原客户端事件实际发布第二版合同。

首版快照的独立 R=1；同一 episode 的终局 R=0、记录可信，后继工作确实没有完成。该 R=1 的 SQL 与产品来自预先 CPU 见证；不能说人工 transport 承担了业务计算，更不能说真实模型完成了项目群。

| 角色 | 新义务实际进入原始模型输入 | 收件前已用 / 剩余决策 | 会话与再激活 | 后继固定交付 |
|---|---|---|---|---|
| P0 | 无新义务，null | null | 无需再激活 | null |
| P1 | 是，第 2 个请求 | 1 / 43 | 同一 Conversation，1 次再激活，meter 未重置 | 未完成 |
| P2 | 是，第 2 个请求 | 1 / 43 | 同一 Conversation，1 次再激活，meter 未重置 | 未完成 |
| P3 | 是，第 2 个请求 | 1 / 43 | 同一 Conversation，保持活动，不需要再激活 | 未完成 |

实际共有 7 份人工模型响应、1 次由响应驱动的真实世界 submit。变更触发与收件均为 true，断点为 `change_entered_successor_delivery_or_quality_incomplete`。P3 没有再激活事件时 `reactivation_preserved_budget=null`，不能把“无需再激活”伪装成验证了再激活。

首个 SDK 夹具失败保留在 `runs/retail-projects-v018-sdk-controls/`：它一开始就继承全部完成世界，导致客户端变更在第一次模型机会之前触发，角色首个请求已看到新义务，没有经历先 done 再唤醒。测试却要求 `reactivation_preserved_budget=true`，因此失败。修改的是测试时间安排，上述修订夹具才真实覆盖再激活；没有把这次失败解释为 SDK 生产代码缺陷，也没有删去旧失败记录。

## 执行记录与限制

默认环境针对新文件运行得到 **5 passed、1 skipped，13.68 秒**；跳过的是需要实际 SDK 环境的控制。实际 SDK 分阶段控制单独运行得到 **1 passed、5 deselected，26.00 秒**，有 1 条上游 Pydantic 警告。首个时间安排错误的 SDK 夹具为 **1 failed、5 deselected，22.46 秒**。报告器严格版本绑定针对检查 **2 passed，0.08 秒**；最终新增 `initial-workers.json` 与诊断哈希一致性针对检查 **1 passed、4 deselected，1.14 秒**。改动文件 Ruff 通过。当前集成版本的一次完整默认测试为 **993 passed、29 skipped、0 failures/errors，pytest 报告 192.06 秒**（进程计时 192.561 秒），全库 Ruff 通过（0.053 秒）；结果独立归档在 [harness-v018-validation.json](harness-v018-validation.json)。

归档的 native/SDK 主控制早于几项最终元数据补充：fixture/概率说明、显式原末会话 ID、initial-workers 文件哈希，以及收件需实际成功响应的收紧。旧原始档案保持不变；其中保留的成功请求和返回支持相同收件结论，最后的启动元数据针对检查验证新增文件。不能把旧档案来源改写成后续源码。

这些结果支持有限接口与测量机制，不提供共享模型四项目能力排名、学习收益或真实概率重算证据。记录完整性检查不替代 resident 数值 guard，也未实现四项目 actor/critic 训练投影。新四项目模型运行仍须等待完整 H1 选择，并使用当前明确冻结的后继源；本轮未热改运行中的 H1、旧分母或旧奖励。
