# GPU0/1/2/4 历史启动失败窄审计（2026-10-23）

决定：维持当前四个MP resident、全局八回合运行。此项只查阅四份历史启动记录和现有调度代码，复制小凭据；没有新的GPU查询、CUDA诊断、模型加载、测试、队列／pool状态修改或旧失败清理。

## 历史失败与证据边界

四卡均在2026-10-22 10:16（北京时间）的一次启动中，进入 `cuda_capacity_snapshot` 后失败：

| GPU | 原CUDA错误 | 当时普通空闲显存 MiB | 原启动缓存目标 MiB |
| --- | --- | ---: | ---: |
| 0 | No CUDA GPUs are available | 50528 | 49504 |
| 1 | CUDA-capable device(s) is/are busy or unavailable | 50543 | 49519 |
| 2 | No CUDA GPUs are available | 50751 | 49727 |
| 4 | No CUDA GPUs are available | 81152 | 73728 |

四份 `startup-resource-receipt.json` 均明确：`loader_not_entered=true`、`new_model_calls=0`、`allocation_attempts=0`、`status=fault`、`retryable=false`。现场没有resident ready／模型identity／handoff结果，owner-service仅有startup；原pool记录正式claim为0，未注册为可派发resident。源码 `software_benchmark_owner_ipc_v054.py:338` 将startup guard放在 `load_actor` 之前，与这些实际回执一致。因此可确认四次均未进入模型加载器、没有资格生成或正式模型调用，不是结果未知的生成回合。

这里的“未进入loader”不等于“没有启动尝试”：`launcher-started.json` 已存在，原provisioner依据它将 `model_load_attempted` 设为true。原policy固定 `maximum_actual_load_attempts_per_gpu=1`、`automatic_retry_after_load_failure=false`；四卡原启动尝试额度已消耗，不能直接清failed或伪装成尚未开始的resource_wait。

本次没有确证CUDA不可用的更深层原因。**GPU4失败时已经有81152 MiB空闲**，因此后来同样空闲不能证明故障已解决，也不能以显存容量满足为由盲目重新加载。

## 原预算与并发限制

每卡资格permit仍有未使用的6请求／61440输入加输出token上限，四卡合计24请求／245760 token。permit绑定原部署身份且禁止自动重试；这些未使用token额度不会取消上述一次启动政策。如果将来决定诊断与恢复，必须独立记录零模型故障、必要的新CUDA入口证据和有限恢复版本，保留旧失败、原身份及已消费尝试。当前未启动这项后续工作。

全局生成8是**硬上限**：

- `v054-formal-authorization-r3-interleaved.json` 和 `v054-formal-execution-plan-r4-interleaved.json` 都固定8，authorization的 `global_episode_limit` 也为8。
- `software_benchmark_queue_v054.py:99` 起的 `check_plan` 硬校验这三个值。
- 当前r6继承的派发路径在 `run_qwen_resource_recovery_v054_r1.py:221` 将计划上限传入 `select_pool_slot`；后者在活动数达到上限时直接停止新增派发。

因此增加resident不会自动变成16回合并发。原selector优先选择占用较少的resident，再按GPU index排序；更多合格GPU有可能将**同8个回合**分散到更多物理卡，减少同卡FIFO争用。但收益未经测量，受推理／公开CPU测试比例影响，不保证提速。新加载还会占用CPU、RAM、磁盘读取及最高72 GiB/卡的原启动缓存目标。当前没有为此干预八个在途回合。

## 小凭据

`artifacts/software-benchmark-v054/failed-extra-gpu-static-audit-20261023/` 保存四卡既有startup receipt、permit、launcher-started/status、stderr，以及原pool policy、正式authorization和execution plan，共23份原件、111603字节。`audit.json`记录审计结论和代码位置，`evidence-index.json`记录来源路径、大小与SHA。没有扫描权重／rootfs或执行新测试，原失败和运行状态保持。
