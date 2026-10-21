# v054 GPU6 请求耗时补充协议

本补充只分析既有 `speed-monitor-r4` 收集的已闭合回合及其原生请求记录，不启动新监测器、GPU 采样、模型调用或服务操作。实现为 `tools/summarize_kernel_requests_v054.py`。准备阶段仅以一个临时合成 fixture 验证字段连接与统计分母；尚未执行真实观察窗口，也没有本补充的实际性能结论。

## 执行时机与命令

既有 monitor 的 `summary.json` 必须已是 `status=completed`，否则脚本拒绝运行。只在原 30 分钟窗口结束后执行一次，输出目录必须不存在：

```bash
.venv/bin/python tools/summarize_kernel_requests_v054.py \
  --monitor runs/software-benchmark-v054/kernel-optimization-r1/speed-monitor-r4 \
  --output runs/software-benchmark-v054/kernel-optimization-r1/request-timing-supplement-r1
```

输出 `report.json`、便于阅读的 `report.md`、逐原生请求 `requests.jsonl`、逐排队回执 `queue-receipts.jsonl` 与实际读取来源 SHA 清单 `sources.json`。来源错误保留在 `errors`，不补零或补造费用；缺少整个 session 的排队回执记为 unknown，不解释为零等待。

## 样本与区间

- 基线直接取 monitor 的 `baseline.json.records` 与其中的 45 分钟区间。本次 monitor 的 `activation_utc` 是最初 drain/router 接管时间 `2026-10-21T13:17:32.375765+00:00`，因此基线为 `[12:32:32.375765, 13:17:32.375765)` UTC；不会替换成 r6 实际激活时间。
- 新组区间取 `trigger.json.first_dispatch_utc` 至 `window_end_utc`，为首次新 GPU6 派发后的 30 分钟。新组仅接受 monitor intent 中确切新 bindings SHA 的 GPU6 已闭合回合。
- 两区间之间的模型准备停机不属于两个比较窗口。旧组和新组均以回合闭合时间选样，读取这些回合中已有完整用量的请求，因此可能包含窗口开始前发起的请求；窗口结束时仍在运行的回合及其请求不在本补充中。不能将本表解释为严格逐请求时钟窗口内的吞吐。
- 复用 monitor 已核实的 completion 时间与引用，不再次扫描全队列或所有历史回合。只读取所选 controller ledger、原生 response、PROJECT owner-finish 和同一 resident session 顶层的小型 turn/取消回执。没有 task tree、hidden grader、preflight 完整提示体、完整 world state 或 NVML 读取。

## 原生请求耗时

MATCH 使用 controller `ledger.calls[].response` 引用的 `match-ledger/native-response-*.json`，同时核对 attempt ID 与实际 usage。PROJECT 使用已结算 charge 的 `response_id` 精确定位 `owner/calls/calibration_*.json`，核对 HTTP status、response ID 与 `native_result.usage`。每个来源只做必要的一次 SHA 核验或记录；不重读模型任务内容作分析。

`generate_seconds` 来自 `CalibrationActor.generate_native()` 的 `seconds`。它包括输入张量准备、开始记录、模型 prefill 和 decode、输出 ID/logprob 转 CPU 等原生调用区间；不含外层 FIFO 等待和此前的提示准备，不含结果构造后完整结果写盘。它不是纯 GPU kernel 时间，也没有可用的独立 prefill/decode 分段。

按组、bindings revision 与 prompt token 桶 `0–2047`、`2048–4095`、`4096–8191`、`8192–12287`、`12288–16384`、`>16384` 分层。报告请求数、回合数、输入/输出 token、原生生成耗时总和及分布、单请求输出 token/原生秒分布，以及 `sum(output_tokens) / sum(generate_seconds)` 的合并比率。原生秒缺失或用量不匹配的请求不能进入耗时分母；保留已知请求数与实际提取数的差异。

## 排队与工具耗时的可解释范围

`*-turn.json.queued_seconds` 是从入队到 `_perform()` 开始的单调时间差，包含 FIFO、grant/commit 等待。`finished_monotonic - started_monotonic` 是更宽的 executor 窗口，含 RNG 保存/恢复、同步和原调用等，不是纯模型时间。取消前等待来自 `*-not-dispatched.json`，与已执行请求分列，不计为模型生成。两个 session 的等待可能重叠，不能把相加的等待当作 GPU 空闲时间。

小型 turn 回执没有可直接连接原生 attempt/prompt 长度的键，因此排队只按组、revision、操作与执行/取消状态分层；不按 ordinal 或相似时间猜测逐请求对应，不强行分配到 prompt 桶。

真实工具 CPU 时间未被统一记录。MATCH 原生工具 transcript 没有工具 wall timer。PROJECT 的 interaction wall 位于完整 world state，涵盖锁等待、加载、工具及派生，且不含最后 journal/save；它不是 CPU 时间。抽样完整 world state 约 93 MB，为遵守本次不重读整任务的范围，该补充不解析它。工具 wall/CPU 均明确为 null，只保留 controller 中已有的动作/工具数量；不把配置的时间上限或 episode 减去模型耗时的残差当作工具实耗。

## 结论限制与必要验证

这是不同题目、输出长度、提示长度、共同 GPU 负载下的观察。分桶减少长度混杂但不能消除题目、会话调度或 CPU 工作差异，不能推断因果 kernel 加速，也不能推断任务正确率等价。缺失字段与尚未闭合回合不会补数。

唯一合成端到端 fixture 覆盖一条 MATCH 与一条 PROJECT 的原生映射、两组分桶、合并速率分母、取消排队单列和 usage 不一致拒收。合成请求未触发任何真实模型、服务或 GPU 采样。另做一次窄静态字段审阅，修正无排队回执的 unknown 表述和 Markdown revision 分层；不执行整项目测试或重复历史模型验证。
