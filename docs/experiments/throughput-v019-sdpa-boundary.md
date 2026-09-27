# v0.19：FP32 GQA 后端与显式 KV 修订边界

原冻结 `b37059e585f03fc8472d2b209ceba422d8f5a3a2` 的正式 9B 探针在旧 SDPA 基线长序列反向发生显存不足，优化路径尚未执行。随后安装代码、官方后端约束和小规模 CUDA 控制共同支持一个具体机制：FP32 且 `enable_gqa=True` 时，当前组合走 Math SDPA；显式展开 KV 头并要求 efficient SDPA 能避开该路径。这个证据很强，但没有采集原 OOM 那次分配的逐张量堆栈，不能写成已经排除所有其他因素的唯一因果诊断。

## 原失败保留

原命令使用同一冻结清单的三个真实请求、`--max-output 2048 --backward-all`、GPU 0/1。launcher 实际运行 304.85 秒后 `exit_code=1`。原日志、局部 report、四个实际模型响应和资源记录均未改动。

- 首请求为 8,473 输入、173 输出 token。两次生成 36.02/36.68 秒；完整原序列概率重算最大差 `0.00016606`、均差 `0.0000020735`，通过原 max 0.02/mean 0.002 门。真实反向 57.43 秒、同一概率门通过、梯度有限且有 589,824 个非零元素；优化器更新为零。
- 第二请求两次实际生成均为 14,303 输入、437 输出 token。反向在 `(-gradlogps.mean()).backward()` 抛 `torch.OutOfMemoryError`。GPU 1 要分配 12.95 GiB，当时可用 12.85 GiB；日志报告该进程用量 66.39 GiB，其中 PyTorch 已分配 60.79 GiB、保留但未分配 5.11 GiB。不能只据这个保留量就把失败归因于碎片。
- 原 report 在反向结束后才落盘该行，因此只保存三行，而 resident ledger 已保存四次生成。第二请求热调用的数值/反向统计未成功落盘，不补造数值。第三请求及新优化 variant 尚未执行；27B 正式探针也未因这次失败而启动。
- 资源采样共 21 条。GPU 0/1 仅见此 probe，自用采样峰分别 76,810/74,576 MiB；其他项目当时在 GPU 6/7，原 27B H1 在 GPU 2–5。其他卡竞争不等于本次 OOM 卡上的同卡争用。
- 原 probe 因异常没有写最终 `source_after`。独立收口观察读取的冻结 commit、clean 状态和源码树 SHA 与原 `source_before` 相同；观察记录与缺失的实验终态字段分开保存。

收口记录为 [qwen35-9b-probe-observation.json](../../runs/throughput-v019-admission/qwen35-9b-probe-observation.json)，SHA256 `5a4b1b4abe3e2fa5356e3468b99dee6482366700355ff8b26ed69db7cd011382`。它引用原 launch、log、resources、report 和各响应的路径与 SHA。原 log SHA 为 `7c2a07618ed7553d96a23e95988c317349c8c7025b074f9cab836851c3bcc73e`，原局部 report SHA 为 `c6dbef3f5ca015ae09d11c7abcb60467cb3ceb9febbd01bf7b4740e956b5c287`。

## 后端证据

安装版本是 Torch `2.6.0+cu124`、Transformers `5.17.0`。安装的 `transformers/integrations/sdpa_attention.py` 在无显式 mask、KV head dimension 相等且不超过 256 时令 `enable_gqa=True`，而没有先展开 KV。Qwen3.5 的 full-attention 层使用该 attention registry；本轮 9B 为 16 个 query heads、4 个 KV heads、head dimension 256。

PyTorch 2.6 官方说明 GQA 的 CUDA 支持限于 Flash 和 Math 后端；不同 SDPA 后端可能产生不同浮点结果，强制后端不可用时应报错。HF 文档还说明 FP32 不适用 FlashAttention，并要求自定义 attention 名称同时注册对应 mask formatter，避免丢失 causal/padding 约束。[PyTorch 2.6 SDPA](https://docs.pytorch.org/docs/2.6/generated/torch.nn.functional.scaled_dot_product_attention.html)、[HF 5.17 AttentionInterface](https://huggingface.co/docs/transformers/v5.17.0/attention_interface)。

当前 learner 的 `selected_logprobs` 使用完整 `input_ids + output_ids`，因此失败请求的序列长度是 14,740。一个形状为 `[1,16,14740,14740]` 的 FP32 张量需要 `12.950158 GiB`，与异常文本中的 12.95 GiB 一致。这是形状和机制上的吻合，不是原失败现场的逐张量识别。

## 小规模真实 GPU 控制

微控只使用 GPU 0 上的小张量，未加载候选模型、未更新参数、未操作工作世界。启动前 GPU 0 可用约 39,997 MiB，并非空卡，因此只验证核函数选择、有限张量数值与内存行为；带 profiler 的短耗时不作为端到端加速比。

第一组以 FP32/highest、Q heads 16/KV heads 4/head dimension 256 对照安装 HF 与现有 `sdpa_explicit_kv_attention_forward`。

| 条件 | 安装 HF 的实际后端 | 显式 KV 的实际后端 | 输出最大绝对差 |
|---|---|---|---:|
| 无 mask 完整前填充，L=1024 | Math | efficient 前向及反向 | 2.74e-6 |
| 显式偏移因果 mask，Q=97/K=161 | efficient | efficient 前向及反向 | 0 |
| 单 token decode，Q=1/K=256 | Math | efficient 前向及反向 | 3.28e-7 |

L=1024 的张量控制中，采样峰增量从 336.25 MiB 变为 128.19 MiB；所有梯度差最大不超过 `1.97e-10`。保留 GQA 不展开 heads、同时只允许 efficient 后端的负控直接报 `No available kernel`，告警说明 fused kernel 要求 Q/K/V 的 heads 数相同。

第二组专门检查奇数 key 长度及前缀续算：完整前缀 Q=K=768；Q=257/K=1025 的偏移因果布尔 mask；单 token Q=1/K=1025。矩形 mask 的原始 stride 是 `[263425,263425,1025,1]`，首 query 允许 key≤768。未做额外 padding，显式 KV 在三种条件下都实际进入 efficient 前向及反向，输出和梯度均有限。对强制 Math 参考，输出最大差分别 `2.56e-6/6.71e-7/1.94e-7`，梯度最大差不超过 `8.51e-11`。这说明这些具体形状不需要为 efficient 后端补 padding，不推广成任意 mask/shape 的保证。

证据：

- [sdpa-gqa-microcontrol.json](../../runs/throughput-v019-admission/sdpa-gqa-microcontrol.json)，SHA256 `5e9f989881c34cc0c0c336d0254ec452f02163977621d97aabd71f3ef67942ef`。
- [sdpa-odd-suffix-microcontrol.json](../../runs/throughput-v019-admission/sdpa-odd-suffix-microcontrol.json)，SHA256 `6bbbf20f14cc1ce27bebb06ef5a9db61e65521d52e10b7a456cd1ad43800e85c`。

## 新执行配置与正式复验边界

修订只进入新的 candidate v0.19 执行配置。构造器复用原项目已有的 `configure_attention_runtime('sdpa_explicit_kv', 'high')`，注册 attention 与同名官方 SDPA mask，再使用模型的 `set_attn_implementation`。现有函数在单次 full-attention 调用内展开 KV，保持模型原 KV cache 的头数，且仅允许 efficient CUDA kernel；没有静默 Math、低精度或 CPU 回退。DeltaNet 层实现与 FP32 权重保持，high、显式 KV 和前缀缓存作为明示的新组合执行配置验证。

它会改变浮点计算顺序及运行成本，因此属于需要准入的新配置。原 max 0.02/mean 0.002 概率容差不变；真实完整输入/输出 token、实际生成概率、完整序列 learner 重算和真实反向仍需重新通过。小张量误差不替代全模型、长输出和多卡容量验证。更少卡数尚须单独实测，不能从密集矩阵消失直接宣布 9B 单卡或 27B 双卡已可用。

新 probe 保留同三个预声明真实请求、同 seed 和 2048 输出上限。新 baseline 明确命名为 `fp32-highest-efficient-baseline`：baseline 与 candidate **均使用修订后的显式 KV efficient 后端**，仅对照 highest/无前缀缓存与 high/精确前缀缓存。原 Math-GQA 基线的长反向 OOM 保留于 `b37059e`，不再重复运行该旧实现。因此新性能表只能解释修复后同一 efficient 后端上的精度/缓存组合差异，不能写成相对原 H1 Math-GQA 的直接等工作量加速比。

新 baseline 保留生成和完整原序列前向概率诊断；实际反向只考 candidate，baseline 行明确写 `backward_not_repeated`。这省去重复的基线反向工作，将有限容量验证放在待部署路径；不能把没有执行的新 baseline 反向标为通过，也不能因为原 Math-GQA 失败就宣称新 efficient baseline 反向已失败。原首请求反向通过、第二请求 OOM、第三请求反向未测的事实分别保留。Candidate 在原概率门通过后仍执行全部三条真实反向，零优化器更新。

这项省略不是隐藏原失败。两个新 variant 的整个进程总时长因诊断工作量不同不能直接作为等工作量加速比；对照应使用明确的生成区间以及绑定同一原输入/输出的 fixed-work replay 字段。原 `b37059e` 文件和结果不改，新 clean source 的正式结果另行记录。

## 必要 CPU 接口复核

在独立 resident 环境、`CUDA_VISIBLE_DEVICES=''` 下运行 `tests/test_sampling_replica_v019.py` 与 `tests/test_prefix_cache_v019.py`，8 项通过（4.48 秒）。人工 TinyActor 补了显式 config setter，生产构造器没有为夹具放宽要求。

新增真实官方随机 tiny Qwen3.5＋PEFT 的 CPU 构造控制，未做模型 forward：确认 full-attention 与同名 SDPA mask 已注册，三个 linear-attention 层及其类型不变，profile 为 efficient-only/high，所有模型参数仍在 CPU。其余控制覆盖 readonly 副本不构造 critic/optimizer、精确 snapshot/actor 身份与原采样轨迹，以及前缀 cache clone、匹配、清空边界。前缀数值控制使用官方 CPU SDPA 小模型；它不声称验证 CUDA-only 显式 KV 的全模型数值，后者由新正式 GPU 门负责。相关 Ruff 检查通过。
