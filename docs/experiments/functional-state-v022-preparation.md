# v0.22 N1：函数式状态与非重入重算候选准备

日期：2026-09-27。本记录说明唯一 N1 候选的实现、CPU 正确性控制与真实验证接口。没有在本准备阶段启动 GPU、下载权重、读取两条保留请求的内容，或改变模型/精度/概率门。旧 v0.20、v0.20.1、v0.21 运行源与原结果保持原样。

## 1. 一个候选及其计算对象

模块：`src/proworksim/functional_qwen_v022.py`；版本 `functional-qwen-state-v0.22`。生产接口：

```python
from proworksim.functional_qwen_v022 import learning_logprobs
probabilities = learning_logprobs(owner.model, original_token_trace)
```

调用方需保留原 owner 的身份/dtype 校验，按实际 learner 的 train 模式执行，再使用原优化目标；函数返回每个原输出 token 的 FP32 条件 logprob。它没有改动共享训练器、PPO 分母、优势、成员/窗口归一化或优化器配方。N1 诊断本身使用所有原输出 token 的负平均 logprob 做一次真实反向，但不执行参数更新。

对固定 teacher token 序列，原逐 token/逐层的因果计算可按层作拓扑重排：每一层先完整处理 prefill，再按原顺序处理后续 token；下一层接收这一层各位置的结果。每次状态转移显式接收旧 `(conv,recurrent)` 或 `(K,V)`，返回新状态，不依赖可变的推理 Cache 对象。当前 token 仍可通过先前状态依赖过去的 LoRA 计算。

全部原 prompt 进入 prefill，所有原输出 token 都保留为目标。最后一个输出 token 不需要再产生它后面的预测，因此实际 teacher 输入为 `input_ids + output_ids[:-1]`；最后一个输出仍然有自己的条件概率和梯度。这不是裁尾或减少目标。对 prompt 的参数依赖也保留，但 prompt、工具结果与同事消息不会被新增为生成目标。

冻结的重算组织为：

- 每个 decoder 层的完整函数式扫描设置外层非重入 checkpoint。
- 层内 prefill 是完整独立重算块；后续每 **8 个**单 token 转移为一个块。
- 每个输出目标的最终 norm/head/FP32 归约设置独立 checkpoint。
- 所有 checkpoint 显式 `use_reentrant=False`，保留 RNG；跨块状态作为 tensor 参数传递，无生产路径 detach。
- 仍使用原 Qwen 模块权重、官方 chunk/recurrent 运算、当前 attention adapter、原 FP32 head 和原精度。只将卷积/缓存状态的可变写入表达为新 tensor 状态，不新增 kernel、框架、精度或模型。

块大小 8 在读取保留请求内容和任何 GPU 结果之前选定。根代理提供保留请求的预选长度后，将长序列内存纳入该候选的事前设计；没有根据保留请求概率/梯度成绩调整块大小。

## 2. 为什么需要验证真实梯度

不 checkpoint 的完整函数式递归图只用于小模型参考；它不是另一个真实 GPU 候选。测试另有一个明确错误的控制：在 decode 前 detach 过去状态。该控制只存在于参考接口的测试选项中，生产 `learning_logprobs` 不接受这个选项。

[PyTorch 2.6 checkpoint 文档](https://docs.pytorch.org/docs/2.6/checkpoint.html)说明，非重入 checkpoint 会记录 autograd 图并支持重算；默认确定性检查主要核对 tensor shape、dtype、device，不能替代数值和梯度对照。若重算依赖改变的全局状态，可能产生错误梯度。因此，本候选不以 `requires_grad=True` 或前向一致作为完整证明，而做参考梯度、有限差分与截断依赖负对照。

模型参数在 forward/backward 之间须保持同一身份。候选没有关闭全局精度检查或放宽概率门来追求一致；模块中的记录性 hook 计数不作为计算分支条件。

## 3. CPU 实验与结果

环境：项目独立 resident 环境，Torch 2.6、Transformers 5.17.0、真实 PEFT；命令显式 `CUDA_VISIBLE_DEVICES=''`。

控制对象为随机小型 **8 层**官方 Qwen 混合结构：每四层三个 linear-attention 加一个 full-attention，hidden size 32、词表 64，q/v LoRA r8/alpha16/dropout0。CPU fixture 的 LoRA B 按固定种子初始化为非零小值，以同时检查 A/B 梯度，并让第一个 full-attention 中的 LoRA 经后续 recurrent 层影响输出。该 fixture 不使用候选模型权重，不产生训练数据或目标模型支持。

固定长度为 70 个 prompt token、12 个 teacher 目标，跨越官方 prefill chunk 边界及候选 8-token decode 块边界。

执行：

```text
CUDA_VISIBLE_DEVICES='' PYTHONPATH=src runs/v016-sdk/resident-venv/bin/python -m pytest -q -s tests/test_functional_qwen_v022.py
```

最终结果：**1 passed in 5.60s**。这是一个包含多项断言的集成控制，不应计作多个真实任务样本。

| 检查 | 实际结果 |
|---|---|
| checkpoint 候选 vs 完整无 checkpoint 图的输出概率 | 最大绝对差 `0.0` |
| 两者所有可训练 LoRA 参数的梯度 | 最大绝对差 `0.0`，均有限且有非零元素 |
| 候选/参考 vs 独立官方 cache teacher 重放 | 在 `atol=1e-5, rtol=1e-5` 下通过；未另报该比较的精确最大差 |
| `.autograd.grad` 与实际 `.backward()` 两种调用 | 候选实际 `.backward()` 的逐参数梯度与完整参考图一致 |
| 有限差分方向导数 | `0.08556842803955078` |
| 对应解析方向导数 | `0.08554976433515549` |
| detach 负对照的前向 | 与完整图完全相同 |
| detach 负对照相对梯度 L2 误差 | `0.6777320504188538`，约 67.77% |

有限差分使用第一个 full-attention V 投影 LoRA B 块的归一化参考梯度方向，中心差分固定 `epsilon=0.01`；接受界为绝对 `2e-4`、相对 `0.02`。这是一条方向导数核查，不是穷举所有参数的有限差分。全参数 autograd 梯度另有参考图逐项对照。

真实 `.backward()` 产生参数 grad 后清除，没有创建或执行优化器更新。有限差分对参数的 CPU 人工扰动随后精确恢复。负对照说明当前检查能发现“前向看起来一致、历史参数依赖却丢失”的错误；其 67.77% 是这个随机 fixture 的值，不是 9B 的梯度偏差估计。

相关三个源码/测试文件 Ruff 通过，CLI `--help` smoke 通过。没有重复旧 N 无梯度诊断，也没有运行全库测试。

## 4. 真实 N1 接口与预先保留材料

```text
python -m scripts.functional_paths_v022 \
  --plan examples/id-vtdo-v22/n1-heldout.json \
  --output <new-N1-directory>
```

该 CLI 不选择 GPU、不排队、不重试、不采新 token、不启动后继。统一监督负责资源授权。计划提供原 v0.20.1 `owner_plan_ref`，按原 base manifest、profile、recipe 初始化一个 owner；每条记录必须与实际 owner 的 actor identity 和完整 inference_profile 相同。

预先由根代理选择的有限清单为：

| 用途 | 原 prompt / 原输出 token 数 |
|---|---:|
| 旧开发诊断 | 8473 / 146 |
| 保留请求 1 | 4251 / 308 |
| 保留请求 2 | 13275 / 2048 |

选择按长度条件和固定文件名破同规则进行，未使用概率差或梯度结果。两个保留请求仍是已有开发模型记录，不是独立来源锁定测试集。本实现阶段只读取其计划元数据，未打开请求文本/token/logprob 内容；实际执行入口在候选与 CPU 控制冻结之后逐条读取并校验 SHA。长度上限结束的 2048 个输出仍全部作为实际目标保留。

每条请求先写 `task.json`，然后：

1. 保持原 `.02/.002` 门，执行候选可微前向并与原行为概率比较。
2. 原门失败即结束该候选；不执行此请求 backward，也不换实现或补采。
3. 通过才执行真实负平均 logprob 的 backward，记录尝试/完成、耗时、梯度 dtype、有限性与非零元素、实际显存峰。
4. 任何非有限梯度、身份变化，或负均值诊断出现全部零梯度，都不构成合格候选；零梯度有独立 `stopped_candidate_zero_gradient_diagnostic` 状态。
5. 只有三条固定请求均通过前向门和实际非零有限反向，且最终参数/优化器状态及源码保持不变，才报告有限清单资格通过。

N1 的零梯度诊断失败与后续真实 RL 的零优势/零信号不同：真实业务窗口若无有效优势，应如实零步，不能人为制造更新；本诊断的目的则是建立可观察的可微路径。所有 N1 参数步数为 0。

## 5. 资源建议及尚未证明的事项

根代理冻结资源为 N1 单实例、单 GPU、最多 30 GPU 分钟，每请求含前向/反向最多 15 分钟，自身 GPU 进程采样上限 72 GiB、RSS 64 GiB。是否及何时启动由统一监督处理，本文不是实际运行状态或新授权。

完整 prefix 与过去状态依赖不能因长请求而裁剪。对于 13,275＋2,048 的记录，K/V 随时间增长，prefill 重算、嵌套 checkpoint 和逐目标 FP32 head 都可能带来较大计算与内存代价。层级与 8-token 内块重算的作用是避免同时保存所有逐步 attention 中间量；它仍要保存/重算所需边界状态，不保证可以在 72 GiB 或 15 分钟内完成。

CPU 控制不证明真实 9B/BF16 概率门、实际反向容量或吞吐量。真实请求若失败或超限，应保留部分进度及失败原因并结束该候选，不读取剩余额度为修改块大小、尝试第二数值实现或扩大训练的许可。

即使 N1 有限清单合格，也不是学习收益。后续只有在训练投影、世界合同和独立资源预算都具备时，才可接入真实工作—至多一次共享更新—新策略再工作的桥接；更新目标及数据归属规则不能由本模块悄悄改写。
