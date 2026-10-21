# v054 独立 FP32 单 token recurrent 候选 r1

日期：2026-10-21，Asia/Shanghai。本文只记录新算子源码和有限算子控制；不代表完整模型准入或正式部署已经通过。

## 动机与实现边界

此前 FLA 两个 delta 算子的合成控制通过，但后续完整模型出现真实数值门失败。因此不能把算子级通过外推为模型等价，不能放宽原 logits 门把该候选变为通过。本候选另起独立目录，仅替换 `torch_recurrent_gated_delta_rule` 的 **T=1、H=32、K=V=128** 路径；chunk prefill、两项 causal-conv1d 保持原 Torch 参考实现。未改原 FLA 0.4.2 overlay、旧冻结源码、权重或任务配置。

`proworksim_fp32_recurrent.py` 使用现有 Torch 2.6.0+cu124 / Triton 3.2.0，无新增包安装、下载或 FLA 导入。每个 head 使用一个 CTA、128×128 state，batch 为第二个 grid 维；Q/K/V、g、beta、state 以及全部加乘、归约均为 FP32。Q/K normalization 按原参考的 `rsqrt(sum(x*x)+1e-6)`，query 按参考实际操作除以 `sqrt(128)`，依次计算 decay、state/key 归约、delta、state 更新和 output 归约，最后 output 转回原 query dtype，返回新 FP32 state，不修改 initial state。

固定 `num_warps=8`、`num_stages=1`、`enable_fp_fusion=False`，无 autotune、BF16 dot 或 TF32。Q/K/V/state/g/beta 的实际 stride 均传入 kernel。unsupported T/H/K/V 等形状回到原 Torch 函数；此 fallback 是候选边界，不是额外加速覆盖声明。该实现仅用于推理，拒绝参与需要梯度的调用。

`install()` 在新模型进程构造模型前显式安装，仅替换 recurrent 符号；若其余三符号已选择其他优化实现则拒绝。wrapper 使用 `functools.wraps(original_torch_function)`，保留 `__wrapped__` 与实际 `implementation` / `is_new_implementation=True` closure，供原来源检查核对。没有伪装成官方 FLA 包。

## 固定控制

执行前冻结新源码、计划、检查器及受限 launcher。沿用原算子工程容差：归一化 RMSE ≤0.015625、归一化最大绝对误差 ≤0.03125；输出/state 的 shape、dtype 必须相同且有限。没有根据结果更换 seed、阈值或 kernel 编译候选。

仅运行两个新场景，不重跑旧 FLA 四场景：

| 场景 | 输入和状态 | 检查目的 |
| --- | --- | --- |
| 1 步 | B=1，T=1，32 heads，BF16 Q/K/V，初 state 为 None | 零 state 分支、完整宽度输出/state |
| 4 步链 | B=2，每步 T=1，32 heads，time 切片输入，K/V 维转置的 FP32 初 state | 实际 stride、batch 维、连续承接自己的 state、初输入 state 不变 |

seed 固定为 `202610210651`；两侧使用相同输入。每实现每场景包含一次首次调用、两次 warmup 和五次稳态测量，交替反转基线/优化顺序，调用前后 CUDA synchronize。四步场景每次执行四次单 token 更新，因此本次实际新 kernel 40 次、参考单步 40 次，不能写成只有两次算子调用。

## 数值与时间结果

两场景均通过，初 state 均未被原位修改。1 步输出在该合成输入上逐位相同；4 步输出和两场景 state 并非全部逐位相同，不宣称数学或全模型精确等价。

| 场景 | 输出 NRMSE | 输出归一化最大绝对误差 | state 最大绝对误差 | state NRMSE |
| --- | ---: | ---: | ---: | ---: |
| 1 步 B1 | 0 | 0 | 2.98023e-8 | 4.81088e-8 |
| 4 步 B2 | 1.68331e-5 | 4.37063e-4 | 8.94070e-8 | 1.10609e-7 |

| 场景 | 参考稳态中位数 ms | 新算子稳态中位数 ms | 参考/新算子 | 新算子首次调用 ms（含 JIT） |
| --- | ---: | ---: | ---: | ---: |
| 1 步 B1 | 2.55187 | 2.43234 | 1.04914 | 1105.442 |
| 4 步 B2 整链 | 2.95791 | 2.48285 | 1.19134 | 607.588 |

这是共享 GPU5 上的同步 wall 计时，包括 Python 调度、新输出/state 分配及输出拼接；其他 GPU 工作未隔离。它不等于独立 kernel 延迟、模型 decode tokens/s 或整条流水线提速。四步计时是整链，不能称每步延迟。

检查器复用了旧 `run_case` 帮助器，其原 `timing_includes_python_dispatch_and_same_state_clone=true` 描述字段随原回执保留。新操作实际直接只读同一初 state，不在计时内主动 clone 它；帮助器对首次结果 state 的 clone 在首次计时之外。实际口径已另附 `measurement-annotation.json`，未改已冻结原回执，也未为修正描述重复执行控制。

## 资源与成本

采用原受限 GPU5 launcher：启动剩余显存要求 ≥3072 MiB，Torch allocator 上限 1 GiB、本进程总显存上限 2048 MiB、CPU 2 线程、900 秒期限；不停止其他进程。运行正常完成，宿主耗时 **8.048 秒**，约秒级采样所见进程峰值 **534 MiB**；Torch peak allocated **38,193,664 B**、peak reserved **44,040,192 B**。两种内存口径分别记录，采样峰值不冒称连续精确峰值。

本阶段模型加载 **0**、模型生成请求 **0**、生成 token **0**、正式任务 **0**、官方评分 **0**、训练/反向/参数更新 **0**。新增的是有限 GPU 算子控制；它与之后完整模型的独立六请求、交错准入和正式任务成本分开。

## 固定身份与下一阶段

| 对象 | SHA256 |
| --- | --- |
| 自定义 kernel 源码，6694 B | `12bdbfabfab9f346f43e53f518341ea8b7c8a3e30e19269048fba601ac4177d2` |
| 固定算子计划，3661 B | `5f834cad3463a36df710002073939a5ac8ab8e3a9dfbf226c57a1ac224da0dfa` |
| 新独立 overlay manifest，4948 B | `9c75e2608854f10e1342eaadbad000ffc18a78dec5d1608e5e334160f8f1d10d` |
| operator admission，3203 B | `5b7b31f77295f0470dd1a099ea17fcb495e9522940fb32ba81ba0ee486991097` |
| 算子结果，7240 B | `3dbb0b0a9c62fd3c2ecf9f1d1934c7017613cc9251b8f878626d4725da935de4` |

独立运行根为 `runs/software-benchmark-v054/kernel-optimization-r1/fp32-recurrent-r1/`，overlay 中只含本项目自定义模块；调用入口为 `proworksim_fp32_recurrent.install`。`admission.json` 仅列 recurrent 为 qualified，其余三符号不是本候选的优化准入。

完整小证据及源码归档于 [`artifacts/software-benchmark-v054/kernel-optimization-r1/fp32-recurrent-r1/`](../../artifacts/software-benchmark-v054/kernel-optimization-r1/fp32-recurrent-r1/)。控制完成后未修改源码或追加形状/编译搜索。下一阶段仍须保持原全模型 logits 门完成独立数值与双会话准入，成功后才允许正式 registration/activation；本报告不预先填写其结果。
