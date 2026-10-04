# v0.30 原生模板与真实 SDK 的 CPU 控制

北京时间 **2026-10-04 13:28:28—13:29:23** 完成恢复版 CPU 资格，18 个模型/案例组合全部通过。观测墙钟耗时约 **54.665 秒**，并行处理三个组合载体；不是 GPU 时间或模型推理成本。

实际执行 **72 次脚本化 SDK transport 请求**，72 次公共工具参数的原生编码/解析往返正确，24 个由 WorldCore 实际产生的不存在路径错误均完整进入下一次实际原生编码消息。三模型均使用真实本地 tokenizer 与已声明 renderer。**模型调用为 0，未加载权重、未初始化 GPU、未生成 token_trace、未创建可训练 rollout、未更新参数。**这项通过只说明本次有限输入下的格式、消息承载与容量可用，不能作为推理/训练资格或工作能力结果。

可提交的结构化摘要见 [software-native-templates-v030.json](software-native-templates-v030.json)；完整原件为 `runs/v030-controls/native-templates-r1/qualification.json`，SHA-256 为 `c643457857aa2e0bc923d550fa4259dfc398ec8e522fe477be8d1a5acb5bafaf`。运行脚本为 [qualify_code_templates_v030.py](../../scripts/qualify_code_templates_v030.py)。原始请求、选择后请求、实际原生消息、输入 token IDs、原生响应 fixture、参数解析以及世界回执均逐请求保留。

## 本次控制怎么执行

使用新 v0.30 `build_runtime` 与 `run_fragment`，不绕过受管 SDK 直接调用世界。每个活跃成员固定执行三个 fixture 动作：读取最长字符数的合法 180 行冻结源码页；读取事先确认不存在的路径以获得真实拒绝；在下一请求确实原生编码了该错误之后执行 `staff_done`。四个单执行者案例每组合三次请求，两个双成员案例每组合六次，共 6×3=18 组合、72 次请求。首个 Devstral 案例先过完整三步门，再接续其余17组合；它计入18且没有重复运行。

读取页固定为 `src/marshmallow/fields.py` 第122行起180行，是按公共冻结文件文本搜索得到的压力页。缺失路径为 `cpu_native_template_definitely_missing_v030.py`；实际 WorldCore 回执为 `ok=false`、`ValueError`、`Path must be an indexed working file`。脚本没有生成该回执，而是核对捕获的真实返回与后续请求完全一致。Repair 案例自身要求的初始公开测试仍由真实环境构造执行，并保留为环境准备；没有额外执行独立验收或把控制动作记作自主修复。

公共 SDK 使用 `first_and_latest_observation_last4_tool_rounds`，保留首个及最新真实 observation、至多四个完整工具轮。之后继续使用既有 `project_software_request`，严格16,384上下文、2,048输出预留，只允许移除较早完整工具轮。此次该容量投影 **未触发移除**，没有降低工具行数上限、截短源码或改动输出预留。

Qwen3.5-9B 使用已冻结非thinking XML 工具格式，SWE-Next 使用 Qwen2 JSON 工具格式。Devstral 用官方 mistral-common v13 `encode_assistant_message` 得到原生输出 token IDs，并经实际 decoder/parser 核对名称与参数，不使用旧 v7 工具数组。Devstral 的输入保留官方 native encoder 返回的 token IDs，审计文本不会重新分词替代原生输入。

## 原生消息阻断与修订边界

首次完整矩阵中，当前9B与SWE分别6/6通过；Devstral完成首个读取后，官方 validator 拒绝真实 SDK 序列中的 `tool → user`，精确异常为 `Unexpected role 'user' after role 'tool'`。其六个组合都没有走到错误回流资格。该失败原件仍在 `runs/v030-controls/native-templates/`，没有回改；更早的源码前缀选择错误发生在任何脚本化SDK调用之前，另存 `native-templates-attempt-0-path-error/`。

新公共 SDK 保留初始真实 user，使官方 v13 的工具定义有稳定首user位置。Mistral专用原生投影把工具结果之后的真实user消息放入标明来源的tool envelope：`original_tool_message` 与 `subsequent_user_messages` 分别保存原role、完整原文、原索引；投影另记每条原消息hash及原生消息对应索引。它没有制造assistant发言、替换工具结果、删除观察或改动已采样输出token。原始SDK request与实际native消息分开保存。

恢复版不只检查选择前的 SDK 错误消息：还递归解包**实际交给native encoder的tool内容**，要求世界返回结构完全相等；成功源码读取的回执也执行同样的完整保留检查。这一格式适配有明确载体差异，因此本轮是运行组合选择，不能解释为纯参数量对照。

## 各案例容量结果

表中为每组合所有请求的最小余量，即 `16,384 − 2,048 − 实际输入token数`；数值越大只表示这个有限fixture下剩余上下文越多，不是工作能力指标。

| 开发案例 | 每组合脚本请求 | 当前9B最小余量 | SWE-Next-14B最小余量 | Devstral最小余量 |
|---|---:|---:|---:|---:|
| `mm-nested-order-import` | 3 | 4,391 | 4,538 | 4,097 |
| `mm-event-projection` | 3 | 4,456 | 4,602 | 4,187 |
| `mm-envelope-hook-repair` | 3 | 3,210 | 3,375 | 2,839 |
| `mm-nested-error-repair` | 3 | 3,269 | 3,415 | 2,858 |
| `mm-ledger-rootgoal` | 6 | 3,692 | 3,848 | 3,374 |
| `mm-settings-rootgoal` | 6 | 3,795 | 3,941 | 3,467 |

全部实际请求的最大输入为 **11,497 token**，预留输出后最小余量 **2,839 token**。这不保证未来任意完整工作轨迹都能装入；真实运行仍需每请求容量门与明确容量停止。

## 必要核验与限制

执行环境为指定 resident Python，Transformers **5.17.0**、mistral-common **1.7.0**。报告保存开始/结束的源码身份，以及直接实现、六案例资产、实际冻结上游文件与三组tokenizer文件的hash；运行中所需文件及全源码树均未变化。当前脚本的Ruff检查通过，没有重跑其他来源或WorldCore测试套件。

本次 SDK 事件里沿用了系统的 model_call 命名，但来源是明确 fixture transport，不能据事件数声称调用真实模型。缺少实际采样token trace与行为概率，加上案例声明禁止学习，不能将这72次控制请求纳入在线经验或构造训练目标。真实采样、学习概率一致性、完整反向、保存重载、新权重回流及单卡容量仍须由后续真实模型资格分别验证。
