# v0.19 DeltaNet 快速路径只读核对

核对日期：2026-09-27。结论是：**当前完整 FP32/highest 路线没有一个已经安装、可以直接打开并保持原数值合同的 FLA prefill 快速开关。优先验证保留现算子的前缀缓存；FP32 causal-conv1d 虽是技术上范围最窄的 kernel 候选，但随后取得的本机 profiler 显示卷积份额很小，本轮不安装。FP32 recurrent fusion 仅保留为未来单独推理候选。**本次只读子任务未安装包、编译 kernel、创建模型或启动 GPU 工作，未修改正在运行的 H1 环境；下面另列根代理实际运行的本机 profiler 证据，不能把二者混称为本子任务的 kernel 实测。

## 当前服务器和实际 dispatch

只读 package metadata 得到：Python 3.12.3；Transformers 5.17.0；torch 2.6.0+cu124；Triton 3.2.0。`flash-linear-attention`、`fla-core`、`causal-conv1d`、`kernels`、`flash-attn` 均未安装，对应 `fla` / `causal_conv1d` / `kernels` 模块也未找到。隐藏 CUDA 后只导入 torch 读取编译元数据，确认 CUDA 12.4、`_GLIBCXX_USE_CXX11_ABI=False`，`torch.cuda.is_initialized()` 为 false。`nvidia-smi` 只读查询显示八卡均为 A100-SXM4-80GB，compute capability 8.0。

候选 runtime 明确使用 float32、`torch.set_float32_matmul_precision('highest')`、cuDNN TF32=false、SDPA、`use_kernels=False`。本机 `modeling_qwen3_5.py` 的 DeltaNet 不是一个简单的统一 `is_fast_path_available` 开关，而是分别装饰四个 helper：causal convolution prefill/update、chunk gated delta rule、fused recurrent gated delta rule。有先前状态且本次 seq_len=1 时进入 recurrent；长输入及多 token suffix 进入 chunk。卷积的单 token cached 路径还受 `record_past` 控制。

本机 `hub_kernels.py` 的分派优先级为：显式请求的 Hub kernel → 能导入的原包实现 → PyTorch reference。因此，**`use_kernels=False` 只排除 Hub 替换，不阻止新增原包在导入时自动替换 helper**。直接往共享 resident 环境安装 FLA/causal-conv1d 会改变后续新进程的有效实现，不能当作与旧源完全相同的运行。当前原包和 Hub loader 均不可用，四个 helper 使用 reference 路径。

安装源码的精确 SHA256：

| 文件（resident-venv 的 site-packages 下） | SHA256 |
|---|---|
| `transformers/models/qwen3_5/modeling_qwen3_5.py` | `762feb6c7426a7f15b5bf830df54c07438bf9e7c27b8cdb23179045920412c3b` |
| `transformers/integrations/hub_kernels.py` | `c1eafefe0cbdf7f0deaa21b1ef6cb6d7c6082b3f486651d069ff38fcf3e53c95` |
| `triton/language/core.py` | `6bd038079b94067d628eea9264530fec03d4d7027ff834e89b9d6fbc31ae8bd9` |

## 各快速路径的精度与依赖边界

| 路径 | 已核实事实 | 当前判断 |
|---|---|---|
| 原 PyTorch reference + 输入前缀复用 | 不需要新增 kernel 包；必须同时保留 attention KV、卷积状态、recurrent state 和准确位置/输入身份 | 最少改变数值实现的首选实验；实际 token/logp 与时间由独立固定请求控制决定 |
| causal-conv1d | 官方声明支持 FP32/FP16/BF16；C++ prefill/update 都接受 Float，卷积 width 限 2–4；FP32输入和权重不需要强制降为 BF16 | 适合另环境的小范围候选，收益尚未测；需核对实际 layout、状态更新、logp 与反向路径 |
| FLA chunk prefill | 固定官方源在 Ampere+ 明确选择 TF32 solve-tril，另外存在默认 `tl.dot` | 即使输入/输出 dtype 是 float32，也不满足当前 strict highest 的无降精度前提；不能直接启用 |
| FLA fused recurrent | 固定源加载 q/k/v/state 后内部转 FP32，以 FP32 状态累积；输出随输入 dtype，final state 是 FP32；其 backward 明确未实现 | 存在 FP32 推理解码候选，不是只支持低精度；不直接替换可微训练路径，数值与收益仍须实测 |
| Hub `kernels` | 是加载/分派机制，不是 dtype 保证；本机未安装且候选 runtime 显式禁用 | 不能凭安装 loader 宣称获得 FP32 安全 fast path；本次未证明对应 Hub build 的 ABI 或数值合同 |

卷积结论对应 [causal-conv1d 官方 README](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/README.md) 与 [实际 C++ dtype/shape 检查](https://github.com/Dao-AILab/causal-conv1d/blob/cd81f0413cad2fc1e6f17e785ac39f59aae690cd/csrc/causal_conv1d.cpp)。接受 Float 不证明与 PyTorch reference 逐位相同，融合、累加顺序和激活实现仍需按冻结概率合同检查。

FLA 核对固定到官方提交 `1837094334042434776f3b302f5131ac8ad9f575`（2026-09-27 00:55:09 UTC），不是从未固定的教程推断。其 [chunk_fwd.py](https://github.com/fla-org/flash-linear-attention/blob/1837094334042434776f3b302f5131ac8ad9f575/fla/ops/gated_delta_rule/chunk_fwd.py) 使用显式 `SOLVE_TRIL_DOT_PRECISION='tf32'`；[硬件判断](https://github.com/fla-org/flash-linear-attention/blob/1837094334042434776f3b302f5131ac8ad9f575/fla/utils/_device.py) 的条件是 NVIDIA compute capability≥8，没有读取 torch highest 设置。本机 A100 满足此条件。仅设 `TRITON_F32_DEFAULT=ieee` 也不会覆盖显式传入的 solve-tril 精度。

[Triton 官方 dot 文档](https://triton-lang.org/main/python-api/generated/triton.language.dot.html)声明 NVIDIA FP32 dot 默认使用 TF32，本机 Triton 3.2.0 的 `language/core.py` 和 `backends/nvidia/compiler.py` 也直接证实这一点。保留张量 dtype、保留 PyTorch highest 设置和保留 Triton 内部 IEEE FP32 计算是三件不同的事。这里没有断言所有旧版 FLA 或所有可能定制 kernel 都拒绝 FP32；结论只针对实际核对的默认路径。

FLA [fused_recurrent.py](https://github.com/fla-org/flash-linear-attention/blob/1837094334042434776f3b302f5131ac8ad9f575/fla/ops/gated_delta_rule/fused_recurrent.py) 没有要求将 QKV 转为半精度，但它是没有 backward 的融合递推。DeltaNet 权重冻结不意味着训练时可以切断穿过该层、通向更早 LoRA 的输入梯度。因此推理专用替换和可微概率重算应分开，不能从推理成功推导训练兼容；即使同为 FP32，也须重新确认输出状态、真实 token 概率和固定门限。

## 包兼容性与服务器缓存

固定 FLA 源的 [pyproject.toml](https://github.com/fla-org/flash-linear-attention/blob/1837094334042434776f3b302f5131ac8ad9f575/pyproject.toml) 中 CUDA extra 要求 torch≥2.7、Triton≥3.3；当前环境为 2.6/3.2。其基础包现在不自动携带 torch/triton，这并不认证老环境兼容。未在当前环境导入或执行 FLA，更没有为了 fast path 升级已运行环境。

causal-conv1d 官方 [v1.7.0 发布](https://github.com/Dao-AILab/causal-conv1d/releases/tag/v1.7.0) 的 API 元数据列有与当前 Python/Torch/CUDA major/ABI 标签相符的 wheel：

- `causal_conv1d-1.7.0+cu12torch2.6cxx11abiFALSE-cp312-cp312-linux_x86_64.whl`
- 大小 196,306,803 bytes；发布方 SHA256：`5a76a78af8b600dac20cfc017bb45b7b650d27322f1d8f9250b28e51f6bf9ea9`。
- [官方 wheel 地址](https://github.com/Dao-AILab/causal-conv1d/releases/download/v1.7.0/causal_conv1d-1.7.0%2Bcu12torch2.6cxx11abiFALSE-cp312-cp312-linux_x86_64.whl)。本次只读元数据，未下载约 196 MB 的 wheel，也未证明本机可成功加载。

在用户拥有的 `/home/zhuxinrui/.cache`、`/data1/zhuxinrui/.cache`、`/data1/zhuxinrui/cache`、Miniconda package cache，以及已知 Miniconda env / 本项目 runs 内虚拟环境的有界搜索中，没有发现可直接复用的 FLA、causal-conv1d 或 kernels 安装/具名 wheel。未扫描全服务器所有用户，pip 按内容散列的 HTTP 缓存也不能据此宣布不存在相同源码。较早一次 `/tmp` 广搜遇到其他用户权限拒绝，未据此作不存在判断；未读取这些目录内容。

官方源码文本及获取时的提交/文件哈希保存在本机 `/tmp/proworksim-v019-kernel-readonly/`，仅作只读核对素材。Hub FLA model-tree API 返回 401，未用凭据重试，因此没有对其具体发布二进制或内嵌 FLA 提交作兼容性结论。Hub kernel card 仅证明它[提供 chunk/recurrent 功能入口](https://huggingface.co/kernels/kernels-community/fla)，不提供本机 strict-FP32 准入证据。

## 同轮实际原请求 profiler 的优先级修正

根代理另行完成 9B 固定原请求控制；本文件只读核对其 `runs/v019-throughput-probe/original9b/profile.json`。实际请求为 8,444 输入 token、64 个新生成诊断 token，HTTP200；不是原业务轨迹重演或工作评分。文件 SHA256 为 `eb94226693501ad0d2cab284f28a3083bfe9e4e77de39b4d27cf6ec0b3873561`。

为避免同时累计 ATen 父事件和 CUDA 子 kernel 而重复计时，以下分母仅取所有 `aten::` 事件的 `self_device_us`，合计 9,960,835.184 微秒：

| 操作 | self device 微秒 | ATen self device 份额 |
|---|---:|---:|
| `aten::mm` | 7,553,754.936 | 75.83455% |
| `aten::bmm` | 966,639.357 | 9.70440% |
| `aten::_conv_depthwise2d` | 36,346.714 | 0.36490% |

这表明本请求的主要归属时间在矩阵乘，而不在卷积。即使只在这份归属时间模型内假设把 depthwise 计算成本完全消去，其约 0.365% 份额也只能给出很小变化；此推断不是整条墙钟的严格上界，因为没有估计关联 CPU/launch 开销。**据此本轮不下载或安装 causal-conv1d，不把包易装当作值得优先部署的证据。**

profile 本身声明存在 profiler overhead，不应把上述 9.96 秒当作正常吞吐，也不能把一次 64-token 诊断外推到所有长输出、27B、反向训练或不同共享 GPU 竞争。前缀缓存能省去多少计算由实际可重复前缀和计时决定，不从省去输入 token 的比例推导数倍加速。

对矩阵乘另测 `high` 若被采用，只能作为独立数值诊断：它改变了当前 `highest` 路线，不能声称保持原精度或自动准入。必须保留固定原请求与选中输出、检查原 logprob 绝对误差门（最大 0.02、平均 0.002）及需要的真实可微路径，失败不得放宽门限。这里未取得该诊断结果，也没有修改或重启 H1。

## 有界后续建议

先完成同一实际原请求上的 uncached/cached 对照，分别报告首次 prefill、重复前缀计算、decode、缓存字节与复用长度，同时核对输入 token、adapter 身份、采样状态和选中输出概率。只复用同一有效参数及同一精确输入前缀；不能把 KV 复用等同于更新后仍有效，也不能忽略混合架构的卷积/recurrent 状态。共享 GPU 的同时占用另列，不能仅凭一条墙钟时间断言固有吞吐收益。

如果其他代表性请求显示卷积占比明显上升，才考虑在独立冻结环境核对 causal-conv1d；保留 FLA chunk reference，先验证 FP32输出、状态、概率以及需要时的输入梯度。单 token recurrent fusion 也应有可量化瓶颈依据，并明确仅推理或提供已验证的独立可微路径。本轮不提出静默降低 dtype/TF32、批量更换依赖或替换所有 DeltaNet helper；任何新核的正收益和失败都须由实际控制给出，不能引用上游 H100/GB200 基准推算本项目速度。
