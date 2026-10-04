# v0.31 密集模型的完整可微缓存重算

v0.30-r1的SWE-Next-14B和Devstral分别在一条真实trace上未通过原行为logprob重算门。采样使用完整prefix预填充及逐token缓存解码，学习重算使用整序列一次forward。BF16下，这两种形状和归约路径可能产生不同结果；这是当前待GPU对照检验的解释，不能在实测前断言某个GEMM、attention或normalization算子就是唯一原因。

修订保留官方权重、BF16主干、FP32 LoRA和输出头、原高效SDPA、temperature=0.7、原EOS、16,384上下文及2,048输出上限。误差门仍为max absolute delta≤0.02、mean absolute delta≤0.002，不重写保存的行为概率，不裁剪原输入或输出目标。

## 计算对象

给定实际prefix P和原采样输出 y₁…yₘ，先计算完整预填充状态S₀，再依次以y₁…yₘ₋₁作为解码输入；每个原输出包括EOS都作为一次预测目标。最后一个目标无需再作为额外输入，这与原自回归采样依赖一致，不是删去最后目标。

梯度必须经过prefix及所有先前KV状态：Sₜ取决于Sₜ₋₁和同一组LoRA参数。把过去缓存detach后再重算当前logprob，即使forward值相同，也不等于完整的条件概率梯度。新[functional_dense_v031.py](../../src/proworksim/functional_dense_v031.py)用纯tensor状态和`torch.cat`返回新KV；每次attention内部的临时容器只活在一次转换内，不让可变HF缓存跨越checkpoint重放边界。

每层先完整处理prefix，再逐token处理后续原目标输入。外层checkpoint覆盖整层扫描；内层覆盖预填充、每8个单token转换及各目标输出头，均为non-reentrant checkpoint。仍直接使用已加载模型的attention、LoRA、norm、MLP和FP32输出头。这个结构为了减少保留激活，不构造新的奖励、优化器或训练算法；真实单卡峰值与耗时仍必须实测。

## 已有CPU证据

8项真实TinyTorch控制覆盖Qwen2及Mistral。原生缓存forward与新路径最大差值均为0；checkpoint与不使用checkpoint的完整可微参考图梯度最大差值均为0。刻意detach过去状态的反例forward保持相同，但梯度相对差异分别约0.87568、0.70143，且丢失了prefix对最后目标的梯度。方向有限差分、BF16主干加FP32 LoRA/head、所有12个目标含EOS保留等控制通过。

这些是小模型机制控制，不是两个实际预训练模型的数值或近16K训练资格。原件为`runs/v031-functional-dense-controls/summary.json`；模型级GPU验证另计。

## 两条真实旧trace的GPU对照

[probe_dense_replay_v031.py](../../scripts/probe_dense_replay_v031.py)固定使用SWE原第1条和Devstral原第3条失败trace。先用原v0.30 loader/profile构造owner，显式迁移软件坐标，再严格重载该模型旧common checkpoint；原actor身份必须与采样response完全一致。新v0.31原生提示不会被拿来重构这些旧输入。

同一权重、输入IDs、输出IDs和原行为logprob比较四条路径：

1. 原整序列no-grad重算，保留历史失败复现结果。
2. 安装库原生缓存no-grad teacher replay，不调用generate或采样。
3. 新纯tensor路径的no-grad重算。
4. 新路径在train/grad模式的重算与完整真实backward。

新数值准入只合取后3条对原行为的原误差门、全部原目标保留、真实有限非零LoRA梯度、原actor身份和最终共同状态完整恢复。第一条是比较对象，历史失败成功复现不会反而阻止新路径准入。所有路径的派生概率、梯度摘要和失败均保存，原trace文件不修改。

GPU对照不生成新token、不调用optimizer.step，也不使用软件开发案例作更新。只验证原失败trace的完整反向，不把这条较短输出当作近16K容量证明。正式新组合仍需重新生成预定4条原生资格trace，并通过完整概率/更新/重载/新身份回流/近16K容量门，才进入开发筛选。

## 版本与证据边界

新[CandidateActor](../../src/proworksim/candidate_runtime_v031.py)复用原权重加载及缓存采样实现，在SharedActor建立首次身份之前绑定v0.31原生协议和学习路径；不会先保存旧身份再改写。旧GPU对照有意使用旧完整profile，新采样使用新完整profile，两者明确分开。

SWE原生协议同时改为作者OpenHands XML变体，Devstral提示改为仅列实际提供的工具，见[原生协议依据](../research/software-native-protocol-v031.md)。因此新工作成绩属于新版运行组合，不能用来单独归因数值路径或模型参数量，更不是ID-VTDO分配收益。原v0.30及r1失败全部保留。
