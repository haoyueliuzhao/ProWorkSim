# v0.33r1 原固定单人／团队诊断的记录修复与未开始槽接续

状态：`waiting`；新源码：`ab6cd083beb33b4ffbccf48546d9394a34175ed3`；新原件：`/data1/zhuxinrui/projects/ProWorkSim/runs/software-paired-o1-v033-recovery`。

原 v030–v032 业务结果和候选筛选结论不改。此次确实修正 v033 的记录分类：原 T 行的 unknown 经离线成员视图重导出成为派生可信记录；原业务验收分数仍取原 assessment，原 v033 execution-stop 原件保持原样。四条已经执行的记录不重新验收、重采样或产生参数更新。这里只新执行原库存余下十二槽，每模型六槽；合并后仍是原两模型各八槽、共十六个逻辑槽。

同一原 common、原模型 profile、固定 seed、根目标、合同与初始信息关系不变；S/T 各有共同团队总上限 128 决定、128 尝试、500000 token、32 次 run_tests。没有新增资格题、16K 压力、优化步骤或自动重试。

| 模型 | 根目标 | seed | S 完整 R | T 完整 R | T-S | 配对观察 |
|---|---|---:|---:|---:|---:|---|
| qwen3.5-9b | mm-ledger-rootgoal | 202610050701 | 0 | 0 | 0 | both_failed |
| qwen3.5-9b | mm-ledger-rootgoal | 202610050702 | 未知/未开始 | 未知/未开始 | 未知/未开始 | unknown_or_not_started |
| qwen3.5-9b | mm-settings-rootgoal | 202610050701 | 未知/未开始 | 未知/未开始 | 未知/未开始 | unknown_or_not_started |
| qwen3.5-9b | mm-settings-rootgoal | 202610050702 | 未知/未开始 | 未知/未开始 | 未知/未开始 | unknown_or_not_started |
| devstral-small-2507 | mm-ledger-rootgoal | 202610050701 | 0 | 0 | 0 | both_failed |
| devstral-small-2507 | mm-ledger-rootgoal | 202610050702 | 未知/未开始 | 未知/未开始 | 未知/未开始 | unknown_or_not_started |
| devstral-small-2507 | mm-settings-rootgoal | 202610050701 | 未知/未开始 | 未知/未开始 | 未知/未开始 | unknown_or_not_started |
| devstral-small-2507 | mm-settings-rootgoal | 202610050702 | 未知/未开始 | 未知/未开始 | 未知/未开始 | unknown_or_not_started |

每一侧独立展示其已知结果；只有两侧都已知才计算 T-S。未知和未开始不补零。

| 模型 | 条件 | 完整交付／已知 | 内容通过／已知 | 过程通过／已知 | 未开始 | 技术未知 |
|---|---|---:|---:|---:|---:|---:|
| qwen3.5-9b | S | 0/1 | 0/0 | 0/0 | 3 | 0 |
| qwen3.5-9b | T | 0/1 | 0/1 | 0/1 | 3 | 0 |
| devstral-small-2507 | S | 0/1 | 0/1 | 1/1 | 3 | 0 |
| devstral-small-2507 | T | 0/1 | 0/0 | 0/0 | 3 | 0 |

后续决策：`pending`；新训练来源支持采集候选：`None`。
局部候选仍须该模型八条完整可信、common 保持一致且 T 至少一条完整交付；这不追认原 v030 winner。若无合格候选而尚有技术未知，不使用“全 T 为零”的研究分支。另一模型技术停止不会抹去一个已经完整合格模型的事前资格。

| 成本口径 | GPU 秒 |
|---|---:|
| 原 v033 两 worker 已记录成本 | 2303.728233814 |
| 本次新 distinct worker 成本 | 0.000000000 |
| 原／新区间同卡交集 | 0.000000 |
| 原／新已结束 worker 区间并集 | 2303.728233 |
| 当前新 worker 运行中墙钟（暂未闭合） | 0.000000 |

这些是按每卡 assigned→ended 区间计算的 worker GPU 秒，不代表 GPU 利用率；原成本、新增成本和并集分列。离线导出不新增模型调用或 GPU 工作，CPU 修订成本未计入。

| 记录来源 | 已观察槽 | 已记录模型尝试 | 已记录 token | 有用量记录槽 |
|---|---:|---:|---:|---:|
| offline_recovered_original_v033 | 4 | 138 | 1665658 | 4 |
| new_v033r1 | 0 | 0 | 0 | 0 |

用量汇总只覆盖有留存账本的观察行，未开始和未能导出的技术未知不会被猜测为零次执行。旧记录在合并视图只计一次，不把导出操作当新采样。每行列出原/新/派生来源和原件引用；完整 boundary、成员视图、transport、team ledger 只保存在服务器 runs 原件。

这仍是有限开发工作行为诊断，正式优化步骤为零；不能推出 ID-VTDO 收益、训练效果、通用团队优劣或独立来源泛化。后续训练必须使用新冻结的训练来源和当前策略采集，开发记录不转作训练。
