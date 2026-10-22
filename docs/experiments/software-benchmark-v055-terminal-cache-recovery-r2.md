# 九组终态但旧退出证据未闭合的共享模板回收

2026-10-22，用户要求清理无用数据以缓解运行中主盘和副盘的磁盘准入压力。本修订只处理主盘共享原生模板。现场审计时，198 道题已经满足旧 Qwen 三组和新 DeepSeek 六组全部生成及既有评分终态；原滚动回收器已回收其中 182 道，仍保留 16 道。原 watcher 正常运行，并非停止或卡死；它保守拒绝旧 writer 退出证明不完整或历史 attempt 尚未单独审计的任务。

本次已实际回收 **16/16 个 rootfs，失败 0**。删除前一次 `du -s -B1 -x` 观测的这些目录分配空间合计为 **61,978,038,272 bytes，即 57.7215 GiB**。这是已退役 payload 的分配块测量，不是并发实验期间整盘 free 的差值，也不把当前磁盘可用空间全部归因于本次操作。目录下的资格、源版本、镜像及回收元数据均保留。

## 为什么使用新的现场证明

16 道题中，原回收器首先报告 12 道完整 quiescence 未证明、3 道存在额外历史 generation attempt、1 道 resource release 未证明。类别按首次拒绝原因计数，部分任务同时具有多种旧问题。对应任务都仍保留完整的单次 claim 和 `scope-registry.json`。

旧证据中的 FileNotFoundError、退出等待 TimeoutError、技术未知、预进入失败和行政闭合记录没有修改。本次也没有把它们重分类为成功。新的证据只回答清理时这些目录是否还有合法消费者或 writer，不补写过去时点的退出事实。

新入口 `tools/reclaim_terminal_cache_v055_r2.py` 固定允许 16 个任务，计划绑定各 rootfs 的设备与 inode、原 lazy preparation 引用及九组终态投影。它私有加载已封存的原回收器，只替换其历史 quiescence 前提；原 `privileged_one` 中的排他 cache 锁、精确 registry/manifest、rootfs 路径和设备、禁止内部挂载、删除前重新比较同题状态、不可覆盖 intent 和 fd 式安全 `rmtree` 原样复用。

新现场证明在原 cache 排他锁内完成，具体包括：

- 九个消费者必须与原 1500/3000 槽位清单逐字段相符，全部生成和既有评分终态；closed 生成仍须具有评分记录。
- 每个消费者必须具有精确 claim 与非空完整 scope registry。旧 quiescence 内的 scope 也并入检查，不能通过新 registry 漏掉旧 writer。
- 所有当前及历史 generation job 必须有绑定的真实退出 completion。v054 使用 `exited`，v055 使用 `process_exited`；预进入失败须保留其 `slot_claimed=false`、`entered=false`、零模型调用证据。
- 所有生成、历史 attempt、预热和评分 worker 必须 inactive/failed、MainPID 为 0；所有注册 scope 的 InvocationID、cgroup、main PID/start ticks 和 outer launcher PID/start ticks均重新核对。
- 检查每个 claim 的完整资源 slice 当前未 populated，防止只核对已登记 scope 而遗漏其他后代。检查结束再次核对 claim 和 registry 字节身份。

本次实际重新证明 **144 个终态消费者及 362 个注册 scope**。没有停止、重启或重载模型服务，没有向任务进程发信号，没有修改任务队列或预算账本，也没有新模型调用。

## 范围和保留材料

唯一删除范围是 `runs/software-benchmark-v054/native-lazy-cache/<任务>/<版本>/rootfs`。16 个任务及各目录删除前分配量保存在固定 plan 中；没有扩大到其余任务、工作树、Docker image、模型、补丁、轨迹或评分记录。

本次 intent 和 completion 位于独立的 `runs/software-benchmark-v055/terminal-cache-recovery-r2/`。cache key 中仍按原回收格式新增 `cache-eviction-v055-r1.json`，并在原回收记录目录新增只指向本次 completion 的 forwarding receipt，使未改动的 watcher 不会持续重复尝试这些已经退役的模板。旧失败或不完整证明保留在原位置。

本批九个消费者都已经终态，因此本轮后续生成不会复用这些模板。未来新增实验如需同题环境，必须识别 tombstone 并在新的 cache generation 中从保留的 Docker image 重新准备和准入；原 payload 不再存在，也不声称重建后字节必然完全相同。

## 必要核验和审计引用

新增部分执行一次 8 项 CPU 控制：合法已回收 unit 可通过，跨 claim、PID=1、复用 InvocationID、活跃服务、populated cgroup、原 main 仍活、原 outer launcher 仍活均拒绝。原已封存删除器的全部测试没有重复执行。随后只读检查最复杂的 django-11276，9 个消费者、24 个 scope 全部通过，再封存计划并逐题执行有限 helper。

第一次只读预览把 v055 completion 错按 v054 的 `exited` 解析而拒绝，实际删除为 0；封存前修正为两代各自的精确状态值。该预览失败在 CPU 回执中保留，未伪称第一次即通过。

小型证据归档在 `artifacts/software-benchmark-v055/terminal-cache-recovery-r2/`，合计约 46 KB；完整现场 systemd/claim 证明保留在本地 intent，以 SHA 引用。未复制任何模型输入正文、密钥或环境 payload。

- 新入口 SHA：`368d9dac7a2714f48188599cf31c01def3e13b426620d16c8ebe57b7d70d7b67`。
- 原回收器 SHA：`add7b61e57b7518f130eda86294b225a30dadacec70ad549dd6ed94649e300de`。
- plan SHA：`f1a0beacf91344231e4a2c40977af6d26b1259a17ecd0de303c7467aee5cd33e`。
- summary SHA：`59220324c1f68a8c4282428d066ccf43091ddcf34865e75d1aa8322c23bc3ba9`。

这次回收增加了可供主盘后续派发使用的容量。实际并发和完成速度仍由主/副盘剩余预约、CPU、内存、环境供给和模型任务耗时共同决定，不能仅凭回收字节数宣称吞吐已经提升。
