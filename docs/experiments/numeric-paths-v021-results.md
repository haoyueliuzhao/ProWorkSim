# v0.21 N 线结果：固定 token 的增量与完整计算路径诊断

实验日期：2026-09-27。本记录基于已闭合的 `runs/domain-v021-ne/N` 原始产物，只读整理；撰写过程中未重放模型、重跑评价或测试，也未更改运行源码、参数及旧失败记录。

**主要结果：同一 v0.20.1 参数与数值配置下，按原生成约定进行的缓存增量重放，精确复现了原 146 个已采样 token 的行为 logprob；完整无缓存前向仍复现原概率门失败。开启实际 learner 的 train 模式与非重入 checkpointing 后，完整前向的概率及所观察 hidden 与完整无梯度前向相同。**

这将本条记录上的差异范围收窄到了增量缓存与完整计算的执行差别，而不是原行为概率记录无法复现。它没有确定单个算子的因果责任，也没有得到可用于更新的缓存梯度实现。本次 0 新采样、0 世界 episode、0 backward、0 actor/critic 更新；`complete_diagnostic` 仅表示诊断完整执行，不表示通过训练准入。

## 1. 对象、源码与执行边界

使用 v0.20.1 已保存的首条真实调用：8,473 个输入 token、146 个输出 token。完整序列长度为 8,619。固定原输入、输出、行为概率、原始权重与初始化 LoRA；未重新生成输出或选择新的请求。

原调用文件：

`runs/domain-v0201-p1-9b/resident/calls/resident_fc46ba8217e7496985f6c9054741f6f6.json`

SHA256：`6a348353e319fe7ceb4954168f592f61188ea2a6ef94be02c58aa6d8566c9f65`。

关联原数值报告为 `runs/domain-v0201-p1-9b/numerical.json`，SHA256 `49371bd535c435e9e09242d341e41def50c837eba5c63edf708a952f6373687a`。原报告的 max/mean logprob 差分别为 `0.07183623313903809 / 0.0026083623531591538`，原 `0.02 / 0.002` 门仍保持失败。

本次运行源码 commit：`7d71b1ff33e54e37590b09c96151bc667f840401`；source tree SHA256：`8431a519984c7bd77ab3addf31ce4fb32866319b41478c87b47e6e67ae6a972a`。运行前后 commit、tree SHA 和 clean 状态相同。原 v0.20.1 执行源 `73d5a55…` 与原报告不改；本次是新诊断源，不将新测量回填旧运行。

沿用的数值配置为 `candidate-runtime-v0.20.1`：BF16 冻结 backbone、FP32 冻结 untied LM head、FP32 LoRA 与归约、FP32 matmul `highest`、原 BF16 explicit-KV efficient-only attention、无 prefix cache、一个 resident。原生窗口初始化、原参数与实际 inference_profile 在诊断前逐字段核对。

运行于物理 GPU4，子进程 PID `82557`。北京时间开始 `2026-09-27 18:56:04.255516`，结束 `18:56:49.013613`，exit code `0`；分配设备时间 `44.758097648620605` 秒。监督预算为 N 最多 1,200 秒、单任务最多 900 秒，预留 30 秒用于停止，实际 N 停止阈值为 1,170 秒；未触发资源或时间停止门。

## 2. 三条实测重放路径

原采样程序保存的概率记为 s。本次没有覆盖或替换 s。三条路径都对同样的 146 个已采样 token 计算条件概率，再与 s 比较。

| 路径 | 执行方式 | 对原 s 最大绝对 logprob 差 | 对原 s 平均绝对差 | 原门 | 与 s 完全相同的 token 数 |
|---|---|---:|---:|---|---:|
| `cache_no_grad` | 原约定 prefill＋逐 token cache；`inference_mode`；teacher forcing 原输出 | 0.0 | 0.0 | 通过此条记录检查 | 146/146 |
| `full_no_grad` | 完整原 input＋output，`use_cache=False`，无梯度 | 0.07183623313903809 | 0.0026083623531591538 | 失败 | 83/146 |
| `full_grad` | 同一完整输入，实际 learner 的 train＋非重入 checkpointing，有梯度图 | 0.07183623313903809 | 0.0026083623531591538 | 失败 | 83/146 |

两条 full 路径各有 6 个 token 的绝对差超过 `0.02`。两者逐项 logprob 完全相同，`full_grad` 对 `full_no_grad` 的 max/mean 差均为 `0.0`。`full_no_grad` 对 cache 的 max/mean 差即为上表 full 对 s 的差。

cache 重放通过安装版官方 `prepare_inputs_for_generation`、position 准备和 model kwargs/cache 更新接口喂入原 token，不调用 `generate` 或 `multinomial`。第一次处理全部 8,473 个输入，随后 145 次处理上一个已保存输出 token，每次记录下一个已保存 token 的概率。最后一个目标输出的预测使用 cache 长度 8,618；完整重放依照原 learner 接收 8,619 个 token，并排除最后一个无后继目标的 logits 位置。这是自回归条件概率的对齐，不是裁剪输出训练目标。

**这里的逐项相同限定为已选 token 的保存 logprob。**不能据此声称所有 248,320 个词表项逐位相同、全分布 KL 为零或梯度一致。它也只覆盖这一条已保存请求，不能估计其他请求的通过率。

## 3. 实际进入的计算分支

通过 Python call profiler 观察已安装上游参考函数的真实 code object 调用，未修改或替换函数计算。下表是实际计数，不是根据形状推测的分支。

| 路径阶段 | `causal_conv1d_fn` | `causal_conv1d_update` | `torch_chunk_gated_delta_rule` | `torch_recurrent_gated_delta_rule` |
|---|---:|---:|---:|---:|
| cache prefill | 24 | 0 | 24 | 0 |
| cache 145 次增量 decode | 0 | 3,480 | 0 | 3,480 |
| full 无梯度 | 24 | 0 | 24 | 0 |
| full 有图前向 | 24 | 0 | 24 | 0 |

模型共有 32 个 decoder 块，其中 24 个为 linear-attention 块。增量阶段的 `3,480 = 145 × 24`。cache 路径共观察到 7,008 次上述参考函数进入，两条 full 路径各 48 次。原日志同时报告未安装 `causal_conv1d` 和 `flash-linear-attention`，使用参考 PyTorch 路径；实际 profiler 计数与该记录相符。

这证明当前所测路径在卷积更新和 gated-delta 计算中实际采用了不同的完整/逐步实现。它尚不区分卷积、DeltaNet、投影形状、其他归约与低精度运算各自造成多少误差；没有执行单算子替换或因果消融。

## 4. hidden 最早可见差异及其限制

预声明的零基输出位置为 `0,1,2,31,73,145`；位置 `62` 是由原数值报告最大失效位置选出的额外诊断，不能将其当成独立预注册稳定率样本。观察的是各 decoder 块**输出**，而不是块内每一个中间算子。

full/cache 比较结果如下。位置 0 为 prefill 对首个输出 token 的预测；其他位置属于增量 decode 对应的预测。

| 输出位置 | 首个非零差异 decoder 块 | 第 0 块 max 绝对 hidden 差 | 第 0 块 mean 绝对差 | 第 31 块 max 绝对差 | 第 31 块 mean 绝对差 |
|---|---|---:|---:|---:|---:|
| 0 | 无；32 块均相同 | 0 | 0 | 0 | 0 |
| 1 | 0 | 0.00048828125 | 0.000022907275706529617 | 0.5 | 0.025740116834640503 |
| 2 | 0 | 0.00048828125 | 0.00004035164602100849 | 0.5 | 0.027179181575775146 |
| 31 | 0 | 0.00048828125 | 0.000021459534764289856 | 0.5 | 0.027769014239311218 |
| 62（额外诊断） | 0 | 0.00048828125 | 0.000028197653591632843 | 0.5 | 0.029923856258392334 |
| 73 | 0 | 0.0009765625 | 0.00004274072125554085 | 0.25 | 0.025196701288223267 |
| 145 | 0 | 0.0009765625 | 0.00003705499693751335 | 1.0 | 0.04600059986114502 |

除位置 0 外，六个观察位置的 32 块输出均存在非零差异。full-grad/full-no-grad 比较则在这 7 个位置×32 块的 hidden 向量上全部差值为零。

**位置 0 需要单独限定：decoder 输出相同，不等于后续投影与归约得到的概率逐位相同。**原 s 与 cache 在位置 0 的 chosen logprob 均为 `-1.1122171878814697`，两条 full 路径均为 `-1.112210750579834`，故 `full − cache = +0.0000064373016357421875`（约 `6.44e-6`）。该值直接来自 `paths.json` 中 `between_paths.full_vs_cache.signed_delta[0]`，以及各路径 `comparison_to_original_sampling` 的第 0 项。对应位置 0 的 chosen raw logit 摘要也不同：cache 为 `26.600521087646484`，full 为 `26.600547790527344`；两者 logits dtype 都是 FP32。当前没有在 decoder 后的最终 norm、head 投影及概率归约之间逐一设置因果对照，因此只报告这个后续数值差异，不将其归因于 head 单个模块，也不据 decoder hidden 相同宣称整条概率计算相同。

因此可以说：**从首个被观察的增量预测位置 1 开始，差异已在第 0 个 decoder 块输出可见。**不能说“第 0 层 DeltaNet 被证明是根因”：该块同时包含归一化、投影、卷积/DeltaNet、残差与 MLP，当前记录没有把这些块内边界逐一分开。第 31 块是最终 decoder 块的输出，不能误称为 LM head logits 差或最终 norm 后 hidden 差。

完整 hidden 向量只在诊断进程内短暂用于逐元素比较；产物保存标量差值及少量元素/统计量，没有写出全模型激活或全词表 dump。logit 摘要包括 chosen raw logit、top-8、FP32 dtype、温度及 logsumexp，不据此计算未测量的全分布 KL。

## 5. mask、position、cache 与实际梯度前向

所记录位置的 decoder mask 均为 `None`，对应该无 padding 输入在当前 mask/causal 接口下的实际传值；这不表示关闭了因果约束。cache 的 `record_past` 为 `False`。

代表性状态：

| 状态 | 实际 dtype | 代表性 shape | autograd 状态 |
|---|---|---|---|
| linear 块卷积缓存 | BF16 | `[1,8192,4]` | `requires_grad=False`，无 grad_fn |
| linear 块 recurrent 缓存 | FP32 | `[1,32,128,128]` | `requires_grad=False`，无 grad_fn |
| full-attention K/V 缓存 | BF16 | `[1,4,L,256]` | `requires_grad=False`，无 grad_fn |

cache 长度从 prefill 的 8,473 增至最后预测时的 8,618。增量位置 1/2/31/62/73/145 实际 position id 分别为 8,473/8,474/8,503/8,534/8,545/8,617。完整前向 position ids 从 0 到 8,618，hidden 输入 shape 为 `[1,8619,4096]`；逐步输入为 `[1,1,4096]`。已观测的序长与位置对应关系没有出现明显 off-by-one。

`full_grad` 的实际记录为：

- `grad_enabled=True`、`model_training=True`。
- 33 个带 checkpoint 属性的模块均 `enabled=True`、`use_reentrant=False`。
- `config_attention_dropout=0.0`；`nn.Dropout` 模块列表为空。LoRA 原 dropout 为 0，当前 PEFT 用 Identity，不把空列表解释为漏跑了正 dropout。
- 选定 token 的归约输出为 FP32，`requires_grad=True`，grad_fn 为 `SqueezeBackward1`。
- 未调用 backward，诊断结束所有 actor 参数 `.grad` 均为空。

输入 embedding 上的既有 `enable_input_require_grads` hook 会令部分 no-grad 观察行的输入 `requires_grad=True`；不能孤立据此声称无梯度路径建立了训练图。路径上下文、缓存状态及最终概率 tensor 的 graph 记录才用于区分执行模式。

## 6. 为什么 no-grad cache 不能直接成为当前训练路径

这次 cache 路径在 `inference_mode` 下执行，状态没有保留可微过去依赖。它验证了原采样的重现性，**没有实现一个可微的缓存 learner**。

安装版 cache 的卷积和 recurrent 更新含原地 `copy_`；安装版 `GradientCheckpointingLayer` 在 train＋checkpoint 模式下会关闭 `use_cache`，并对不支持带缓存 checkpoint 的层移除 `past_key_values`。这些事实限制了把现有缓存对象直接搬入 learner 的做法。

因此本次明确没有执行 cached-grad 或 cached-backward，也没有 detach 过去状态后冒称同一训练目标。未来若研究一致的增量/分块学习实现，必须保留历史 LoRA 对后续输出的依赖并证明可微执行；改变概率分母或另设 mismatch 处理配方则属于另一项基础优化协议修订，不由本次诊断自动授权。

## 7. 参数身份与资源

诊断前后实际 adapter hash：`4e82a9439a4ea533a327313426684874b1eec32eb45433fd24f8e7d9ce2241fa`。

基座 manifest SHA256：`030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6`。

实际 inference_profile SHA256：`c640cad53145a1df8ee7cc81932be81d931d58c1182aa872530460a030a694a6`。

这些字段与原 v0.20.1 采样 identity 相同，N 的初始和结束实际 identity 也相同。新 `resident/owner.json` 的字节 SHA 恰与原 owner 相同。actor/critic 步数均为 0，未检测到参数梯度，源码前后不变。身份检查不是对每个冻结基座参数结束后重新做全量权重哈希；冻结基座与有效配置受原加载 manifest、实际 dtype/布局检查及只读执行边界约束。

| 路径 | 路径耗时（秒） | Torch allocated 峰值（bytes） | GiB |
|---|---:|---:|---:|
| cache 无梯度 | 10.09389182087034 | 22421225472 | 20.881393432617188 |
| full 无梯度 | 1.4955050218850374 | 22162109440 | 20.6400728225708 |
| full 有图前向 | 2.7547342437319458 | 24210104832 | 22.547417163848877 |

每条路径重置对应 Torch 峰值统计；该峰值包括当时已驻留模型，并非“额外激活内存”。路径耗时包含 profiler、hooks 和摘要统计开销，不作为生产推理/训练吞吐 benchmark。

整个 N 的分配设备时间为 `44.758097648620605` 秒，包含加载与监督退出。监督共 20 个样本，资源查询失败 0；自身 NVML 进程峰值为 `24350 MiB`，RSS 采样峰值 `15998779392 bytes`，采样中 GPU4 未出现其他计算 PID。启动观测中 GPU4 空闲 `81154 MiB`、utilization 0、无计算进程。离散样本不能证明样本之间绝无短时竞争或峰值。

N 目录当前产物合计 `2707789 bytes`，不包括父目录的监督日志、资源记录及其他实验产物。统一监督的总产物预算另行涵盖父运行目录。N 未触发 72 GiB 自身 GPU 进程观察门、64 GiB RSS 或 5 GiB 总产物门。

**22.55 GiB 是本次 full-grad 有图前向的实测峰值，不是 backward 或 optimizer step 峰值。**本次不能认证单卡训练容量。

## 8. 原件与上游源码索引

以下 N 路径均相对于仓库根；原始文件是结果依据，本文不替换原件。

| 原件 | SHA256 |
|---|---|
| `runs/domain-v021-ne/N/report.json` | `793dba4a54702e0e666c3c572715a711d3fd3282745424a6f380ddf60428421c` |
| `runs/domain-v021-ne/N/paths.json` | `0c872dda89de89f9ce1cf4ff3e408a38167de1123f930cb713eaa3bb3c4015f2` |
| `runs/domain-v021-ne/N/cache_no_grad.json` | `9df7e281ca680cc18bd0ce7436dece84aad1a1c904e5f957484b12d042780c83` |
| `runs/domain-v021-ne/N/full_no_grad.json` | `df91d67babc0eb86bcdd13310f55d28caf7b21604a881c0b95743427a800f5d4` |
| `runs/domain-v021-ne/N/full_grad.json` | `cc62caf8af27ec2b9215cf409e3da76d88d90bbbfe5a5605293bbb35baeed6c4` |
| `runs/domain-v021-ne/N/resident/owner.json` | `02927f762403997e4dece7feefca1ec17a86b3fd9803a6c1dd6c7261eae858cc` |
| `runs/domain-v021-ne/N/resident-model-loading.json` | `f3cc7aca76bf55de4b62d1bb5067c3739d5ba40312d48e72e6346918e6209acc` |
| `runs/domain-v021-ne/N/resident-generation-contract.json` | `9b60ed07e753027646e01b7c64ee707258adcf7663e523d43e77dd562718dcf7` |
| `runs/domain-v021-ne/N/resident-eos-contract.json` | `0f52bd2df2d5a7a35b01c72df247577b7c85bc64fe2c60f2fb25608329e1891f` |
| `runs/domain-v021-ne/N-resources.jsonl` | `ca4c7f73232dd5768fdb517e01726912d48ff61fbaecb0d61bec0ca8b812aff0` |
| `runs/domain-v021-ne/N.log` | `2199476309d0ea6718da0fabe109233f04813aaf247cb1de2df64340e3c5aabc` |

实际安装源码均位于 `runs/v016-sdk/resident-venv/lib/python3.12/site-packages/transformers/`：

| 相对源码文件 | SHA256 |
|---|---|
| `models/qwen3_5/modeling_qwen3_5.py` | `762feb6c7426a7f15b5bf830df54c07438bf9e7c27b8cdb23179045920412c3b` |
| `cache_utils.py` | `702144bb44553f6339ea1bf23c8205a708bb5f8c7c09cb3a2db484182646743c` |
| `generation/utils.py` | `bb558d8676be95457126c82a32600dad206c13e4fb96b4f5d114f1f2483d7f62` |
| `integrations/hub_kernels.py` | `c1eafefe0cbdf7f0deaa21b1ef6cb6d7c6082b3f486651d069ff38fcf3e53c95` |

N 的有限结论不依赖 E 是否成功。独立 E 的业务结果应在其自己的归档中报告；本文件不将 N 诊断计为工作 episode、学习改善或外部 benchmark 成绩。
