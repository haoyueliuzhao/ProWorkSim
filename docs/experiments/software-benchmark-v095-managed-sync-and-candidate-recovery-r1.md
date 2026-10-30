# v095：受管同步权限修复与原候选恢复

**已封存26个不同任务的原候选，供独立补评；没有重跑模型或修改原补丁。** 它们仍不是“补评已通过”的结果。固定清单见 [combined-ready-results.json](../../artifacts/software-benchmark-v095/candidate-recovery-batch-r1/combined-ready-results.json)。原 unknown、账本、控制器退出状态和旧文件均保留。

## 同步故障及修复

6068（Matplotlib-23299／PROJECT）的首个公开测试在同步源码时失败。旧 `synchronize_tree` 对每个文件无条件 `chmod`，包括内容与Git执行模式完全未变的文件。归档中的 `build/freetype-2.6.1/CMakeLists.txt` 为 uid1000、gid100、0644；容器进程没有权限对该外来 inode 改模式，即便目标模式本来也是0644。RPC随后进入不可重放的失败状态，最终 `sync_terminal` 再次报错。

[新同步函数](../../src/proworksim/software_benchmark_managed_sync_v095.py)跳过内容和Git执行模式未变的 inode。真正需要修改时，在同一私有目录创建本进程拥有的临时文件，写入并设定所需模式，再原子替换；保留 `.git` 控制数据，并核对完整目标树。没有 chown、提权、能力扩大或吞掉真实父目录写权限错误，也没有修改旧 worker。部署须由新版本显式接入。

4项必要CPU检查通过：复现旧EPERM并验证新路径不再修改该inode；必要执行位变化仍落实；只读内容通过原子替换更新且保留Git控制；父目录禁止替换时明确失败。另7项闭合门检查通过，拒绝中间树、未知用量、活跃writer及账单不一致。Ruff通过。

## 可补评候选来自哪里

| 来源 | 数量 | 闭合证据与处理 |
| --- | ---: | --- |
| 本轮6068 | 1 | 37次模型调用全部结算，2,926,290 token；SDK关闭后已生成唯一v4代码锁与原roundtrip补丁，随后仅终态同步失败。保留未合法提交的事实 |
| 历史同类终态同步失败 | 22 | 逐项验证完整原归档、一次性close claim、原候选bundle／tree／patch、已知费用和writer静止，只恢复行政导出记录 |
| owner OOM但子控制器实际已正常closed | 3 | PROJECT3171／3459保留代码及原合法交付两端点；REF3514保留原normal finish、candidate claim和同actor停止后完整归档，按原最终工作树规则导出并验证补丁 |

三项owner恢复还逐request_id、response_id和usage对账原API账本，全部匹配已结算原件。3514补的是已选定最终工作树的导出，未从多份中间代码中择优。PROJECT恢复始终使用真正的managed版本，不能用同步可能滞后的actor树代替。

所有恢复均写入独立v095目录，`status=closed`明确限定为**行政产物闭合**，不伪造原控制器正常退出、不新增项目交付、不推断代码正确，也不把已结算费用再算一遍。评分方仍须对这些精确result／lock引用单独准入。

## 保留的未知与边界

历史27份小锁中，22项同类异常与3459已恢复；1122、4068、4168、5110仍缺最终controller-result，模型桥接记录为EBADF。它们的账单已知且有代码锁，并不等于必须重跑，但当前闭合门不足以将其改成正常结果。本轮不新增闭合规则，见 [remaining-boundaries.json](../../artifacts/software-benchmark-v095/candidate-recovery-batch-r1/remaining-boundaries.json)。其中3项原锁记有合法交付，这一事实也保留。

对33项owner OOM另外进行了仅小元数据和归档清单的流式核验，没有整库解包或选代码。30项有可信控制器归档，3项没有；最终child为closed的实际有3项，technical_unknown有16项，其余14项缺最终child（含3项无归档）。9项仍保留未知费用。本轮恢复了上述3个实际closed案件，其余维持技术未知，不记为模型错误，也不一律要求重新生成。完整分类见 [OOM审计](../../artifacts/software-benchmark-v095/OOM-candidate-audit-r1/summary.json)。

本轮候选准备和修复过程中没有启动容器、服务、API请求或GPU任务。评分结果由独立补评阶段产生，不能用本报告的“可评候选数”代替正确题数。
