# v0.31 两个代码模型的原生协议修订

本次固定 **SWE-Next 作者 OpenHands XML 内容协议**，并修正 Devstral 提示与实际工具表不一致的问题。它们属于新的运行组合；v0.30 的真实失败、原始输出、token trace 和判定全部保留，不能按新解析器追认旧成功，也不据 CPU 控制宣称新组合更强。

实现与接口见 [native_codecs_v031.py](../../src/proworksim/native_codecs_v031.py)，定向控制见 [test_native_codecs_v031.py](../../tests/test_native_codecs_v031.py)，固定官方来源、旧实测证据与 CPU 回执摘要见 [software-native-protocol-v031.json](software-native-protocol-v031.json)。本次没有加载模型权重、生成模型响应、使用 GPU 或更新参数。

## 实际问题与证据边界

SWE-Next 恢复资格的四次实际 rendered prompt 均没有 `<function=...>` 或 `execute_bounded_tool` 提示。Dense actor 走的是 Qwen2 JSON 的 `prepare_prompt`；冻结官方 `chat_template.jinja` 本身明确要求 `<tool_call>` 内的 JSON 函数对象。没有发现继承旧9B XML提示的证据。它实际生成 XML 是已观察到的输出行为，不能把这一结果改称“9B提示污染”。

但官方 HF chat template 与发布者软件代理的实际内容协议不是同一概念。官方仓库 README 的本地学生模型评估示例关闭 provider-native function calling；14B训练配置使用 `template: qwen`。作者 OpenHands 配置明确允许并要求函数调用前的自然语言reasoning，以单个 `<function=...>` / `<parameter=...>` 调用结束、没有后缀；作者 agent 也从该内容中解析函数。与之相比，另一个 R2E 配置要求无reasoning输出。**本轮选择并明确登记 OpenHands 变体，不把两个配置说成统一格式。**这为新版XML运行组合提供公开依据，但不证明每一条SFT轨迹都使用相同形式。

另一个可直接确认的缺陷是：旧SWE与Devstral公共hint都提及 `staff_wait/staff_done`，资格工具表却只有 `read_public_note`、`record_fact`、`write_diagnostic_file`。Devstral第三次实际输出未提供的 `staff_done{}`。新版依据每次实际tool schema生成hint，不在没有对应工具时提这两个控制；原失败依然是真实的不符合协议结果。

Devstral第三条指令没有丢失。实际29,100字符渲染中，继续 `record_fact` 的指令位于第23,813字符，距尾5,287字符；system已有说明后续user消息承载于envelope且仍是当前指令。第二条也已在相同envelope机制下成功记录事实。无关staff提示存在是事实；它造成第三条失败的程度、重复记录与长fixture是否影响停止判断，均没有因果证据，不能作为已证实根因。

## 官方固定来源

作者仓库固定提交为 `b55c0841f364f9fe7363b2012cd0ae8d8afdf872`。只归档了六个必要小文件，共75,912字节；每个文件的实际Git blob SHA均与此前保存的官方Git树一致，并另算SHA-256。原件及清单在 `runs/v031-research/official-swe-next/`。

| 官方文件 | 支持的事实 |
|---|---|
| [README](https://github.com/TIGER-AI-Lab/SWE-Next/blob/b55c0841f364f9fe7363b2012cd0ae8d8afdf872/README.md) | 本地模型评估使用非provider function-calling模式 |
| [14B训练配方](https://github.com/TIGER-AI-Lab/SWE-Next/blob/b55c0841f364f9fe7363b2012cd0ae8d8afdf872/train/swe_next_14B.yaml) | Qwen2.5-Coder-14B基座、qwen聊天模板 |
| [OpenHands内容配置](https://github.com/TIGER-AI-Lab/SWE-Next/blob/b55c0841f364f9fe7363b2012cd0ae8d8afdf872/src/swenext/agenthub/config/openhands/edit_non_fn_calling.yaml) | reasoning在函数前、单XML函数、无后缀、多行参数例子 |
| [R2E内容配置](https://github.com/TIGER-AI-Lab/SWE-Next/blob/b55c0841f364f9fe7363b2012cd0ae8d8afdf872/src/swenext/agenthub/config/r2egym/edit_non_fn_calling.yaml) | 另一更严格无前缀变体；本轮没有冒称采用它 |
| [agent实现](https://github.com/TIGER-AI-Lab/SWE-Next/blob/b55c0841f364f9fe7363b2012cd0ae8d8afdf872/src/swenext/agenthub/agent/agent.py) | 非原生function-calling路径解析XML内容 |
| [Action解析器](https://github.com/TIGER-AI-Lab/SWE-Next/blob/b55c0841f364f9fe7363b2012cd0ae8d8afdf872/src/swenext/agenthub/action/action.py) | 作者参数解析会strip；其宽松行为不能直接用于本项目代码内容保真 |

## SWE-Next 的新声明

继续使用冻结官方Qwen tokenizer及聊天边界，但 `apply_chat_template` 明确传 `tools=None`；相同的实际公共函数、说明和完整参数schema作为文本工具手册提供。这样不会同时注入HF默认JSON函数调用说明。工具能力和WorldCore权限不由codec扩大。

输出接受可选reasoning前缀，随后恰好一个完整的等号形式XML函数调用；禁止调用后的额外文本。前缀和原XML内容保留于assistant消息和未来历史，原采样输出token始终另行完整保存。只接受实际提供的函数名和参数名，要求所有必需字段及完整schema成立；不接受JSON函数对象、`tool_call`外壳、多个函数，或把未知 `execute_bounded_tool` 的内部对象自动提取成另一个工具。

没有直接复用旧9B解析器：旧实现依赖另一层 `tool_call` 外壳、部分未知名字留到下游处理，对type union也没有完整保真。也没有照搬作者Action解析器的双参数写法、无条件strip或“只取第一调用”。本轮语法只选一种等号形式；普通排版空白不改变该形式。

**参数值的精确规则：**

- 参数schema恰为string（包括指向该类型的本地引用）时，正文是字面文本。其开头与末尾若各有一个LF，只移除这一对结构性LF；其他空格、代码缩进、内部LF及额外首尾LF均保留，不调用全局 `.strip()`。
- CPU/helper编码string时始终加入这一对框架LF，因此真正属于代码内容的首尾空白不会丢失。行内string同样合法；若要保留边界LF，应将其放在框架内。
- 其他类型及类型union使用严格JSON值。标准JSON Schema校验覆盖nested object、array、local reference、union及组合条件；integer必须保留为int，不能把bool或17.0修成17。不接受重复JSON键或非有限数值。
- 值中的 `&`、`<`、`>`使用对应XML实体；解析只做这一层实体恢复。控制标签字面量可安全保留在代码字符串中，不会被当成第二次函数调用。不存在根据预期答案修正参数的分支。

未来历史已有原XML内容时，必须与对应结构化函数/参数一致并原样使用；只有没有原XML文本的明确CPU fixture或结构化历史才按已声明规则序列化。该输入呈现不修改任何生成token或行为概率。

## Devstral 的新声明

保留官方mistral-common v13 encoder、原生输入token IDs、NativePrompt载体、9字符工具ID和现有透明tool→user envelope。新hint只根据当前真实提供的函数列表生成；仅存在 `staff_wait/staff_done` schema时才介绍其用途。Mistral原生调用仍只有 `[TOOL_CALLS]name[ARGS]{...}` 这一格式；无XML或JSON工具格式回退。

解析后的函数及参数也必须属于当前提供的schema，且保留JSON类型与数值；未知工具、额外参数、重复键及非有限值直接拒绝，不改写成正确调用。v13已允许的前缀保持，前缀中的字面 `[ARGS]` 不会误当作真正调用的参数对象。真实tool及后续user消息仍保留原角色、全文、原索引和hash；模块不追加事实、答案或假assistant行动。

## 给运行时的接口

| API | 输出 |
|---|---|
| `prepare_swe_xml_request(request, tokenizer)` | rendered text、实际native messages、投影记录 |
| `parse_swe_xml_generated(raw, request)` | assistant message、错误或None |
| `prepare_mistral_v13_request(request, tokenizer)` | NativePrompt、实际native messages、投影记录 |
| `parse_mistral_v13_generated(raw, request)` | assistant message、错误或None |
| `prepare_code_request` / `parse_code_response` | 第三个参数为固定candidate_id的统一分发 |
| `xml_call_text(name, typed_arguments, request)` | 显式CPU fixture/历史呈现用XML；禁止拿它修复真实输出 |

## 已完成验证及未测量部分

最终定向CPU控制 **29项通过**，另有两个第三方SWIG弃用告警；Ruff通过。控制使用已有resident环境的标准JSON Schema校验器，包含两组真实冻结tokenizer、官方OpenHands前缀与多行参数例子、路径框架LF、代码缩进和额外LF保真、复杂nested/ref/union、未知wrapper/多调用/后缀拒绝、真实v13编码及envelope保真。没有运行其他来源或WorldCore测试套件。

命令为指定resident Python执行 `-m pytest -q tests/test_native_codecs_v031.py`，`PYTHONPATH`包含既有v030 native依赖与项目src；原始stdout、stderr及被测源SHA保存在 `runs/v031-controls/native-codecs-r2/`。普通项目`.venv`缺少这些可选SDK依赖时本测试模块会明确skip，不能把skip当作上述29项通过；上述通过来自实际resident执行。

这些控制没有检验模型是否能按新协议自主生成正确调用，也没有证明数值概率门、完整反向或工作能力通过。后续真实模型资格须以新profile、新请求、新实际token trace单独运行。旧失败不回改，格式更换、数值修订和工作收益必须分别表述。
