# v055 新终态工作区无损归档 r2

## 范围与准备结果

用户要求继续清理无用历史数据。只读审计由现有 DeepSeek 队列的终态异常条目定位精确 rootfs 路径，未扫描整盘。固定 51 个此前未归档的克隆，原展开目录实际 allocated 合计 **169,918,124,032 字节（158.2486 GiB）**。这是待压缩源占用，不是已经释放或预计净释放量。

| 源卷 | 设备 | 数量 | 展开 allocated 字节 |
| --- | ---: | ---: | ---: |
| queue-r1（data0） | 66306 | 9 | 28,613,926,912 |
| secondary-volume-r1（data1） | 66307 | 26 | 90,334,273,536 |
| tertiary-volume-r1（data2） | 66308 | 16 | 50,969,923,584 |

旧副盘63项与主盘53项的冻结计划按原 SHA 核对，源目录和 item ID 均不相交。另13个历史静默证据不完整的候选排除；失败预热 matplotlib25122 的唯一 rootfs.tar 不清理。原 technical_unknown、claim、patch、候选、评分、轨迹与账本保持原样，任务不重跑。

全部51项已在原 scope-registry.lock 内完成一次现场静默准入：generation/scoring unit、注册 scope、PID/start ticks、cgroup、完整资源 slice 与目录挂载检查均通过。该准入仅说明观测时符合条件；真正 archive 与 release 仍各自持锁重证。

## 冻结实现和计划

新入口 `tools/archive_terminal_rootfs_v055_r2.py` 私有绑定旧归档模块的 OUT/VERSION/PATH_RE；第三盘语法只增加 `tertiary-volume-r1/workers/generation-<24hex>/episode/(public-test-N/)?actor/rootfs`，按路径卷名检查设备66306/66307/66308。原归档器 SHA `a1929b16a0deb0884e08ea66b542451d7bd8780ef6a6e936fd47a1661b233e13` 未修改。

- wrapper SHA：`875d0a44f5bad804848722b5ff59a731858555e8c01edf5f36c69d23c0a7341e`。
- batch SHA：`289ed003b68e66357280c0907ee194f3c56086036ce80052c7a9f97a3ca433e9`。
- plan：`runs/software-benchmark-v055/terminal-rootfs-archive-r2/plan.json`，SHA `0a221e788e1730e934ea68433d6111407efa7d76866b2c2e10f369ac53a1eb83`。
- allowlist：`runs/software-benchmark-v055/terminal-rootfs-archive-audit-r2/allowlist.json`，SHA `3adde46a9d2964b94312866abef405000e4a79f154c0cdb4345ac5ee4c4f987d`。
- 进度：`runs/software-benchmark-v055/terminal-rootfs-archive-batch-r2/state.json`。
- 回执：`runs/software-benchmark-v055/terminal-rootfs-archive-r2/<item_id>/`。

压缩包保持在各源卷既有 `terminal-rootfs-archive-r1/<新item_id>/rootfs.tar.zst` 容器内。这是原实现强制的 payload 路径格式，不代表重用旧任务；本批 metadata、plan、unit及51个源身份独立，原116项和回执保持不变。

## 保留的回收与恢复条件

直接复用原 GNU pax tar+zstd level1 编码、完整内容/metadata清点、全量解压回读、源稳定检查、同盘payload和100GiB空间保底。回读验证成员集合、文件SHA、uid/gid/mode、纳秒mtime、symlink、hardlink拓扑、xattrs/ACL和稀疏extent。只有 verified 回执可信且重新静默后才回收展开副本；每项保留恢复标记、压缩包和独立 released 回执。

恢复使用新 wrapper 的 `restore` 操作，必须提供本批 plan SHA、wrapper SHA、唯一 item ID，写入本批 metadata namespace 下的新目录，不覆盖原位置；完整恢复验证继续复用旧实现。原模型最终代码或异常状态不会因归档恢复而改判。

批次最多两个不同claim同时进行，同一claim串行；每个worker为2CPU/2GiB、IOWeight10、Nice10、1800秒上限。普通失败保留原件/partial并继续下一项，不重试未知partial。若不能确认失败清理worker退出，停止新增清理，不向模型队列发送信号。共享缓存回收和这个异常归档批次互不代替。

## 必要控制与状态边界

本次只运行新增绑定控制：51项数量、旧namespace拒绝、跨盘payload拒绝、tertiary错误设备拒绝、未登记卷拒绝、旧116身份不相交，以及独立worker资源参数。原codec与调度器已有控制不重复。详见 [wrapper-control.json](../../artifacts/software-benchmark-v055/terminal-rootfs-archive-r2/wrapper-control.json)、[admission.json](../../artifacts/software-benchmark-v055/terminal-rootfs-archive-r2/admission.json)、[live-admission.json](../../artifacts/software-benchmark-v055/terminal-rootfs-archive-r2/live-admission.json)。

准备阶段真实 archive/release 均为0。主协调者于北京时间2026-10-22 23:44:47启动 `proworksim-v055-terminal-rootfs-archive-batch-r2.service`，初次观察为2个真实archive worker运行、0项释放、无失败。真实成功项、失败项与净释放量以 batch state 和逐项 released 回执为准；净释放须扣保留压缩包allocated及少量metadata，不用并发实验期间整盘free差值替代。起步快照尚未执行到第三盘任务，不能把三卷路径控制通过表述成第三盘真实归档已通过。

## 实际三卷回收与交付前观察

北京时间 2026-10-22 23:55:55，批次仍在运行，**21/51项已释放，0失败或partial**，已释放项源allocated为68,565,880,832字节，保留压缩包allocated为26,370,449,408字节，实际净释放 **39.297558 GiB**，未减少量metadata。

首次第三盘item `07082286685481f18fc5b09c` 已产生完整内容与metadata回读verified回执和released回执，源目录已移除，保留压缩包实际设备为66308。主盘、副盘此前也已有成功released项，因此目前三卷均有真实归档后释放证据；这不代表余下所有项都已完成。有限批次会继续，个别异常仍由原生state和日志单列。

[固定观察快照](../../artifacts/software-benchmark-v055/terminal-rootfs-archive-r2/progress-at-three-volume-proof.json)与[首个第三盘释放回执](../../artifacts/software-benchmark-v055/terminal-rootfs-archive-r2/first-tertiary-released.json)。后台worker只更新runs，不持续改写这份Git快照。
