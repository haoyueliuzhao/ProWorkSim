# v0.36 P2 固定当前策略支持窗口

状态：`waiting`；支持门：`not_available`；源码：`e26ab99df8e555cd144eef2b38641174addb28d7`；原件：`/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036`。

仅使用已选9B原完整3/3 common及v036成员自测反馈／Γ（原v034容量与去重算法保持）；这不是fresh base。沿用原训练用途根目标、一个精确情境、固定member_a先手和16个事前seed。每例共同128决定／128尝试／500000 token／32 tests；不采到成功或两类才停止。

P2只采集，不执行参数更新、贡献开发或独立确认。新来源与用途隔离，P1／历史开发记录未改标为训练；没有重复GPU资格、16K压力或用完即丢的生产诊断更新。

| 槽 | seed | 状态 | 完整R | 提交 | Mapper状态 | 方法 | 实际tokens |
|---|---:|---|---:|---|---|---|---:|
| v036-support-00 | 202610070101 | not_started | None | None | None | None | None |
| v036-support-01 | 202610070102 | not_started | None | None | None | None | None |
| v036-support-02 | 202610070103 | not_started | None | None | None | None | None |
| v036-support-03 | 202610070104 | not_started | None | None | None | None | None |
| v036-support-04 | 202610070105 | not_started | None | None | None | None | None |
| v036-support-05 | 202610070106 | not_started | None | None | None | None | None |
| v036-support-06 | 202610070107 | not_started | None | None | None | None | None |
| v036-support-07 | 202610070108 | not_started | None | None | None | None | None |
| v036-support-08 | 202610070109 | not_started | None | None | None | None | None |
| v036-support-09 | 202610070110 | not_started | None | None | None | None | None |
| v036-support-10 | 202610070111 | not_started | None | None | None | None | None |
| v036-support-11 | 202610070112 | not_started | None | None | None | None | None |
| v036-support-12 | 202610070113 | not_started | None | None | None | None | None |
| v036-support-13 | 202610070114 | not_started | None | None | None | None | None |
| v036-support-14 | 202610070115 | not_started | None | None | None | None | None |
| v036-support-15 | 202610070116 | not_started | None | None | None | None | None |

完整成功：0/0 已知；提交 0，未提交 0。未知／未开始不填零，未提交内容不补验。

| 精确情境 | 成员 | 原M | n+ | v | 类频数 | b | 状态 |
|---|---|---:|---:|---:|---|---|---|

后续状态：`collecting_fixed_inventory`；首合格成员块：`None`。
无支持、只有一类、多类频数不足与形式自由度存在但梯度尚未验证分别记录。全部原16槽保持基础分母，可信失败／unmapped／低频及未选成员维持基础损失，不删样本后重新平均。

按当前n+/K计算的条件化后继规模：`None`。
任何贡献反馈前还须另冻类内核、完整探测方向与步长、唯一试训表、共同B复用、正式更新和公平预算。事前面板是4贡献根目标×4seed与另4确认根目标×4seed；P2未执行。真实概率／目标消费及完整反传合并进共同B试训。已有静态分配自由度不等于梯度或配置效果已可辨识。

分配接口逐字复用v035绑定及既有logN、历史／覆盖双KL和B/G-raw/I-P求解器；不改数值更新，不把旧G-lift冒称G-raw。

本阶段已闭合worker成本 0.000000 GPU秒；运行中 0.000000秒。排队等待、旧阶段成本及CPU开发未叠成新采样GPU成本；未据P1采样时长承诺完整P3工时。

本P2报告不构成训练收益、分配增量或独立确认结论。用户已明确批准条件自动推进：支持合格后先冻完整实际清单，再共同B核验，随后全方向与正式／确认。未冻结P3不会启动；正式B/G/I从同一完整common出发，试训不得累加。实际后继状态另见software-allocation-v036报告。
