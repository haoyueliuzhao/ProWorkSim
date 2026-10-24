# v057 执行修复集成与资格边界

日期：2026-10-24。用户要求处理v056故障分析发现的问题。本记录说明新执行代码的集成与CPU验收；评分环境修复和原候选补评另行记账。

## 已实现的执行改动

新的生产入口为`tools/run_ref_budget_episode_v057.py`，宿主运行器为`software_benchmark_runner_v057.py`，实际启动`tools/run_ref_budget_controller_v057.py`。生产控制器使用原生OpenHands五工具工厂，并同时接入以下两项修订：

1. **响应字段规范化。** 原始vLLM响应先照常存档和结算；只在交给SDK的副本中将`reasoning`映射为`reasoning_content`。正文、工具调用和用量不改变；不重试请求。双字段内容冲突明确拒绝。
2. **公开工作指南与一次有限纠正。** 初始消息保留原问题正文，追加通用需求覆盖、公开验证、终端命令规则和该仓库的公开测试入口。只有SDK进入stuck且预算、次数、时间及账单仍允许时，才在同一会话中追加一次纠正；再次stuck即结束。原生检测器、工具权限和账本均保留，不创建第二个Agent。

公开指南从原固定registry与对应基线映射中投影`cwd`、解释器和仓库级测试入口。拒绝不同任务、非公开来源、答案选择的文件或隐藏测试来源；映射详情、哈希及评分信息不进入模型。入口存在不代表完整测试套件已通过，也不强制每次运行全部公开测试。

一般修复检查要求针对问题提及的不同接口和边界进行检查，明确区分“测试通过”“测试未运行”“收集或依赖错误”。这属于新执行条件中的通用指导，不能保证模型不再漏修，也没有人工改写任何历史候选。

## 摘要异常的闭合保护

实际SDK的SOFT摘要会吞掉某些completion异常并退回原历史。若冲突响应已经结算用量，仅检查账单完整性不足以发现这类投影错误。因此新投影版本增加Agent和condenser共享的持续故障标记：投影失败后，后续计数和生成均拒绝，控制器在可信闭合前再次检查；错误归为技术未知，原用量保留。

此修订为`v057-exact-native-response-projection-r2-fault-guard`。前一版CPU控制使用的源码和根绑定已经精确归档，不能把r1、r2说成未发生源码变化。

## 条件与旧实验隔离

新执行组固定标识为`REF_REPAIRED_V057`。槽位必须使用`v057:`前缀、`v057-ref-repaired-slots-r1`题单格式及匹配的`v057-ref-repaired-authorization-r1`授权清单。旧v056槽不能送入该运行器重放。

原四档数值条件作为独立引用复用：原始Qwen3.5-9B、思考、131,072上下文、32,768输出、原采样、512尝试／决定、6小时软与6.5小时硬期限保持。原累计token额度不会因纠正而重置；新增指令和纠正消息本身进入真实输入并计费。新的响应历史和指令可能改变后续动作，不能将其冒称完全相同的原REF条件。

为了复用已验证的rootfs所有权和清理助手，新回合物理目录位于`runs/software-benchmark-v056/execution-v057/`；其slot、claims、结果版本和执行组均独立。运行器还要求当前存活的resident ready身份与PID/start_ticks吻合，不能仅凭旧ready文件启动。

执行策略及完整新来源绑定见`config/v057-native-execution-policy.json`和`artifacts/software-benchmark-v057/execution-repair-r1/binding.json`。具体新模型题单和回合没有在这次代码修复中启动；入口需要后续独立计划与实际环境资格。

共享服务器事故后，当前执行策略修订为`v057-ref-execution-policy-r2-shared-server-hold`，来源封存纳入暂停模块与配置，并刷新实际host runner及controller的哈希。当前`hold=true`，无自动解除；只读绑定校验仍可执行。挂载可见性已恢复，但事故期间工作负载影响和独立安全准入未完成，不能据此启动新模型或评分。旧绑定、策略及暂停配置的精确字节见[修订前档案](../../artifacts/software-benchmark-v057/revisions/pre-hold-seal-r1/index.json)，原CPU控制证据保持其原有版本含义。

## 必要验证

| 验证 | 结果与范围 |
| --- | --- |
| 响应投影边界单测 | 3项通过；包括字段保留、非法或冲突字段拒绝 |
| 实际SDK响应回放 | 同步／异步转换均保留真实旧响应中的8,440及155字符思考；原正文、工具、usage和raw response不变 |
| 执行策略单测 | 2项通过；公开信息与恢复边界 |
| 实际SDK正常路径控制 | 三场景通过：一次stuck纠正后finish；第二次stuck停止；直接使用生产五工具工厂，远程工具RPC为0 |
| 摘要故障增补控制 | 一次实际SOFT摘要冲突控制通过：SDK退回历史后仍不能继续生成或可信闭合；已结算的1次合成响应用量保留 |
| 新旧槽位与来源绑定单测 | 3项通过；拒绝旧命名空间、预算条件／seed替换和不完整来源封存 |

这些是CPU脚本响应或既有响应回放，真实模型、GPU、评分调用均为0，不是新的能力评测。控制r1/r2中的fixture失败也完整保留，最终正常控制为r3；追加fault guard只补测受影响的异常路径，没有重复运行无关模型实验。新实现的针对性Ruff检查通过。

## 证据

- [执行绑定](../../artifacts/software-benchmark-v057/execution-repair-r1/binding.json)
- [响应投影验证](../../artifacts/software-benchmark-v057/reasoning-projection-r1/validation.json)
- [执行策略与生产工厂控制](../../artifacts/software-benchmark-v057/native-execution-repair-r1/validation.json)
- [摘要故障保护](../../artifacts/software-benchmark-v057/fault-guard-r2/validation.json)
- [原执行绑定归档](../../artifacts/software-benchmark-v057/revisions/control-source-r1/index-root-binding.json)

上述实现只能证明机制已接线且通过必要控制，尚不能声称消除了全部循环、修复遗漏或提高了模型正确率。其性能影响须在新版本独立运行中测量，不能补记到v056历史生成结果。
