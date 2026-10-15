# v050 r4 两个 Q 分支累计计算边界

本回执只进行 CPU 原件读取、JSON/哈希/代码对象验证与合成合同控制。没有导入 torch、加载模型或张量；没有启动模型请求、反向或 optimizer。真实来源推导执行一次，结果保存在同目录 `q-r4-boundary-proof.json` 的 `budget` 字段；宿主可引用该封存结果，不重复读取大体积原件。

## 旧 Qplus 停止来源

2026-10-15 22:29:20（Asia/Shanghai），原 r1 监督器 PID 465916 因 `shared_device_free_memory_reserve` 主动发送终止信号。原 worker PID 3124120 的退出原件明确为 `KeyboardInterrupt: signal 15`；宿主于 22:29:24.952937 闭合进程，返回码 -2。22:29:13 GPU2 空闲 36453 MiB；22:29:20 另一项目 PID 2081553 增占 32234 MiB，GPU2 空闲降至 4214 MiB，低于原 6144 MiB 保护门。Qplus 自身仍占 44686 MiB。原停止回执与终态没有回写。

Qplus 原终态为 643 条材料中的 345 条已确认完成反向；第 346 条梯度前向已开始未完成。总前向 started/completed 为 989/988，actor/critic optimizer 各 0，完整状态仍为 S_star 4/4。仅存在更新前 `update/shared-before.pt`，没有更新后 checkpoint 或可恢复的累计梯度文件。因此本轮从同一完整 S_star 重新执行全部 643 条，不拼接旧部分梯度。累计预算为第 346 行保守预留反向上界，不将其称为已经完成的反向。

## 144 小时总额的重新分配

本轮用户明确要求取消共享显存余量限制并继续任务。两个 Q 分支旧的单分支 48 小时限制作为资源政策变更解除；原三个科学分支总训练计算区间 144 小时（518400 秒）保持不变。生成预算和原未启动 16 槽不在此增加。

| 已发生区间 | 入账秒数 | 口径 |
|---|---:|---|
| B 完成训练 | 111012.14107847214 | 原 training-compute 实际完整区间 |
| Qminus 两次旧中断 | 64586.59382510185 | 各自 training-compute started 至宿主 ended 的上界，原成本各一次 |
| Qplus 本次中断 | 71839.14961147308 | 1792074564.9529374 − 1792002725.803326 |
| 合计已用 | 247437.88451504707 | 不重复计算嵌套时间 |
| 总额剩余 | 270962.1154849529 | 518400 − 合计已用 |

原 r3 全部 17 个 owned worker 都为 attempted=false，GPU-worker 费用为 0。其 Qminus 的 170001 秒只是未消费预留，不能作为已发生费用扣除。

剩余平均分给两个新完整尝试并向下取整：Qplus 和 Qminus 各 **135481 秒，即 37 小时 38 分 1 秒**。三个科学分支的旧计算与两次新上限之和为 **518399.8845150471 秒**，余 **0.11548495292663574 秒**不分配。新尝试仍各最多 1292 个包装前向、actor/critic 各 643 行反向、各 1 次 optimizer。

| 科学分支 | 旧前向 started/completed | 旧反向确认下界/保守上界 | 加新完整尝试后的前向上界 | actor/critic 各自反向上界 |
|---|---:|---:|---:|---:|
| Qplus | 989/988 | 345/346 | 2281 | 989 |
| Qminus | 1524/1524 | 236/238 | 2816 | 881 |

两分支均保持原累计每分支 6150 前向、actor/critic 各 3072 反向和各 1 optimizer 的上限。旧中断的正式未知和停止事实保持；本轮不是恢复旧进程或原样完成旧尝试。

## 实现与必要控制

新增独立 `scripts/software_learning_resume_compute_v050r4.py` 与对应测试；r1/r2/r3 源码未修改。更新包装继续私有绑定原 `scripts/software_learning_v050._update`，继承 r1 provenance 入口与原 H1 函数。数值源码与原代码对象一致；critic 不重加权。分支包装只改变计算额度、来源记录、同源分支选择和累计计量。

15 项不同 CPU 合同一次执行全部通过：真实数字算术、Qplus 结束前未完成前向/零 optimizer/同状态、信号与宿主来源、异常检查点、r3 零消费与材料篡改拒绝、两分支时间/计数门及截止前阻断、本人材料顺序不变、两分支各调用原 H1 一次并使用对应冻结权重、不可重跑同输出目录、原数值代码对象复用。定向 Ruff 通过。日志在 `runs/software-learning-v050-resume-r4-controls/compute-pytest-attempt1.log` 与 `compute-ruff-attempt1.log`。实际旧来源推导一次通过，耗时约 5.196 秒。

接口：`derive_replay_budget(r3_root)` 返回整体封印对象，`allocation` 是全局分配凭据，`branches.Q_plus` 和 `branches.Q_minus` 是各自封印子集并绑定相同全局封印。宿主 `plan.q_compute_replay` 保存整体对象；`training_compute_receipt(admission, replay=budget['branches'][branch])` 与 `update(..., worker='update-Q_plus'/'update-Q_minus', ...)` 使用对应子集。新 worker 不重复推导旧原件，不读取或恢复旧部分梯度。
