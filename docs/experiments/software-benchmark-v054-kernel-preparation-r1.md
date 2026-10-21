# v054 原生生成 kernel 优化准备与算子准入 r1

记录日期：2026-10-21，Asia/Shanghai。本文记录依赖准备及截至 20:19 算子准入回执的结果。后续完整模型诊断和部署应另记版本，不能用本记录证明它们已经完成。

## 结果与适用范围

独立环境中的 FLA 0.4.2 两个 gated-delta-rule 算子已经通过预先固定的四个合成输入控制：短序列实际宽度 prefill、长序列 head 切片 prefill、实际宽度单步 decode、实际宽度四步 decode。**4/4 指四个 delta 控制场景，不是原计划中四个函数全部通过。** `causal_conv1d_fn`、`causal_conv1d_update` 尚未准入，保持参考实现；其依赖准备是独立候选，不阻塞这两个 delta 算子的下一阶段诊断。

本阶段没有加载完整 9B 模型，没有模型生成请求、正式任务或官方评分调用，没有改变正在运行的 resident 或正式配置。算子结果支持继续评估这个明确版本的优化候选；不能据此宣称完整模型已加速、模型输出等价或正式流水线已上线。

长序列切片的稳态中位数从 59.973 ms 降至 3.137 ms，观测比值约 19.12。但它只覆盖 `16384 × 2 heads`，实际模型的相关宽度为 32 value heads；共享 GPU 干扰没有被隔离，计时含 Python 调度和状态复制。**这一比值不能外推为完整 9B、单回合或整条评测流水线的加速比。** 短 prefill 和 decode 的观测差异明显较小，详见下表。

## 选择的依赖与原环境

保持原 Python 3.12.3、Torch 2.6.0+cu124、CUDA 12.4、Triton 3.2.0 和 Transformers 5.17.0，不原地升级现有环境。在独立 overlay 中安装固定的 `fla-core==0.4.2`、`flash-linear-attention==0.4.2`、`einops==0.8.2`。

依赖准备时记录的官方来源表明：FLA 0.4.2 的 Triton 推荐下界与当前 3.2.0 相容；当时核对的较新 0.5.2 CUDA extra 要求 Torch ≥2.7、Triton ≥3.3，因此未选用。此处明确采用兼容旧基础环境的 0.4.2，**不称所选包为最新版**。包自己的 `METADATA` 与源码中的推荐条件并非同一个字段，归档同时保留两者的来源，避免把推荐条件误写成安装器强制依赖。[FLA 0.4.2 utils](https://raw.githubusercontent.com/fla-org/flash-linear-attention/v0.4.2/fla/utils.py)、[FLA 0.4.2 pyproject](https://raw.githubusercontent.com/fla-org/flash-linear-attention/v0.4.2/pyproject.toml)、[FLA 0.5.2 pyproject](https://raw.githubusercontent.com/fla-org/flash-linear-attention/v0.5.2/pyproject.toml)。

两个 FLA wheel 通过清华 TUNA 直接 HTTPS 下载，合计 794,900 B；einops 复用本地 65,638 B wheel。另下载 causal-conv1d 1.7.0 源码 30,328 B，因此三项新包资产下载合计 825,228 B。这些数值是已记录包文件字节，不包含目录元数据、请求开销或编译器探测流量；不把它们冒称整个准备过程的网络总量。没有代理或原站资产回退，原虚拟环境未修改。

overlay 清单冻结了 402 个文件、3,446,074 B，SHA256 为 `786df9ea121c95828d7b755777b285a7238666db9c37ad211682e8c5abd71eeb`。后续因果卷积编译或任何包增删都必须形成独立 overlay 修订，不能改写这个清单后继续使用旧准入。

优化绑定通过 Transformers 当前实际装饰器的 closure 识别，不仅检查“模块能够 import”：

| 原入口 | 实际选中实现 |
| --- | --- |
| `torch_chunk_gated_delta_rule` | `fla.ops.gated_delta_rule.chunk.chunk_gated_delta_rule` |
| `torch_recurrent_gated_delta_rule` | `fla.ops.gated_delta_rule.fused_recurrent.fused_recurrent_gated_delta_rule` |

使用 `USE_HUB_KERNELS=NO`、`FLA_DISABLE_TENSOR_CACHE=1`、`TRITON_LIBCUDA_PATH=/opt/host-nvidia`，禁网络自动获取和运行时字节码写入，使用独立 Triton cache。显式禁用 tensor cache 避免把输入复用缓存混成算子性能收益。最终回执记录优化函数模块、限定名、源文件 SHA、实际可接受参数以及原始参考函数的 SHA。

## 事前控制方案与资源边界

固定计划 `plan.json` 于 19:33 写入，seed 为 `202610210641`。所有输入由固定 CPU RNG 生成，batch=1，输入/输出 bfloat16，循环 state float32，key/value dimension 均为 128，key-head repeat=2，启用 Q/K L2 normalization。短序列使用 128 tokens、32 value heads；长序列仅使用 16,384 tokens、2 value heads，以服从本次诊断资源上限。单步和四步 decode 均为实际 32-head 宽度。

decode 两侧从同一参考短 prefill state 开始；四步链中每一侧逐步承接自己的 state。这样既有共同起点，也检查有限步数的状态递推，不声称覆盖长对话累计漂移。

误差门在运行前固定：输出和 state 的形状、dtype 一致且全部有限；归一化 RMSE ≤0.015625，归一化最大绝对误差 ≤0.03125，归一化分母下限为 1e-6。它们分别对应 2、4 个 BF16 epsilon 的工程门，不是理论误差界，也不保证 logits、采样或任务结果相同。CPU 六项控制检查相同输入通过、dtype 变化拒绝、非有限值拒绝、大误差拒绝、小 BF16 差异按门通过，以及卷积 state 要求逐位相同；全部通过。卷积 state 控制属于判定函数控制，不代表卷积 GPU 实现已验证。

GPU 控制在物理 GPU5 的独立受限进程执行，没有停止其他用户进程或改动正式 GPU3/6/7 resident。启动观测 GPU5 剩余 15,053 MiB；准入要求至少 3,072 MiB。计划限制 Torch allocator 1 GiB、本进程总 GPU 占用 2,048 MiB、CPU 2 线程、900 秒期限，宿主约每秒监控一次。成功运行宿主观察峰值 1,070 MiB，Torch peak allocated 为 386,859,008 B、peak reserved 为 591,396,864 B；这些是不同口径，不能互相替代。约秒级宿主采样不是连续精确峰值测量。成功启动到结束总计 120.906 秒。

计时每实现先单独记录首次调用，再各 warmup 两次、稳态五次；基线/优化调用顺序交替反转，每次前后 CUDA synchronize。首次调用包括 JIT 编译，单独列出，不计入稳态中位数。共享 GPU 上其他工作未受控，因此下表是这次观测值，不是隔离性能认证。

## 四个 delta 场景的结果

| 控制场景 | 参考稳态中位数 ms | FLA 稳态中位数 ms | 参考/FLA | FLA 首次调用 ms（含编译） | 误差门 |
| --- | ---: | ---: | ---: | ---: | --- |
| 128 tokens、32 heads prefill | 3.018 | 2.493 | 1.210 | 61,388.870 | 通过 |
| 16,384 tokens、2 heads prefill 切片 | 59.973 | 3.137 | 19.117 | 47,657.218 | 通过 |
| 32 heads、单步 decode | 2.541 | 2.435 | 1.044 | 566.850 | 通过 |
| 32 heads、四步 decode 链 | 2.878 | 2.459 | 1.170 | 2.452 | 通过 |

四步链计时是四步整体，不应再当作每步延迟。初次约 61.4 秒、47.7 秒的 JIT 成本不能隐藏；后续完整模型形状可能引入新的编译成本。本次未验证全宽 16,384-token 的容量和执行耗时。

| 场景 | 输出归一化 RMSE | 输出归一化最大绝对误差 | state 归一化 RMSE | state 归一化最大绝对误差 |
| --- | ---: | ---: | ---: | ---: |
| 短 prefill | 0.00453248 | 0.00714286 | 0.00330852 | 0.00501699 |
| 长 prefill 切片 | 0.00468950 | 0.00602410 | 0.00334789 | 0.00439672 |
| 单步 decode | 1.73700e-7 | 1.98488e-6 | 6.24316e-8 | 1.37123e-7 |
| 四步 decode | 4.45133e-8 | 1.19677e-6 | 1.30990e-7 | 2.78966e-7 |

所有输出/state 均有限、形状和 dtype 相同，但并非逐位相同。这一点必须保留；不能把通过误差门称为精确复现原数值路径。

## 启动异常与未完成候选

原始失败回执保留，没有删除或把失败记录改为通过：

1. `delta-r1` 在 wrapper 不具备可执行权限时失败；未启动 GPU 进程、未调用算子。后改为显式 `/bin/bash` 调用既有 wrapper，没有 chmod 或修改冻结 wrapper。
2. `delta-r2` 启动后未找到实际优化实现，绑定门报错；没有完成任何优化算子控制，不能记作通过。宿主运行 5.749 秒、观测占用峰值 416 MiB。后续显式指定既有 REF namespace 内的 libcuda 路径并增加 Triton 启动诊断，数值计划、seed、误差门不变。
3. `delta-r3` 完成全部四场景，退出码 0。`execution-seal-delta-r3.json` 关联最终检查器和 launcher，`admission.json` 才记录两个 delta 符号准入。

此前下载的 causal-conv1d 1.7.0 源码不是可用 GPU 扩展。编译器候选曾出现国内路径 404 或未批准重定向；后续华为精确地址 HEAD 返回 200，但 HEAD 成功不代表完整包已下载、编译器可用或扩展已通过。对 TUNA 的 `nvidia-cuda-nvcc-cu12` wheel 仅做 65,536 B Range 目录检查，记录找到 `ptxas`、未找到 nvcc driver，未把该 wheel 冒认为完整编译工具链。归档时 `conv-preparation-r1/` 为空，因此两项卷积优化仍为未准入。它们需要独立后续候选与记录。

## 完整模型与正式部署的边界

本记录包含的 GPU 工作只执行合成算子输入，无完整模型加载；`model_loads=0`、`model_requests=0`、`official_scoring_calls=0`。本归档和文档整理没有追加任何算子或 GPU 重测。

进入完整模型诊断前，仍需固定新模型运行环境、实际绑定门、与当前正式资源相容的容量边界，以及不使用正式成绩调参的比较输入。正式部署则还需独立运行修订与自然任务边界接管，保留原槽身份、seed、生成账本和既有结果，不中断或重跑已进入的回合。新 kernel 的计算次序可能改变浮点和采样结果；即使完整诊断通过，也应按 runtime 修订分层报告，不能把不同实现混称完全相同数值配置。

这些是后续准入要求，不是本文声称已执行的工作。截至本文的算子证据截止点，完整 9B 诊断、正式部署和端到端吞吐收益均尚未取得证据。

## 证据位置与复核范围

必要小文件归档于 [`artifacts/software-benchmark-v054/kernel-optimization-r1/`](../../artifacts/software-benchmark-v054/kernel-optimization-r1/)：

- `operator-control/`：固定计划、CPU 回执及控制脚本、各版检查器/launcher、执行 seal、三次尝试的原始小回执/日志、最终算子准入。
- `dependencies/`：完整 overlay 文件清单、固定包下载回执、已存镜像元数据与编译器探测、所选包 METADATA、官方源码引用及卷积状态快照。
- `archive-manifest.json`：每个原始副本的源路径、归档路径、SHA256 和大小。回执中的原绝对路径保持不变，通过归档清单映射到永久副本；未改写原始证据。

没有复制包 overlay 本体、wheel/源码大资产、Triton 编译 cache、模型权重、评测题目、参考补丁、隐藏测试或评分材料。整理时只做归档 SHA 对照、JSON 可读性和文档数字核对；没有重跑已通过的 CPU/GPU 项。所有后续完整模型或部署结果应另文或明确新增时间段，不回填成这一准备阶段已经完成。

## 后续模型准入的新增 CPU 绑定控制

在以上算子记录之后，单独核对了新完整模型诊断模块的环境和依赖绑定门，尚不执行模型诊断。旧模块 SHA `552dc1e974f8c09836bae99dde0336a30468fc09900e72576326c06673a2c45b` 的六项 CPU 控制原件保持通过，未重跑。新模块 SHA `6aa549bf9dba8bd59a3d85c8d93478d0930c63543873ef8daae0edd3a18f6ed1` 的三个数学/提示/provenance 函数、固定请求和预算常量，以及实际模型执行/关闭主体，与旧版 AST 一致。

仅对新源码中实际的 guard AST 表达式执行七项纯 CPU 检查：真实固定 plan 与环境通过；错误 qualified symbols、错误依赖 SHA、错误依赖路径、runtime 缺少 cache-disable、runtime cache-disable 值错误，以及 plan 缺少 cache-disable 均被拒绝。没有导入 Torch/FLA，没有 CUDA 调用，没有生成请求；也没有通过修改 source 来使测试更容易。旧六项与新七项分别保存在 `model-cpu-control/prior-six-controls.json` 和 `model-cpu-control/new-binding-control.json`，不把旧结果冒称在新版本重新执行过。

新完整模型 plan 固定三对参考/优化的合成请求，输入长度为 128、512、16,384，各输出最多 64 tokens，诊断子项最多六请求、34,432 输入加输出 tokens；另有独立交错准入，不能混为这六项已经运行。此 plan 的存在和 CPU 门通过均不等于完整模型准入通过。

## 切换后的只读吞吐观察器

用户追加要求验证后切换，并观察一段时间的实际运行速度。已准备 [`tools/monitor_kernel_rollout_v054.py`](../../tools/monitor_kernel_rollout_v054.py)，本记录的归档进程没有启动它。部署负责人提供确切新 bindings SHA 与 `activation_utc` 后，观察器等待该新版本首次在 GPU6 启动正式 worker，按该首个启动时间取 30 分钟窗口，约每 30 秒一次读取队列与 GPU3/6/7 的 `nvidia-smi` 利用率/显存。若触发检测延迟或查询异常，实际样本数及错误保留，不伪造完整 60 个有效样本。等待触发默认最多两小时。

本次 `activation_utc` 定义为 router adoption、开始停止旧 GPU6 新任务派发的调度转移时刻，**不是新模型 ready 时刻**。基线固定为 `[activation_utc−45分钟, activation_utc)` 内 GPU6 的闭合回合，因此其分母不包含之后排空旧回合、加载模型及准入诊断造成的部署停顿。新版本实际观察窗口独立使用 `trigger.json` 中的 `first_dispatch_utc`，两种时间均完整保留，不能把中间停顿隐藏成连续运行时间。调用者应按实际 adoption 回执传入该时刻，不能事后按吞吐选择基线截止点。

窗口归属依据原始 completion 的 UTC 时间，按 slot 去重；completion 与 controller ledger 文件每个最多读取一次。原始 request/prompt、补丁与隐藏评分材料均不读取。闭合记录按 GPU、arm、实际 bindings 修订分组，报告 worker 回合 wall time、实际输入/输出/总 token 和窗口关闭速率。未知账本保留，不以预约 token 代替实际消耗；窗口末仍在运行的回合属于右删失，不估填其总成本。

输出为逐次 `samples.jsonl`、逐题 `closed-episodes.jsonl`、基线、触发回执，以及滚动/最终 `summary.json` 与 `summary.md`。GPU 指标是整张设备采样，包含其他进程，不是本项目专属 kernel profiler。闭合任务的 token/window-second 包含其窗口开始前已执行的工作，不能当作模型 decode tokens/s。不同时间窗的任务组成、长度和并发条件可能不同，因此观察比值不称为 kernel 因果加速。

观察器七项纯 CPU fixture 检查已通过：时区统一、半开时间窗边界、原生/项目账本与未知预约处理、去重及分组速率、精确新版本触发、不可变回执只读一次、利用率分位算术。测试没有查询 GPU、读取实时队列或启动监测；回执为 `model-cpu-control/monitor-control.json`。
