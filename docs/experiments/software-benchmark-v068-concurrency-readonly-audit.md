# v068 并发瓶颈：已完成 episode 的只读证据

当前 profile 的 30 路硬资源需求不可行；历史记录也不足以证明可以降低 actor 或 controller 内存。审计只读统一恢复库存中的旧结果及原账本，没有检查或操作 live 容器，没有压力测试、限额修改或新 API 请求。小型数据产物见 `artifacts/software-benchmark-v068/concurrency-readonly-audit-r1/summary.json`。

## 查到了什么

库存包含 197 个可读结果引用：API 15 closed / 165 technical_unknown，Qwen 6 closed / 11 technical_unknown。本次检查 1198 份结果、执行意图、controller-result、就绪及清理 metadata。它们不包括恢复后新完成的 v068 任务。

没有找到 `memory.peak`、Docker `memory_stats/cpu_stats`、`cpu.stat`、`CPUUsageNSec`、RSS 等所检索的实测字段；现有运行器也未保存 Docker stats 或退出前 cgroup peak 采样。可用的停止状态有 187 个 actor、185 个 controller，均记 `OOMKilled=False`。这证明这些 State 中没有记录 OOM，不能推出内存峰值低于 16 GiB，更不能证明 2/4/8 GiB 足够。

可从 Docker State 的 StartedAt / FinishedAt 得到真实容器存活时间：

| 已闭合组 | 数量 | controller 存活中位数 | actor 存活中位数 | controller 范围 |
|---|---:|---:|---:|---:|
| API | 15 | 462.691 秒 | 510.336 秒 | 91.795–1452.494 秒 |
| Qwen | 6 | 887.610 秒 | 914.448 秒 | 634.063–1969.754 秒 |

在有两端时间的 API 177 条记录中，actor 启动到 controller 启动间隔中位数为 24.705 秒，范围 10.291–47.948 秒。这是启动阶段时间，并非 actor CPU 时间或测试时长。抽查 R3 episode 50 的 native-rpc-transcript 共 45 个 request/response 对，没有逐工具用时字段；不能据此计算测试占空比。

对 15 个 API closed 槽的 691 个已结算请求，原账本 reserved_utc→settled_utc 的时长中位数为 2.082 秒，范围 0.6571–69.4386 秒。逐槽合并重叠区间并裁剪到 controller 存活窗口后，其覆盖比例中位数为 53.06%，范围 8.08%–74.77%。这只是**金额预约期间的时间覆盖**，既不是 CPU 空闲比例，也不是纯 HTTP 延迟；不能把 controller 或 actor 在其余时间都归为测试，也不能把预约期间都归为可释放内存的闲置状态。

## 30 路具体缺什么

冻结 actor=4 CPU/16 GiB、controller=2 CPU/16 GiB，一对固定预约 6 CPU/32 GiB。30 对仅自身即为 **180 CPU / 960 GiB**，已超过全项目 **152 CPU / 832 GiB**，尚未计模型、评分器和协调器。另有独立的 12 个合法 actor lane、对应 CPU 布局与 12 线程 generation executor；desired=32/64 不会增加这些实际资源。

保留 30 个 controller 的 16 GiB，仅 controller 就需 480 GiB。若同时保留六个原 96 GiB Qwen resident，再加两个 coordinator 的 32 GiB，已经达到 1088 GiB，尚无任何 API actor、Qwen episode 或 grader。因此，在 controller 限额不降且本地六驻留继续优先的情况下，30 路不能仅靠“actor 空闲时少占一点”实现。

## 唯一值得继续验证的最小路线

保持每题独立 volume、actor 进程/命名空间、持久 shell 和所有后台进程，保持 controller 16 GiB；只研究把 API actor 的**静态整题预约**改为“实测可回落的 idle 预约 + 有界工具执行 burst 池”。不要通过复用别题容器、丢弃 shell 状态或把任意 terminal 命令当成可中断测试来节省内存。

这条路线的硬算术门可以具体写出：30 个 API controller 480 GiB，1 个 Qwen resident 96 GiB、2 个原 Qwen pair 64 GiB、2 个 grader 32 GiB、2 个 coordinator 32 GiB，共固定 704 GiB，留给 API actor 全体的上限为 128 GiB。若允许最多 4 个 actor 同时使用原 16 GiB burst，其余保持 idle 上界 m，则必须满足 `30m + 4(16-m) ≤ 128`，即 **m≤2.462 GiB**。例如 m=2 GiB 时合计 820 GiB，但这只是算术可容纳条件，当前没有实测数据证明 m=2 GiB 安全。

因此最小下一步应是只读取得现有 actor/controller 的 `memory.current/peak`、CPU 计数，以及命令/后台进程的生命周期对齐证据，先检验这个数值门。若后台命令尚存或内存不能安全回落，必须继续占有 burst 预约；不能强制缩内存、杀后台进程或伪造工具完成。真正实施还必须另建 allocator/角色分离与新合法 CPU lane，保持原任务、工具 schema、反馈、token/金额预算不变，并明确记录排队对现有墙钟边界的影响。本轮没有实施上述 profile，也没有据此宣称达到 30 路。
