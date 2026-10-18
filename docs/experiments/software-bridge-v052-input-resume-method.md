# v0.52 初态资格修订：原件复用、源码绑定重物化与唯一剩余库存

本说明记录初态资格工具的两次执行前/捕获后错误，以及随后对唯一尚未测量的首个 PS1 输入的恢复方式。修订仅作用于资格脚本和记录，不改变原 614 个实现文件、正式 OH/PS1 执行路径、问题、种子、模型、解码参数、Γ1 或预算。来源资格的 18 个逻辑单元、9 次实际测试执行已经闭合，本修订不再次执行业务测试。此文件完成时，根代理正在另行签发并执行原剩余 10 个初态；它们的最终结果以独立接续摘要为准，本方法不预填通过结果。

## 1. 保留两次原始失败

第一次初态执行在检查 tokenizer 文件集合时停止。release 将模型 `config.json` 与精确要求的三个 tokenizer/template 文件放在同一集合，资格脚本拒绝该集合，实际 SDK 请求和编码均为 0。原 release、声明、stdout 和退出回执保持原样。随后 r2 仅将模型 `config.json` 独立绑定为 `model_config`，没有改变代码或业务资产。

第二次执行已经跨过两个真实初态 SDK 边界：首个 `v052-cal2-boltons-1-OH_ref` 完整保存请求、native input、投影与容量结果；首个 `v052-cal2-boltons-1-PS1` 已在真实 SDK 第一次 `prepare_for_budget` 边界捕获请求，但后置断言把 `_completions=1` 当作一个已返回响应而失败。该字段是 LLM 入口计数；第一次 prepare 中的受控 `BaseException` 已在 reserve 之前截断，`CaptureTransport.complete` 不会生成响应。因此本次不是 SDK、模型或容量故障，实际模型生成、attempt、预约、返回响应和工具动作均为 0。PS1 保留真实的 harness/team 各 1 次决定记账，不为满足零计数而改变第一次机会或预算视图。

旧脚本在错误断言之后才写出 provider request，因此第二个请求的原始 provider JSON 未落盘，也没有独立原 SHA。其实际 SDK 系统/用户事件、工具 schema、会话 base state 和机会/预算记录已保存。剩余 10 个逻辑形状尚未开始。原始失败、旧控制和旧费用事实均不覆盖。

| 证据 | 路径 |
| --- | --- |
| 原初态方法 | [input-qualification-method.md](software-bridge-v052-input-qualification-method.md) |
| 第一次 release | [input-execution-release.json](software-bridge-v052-input-execution-release.json) |
| 第一次退出回执 | [actual-initial-exit.json](../../artifacts/software-bridge-v052/input-controls/actual-initial-exit.json) |
| r2 release | [input-execution-release-r2.json](software-bridge-v052-input-execution-release-r2.json) |
| r2 退出回执 | [actual-initial-r2-exit.json](../../artifacts/software-bridge-v052/input-controls/actual-initial-r2-exit.json) |
| 已完成 OH 测量 | [OH_ref-progress.json](../../artifacts/software-bridge-v052/initial-inputs-r2/v052-cal2-boltons-1-OH_ref-progress.json) |

## 2. 首个 PS1 的来源绑定重物化

这一步只将已存实际 SDK 输入经冻结转换函数重物化，没有新建 Agent/Conversation，没有调用 SDK completion，没有生成 UUID，也没有重新准备世界或调用工具。其来源和转换链为：

1. 原 `experience.jsonl` 中唯一的 `SystemPromptEvent` 和用户 `MessageEvent`，以及同一会话的 `base_state.json`。要求没有动态上下文、扩展用户内容、condenser、既往 agent state、模型/工具调用或身份刷新。
2. 已绑定 SDK 的 `SystemPromptEvent.to_llm_message`、`MessageEvent.to_llm_message`、`LLMConvertibleEvent.events_to_messages` 和 `Message.to_chat_dict`；使用原 `_complete` 的序列化参数及用户块展开规则。无需重建动态工具类，事件转换只使用已存文本字段。
3. 原首轮 `select_context` 和固定策略。两条实际 system/user message 均保留；不猜测隐藏历史或删减。
4. 实际已存 27 个完整工具 schema，加冻结的 2 个控制 schema及原 S1 的 wait/done 描述。所有 29 个名称、描述都与实际 SDK 系统事件中解析后的工具对应。
5. 原 `_config`/`normalize_config`、只读 raw owner 元数据、实际用户消息中的 `role_task`、原机会记录中的 128 决定上限，及原 `build_runtime` 的固定覆盖项。SDK 会话中实际 temperature、输入/输出容量与该配置一致。provider 配置来自原构造函数；不会将 SDK LLM 对象自身默认字段冒充 provider 请求字段。
6. 原 before/after 机会、唯一 decision-consumed 账项及冻结 call ID 生成规则绑定 runner turn。它们证明第一次机会、`member_001`、1 次决定、0 attempt/预约/收费；没有新造会话标识或猜测可变字段。

完整依赖路径、SHA、事件 ID、配置、机会和转换说明保存于 [dependency-chain.json](../../artifacts/software-bridge-v052/initial-input-PS1-rematerialized/dependency-chain.json)，SHA `88623bb826ce9fbbb107414de066dfab27c18f937fdaf1c2ef7b47c174a543fe`。实际原事件中已有的可见 UUID 原样保留，没有归一化；本方法不声称输入对 UUID 不敏感。

输出是来源确定的重物化请求，不是重新找到的原 provider JSON。该行及最终摘要明确保留：

```json
{
  "original_provider_request_persisted": false,
  "original_request_sha256": null,
  "source_derived_rematerialization": true
}
```

最终摘要中的上述字段明确限定到 `source_derived_shape_slot_id` 对应的唯一 PS1 行；其他行分别保存自己的原请求证据。新重物化文件自身有 SHA，仅用于绑定这次输出，不能替代不存在的独立原请求 SHA。准入结论限于来源链和初始容量，不宣称逐字节复现了一个独立保存的原件。

## 3. 唯一首次 PS1 容量测量

重物化之后，授权执行了该 PS1 形状此前尚未发生的首次 Γ1/native/tokenizer 测量。使用原 tokenizer/config/template、C=18432、O=2048 和 metadata-only raw 身份；不加载权重，不以历史 owner 元数据声称当前模型 tensor/guard 已通过。模型原件、来源资格和 source/runtime 身份仍通过原 r2 release 绑定。

结果为原 prompt 7090 token，selected prompt 6744 token，`6744 + 2048 = 8792 ≤ 18432`。本次实际编码 2 次、native template render 2 次、编码精确缓存命中 5 次、render 缓存命中 0 次；新 SDK 请求、模型调用和业务测试均为 0。首个 OH 的已完成 5024-token 输入直接引用原件，没有再次编码。

| 新原件 | SHA256 |
| --- | --- |
| [summary.json](../../artifacts/software-bridge-v052/initial-input-PS1-rematerialized/summary.json) | `c8860560a8d03a9b3504af7e7bbf00adc5bef4e1fd9f944006d0b92d5595dd8e` |
| [source-derived-request.json](../../artifacts/software-bridge-v052/initial-input-PS1-rematerialized/source-derived-request.json) | `fffe2ab0d2b4ada0392fa08ab0ef0222becf3785476896654535ec37c584bd8c` |
| [selected-native-input.json](../../artifacts/software-bridge-v052/initial-input-PS1-rematerialized/selected-native-input.json) | `1d192536b1a7547b91c6b11993dc5d7d1a44b1c8fae28c9877b9f6dc0f07b645` |
| [projection.json](../../artifacts/software-bridge-v052/initial-input-PS1-rematerialized/projection.json) | `57ff1041e1de8deacabd3d3346b790ea1c020531eb465b2827d90520d8e1e3fa` |
| [退出回执](../../artifacts/software-bridge-v052/input-resume-controls/rematerialization-exit.json) | `6591ca372d65c2534d1bb34d1f03c74b9deaae58296f4cfab14b19687ded3cb5` |

首次 OH 执行的 aggregate tokenizer 计数对象没有在随后 PS1 断言失败前整体落盘。接续摘要将其 1 次编码、1 次 render、0 cache hit 列为依据未分支的唯一 `prepare_native_input` 调用及已存 native 原件所得的来源计数，明确不冒称原保存的计数快照。它与本次实际保存计数、后续十份实际计数分阶段列示后才求和。

## 4. 独立接续实现和两项必要纯控制

新增 [software_bridge_inputs_v052_resume.py](../../scripts/software_bridge_inputs_v052_resume.py)，不改原资格脚本。PS1 保留原建世界、原 runtime、原第一次 `runtime.step()`；一旦捕获实际请求，先写 `original-request.json` 和 capture envelope，再验证 member、身份、世界状态和计数。LLM 入口单列为 `LLM_entries`；返回响应以实际响应体是否存在计数，实际生成以 HTTP attempt 计数。真实首次机会的 harness/team 各 1 次决定不转入正式模型 episode，也不算模型采样/账单。

新增控制仅为两个受影响边界：LLM 入口不能冒充返回响应；唯一剩余库存必须是原 12 个唯一槽扣除已完成首 OH 与来源重物化首 PS1，拒绝交换身份、重复槽和旧形状再次执行。两项第一次执行均通过，Ruff 通过；不重复原 3 项纯控制、旧 SDK fixture、来源三态或模型资格。

控制后仅补充最终摘要的明确 provenance 字段及其单行作用域，不改变捕获、库存或 tokenizer 行为。摘要同时保存测试时源快照与最终源码引用，保留这个差异，没有为纯报告字段再次运行控制。

[controls summary](../../artifacts/software-bridge-v052/input-resume-controls/summary.json) SHA `e7d5b72872c1013af5c821e0276b1be2dc2da52f1ff25496a999d672b886168e`，含首次 pytest/Ruff 日志、源文件、测试文件、原执行快照及重物化摘要引用。控制本身 SDK、tokenizer、模型和业务测试执行数均为 0。

## 5. 原十份执行门和计数口径

接续必须由根代理另签 `version=v052-initial-input-resume-execution-release-v1`、`released=true`、`maximum_new_SDK_requests=10`。release 绑定 `prior_input_release`、`prior_OH_progress`、`rematerialized_PS1`、`prior_partial_exit`、新 `implementation_sources`、两项 `control_refs` 和精确 `remaining_slot_ids`；PS1 依赖链通过不可变 summary 引用同时绑定。脚本再次消费原 release 的原 614 文件、模型/SDK/来源/运行环境身份门，且输出目录必须全新。

只有原剩余 10 个 SDK 初态可以开始。此前 OH 的请求/native/projection直接复用；此前 PS1 的来源绑定重物化和首次测量直接复用。完成后的逻辑分母为 12，实际累计 SDK 边界为原 2 加新 10，新增模型调用为 0；其中 11 份应为直接保存的原请求，1 份明确为来源重物化。重物化不计新增 SDK，先前失败不抹除。两路框架输入本来不同，不要求 OH 与 PS1 输入字节相等，不按可见 UUID 归一化；只检查相同任务/来源/资产及各自 selected+2048 的硬容量。

实际命令使用正式 SDK Python 和依赖路径，禁止用仅执行纯控制的 `.venv` 冒充正式 SDK 环境：

```bash
CUDA_VISIBLE_DEVICES='' \
PYTHONPATH=runs/v030-runtime-deps:src:. \
runs/v016-sdk/resident-venv/bin/python \
  -m scripts.software_bridge_inputs_v052_resume resume \
  --release /ABS/ROOT-SIGNED-INPUT-RESUME-RELEASE.json \
  --output /ABS/FRESH-INITIAL-INPUTS-ROOT
```

根代理负责唯一真实接续执行、保存 stdout/exit 和最终准入。发生新基础设施或测量错误时保存已消费范围，不自动重试、改源或重编码已完成形状。本说明不授权模型生成、GPU worker、额外资格形状或旧工作区补验。
