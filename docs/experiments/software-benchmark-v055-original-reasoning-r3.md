# v055 原生 SDK 原始 reasoning 序列化修订 r3

本修订针对思考模式下无工具调用的 assistant 历史字段丢失。它独立于 r2 的压缩器前缀计数修复；不修改任何已冻结 r1/r2 文件，不恢复或重跑已进入任务，不改变输出上限、模型配置、工具或空摘要行为。

## 原始故障与证据边界

已结束的 MATCH 思考 django-15814、matplotlib-24970 回合，在分别完成 5、17 次实际请求后，后续本地准备请求被 `validate_payload` 拒绝：`Thinking tool history must preserve reasoning_content, including empty strings`。

两例最后一笔已结算响应均为 `finish_reason=length`，没有工具调用；原始 reasoning_content 有值，长度分别为 8,757、7,708 字符。SDK 的 `Message.from_llm_chat_message` 和持久化 MessageEvent 均保留该字段，但 `LLM._to_chat_dicts` 根据模型功能表的 `send_reasoning_content` 开关序列化，当前模型别名对应的开关为 false。原 r1 的工具调用历史缓存只恢复具有 tool_calls 的 assistant，因此没有修复这条无工具消息。

此外，即使打开 SDK 的发送开关，`Message.to_chat_dict` 也只在字段 truthy 时写入，仍会遗漏提供者确实返回的空字符串。这是“缺失”和“原始空字符串”两种不同情况，不能通过统一填空掩盖。

客户端只读审计确认，这两个被拒绝的后续 request_id 在共享人民币账本中不存在：分别为原第 6、第 18 个本地准备请求，未发 API、未占用费用预约。原已执行请求和费用保持；旧本地适配器残留 inflight 不能自动改成一次已收费请求。相关旧故障与独立账本证据保留，r3 不回写旧记录。

## 精确修复

新类继承 r2 的 `PrefixCountingNativeLLM`，仅覆盖 `_to_chat_dicts`：先调用原 SDK 序列化，再按同一序列位置对应的原 `Message`，将 assistant 的 reasoning_content 原字段为字符串时精确写回。真实空字符串也保留；原字段为 None 时不制造值。没有基于文本相似性的查找，没有重建思考，没有伪造工具调用或反馈。

因此完整 SDK Message 身份和顺序就是恢复来源。原生工具调用的原响应恢复继续沿原适配器；r2 不完整计数前缀处理继续继承。真正网络派发、严格完整请求计数、API 参数、128 次调用、500,000 总 token、REF 32,768 / MATCH 2,048 输出限制均保持。非思考序列化完全沿原路径。PROJECT 不经过该原生 LLM 替换，保留 r1。

固定新文件：

* `src/proworksim/software_benchmark_deepseek_reasoning_v055_r3.py`：SHA256 `5150baa5c054adddcd19f16575259f43d1480c908f0b5771a8bb9484316d7ad7`。
* `tools/run_deepseek_controller_v055_r3.py`：SHA256 `53aa53445c717a7ed06ddbd2b43d70e6ac8b897ae8bc9238ef9615a87ffe137e`。

入口仅切换原生 LLM 构造函数和版本标识。由独立 activation 为未开始的 REF/MATCH 库存选择新入口；源码已固定，不能对在途回合热改。

## 必要 CPU 控制

在现有隔离 CPU SDK 环境只读重物化上述两条完整失败历史，没有调用 API、工具、评分或恢复原回合。两例均精确复现 r2 的字段缺失拒绝；r3 严格校验通过，除了对应无工具 assistant 的原始 reasoning 字段外，请求其余字节同值。恢复内容哈希与最后一笔原始响应一致，不保存或披露思考正文。

| 回合 | 精确恢复字符数 | 新严格计数预留（含固定 128 余量） | 原输入 16,384 上限 |
|---|---:|---:|---|
| MATCH 思考 django-15814 | 8,757 | 14,984 | 满足 |
| MATCH 思考 matplotlib-24970 | 7,708 | 11,873 | 满足 |

同一次控制还核对：原 SDK 空字符串得到保留；原字段 None 仍缺失并被严格请求校验拒绝；非思考序列化不变；r2 前缀计数方法原样继承；原事件文件哈希未变。Ruff 通过。

回执为 `runs/software-benchmark-v055/native-reasoning-r3/cpu-control-r1/receipt.json`，SHA256 `b5a129e8ba4ce4b382f015e9c6fea8a272681483d1bc25c414291c19457b8f75`。部署候选绑定为同目录上级 `deployment-candidate-r1.json`，SHA256 `92ac054a88dd11b3a7e04aee02348d41f006c96b90690bf74869b4bc939eef92`。

本次只是工程故障修复，不是模型能力结果。此前观测到的思考模式 condenser 空摘要仍客观保留，不在本次修订中调整 2,048 输出限额或模板。真实线上自然触发情况应另行记录；没有自然触发时，只能报告已部署及有限 CPU 证据，不能额外请求模型制造成功案例。

## 实际部署与有限窗口观察

独立宿主 activation 为 `native-host-revision-r3/activation.json`，SHA256 `99c4aadb7a23be7f96b649dd19bf319b163c26db42e6a83d1c3195ecc853a186`。以队列实际记录为准，最早 r3 派发为 **2026-10-22 01:18:39.672 CST**；不采用人工估写的启用时间。

在 **01:19:50–01:20:50 CST** 做了严格两点、间隔 60 秒的只读自然观察。选择规则在观察前固定为最早的 r3 MATCH 思考回合（最多 8 条；尚无时只看最早两条原生回合），不依据成绩选择，没有打开评分产物或记录思考正文。观察结束时全队列共有 10 条 r3 派发；所选最早 MATCH 思考 django-15252 已由 r3 控制器启动，8 次请求已结算、79,521 token，第 9 次仍在途；另一早期 MATCH 思考 sphinx-8638 仍在准备阶段。

窗口内未自然出现“无 tool_call 的 assistant 携带 reasoning 后继续下一实际请求”的可核对样本，也没有所选回合已返回的错误。因此本窗口只证明 **新版本真实运行与前述有限 CPU 修复证据**，不声称该恢复分支已获在线触发验证。观察按时结束，没有扩大验证、人工追加 API 请求或干预正在运行的任务。

回执为 `runs/software-benchmark-v055/native-reasoning-r3/rollout-observation-r1/receipt.json`，SHA256 `9099a8755fb97f16433b8ddbe4f26a22cd7eff9afb0dee4c87ee8945f707adc3`。两次样本及回执已追加归档，不改原 CPU、源码和失败记录。
