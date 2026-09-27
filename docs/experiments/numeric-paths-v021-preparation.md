# v0.21 N：固定 token 数值路径诊断准备

此项保持已执行 v0.20.1 的同一基座、初始化 LoRA、FP32 head、attention、dtype、温度及概率门。它不是第三种数值配置；既不重新采样，也不把旧失败放行。实际 GPU 执行由独立授权与统一监督控制，本准备记录仅包含 CPU 控制。

## 固定输入与四个量

原实际调用：`runs/domain-v0201-p1-9b/resident/calls/resident_fc46ba8217e7496985f6c9054741f6f6.json`，SHA256 `6a348353e319fe7ceb4954168f592f61188ea2a6ef94be02c58aa6d8566c9f65`；关联原数值报告 SHA256 `49371bd535c435e9e09242d341e41def50c837eba5c63edf708a952f6373687a`。CLI 硬绑定这两个已有对象，并检查原报告引用的计划 SHA。启动新 owner 后必须逐字段匹配原 actor identity 与实际 inference_profile，才允许诊断。原 8,473 个输入及 146 个输出全部保留。

1. **原实际采样概率 s**：直接读取保存的原始 logprobs，不能替换。
2. **cache teacher replay**：调用安装版官方 `prepare_inputs_for_generation`、position 准备与 kwargs/cache 更新接口。首步完整 prefill，随后每步喂入原已保存 token，使用原采样的 inference_mode；不调用 `generate` 或 `multinomial`。只记录给定序列的条件概率。
3. **full no-grad**：完整 input+output、`use_cache=False`、`logits_to_keep=147`，按原 selected-token FP32 温度与归约路径计算。
4. **full grad-enabled**：同一完整输入与 logits 处理，但使用实际 learner 的 `model.train()`、已有非重入 gradient checkpointing 和零 dropout；记录各模块 checkpoint 开关/`use_reentrant`、实际 dropout、输出 `requires_grad` 和 `grad_fn`。没有执行 backward、critic forward 或 optimizer step。

三个重放路径均报告相对原 s 的原 `.02/.002` 检查，还报告 full/cache 及 full-grad/full-no-grad 的差值。命中原门只表示这条保存序列上已选 token 的检查，不能等同全词表 KL 一致、梯度无偏或训练准入。

## 观察哪些执行证据

预声明输出位置为零基 `0,1,2,31,73,145`。原 v0.20.1 最大失效位置 `62` 是额外诊断位置，明确标注来自已观测失败，不作为稳定率样本。每个位置保存各 decoder layer 的 hidden 标量摘要与 8 个首元素、selected logit、top-8 token/logit、温度及 logsumexp。仅少量 hidden 向量在诊断进程 CPU 内暂存，用于精确逐层差值；不写完整向量或全词表 dump。

模型层 hooks 记录实际 mask/position 的 dtype、shape、首尾少量元素；缓存只记录 KV、卷积、recurrent 状态的 dtype、shape、设备和 autograd 元信息。摘要不改变模型张量或缓存。Python call profiler 观察安装版四个原始参考函数的 code object，按路径、层与 prefill/decode 计数：

- `causal_conv1d_fn`
- `causal_conv1d_update`
- `torch_chunk_gated_delta_rule`
- `torch_recurrent_gated_delta_rule`

这是真实进入参考 Python 函数的观测，而非仅由序列形状猜测。若调用没有进入这些 code object，则如实保留缺证据，不自动宣称某个外部 kernel。上游 Qwen、generation、cache、kernel-dispatch 文件的 SHA 引用随运行保存。每条路径记录耗时和该路径实际 Torch allocated 峰值，NVML/RSS/总量由外部监督采样；观察 hooks/profiler 有额外开销，不将这些耗时当生产吞吐量。

## 为什么本次不做 cached-grad

已安装 Transformers 5.17.0 的 Qwen cache 在卷积与 recurrent 状态更新中使用 `copy_`/原地写；`GradientCheckpointingLayer.__call__` 在 train+checkpoint 下将 `use_cache` 关闭，对不能 checkpoint 写 cache 的层移除 `past_key_values`。直接将 cache 路径设为 train 并不证明它仍是同一缓存计算。

本次没有建立过去 LoRA 依赖完整保留的可微缓存实现，因此 cached-grad/backward 明确不执行；不会 detach 过去状态后声称训练目标不变。诊断 hidden 摘要的 detach 只作用于旁路观察副本，不是向模型回传的状态。

若 cache replay 本身不对应原 s，优先检查记录、位置、状态和重放约定；不能归因 DeltaNet。若 cache 达原门而 full 失败，则说明应聚焦已观测增量/完整执行差异；仍不能直接把责任归于单个模块或准入 cached training。

## 接口和 CPU 控制

```text
python -m scripts.numeric_paths_v021 --prior-run runs/domain-v0201-p1-9b --output <new-N-directory>
```

CLI 没有 GPU 选择、等待、重试或后继；输出目录必须新建，source 必须干净，统一监督负责授权设备与资源。每条路径分别落盘，失败前已完成路径不丢失；不会据 N 结果启动或阻断其他实验。报告最终区分 `complete_diagnostic` 与数值门是否通过。

CPU 必要控制：`CUDA_VISIBLE_DEVICES='' .../resident-venv/bin/python -m pytest -q tests/test_numeric_paths_v021.py`，**1 passed in 4.20s**，三个相关文件 Ruff 通过。

控制使用随机小型官方混合 Qwen、真实 PEFT LoRA，在 CPU/FP32 建立小型原采样夹具。诊断过程中禁止调用 generate/multinomial；缓存重放与夹具原采样的 max logprob 差小于 `1e-5`。真实 profiler 观察到 3 层 prefill 的 conv_fn/chunk，5 次 decode×3 层的 conv_update/recurrent；full 路径只出现 chunk。full_grad 的 train、requires_grad 与非重入 checkpoint flags 实际成立，参数 hash 不变，所有参数 grad 仍为空。缓存实际状态在当前安装版使用字典，控制已覆盖其结构。

这仅确认接口与观测机制，不代替 9B/BF16 实际 N 结果、单卡 grad 图容量或任何反向资格。未更改候选运行时、旧 profile、原概率门或旧失败文件。
