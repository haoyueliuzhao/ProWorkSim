# v050 r5 有限控制、独立审查与部署准入

记录日期：2026-10-16。本文件记录模型启动前的修复证据；实际后台进度以新运行根的 `supervisor.json`、各 worker 原件及部署回执为准，不把 CPU 模拟写成真实 GPU 恢复结果。

## 修复与授权

用户已明确要求修复自动恢复覆盖不足或由此造成的整个任务池阻塞。新源码独立于仍在运行的 r4 Q+，只接续原 Q− 尚未进入模型的计算和原16开发槽。完整边界、预算和成本口径见[本轮协议](software-learning-v050-resume-r5-protocol.md)。

旧 Q− 的首次 CUDA 显存查询在真正模型 loader 前 OOM。旧监督器按 execution_fault 暂停未开库存，记录保持不变。新路径在重材料检查前先取得 CUDA 缓存，仅在来源、启动命令、PID/start_ticks、明确 CUDA 容量错误和零模型原件同时成立时归档并重排。出现 model-load-intent 或任何模型计算证据便禁止资源自动重试；其他就绪任务不等待该资源失败 worker 的退避。

## 必要验证与原始失败

最终三个新增测试文件共49项不同 CPU 控制全部通过，0.56秒；全仓 `ruff check src tests scripts` 通过。此前资源子集16项与宿主首轮20项通过；最终49项包含这些子集，累计85次控制执行、49项不同控制、pytest失败0次，不能混用累计执行与不同案例口径。未重跑历史模型资格、旧112输入核验或全仓 pytest。

测试覆盖首次 CUDA 查询 OOM、分配失败后不再调用 CUDA、严格错误分类、资源缓存同进程接用、模型意图/实际目录/计算证据禁止重试、进程身份不明禁止重试、完整原件归档和只计一次的启动费用、逐 worker 退避与其他候选并行推进、外部 Q+ 终态来源及原135481秒预算保持。CPU 调度模拟包含一次资源失败后换卡，以及同轮独立开发候选继续派发；这仍是模拟证据。

首轮 Ruff 报一个测试文件未使用的 `copy` import，删除该 import 后最终通过；原日志保留。工具沙箱数次在执行命令前报 `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`，改用经自动审批的执行通道继续读取/封存，不是模型或测试失败。一次只读状态摘要引用不存在的 `last_observed_at` 键而失败，随后改读实际文件更新时间；未修改实验状态。

[机器控制封存](software-learning-v050-resume-r5-cpu-controls.json)绑定原 r4 plan、旧失败原件证明、最终源码 SHA、协议和全部日志。原失败的 sealed boundary 为 `87a64236b5a635e10c5ceff15b29c10512efd2afcc7538e0f4aa34060c6d3e65`；12.528383493423462秒资源启动费用只保留一次，模型调用、反向、参数更新和训练区间消费均为0。

独立只读审查核对四个生产文件及上述边界，结论通过、无阻塞发现；没有重复测试、读取 checkpoint、查询 GPU 或改变任何运行进程。原始日志及审查回执位于[证据目录](software-learning-v050-resume-r5-evidence/)。

## 部署规则与可观察状态

先提交推送本轮隔离分支，再从同一干净 HEAD 准备新运行根 `runs/software-learning-v050-resume-r5` 并启动监督器。r4的源码、HEAD、Q+ PID2111917和原监督器PID2183667不动。r5仅观察其完成凭据，原Q+完成后从原库存释放对应八个开发候选。

新状态单列 `dispatch_status`、`ready_worker_count`、`monitoring_active_workers`、`resource_backoff_workers` 和 `last_resource_sample_at`。应区别等待足够显存、资源重排退避、模型计算进行中与完整性暂停，不能仅用顶层 `running` 宣称派发正常。

资源门仍为GPU0—7、装载前至少46080MiB空闲、目标 `min(73728, free−1024)` MiB且最低45056MiB；保留已授权的取消人为并发上限/60秒稳定等待/共享6144MiB终止/自身56GiB限额。模型数值路径、科学预算和原队列暂停范围均保持。没有新增样本、训练材料、方向或新模型资格；部署本身不构成科学实验已完成。
