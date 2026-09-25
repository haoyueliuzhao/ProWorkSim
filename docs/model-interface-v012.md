# v0.12 模型工作接口开发合同（D0）

v0.11 的终止式协议及全部失败记录保留。v0.12 新增可显式选择的格式反馈续行协议，并冻结推理精度、注意力实现和本地提示投影的身份。这些是运行协议 Γ 的改动，不是训练或 ID-VTDO 调权收益。本文件描述实现与离线机制验证；实际模型结果须另按冻结批次报告。

## 1. 一次失败决策与一次真实世界动作分开

`ModelPolicy` 配置增加：

```json
{
  "action_protocol": "single_decision_json",
  "context_policy": "latest_observation",
  "format_error_policy": "format_feedback_continue",
  "format_limits": {"max_total": 4, "max_consecutive": 2}
}
```

默认 `format_error_policy="stop"` 仍在首个格式失败后终止。只有显式的 `format_feedback_continue` 启用新行为，两种动作协议（原生工具、单 JSON）均支持。累计和连续上限均为正整数；**达到任一上限的那次失败即停止**，例如连续上限 2 允许第一次错误后得到一次新的角色机会，第二次连续错误终止。一个格式正确的决定重置连续计数，不重置累计计数；真正的工具拒绝不算包装格式错误。

模型输出必须整体通过原有格式校验。多工具调用、坏 JSON、重复键、错误包装、输出长度截断等，均不取其中一部分执行，也不把 `kind=adopt` 自动改成 `kind=act`。实际响应和所有已发生的 HTTP attempt 原样记录。每次错误消耗一次模型决策及其实际 attempt/token/费用预算；续行仍受同一固定的模型与场景机会预算约束。没有本次 `decide()` 内的重采样。

可续行失败追加一条公开 `public_format_feedback` 用户消息，只含格式错误、当前协议、语法合同、计数和上限；不含隐藏正确数值、应选择的业务来源或下一步动作。策略返回 `protocol_rejection`，运行器记录 `model_format_feedback`、`decision_consumed=true`、`action_performed=false`。这不是世界工具调用，不前移世界时钟，不生成世界工具结果。角色轮转照常推进，模型只能在自己的下一次机会观察并决定；此状态不会被一次完整 idle sweep 误认为所有成员均在等待。

服务失败、未知用量、预算用尽、坏响应 envelope、缺失真实 assistant，以及 pending tool 与实际返回身份不匹配，不借此变成可重试的普通模型输出错误。它们继续使用已声明的终止边界。默认终止协议与可续行协议必须分别记入配置身份，checkpoint 不允许悄然换协议。

## 2. 原生工具错误历史的显式输入投影

原生响应如果携带多个调用或坏调用结构，既不能执行部分调用，也不能伪造 `role=tool` 的“执行结果”。直接把悬空 `tool_calls` 放回下一请求，还可能使 API 拒绝整个对话。

新协议保留 memory 中完整原 assistant 消息，同时登记其索引和 SHA256。仅在之后 HTTP 输入中，将这类**已经拒绝**的 assistant 消息投影为普通 assistant 文本：内容是包含完整原消息的 `rejected_assistant_response` JSON。这是一种公开记录的历史呈现，不是修改原始模型输出，也不是将其转换成正确世界动作。普通坏 JSON 文本无需这种投影，保持原文。

`context_selection` 对每条历史消息同时保存原索引、原 SHA256、是否进入请求、实际 wire SHA256 和 `projection`（`unchanged` 或 `rejected_assistant_as_data`）。请求体与服务实际 input token 仍另行保存。训练原错误决定时使用其当时实际 output IDs；未来决定的 input 使用其当时真正收到的投影后的 prompt IDs，不能用归档原文猜测当前输入。

## 3. 完整档案与模型当前上下文分开

已有 `full_history` 与 `latest_observation` 保持为明确配置。后者只移除此前已登记的公开观察消息；最新公开观察、角色任务、当前完整工具定义、所有真实 assistant 输出、工具返回和格式反馈仍按规则进入请求。完整历史留在 memory，原观察索引及移除理由留痕，不通过内容关键词猜测哪些消息“像观察”，不暗中摘要或裁剪输出。

D0 成组比较必须冻结上下文策略、输出上限与格式上限，并同时报告实际决策数、模型输入 token、保守预算预留和最终边界。名义允许 120 次决策不保证实际发生 120 次调用；`max_output_tokens=8192` 也不是唯一可用配置。若开发选择更小的输出上限，应在采样前声明，不能对产生截断的失败临时补发更大额度。

## 4. 本地服务的可冻结计算与提示配置

本地服务新增三个选项，默认保持 v0.11 的原选择：

```text
--dtype bfloat16|float32                 默认 bfloat16
--attention sdpa|eager                 默认 sdpa
--native-tool-prompt template_default|single_call
                                      默认 template_default
```

既有 `--max-batch` 继续显式记录，必须为正数。未来稳定概率复算可以在新批次预先选择 `float32`、单 batch；本修改没有执行 GPU，也没有声称该选择已经通过多轮 PPO 概率核验。

`single_call` 仅在请求实际包含原生工具定义时追加固定的公开语法提示，要求每个决定一个 `<tool_call>`、保留控制操作、不得发明工具结果。单 JSON 请求不受影响。服务保存原 HTTP request、实际归一化后的 prompt messages、实际 rendered prompt 及逐层摘要，故额外提示不会成为未记录的隐藏条件。

服务 manifest 和每次真实响应同时给出 `inference_profile` 与其 SHA256，含声明/实际 dtype、声明/实际 attention、提示选择、max batch、context limit 和 seed。`token_trace` 继续来自实际生成 IDs、实际采样 logits、温度、top-p/top-k；保留 EOS、完整输出、原 batch group/row/prefix width，不从文本重建。权重/adapter 身份与推理协议身份分别记录，不能只以模型别名判断两次行为分布相同。

## 5. 当前离线核验与实际实验边界

离线测试使用明确的模拟模型响应与真实 WorldCore 公开端口。验证覆盖：失败计费且无世界动作、下一机会与 checkpoint 续行、累计/连续双限、模型预算优先停止、格式正确但业务错误的真实拒绝、全部原生调用整体拒绝与可重建 wire 投影、输出截断、真实场景 idle sweep、私有角色材料隔离，以及本地推理选项和提示来源。旧模型接口/上下文/运行器/服务相关 54 项通过，新 D0 与服务配置 20 项通过；这是机制证据，不是模型工作成功率。

后续 D0 应在相同起点、模型与业务要求下，按预先固定的顺序随机化协议配置，保留所有格式、预算和业务失败。先检查多个实例上能否重复形成合法完整交付，再固定 Γ 采联合支持材料；不能边调提示边把成功池当作当前团队支持。公开来源/交付结构预检由世界接口另行提供，模型适配器不导入评价器，也不替工作人员补采用或依赖。

D3 将另建完整多轮、成员归属明确的训练材料和基础 PPO 合同，不继续训练 v0.11 的三条零奖励首决策。格式失败的自身生成 token 是真实动作记录；同事消息、工具返回、先前输出作为后来 prompt 的部分，均不成为当前输出目标。奖励可训练性、有效工作 V、可靠 Mapper 与可重配支持资格继续分开。

## 6. D0/D1 初始冻结之后：显式 efficient attention 候选

这一节属于新候选 `local-inference-profile-v0.12.1`，不回写原 D0 或初始 D1 的 Γ、失败和 token 概率。新服务启动命令可明确选择：

```text
--dtype float32 --attention sdpa_explicit_kv --max-batch 1
--matmul-precision highest --native-tool-prompt single_call
```

`--matmul-precision` 只允许 `highest` 或 `high`，默认 `highest`。profile 同时保存声明值、`torch.get_float32_matmul_precision()`、CUDA matmul 的实际 `allow_tf32`、cuDNN 的实际 `allow_tf32` 和 `NVIDIA_TF32_OVERRIDE`。`high` 是另一个明确的数值配置，不能当作与 `highest` 位级相同；这组字段进入服务与每次响应的 profile SHA256。已有服务进程不热修改，新源仅供另一次冻结和启动。

**发现的计算路径问题。**安装环境是 PyTorch 2.6.0+cu124 / Transformers 4.57.6。Qwen2.5-7B 是 28 个 query heads、4 个 KV heads。HF 对无 padding 的单批 prefill 省略显式 attention mask，使用 `is_causal`；其 SDPA 适配器在该条件下传 `enable_gqa=True`。PyTorch 2.6 的 GQA 仅支持 Flash/math；同版 CUDA 选择器的 Flash/cuDNN 分支要求 FP16/BF16，而允许 FP32 的 memory-efficient 分支不接收这种头数不一致的原生 GQA。因此该 FP32 组合会走 math attention。[PyTorch 2.6 SDPA 文档](https://docs.pytorch.org/docs/2.6/generated/torch.nn.functional.scaled_dot_product_attention.html)、[2.6 CUDA 后端选择源码](https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/transformers/cuda/sdp_utils.cpp)。

这使长 prefill 的注意力中间量按 N² 增长。仅一个 `B=1,H=28,N,N` FP32 张量，在 N=12000 时就是 15.02 GiB；这是尺寸公式，不是实际模型总峰值预测，也不能乘以层数冒充同时存活量。原错误记录中本进程张量 allocated 约 67.12 GiB，另有约 7.26 GiB reserved-but-unallocated，不能都归因其他共享作业或未用缓存。PyTorch 说明 `empty_cache()` 释放的是未用缓存，不能释放仍被张量占用的内存。[CUDA 内存管理说明](https://docs.pytorch.org/docs/2.6/notes/cuda.html#memory-management)。HF generate 已对支持的 Qwen forward 自动设置 `logits_to_keep=1`，此次不能先把主要峰值解释为全 prompt 的 vocabulary logits。

**独立小张量实证。**在另一个物理 GPU6 进程、固定 seed、B=1、heads=28/4、head_dim=128、FP32、L=64/128 上，没有加载模型或生成业务动作。两种长度的默认 profiler 均实际记录 `aten::_scaled_dot_product_attention_math`；强制 Flash 因 dtype 拒绝，强制原生 GQA efficient 因头数不等拒绝。显式把相同 KV 按原组关系重复后，`enable_gqa=False` 的 efficient 调用实际运行 `fmha_cutlassF_f32_aligned_64x128_rf_sm80`。相对 math 的最大绝对差分别约 3.10e-6、2.98e-6；显式重复配合 math 为零差。实际自身进程 GPU 快照最高 562 MiB、PyTorch 分配峰值约 26.63 MiB，低于声明的 1 GiB 进程上限；源码摘要起止一致。原报告、源、张量和资源记录位于 `/tmp/proworksim-v012-sdpa-microprobe/`。

小张量结果只证实存在可用、数学结构一致的计算路径，不能推出 12k 上下文性能、语言模型输出概率一致或任务成功。原正式运行没有 profiler，不把新的小张量记录倒填为旧模型运行的 kernel 测量。

**实现约束。**`sdpa_explicit_kv` 在每层 attention 调用内部将 4 组 KV 按原映射 repeat 到 28 头，再设置 `enable_gqa=False`，强制 `SDPBackend.EFFICIENT_ATTENTION`。模型 KV cache 保持原 4 头，不改变参数、不删除分组语义、不降低 dtype。注册自定义 attention 时同时复用安装版 `sdpa` mask 函数，避免自定义名称漏掉 causal/padding mask。kernel 不可用就明确失败，不回退 math、eager 或 CPU，不偷偷改精度。

对应离线检查覆盖 CLI、原 prompt 投影、原 KV 值与分组保持、causal/mask 传递、拒绝回退，以及 attention/mask 双注册和 TF32 身份；其中真实 Torch CPU 测试不加载模型、不初始化 CUDA。多轮训练入口也先注册同一 profile 并核对实际精度旗标，原 `.02/.002 nat` 概率门槛不变。

在新正式模型批次前仍须单独执行一次旧短 prompt 的真实模型开发核验，记录实际概率、backend、资源与用时，再决定是否采用新 profile。若采用，应重新冻结并采样新的本地槽；旧批已闭合、中断和未尝试槽分别保留，不能用新结果替换旧失败或混合 Γ。本文不预写该模型级核验、长上下文或新批已经通过。

## 7. 独立启动资源预留

新增资源选项 `--startup-reserve-gib`，默认 0，仅接受有限的 0–64 GiB（含边界）；NaN、无穷和越界值在 CLI 解析时拒绝。它不进入数值 `inference_profile`，不改变 attention、TF32、采样、提示或 PPO 概率门槛；启动资源单独记录在 `startup-resource.json`，完整记录及其路径/大小/SHA256纳入 service manifest。

当值大于 0 时，本进程先申请指定字节数的 CUDA 空张量，持有它完成 CPU 权重加载；然后释放张量引用到**自身 allocator 缓存**，不调用 `empty_cache()`，再将已加载权重搬到 CUDA。可选 adapter 的加载也计入启动阶段。默认 0 不申请占位张量，仍保留启动阶段事实。预留不保证后续所有计算一定有空间，也不控制、暂停或终止其他项目进程。其他进程可能看到可用显存减少，这属于已声明的共享资源使用，不能称为没有竞争。

阶段记录包含实际 allocated/reserved、峰值、设备 free/total、CUDA_VISIBLE_DEVICES、PID 和 allocator 环境变量；CPU加载或预留失败也写明实际错误并释放本进程的预留引用，绝不将启动失败伪造为一次模型响应。预留没有随机采样，不消耗模型输出序列。

启动结束后明确保存 `startup_peak_allocated_bytes` 与 `startup_peak_reserved_bytes`，再重置峰值统计。每个真实 generation group 开始前再次重置统计，响应的 `service_record.compute_resource` 分开记录实际 allocated 峰值、生成前 allocated 基线和新增峰值。reserved 总量可能仍含启动缓存，不能当作计算新增占用；同一 batch 多行共享这份测量，不能按每条响应累加。

CPU mock 验证了“先预留→持有期间CPU加载→释放到缓存→权重搬入→重置计算峰值”的调用顺序、默认零预留、预留申请/CPU加载失败、adapter计入启动以及参数边界；这些检查不分配GPU、不启动模型。主运行者记录的独立模型数值/资源核验见 `runs/id-vtdo-v12-kernel-model-probe-gpu0/report.json`，与启动预留测试和新正式采样批分别报告。
