# v0.5.4：REF/MATCH 共用准确计数接口与 REF HTTP transport

日期：2026-10-20（Asia/Shanghai）。本项只准备可执行包装和必要 CPU 控制，没有启动真实 vLLM 模型服务、加载权重或使用 GPU；没有缩小 REF 的 131,072 总窗口。

## 已实现的共同接口

新增 `src/proworksim/software_benchmark_exact_transport_v054.py`。REF 与 MATCH 现在可以使用 `build_llm(adapter)` 返回的**同一个 `ExactCountingNativeLLM` 类**，再传给已有 `software_benchmark_native_v054.build_conversation`。

共同类统一执行：

1. 调用官方 `LLM.format_messages_for_llm` 导出完整历史。
2. 调用每个官方工具的 `to_openai_tool` 导出完整 schema。
3. 生成完整 request，保留相应条件的模板参数。
4. 通过相同 `count(request) → complete input_ids/count/proof` 接口获得准确输入计量。
5. 用该条件的固定输出上限先预约，再执行一次 generation。

两个条件均不使用 LiteLLM 的近似 token counter，也不在计数失败后回退近似值或返回 0。空消息序列的计数为 0，是没有输入的明确情形，不代表请求失败可按零成本处理。

原生五工具、官方系统模板、Agent/Conversation 和 `LLMSummarizingCondenser(max_size=80, keep_first=4, max_tokens=None, hard_context_reset_max_retries=1)` 不变。condenser 的 LLM 副本保留同一个 adapter，因此使用相同准确计数接口和同一单题账本。**此次没有修改已经冻结的 MATCH bridge、其旧控制、REF 依赖或 native factory。**

## 两个 backend 的准确计数依据

| 项目 | REF | MATCH |
| --- | --- | --- |
| Adapter | `RefExactAdapter` | `MatchExactAdapter` 包装既有 `MatchBridge` |
| 准确输入来源 | 固定 vLLM 服务的 `/tokenize` 返回完整 IDs | 原 project owner `bridge.prepare` 的完整实际 `input_ids` |
| 输入上限 | 98,304 | 16,384 |
| 固定输出预约 | 32,768 | 2,048 |
| 总窗口 | 131,072 | 18,432 |
| 生成入口 | 同服务 `/v1/chat/completions` | 既有 `CalibrationActor.generate_native` |
| 原数值路径 | 已固定 vLLM BF16 | 既有 PROJECT BF16/FP32/head/attention/sampler |

在实际已安装的 vLLM 0.32.0 源码中，`TokenizeChatRequest` 支持 `messages/tools/chat_template_kwargs/add_generation_prompt/continue_final_message/add_special_tokens`；`TokenizeResponse` 返回 `tokens/count/max_model_len`。包装使用这些明确字段，不调用只统计裸文本、漏掉工具或漏掉系统提示的简化计数接口。

REF 的 `/tokenize` 与生成请求使用同一 model alias、完整 messages、完整 tools 和模板选项。计数回包必须满足 `count == len(tokens)`，所有 ID 都为非负整数，且服务声明的最大窗口必须仍为 131,072。相同完整模板请求可在同一 episode 内复用已经取得的准确计数凭据；缓存不跨题共享。

生成回包的 `usage.prompt_tokens` 必须等于预约前的准确计数；`completion_tokens` 必须在输出上限内，`total_tokens` 必须等于输入加输出。若提供 reasoning token 细分，它必须包含于 completion 总数。返回 usage 与预计输入不一致时，不将其当成一个可以信任的低成本回包。

MATCH 的包装只取原 bridge 已渲染的真实 token IDs，没有把 PROJECT 的 sampler 换成 vLLM，也没有更改原输入渲染或账本。共同之处是完整实际 ID 的计量合同；两个 backend 不需要使用相同软件来执行计数。

## REF 单题预算与 HTTP 边界

REF 使用每题 500,000 输入加输出 token、128 次全部实际 model attempts、128 次 Agent decisions。condenser 的调用和输入输出均进入同一账本；其摘要操作不另算一个解题 Agent。

计数 HTTP 请求只执行 tokenizer，不是 model generation attempt，不虚构生成 token 成本。真正发出生成请求前，账本先记录完整 request、准确计数凭据和 `prompt_tokens + 32768` 的预约。HTTP 返回的完整 JSON 在结算前保存。

HTTP transport 只允许显式的 `http://127.0.0.1:<port>`，正式 REF 固定端口为 18054。它使用直接 `HTTPConnection`，不继承代理，不使用环境中的 endpoint，不跟随重定向，不自动重试，也没有跨 endpoint 或远端 fallback。synthetic fixture 不能指向正式端口 18054。

以下情况均停止后续 dispatch：

- `/tokenize` 回包不完整、数量与 ID 不一致、窗口改变或计数失败。
- 生成请求超时、HTTP/JSON 故障、完整 usage 无法对账、回复身份或候选数异常。
- 预约不足、上下文不足、attempt 或 decision 上限到达。

如果故障发生在生成请求发出之后，保留全部未决预约，`complete_actual_tokens=null`；不把无法确认的成本写成 0。已有可结算的调用继续保留其真实费用记录，金额估计仍为 null。不会因为失败而偷偷重新生成。

调用前检查 5,400 秒软边界；准确计数耗时之后再次检查，防止计数结束时已越界却继续发起生成。6,000 秒生成后边界也被记录。独立宿主硬 watchdog 与取消凭据仍需后续生命周期装配，不能把这些 Python 检查当作已经有了不可超越的硬中断。

每次 REF 请求携带题单预定的同一个 task seed。这是明确固定的服务请求规则，不宣称其 RNG 序列与 PROJECT 连续推进的本地 RNG 相同；不同推理 backend 的 seed 不保证相同动作。

## 已完成的四组 CPU 控制

`tools/check_exact_native_transport_v054.py` 于 **2026-10-20 23:30:22–23:30:32（UTC+8）**全部通过：

| 控制组 | 证据 |
| --- | --- |
| 真实 SDK/condenser 共用预算和完整 HTTP 请求 | 官方 SDK `generate` 与官方 condenser 都访问本机 synthetic HTTP；2 次计数、2 次程序化生成回复，共同账本为 attempts=2、decisions=1；每次预约都是完整输入加 32,768；相同计数凭据被复用 |
| usage 不一致与计数错误 | wrong prompt usage 保留未决预约并禁重采；`count != len(ids)` 在生成前拒绝，生成请求数为 0 |
| timeout 与 endpoint/redirect | 生成超时后只有一次请求，费用保持未知；远端、HTTPS/DNS别名被拒绝；302 只产生一次请求且不跟随 |
| MATCH 共用同一类及真实 tokenizer | 使用已有 Qwen tokenizer，合成主请求为 7,397 个实际输入 ID；与原 bridge 的生成输入数量一致；REF/MATCH 导出的 messages 和 tools 完全相同 |

REF fixture 的 token IDs 是该合成 HTTP backend 明确生成的测试 IDs，**不是 Qwen 的实际 tokenization，也不是模型消耗或本轮正式费用**。不能将其计数与 MATCH 的 7,397 作能力、效率或资源差值比较。该控制验证真实 HTTP 协议、准确计数合同、预约、usage 对账和失败边界；真实 vLLM 模型服务的 `/tokenize` 与生成一致性仍须等服务准入后验证。

真实模型调用、权重打开、GPU 打开和外部网络尝试全部为 0。只使用本机自有 loopback fixture，完成后全部关闭。

主控制回执：`software-benchmark-v054-exact-transport-control-r1.json`，SHA256 `5c3ded7f2b34080116164bc7e0274ca4b790d8d8fa9118c4e076a901002a32f7`。

随后对“计数耗时跨过软截止点”的新增检查只做了单独 CPU 断言：生成 HTTP 从未调用、attempts=0；没有重跑四组已通过控制。补充回执为 `software-benchmark-v054-exact-deadline-control.json`，SHA256 `d1bf978c32275e106bdf8aeb448137fe35fd5ae0301441a0fa5ef8555a21f71a`。新源码和控制脚本通过 Ruff。

## 可执行装配方式与剩余准入

MATCH：

```python
adapter = MatchExactAdapter(existing_match_bridge)
llm = build_llm(adapter)
conversation = native.build_conversation(
    llm, workspace=prepared_workspace, persistence_dir=episode_directory)
```

REF：

```python
transport = LoopbackHTTP("http://127.0.0.1:18054", timeout_seconds=1800)
adapter = RefExactAdapter(
    transport=transport, folder=episode_evidence, slot_id=frozen_slot_id,
    seed=frozen_task_seed, service_identity=admitted_service_identity,
    execution_authorized=False)
llm = build_llm(adapter)
```

示例保持正式执行授权为 false；不会启动服务或执行 `Conversation.run()`。真实授权分支还要求实际服务准入凭据、原始模型 revision/manifest、无 adapter、固定 vLLM 版本和固定输入输出容量匹配；名称相同不足以准入。

固定准备清单为 `config/v054-exact-native-transport.json`。本项已经实现共同准确计数与可执行 REF 包装，剩余的是实际 GPU 服务、每题 owner window/seed 生命周期、宿主 watchdog、隔离 Docker workspace 与官方评分闭合，以及独立模型预算授权。未满足这些条件前，不启动正式回合，也不通过缩短上下文绕过 REF 的容量门。
