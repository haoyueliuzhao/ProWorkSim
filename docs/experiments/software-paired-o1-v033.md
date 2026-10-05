# v0.33 同一O1根目标的单执行者／双成员有限诊断

状态：`ended_with_execution_stop`；执行源码：`6325ddb07b79b8d7573c1592cd76da33a32ff17d`；原始记录：`/data1/zhuxinrui/projects/ProWorkSim/runs/software-paired-o1-v033`。

仅9B与Devstral，两个相同根目标×S/T×两个固定seed，每模型8槽，总16槽。两条件共同团队总预算128次决定、500000 token、32次run_tests；T不按人数翻倍。旧三个候选无赢家结论不改，SWE不复测。

旧实际数值／16K／更新／恢复证据在同一common和未变数值实现下继承；没有新增三题资格、压力反向或诊断优化。普通schema错误保留原输出、实际消耗机会并反馈到共同预算，身份／权限／关键记录问题独立阻断。内容、规定API过程和完整固定交付分列。

| 模型 | 根目标 | seed | S完整R | T完整R | T-S | 配对观察 |
|---|---|---:|---:|---:|---:|---|
| qwen3.5-9b | mm-ledger-rootgoal | 202610050701 | None | None | None | unknown_or_not_started |
| qwen3.5-9b | mm-ledger-rootgoal | 202610050702 | None | None | None | unknown_or_not_started |
| qwen3.5-9b | mm-settings-rootgoal | 202610050701 | None | None | None | unknown_or_not_started |
| qwen3.5-9b | mm-settings-rootgoal | 202610050702 | None | None | None | unknown_or_not_started |
| devstral-small-2507 | mm-ledger-rootgoal | 202610050701 | None | None | None | unknown_or_not_started |
| devstral-small-2507 | mm-ledger-rootgoal | 202610050702 | None | None | None | unknown_or_not_started |
| devstral-small-2507 | mm-settings-rootgoal | 202610050701 | None | None | None | unknown_or_not_started |
| devstral-small-2507 | mm-settings-rootgoal | 202610050702 | None | None | None | unknown_or_not_started |

| 模型 | 条件 | 完整交付／已知 | 内容通过／已知 | 规定过程通过／已知 |
|---|---|---:|---:|---:|
| qwen3.5-9b | S | 0/1 | 0/0 | 0/0 |
| qwen3.5-9b | T | 0/0 | 0/0 | 0/0 |
| devstral-small-2507 | S | 0/1 | 0/1 | 1/1 |
| devstral-small-2507 | T | 0/0 | 0/0 | 0/0 |

后续支持采集决策：`no_local_team_carrier`；局部载体：`None`。

这不是追认旧v0.30候选入选，也不是通用模型或团队优劣排名。两个seed仅描述本开发复测；完整比较保持同根目标、初始代码／合同／验收、总资源和固定参数，S为T合法初始信息并集，T使用两个私有工作副本。

有局部团队可行性后应转入新训练来源的当前支持采集，不能把这些开发轨迹改作训练；必须再冻结实际支持、方法频数、可辨识梯度和公平可承担的B/G/I试训维度。没有自动追加本诊断、搜索模型或启动未冻结分配更新。

已闭合worker成本：2303.728234 GPU秒；当前运行：0.000000秒。

GPU成本为分配单卡worker墙钟；预约与worker总占卡应按每张卡的区间并集另算，不把二者直接相加。所有原先累计时限仍为None，单任务／内存／产物保护门保留。

本轮是工作行为诊断，零正式参数更新，无ID-VTDO效果或独立来源泛化结论。未开始／技术未知不补0分。完整团队预算账、逐槽结果、源状态及配对证明见JSON与服务器原件。
