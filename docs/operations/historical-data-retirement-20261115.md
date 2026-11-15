# 2026-11-15 历史实验原始数据清理

用户明确选择“连旧实验原始数据也删除，仅保留报告和汇总”，并进一步授权 root 只读核对进程与挂载引用。此次删除由普通用户 UID 1021 执行，root 仅用于只读预检，无进程停止、权限修改、卸载、Docker清理或共享配置变更。

## 实际结果

删除 **110,028 个文件**，删除前 `st_blocks × 512` 合计 **1,969,249,669,120 字节，即 1.7910 TiB**。错误0、文件身份变化跳过0。每项 unlink 后确认路径不存在。候选均为单硬链接普通文件，因此未把仍由其他硬链接占用的块计入。共享盘实时空闲差值可能受其他任务影响，未用它替代逐文件计量。

| 数据盘 | 删除前分配字节 | GiB |
|---|---:|---:|
| /data0 | 1,219,111,030,784 | 1135.39 |
| /data1 | 584,410,243,072 | 544.27 |
| /data2 | 165,728,395,264 | 154.35 |

操作后 df 快照：/data0 可用约1.3TiB、使用82%；/data1 可用约614GiB、使用92%；/data2 可用约177GiB、使用98%。系统盘及/data3未清理。此前196个普通缓存文件的12.9MiB另有独立记录，不重复计入。

## 范围与保留项

固定66个候选根目录，覆盖旧实验 episodes、workers、controller-output、终态rootfs归档、v194完成世界归档及迁移的历史数据。删除旧日志、快照压缩包、大型原始响应及其他符合清单条件的载荷。每项路径、inode/device、大小、mtime和分配块保存在压缩清单中。

没有整棵删除项目或runs。项目源码、docs与原有artifacts保持；候选树内名字含summary/report/result/metric/score/usage/ledger/budget/receipt/manifest/quiescence/finalization的文件、Markdown/CSV/TSV/SQLite/DB、1MiB以下JSON及report/summary目录保留。它们包含报告、汇总和来源元数据，也可能包含小型原始记录；因此本次并非所有旧原始数据已被彻底删除。

当前 v203.2.3 全部保留，其配置引用的v053/v054/v064/v066相关资源排除。另跳过rootfs/sysroot、环境、site-packages、node_modules、.git、符号链接和跨设备目录；共255个跳过子树，详情见inventory.json。最近24小时更新、非本人属主、多硬链接或特殊文件未纳入。保留文件计数1,245,593（包括上述元数据等），不能将它们全部认作报告。未对残余环境发起root删除。

原始数据删除不可由报告/汇总恢复；旧manifest、路径引用或完成记录可能指向已删除载荷，仅代表历史状态，不再证明载荷存在，也不应自动恢复下载。

## 执行与核验

第一次root引用检查被自动审批拒绝，因为原授权只涵盖磁盘统计；获得本轮明确授权后只读检查/proc的cmdline/maps/cwd/exe/root/fd以及宿主mountinfo，66目录无进程引用、无内部挂载、无权限错误。这是执行前时间点快照，不保证未来不会新建消费者。未重做整盘du或实验测试。

逐文件删除前复核清单SHA256、UID、单链接及inode/device/size/mtime。通过从/开始逐层O_NOFOLLOW打开父目录，再用dir_fd unlink，拒绝符号链接跳转。普通用户nice19、idle I/O执行。逐文件删除回执与本次实际执行脚本一并保存，未改写旧实验的结果或评分。

## 审计文件

`artifacts/historical-data-retirement-20261115/`保存candidate-roots、原计划摘要、只读引用检查、逐文件压缩计划与删除事件、完整盘点和最终删除摘要。plan-summary的planned_not_deleted是执行前原件；实际完成状态以deletion-summary为准。压缩文件仅是路径和元数据清单，不是被删除原始数据的备份。
