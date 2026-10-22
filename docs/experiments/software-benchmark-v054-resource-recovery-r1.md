# v054 Qwen 磁盘资源故障后的独立调度恢复 r1

## 观察与原因

2026-10-22 04:03:55（Asia/Shanghai），原 CPU 预热器为
`matplotlib__matplotlib-25122` 导出环境时触发
`Native rootfs disk reserve gate during export`。证据为
`runs/software-benchmark-v054/native-prewarm-r4/events/00000299.json`；该操作的
`model_calls`、`formal_claims` 均为 0，原模板的 `preparation-failure.json` 保留。
原预热器 `proworksim-v054-prewarm-81a0e6c6.service` 为系统级服务，现为
`failed/failed`、`MainPID=0`，cgroup 已消失，原 PID 541413 不存在。

原 kernel 调度器将任意预热历史失败归入共享完整性错误，04:03:59 暂停新派发，
04:17:07 完成在途任务收集后退出。`waiting.reason` 中的
`no_healthy_prepared_resident_session` 是先前保存的等待描述，不能单凭它认定模型失活。
GPU3、GPU6 kernel-r6 和 REF-r2 驻留服务仍在运行。本次恢复不重载这些模型。

暂停快照包含 1,500 个原定回合：正常生成闭合 442、生成技术未知 5、未开始 1,053。
432 个回合取得明确代码评分；另有 10 个代码评分技术未知。汇总字段中的
461 个 `official_report` 还含 PROJECT 的交付端点评分，不代表 461 个独立回合。
这些数量只是恢复前运行进度，不是模型准确率。

## 修订范围

新增独立入口 `tools/run_qwen_resource_recovery_v054_r1.py`，继承已采用的原
`TransitionCoordinator`。原冻结源码、模型、原 1,500 槽位、种子、预算、候选锁定、
评分器及 GPU6 kernel-r6 执行绑定保持原身份。已进入回合不重放；原异常记录不覆盖。

恢复器只对两个精确封存的预热证据延期处理：299 号磁盘导出失败，以及与该失败对应的
1 号原 worker 启动记录现在已结束。失败任务本身继续留在未开始库存，直至未来有明确
环境修复；本版本不自动修复或重试它。其他预热失败、事件链变化、模板身份变化、
来源完整性错误及 claim 身份异常仍保持硬停止。可运行任务必须先具有原合格模板证据。

一次 `adopt` 在原 controller lock 下确认前一调度器已停止、整个暂停状态仍等于封存快照、
所有旧回合已排空且 pending 槽位没有 claim 目录。然后记录新的恢复收据，将全局派发状态
改为运行；原 rows 和 faults 在操作前后逐项保持相等。该动作本身不调用模型、不创建正式
claim、不启动或停止 GPU 服务。不能重复执行 adopt。

## 共享磁盘预约

恢复器与 DeepSeek host r4 使用同一个
`runs/software-benchmark-v055/disk-dispatch-r4.lock`。每次派发在该锁内读取对端最新状态，
扣除两个队列全部 `intent/running` 回合及新预热的完整估算峰值，执行容量准入，再保持锁
直到当前 durable intent 写入和服务启动调用完成。不会出现两个调度器同时依据同一瞬时
空闲容量放行的检查与写入竞态。

每个生成回合按根文件系统清单估算：
`2 × (regular_file_bytes + entry_count × 8192) + 8 GiB`。已有活跃回合若缺少可信清单，
按 96 GiB 预约；新回合缺少可信清单则等待。新环境预热每项预约 128 GiB。生成和预热
分别保留 100 GiB、128 GiB 余量。已经写入磁盘的活跃回合仍全额预约，属于有意的保守重复
扣除。对端状态暂时不可读时等待，不创建新任务，也不把它算作模型失败。

原 v054 预热器已经退出且本版本不恢复它；缺失模板由具有同一共享锁的 v055 预热流程补齐。
已合格模板仍通过原正式 worker 的 `qualified_paths` 检查；正式 worker 不依赖预热器持续存活。
评分和已在途任务收集不受新生成磁盘准入的阻塞。

上述预约是新任务准入机制，不是文件系统配额。它不能严格限制其他用户写盘或任意公开脚本
产生超出清单估计的文件；保守余量和已授权缓存回收仍需共同工作。

## 必要 CPU 控制与封存

`tools/check_qwen_resource_recovery_v054_r1.py` 的控制通过：精确故障集合以外仍硬停；
仅已确认失败任务延期；磁盘拒绝时槽位仍 pending 且不创建工作目录；两个队列的最新观察、
durable intent 和启动调用都处于同一锁中；已进入行不变；对端元数据缺失只等待。
该控制没有模型调用、GPU 加载、正式 claim 或服务修改。

部署封存：

- `runs/software-benchmark-v054/resource-recovery-r1/revision.json`
- SHA-256：`22edc9450e2c8d9fed97189965e1d2c9231a0bd2486af695f9e0852da7bd906a`
- CPU 收据：同目录的 `cpu-control.json`
- 原暂停快照：同目录的 `state-before-freeze.json`

本说明记录代码与控制就绪；实际 adopt 和后台服务启动应以同目录的 adoption 收据与运行
队列新状态为准，不能由 CPU 控制推断实验回合已经恢复。

## 已加载镜像的下载副本清理

用户随后明确授权“可以先删除部分无用历史数据”。本轮另行执行了范围固定的下载层回收，
没有删除实验历史结果：仅移除
`runs/software-benchmark-v054/images/preparation-r1/blobs` 下 597 个至少 1 MiB 的压缩
layer `.blob` 文件。500 个任务对应的 499 个唯一官方 image ID 均已在当前项目 Docker
中存在。当前原 Qwen、GPU6 kernel-r6 以及 DeepSeek 的 2,411 个直接冻结文件路径均不包含
所选 payload；后续原生环境由已载入的 Docker image 导出，使用的 actor 配置仍保留。

清理前后均未停止服务。执行时持有原准备/装载总锁及所有选中 payload 的下载锁；每个文件
必须仍是唯一硬链接的普通文件，stat 与已有 SHA 验证收据完全相符。执行前的项目下载消费者
检查为空。原配置 blob、小型 layer、下载和失败日志、manifest、SHA 收据、原镜像清单、
Docker images 与 Docker 内部存储全部保留。未来若主动重建离线下载缓存，需依据保留的
固定 digest 重新下载；历史下载完成收据不再代表副本仍在，清理收据明确记录其退役状态。

实际删除 payload 共 **131,930,045,491 字节**；删除前 stat 的分配块总量为
**131,932,614,656 字节（约 122.87 GiB）**。该数字是所删文件的已分配字节数，不是把并发
运行中的文件系统空闲量差值当成独立测量。

- 清理工具：`tools/reclaim_loaded_image_layers_v054.py`
- 计划：`runs/software-benchmark-v054/download-payload-retirement-r1/plan.json`
- 计划 SHA：`74bb51fc501091791f445bf8ed00d3bd3f8b85047914fd9074b5425d8719b126`
- 完成收据：同目录 `completion.json`
- 完成收据 SHA：`d17b2c19487719e8954324cf9595fc3ce103415a1e88fbc6e44d5e7f2db9898e`

计划、执行前证据及完成收据以原字节归档在
`artifacts/software-benchmark-v054/download-payload-retirement-r1/`，供审阅与追溯。
