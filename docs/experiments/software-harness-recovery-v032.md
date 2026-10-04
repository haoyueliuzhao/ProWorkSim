# SWE v0.32 工具说明、反馈与预算准入修订

状态：`qualification_failed`；源码：`b9af2331caea930eb420ce29cac95504766e47ac`；原始目录：`/data1/zhuxinrui/projects/ProWorkSim/runs/software-harness-recovery-v032`。

本次为独立的新harness开发修订。原v031路径准入失败和r2已闭合12槽0/12全部原样保留，未重判或覆盖旧成绩。仅修改显式允许的公开工具手册、错误反馈、精确本地token预约／透传和终态细分代码；原actor、native syntax、profile、数值门、世界、两seed、role额度和验收／排名规则不变。

先恢复原v031完整actor／critic／optimizer／RNG common，再做真实无参读取＋8K事实／10K实际错误反馈的新技术准入。通常3次调用，首次真实读取失败且完整trace时最多一次纠正，总计最多4次。每条新完整轨迹都经原概率门与完整零step反向；原16K／1次更新／保存重载／新身份回流证据只在同一common下继承，不重复长stress，不声称本次重新测量。

新推理准入：`False`；训练准入：`False`；完整common恢复：`True`。

通过新准入才执行原六开发合同×两seed完整12槽一次。停止减少、合法调用增加、测试通过或任务创建均不自动等于固定集成交付；新修订是否改善结果以本次实际记录为准，不能由修订设计推断。未启动／未闭合不补0。

| 案例／seed | 原r2 R | v032状态 | v032完整交付 | v032 R |
|---|---:|---|---|---:|
| mm-nested-order-import / 202610040701 | 0 | not_started_or_not_closed | None | None |
| mm-event-projection / 202610040701 | 0 | not_started_or_not_closed | None | None |
| mm-envelope-hook-repair / 202610040701 | 0 | not_started_or_not_closed | None | None |
| mm-nested-error-repair / 202610040701 | 0 | not_started_or_not_closed | None | None |
| mm-ledger-rootgoal / 202610040701 | 0 | not_started_or_not_closed | None | None |
| mm-settings-rootgoal / 202610040701 | 0 | not_started_or_not_closed | None | None |
| mm-nested-order-import / 202610040702 | 0 | not_started_or_not_closed | None | None |
| mm-event-projection / 202610040702 | 0 | not_started_or_not_closed | None | None |
| mm-envelope-hook-repair / 202610040702 | 0 | not_started_or_not_closed | None | None |
| mm-nested-error-repair / 202610040702 | 0 | not_started_or_not_closed | None | None |
| mm-ledger-rootgoal / 202610040702 | 0 | not_started_or_not_closed | None | None |
| mm-settings-rootgoal / 202610040702 | 0 | not_started_or_not_closed | None | None |

| 类别 | v032完整成功／已知 |
|---|---:|
| api_normal_path | 0/0 |
| repair_after_real_failure | 0/0 |
| o1_root_goal | 0/0 |

SWE本次是否满足原候选可选门：`False`；这不等于三模型最终选中。

本运行不重启或控制9B／Devstral，不覆盖其报告；其他候选仅保留读取时状态。不执行三模型最终chooser，也不自动启动B/G-raw/I-P。

| 成本阶段 | GPU秒 |
|---|---:|
| original_worker_gpu_seconds | 15.887841 |
| r1_worker_gpu_seconds | 236.632682 |
| v031_old_trace_gpu_proof_seconds | 28.811610 |
| v031_worker_gpu_seconds | 2799.487545 |
| v031r2_worker_gpu_seconds | 1410.463386 |
| v032_worker_gpu_seconds | 78.766694 |

旧v031累计成本和r2实际worker各只加一次，再加v032完整分配worker墙钟；预约／排队另存记录。原每worker64GiB RSS、全部旧新产物128GiB、卷预留20GiB和单任务帽保持，无累计GPU／排队／总墙钟截止。

这仍是已见开发材料上的harness准入和筛选比较，不是参数训练收益、独立确认或分配算法收益。配套JSON保留允许变更前后文件hash、逐字节不变的数值／世界文件、原common、原22项数值证据、r2完整12槽、所有旧成本和新轨迹。
