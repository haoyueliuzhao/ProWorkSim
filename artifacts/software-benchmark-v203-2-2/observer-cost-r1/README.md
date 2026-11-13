# v203.2.2 观测器有限合成配对成本控制

本实验直接使用现行 `Sidecar.record/finish`、`ObserverJournal`，未修改旧模块；恢复时使用真实 `PassiveState`。它衡量局部追加捕获开销，不能代表完整生产请求成本或长期可靠性。

同一冻结输入：3 对 × 每臂 1000 个捕获边界，另有 INITIAL/CAPTURE_CLOSED 两条。每臂 500 个合成操作，每操作两条边界；250 个模型输入/响应和 250 个工具意图/回执（默认规模）。全部为本地数据，真实模型/API/容器/GPU调用为 0。

各臂使用独立普通子进程，顺序交替，最多 1 个运行中子进程；单线程，CPU 硬上限 60 秒、地址空间上限 1 GiB。两臂输入散列、输出散列、操作数完全相同。所有开启臂逐条校验完整 journal 哈希链、键、类型及 payload；无捕获故障。

| 配对 | 观测 | 工作负载 CPU 秒 | 工作负载墙钟秒 | 进程峰值 RSS MiB | 每操作 p50 / p95 / p99 μs | 关闭后逻辑字节 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | off | 0.004154 | 0.004085 | 51.641 | 6.694 / 8.845 / 11.914 | 0 |
| 1 | on | 0.124103 | 0.149459 | 54.594 | 253.058 / 444.579 / 870.662 | 1630726 |
| 2 | off | 0.004165 | 0.004072 | 51.828 | 6.731 / 8.515 / 11.879 | 0 |
| 2 | on | 0.131714 | 0.159943 | 54.699 | 256.452 / 505.274 / 969.011 | 1630726 |
| 3 | off | 0.004148 | 0.004060 | 51.684 | 6.666 / 8.347 / 10.155 | 0 |
| 3 | on | 0.127272 | 0.155371 | 54.848 | 255.504 / 501.064 / 930.480 | 1630727 |

配对增量中位数：工作负载 CPU 0.123125 秒、墙钟 0.151311 秒、生命周期 CPU 0.129536 秒；峰值 RSS 差 2.953 MiB。RSS 是进程高水位，含双方共同导入，微小差值不解释为精确分配量。

独立故障例在最后一条回执提交成功、返回确认前自退出（退出码 73）；恢复子进程验证 1001 条 durable 记录并重建 250 个回执的 PassiveState，持久化投影检查点。恢复内部墙钟 0.051852 秒、CPU 0.051101 秒；含解释器启动、导入、结果写出的恢复进程墙钟 0.420506 秒。未重新派发任何世界动作。

`summary.json` 保存每臂的全部指标、配对差值、按操作类型延迟、进程总 CPU/墙钟、每 200 边界的 RSS/磁盘增长、开库采样峰值、故障恢复及限制；`protocol.json` 固定源文件和输入 SHA-256。`pair-*/{on,off}/measurement.json` 是原始测量，开启臂保留 SQLite 原件，`frozen-input.json` 是完整合成数据。

## 边界与限制

- Only 3 pairs of 1000 synthetic capture boundaries; no long-duration production or leak claim.
- The real v203.2.1 Sidecar.record/finish and ObserverJournal WAL/FULL path are reused; no legacy PassiveRecorder substitute.
- Both arms import the same runtime modules. Startup, imports and frozen-file loading are excluded from capture_lifecycle/workload times but included in parent-measured process totals.
- Synthetic model inputs/outputs and tool receipts are frozen, small and deterministic; no provider, real tool, controller scheduling, actual task, model reasoning or production payload replay occurs.
- Measured latency is a local synthetic operation (two capture boundaries), not provider/HTTP request latency; off-arm work is deliberately tiny, so relative slowdown is not a production percentage.
- Capture lifecycle includes initialization, INITIAL, append boundaries and finish/CAPTURE_CLOSED; operation percentiles exclude initialization, finish, disk/RSS sampling and verification.
- Workload CPU/wall includes common synthetic result hashing and bounded resource samples; no online graph projection is added, matching the real append-only Sidecar.
- Host HTTP capture, physical provider journal, SDK history, archival/compression, scoring, export, full offline analysis and persistent services are excluded.
- RSS is a process high-water mark/current Linux proc snapshot, not an allocation attribution. Startup imports are present in both arms; small paired differences can be noisy.
- Disk figures are logical file bytes and allocated st_blocks*512, sampled while open and after close; transient within-sample WAL peaks and directory metadata are not measured.
- Crash recovery covers process exit after final durable commit, with no prior projection checkpoint; it verifies the journal and reconstructs receipt-derived PassiveState only. It is not a restored running agent/controller or full accepted-request view reconstruction.
- Recovery excludes MODEL_REQUEST/MODEL_RESPONSE semantic projection; those records are still hash-chain verified and exactly reconciled against the frozen manifest.
- No power/storage loss, precommit evidence loss, concurrent writers, missing host records or production completeness guarantee is tested here.
- A single sequential run order off/on, on/off, off/on has no CPU pinning, cache flushing, isolation or confidence interval; shared-host scheduling/filesystem load may influence results.

## 复现

以新的空输出目录执行（拒绝覆盖已有证据）：

```bash
.venv/bin/python tools/benchmark_passive_observer_cost_v203_2_2.py --output artifacts/software-benchmark-v203-2-2/observer-cost-r2
```

本次运行是必要机制断言与测量本身；未重算原 12 题统计，未全量重放原模型载荷，也未运行冗余测试。
