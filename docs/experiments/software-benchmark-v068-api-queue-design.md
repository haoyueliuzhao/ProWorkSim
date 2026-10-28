# v068 API 原库存恢复与动态并发

本文记录新 API 协调器的代码与 CPU 合同控制，不宣称已经发生新的 API 请求或实际达到任何配置并发数。真实启动、共享服务器状态、原队列收口和恢复库存的最终数量由独立运行记录给出。

## 恢复对象与不可重放边界

新入口为 `tools/run_api_continuation_v068.py`，自身输出根为 `runs/software-benchmark-v068/recovery-r1/api-coordinator`，实时环境资格来自同一恢复批次的 `primary-coordinator/cursor.json`。共享演员、控制器和评分器继续使用原 R3 `resource-claims` 池、原 `allocation.lock` 与既有创建身份。API 协调器不导入真实 Qwen 驻留控制模块；其 `start_residents`、`ready_residents`、`stop_residents` 均为空操作。

运行器保留原 3000 个 API 槽位及六个 500 任务分母，读取已封存的统一恢复库存。库存应合并 v064 原结果、R3 真实结果和 v067 API 结果；原 provider 暂停产生的未开始占位记录不能误作新实验结果。当前允许集合必须恰好等于原 API 全集减去库存中已保留的 generation 身份，加上库存明确列出的零生成重试集合；本轮预定重试集合为空。

已消费 actor 身份即使没有 API 请求也不重用。新 runtime 在启动前只检查当前允许集合；原先有调用但已退出允许集合的槽位不再使整个初始化错误失败。允许集合内一旦存在任何旧请求或已消费 actor 文件，初始化即拒绝。新 runtime 继承已冻结 v067 的线协议、schema 检查、canonical 使用量验证、传输取消和单槽 broker 去重，仅替换恢复授权、当前库存与新的 identity 文件路径。原 `full-verified-r1/api-budget/ledger.sqlite3` 仍是唯一金额账本，原总额 1500 元、provider 并发上限、模型参数、tokenizer 和两次已完成中性资格请求保持不变。

## 动态并发与实际资源

控制文件为 `api-coordinator/concurrency-control.json`，格式为 `{"desired": 32}`。缺少文件时期望上限默认为 32；只接受 1–64 的整数。文件可用原子替换更新。降低配置只阻止后续补入，不取消在途任务；无效或暂时不可读的控制文件暂停新准入，并保留已有任务。

每 3 秒读取共享池的实际 active 预约。CPU 使用量按原 allocator 的固定主协调器 4 核，加上所有 active 预约计算；内存同样按固定 16 GiB 加全部 active 预约计算。模型、Qwen actor、API actor、评分器和 API 辅助协调器均进入同一总账，不增加 152 CPU / 832 GiB 上界。

新增 API actor 可用数取以下限制的最小非负值：

- 原 12 个 actor 槽的剩余数；
- 总 CPU 剩余量除以每对 6 CPU；
- 总预约内存剩余量除以每对 32 GiB；
- 物理可用内存扣除原 128 GiB 保留量后可容纳的对数；
- 物理可用磁盘扣除原 128 GiB 保留量和已有 spool 预约后，可新增每对 4 GiB spool 的数目。

此外仍调用冻结 episode 的物理准入函数：1 分钟负载小于 140、可用内存达到其原 224 GiB 门槛、磁盘至少 256 GiB。该 224 GiB 门槛包含 128 GiB 保留量、两对 generation 与两个 grader，不是将 128 GiB 保留量改为别的值。物理门不通过时仅允许已有 API actor 继续完成，不补入新任务。最终 generation ceiling 为期望上限与“已有 API actor 加可新增数”的较小值。当前合法环境槽仍为 12，冻结 generation executor 也仍为 12，因此期望 32 或 64 均不绕过本地 12 路及共享 CPU/RAM 门槛；最终创建仍由共享 allocator 在原锁内重新裁定。

进度独立列出期望上限（默认 32）、内部账本远端请求 cap（64）、`environment_lane_limit`（当前 12）、资源允许上限、最终有效上限、API/Qwen 实际 active actor、实际 generation future 数、模型/评分/辅助预约数及账本 API inflight 请求数。`additional_slots_by_constraint`、`capacity_limiting_constraints` 和单独的 CPU/RAM generation ceiling 说明实际限制来源。`capacity_observed_unix` 标明资源快照时间；期望 32 不表示已经有 32 个模型请求。内部账本 cap 也不冒称供应商账户的官方并发上限。

同时按两次 `/proc/stat` 主机聚合计数的差值记录 CPU busy 百分比与采样间隔。首个样本保持 `null`；user/nice/system/irq/softirq/steal 计为 busy，idle/iowait 不计入 busy，guest 不重复计数。这是主机整体利用率而非本项目单独利用率；CPU 利用率仅用于诊断，本次不替代原 load<140 的准入门。

## 30 路的当前硬资源瓶颈

每个完整 generation pair 预约 6 CPU 和 32 GiB（actor/controller 仍各为原 16 GiB）。30 对仅 episode 自身就需要 180 CPU 和 960 GiB，分别超过项目所有队列合计的 152 CPU 与 832 GiB 硬上限，尚未计入两个 coordinator、Qwen resident 和 graders。故当前 profile 无法通过只提高期望数实现真实 30 路。

即使暂不计任何模型和 graders，仅保留两个 coordinator 的 8 CPU / 32 GiB，CPU 余额最多容纳 24 对，内存余额最多容纳 25 对；真实工作还要扣除模型和评分预约，且当前先受原 12 个环境槽约束。后续如需 30+，必须单独设计并验证受限的本地资源 profile、合法 lane/CPU 布局和执行器资源范围。观察 actor 闲置内存或考虑按需测试可以作为后续实验方向，不能替代工作集测量和并发压力控制；本轮没有减少 controller 的 16 GiB 限额。

## 正常等待、评分与停止作用域

冻结 `execute_queue` 仍承担异步生成和评分。新 callback 在没有在途 API generation 且资源或资格未齐备时等待外部进度，同时持续写自身 progress；这避免把正常容量不足误报成 `missing_environment_qualification`。即使第一次准入仍在等待，也先写自己的初始 cursor。环境资格继续通过浅复制后仍存活的 `LiveQualification` 值对象只读更新；API 队列不重跑 controls。

评分接入 `software_benchmark_grading_recovery_v068`，其修复范围与物理清理证明另行记录。API 队列自身预算停止只作用于自己的 provider；资源等待不会遮蔽已经观察到的预算停止。主恢复队列报告真正 shared safety failure 时，API 队列停止自己的补入并保留未开始库存。用户停止处于准入等待的 API 协调器也会保留其取消原因，不误报完整完成。

普通已经证明清理完成的单槽 `technical_unknown` 不影响其他原槽。任何没有可信清理结果的异常仍按冻结循环的安全规则停止该 API 协调器。其 finally 只释放自己占用的辅助 coordinator 预约，不停止或释放任何 Qwen 模型。

## 已完成的 CPU 控制

最初 API 恢复实现的完整 9 项控制结果：

```text
.venv/bin/python -m pytest -q tests/test_api_continuation_v068.py
9 passed in 0.41s
.venv/bin/python -m ruff check tools/run_api_continuation_v068.py src/proworksim/software_benchmark_deepseek_runtime_v068.py tests/test_api_continuation_v068.py
All checks passed!
```

控制包含：真实预约算术扣除各角色；动态调整和非法配置只 drain；容量及环境资格同时等待后恢复；CPU fixture 的实际 generation 并行数超过 4 且不超过 12；资源不足时 API 现金停止仍收口；旧请求不在当前允许集合时不会错误阻断；当前允许集合遇到旧 request 或 consumed actor 必须拒绝；新授权与 identity 不修改冻结 v067 globals；已消费零请求 actor 不重放；局部 technical unknown 后其他原槽继续；有资格且有容量时真正 shared safety failure 仍阻止新 actor。

随后将 desired 改为 1–64、默认 32，并补充容量原因与 CPU 利用率诊断。仅复查受此变动影响的控制，不重复其余 6 项：

```text
.venv/bin/python -m pytest -q tests/test_api_continuation_v068.py -k 'capacity_counts or control_changes or capacity_and_live'
3 passed, 6 deselected in 0.30s
.venv/bin/python -m ruff check tools/run_api_continuation_v068.py tests/test_api_continuation_v068.py
All checks passed!
```

补充断言确认：默认期望 32 而实际资源 ceiling 仍为 12；desired=1 和 64 均合法，65 被拒绝新准入；共享 CPU/RAM 与环境槽原因分别报告；两次合成 CPU 计数得到 11% busy，此数是 fixture 验证结果，不是实时服务器测量。

这些测试仅使用临时 JSON、内存中的计划及模拟调度任务，没有启动 API 请求、Docker、模型、GPU、systemd 或新的真实资源。早期一轮静态检查发现测试文件有一个未使用 import，删除后复查通过。运行时真实性能、最终完成率及容量等待时长尚未由这些控制测量。

## 两个普通用户协调器的启动器

`tools/launch_recovery_v068.py --prepare` 只生成两个 coordinator-unit.json 与可审阅的命令，不要求新授权已经存在，也不访问 systemd/user bus。`--commands` 只读取并校验已有规格。root 准备授权时应绑定两份规格引用及启动器、对应 entrypoint 源码。只有 `--launch` 才检查已批准的恢复授权并调用用户服务管理器。

主队列使用现有 inactive 的 `proworksim-v066-continuation.service`，原 coordinator 的四 CPU affinity、4 CPU/16 GiB/0 swap/512 tasks、Restart=no、KillMode=mixed、TimeoutStopSec=420 不变；入口为 `run_full_benchmark_v068.py --execute`。API 使用独立的 `proworksim-v068-api-continuation.service` 与原 host pool 的 164:168 四 CPU，其他限额相同，入口为 `run_api_continuation_v068.py --execute`。两者均通过 `.venv/bin/python -B tools/run_offline_scorer_v058.py` 引导项目私有 Python 运行时，命令中不携带 key。启动管理器环境沿用已有的最小 HOME/USER/LOGNAME 和固定 PATH、普通用户总线变量白名单，不复制进程中任意 API key 环境变量。

默认 `--launch --role all` 先启动 primary，等待其写出 starting/running cursor，至多 45 秒；cursor 尚未出现则保留主队列运行并返回 API 尚未尝试启动，后续可用 `--launch --role api` 单独继续。也可先 `--role primary`，优先恢复本地队列。启动前只核验指定 unit 为 inactive、MainPID=0；活动中的 unit 不会被停止、替换、重启或 reset-failed。

API 启动前在共享 allocator 中预约自身 4 CPU/16 GiB，进入实际 API cgroup 后再次预约时复用相同 claim。API 启动失败或超时不能推断 unit 没有创建，因此保留该预约和 launch-intent，等待其精确状态核验；不自动释放未知资源，也不回滚已经启动的 primary。记录中只写命令、规格、授权引用和 systemd-run 返回信息，不写 API key。

新增的启动器 CPU 控制只使用临时目录和 subprocess fixture：准备无 user bus 操作、两个命令的精确资源/entrypoint/用户边界、活动 primary 拒绝、primary 先启动而 API 超时时预约保留。结果为 `3 passed in 0.12s`，两文件 Ruff 通过。没有在这组控制中实际 prepare 真实运行目录、启动或停止任何服务。

## 启动前补充：为本地 Qwen 保留环境槽

只要 primary cursor 仍有待开始或在途 Qwen generation、且没有 shared failure，API 的 lane 计算为本地保留至少 2 个 actor 槽。实际 Qwen actor 数已经达到 2 或更多时按实际数量扣减，不额外再扣 2。因此仅看环境槽时，API 在 Qwen 尚未入场时最多 10 路，Qwen 实际 2 路时仍最多 10 路，Qwen 实际 4 路时最多 8 路；Qwen 已无待开始及在途 generation 后解除预留，最高回到原 12 槽。CPU/RAM 总账不变，不取消或抢占任何在途 API。

进度保存 `qwen_lane_reservation`、`qwen_additional_reserved_lanes` 及 `primary_qwen_lane_reservation` 限制原因。新增单项公平性控制及直接受影响的资源算术控制结果为 `2 passed, 8 deselected in 0.14s`；runner/test Ruff 通过。此后运行源已交付冻结，本文中的只读资源审计不改变该运行版本。
