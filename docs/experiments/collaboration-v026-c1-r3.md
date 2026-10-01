# 资源恢复：5次独立尝试

原中断与未启动状态在R2报告中保留；本文件只记录预声明恢复尝试。

# v0.26 C1：冻结参数协作载体验证

运行状态：`complete`；终态归档：是。

本报告只读原评分、原角色事件及世界边界；没有重新评分或模型调用。本轮检验小型协作载体与沟通条件，不检验参数学习收益、成员经验配置或 ID-VTDO 增量。

预定 5 槽：已知 5，已启动未知 0，未启动 0；已知完整职责 0。未知和未启动均未记作 0。

## 沟通条件与配对结果

| 条件 | 预定 / 已知 / 未知 / 未启动 | 完整职责 | 已知均分 | 全预定完成率 |
|---|---|---|---|---|
| normal | 2 / 2 / 0 / 0 | 0 / 2 | 0.0000 | 0.0000 |
| single_pass | 3 / 3 / 0 / 0 | 0 / 3 | 0.0000 | 0.0000 |

normal − single_pass 的预定完整职责均差：**未知 / 未取得**；可用配对 2/3。已知配对子集描述值：0.0000，不替代缺失的全预定点估计。

single_pass 只限制额外解释性交接；两臂保留 SQL、产物访问、正式交付和复核。因此这一差值也不是“有团队与无团队”比较。

| 成果条款 | normal 达成 / 已知 | single_pass 达成 / 已知 | 全配对达成率差 |
|---|---|---|---|
| 正确源端固定交付 | 0 / 2 | 0 / 3 | 未知 / 未取得 |
| 正确消费端固定交付 | 0 / 2 | 0 / 3 | 未知 / 未取得 |
| 双向消费与最终再验证 | 0 / 2 | 0 / 3 | 未知 / 未取得 |

## 原型、情境与重复

| 分组 | normal 完整 / 已知 | single_pass 完整 / 已知 | 全配对完整职责差 |
|---|---|---|---|
| prototype=unit_pair | 0 / 1 | 0 / 2 | 未知 / 未取得 |
| prototype=demand_pair | 0 / 1 | 0 / 1 | 0.0000 |
| case_id=reciprocal-v26-02 | 0 / 1 | 0 / 2 | 未知 / 未取得 |
| case_id=reciprocal-v26-00 | 0 / 1 | 0 / 1 | 0.0000 |
| repeat_index=0 | 0 / 0 | 0 / 1 | 未知 / 未取得 |
| repeat_index=1 | 0 / 2 | 0 / 2 | 0.0000 |

## 初始反事实实际输入

以下取受限成员第一次真实 model_attempt 请求，直接对完整原字典序列化计算 SHA256。未删除 ID、系统提示、工具、模型标识或任何字段；mapping 顺序也保留。

| 原型 / 条件 / 重复 | 受限成员 | 原始输入比较 | 原请求序号 |
|---|---|---|---|
| unit_pair / single_pass / 0 | consumer | unavailable | 13 |
| demand_pair / normal / 1 | maintainer | unavailable | 3 |
| demand_pair / single_pass / 1 | maintainer | unavailable | 3 |
| unit_pair / normal / 1 | consumer | unavailable | 13 |
| unit_pair / single_pass / 1 | consumer | unavailable | 13 |

这只核对有限初始输入；相同输入不自动证明后续使用，差异也需结合此前伙伴动作解释。未观察到结构化资料回执，不代表自然语言中绝无披露。

## 逐槽工作与协作证据

| 槽 | 状态 | 分数 / 完整职责 | 请求 / 响应 / 工具拒绝 | 角色停止 |
|---|---|---|---|---|
| c1-02-single_pass-0 | known | 0.0000 / 否 | 48 / 47 / 12 | consumer: model_budget_exhausted; maintainer: model_budget_exhausted |
| c1-00-normal-1 | known | 0.0000 / 否 | 46 / 45 / 10 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-00-single_pass-1 | known | 0.0000 / 否 | 48 / 48 / 11 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-02-normal-1 | known | 0.0000 / 否 | 48 / 48 / 13 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-02-single_pass-1 | known | 0.0000 / 否 | 48 / 48 / 23 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |

### c1-02-single_pass-0

- 源端正确固定构建：原评分未确认。
- 消费端正确固定构建：原评分未确认。
- 消费端固定版本检查：原评分未确认。
- 维护者最终再验证：原评分未确认。
- 未达成或未知原因：正确源端固定交付；正确消费端固定交付；双向消费与最终再验证。
- seq 53，maintainer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 87，consumer → handoff_information，工具返回=True。
- seq 203，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 249，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 261，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 284，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 353，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 364，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 376，maintainer → sql_build，工具返回=True，SQL执行=success。
- seq 399，maintainer → submit，工具返回=True。
- seq 422，maintainer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 491，maintainer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- 协作层次 seq 87：运输/可访问证据 2 条；maintainer entity_in_input 进入seq 94的生成输入；maintainer reference_in_input 进入seq 94的生成输入；maintainer exact_read_content_in_later_input 进入seq 140的生成输入；显式引用使用 3 条。计数仅作索引，不作协作收益。
- 协作层次 seq 399：运输/可访问证据 0 条；consumer entity_in_input 进入seq 404的生成输入；显式引用使用 1 条。计数仅作索引，不作协作收益。
- [原角色事件](/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v026-c1-r3/recovery/actual/c1-02-single_pass-0/runtime.json)；评分和边界 SHA 见 JSON。

### c1-00-normal-1

- 源端正确固定构建：原评分未确认。
- 消费端正确固定构建：原评分未确认。
- 消费端固定版本检查：原评分未确认。
- 维护者最终再验证：原评分未确认。
- 未达成或未知原因：正确源端固定交付；正确消费端固定交付；双向消费与最终再验证。
- seq 53，maintainer → request_information，工具返回=True。
- seq 64，consumer → handoff_information，工具返回=True。
- seq 88，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 123，maintainer → sql_query，工具返回=False，错误={"message": "SQL code/output alias is outside this work's declared execution scope", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "sql_query"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 180，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 226，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 307，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 318，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 330，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Exports must select actual model names", "phase": "model:interface_meta", "type": "ValueError"}。
- seq 422，maintainer → sql_build，工具返回=True，SQL执行=success。
- seq 433，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 468，maintainer → submit，工具返回=True。
- 协作层次 seq 53：运输/可访问证据 0 条；consumer entity_in_input 进入seq 58的生成输入；显式引用使用 1 条。计数仅作索引，不作协作收益。
- 协作层次 seq 64：运输/可访问证据 3 条；maintainer entity_in_input 进入seq 71的生成输入；maintainer reference_in_input 进入seq 71的生成输入；maintainer exact_read_content_in_later_input 进入seq 94的生成输入；maintainer exact_read_content_in_later_input 进入seq 462的生成输入；显式引用使用 2 条。计数仅作索引，不作协作收益。
- 协作层次 seq 468：运输/可访问证据 0 条；consumer entity_in_input 进入seq 473的生成输入；显式引用使用 1 条。计数仅作索引，不作协作收益。
- [原角色事件](/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v026-c1-r3/recovery/actual/c1-00-normal-1/runtime.json)；评分和边界 SHA 见 JSON。

### c1-00-single_pass-1

- 源端正确固定构建：原评分未确认。
- 消费端正确固定构建：原评分未确认。
- 消费端固定版本检查：原评分未确认。
- 维护者最终再验证：原评分未确认。
- 未达成或未知原因：正确源端固定交付；正确消费端固定交付；双向消费与最终再验证。
- seq 64，consumer → handoff_information，工具返回=True。
- seq 88，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 157，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 226，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 238，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 261，maintainer → adopt_version，工具返回=False，错误={"message": "Fixed adoption requires a new work declaration", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt_version"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 295，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 330，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Code declares only models/tests/config", "phase": "load_inputs", "type": "ValueError"}。
- seq 364，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 399，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Code declares only models/tests/config", "phase": "load_inputs", "type": "ValueError"}。
- seq 433，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 445，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Code declares only models/tests/config", "phase": "load_inputs", "type": "ValueError"}。
- seq 502，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 537，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Model name duplicates an input or model", "phase": "model:demand_meta", "type": "ValueError"}。
- 协作层次 seq 64：运输/可访问证据 3 条；maintainer entity_in_input 进入seq 71的生成输入；maintainer reference_in_input 进入seq 71的生成输入；maintainer exact_read_content_in_later_input 进入seq 94的生成输入；maintainer exact_read_content_in_later_input 进入seq 140的生成输入；显式引用使用 2 条。计数仅作索引，不作协作收益。
- [原角色事件](/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v026-c1-r3/recovery/actual/c1-00-single_pass-1/runtime.json)；评分和边界 SHA 见 JSON。

### c1-02-normal-1

- 源端正确固定构建：原评分未确认。
- 消费端正确固定构建：原评分未确认。
- 消费端固定版本检查：原评分未确认。
- 维护者最终再验证：原评分未确认。
- 未达成或未知原因：正确源端固定交付；正确消费端固定交付；双向消费与最终再验证。
- seq 53，maintainer → request_information，工具返回=True。
- seq 64，consumer → handoff_information，工具返回=True。
- seq 134，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 180，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 192，maintainer → sql_query，工具返回=False，错误={"message": "SQL code/output alias is outside this work's declared execution scope", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "sql_query"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 215，maintainer → sql_build，工具返回=False，错误={"message": "SQL input requires this work's exact adoption: source_contract", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "sql_build"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 272，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 284，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Code declares only models/tests/config", "phase": "load_inputs", "type": "ValueError"}。
- seq 307，maintainer → submit，工具返回=False，错误={"message": "Work is not open for submission by this actor", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "submit"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 353，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Code declares only models/tests/config", "phase": "load_inputs", "type": "ValueError"}。
- seq 399，maintainer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 422，maintainer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 433，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 445，maintainer → submit，工具返回=False，错误={"message": "Work is not open for submission by this actor", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "submit"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 468，maintainer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 502，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- 协作层次 seq 53：运输/可访问证据 0 条；consumer entity_in_input 进入seq 58的生成输入；显式引用使用 0 条。计数仅作索引，不作协作收益。
- 协作层次 seq 64：运输/可访问证据 3 条；maintainer entity_in_input 进入seq 71的生成输入；maintainer reference_in_input 进入seq 71的生成输入；maintainer exact_read_content_in_later_input 进入seq 94的生成输入；maintainer exact_read_content_in_later_input 进入seq 140的生成输入；显式引用使用 5 条。计数仅作索引，不作协作收益。
- [原角色事件](/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v026-c1-r3/recovery/actual/c1-02-normal-1/runtime.json)；评分和边界 SHA 见 JSON。

### c1-02-single_pass-1

- 源端正确固定构建：原评分未确认。
- 消费端正确固定构建：原评分未确认。
- 消费端固定版本检查：原评分未确认。
- 维护者最终再验证：原评分未确认。
- 未达成或未知原因：正确源端固定交付；正确消费端固定交付；双向消费与最终再验证。
- seq 53，maintainer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 214，maintainer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 225，consumer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 283，maintainer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 352，maintainer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 386，consumer → handoff_information，工具返回=True。
- seq 456，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 491，maintainer → sql_build，工具返回=False，错误={"message": "SQL input requires this work's exact adoption: source_contract", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "sql_build"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- 协作层次 seq 386：运输/可访问证据 2 条；maintainer entity_in_input 进入seq 393的生成输入；maintainer reference_in_input 进入seq 393的生成输入；maintainer exact_read_content_in_later_input 进入seq 416的生成输入；显式引用使用 1 条。计数仅作索引，不作协作收益。
- [原角色事件](/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v026-c1-r3/recovery/actual/c1-02-single_pass-1/runtime.json)；评分和边界 SHA 见 JSON。

## 参数身份、成本与限制

全部已观察 worker 的 actor/critic 实际步数增量均为 0：是。
已知闭合槽的完整学习状态与 RNG 保护：5 个通过，0 个缺失或失败。这是保存的 guard 结果，报告不重新加载张量。

| Worker | Actor 前→后 | Critic 前→后 | 完整恢复/原标记不变 | 已终止 GPU 小时 |
|---|---|---|---|---|
| recovery | 3→3 | 3→3 | 是 / 是 | 0.7102 |

1 个 worker 已终止阶段成本合计 **0.7102 GPU 小时**；快照中尚在运行的额外成本 0.0000 GPU 小时。加载、异常和停止耗时保留；并行墙钟时间未当作 GPU 小时。

实际请求 238；响应 236；其中带实际输出 token trace 236；上下文拒绝 2；工具拒绝 69。

本轮没有参数学习或经验配置干预。消息更多、工具成功更多或出现闭环，都不能单独证明成员经历更值得训练。C2/C3 需要另行冻结当前策略支持及共同学习状态的配置对照；本报告不自动启动后继。

全部源路径、SHA、逐组件结果、精确初始输入比较、动作序号和各协作层次保存在同名 JSON。
