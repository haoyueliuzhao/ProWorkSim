# v0.36 P2 固定当前策略支持窗口

状态：`complete`；支持门：`ready_for_postcollection_freeze`；源码：`e26ab99df8e555cd144eef2b38641174addb28d7`；原件：`/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036`。

仅使用已选9B原完整3/3 common及v036成员自测反馈／Γ（原v034容量与去重算法保持）；这不是fresh base。沿用原训练用途根目标、一个精确情境、固定member_a先手和16个事前seed。每例共同128决定／128尝试／500000 token／32 tests；不采到成功或两类才停止。

P2只采集，不执行参数更新、贡献开发或独立确认。新来源与用途隔离，P1／历史开发记录未改标为训练；没有重复GPU资格、16K压力或用完即丢的生产诊断更新。

| 槽 | seed | 状态 | 完整R | 提交 | Mapper状态 | 方法 | 实际tokens |
|---|---:|---|---:|---|---|---|---:|
| v036-support-00 | 202610070101 | closed | 1 | True | mapped | evidenced_peer_product_delivery | 453716 |
| v036-support-01 | 202610070102 | closed | 1 | True | mapped | local_lineage_delivery | 431382 |
| v036-support-02 | 202610070103 | closed | 1 | True | mapped | local_lineage_delivery | 487641 |
| v036-support-03 | 202610070104 | closed | 1 | True | mapped | evidenced_peer_product_delivery | 358444 |
| v036-support-04 | 202610070105 | closed | 1 | True | mapped | local_lineage_delivery | 497993 |
| v036-support-05 | 202610070106 | closed | 1 | True | mapped | evidenced_peer_product_delivery | 437096 |
| v036-support-06 | 202610070107 | closed | 1 | True | mapped | local_lineage_delivery | 480748 |
| v036-support-07 | 202610070108 | closed | 1 | True | mapped | evidenced_peer_product_delivery | 436195 |
| v036-support-08 | 202610070109 | closed | 0 | False | unmapped | None | 490814 |
| v036-support-09 | 202610070110 | closed | 1 | True | mapped | local_lineage_delivery | 496720 |
| v036-support-10 | 202610070111 | closed | 1 | True | mapped | local_lineage_delivery | 494341 |
| v036-support-11 | 202610070112 | closed | 1 | True | mapped | local_lineage_delivery | 398548 |
| v036-support-12 | 202610070113 | closed | 0 | False | unmapped | None | 497828 |
| v036-support-13 | 202610070114 | closed | 1 | True | unmapped | None | 414682 |
| v036-support-14 | 202610070115 | closed | 1 | True | mapped | local_lineage_delivery | 313932 |
| v036-support-15 | 202610070116 | closed | 1 | True | mapped | local_lineage_delivery | 435867 |

完整成功：14/16 已知；提交 14，未提交 2。未知／未开始不填零，未提交内容不补验。

| 精确情境 | 成员 | 原M | n+ | v | 类频数 | b | 状态 |
|---|---|---:|---:|---:|---|---|---|
| sp-script-inventory-v035::condition=T::active=member_a,member_b::first=member_a | member_a | 16 | 13 | 0.812500 | {'evidenced_peer_product_delivery': 4, 'local_lineage_delivery': 9} | {'evidenced_peer_product_delivery': 0.3076923076923077, 'local_lineage_delivery': 0.6923076923076923} | formal_composition_freedom_gradient_unchecked |
| sp-script-inventory-v035::condition=T::active=member_a,member_b::first=member_a | member_b | 16 | 13 | 0.812500 | {'evidenced_peer_product_delivery': 4, 'local_lineage_delivery': 9} | {'evidenced_peer_product_delivery': 0.3076923076923077, 'local_lineage_delivery': 0.6923076923076923} | formal_composition_freedom_gradient_unchecked |

原始可用训练材料：682 条本人决定、6964120 输入token、161827 本人输出目标token；最大真实序列 15906 token，总输入＋输出序列规模 7125947。
这只是静态真实材料规模，不是一次完整更新耗时。训练输入必须与原selected请求及原input IDs一致，目标仅为本人原output IDs与行为概率；不补回被公开反馈投影删除的信息。

后续状态：`ready_for_postcollection_freeze`；首合格成员块：`['sp-script-inventory-v035::condition=T::active=member_a,member_b::first=member_a', 'member_a']`。
无支持、只有一类、多类频数不足与形式自由度存在但梯度尚未验证分别记录。全部原16槽保持基础分母，可信失败／unmapped／低频及未选成员维持基础损失，不删样本后重新平均。

按当前n+/K计算的条件化后继规模：`{'n_positive': 13, 'K': 2, 'unique_trial_updates': 27, 'development_episodes': 432, 'formal_updates': 3, 'independent_confirmation_episodes': 48, 'frozen_or_executed': False, 'measured_window_update_seconds': None}`。
任何贡献反馈前还须另冻类内核、完整探测方向与步长、唯一试训表、共同B复用、正式更新和公平预算。事前面板是4贡献根目标×4seed与另4确认根目标×4seed；P2未执行。真实概率／目标消费及完整反传合并进共同B试训。已有静态分配自由度不等于梯度或配置效果已可辨识。

分配接口逐字复用v035绑定及既有logN、历史／覆盖双KL和B/G-raw/I-P求解器；不改数值更新，不把旧G-lift冒称G-raw。

本阶段已闭合worker成本 10567.879118 GPU秒；运行中 0.000000秒。排队等待、旧阶段成本及CPU开发未叠成新采样GPU成本；未据P1采样时长承诺完整P3工时。

本P2报告不构成训练收益、分配增量或独立确认结论。用户已明确批准条件自动推进：支持合格后先冻完整实际清单，再共同B核验，随后全方向与正式／确认。未冻结P3不会启动；正式B/G/I从同一完整common出发，试训不得累加。实际后继状态另见software-allocation-v036报告。
