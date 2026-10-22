# 共享模板的消费者库存与预热优先门

## 原因与最小修订范围

原 v055 预热库存门按六组都未进入的合格任务计算，库存达到 8 个就停止新预热。这个总量无法代表进度更快的其他消费者：本次观察时，Qwen REF 的 pending qualified 库存只有 1 个，MATCH/PROJECT 仍各有 131/132 个，v055 总体未使用合格库存仍有 115 个。继续依赖总体库存会让 REF 消费最后一个模板后等待，即使仍有大量其他消费者尚未使用的缓存。

另一个限制是磁盘竞争。cold prewarm 本身预约 128 GiB，并要求启动后保留 128 GiB；新 generation 原门仅要求其完整预约后保留 100 GiB。即使释放一批缓存，新生成也可能先消耗空间，使预热长期得不到所需的 256 GiB 未预约空间。

此次新增共同 helper、v055 r5 host 与 Qwen 对应薄 host。原 frozen sources 不修改；scientific solver、slots、模型服务、采样、预算、评分、已进入的任务全部保持原身份。主协调端负责分别在两个旧 coordinator 的安全边界切换，worker 不停止。

## 库存需求与原题顺序

共同 helper 只读取原任务身份、`generation.status`、模板 readiness 和准备 worker 的运行状态，不读取模型答案、补丁、成绩或失败题接近程度。

对 Qwen 三个消费者分别统计 pending qualified 与 pending preparing 的数量，目标是保留合计 2 个未来可用模板。这里的 2 是补货目标，不要求删除其他消费者已经积累的合格库存。对不足的消费者，按其原冻结队列顺序选择所需的最前冷模板；合并重复身份后，按 v055 原任务顺序最多选择 2 个不同模板。failed 模板不进入该预热候选集合，也不自动重试。

v055 原有“未使用合格库存不足 8”的正常预热门保留。若总体库存已很多，仅共同 helper 指定的低库存补充任务可以通过这一库存门；其余 CPU、内存、磁盘、准备并发与原 initializer 资格要求仍照常执行。每轮仍最多两个准备 worker，不增加另一个旧版预热生产者。

## 防止预热被新生成抢占空间

两个 host 继续使用同一个 `disk-dispatch-r4.lock`。持锁期间读取双方最新状态、计算预约和低库存需求，并一直持锁到 durable intent 与 launch 完成。

若确有选定冷模板需求，且没有准备 worker 正在运行，新 generation 要满足：

```
free − 两队列活动峰值预约 − 本次新generation预约 >= 256 GiB
```

256 GiB 等于 cold preparation 预约 128 GiB 加 preparation 的 128 GiB 最低余量。它替代普通 generation 的 100 GiB 门，不额外叠加成 356 GiB。

一个预热 worker durable 启动后，其 128 GiB 已自然进入原活动预约；此时取消额外的预热优先门，普通 generation 回到原 100 GiB 最低余量。准备中的任务也计入对应消费者的未来库存，避免每个 tick 继续过度补货。评分和在途任务不受新增优先门控制。

v055 r5 只对所选模板绕过总体库存门，仍调用原 `Coordinator.launch_preparation` 构建完全相同的受限 worker、请求和持久化 intent。其余 generation 路径继承 r4，不重写派发主体。

## 必要控制与身份

一次 CPU 控制通过，零模型、零实际预热、零 worker、零 rootfs 删除、零正式队列写入，覆盖：

- 1 个合格库存只补原序第一冷模板，失败模板跳过、三消费者同题去重。
- 零库存时最多选 2 个不同模板。
- 准备中的任务计入库存并解除额外优先空间保留。
- 修改模拟成绩字段不改变需求结果。
- 256 GiB 边界和差 1 byte 的拒绝，且无需求时恢复原 100 GiB 门。
- 容量元数据缺失时安全拒绝，不抛异常中断队列。
- 仅选定模板可绕过总体大库存门，原 worker builder 在共同锁内调用。

证据位于 `artifacts/software-benchmark-v055/shared-preparation-priority-r1/`。

- 共同 helper：`src/proworksim/software_benchmark_preparation_priority_v055_r1.py`，SHA `26b4055e559701defdd957b568a7eed9d33e8b6c867457b12eeb6e7cd4964b1e`。
- v055 r5 host：`src/proworksim/software_benchmark_queue_native_host_v055_r5.py`，SHA `1da064361a1b6d2fad67fa11d9fb852aa2dc0c4168d0153dcf64919daea1466b`。
- v055 r5 revision SHA：`682263c0d1a40676bbf5387c3ca0a1cfa668727c95baf72e6ba06b334eb0aaf3`。
- CPU 控制 SHA：`6488586f2790e676d7a5b22fb3199e1d28434487f56c8a52e71b802fef2635e5`。

Qwen 薄 host 的独立 seal、原派发主体保留证明与控制由对应 host 修订记录提供。这里的 passed 指 CPU 准入控制通过，不表示实际冷模板已准备完成，也不表示整批实验完成。
