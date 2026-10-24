# v057 模型响应 reasoning 字段适配

日期：2026-10-24。该修订供新版本控制器使用，不修改 v054／v056 冻结源码、原始响应、账单或评分。

## 修复内容

固定 vLLM 0.32.0 响应使用 `message.reasoning`，现有 OpenHands SDK 1.49.6 的 `Message.from_llm_chat_message` 读取 `reasoning_content`。旧路径直接构造 `ModelResponse`，导致该思考字段没有进入 SDK Message。

新增 `software_benchmark_exact_transport_v057.build_llm(adapter, normalization_folder=...)`，沿用原精确输入计数、请求序列化、预算与派发适配器。适配器先照常保存原始响应、核对实际用量并结算，然后新工厂在独立副本中添加 SDK 字段别名。`LLMResponse.raw_response` 仍保留提供者原字段，投影证据单独保存，不覆盖原始记录。

处理规则：

- `reasoning` 为字符串、`reasoning_content` 缺失或为 null 时，添加同值别名。
- 两个字段都有非 null 值且相等时保留，不重复映射。
- 两个非 null 值不相等时明确拒绝；空字符串也视为显式值，不静默覆盖。
- 非字符串、非 null 的字段值明确拒绝，不猜测其含义。

本次不改变32,768单次输出上限、98,304完整输入上限、采样设置或重试规则。SDK投影中的正文、工具名称／参数和usage保持同值。新增证据只记录字段长度、哈希与来源，不重复保存思考原文。

## 必要验证

三个针对性测试通过，覆盖原始对象不变、正文／工具／用量保留、幂等、null／空字符串边界、冲突与错误类型拒绝；Ruff通过。

另在固定的真实SDK环境中，经新 `build_llm` 的同步及异步 `completion` 路径回放两份历史响应，未调用模型、计数器、工具或评分器：

| 历史响应 | 原SDK思考字符 | 新SDK思考字符 | 正文／工具／用量 |
| --- | ---: | ---: | --- |
| reasoning-only响应 | 0 | 8,440 | 保持同值 |
| 工具调用响应 | 0 | 155 | 保持同值 |

原 wire 文件、`raw_response`提供者字段和已记录用量未改变，工厂输入／输出限制及零重试配置保持。结果见[真实SDK转换证据](../../artifacts/software-benchmark-v057/reasoning-projection-r1/result.json)和[验证记录](../../artifacts/software-benchmark-v057/reasoning-projection-r1/validation.json)。

## 解释边界

这证明新SDK投影不再遗漏该字段，不证明正确率提高。SDK对空响应与仅思考响应仍使用原纠正规则；该修复不能单独证明能解决无行动循环。后续历史组织可能因字段得到保留而改变，因此新工厂属于新执行版本，不能将其潜在结果并入原冻结实验或回改旧分数。
