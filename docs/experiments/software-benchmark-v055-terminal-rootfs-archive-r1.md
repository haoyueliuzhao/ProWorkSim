# v055 已结束异常工作区无损归档（2026-10-22）

本次回收对象是已结束异常回合遗留的展开文件系统。它们并非可直接丢弃的缓存：46 个 Actor rootfs 缺少独立候选导出，17 个公开测试 rootfs 也没有完整外部输出，内部可能包含唯一末工作树、复现脚本或测试日志。因此本次先保全完整文件系统，经实际回读核对后再释放展开副本。原技术未知、费用、任务身份和历史结果全部保留，不据此重新生成或补选候选。

另一个 xarray-2905 Actor rootfs 的历史 `all_quiet=false`，虽然当前进程已经静止，仍从本轮严格清单中排除。63 项展开数据的 **212.345 GiB 是非特权读取的已分配字节下界**，不是精确容量，也不是预计净收益。最终以特权归档清单及压缩文件实际大小逐项计算。

## 固定范围及实现

新增独立工具 `tools/archive_terminal_rootfs_v055_r1.py`，不修改任何冻结运行器、原 rootfs manifest、claim、评分或账本。实施源 SHA-256 为 `a1929b16a0deb0884e08ea66b542451d7bd8780ef6a6e936fd47a1661b233e13`。固定计划为 `runs/software-benchmark-v055/terminal-rootfs-archive-r1/plan.json`，SHA-256 为 `2842e8a4ce9476706fce081e9c1b710f29be89dd2caf86c014b850200bd6d8fb`，含 46 个 Actor 和 17 个公开测试 rootfs。

原审计和控制保存在 `runs/software-benchmark-v055/terminal-rootfs-archive-audit-r1/`。执行 `archive`、`release`、`restore` 都必须同时提供精确计划 SHA、实施源 SHA 和计划内 item ID；特权入口限制 `SUDO_UID=1021`。新建容器目录权限为 0700，新归档与回执归项目用户 1021:1022 所有，原文件系统内容的 uid/gid/mode 不变。

源路径语法仅允许：

```
runs/software-benchmark-v055/{queue-r1,secondary-volume-r1}/workers/generation-<24hex>/episode/actor/rootfs
runs/software-benchmark-v055/{queue-r1,secondary-volume-r1}/workers/generation-<24hex>/episode/public-test-<integer>/actor/rootfs
```

压缩 payload 必须位于源同一真实文件系统的 `terminal-rootfs-archive-r1/<item>/rootfs.tar.zst`；轻量计划、清单和回执位于主盘。这避免将副盘展开数据的归档重新堆入主盘。输出启动前，以所有独立普通文件逻辑大小加每成员 8 KiB 和 16 MiB 额外开销保守估算最坏输出，并要求仍有 100 GiB 余量。该门是本工具的局部瞬时空间门，其他实验仍可并发消耗磁盘，不将它描述为系统全局磁盘保证。

## 每项资格与保全

每项操作持有原 claim 的 `scope-registry.lock` 排他锁，复核原唯一槽仍是 `technical_unknown`、所有评分均终态、原行投影没有变化、保留证据 SHA 和对应 rootfs manifest 没有变化、原资源释放已闭合。随后现场检查 generation/scoring 的 user service、所有注册 actor/controller/test scopes、精确 PID/start_ticks、资源 slice 的 cgroup population，以及 rootfs 下没有挂载。任何活动、缺证、身份变化或未知节点均拒绝该项，不删除原件。

源清单保留目录成员、普通文件完整 SHA-256、文件类型、uid/gid/mode、纳秒 mtime、软链目标、完整硬链拓扑、全部 xattr（包含原始 POSIX ACL 字节）和稀疏数据 extent。设备文件、FIFO、socket 等特殊节点以及链接到此 rootfs 外部的普通文件硬链不在本工具支持范围，遇到时直接保留原目录。

GNU tar 1.34 使用 pax、`--acls --xattrs --xattrs-include=* --sparse --numeric-owner`，zstd 1.4.8 使用 level 1、单压缩线程。生成后进行一次完整解压流回读：逐一核对所有成员及完整普通文件内容，并核对上述元数据、硬链和稀疏 extent，完整读取压缩帧末尾。没有只用压缩流测试或只用文件数量代替内容核验。回读通过后重查完整源树成员和 stat/xattr、原 root inode 以及现场静止，才写 `verified.json`；此时源展开目录仍在。

`release` 是显式的独立操作。它再次校验归档 SHA、完整成员清单、源原 inode、全树 stat/xattr 和当前生命周期证据，先写原路径旁的 `rootfs.lossless-archive-r1.json` 恢复指引，再使用支持抗 symlink 攻击的 fd-based `shutil.rmtree` 释放唯一指定目录。所有目录外历史证据保留。失败的 partial archive 和源目录都保留，不自动重试或擅自删掉失败证据。

## 恢复及资源边界

恢复默认写入该 item 的全新 `restored/` 目录，绝不覆盖原路径或任何已存在目录；可显式指定本归档区内新的目录。恢复使用数值 owner、原 mode、ACL、xattr、稀疏文件和硬链，再完整计算恢复树内容与可移植元数据，成功才写恢复回执。归档保留的是文件系统内容与要求的恢复元数据；inode/dev、ctime 和物理分配位置不是可移植恢复端点。

批处理最多两个归档 worker，并且同一个 claim 下的 Actor/测试目录依次处理。每个 worker 使用 2 CPU、2 GiB 内存、IOWeight=10、Nice=10，单项 systemd 上限 30 分钟。它们不会读取模型 key、调用 API、加载 GPU、重启队列或更改已运行回合。

## 必要控制和执行状态

`tools/check_terminal_rootfs_archive_v055_r1.py` 必须传入全新 `/tmp/pws-terminal-archive-control-*` 根目录；生产 plan/状态/释放入口在 fixture 中被显式禁止。六项控制通过：含二进制 xattr、ACL、硬链、软链、稀疏文件、纳秒 mtime 的完整流核验与真实恢复；源变动拒绝；FIFO 拒绝；外部硬链拒绝；非 allowlist 路径拒绝；截断归档拒绝。初始实现的控制和新增空间/owner 实现的控制分别保留，未把旧 SHA 的完整控制假称为新 SHA 重跑。新增 owner/space 纯控制确认项目归属、0700 容器权限及恰好达到/低一字节空间门边界；46 个原 claim 锁均存在。限定两个新增工具的 Ruff 检查通过。

首批两个不同 claim 的实际 `archive`+完整验证均成功，两个 systemd 单元均正常退出。django-13568 工作区完整核对 78,128 成员，展开已分配 3,047,747,584 B，压缩包 1,179,098,443 B；sphinx-10435 工作区核对 75,645 成员，展开已分配 2,963,447,808 B，压缩包 1,121,604,040 B。此阶段原展开目录仍保留，`release` 由主代理读取真实验证回执后显式执行。最终释放项数、净回收字节及失败清单以后续逐项真实回执为准；本说明不将验证通过当作已经回收空间，不宣称性能提升已经发生。

可提交的小型证据见 `artifacts/software-benchmark-v055/terminal-rootfs-archive-r1/`，包含固定计划摘要、必要控制和首两个真实完整验证回执。完整成员清单、压缩 payload 及原始实验内容仅保存在运行区，不纳入 Git。

## 有限批处理器

独立新增 `tools/run_terminal_rootfs_archive_batch_v055_r1.py`，SHA-256 为 `71020bcdcbad655763b938665dc8183f219c9bda24a7db626739f45d7d664bf2`；不修改上述已冻结归档器。它只能读取此固定63项计划和指定归档器 SHA，按 `slot_id` 分组，最多同时运行两个不同 claim，同 claim 内 Actor 和公开测试 clone 串行。

父进程以项目用户运行，仅协调任务与写进度。每次实际 `archive` 或 `release` 通过 `sudo systemd-run --wait --pipe --collect` 在独立系统服务内运行，显式传入 `SUDO_UID=1021`，每项2 CPU、2 GiB、IOWeight10、Nice10、最长1800秒、KillMode=control-group。已经存在合法释放回执且原目录已消失的项目直接计入统计；已有完整验证回执只执行释放；已有partial目录或释放指引但缺完成回执的项目保留并跳过，不盲目重试。单项归档/释放失败记为异常后继续后续项目。只有失败后的进程存活状态无法确认时，才停止新增清理项，防止未计入的旧worker与替换worker形成超并发；实验队列不受影响。

状态保存在 `runs/software-benchmark-v055/terminal-rootfs-archive-batch-r1/state.json`，逐步事件为 `progress.jsonl`，每次归档和释放各保留独立日志。最终回收量使用源完整清单的已分配字节减压缩包当前 `st_blocks*512`，明确是未扣轻量元数据的净释放估计；没有用压缩逻辑大小替代实际磁盘占用。批处理器的七项纯内存fake控制已通过，涵盖已释放跳过、仅释放已有验证项、保留partial、归档失败禁止释放、同claim后续继续、释放失败隔离、两claim并行上限与串行边界；控制过程没有真实sudo调用或文件系统写入。限定单文件Ruff检查通过。
