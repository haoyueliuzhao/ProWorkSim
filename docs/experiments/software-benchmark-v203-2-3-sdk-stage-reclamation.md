# 已归档 SDK 展开副本清理（v203.2.3）

本次只清理用户已授权、主代理确认已结案或未进入正式运行的旧 SDK bundle `stage` 展开副本。当前最终 `sdk-bundle-r5`、全部 `runtime.tar.gz`、manifest、成员清单、源码引用、probe、模型/评分证据及依赖环境均保留。没有 root、Docker、服务或共享配置操作。

## 必要验证和删除范围

采用明确的逐目录清单，没有全盘扫描。每个目标先验证 manifest 所引用 tar 与成员清单的大小和 SHA256；完整读取 tar，对全部 stage 普通文件校验内容 SHA256，并要求 stage、archive 与 inventory 的文件集合一致。路径必须为当前普通用户所有，不接受软链接或特殊文件。删除前复核 inode、大小与修改时间，避免删除验证后发生变化的展开副本。

检查当前可见 `/proc` 中本用户进程的 cwd、exe、root、cmdline、maps 与 fd 引用；该记录限定于当前可见进程空间，不宣称进行了服务器所有用户进程的全局审计。历史运行已结案的判断由主代理确认。无 manifest 或有疑点的目录跳过，不猜测归档内容。

核验最多使用两个线程；普通用户降低自身优先级（nice +10，ionice idle），仅在核验成功后顺序删除。每项先持久化 verified 回执及压缩 stage 模式/属主/时间元数据，再删除 stage，最后写结果回执。

## 第一批结果

| 旧 bundle | 结果 | 回收分配空间（GiB） |
|---|---|---:|
| software-benchmark-v203-2-1/sdk-bundle-r1 | 已验证并清理 stage | 0.4689 |
| software-benchmark-v203-2-1/sdk-bundle-r2 | 已验证并清理 stage | 0.4689 |
| software-benchmark-v203-2-3/sdk-bundle-r1 | 已验证并清理 stage | 0.4691 |
| software-benchmark-v203-2-3/sdk-bundle-r2 | 已验证并清理 stage | 0.4690 |
| software-benchmark-v203-2-3/sdk-bundle-r3 | 已验证并清理 stage | 0.4691 |
| software-benchmark-v203-2-3/sdk-bundle-r4 | 已验证并清理 stage | 0.4692 |
| software-benchmark-v143/sdk-bundle-r1 | 已验证并清理 stage | 0.4687 |
| software-benchmark-v146/sdk-bundle-r1 | 已验证并清理 stage | 0.4687 |
| software-benchmark-v157/sdk-bundle-r1 | 已验证并清理 stage | 0.4690 |
| software-benchmark-v159/sdk-bundle-r1 | 已验证并清理 stage | 0.4695 |
| software-benchmark-v161/sdk-bundle-r1 | 已验证并清理 stage | 0.4697 |
| software-benchmark-v161/sdk-bundle-r2 | 已验证并清理 stage | 0.4693 |
| software-benchmark-v168/sdk-bundle-r1 | 已验证并清理 stage | 0.4694 |
| software-benchmark-v170/sdk-bundle-r1 | 已验证并清理 stage | 0.4695 |
| software-benchmark-v181/sdk-bundle-r1 | 跳过：缺少 manifest | 0.0000 |
| software-benchmark-v181/sdk-bundle-r2 | 已验证并清理 stage | 0.4695 |
| software-benchmark-v181/sdk-bundle-r3 | 已验证并清理 stage | 0.4697 |
| software-benchmark-v192/sdk-bundle-r1 | 跳过：缺少 manifest | 0.0000 |

第一批按删除前唯一文件链接与目录的 allocated blocks 计，回收 8,060,710,912 字节（7.5071 GiB）。磁盘可用空间从 138,343,956,480 增至 146,401,415,168 字节；同时发生的其他 I/O 和新回执写入会使实际空闲增量与 stage 回收计数不同。

缺 manifest 的 v181/r1 和 v192/r1 未删除，因此第一批低于 8 GiB 目标。补充清理须继续使用已经核实归档的具体历史目录，不降低运行安全磁盘门槛。

第一批逐项证据：[summary.json](../../artifacts/software-benchmark-v203-2-3/disk-reclamation-r1/summary.json)。同目录保留 `intent.json`、实际执行 `procedure.py`、每目录 `verified/result/skipped` 回执与 metadata 压缩档。

## 补充批与最终结果

经确认 v192/r2 与 v193/r1 也已结案，补充批对这两个明确目录执行相同完整核验后删除 stage。它们的 tar、manifest、全部旧结果与源码记录仍保留。没有扩大扫描或降低运行磁盘门槛。

| 旧 bundle | 回收分配空间（字节） |
|---|---:|
| software-benchmark-v192/sdk-bundle-r2 | 504315904 |
| software-benchmark-v193/sdk-bundle-r1 | 504418304 |

两批共移除 18 个可重建 stage、跳过 2 个缺 manifest 的目录；回收 **9,069,445,120 字节（8.4466 GiB）**，已达到至少 8 GiB 目标。最后观察的可用空间为 **147,450,478,592 字节（137.3240 GiB）**。磁盘工作至此结束，后续正式 gate 应按当时实际空闲量重新判断，不将本回执当作永续容量保证。

补充批 [summary.json](../../artifacts/software-benchmark-v203-2-3/disk-reclamation-r2/summary.json)；最终合并 [final-summary.json](../../artifacts/software-benchmark-v203-2-3/disk-reclamation-r2/final-summary.json)。

## 按需恢复

只在确实需要旧展开目录时，先重新检查对应保留 tar 的 manifest SHA256，在一个新的空目录中以普通用户执行 `tar --no-same-owner -xzf runtime.tar.gz -C 新目录`。tar 的普通文件内容与被删除 stage 已逐文件核验一致；如需复原原先的普通用户目录模式和时间戳，使用对应 `stage-metadata.json.gz`。不需要 root，也不要把 tar 中容器用的 UID 0 应用于宿主机。
