# v0.20.1：唯一显式后继 P1 数值配置

日期：2026-09-27。v0.20 原尝试与 frozen `9e74e7b89fa4d855bbdfb73451f7c4ec2194d8f0` 保持原样。本文件记录一个新的执行配置，不重判原失败，也不声称已证明误差的主要来源。

## 原尝试与改动依据

`runs/domain-v020-p1-9b/numerical.json`（SHA256 `7f54f5259cc83a46f04c48a22dbf0c5c060b078610987fc65e11e5b5b17bc5c1`）记录首条实际 8473 输入、146 输出 token。真实原始与保留输出 ID/概率一致，但自身完整输入复算的 max/mean 绝对 logprob 差为 `0.16864824295043945 / 0.005917357799908498`，超过原 `0.02 / 0.002`；146 token 中 10 个超过 max 门。仅 1 次复算、0 反向、0 业务情境、0 更新。原 launch exit 2，耗时 `46.31456899642944` 秒，source 前后相同。

安装 Qwen `forward` 直接将 hidden states 交给 `lm_head`，不在 head 内升精度；原配置 head 权重和输出为 BF16。HF 生成循环及现有学习归约在取得 logits **之后**转 FP32；实测 sampling processor 收到的也是已转换 FP32 logits。这不能恢复先前 BF16 输出量化损失。因此提升输出投影精度是合理的单个诊断变量，但原记录未保留完整 logits/hidden states，尚不能确认其为主要误差来源。BF16 backbone/DeltaNet 的增量与整段执行差异仍可能存在。

## 新实现与不变项

新增 `candidate_runtime_v0201.py`，profile version 为 `candidate-runtime-v0.20.1`。v0.20 仅抽出默认不变的 profile、模型准备、storage 检查接口；旧 frozen 源不变，不据此将旧结果重新准入新源。

- 保留官方 BF16 加载路径，先验证全部原始冻结基座为 BF16、LoRA 为 FP32。
- 只允许 untied、无 bias、无 buffer 的原始 `torch.nn.Linear` LM head，参数身份必须明确，遇到其他 head 结构即拒绝。
- 将该冻结 head 权重真实转 FP32；在 head 乘法前将输入转 FP32，输出检查必须 FP32。这不是输出后 `.float()`。
- 逐项记录 BF16 backbone、FP32 head、FP32 LoRA 的实际参数个数、元素数、字节数、设备、布局 SHA；head buffer 列表实际为空。实际 head 调用数、原始输入 dtype、计算输入及输出 dtype 随真实采样响应保存；完整复算和梯度前向诊断另存实际计数及归约 dtype。
- 归约、LoRA、critic、FP32 matmul `highest`、BF16 full-attention QKV、efficient-only 后端、单实例、无 prefix、原 token、原 `.02/.002` 门均不变。

官方 9B checkpoint safetensors 头确认 LM head 原存 BF16，shape 为 `[248320,4096]`，与 embedding 不绑定。上转精确保留这些已存 BF16 数值，额外 head 参数存储为 `2034237440 bytes = 1.89453125 GiB`。这不包括转换短时峰值、激活、缓存、梯度或分配器；不保证 40 GiB 进程门或概率门通过。

## 显式选择及累计预算

```python
plan = build_plan(
    model, manifest, inventory,
    execution_profile="v0.20.1",
    prior_attempt_ref=ref("runs/domain-v020-p1-9b/launch.json"),
)
```

默认原配置用 `execution_profile="v0.20"`；仅允许这两种声明，不依据实际结果自动切换。新配置必须引用已经闭合、源不变、0 工作/0 更新、因数值门停止的原 v0.20 运行。`remaining_gpu_seconds` 从实际旧 launch elapsed 派生为 `3553.6854310035706`，不接受增加为 3600；监督以剩余额度执行，输出资源合并原尝试产物字节数，结束记录累计设备秒。仍保留每任务 900 秒、单卡 A100、自身显存观察上限 40 GiB、RSS 64 GiB、总产物 5 GiB、模型 API 0，不部署 P2、重试或其他后继。

## CPU 控制结果与边界

命令（GPU 全部隐藏）：

```text
CUDA_VISIBLE_DEVICES='' PYTHONPATH=src runs/v016-sdk/resident-venv/bin/python -m pytest -q tests/test_candidate_runtime_v020.py tests/test_candidate_runtime_v0201.py tests/test_p1_v020.py
```

**17 passed in 4.60s**，相关六个源码/测试文件 Ruff 通过。这 17 项包含原 dtype 及监督控制，不能按新独立实验样本累计。

新增核心控制包括：随机官方小 Qwen 构造时只将 head 升到 FP32，权重值逐位等于原 BF16 的 FP32 表示，embedding 仍 BF16；只执行其 head 的 CPU 前向并核查输入/输出 dtype，未执行官方混合 backbone 前向。另一个随机真实 PEFT 小语言模型执行 5 个采样 token、完整输入复算及有限非零 FP32 adapter 梯度，原概率门通过、head 无梯度、优化器无状态/0 更新。head 执行 hook 移除或 tied 条件会被拒绝。协议控制拒绝缺旧运行引用、手增剩余额度或第三种配置，并确认四个工作情境与三条原请求不变。

这些是实现控制，不是 9B 的实际候选数值准入或训练容量证明。所有 GPU 运行由 root 在新的 clean source、独立计划和新输出目录冻结后另行启动；本实现阶段未执行 GPU/候选模型/API。
