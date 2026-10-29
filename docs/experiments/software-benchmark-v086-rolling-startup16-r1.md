# v086：16 个环境启动槽的滚动接续方案

状态：已通过有限 CPU 控制并完成真实滚动部署。旧 v085 只暂停新派发，在途任务自然完成；新 v086 已开始接续互斥库存。实际吞吐与资源观测另存，不能仅由 CPU 控制通过或配置上限推定性能。

## 目标和不变条件

v085 已跨过之前 FD 故障触发时长，仍可能因为 8 个环境启动槽长期满额而无法及时补足实际生成任务。v086 把共享环境启动上限提高至 16，并给新管理进程 8 CPU，目标是减少环境初始化造成的派发空档。全局 API actor 上限仍为 48，Qwen 仍为 4；容器单体限额、原模型、任务、seed、上下文、每题 token 预算、工具接口及官方评分标准保持。原 1500 元唯一账本和 uncertain 预约不重置。

此处“启动槽”指 actor 尚未形成可信 controller-ready 的阶段，不是 API 请求并发或已完成任务数。16 个启动槽、48 个 actor 上限都不能写成实际达到的并发。需要观测完整启动耗时分布、实际 active generation／API 请求、评分积压和单位时间终态增量。

## 资源变化

| 项目 | v085 | v086 |
| --- | --- | --- |
| 环境同时启动上限 | 8 | 16 |
| API／Qwen actor 总上限 | 48／4 | 48／4 |
| 管理进程 CPUQuota | 400% | 800% |
| 管理进程 CPUAffinity | host pool `[164:168]` | host pool `[168:176]` |
| 管理进程 MemoryMax／swap | 64 GiB／0 | 64 GiB／0 |
| 单服务 NOFILE | 16384 | 16384 |
| API 容器共同父组 | v085 第二生命周期，224 GiB／swap0 | 复用同一实例 |

本服务器固定 host pool 为 0–175；新管理集合为 168–175，与当前本项目 actor/controller 4–75、grader 76–91、模型 92–163、Qwen 管理 0–3、v085 API 管理 164–167 不相交。没有枚举或修改其他用户任务，不能据此宣称这些核心为主机独占资源。

滚动重叠期间明确保留旧 4 CPU／64 GiB 和新 8 CPU／64 GiB 两份管理租约，因此新增配额为 8 CPU／64 GiB；224 GiB 父组仅约束 API 容器，不包含管理进程。新管理服务的首次预约要求真实宿主可用内存至少 384 GiB，并使用已有 CapacityProbe 的新鲜全机 CPU 样本确认利用率低于 85%。CPU 采样在共享分配锁外完成，进入锁后核对样本不超过 10 秒，避免等待采样阻塞在途资源申请。原 quota 数值总和仅用于诊断，不能替代真实余量门。

actor 准入继续受真实 CPU、内存、磁盘、父组及管理进程内存门保护；待启动 pair 仍按原完整 32 GiB 预留估计计入计算。新服务继承 v085 FDGuard 和 ManagedClient／ManagedLedger，首次初始化即使用显式关闭 SQLite 预检连接的客户端，不能先初始化旧客户端再加外层包装。

## 滚动交接和旧任务保护

1. 核验精确旧 `proworksim-v085-api.service` 身份，入口必须为 `run_api_recovery_v085.py`。将旧新增派发设为 0，等待修改后新鲜的 configured/effective 0 确认。
2. 冻结全部旧调度事件和游标。新 allowlist 排除已有生成状态、任何旧 scheduled 身份、历史 actor/controller/volume claim、原 episode 目录和账本中任何请求身份。仍使用完整原 1000 题分母。
3. 旧在途生成在新报告中单列 `external_running`，不计完成或失败。新服务仅接未消费身份，与旧端共享同一父组、资源锁和账本。
4. 如果旧端还有已经排入 future、尚未取得 actor claim 的任务，新端暂停额外新增，优先让这些旧 future 取得资源。这一点比单纯从 48 中扣除旧 future 更严格：旧 allocator 仍只有 startup8，若新端持续填满 startup16，可能令旧未领取资源的任务一直被旧 8 槽门挡住。
5. 旧端所有实际生成、评分、待评分及 `active_grading_jobs`／`pending_grading_jobs` 必须自然清空，旧身份的活跃 claims 和未结 reserved 请求也必须归零。仅有 prepared request 并不证明归档校验或交付分析已经停止；本次不转移未完成旧评分来提前退役。
6. 确认旧 cgroup 仅剩原主 PID，持有共享分配锁再次验证静止与游标未变化后，用 pidfd 只结束旧主进程，避免其正常 finally 提前清理新旧共用父组。释放的只是旧管理租约。
7. 封存旧最终历史并按任务 ID 合并一次。新队列的全部评分准备、执行、交付验证继续使用 v082 的异步工作线程；新代码不操作 Qwen 生命周期。

跨版本结果保留 v085／v086 部署标签。这是部署并发变化，不能宣称墙钟影响完全消失：拥塞和初始化时延仍可能改变超时概率。模型任务限制虽然未放宽，后续报告仍应保留实际墙钟、技术未知和不同部署阶段。

## 验证与入口

8 项针对性 CPU 控制通过，包括实际 policy 绑定下 11 个 pending 启动只剩最多 5 个新启动位；原 v076／v079 常量保持 4／8；旧 unclaimed future 优先；异步准备／交付 descriptor 阻断静止；CPU 范围与 NOFILE；真实 CPU 门；新 parent／owner scope 实际绑定；库存互斥；FD 客户端初始化顺序。只使用 synthetic fixture，不运行 Docker、模型或外部 API。

主协调者决定部署后执行：

```bash
.venv/bin/python tools/run_offline_scorer_v058.py tools/prepare_rolling_api_v086.py --bootstrap
.venv/bin/python tools/run_offline_scorer_v058.py tools/prepare_rolling_api_v086.py --gate
.venv/bin/python tools/run_offline_scorer_v058.py tools/prepare_rolling_api_v086.py --inventory
.venv/bin/python tools/run_offline_scorer_v058.py tools/launch_rolling_api_v086.py --launch
```

库存返回 waiting 时不得提前启动。未产生新 launch-intent 前可用 prepare 的 `--rollback-before-launch` 恢复原旧控制；新服务启动后禁止重新打开旧库存。没有创建新的 root 资源组或修改 v085 冻结源码。

准备时只读检查还确认：v085 进度中的既有 1 条 isolated exception 是初始库存继承的旧 slot4212 生成未知；当前 3 个 active 与 3 个 pending 评分 descriptor 均无 outcome，属于真实未完成工作，没有发现 terminal descriptor 导致永久静止阻塞的证据。本观察不替代实际交接时的重新核验。

## 已完成部署

封存时旧端有 42 个在途生成任务，新端固定接续 168 个未消费任务。实际启动后全局 API 活动任务预约达到 48，Qwen 仍为四题；这里包括旧端运行与新端启动，不是 48 条同时推理的 HTTP 请求。旧在途未被取消，旧评分保持原身份继续执行。新服务复用了 v085 父组，本次没有新建 root 资源组或更改共享主机配置。

部署证明位于 `artifacts/software-benchmark-v086/deployment-r1/`；独立只读监测使用现有 v085 监测器，明确传入 v086 根目录及服务名，记录全体 API actor／账本请求与新管理进程 FD。旧管理进程仍有独立自身限额与生命周期，不能把新进程的 FD 数当成新旧总和。
