# v093：完整运行计划与两条件启动健康门

v092 的44项均因缺少 `host_cpu_pool` 在 `DockerClient` 构造前失败。44项原 actor 容量 claim 已消费并释放，模型调用和 API 账本请求均为0；原件、费用及失败状态保留。本轮使用新物理索引6044–6087，逻辑 `slot_id`、任务、seed、5M预算和授权的44个模型尝试不变，新增模型尝试数为0。

**实际运行结果更新：v093 首2项6044／6045已创建环境，但没有开始模型调用。** 原模型FIFO服务函数内部仍局部导入旧v066 guard，拒绝恢复任务身份，两个模型线程均在ready之前失败。此前CPU控制只执行到Docker构造前及独立broker授权，没有覆盖实际线程目标，因此没有发现这个遗漏。健康门未通过并停止后续派发，其余42项6046–6087未消费；首2项原件保留为技术未知，不能写成模型失败。

本轮真实创建了4个容器和2个任务卷，已全部清理、无保留或不明创建；manager及parent093已释放。必须保留这项环境成本，不能沿用v092的“0 Docker创建”。44项逻辑恢复模型的API请求仍为0。后续独立v094仅为这2项使用新物理6088／6089，并继续原42个未消费物理身份；拟通过实际FIFO计数、生成及计费持久化控制后再上线。

## 修复

- 新计划继承原v066完整结构，包括原固定CPU库存引用，再限定44项 rows、环境及资源，重算计数、范围与 continuation inventory。原 matrix／configurations 保留作来源，`active-configurations.json`绑定新44个实际配置；不以来源索引授予原6000项资源。
- 预算 runtime 保持原v089 canonical registry。外层严格验证新物理row／配置后映射回原canonical row，继续使用原 API 请求身份、反重放、实际token与1700元唯一账本。旧已消费物理身份不复用。
- 初始最多派发预选REF、PROJECT各1项。只有两项分别出现至少1条真实 `settled`、有费用的 API 请求记录，才开放48的调度上限；不看测试或评分。若初始项结束仍无该证据，停止未开始库存，防止共同启动错误再次消耗全部44个物理身份。48是上限，实际并发另报。
- 使用独立普通用户manager和已批准的parent093生命周期；原推理配置、工具、控制器输入和官方评分保持，Qwen不启动。

## 必要验证与边界

完整计划、原固定CPU读取、物理→canonical映射，以及两项启动门的成功／失败路径共4项CPU控制通过。实际执行了真实账本的付费请求SQL和真实Admission事件顺序检查；未调用API。

启动路径控制使用真实新scope／policy和 `run_episode`：REF、PROJECT各1项实际经过配置、临时容量claim、bundle、公开上下文和原 `host_cpu_pool`，抵达DockerClient构造前的显式哨兵；随后独立验证真实controller输入、原validator、完整API初始化与两组broker授权。临时账本和模拟资源仅用于CPU控制，不创建真实Docker对象或访问网络。最终记录见 [启动路径控制](../../artifacts/software-benchmark-v093/episode-startup-control-r1/summary.json)；封存必须等待该文件的完整控制完成标记。

CPU检查没有实测容器内隔离、FIFO和远端模型响应，不能称整个真实评测已经通过。真正放行依据是上线后两条件的真实付费请求健康门；后续完成率、用量及评分仍由正式运行记录给出。旧44项零调用部署失败不混为新的模型结果。

证据：[原44项零模型与资源审计](../../artifacts/software-benchmark-v093/zero-generation-physical-handoff-r1/summary.json)。运行目录：`runs/software-benchmark-v093/physical-startup-recovery-r1/api-coordinator/`。
