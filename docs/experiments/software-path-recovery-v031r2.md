# SWE v0.31-r2 公开路径准入修复与独立筛选

状态：`complete`；源码：`2456572481b01a8b6bde9cfd5fd168c35024a830`；原始目录：`/data1/zhuxinrui/projects/ProWorkSim/runs/software-path-recovery-v031r2`。

仅针对原 SWE 首次输出 `/public-note.json` 未满足已声明相对路径的准入失败。旧调用、旧资格失败及其全部成本保留不变。新准入公开唯一相对路径，首次真实读取失败时最多一次真实错误反馈纠正；最多4次新原生调用，不执行新的 optimizer step。

原同一 common actor 的近16K完整概率／反向、1次诊断更新、保存重载及新身份SDK回流已有正证据。本次先恢复完全相同的actor／critic／optimizer／RNG common再继承这些证据，不重复长stress，也不声称它们是本次重新测量。新调用仍逐条保留完整轨迹并通过原概率门和完整反向。

新推理准入：`True`；训练准入：`True`；完整common恢复：`True`。

通过路径准入后才执行原六开发合同×两seed的完整12槽一次；SDK、原生协议、模型profile、数值门、世界、role预算、分类门和排名定义不变。未启动／未闭合不补0分。

| 案例／seed | 状态 | 完整交付 | R |
|---|---|---|---:|
| mm-nested-order-import / 202610040701 | closed | False | 0 |
| mm-event-projection / 202610040701 | closed | False | 0 |
| mm-envelope-hook-repair / 202610040701 | closed | False | 0 |
| mm-nested-error-repair / 202610040701 | closed | False | 0 |
| mm-ledger-rootgoal / 202610040701 | closed | False | 0 |
| mm-settings-rootgoal / 202610040701 | closed | False | 0 |
| mm-nested-order-import / 202610040702 | closed | False | 0 |
| mm-event-projection / 202610040702 | closed | False | 0 |
| mm-envelope-hook-repair / 202610040702 | closed | False | 0 |
| mm-nested-error-repair / 202610040702 | closed | False | 0 |
| mm-ledger-rootgoal / 202610040702 | closed | False | 0 |
| mm-settings-rootgoal / 202610040702 | closed | False | 0 |

| 类别 | 完整成功／已知 |
|---|---:|
| api_normal_path | 0/4 |
| repair_after_real_failure | 0/4 |
| o1_root_goal | 0/4 |

SWE本次是否满足原候选可选门：`False`；这不等于三模型最终选中。

本运行不重启9B或Devstral，不控制其进程，不覆盖原v031报告；其他候选仅记录读取时状态。此独立运行不执行最终三模型选择或后续B/G-raw/I-P实验。

| 成本阶段 | GPU秒 |
|---|---:|
| original_worker_gpu_seconds | 15.887841 |
| r1_worker_gpu_seconds | 236.632682 |
| v031_old_trace_gpu_proof_seconds | 28.811610 |
| v031_worker_gpu_seconds | 2799.487545 |
| v031r2_worker_gpu_seconds | 1410.463386 |

GPU成本为分配单张GPU后的完整worker墙钟，包括导入、加载、补验、筛选、清理及失败；预约和排队另存记录，不重复加旧累计成本。资源限制仍为每worker64GiB RSS、全部旧新产物合计128GiB及卷预留20GiB，无累计GPU／队列／总墙钟截止。

以上是已见开发材料上的运行准入与筛选证据，不是参数训练收益或分配算法收益。机器可读报告保留全部原件引用、继承范围、补验细节和失败原因。
