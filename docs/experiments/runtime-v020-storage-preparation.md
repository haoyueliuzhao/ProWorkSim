# v0.20 低存储共享模型：CPU 实现准备

日期：2026-09-27。此记录仅说明新数值路径与 CPU 控制；不重判旧 H1/v0.19，不证明 9B/27B 的 GPU 容量、学习收益或候选准入。没有加载候选权重、执行 GPU 前向或调用模型 API。

## 配置与接口

新增 `src/proworksim/candidate_runtime_v020.py`，沿用既有 SharedActor 和 v0.17 原生工具解析；未修改 v0.15/15.1/17/19 loader、概率容差或公共学习实现。

```python
from proworksim.candidate_runtime_v020 import CandidateActor, candidate_profile
profile = candidate_profile("qwen3.5-9b", dtype="bfloat16", devices=1)
owner = CandidateActor.from_candidate(
    model_path, manifest=weight_manifest, profile=profile, output=resident_directory,
    recipe={"max_length": 16384, "max_output_tokens": 2048,
            "max_rss_bytes": 64 * 1024**3},
)
```

这只是未来获准执行时的接口，不是本记录已运行的命令。资源监督、任务时间及累计设备预算由外层 P1 控制。profile 的设备数表示同一实例分片设备数；单 resident 不在理论上等同单 GPU。本轮 root 另行冻结 9B、一个 GPU 的具体准入条件。

| 部分 | 新声明及执行约束 |
|---|---|
| 冻结文本基座 | 官方 `from_pretrained(dtype=torch.bfloat16)` 直接创建低存储权重；逐参数验证真实 BF16、无梯度；不是 autocast 降存储 |
| LoRA | q/v、r8、alpha16、dropout0，PEFT 将 LoRA 权重保持 FP32；逐参数验证真实 FP32、可训练；输入显式转 LoRA 参数 dtype，增量合入后返回基座投影 BF16 |
| Full attention | 新注册 `sdpa_bf16_explicit_kv_v020`；Q/K/V 每次调用必须 BF16，复用 explicit-KV efficient-only CUDA SDPA；沿用 SDPA mask 注册；不支持则报错，无 Math/CPU/其他精度 fallback |
| 其余官方数值路径 | 保留 DeltaNet、RMSNorm、rotary 的官方 FP32 中间运算；不宣称整个网络仅执行 BF16 运算 |
| FP32 matmul | `highest`，cuDNN TF32 关闭；不沿用 v0.19 的 `high` |
| 实际抽样概率 | 传给实际 generator 的唯一 processor 在温度与 log-softmax 前将 scores 转 FP32，返回相同 FP32 scores 供抽样；已有 FP32 scores 再 `.float()` 不改值 |
| 可微复算 | 原始完整 input/output IDs；既有 selected_logprobs 显式 FP32 温度与 log-softmax；新路径检查返回 dtype |
| critic | FP32 参数，独立优化器，属于同一个共享 learner |
| 缓存与实例 | 仅单次 generate 的正常 KV；无 prefix-cache，禁止 readonly replica snapshot；同一 owner 顺序服务各角色 |
| 概率准入 | max 0.02、mean 0.002，保持原值；新配置只与自身真实行为概率比较，不要求重现旧 FP32 输出 |

`owner.inference_profile` 包含完整新声明以及实际基座/adapter tensor 数、元素数、字节数、设备、参数布局 SHA 和 buffer dtype 汇总。buffer 与官方内部 FP32 中间状态单列，参数字节数不包括 cache、激活、梯度、优化器、分配器开销。实际抽样响应另记录 processor 收到的 score dtype、FP32 归约次数与单 resident 声明。QKV 与归约约束只在实际调用时得到检验；配置文件存在不等同候选已经执行成功。

构造及执行拒绝 ambient autocast、错误实际权重精度、非 LoRA 可训练参数、非最高 FP32 matmul、变更 attention 或参数布局。正式 CUDA loader 要求原生 BF16 支持，不允许 CPU/磁盘 offload。CPU 构造仅用于明确标记的小模型控制，生产 attention 调用拒绝 CPU。

## 必要 CPU 验证

命令：

```text
CUDA_VISIBLE_DEVICES='' PYTHONPATH=src runs/v016-sdk/resident-venv/bin/python -m pytest -q tests/test_candidate_runtime_v020.py
```

结果：**3 passed in 4.11s**。

1. profile 声明单 resident、无 prefix、副本为零、原概率门；错误 profile 在 loader 前被拒。
2. 随机四层小 Qwen 经官方本地 save/load 路径按 BF16 加载，真实 PEFT LoRA 为 FP32；基座存储为每元素 2 bytes，adapter 为每元素 4 bytes；完整 factory 字段进入 owner；attention 与 mask 注册正确。此控制只构造，未运行 Qwen 前向。错误 FP32 QKV 及 CPU attention 调用均被明确拒绝。
3. 无 attention 的随机小语言模型使用真实 PEFT q/v LoRA；CPU BF16 基座输出进入 FP32 sampling processor，5 个实际输出 token 在完整原输入上复算，原 .02/.002 概率门通过；实际反向的 adapter 梯度 FP32、有限且非零，基座无梯度，actor/critic 更新计数均 0，优化器 state 仍为空。此控制不验证 CUDA SDPA 或长序列容量。

定向 Ruff：`src/proworksim/candidate_runtime_v020.py tests/test_candidate_runtime_v020.py`，通过。未运行全库或重复旧控制。

## 已安装上游依据与未完成项

依赖研究以 resident 环境实际代码为依据：Transformers 5.17.0、PEFT 0.18.1、Torch 2.6。相对目录为 `runs/v016-sdk/resident-venv/lib/python3.12/site-packages/`：

- `peft/tuners/lora/layer.py`：输入按 LoRA 权重 dtype 转换，增量相加后回到原投影 dtype；SHA256 `e8a47a49cf69f92ded68bf7ab286aeaf068f0ac809ab3465ad16f78a8f9f8b63`。
- `peft/tuners/tuners_utils.py` 的 `cast_adapter_dtype`：默认将 BF16/FP16 adapter 升到 FP32；本实现仍检查实际 tensor，不仅信任默认值。
- `transformers/models/qwen3_5/modeling_qwen3_5.py`：官方混合结构、FP32 归约及 full attention 接口；SHA256 `762feb6c7426a7f15b5bf830df54c07438bf9e7c27b8cdb23179045920412c3b`。
- `transformers/generation/utils.py`：官方生成循环；SHA256 `bb558d8676be95457126c82a32600dad206c13e4fb96b4f5d114f1f2483d7f62`。

后续若执行获准 P1，仍须记录真实基座/adapter dtype、实际采样与 full-input 重算概率、实际反向、真实显存/RSS/时间，以及工作能力证据。成功的 CPU 控制不会自动准入候选、证明一个 GPU 可训练，或授权 P2。新 BF16 配置改变数值路径，不是旧 FP32 实验的无影响勘误。

## P1 监督与停止边界的 CPU 检查

随后对 `scripts/p1_v020.py` 完成一次窄范围实现复核，新增 `tests/test_p1_v020.py`。最终定向运行 **11 passed in 1.50s**，同两文件 Ruff 通过；子进程、GPU 查询、时钟及资源超限全部使用明确 CPU fixture，没有真实启动进程或模型。

修订包括：固定绑定冻结 `examples/throughput-v19/probe-inventory.json` 的三条 9B 请求；计划单独写明一个 resident、零 sampling replica；CUDA 环境必须恰为允许的一个物理编号，候选卡须为 A100；数值门失败不调用业务收集或后继；raw/retained 输出 ID 与行为概率必须一致；资源查询失败或自身显存值不可解析不按零用量继续；监督异常与超限均只对本监督器通过 `start_new_session=True` 启动的子进程组发送 SIGTERM，最多等待 5 秒后升级 SIGKILL，已退出进程不再发信号。

CPU 控制逐项覆盖总 GPU 分配时间 3600 秒、单任务 900 秒、RSS 64 GiB、输出 5 GiB、自身 GPU 进程占用 40 GiB 与资源查询失败。启动空闲阈值为 40 GiB，设备依次 2、3、4、5、6；无合格卡时不创建运行目录或进程。监督按 2 秒间隔加查询耗时采样，这是一条观测后终止边界，不是 GPU 分配器硬上限，短时峰值可能发生于采样之间。单次启动无自动重试或后继；本记录不承诺重复人工启动共享全局配额账本。

数值诊断采用明确的诊断闭合，记录真实 learner-forward 尝试、backward 尝试与完成数，不调用会声明“未做学习前向”的 `finish_evaluation`。若第一次模型调用失败，计数全部为零，不能写成反向已完成；随后四个真实工作窗口若获准实际执行，则仍为独立的零更新评价窗口。所有采样预算、四个预定情境、native harness、原概率容差均未改变。
