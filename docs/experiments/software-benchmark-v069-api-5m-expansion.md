# v069：原 500 万 token API 库存交接与环境槽扩展

本次用户范围已收缩为 DeepSeek 每题 500 万 token 一档，仅保留原 REF/PROJECT 两组各 500 个逻辑任务继续执行。750 万和 1000 万两档停止新准入，已启动任务按其原身份和预算自然收尾，旧结果与费用全部保留。Qwen 原任务继续运行，不由新 API 协调器管理。本文记录实现与 CPU 控制；实际启动数、成功率和费用以运行快照为准，不宣称已达到远端 30 路。

## 库存与零重放

统一根为 `runs/software-benchmark-v069/api-5m-expansion-r1`。交接库存保留两个 500 任务分母，当前允许的新生成身份为 846 个（REF 423 / PROJECT 423），其余 154 个原 5M 槽保留在历史中。新队列执行的只有允许集合，既不为旧在途生成伪造闭合结果，也不把旧在途任务作为新 future 提交。

所有旧曾经 scheduled 的身份均排除，包括尚未获得 actor claim、仍等待容量的 future；任何已消费 actor 身份、任何已有 API request 也排除，`retry_zero_generation={}`。历史 usage 指向已复制的不可变交接快照。准入再核对原计划、原 seed/configuration、5M 条件、旧暂停确认和唯一账本，创建身份仍由同一个 `allocation.lock` 最终保护。

新 API runtime 复用冻结 v067/v068 的线协议、工具 schema、tokenizer、canonical usage 检验和单槽 broker 去重，只在私有函数命名空间替换新授权、当前允许集合和 identity 路径。模型可见内容不变；原 1500 元账本继续覆盖旧高档费用及新 5M 请求，不另开预算。两组 token 均值单独保留 500 分母，选中 5M 的使用量费用与全账本预算状态分别标明。

## 旧队列为什么需要单独排空

旧控制文件原子改为 `desired=0`，旧源码按非法配置处理，进度表现为 `configured_generation_limit=null`、`effective_generation_limit=0` 和原范围错误。该路径不设置停止事件、不取消已有 API 请求，也不回收在途 actor；已提交的 generation 继续。额外的行政暂停说明字段只作为记录，旧运行器不会将其送入模型。

这不是旧源码原生支持的完整 drain 模式：最后一个 generation 完成后，其准入 callback 会因仍有 pending 库存且上限为 0 而等待。已提交 grader 线程可以完成并释放物理资源，但完成元数据及随后产生的 delivery 评分可能尚未由主循环处理，旧 coordinator 也不会自动退出。

因此，新入口后台每 30 秒调用独立 `software_benchmark_api_drain_v069.poll(stop_event=...)`。该模块只有在旧已 scheduled 生成全部闭合、所属 claim/请求及已准备评分均安静，并确认旧 unit 的精确 ownership/PID 后，才结束旧 API coordinator 的空转准入等待；它不停止 Qwen。旧完成评分复用原 receipt，旧未消费评分每次最多继续一项，不重放已消费评分身份。

后台 drain 使用独立的生命周期停止事件，因为冻结 queue 在自然结束时也会设置自己的 stop。新生成库存结束但旧收口未完时，新 coordinator 继续等待；收到本新 coordinator 的终止信号时，两类事件一起设置，并等待后台线程清理完成后才释放自己的预约。poll 异常仅写本新队列事件，不取消正常的新生成。

## 实际容量边界

原资源池扩为 18 个合法 actor lane，新增 lane 12–17 的 CPU 映射和执行权限由新资源模块单独封存。每对 actor/controller 仍预约 6 CPU / 32 GiB，actor 4 CPU/16 GiB、controller 2 CPU/16 GiB 不变。总预算仍为 152 CPU / 832 GiB，普通 API coordinator 使用 4 CPU/16 GiB、host pool 168:172；不使用 sudo。

新队列在私有函数命名空间复用冻结调度循环，只将 generation executor 扩为最多 18 个 worker，自己的 grading executor 为 3 个；未改旧模块 globals。期望值默认 32、允许 1–64，但实际准入由下列约束共同决定：

- 当前模型、Qwen/API actor、grader、两个或三个 coordinator 的实际共享预约；
- 旧 API 已 claim actor 及尚未 claim 的 scheduled future，后者另外预留对等容量，避免两队抢同一份余量；
- 至少两个 grader 的容量余量，已存在的 grader 不重复预约；
- Qwen 仍有 pending/active 时至少四条环境 lane，已有 Qwen actor 按实际数量扣除；
- 原物理内存、磁盘和 load 门。

模型数量按实时 claim 计算，未假定固定两驻留。在四个 Qwen pair、至少两个 grader 的边界下，三模型加三个 coordinator 时理论新旧 API 合计最多约 10 对；旧 API coordinator 的 16 GiB 预约实际释放后约 11 对。已有 grader 更多、物理门不通过或旧 future 尚未入场时还会更低。18 lane 是可选身份数量，不表示 18 个 pair 必然同时获得 CPU/RAM，也不表示远端请求数。

## CPU 控制与只读对接

```text
.venv/bin/python -m pytest -q tests/test_api_expansion_v069.py
6 passed in 0.45s
.venv/bin/python -m ruff check tools/run_api_expansion_v069.py tools/launch_api_expansion_v069.py src/proworksim/software_benchmark_deepseek_runtime_v069.py tests/test_api_expansion_v069.py
All checks passed!
```

控制验证：模型增减、旧 coordinator 释放、评分余量和旧未 claim future 的容量算术；旧 desired=0 不设置取消事件；新允许集合只含原 5M 并拒绝 consumed/old-scheduled；私有 executor 的 CPU fixture 能实际超过 12 路且不修改旧 globals；后台 drain 不随 queue 自然 stop 提前退出且单次观察异常局部保留；launcher 只准备新 API unit、无新授权时仍可生成审阅规格、不接触真实管理器。

唯一实际数据对接检查为只读：1000 目标 / 846 允许、全新队列 generation state 为空、scope 路径一致、旧控制暂停已确认、当前允许集合没有旧 request/actor claim。旧 cursor 中遗留的高档在途身份已在排除集合内；旧进度的实际 generation future 已为 0，说明不能把 cursor 的历史条目直接等同实时 actor 活动。这些检查未启动或停止资源，未重跑模型或测试 episode。
