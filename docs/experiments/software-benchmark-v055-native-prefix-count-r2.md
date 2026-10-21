# v055 原生压缩器前缀计数故障与独立 r2 修订

这是已经结束的失败回合的只读工程诊断，不补跑原题、不改变原结果、不读取隐藏评分。当前 r1 冻结源码及在途进程不修改；候选修复使用新的独立入口，后续部署另行记录。

## 根因

两条代表性 MATCH 回合（`generation-1fc074acc542bb548fd44a48` 非思考、`generation-819f1e1974dff08da0952784` 思考）各完成四次 API 调用，所有用量已结算，适配器 `halted=null`、`inflight=null`。随后失败发生于本地 SDK 压缩器的历史计数，尚未发起 condenser 的实际 API 请求。

调用链为 `LLMSummarizingCondenser._get_forgotten_events` → `get_suffix_length_for_token_reduction` → `get_shortest_prefix_above_token_count` → `get_token_count` → 官方 recipe `ChatCompletionRequest.convert`。

SDK 固定 `keep_first=4`，进行 token 二分查找时先计量 `view.events[:4]`。两例首轮均包含两个工具调用，事件顺序为 system、user、Action、Action、Observation、Observation。因此四事件临时前缀只包含 assistant 的两个 tool_calls，没有后面的工具结果。**完整事件历史中两条工具结果实际均存在且已完成**；不是模型输出的调用漏执行，也不是实际 API 请求收到断裂历史。官方 recipe 的完整 chat 请求转换器被用于计量这个不完整临时前缀，因协议校验而拒绝。

MATCH 的较小上下文使该问题较早进入压缩路径。REF 没有在观察窗口内出现同类故障，并不能证明它不受这一通用计数问题影响。PROJECT 使用不同的受管历史整理方式，不经过这一原生 condenser 路径。

## 最小修订

独立 `software_benchmark_deepseek_prefix_v055_r2.py` 仅覆盖原生 LLM 的 `get_token_count`。完整对话继续走 r1 严格完整请求计数；只有以尚未配齐结果的合法 tool-call 轮次结尾的临时计数前缀，使用同一官方 recipe 的低层 `Conversation` / `DeepseekV41Encoding` 编码。

这个低层接口可以表达真实的未完成消息前缀，无需构造或添加空工具结果。只记录计数、原消息哈希和未完成调用 IDs，不将计数前缀作为反馈或 API 请求发送给模型。孤儿工具结果、历史中间断裂或动作参数改变仍被拒绝。SDK 前缀若只包含一批 tool_calls 的最初几个调用，只有在能对应原响应 IDs 和原参数时才恢复原 reasoning_content；不编造思考内容或补全未包含的调用。

实际生成仍由原适配器调用严格 `ChatCompletionRequest.convert`，不放宽派发校验。Agent、工具 schema、SDK condenser 的边界选择、系统说明、采样、输出/上下文上限、费用和任务初态均不改。新入口 `run_deepseek_controller_v055_r2.py` 仅更换原生 LLM 构造函数及控制器版本标识，PROJECT 代码路径沿用原件。

候选文件位于 `runs/software-benchmark-v055/native-prefix-r2/staging/`，不能将其存在本身视为已经部署。新旧执行修订必须按实际入口和源码哈希分开记录，不回写 r1 失败回合。

通过 CPU 控制后，模块原字节复制为新的 `src/proworksim/software_benchmark_deepseek_prefix_v055_r2.py`；新入口复制为 `tools/run_deepseek_controller_v055_r2.py`，唯一额外调整是将 staging 同目录导入改为 `proworksim` 包内绝对导入。没有覆盖任何 r1 文件，也没有重新调用模型或重放原任务。映射回执为 `runs/software-benchmark-v055/native-prefix-r2/canonical-source-mapping-r1.json`。固定模块 SHA256 为 `c45f3f4b7f2f7b21b658c6f8b317a1526648001b5514486643a128cb74a16528`，独立入口 SHA256 为 `974bd2a319e2f21077eca52966ff8329ae4e3ed37692423806c679b20dc0c090`。实际启用由独立宿主 activation 决定，只针对未开始的 REF/MATCH 库存；PROJECT 沿用 r1。

## 必要 CPU 控制

在原隔离 CPU SDK 环境，只读加载上述两例的完整已存 SDK 事件和响应证据：

| 项目 | MATCH 非思考 | MATCH 思考 |
|---|---:|---:|
| 完整视图原计数 | 16,674 | 17,866 |
| 完整视图 r2 计数 | 16,674 | 17,866 |
| 触发压缩的阈值 | 16,384 | 16,384 |
| 四事件不完整前缀 r2 计数 | 7,990 | 8,008 |
| 三事件半批前缀 r2 计数 | 7,892 | 7,927 |
| SDK 最终合法 summary_offset | 6 | 6 |
| SDK 选择遗忘的事件数 | 6 | 10 |

两例原错误均精确复现；新计数使原 SDK 二分和合法事件边界选择完成。完整计数与原版本完全相同。测试同时确认：真实派发计数仍拒绝不完整历史、半批调用计数可处理、孤儿工具结果仍拒绝、全部原事件文件哈希未变。

本次新增模型/API 请求、工具执行、隐藏评分读取均为 0；不恢复或重跑原回合。Ruff 通过。原始回执为 `runs/software-benchmark-v055/native-prefix-r2/cpu-control-r1/receipt.json`。

这些控制验证了已定位的计数故障及该分支修复，不宣布正式实验完成，也不抹除此前技术异常或费用。后续部署应只对未开始库存启用独立 r2，原异常集合仍单独保留。

## 实际上线短窗口观察

独立 activation SHA256 `33455781469b835a68e7fac78d40e5223cf7c051f9dd2b34c52fd9019c80a76a` 已启用，仅新开始的 REF/MATCH 使用 r2，PROJECT 和原在途进程保持。2026-10-22 **01:00:17–01:00:52 CST** 进行了两次相隔 35 秒的只读采样，没有新发模型/测试请求、修改源码或干预任务。按派发时间选取最早 r2 MATCH，并补充最早出现 condenser 续接、最早实际触发 r2 前缀分支的机械见证，不按分数选样；没有打开官方评分产物或记录模型思考正文。

| 机械见证 | 实际请求 | 其中 condenser | 前缀计数分支次数 | 实际总 token | 观察终态 |
|---|---:|---:|---:|---:|---|
| 最早 MATCH 非思考：sympy-24539 | 12 | 0 | 0 | 123,142 | 正常闭合，未触发压缩 |
| 最早 MATCH 思考压缩续接：sympy-24539 | 35 | 2 | 0 | 401,768 | 两次 condenser 后继续 Agent，正常闭合 |
| 最早触发 r2 前缀分支并压缩续接：MATCH 非思考 astropy-13977 | 41 | 6 | 7 | 497,507 | 六次压缩后继续 Agent，题内 token 预约不足正常闭合 |

最后一条是修复分支的真实运行见证：有 7 条 `count-only-prefix-r2` 计数记录、6 个真实 SDK Condensation 事件及其后续 Agent 请求，6 个摘要均非空（长度 1,148–2,200 字符）。这使证据从 CPU 复现扩展到实际任务通路；仍不代表所有未来历史形状已通过。采样覆盖的 12 条 r2 MATCH 中未观察到原 `insufficient tool messages following tool_calls` 错误复发。

必须保留两个不同的问题，不能将“控制流继续”笼统称为信息保存或全部故障已修复：

* 最早的思考见证中，两次 condenser 的实际输出均为 2,048 token，两个 Condensation 的摘要长度均为 0，SDK 随后仍继续 Agent。这里仅确认控制流闭合；空摘要与思考输出限额的相互影响另列，不声称原信息已保留，也没有放宽输出上限。
* 观察到另一条 MATCH 思考 django-15814 异常：第 5 次响应 `finish_reason=length`，没有 tool_call 或可见正文，原 reasoning_content 存在（仅记录长度 8,757 字符），全部 2,048 输出 token 都记为 reasoning。第 6 个本地准备请求中的这条空 assistant 丢失 reasoning_content，于客户端本地校验失败。该任务此前没有触发 r2 前缀计数，故不是本次原错误的复发。已即时报告并保留异常，没有重跑或热改；是否发生第 6 次网络派发以独立全局账本核查为准，不能仅从本地适配器 inflight 推断。

观察回执 `runs/software-benchmark-v055/native-prefix-r2/rollout-observation-r1/receipt.json` 的 SHA256 为 `77a4c13ecf596d2573cf2f857ec4841a015658e9b3f8cbd29f0df19ebdf2dd96`；摘要长度和新型异常的元数据另存 `metadata-only-supplement-r1.json`。两次样本、回执及元数据已归档到 `artifacts/software-benchmark-v055/native-prefix-r2/rollout-observation-r1/`，不包含模型思考/摘要正文或评分产物。
