# v055 缓存回收 watcher r2：缩短空等待

本修订只把原回收器每轮结束后的空等待从 60 秒缩短到 10 秒。原 `tools/reclaim_benchmark_cache_v055_r1.py` 的 `cycle` 与 privileged helper 原样复用，SHA 仍为 `add7b61e57b7518f130eda86294b225a30dadacec70ad549dd6ed94649e300de`。每轮最多尝试 4 项、原候选顺序与游标、九个终止消费者、进程/服务/cgroup 静默证明、固定模板身份、原准备锁、删除范围和永久异常集合均保持原实现。

新入口 `tools/watch_benchmark_cache_v055_r2.py` 在整个 watcher 生命周期持有原 `cache-reclamation-r1/collector.lock`，不增加 helper 并发。每次 cycle 仍验证原 source SHA，privileged helper 也执行原验证。新入口在启动前检查自身 seal、原 collector 和原 policy 身份，限定项目用户运行。部署保留 CPUQuota=400%、MemoryMax=1073741824、IOWeight=1000、Restart=no；这些由 systemd 服务属性提供，而不是更改删除规则。

必要 CPU 控制仅以 mock cycle 记录 3 次 `cycle(4, None, 原SHA)` 与两次 10 秒等待，未调用原 collector，零 root helper、零删除、零模型请求。它核验周期参数及边界，不重复测试已冻结 helper 的删除资格。证据位于 `artifacts/software-benchmark-v055/cache-watcher-r2/{cpu-control,seal}.json`。

- 新入口 SHA：`41ee98acdd4d6629d1a9058033f973d8e0d2f07638ac63b65407ec88079a8bd9`。
- seal SHA：`6e58e5513782bb2ce7822f618055aeeadf492de13c06a5ac47bb50776c64dde8`。
- CPU 控制 SHA：`5ad78e8d62000c2541ba5fe7327aece39603237e134d55ffe8489a624a648c35`。

切换只应在旧 watcher 处于睡眠且没有活动子 helper 时进行。实验 worker、模型服务和评分任务不随 watcher 切换停止。新版本每轮减少 50 秒固定空等；实际回收吞吐仍取决于资格核验、文件数量与磁盘操作耗时，不能据此宣称整体实验速度提高六倍。
