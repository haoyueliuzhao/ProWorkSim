# 主盘预热解堵：两份终态共享缓存回收

2026-10-22 17:28:50–17:29:03（北京时间），在既有明确缓存清理授权内，删除了下表两份共享环境的 `rootfs`。两题各自的 Qwen 三组、DeepSeek 六组生成及评分均已进入终态。删除成功 2 项，失败 0 项；按删除前 `du -s -B1 -x` 的 allocated bytes，合计释放 **8,093,892,608 bytes（7.5380 GiB）**。

| 任务 | 精确缓存版本 | 删除前 allocated bytes | 本次重新核对 scope 数 |
| --- | --- | ---: | ---: |
| pydata__xarray-6744 | 705510eaefa1dadc | 5,135,515,648 | 25 |
| sphinx-doc__sphinx-9602 | 9830169f0038655d | 2,958,376,960 | 22 |

本次是主盘空间缓解措施的一部分，不能将这 7.5380 GiB 单独表述为预热瓶颈已经完全解除。并行实验仍在持续读写；文件系统可用空间的前后差值不等于本次回收收益。生成保留 100 GiB、预热保留 128 GiB，以及冷预热 128 GiB 预约均未修改。

## 保护条件与历史记录

独立工具 `tools/reclaim_prewarm_relief_cache_v055_r1.py` 将名单固定为这两项，并同时固定缓存版本、主盘 device 66306、原始目录 inode、终态消费者投影和资格清单。它在自己的进程中复用已冻结的 r2 当前静止证明与原 r1 删除器；没有编辑原工具、原 16 项计划或在运行的队列源码。

每项删除持有原任务 cache 排他锁，重新核对全部 9 个消费者及其完整 scope registry、历史 scope、精确 PID/start_ticks、systemd InvocationID、ControlGroup、资源 slice 和评分 worker；重新检查缓存清单、路径、设备、挂载点与终态消费者投影。完整当前静止证据分别保存在新的 `.intent.json` 中。各题历史均有一份 `all_quiet=false`，本次将其原样保留，没有改写为历史成功或抹除技术未知结果。当前观测完成后才调用原有防符号链接攻击的 rootfs 删除逻辑。

只删除两份 `native-lazy-cache/<任务>/<版本>/rootfs`。题目清单、环境元数据、资格回执、模型、Docker 镜像、补丁、候选、评分、账本和正式实验记录均保留。写入新的 cache eviction tombstone，并为原后台回收器补充独立完成引用，使其不重复删除。本次没有进程信号、GPU 重载、模型调用或正式回合重跑。

## 必要控制与证据

仅新增五项 wrapper 边界控制：两项精确计划可接受；第三任务、父目录、其他设备和 wrapper seal 变化均被拒绝。限定两份新增 Python 文件的 Ruff 检查通过。原有八项 scope/PID 静止控制与删除器控制直接复用，没有重复执行。

- 新计划：`runs/software-benchmark-v055/primary-prewarm-relief-cache-r1/plan.json`，SHA-256 `4d3f50d2c0989b0f6047e1398603a0732318219ec0c40e3680d44cb1d3233a45`。
- 新 wrapper：SHA-256 `ae4e5cd4c1390acbbce77dd92bc771b1225c04ae2b46e5613f5550e56c7a2a01`。
- 汇总：`runs/software-benchmark-v055/primary-prewarm-relief-cache-r1/summary.json`，SHA-256 `93204a6af96e39ef4f738c894e26dd9ec2e69d9f93cfd0ff97063dba6601771b`。
- 可提交证据副本：`artifacts/software-benchmark-v055/primary-prewarm-relief-cache-r1/`。

本报告只陈述本次缓存清理结果，不据此推断生成速度、官方通过率或整轮实验完成时间。
