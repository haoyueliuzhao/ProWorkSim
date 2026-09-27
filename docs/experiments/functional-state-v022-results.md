# v0.22 N1 正式结果：函数式状态候选通过固定清单的前向与真实反向检查

日期：2026-09-27。本文及同名 JSON 只读派生自已闭合的 `runs/domain-v022/N1` 原件，没有重新运行模型、概率检查、反向、评分或测试；原件字节保持不变。

**唯一 N1 候选在一条旧开发序列及两条事先冻结的保留请求上，全部精确复现原已选 token 的行为 logprob，并完成有限、非零的 FP32 LoRA 反向。三个请求均未更新参数，actor、critic、优化器、RNG 和源码守卫通过。**

这支持“该固定配置、固定清单上的可微路径与资源准入”，不等于学习收益、所有未来数据的通过保证或全模型梯度正确性的理论证明。N1 的 `qualification_passed=true` 不能代替真实业务训练投影、更新桥接或主 pilot 的独立门槛。

## 1. 固定候选与验证清单

执行源：`7edb95c9f7a147dc579b41694cd6899fc14afb1e`；source tree SHA256：`281dbc19a52dbcc7ba262150b410efdfb46e71029d70f957625f225b702e5f4e`。运行前后均 clean，commit 与 tree SHA 不变。

候选为 `functional-qwen-state-v0.22`：同一原 v0.20.1 数值模型、函数式旧状态→新状态、完整 prefill、层级非重入 checkpoint、固定每 8 个 decode token 的内层重算块、逐目标 head checkpoint。原 BF16 backbone、FP32 冻结 head、FP32 LoRA/归约、attention、温度及 `.02/.002` 概率门均不改变。没有 detach 过去状态，没有更换模型、框架或精度，也没有第二个候选。

所有原输出均为目标，包括原长度上限结束的 2,048 个输出；原 prompt 全部进入 prefill。未新采样、未补采、未以已通过请求替换未通过项。

| 固定用途 | 原输入 / 原输出 token | 原记录来源 |
|---|---:|---|
| development | 8473 / 146 | v0.20.1 首条失败诊断调用 |
| heldout-0 | 4251 / 308 | v0.21 E 已有模型调用 |
| heldout-1 | 13275 / 2048 | v0.21 E 已有模型调用 |

共 3 条请求、2,502 个原输出目标，输入长度之和 25,999。token 不是独立统计样本，也不是本轮新生成量。两条保留请求是在候选实现与 GPU 执行之前，按输入/输出长度及文件名破同规则选定，未根据 N1 概率或梯度结果选择；实现阶段未读取其内容，候选与 CPU 控制冻结后才由实际入口读取。

“保留”仅指未参与 N1 实现选择。这些仍是已有开发记录，不是独立来源的锁定测试；现在已经用于 N1 验证，后续不能继续称为未接触材料。

## 2. 概率、前向与反向结果

| 请求 | 前向秒 | 对原 s 最大 / 平均 logprob 差 | 实际反向秒 | 非零梯度元素 | 梯度检查 |
|---|---:|---:|---:|---:|---|
| development | 13.233658127952367 | 0.0 / 0.0 | 53.47949187178165 | 589824 | 有限，32 个 FP32 tensor |
| heldout-0 | 25.109155520331115 | 0.0 / 0.0 | 82.97690750891343 | 589823 | 有限，32 个 FP32 tensor |
| heldout-1 | 160.71698350692168 | 0.0 / 0.0 | 578.22283930704 | 589824 | 有限，32 个 FP32 tensor |

三个请求分别有 146/308/2048 个已选 token 的 logprob 与原行为概率逐项相同。原 `max_abs_logp=0.02`、`mean_abs_logp=0.002` 门全部通过，没有放宽、改分母或替换原行为概率。

每条请求先执行候选有图前向并检查原门，通过后才对全部原目标的负平均 logprob 调用真实 `.backward()`。三次反向尝试均完成；不是 `requires_grad=True` 的替代记录。模型实际处于 train 模式，概率输出 FP32 且有梯度；每次均观察到 32 个 FP32 梯度 tensor、全部有限，整组存在非零元素；不表示每个 tensor 都非零（初始 LoRA B 为零时部分 LoRA A 梯度可为零）。

上述 32 个 tensor 是每次检查的同一组 LoRA 参数，不是 96 个不同参数对象。这里只记录有限性、dtype 和非零元素数，没有保存 9B 完整梯度矩阵，也没有报告未测得的全模型梯度误差或梯度 L2 范数。

三次诊断后均清除累积梯度。`actual_backward_calls=3`、`backward_calls_attempted=3`；`parameter_steps=actor_steps=critic_steps=0`。N1 没有 critic 学习前向、世界 reward、业务 rollout 或优化器 step，因此它不是一次真实 RL 更新，更不是学习收益。

## 3. CPU 梯度依赖证据及其范围

CPU 控制已在真实 GPU 请求内容打开前完成；细节见 [实现准备记录](functional-state-v022-preparation.md)。随机官方 8 层 Qwen 混合模型加真实 PEFT，70 个 prompt token、12 个输出目标，包含第一个 full-attention 的 LoRA 经后续 recurrent 层产生的历史依赖，并跨过固定 8-token checkpoint 块边界。

结果为 `1 passed in 5.60s`，该单个集成测试中：

| CPU 检查 | 结果 |
|---|---|
| 候选与完整无 checkpoint 递归图的前向最大差 | 0.0 |
| 全部 LoRA autograd 梯度最大差 | 0.0 |
| 实际 `.backward()` 与完整参考梯度 | 逐参数一致 |
| 与独立官方 cache teacher 前向 | `atol=1e-5, rtol=1e-5` 下通过 |
| 固定中心差分，epsilon 0.01 | 0.08556842803955078 |
| 对应解析方向导数 | 0.08554976433515549 |
| detach 负对照前向 | 与完整图相同 |
| detach 负对照相对梯度 L2 误差 | 0.6777320504188538（约 67.77%） |

有限差分只检查第一个 full-attention V 投影 LoRA B 的一个归一化参考梯度方向，不是逐参数穷举。CPU 采用 FP32 随机小模型及非零 fixture LoRA B；它不冒充实际 BF16 9B 权重。负对照证明这些控制可以发现“相同前向却截断历史梯度”的错误，但 67.77% 只属于该 fixture。

真实 9B 三条请求则提供了“原行为概率一致＋实际反向完成＋梯度有限非零＋资源可承担”的证据。没有在 9B 上构建另一个不 checkpoint 的完整参考反向图，也没有对 9B 穷举有限差分。因此结论是**一个已实现候选在具体小模型控制与有限真实数据验证下获得支持**，不是全模型、所有权重状态、所有请求的理论证明。

## 4. 身份、优化器、RNG 与源码

初始及最终 actor identity 完全相同，逐请求也记录了 identity unchanged。关键字段为：

- adapter SHA256：`4e82a9439a4ea533a327313426684874b1eec32eb45433fd24f8e7d9ce2241fa`。
- base manifest SHA256：`030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6`。
- inference_profile SHA256：`c640cad53145a1df8ee7cc81932be81d931d58c1182aa872530460a030a694a6`。

`learning_state_guard.learning_unchanged=true`，覆盖 actor、critic、两个优化器、policy revision、actor/critic step 与 critic 历史标记的前后指纹。没有通过恢复权重掩盖一次更新；检查只按既有守卫恢复 RNG。

本次 RNG 在检查前后本来就相同，before、after-diagnostic（旧守卫字段名为 `rng_after_collection_sha256`）、after-restore 三个 SHA 都是：

`ac512e2811e8199d56b5fee2959ab4bac6bb8ee79fda9bcd747128570fbf6237`。

`rng_restored_exactly=true`。完整前后状态 SHA 均保存在同名 JSON 及原 `actual/report.json`。源码 before/after 同为上述 `7edb95c9…` 干净执行源。

这些身份守卫不等于运行结束后重新对所有冻结基座 tensor 做全量哈希；冻结基座由原 checkpoint manifest、加载与实际 dtype/布局检查、同配置及禁止更新边界约束。实际可训练参数及学习状态则有前后指纹检查。

## 5. 显存、RSS、耗时与成本口径

| 请求 | 前向 Torch allocated 峰值 bytes | 前向 GiB | 含反向的该请求峰值 bytes | GiB |
|---|---:|---:|---:|---:|
| development | 24319824384 | 22.649601459503174 | 26772817408 | 24.934129238128662 |
| heldout-0 | 22216832512 | 20.69103765487671 | 23448705536 | 21.838308811187744 |
| heldout-1 | 27254159360 | 25.382413864135742 | 41479736832 | 38.63101530075073 |

每请求重置 Torch peak，含反向列是该请求前向至反向期间峰值，包含已驻留模型，不是纯反向额外分配量。尤其长请求的 38.631 GiB 已包含真实 backward，与旧 N 仅有图前向的峰值不同；仍未包括 optimizer step，因为本实验没有执行更新。

物理 GPU2，模型 PID `184405`。北京时间开始 `2026-09-27 20:10:05.686737`，结束 `20:26:03.703905`；监督真实分配时间 `958.0171685218811` 秒，即 `15.966952808698018` GPU 分钟或 `0.26611588014496695` GPU 小时。exit code 0，无 stop reason。

此成本含加载、三个诊断、清理与监督退出；不包含 CPU 开发、W1/X1/B1、等待空卡或未来学习。前向/反向计时之和小于整个分配区间，不将两者误作重复计费。也不按这三条不同长度的请求线性推断 144 个业务 episode 的费用。

监督共有 436 个资源样本，查询失败 0：

| 指标 | 观测值 | 范围 |
|---|---:|---|
| 本模型 NVML 进程峰值 | 47180 MiB | 离散进程占用样本，含保留/上下文等 |
| 本线 RSS 采样峰值 | 13309894656 bytes | N1 进程 |
| 同监督账中所有实验线 RSS 峰值 | 18080370688 bytes | 包含并行 W1，不能全部归给 N1 |
| GPU2 同卡其他计算 PID | 未观察到 | 仅限采样时刻 |
| N1 运行目录当前字节数 | 1062390 | 包含该目录原记录；不代表整轮产物总量 |

Torch allocated 与 NVML 采样峰值口径不同，不能互相替代。未观察到同卡其他 PID不排除采样之间的短时活动，且并行 W1 和服务器其他任务仍可能共享 CPU/主机资源。三请求均在预定 N1 总时限、单请求时限及显存/RSS 上限内完成；这些资源结论只覆盖本配置和本清单。

## 6. 原始资源流格式与证据索引

`resources.jsonl` 的实际字节格式是**以空白分隔的多行 JSON 对象流**，不是每一物理行一个 JSON 对象。派生文件用 `JSONDecoder.raw_decode` 顺序解析得到全部 436 条记录；没有改写、压平或替换原文件。后续工具应按实际格式解析，不能把逐行解析报错当成资源查询失败。

| 原件 | SHA256 |
|---|---|
| `runs/domain-v022/N1/actual/report.json` | `7e7f0136f941f5c2de833539f111f93dd3271b152aa51cb95e677257ef170ffb` |
| `runs/domain-v022/N1/state.json` | `6ac38c56861b0481a83578126be0a31d400c0c35f4ae235bdd30ff07965f7aef` |
| `runs/domain-v022/N1/resources.jsonl` | `58a6b6fc49a3fe50eda7714ff3663443bcc8b15689d1040600d3918b56c53ff1` |
| `runs/domain-v022/N1/actual/resident/owner.json` | `02927f762403997e4dece7feefca1ec17a86b3fd9803a6c1dd6c7261eae858cc` |

实际冻结在 `runs/frozen-v022-n1/` 的实现：

| 相对文件 | SHA256 |
|---|---|
| `src/proworksim/functional_qwen_v022.py` | `8c759c43108c3caef3fbcff8c906720471e0f3e9a957d23e65b5ae4d1e0699c8` |
| `scripts/functional_paths_v022.py` | `59b291ce164bc92c1172e671c8c2793841dfcea69d963c230a3b32193c26c685` |
| `tests/test_functional_qwen_v022.py` | `54c727f204a8b19b1f8e639ce3df565446cda8e8d0c72c07f7cec7450a743cf4` |

原请求引用：

| 用途与文件 | SHA256 |
|---|---|
| development：`runs/domain-v0201-p1-9b/resident/calls/resident_fc46ba8217e7496985f6c9054741f6f6.json` | `6a348353e319fe7ceb4954168f592f61188ea2a6ef94be02c58aa6d8566c9f65` |
| heldout-0：`runs/domain-v021-ne/E/resident/calls/resident_94fbbae3d13a41f89602f916799a568f.json` | `6c41c7d09a8f6fc95f2ff5ec4cb6d378f2614cb640bb652cd5c9de927a54d825` |
| heldout-1：`runs/domain-v021-ne/E/resident/calls/resident_8cc2606d71f64c5d998da560d16fd8cd.json` | `e04ad25a5ca46273b9838efdac142ac05ad393609394094b40e84d75e2c21974` |

[同名派生 JSON](functional-state-v022-results.json)保存完整标量、原状态守卫、引用和成本边界，不重复倾倒全部原概率数组。原件仍是最终依据。

## 7. 新共享 actor 接入的只读审查

另外只读审查了新 `collaboration_actor_v022.py`，未修改该文件，也未针对它重新运行模型或测试。该 subclass 仅覆盖 `learning_logprobs`：先执行原 owner 的运行约束检查，再调用已冻结函数式候选，并要求输出 FP32。

原 `update_window` 的无梯度概率准入、train 模式 actor 梯度前向和更新后选定概率检查，均调用这个可覆盖方法。因此接点保留了原行为概率分母、PPO clipping、成员/窗口分母、critic 与优化器步骤；采样仍走原 v0.20.1。这个静态审查支持接口语义，不替代之后的真实更新桥接。

一个报告口径需在后继协议中明确：旧更新报告仍可能使用 `full-sequence recomputation` 文本，不能据此误称执行了 v0.21 失败的“完整无缓存”路径。后继应显式标明 `functional-qwen-state-v0.22` 与本候选 CONTRACT；这里的完整指完整原上下文和全部原目标，数值执行采用函数式增量状态及重算。

N1 的成功资格只为后续有条件的真实工作—更新—再工作提供必要基础，不自动启动主 pilot，也不把这三条历史诊断记录变成训练经历或 ID‑VTDO 方法支持。
