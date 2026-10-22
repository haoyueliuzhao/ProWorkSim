# v055 缓存回收授权与上线观察

2026-10-22，用户明确授权回收 `runs/software-benchmark-v054/native-lazy-cache/<任务>/<版本>/rootfs`，条件是同题旧三组与新六组均已结束，且没有进程或锁占用。所有实验记录、补丁、评分结果、Docker镜像和环境清单继续保留。此次授权针对前次自动审批拒绝的具体目录范围；不扩展为任意项目目录清理。

实际执行仍使用已封存的 `tools/reclaim_benchmark_cache_v055_r1.py`，SHA-256 为 `add7b61e57b7518f130eda86294b225a30dadacec70ad549dd6ed94649e300de`。既有安全门、原缓存锁与每项 intent／completion 记录均保留；单项失败留待异常集合处理，不阻塞后续候选。完整边界见[缓存回收设计](software-benchmark-v055-cache-reclamation.md)。本次没有重新进行原工具的静态审查或CPU测试。

## 必要起点观察

08:41:58（Asia/Shanghai）的只读检查显示：v055 r3协调器仍为active/running，但没有正在执行的生成回合。data0可用约84.0GiB，低于100GiB新生成准入门，也低于128GiB新准备门；CPU一分钟负载约5.07、可用内存约943GiB。因此该时点的直接限制是磁盘容量，不能沿用前一夜“约29并发”的描述。

该时点v055已有609个生成闭合、57个生成技术未知、2334个待生成；这些是流水线状态，不是模型完成率。已准备任务库存充足，重新越过磁盘准入门后协调器可以继续派发。费用账本无hard halt。没有读取任务轨迹、模型思考内容或评分结果值。

旧v054 formal state在04:17:07更新为`paused_technical_unknown`，08:42观察未找到活动formal coordinator，GPU3、GPU6优化resident和REF resident、dynamic-pool、deferred-scoring服务仍在运行。这个状态出现在本轮回收之前，不能把它记为缓存回收造成的暂停。本次观察者没有向这些服务发送信号或改动其状态。

结构化观察保存于 `runs/software-benchmark-v055/cache-activation-observation-r1/before.json`，时间08:43:25，SHA-256为`3cf02a000ed30f1ff2bf7bdb878ef74cb724cc63e3bdfafd6530cc7682b38ceb`。该文件在首个单例已完成后、watcher上线观察之前写入，因此它不是删除前磁盘基线：当时completion数量为1、GC failure数量为0，data0可用97,810,776,064字节（约91.09GiB）。首次删除的真正前后数据应引用collector自己的intent／completion。

## 后续上线观察

后台 `proworksim-v055-cache-reclamation-r1.service` 已启动，初始使用 `--watch --batch-size 4`，每个周期结束后等待60秒；CPUQuota为200%、MemoryMax为1GiB、IOWeight为10、Nice为10。08:44:07只读确认服务为active/running，完成记录累计5项、failed及dispatch-uncertain均为0；08:43:51的一个周期执行4项且全部完成。

同一次08:44:07观察确认v055从0个生成回合恢复至28个，pending从2334降至2306，说明已在某个调度时点重新越过100GiB磁盘门并自动派发。`dispatch_stopped`仍为false。没有重启或重放已进入的实验回合。回执为 `runs/software-benchmark-v055/cache-activation-observation-r1/after-first-cycle.json`，SHA-256为`461a365f7c03a8c1e822b690b8b9c2b3b2f670de2f3d803b696647024a754e09`。

启动并行环境clone也同时消耗空间：08:44:07的可用空间47,917,928,448字节（约44.63GiB），低于新派发门。现有任务继续执行，后续派发由门控和持续回收共同调节。因此只能据此确认恢复过派发，不能称磁盘余量已经稳定在100GiB以上。并发工作可能同时增加或减少磁盘占用，不能把系统可用空间的全部变化直接记为回收量；实际回收对象和证明以逐任务completion为准。


08:46:38累计已有10份completion，对应manifest的普通文件逻辑大小共40,686,153,628字节（约37.89GiB）。该值是被删除目录内文件的历史逻辑大小，不是实测物理回收量；当时data0可用41,702,932,480字节（约38.84GiB），仍受其他并发写入影响。没有重复执行du或重哈希大型rootfs manifest。

抽查首个与当时最后一个按任务名排序的completion（matplotlib-25479、pytest-7432）：两个rootfs均已不存在；各自lazy receipt与四份环境／资格manifest仍存在且文件大小与intent一致，小于100KB的metadata也仍匹配原SHA。两题各9份episode/result.json仍存在。collector intent明确未删除Docker镜像或episode／patch，此处未额外启动Docker镜像扫描。小型核验回执为 `runs/software-benchmark-v055/cache-activation-observation-r1/reclamation-and-retention.json`，SHA-256为`1248bb4966120b8a4801841ccdc173f7c001bb843c8dc35ebc925f1f0b6c40bc`。这是一轮必要抽查，不替代每项collector自身的严格准入证明。


## 共享磁盘预约上线后的有限观察

08:53:29只读确认v055 r4协调器与GC均为active/running。此时641个生成closed、58个technical_unknown、15个running、2286个pending，另有4个评分执行中；这些状态不涉及评分值。r4状态中出现共享`disk_reservation_status`且metadata_error为null，15个在途生成的峰值预约合计288,763,862,948字节。策略刻意把已分配空间重复计入剩余需求，因此预约属于保守估计，**不是文件系统配额，也不等于当时实际额外待写字节**。当时实际free为92,189,974,528字节，尚不满足新的生成准入，不能把15个在途回合全部称为r4新派发。

同期GC累计31份completion，历史逻辑文件103,998,131,721字节（约96.86GiB）；failed与dispatch-uncertain仍为0。回执`after-v055-r4.json`的SHA-256为`c012dea521a72df2f643aaebd84b89cc94dca7f3dad63411ac4ba351151365f1`，已和此前3份小回执一并归档。期间没有执行du、重新测试模型或改动已进入回合。旧Qwen协调器后续恢复由独立变更负责，本观察不把旧prewarm已经退出的进程当作新生产者。


旧Qwen的资源协调器随后完成单独adopt（SHA-256 `d271501e20c416a3f6152438e51d04709ef2c320416361accc8000169741346d`），以USER服务`proworksim-v054-formal-queue-resource-r1.service`运行。08:55:17与08:56:39两次有限只读观察均确认两批新协调器和GC为active/running，两个共享预约状态均无metadata_error。此前旧prewarm SYSTEM服务已在04:03退出，不属于此时在途生产者。

这82.6秒内，v055由644个closed、12个running变为647个closed、9个running；pending保持2286，说明继续完成收集3个既有回合，未新增派发。v054状态已从暂停改为running，但生成仍为0、pending1053不变，明确等待`shared_disk_peak_reservation_gate`且没有claim新槽，不能将协调器恢复称为GPU回合已经恢复执行。两个协调器均继续遵守共享峰值预约。

最后观察时GC累计43项，历史逻辑文件137,548,052,824字节（约128.10GiB），failed和dispatch-uncertain为0；磁盘free156,627,456,000字节（约145.87GiB）。在途9个v055回合仍按策略保留173,174,849,706字节峰值预约，扣除预约再加入下一题后不满足100GiB余量要求，因此新生成暂缓是预期资源门行为。后台继续回收、在途任务继续结束；这组短观察不保证之后恒定吞吐或磁盘余量。

两点回执已归档：`shared-hosts-first.json` SHA-256 `1e4a7687f726a41fccb279a911d35b6e21edd982a46a40688ab55ce6154b9d4e`；`shared-hosts-last.json` SHA-256 `ec7703f70b329b1ee93f577c2d609664967852ada9539ab2097e70e87db1c220`。两点比较只读取任务状态与资源metadata，没有读取模型思考文本或评分值。


## 缩短回收空等后确认实际派发

后续启用`proworksim-v055-cache-reclamation-r2.service`，复用同一r1特权helper、资格门和每批最多4项的规则，只将两轮之间空等由60秒缩为10秒。协调器在旧watcher没有child且睡眠时交接，证据另存`cache-watcher-r2/handoff`；本节只报告其后的有限观察，不重复检验原路径。

09:02:06至09:03:33（约87.4秒）两点观察终于确认两批都有新派发：Qwen pending从1053降至1050，新增3个dispatch，最后3个generation running；DeepSeek pending从2279降至2273，新增6个dispatch，最后10个running、659个closed。两个协调器与GC r2均为active/running，共享磁盘metadata_error均为null。Qwen仍有`waiting=shared_disk_peak_reservation_gate`记录，这是下一槽的准入等待，不能据此否定已经进入的3个回合。

最后GC累计93个rootfs完成，历史普通文件逻辑大小291,778,528,694字节（约271.74GiB），failed和dispatch-uncertain仍为0；实际磁盘free329,971,384,320字节（约307.31GiB）。此时已能确认实际派发恢复，尚不能据87.4秒窗口推断长期稳定吞吐。用户随后另行授权的历史中间数据清理由独立流程记录，不包含在本93项rootfs统计中。

两点回执`gc-r2-first.json`与`gc-r2-last.json`已归档，SHA-256分别为`5eeb1867624e22c1a63a166728fd1de2302466d913edc75ef53930c1e4f0ddb3`、`6443d3970724c8e6e13936e877d9d5f0a4695407b5c2502b516ea3fd1ad99dc9`。本轮至此结束有限观察，不继续无限轮询。
