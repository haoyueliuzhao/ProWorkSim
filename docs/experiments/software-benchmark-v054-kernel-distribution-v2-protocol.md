# v054 kernel 分布门 v2 协议

2026-10-21。本协议配合部署 r6、`model-qualification-r4/plan.json` 和诊断版本 `v054-kernel-model-diagnostic-r2`。协议冻结与 CPU 检查完成后，实际六请求通过新分布门，交错六请求通过，GPU6 于 22:43 正式激活；原 nRMSE 门仍失败。30 分钟观察于 23:13 完成，尚未证实任务级整体提速。

## 修订依据与证据范围

前序 r4 完成 4 次中性请求、1536 tokens 后在首个全词表 KL/nRMSE 门失败，失败数值未保存，无法从哈希还原。r5 改用保留 FP32 中间算术的 recurrent Triton 实现，完成 2 次中性请求、384 tokens；64 输出 ID 相同、首个 prefill 字节相同，但 decode 位置 47 的 raw-logit nRMSE=0.031371165066957474，超过原 0.03。r5 的完整词表 T=1 KL 最大约 1.5e-6，原门仍为失败。

看到这些结果后修订工程准入对象，明确属于事后观察后的协议修订；不是独立确认，不用正式任务成绩选配置，不把 r4/r5 重新标为通过。公共 logits 平移不改变数学 softmax 分布而会影响 raw nRMSE，因此新门直接测量实际采样温度下的概率差异。这个恒等式不证明实测 kernel 误差都是公共平移。

## 固定请求与比较方法

| 配对 | 输入 tokens | 每请求输出上限 | 相同配对 seed |
| --- | ---: | ---: | ---: |
| warm | 128 | 64 | 202610210601 |
| short | 512 | 64 | 202610210602 |
| long | 16384 | 64 | 202610210603 |

每对按 reference、optimized 顺序，共六次合成请求，无仓库任务/正式题目。沿用相同 prompt 构造和原始生成流程，不修改采样或 teacher-force。每个输出头捕获实际全词表向量；只比较由相同输出前缀条件化的合法 prefill/decode 位置，包括首次不同 sample 所在位置，之后不同条件不比较。允许输出轨迹不同，但必须报告共同前缀长度及排除位置。

实际 owner 采样参数固定并验证为 `temperature=0.7`、`top_k=0`、`top_p=1.0`。对每个合法位置，先以 FP32 按实际 sampler 的顺序计算 `log_softmax(logits/0.7)`，KL 的指数与乘加使用 FP64 减小抵消误差；最大概率差使用 FP32 log probability 的指数。新的两个必要数值门为：

- `KL(reference||optimized)≤1e-4`；
- `max_abs_probability_difference≤5e-4`。

shape/finite、全部捕获 logits 与采样 logprob 有限、head/output 对齐、精确 token 账本、原权重/只读状态及 Torch RNG 恢复保持必要。原 T=1 KL≤0.02 和 raw-logit nRMSE≤0.03 另算 `original_gate_passed`，逐 step、逐 pair、最终 receipt 保留；receipt 设 `original_gate_is_diagnostic=true`，不会把新门通过解释成旧门通过。

逐 pair 独立文件与累计 comparisons 先落盘，再拒绝失败。旧失败原件、原 generic `model_calls=null` 和解释实际成本的独立审计都保留。模型输出 logits 全向量只在内存用于比较，不落盘；保存统计、SHA 和必要指标。完整模型准入后仍须完成独立六请求交错准入，才可正式 registration/activation。

## 不变实现与累计准备预算

本次协议修订没有修改实际 FP32 recurrent 数学、Triton 配置、其余三个参考符号或权重。custom installer 在加载前只安装精确 hash 固定的 recurrent 实现；模块名、函数、overlay、依赖 manifest 和实际来源检查保持。正式任务工具、模板、seed、token/输出/时限不变，新运行实现仍独立标记。

| 预算项 | 请求数 | tokens |
| --- | ---: | ---: |
| r4/r5 已结算实际生成 | 6 | 1920 实际 |
| v2 完整模型诊断 | 6 | 最多 34432 |
| 后继交错准入 | 6 | 最多 61440 |
| 含历史实际的累计上界 | 最多 18 | **97792≤100000** |

这是准备预算，不占原正式 1500 槽。各项用实际完成账本分别结算；不得把未发生的上界记成消耗，也不能将旧失败成本零化。无训练、反向、优化器 step、正式任务重采或据成绩追加候选。

## 冻结身份、CPU 结果与留存

| 对象 | SHA256 |
| --- | --- |
| 新 diagnostic 源文件 | `d60941531ee002653640a23a9c07532fec6e8b08a05463179b7b17695ce11f86` |
| 不变 serve 入口 | `4248fd86d9770c08de7d8fe306dd0ea5b693e11f028a1ae2674de1a46a023e79` |
| plan-fields | `997aad8e7746789f94e93cd3448f72146f2c7104523f4a5489942e6b25674735` |
| 不变 FP32 recurrent 源文件 | `12bdbfabfab9f346f43e53f518341ea8b7c8a3e30e19269048fba601ac4177d2` |
| CPU 执行回执 | `f7b5fa7e0c3166f53ad718fc64882c448ee33487846e903a95a070d2f5fe132b` |

必要 CPU fixture 一次执行、9 项通过、0 模型/0 GPU 调用。全 logits 加 10 的 fixture 原 nRMSE=7.071、新 KL≈4.90e-8/最大概率差≈1.79e-7，旧门失败且新门通过；固定非均匀扰动 fixture 原 nRMSE≈0.00775、新 KL≈1.4325e-4/最大概率差≈0.00699，旧门通过且新门拒绝。温度、非有限值、shape、原门标记保存、先落盘后拒绝、共同前缀和预算检查同时通过。没有重跑已通过算子/GPU控制。

原件及小型复现实验位于 [`distribution-v2/`](../../artifacts/software-benchmark-v054/kernel-optimization-r1/distribution-v2/)，`archive-manifest.json` 记录来源与归档 SHA。`preparation-status.json` 只证明本文准备阶段。完整模型、正式激活及监测结果见[单卡切换实施记录的后续追加](software-benchmark-v054-kernel-rollout-r1.md)，不得从本协议或 CPU 成功推断其已完成。

## 冻结后实际六请求回执

实际模型 receipt SHA `43365394dc03dffc7236d2937bb045b9c241f8de915cca7a7cd9d8349a348058` 记录 6 次请求、34432 tokens、1 次模型加载、同一个模型对象、0 正式任务/参数更新。三个配对各比较 64 个相同前缀位置、logits 均有限、各配对 64 输出 ID 相同；T=0.7 KL 最大为 `3.3230895106841723e-7`，最大概率差为 `1.6168865840882063e-5`，新门通过。

三个配对原门全部失败，raw nRMSE 最大为 `0.1246379017829895`，原 0.03 阈值并未通过。结果不证明误差均为常数平移；不能从三种中性输入与 64 输出外推正式完整 18432/2048 组合或面板同值，也不改变观察后修订协议的性质。

模型门刚完成时累计已结算准备为 12 次、36352 tokens（历史 1920 加本次 34432）；`distribution-v2/model-qualification-status.json` 保留该时点交错/activation 尚待回执的状态，原准备快照与旧失败保持。

后续交错 receipt `66183cfc7d0a47bddb542ef15bf4c95c3233650aa699289ba5393ea6a923d7a3` 实际通过 6 次请求、1620 tokens，因此最终准入准备合计 **18 次、37972 tokens**。交错与模型诊断沿用同一个 owner/模型加载，不把两份 receipt 的各自 `model_loads=1` 重复相加。原始输出、token trace、RNG 转移在受测三组顺序/交错配对中一致，不外推完整容量等同。

GPU6 于 22:43:07 激活，正式 bindings SHA `9664f6d348f388bd966fdf888d290f88fa396e5c9586e8b21535b68bb2f68daf`。首个新版本 dispatch 于 22:43:11.329844 触发 30 分钟窗口，23:13:11.329844 窗口结束，共 60 次采样。GPU6 新版闭合 4 个 MATCH，8 个/小时、wall 中位数 672.34 秒；旧 MATCH 基线 7 个、9.33 个/小时、555.95 秒，不能据此声称任务级整体提速。不同题目组成也不能据此归因 kernel 减速。

一次只读补充取得 13 闭合回合、518 个 native 请求计时、提取错误 0。MATCH 同输入桶的输出/native 秒速率：0–8191-token 的三个桶约 +11–13%，8192–12287 约 +2.5%，12288–16384 约 −0.5%。该计时包含 prefill、decode 等原生工作，排除 FIFO 等待；不同任务/输出长度及设备干扰未受控，不能声称纯 decode 或因果 kernel 加速，长上下文收益尚未证实。GPU3/7 保持原版。

独立 activation、handoff、完整窗口小证据和请求补充已归档，滚动队列状态未复制。CPU fixture/必要静态检查、实际准入、累计成本及完整监测口径见[实施记录](software-benchmark-v054-kernel-rollout-r1.md)。准备成本仍为18次37972 tokens；观察及只读补充不新增模型调用，也不恢复旧训练或追加正式回合。
