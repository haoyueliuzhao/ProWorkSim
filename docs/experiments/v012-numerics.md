# v0.12：FP32 SDPA 数值与显存诊断

现有证据支持把 `sdpa_explicit_kv` 作为后续独立冻结的工程候选：显式展开 KV 后，所测 efficient attention 可用；3 条固定历史响应在完整模型上的概率核验均通过预声明门槛，按规则选择 `high`。这不代表新的 rollout 成功、训练收益或自回归加速实测。逐项结果及 35 个原始文件引用摘要见 [数值归档](v012-idvtdo-numerics.json)。归档工作未重跑 GPU、API 或模型。

## 旧 GPU4 问题与派发依据

旧服务为 Qwen2.5-7B-Instruct，FP32、`sdpa`、单请求，Torch 2.6.0+cu124 / Transformers 4.57.6。10 个原始 OOM 返回均报告本进程约 **74.87 GiB**、设备仅余 **4.38 GiB**；当时 GPU4 上匹配旧服务 PID 的进程快照为 76,670 MiB。因此旧问题主要来自本进程的计算和分配峰值，不能仅归因于其他项目竞争。

源码推导是：所装 Transformers 在符合条件的 CUDA、无显式 mask 路径上选择 `enable_gqa=True`，Qwen 使用 28 个 query heads 和 4 个 KV heads。该环境的 FP32 Flash kernel 不可用，efficient dense kernel 又不接受这里未展开的不同头数。独立小尺寸探针以长度 64、128 实际捕获默认路径的 `aten::_scaled_dot_product_attention_math`，且与强制 math 输出完全一致；显式把 KV 重复到 28 头后，捕获 `aten::_scaled_dot_product_efficient_attention`，相对 math 的最大输出绝对差分别约 `3.10e-6`、`2.98e-6`。

这是**源码推导加小尺寸 profiler 实证**，没有把每个旧长上下文 OOM 都完整 profile。`B×H×N×N×4` 在 N=12k、14k、16k 时分别对应一个 FP32 scores 张量约 15.02、20.44、26.70 GiB；这些是尺寸推算，不是总峰值实测。小探针不加载模型，实际进程显存快照最高 562 MiB。

## 加载失败是另一类资源事件

首次完整模型探针被安排在物理 GPU5，权重加载期间 OOM：原日志明确记录另一进程占用 **60.47 GiB**，本探针占用 **18.63 GiB**。原操作记录将其归因于启动期间竞争分配突增。异常中的 “GPU 0” 是 CUDA 可见逻辑编号，对应此次物理 GPU5。

该次执行没有数值检查、生成或优化步骤，不能算作概率不一致。随后 GPU0 的独立探针按保存协议先预留 34 GiB，再加载权重并复用本进程 allocator cache；没有控制其他进程。这个加载竞争案例与旧 GPU4 的自身高峰值须分别报告。

## 三条历史响应的完整模型核验

按保存顺序前两条，以及最长的已成功保存输入选择固定记录，不按 reward 筛选。输入/输出长度分别是 5252/30、5483/45、13711/94 tokens。使用原始 token IDs 和当时采样分数，完整模型 teacher forcing 设置 `use_cache=False`，对所有既定输出 token 计算温度 0.3 下的 log-probability；没有重新分词、重新采样或更新参数。旧记录实际 `top_p=1`、`top_k=0`。

原定逐 token 门槛为最大绝对差 ≤0.02 nat、平均绝对差 ≤0.002 nat；两个模式均须各自通过全部三条。选择规则优先 `high`，未根据结果调整门槛。

| 模式 | 输入/输出 tokens | 最大绝对差 / nat | 平均绝对差 / nat | allocated 峰值 / GiB | 单次前向 / 秒 |
|---|---:|---:|---:|---:|---:|
| highest | 5252 / 30 | 0.000002673 | 0.000000097 | 29.784 | 4.653 |
| highest | 5483 / 45 | 0.000076294 | 0.000004341 | 29.849 | 4.184 |
| highest | 13711 / 94 | 0.000007822 | 0.000000083 | 32.052 | 11.125 |
| high | 5252 / 30 | 0.000639953 | 0.000021705 | 29.784 | 0.856 |
| high | 5483 / 45 | 0.009119719 | 0.000448126 | 29.849 | 0.910 |
| high | 13711 / 94 | 0.000152779 | 0.000001625 | 32.052 | 3.062 |

第二条 `high` 的**序列 log-probability 差之和为 −0.020154219 nat**，原值保留。门槛针对逐 token 最大值和均值，不是序列和。`high` 在记录中使 CUDA matmul 的 TF32 标志为 true；模型权重仍是 FP32。该工程候选仅在 attention 调用内展开 KV，显式要求 efficient kernel，并注册既有 SDPA mask 语义，不静默回退至 math、CPU 或其他权重精度。

表中显存是重置峰值计数后测得的 `torch.cuda.max_memory_allocated`，包括已加载模型但不包括 allocator reserved 显存；它与旧 OOM 的整进程 74.87 GiB 不是同一口径，不能直接计算峰值下降比例。耗时为共享 GPU 上每项一次 teacher-forcing 前向，先测 `highest` 再测 `high`，没有均衡重复计时或实际 KV-cache 自回归对照。

两项探针均保存 dirty `09e45d9` 开发源码身份，各自起止摘要一致；不能重新标成先前 clean D1 的运行配置。此处只归档已保存的旧服务与探针证据，没有读取新服务启动或 rollout 结果。选择 `high` 仅表示这三条历史记录通过数值候选准入，不覆盖全部 32k 上下文，不增加有效工作轨迹或训练支持。
