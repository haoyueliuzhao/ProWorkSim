# v0.35 P2 固定当前策略支持窗口

状态：`complete`；支持门：`no_configurable_support`；源码：`ccf756459d09e769235b25300477f5f98172be56`；原件：`/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v035`。

仅使用已选9B原完整3/3 common及固定v034呈现Γ；这不是fresh base。一个新训练用途根目标、一个精确情境、固定member_a先手和16个事前seed。每例共同128决定／128尝试／500000 token／32 tests；不采到成功或两类才停止。

P2只采集，不执行参数更新、贡献开发或独立确认。新来源与用途隔离，P1／历史开发记录未改标为训练；没有重复GPU资格、16K压力或用完即丢的生产诊断更新。

| 槽 | seed | 状态 | 完整R | 提交 | Mapper状态 | 方法 | 实际tokens |
|---|---:|---|---:|---|---|---|---:|
| v035-support-00 | 202610060801 | closed | 1 | True | mapped | own_tree_delivery | 488505 |
| v035-support-01 | 202610060802 | closed | 1 | True | mapped | own_tree_delivery | 400418 |
| v035-support-02 | 202610060803 | closed | 1 | True | mapped | own_tree_delivery | 487393 |
| v035-support-03 | 202610060804 | closed | 1 | True | mapped | own_tree_delivery | 493320 |
| v035-support-04 | 202610060805 | closed | 1 | True | mapped | own_tree_delivery | 489156 |
| v035-support-05 | 202610060806 | closed | 1 | True | mapped | own_tree_delivery | 314072 |
| v035-support-06 | 202610060807 | closed | 1 | True | mapped | own_tree_delivery | 489083 |
| v035-support-07 | 202610060808 | closed | 1 | True | mapped | own_tree_delivery | 496011 |
| v035-support-08 | 202610060809 | closed | 1 | True | mapped | own_tree_delivery | 433808 |
| v035-support-09 | 202610060810 | closed | 1 | True | unmapped | None | 411438 |
| v035-support-10 | 202610060811 | closed | 1 | True | unmapped | None | 436429 |
| v035-support-11 | 202610060812 | closed | 1 | True | unmapped | None | 494885 |
| v035-support-12 | 202610060813 | closed | 1 | True | unmapped | None | 416180 |
| v035-support-13 | 202610060814 | closed | 1 | True | unmapped | None | 456711 |
| v035-support-14 | 202610060815 | closed | 1 | True | mapped | own_tree_delivery | 489327 |
| v035-support-15 | 202610060816 | closed | 0 | False | unmapped | None | 490042 |

完整成功：15/16 已知；提交 15，未提交 1。未知／未开始不填零，未提交内容不补验。

| 精确情境 | 成员 | 原M | n+ | v | 类频数 | b | 状态 |
|---|---|---:|---:|---:|---|---|---|
| sp-script-inventory-v035::condition=T::active=member_a,member_b::first=member_a | member_a | 16 | 10 | 0.625000 | {'own_tree_delivery': 10} | {'own_tree_delivery': 1.0} | single_supported_class |
| sp-script-inventory-v035::condition=T::active=member_a,member_b::first=member_a | member_b | 16 | 10 | 0.625000 | {'own_tree_delivery': 10} | {'own_tree_delivery': 1.0} | single_supported_class |

原始可用训练材料：701 条本人决定、7125152 输入token、161626 本人输出目标token；最大真实序列 15656 token，总输入＋输出序列规模 7286778。
这只是静态真实材料规模，不是一次完整更新耗时。训练输入必须与原selected请求及原input IDs一致，目标仅为本人原output IDs与行为概率；不补回被公开反馈投影删除的信息。

后续状态：`finite_window_no_configurable_support`；首合格成员块：`None`。
无支持、只有一类、多类频数不足与形式自由度存在但梯度尚未验证分别记录。全部原16槽保持基础分母，可信失败／unmapped／低频及未选成员维持基础损失，不删样本后重新平均。

按当前n+/K计算的条件化后继规模：`None`。
任何贡献反馈前还须另冻类内核、完整探测方向与步长、唯一试训表、共同B复用、正式更新和公平预算。事前面板是2贡献根目标×2seed与另2确认根目标×2seed；P2未执行。真实概率／目标消费及完整反传合并进共同B试训。已有静态分配自由度不等于梯度或配置效果已可辨识。

新版分配接口复用既有logN、历史／覆盖双KL和B/G-raw/I-P求解器；只新增显式权重验证路由，原其余数值实现逐字节继承，不把旧G-lift冒称G-raw。

本阶段已闭合worker成本 11871.519520 GPU秒；运行中 0.000000秒。排队等待、旧阶段成本及CPU开发未叠成新采样GPU成本；未据P1采样时长承诺完整P3工时。

本报告不构成训练收益、分配增量或独立确认结论。正式B/G/I从同一完整common出发，试训不得累加；未冻结P3不会自动启动。
