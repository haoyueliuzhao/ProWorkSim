# v0.28 真实软件开发运行记录

更新时间：2026-10-03T19:44:59.408424+08:00（北京时间）。

本轮接口修订：`software-collaboration-v0.28.1`；上下文策略：`software-context-v0.28.1`；源码：`df37917d0a2b8555125d0bd57309a897be9dd2f5`。

本报告为显式授权恢复的八槽状态总账：保留全部已闭合结果（含失败），原未知尝试单独保留。新旧接口结果可以汇总完成状态，但不能混同为相同协议的效果统计。

监督状态：`complete`。计划8条，已启动8条，可评8条；启动后未知0条、未启动0条。

已知完整职责4/8；完整原分母比率：0.5。

这是2个开发情境×2种先手×2个固定seed的冻结参数运行，零更新。旧Marshmallow仅作接口开发，不是正式训练支持、独立算法确认或B/G/I效果实验。

| 槽 | 先手 | 状态 | 已知完整职责 | 结果来源 | 原始轨迹 |
| --- | --- | --- | --- | --- | --- |
| dev-0-first-0-r0 | member_a | closed | 1 | attempt0 / software-collaboration-v0.28 / latest_observation_last4_tool_rounds | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-open-runtime/worker-0/actual/dev-0-first-0-r0` |
| dev-1-first-0-r0 | member_a | closed | 0 | attempt0 / software-collaboration-v0.28 / latest_observation_last4_tool_rounds | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-open-runtime/worker-0/actual/dev-1-first-0-r0` |
| dev-0-first-0-r1 | member_a | closed | 1 | attempt0 / software-collaboration-v0.28 / latest_observation_last4_tool_rounds | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-open-runtime/worker-0/actual/dev-0-first-0-r1` |
| dev-1-first-0-r1 | member_a | closed | 1 | attempt0 / software-collaboration-v0.28 / latest_observation_last4_tool_rounds | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-open-runtime/worker-0/actual/dev-1-first-0-r1` |
| dev-0-first-1-r0 | member_b | closed | 1 | attempt0 / software-collaboration-v0.28 / latest_observation_last4_tool_rounds | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-open-runtime/worker-1/actual/dev-0-first-1-r0` |
| dev-1-first-1-r0 | member_b | closed | 0 | attempt1 / software-collaboration-v0.28.1 / software-context-v0.28.1 | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-context-recovery/worker-1/actual/dev-1-first-1-r0` |
| dev-0-first-1-r1 | member_b | closed | 0 | attempt1 / software-collaboration-v0.28.1 / software-context-v0.28.1 | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-context-recovery/worker-1/actual/dev-0-first-1-r1` |
| dev-1-first-1-r1 | member_b | closed | 0 | attempt1 / software-collaboration-v0.28.1 / software-context-v0.28.1 | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-context-recovery/worker-1/actual/dev-1-first-1-r1` |

尝试历史（not_started仅表示该轮计划，未发生模型尝试）：

| 槽 | 尝试轮 | 原状态 | 来源提交 | 原始轨迹 |
| --- | --- | --- | --- | --- |
| dev-0-first-0-r0 | attempt0 | closed | `24dbc01eb0d3295a7844b1c8e08fb5c19168fd75` | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-open-runtime/worker-0/actual/dev-0-first-0-r0` |
| dev-1-first-0-r0 | attempt0 | closed | `24dbc01eb0d3295a7844b1c8e08fb5c19168fd75` | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-open-runtime/worker-0/actual/dev-1-first-0-r0` |
| dev-0-first-0-r1 | attempt0 | closed | `24dbc01eb0d3295a7844b1c8e08fb5c19168fd75` | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-open-runtime/worker-0/actual/dev-0-first-0-r1` |
| dev-1-first-0-r1 | attempt0 | closed | `24dbc01eb0d3295a7844b1c8e08fb5c19168fd75` | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-open-runtime/worker-0/actual/dev-1-first-0-r1` |
| dev-0-first-1-r0 | attempt0 | closed | `24dbc01eb0d3295a7844b1c8e08fb5c19168fd75` | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-open-runtime/worker-1/actual/dev-0-first-1-r0` |
| dev-1-first-1-r0 | attempt0 | execution_unknown | `24dbc01eb0d3295a7844b1c8e08fb5c19168fd75` | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-open-runtime/worker-1/actual/dev-1-first-1-r0` |
| dev-1-first-1-r0 | attempt1 | closed | `df37917d0a2b8555125d0bd57309a897be9dd2f5` | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-context-recovery/worker-1/actual/dev-1-first-1-r0` |
| dev-0-first-1-r1 | attempt0 | not_started | `24dbc01eb0d3295a7844b1c8e08fb5c19168fd75` | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-open-runtime/worker-1/actual/dev-0-first-1-r1` |
| dev-0-first-1-r1 | attempt1 | closed | `df37917d0a2b8555125d0bd57309a897be9dd2f5` | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-context-recovery/worker-1/actual/dev-0-first-1-r1` |
| dev-1-first-1-r1 | attempt0 | not_started | `24dbc01eb0d3295a7844b1c8e08fb5c19168fd75` | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-open-runtime/worker-1/actual/dev-1-first-1-r1` |
| dev-1-first-1-r1 | attempt1 | closed | `df37917d0a2b8555125d0bd57309a897be9dd2f5` | `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-context-recovery/worker-1/actual/dev-1-first-1-r1` |

GPU累计占用 1.605299 小时（终态）。

累计GPU时长上限：不设；每worker GPU时长上限：不设；全局墙钟截止：不设。最多1个模型实例；每成员48次决策，context16384/output2048。在GPU5等待空卡，等卡截止北京时间2026-10-06 00:00；未沿用旧v0.26预算或期限。

已登记原始轨迹文件 4581 份。索引：`/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v028-software-dev-context-recovery/trajectory-index.json`。

另计GPU预留占用 0.241815 小时；与上述模型worker占用分列，预留期间模型调用为0。

归档包含生成前请求、原始响应和token、SDK事件流、实际工具返回、世界版本/结束快照、独立验收、Mapper证据与冻结状态guard。中断时已产生的记录保留；没有返回的生成不补文本或token。

同名JSON保存逐槽实际调用及原始结果。8个最终选用结果的逐条内容审阅已完成，原技术未知attempt的根因另有保留，见[完整审阅记录](software-development-v028-context-repair.md)。恢复轮172次响应均HTTP200，无上下文超限；3条均未提交固定集成交付。自动消息数、领取数或测试数不代表协作质量、因果贡献或学习效果。

[新协议](../software-allocation-v028-plan.md) · [实际SWE-smith来源资格](software-sources-v028.md) · [机器记录](software-development-v028-recovery.json)
