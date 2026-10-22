# v055 主盘异常终态工作区无损归档 r1

## 问题与本批边界

2026-10-22，预热新环境需要的主盘空间预约受到阻挡。此前完成的 63 项归档针对副盘，不能用其释放量解释主盘空间变化。本批单独选择主盘 `queue-r1/workers/generation-*/episode/actor/rootfs` 中已经终态的 53 个 DeepSeek 异常回合，保留它们唯一的末态工作区内容，通过无损压缩释放展开副本占用。

这不是生成重试、补充评分或模型结果修正。原始 `technical_unknown`、任务 claim、事件、账本、正式候选和评分记录保持原样；没有把异常改记为模型失败或正常完成。本批不处理 Qwen 工作区、不完整静默证据的 10 个 DeepSeek 主盘工作区、活动任务、共有模板、Docker 镜像、旧 63 项归档或其他用户文件。

固定来源和实际占用见 [admission.json](../../artifacts/software-benchmark-v055/primary-terminal-rootfs-archive-r1/admission.json)。只根据队列元数据检查精确目录，没有扫描整个磁盘。对确定的 53 条路径仅执行一次 `sudo du -s -B1 -x --files0-from=...`，实际 allocated 占用合计 **187,935,690,752 字节（175.0288 GiB）**。这不是预计净释放量；压缩包和新增索引仍占用磁盘，净释放必须从最终 released 回执计算。

## 独立命名空间与冻结身份

| 对象 | 路径或 SHA-256 |
| --- | --- |
| 新归档入口 | `tools/archive_primary_terminal_rootfs_v055_r1.py` |
| 新归档入口 SHA | `9b60ec9ca294977c119baf12455fe8d6ad6792feba4fef759a6d28a3dace08f4` |
| 新有限批次入口 | `tools/run_primary_terminal_rootfs_archive_batch_v055_r1.py` |
| 新批次入口 SHA | `b4377fad0c83c3da384c88991952f262bfa2fef4806de3ac01391607a890713a` |
| 固定 allowlist | `runs/software-benchmark-v055/primary-terminal-rootfs-archive-audit-r1/allowlist.json` |
| allowlist SHA | `69925d56ffafd76de4faf86ea719248f6b6c39b1f885131a03a2e163a0b79072` |
| 冻结 plan | `runs/software-benchmark-v055/primary-terminal-rootfs-archive-r1/plan.json` |
| plan SHA | `14fe3818af99ff344d03c0af18671437a8e9d96b610ef2ba3a9e2b005913fa0d` |
| 独立进度输出 | `runs/software-benchmark-v055/primary-terminal-rootfs-archive-batch-r1/` |
| 独立验证和释放回执 | `runs/software-benchmark-v055/primary-terminal-rootfs-archive-r1/<item_id>/` |
| 压缩包 | `runs/software-benchmark-v055/queue-r1/terminal-rootfs-archive-r1/<item_id>/rootfs.tar.zst` |

新 wrapper 在私有进程中只绑定原归档模块的 `OUT` 与 `VERSION`。原 `archive_terminal_rootfs_v055_r1.py` 的 SHA 固定为 `a1929b16a0deb0884e08ea66b542451d7bd8780ef6a6e936fd47a1661b233e13`；归档、完整回读验证、释放和恢复函数均直接复用，没有修改已发布实现。

原实现强制压缩包与源 rootfs 在同一真实文件系统，且严格绑定源卷路径。本批遵循该限制，将压缩包写在主盘，**没有转移到副盘以绕过副盘的生成空间预约**。metadata 新命名空间与旧 63 项隔离；新旧来源路径和 item ID 集合均不相交。

原有限调度器 SHA 固定为 `71020bcdcbad655763b938665dc8183f219c9bda24a7db626739f45d7d664bf2`。新批次直接复用其分组、两槽线程调度、partial 保护、逐项失败隔离、释放统计与进度刷新，仅独立绑定 53 项计划、输出路径、worker unit 名和计数初始化。

## 每项允许释放的必要条件

1. 固定队列条目仍是同一个 `technical_unknown` 回合；相关评分已终态。精确 row、result、claim、entered、state、完整 scope registry、历史 quiescence、resource slice 和 rootfs manifest 均按 SHA 绑定。
2. 历史 `all_quiet=true`、无历史 errors，且原资源释放回执为真。归档和释放分别持有原任务的 `scope-registry.lock`，重新检查 generation/scoring unit、注册 scope、PID 与 start ticks、cgroup 和整个资源 slice 都已静默。
3. 源必须是冻结的主盘目录、设备 `66306`、稳定 inode/metadata，目录内没有 mount，也不能存在指向 rootfs 外部的文件硬链接。
4. 对源完整清点并计算每个独立文件的 SHA-256；生成 GNU pax tar + zstd level 1 后，完整解压回读验证成员集合、内容、uid/gid/mode、纳秒 mtime、符号链接、硬链接拓扑、xattrs/原始 ACL 和稀疏 extent。
5. 只有验证回执存在且压缩包身份匹配，才能进入独立 release。release 再检查完整源元数据与当前静默，在原 scope 锁持续持有期间写恢复标记、删除展开副本。原记录和压缩包保留。

编码前仍保留原实现的“最坏压缩输出占用 + 100 GiB 实际余量”门槛。没有降低空间安全线。

## 并行、失败处理与恢复

最多同时处理两个不同 claim；同 claim 串行。每个实际 archive/release worker 使用独立系统 unit，限制为 `CPUQuota=200%`、`MemoryMax=2G`、`IOWeight=10`、`Nice=10`、`RuntimeMaxSec=1800`、`KillMode=control-group`、`Restart=no`。

普通单项失败保留原始工作区、partial 产物和日志，记录异常后处理下一项。已有 partial 不自动重跑；存在完整 verified 回执时可只执行 release。若不能确认失败归档 worker 已退出，则仅停止启动更多清理 worker，避免出现第三个不受计量的清理任务；不影响模型队列，不向实验进程发信号。

恢复沿用原验证后的 restore，只能写入该新 metadata namespace 下的**新目录**，不覆盖原位置。恢复后再次对整棵树内容和可移植元数据进行验证。

## 必要验证与当前结果范围

已执行的新验证仅覆盖本次变化：53 项和新命名空间绑定、拒绝错误数量/旧 namespace/跨盘 payload、新旧 63 项不相交、worker 命令资源限制与独立 unit 命名。记录在 [wrapper-control.json](../../artifacts/software-benchmark-v055/primary-terminal-rootfs-archive-r1/wrapper-control.json)。Ruff 检查通过；没有重复原编码器和调度器已通过的全部测试。

一次现场 preflight 在每项原 scope 锁下检查了全部 53 项的当前静默、精确证据与无 mount，全部通过，见 [live-preflight.json](../../artifacts/software-benchmark-v055/primary-terminal-rootfs-archive-r1/live-preflight.json)。这不是删除许可的永久替代：真实 archive 和 release 仍各自重新执行这些必要条件。

## 已启动与预热恢复时点快照

准备 agent 完成计划与控制后，由根代理实际启动 `proworksim-v055-primary-terminal-rootfs-archive-batch-r1.service`。原生批次记录启动时间为 `2026-10-22T09:32:12.126509+00:00`。没有重新运行已经进入的模型任务。

截至北京时间 **2026-10-22 17:50:08**，本批仍在后台进行：**28/53 项 released，0 项失败或 partial**。已释放项原展开占用为 103,339,134,976 字节，保留压缩包 allocated 占用 40,373,903,360 字节，扣除压缩包后的实际净释放 **62,965,231,616 字节（58.6409 GiB）**；该净值未减去很小的 metadata/index 开销，不等于同一时刻整个磁盘 free 的变化。详见 [progress-at-recovery.json](../../artifacts/software-benchmark-v055/primary-terminal-rootfs-archive-r1/progress-at-recovery.json)。

只读辅助 observer 已按根代理要求结束；真实有限归档批次继续，并由自身自动写入最终状态及逐项回执。本 Git 文档固定保留恢复时点快照，不让后台进程修改 tracked artifacts。后续完成项、失败项和最终净释放量，以 `primary-terminal-rootfs-archive-batch-r1/state.json` 及逐项 `released.json` 为准。**当前快照不宣称 53 项全部完成，也不把 175.0288 GiB 原始占用当作实际释放量。**
