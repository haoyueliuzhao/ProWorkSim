# 资源恢复后的16个逻辑槽描述性汇总

本表按事前声明的5个恢复槽合并结果，不覆盖R2原始报告。原中断仍是一次未知尝试；恢复属于新尝试，全部成本计入。不能将此表伪称为无中断的原16次运行。

# v0.26 C1：冻结参数协作载体验证

运行状态：`recovered_descriptive_view`；终态归档：是。

本报告只读原评分、原角色事件及世界边界；没有重新评分或模型调用。本轮检验小型协作载体与沟通条件，不检验参数学习收益、成员经验配置或 ID-VTDO 增量。

预定 16 槽：已知 16，已启动未知 0，未启动 0；已知完整职责 0。未知和未启动均未记作 0。

## 沟通条件与配对结果

| 条件 | 预定 / 已知 / 未知 / 未启动 | 完整职责 | 已知均分 | 全预定完成率 |
|---|---|---|---|---|
| normal | 8 / 8 / 0 / 0 | 0 / 8 | 0.0000 | 0.0000 |
| single_pass | 8 / 8 / 0 / 0 | 0 / 8 | 0.0000 | 0.0000 |

normal − single_pass 的预定完整职责均差：**0.0000**；可用配对 8/8。已知配对子集描述值：0.0000，不替代缺失的全预定点估计。

single_pass 只限制额外解释性交接；两臂保留 SQL、产物访问、正式交付和复核。因此这一差值也不是“有团队与无团队”比较。

| 成果条款 | normal 达成 / 已知 | single_pass 达成 / 已知 | 全配对达成率差 |
|---|---|---|---|
| 正确源端固定交付 | 0 / 8 | 0 / 8 | 0.0000 |
| 正确消费端固定交付 | 0 / 8 | 0 / 8 | 0.0000 |
| 双向消费与最终再验证 | 0 / 8 | 0 / 8 | 0.0000 |

## 原型、情境与重复

| 分组 | normal 完整 / 已知 | single_pass 完整 / 已知 | 全配对完整职责差 |
|---|---|---|---|
| prototype=demand_pair | 0 / 4 | 0 / 4 | 0.0000 |
| prototype=unit_pair | 0 / 4 | 0 / 4 | 0.0000 |
| case_id=reciprocal-v26-00 | 0 / 2 | 0 / 2 | 0.0000 |
| case_id=reciprocal-v26-01 | 0 / 2 | 0 / 2 | 0.0000 |
| case_id=reciprocal-v26-02 | 0 / 2 | 0 / 2 | 0.0000 |
| case_id=reciprocal-v26-03 | 0 / 2 | 0 / 2 | 0.0000 |
| repeat_index=0 | 0 / 4 | 0 / 4 | 0.0000 |
| repeat_index=1 | 0 / 4 | 0 / 4 | 0.0000 |

## 初始反事实实际输入

以下取受限成员第一次真实 model_attempt 请求，直接对完整原字典序列化计算 SHA256。未删除 ID、系统提示、工具、模型标识或任何字段；mapping 顺序也保留。

| 原型 / 条件 / 重复 | 受限成员 | 原始输入比较 | 原请求序号 |
|---|---|---|---|
| demand_pair / normal / 0 | maintainer | equal | 3, 3 |
| demand_pair / single_pass / 0 | maintainer | equal | 3, 3 |
| unit_pair / normal / 0 | consumer | equal | 13, 13 |
| unit_pair / single_pass / 0 | consumer | equal | 13, 13 |
| demand_pair / normal / 1 | maintainer | equal | 3, 3 |
| demand_pair / single_pass / 1 | maintainer | equal | 3, 3 |
| unit_pair / normal / 1 | consumer | equal | 13, 13 |
| unit_pair / single_pass / 1 | consumer | equal | 13, 13 |

这只核对有限初始输入；相同输入不自动证明后续使用，差异也需结合此前伙伴动作解释。未观察到结构化资料回执，不代表自然语言中绝无披露。

## 逐槽工作与协作证据

| 槽 | 状态 | 分数 / 完整职责 | 请求 / 响应 / 工具拒绝 | 角色停止 |
|---|---|---|---|---|
| c1-00-normal-0 | known | 0.0000 / 否 | 48 / 48 / 15 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-00-single_pass-0 | known | 0.0000 / 否 | 48 / 48 / 16 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-01-normal-0 | known | 0.0000 / 否 | 48 / 48 / 15 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-01-single_pass-0 | known | 0.0000 / 否 | 47 / 46 / 9 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-02-normal-0 | known | 0.0000 / 否 | 47 / 46 / 12 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-02-single_pass-0 | known | 0.0000 / 否 | 48 / 47 / 12 | consumer: model_budget_exhausted; maintainer: model_budget_exhausted |
| c1-03-normal-0 | known | 0.0000 / 否 | 48 / 48 / 15 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-03-single_pass-0 | known | 0.0000 / 否 | 45 / 44 / 14 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-00-normal-1 | known | 0.0000 / 否 | 46 / 45 / 10 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-00-single_pass-1 | known | 0.0000 / 否 | 48 / 48 / 11 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-01-normal-1 | known | 0.0000 / 否 | 47 / 46 / 15 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-01-single_pass-1 | known | 0.0000 / 否 | 48 / 48 / 24 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-02-normal-1 | known | 0.0000 / 否 | 48 / 48 / 13 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-02-single_pass-1 | known | 0.0000 / 否 | 48 / 48 / 23 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-03-normal-1 | known | 0.0000 / 否 | 48 / 48 / 18 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |
| c1-03-single_pass-1 | known | 0.0000 / 否 | 48 / 48 / 25 | maintainer: model_budget_exhausted; consumer: model_budget_exhausted |

### c1-00-normal-0

- 源端正确固定构建：原评分未确认。
- 消费端正确固定构建：原评分未确认。
- 消费端固定版本检查：原评分未确认。
- 维护者最终再验证：原评分未确认。
- 未达成或未知原因：正确源端固定交付；正确消费端固定交付；双向消费与最终再验证。
- seq 53，maintainer → request_information，工具返回=True。
- seq 76，maintainer → handoff_information，工具返回=False，错误={"message": "Handoff requires the declared manual provider and exact work lineage", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 122，maintainer → request_information，工具返回=True。
- seq 133，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 191，maintainer → request_information，工具返回=True。
- seq 202，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 214，maintainer → handoff_information，工具返回=False，错误={"message": "Handoff requires the declared manual provider and exact work lineage", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 248，consumer → handoff_information，工具返回=True。
- seq 295，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 399，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Catalog Error: Table with name source_meta does not exist!\nDid you mean \"sqlite_schema\"?\n\nLINE 1: ... TABLE \"interface_meta\" AS SELECT 'pence' as amount_unit FROM source_meta\n                                                                         ^", "phase": "model:interface_meta", "type": "CatalogException"}。
- seq 410，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 456，consumer → handoff_information，工具返回=False，错误={"message": "Handoff identity cannot be reused for different evidence or recipients", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 502，consumer → handoff_information，工具返回=True。
- seq 515，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Code declares only models/tests/config", "phase": "load_inputs", "type": "ValueError"}。
- seq 549，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- 协作层次 seq 53：运输/可访问证据 0 条；consumer entity_in_input 进入seq 58的生成输入；显式引用使用 1 条。计数仅作索引，不作协作收益。
- 协作层次 seq 122：运输/可访问证据 0 条；consumer entity_in_input 进入seq 127的生成输入；显式引用使用 1 条。计数仅作索引，不作协作收益。
- 协作层次 seq 191：运输/可访问证据 0 条；consumer entity_in_input 进入seq 196的生成输入；显式引用使用 0 条。计数仅作索引，不作协作收益。
- 协作层次 seq 248：运输/可访问证据 3 条；maintainer entity_in_input 进入seq 255的生成输入；maintainer reference_in_input 进入seq 255的生成输入；maintainer exact_read_content_in_later_input 进入seq 278的生成输入；maintainer exact_read_content_in_later_input 进入seq 324的生成输入；显式引用使用 1 条。计数仅作索引，不作协作收益。
- 协作层次 seq 502：运输/可访问证据 1 条；maintainer entity_in_input 进入seq 509的生成输入；maintainer reference_in_input 进入seq 509的生成输入；显式引用使用 0 条。计数仅作索引，不作协作收益。
- [原角色事件](/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v026-c1-r2/worker-0/actual/c1-00-normal-0/runtime.json)；评分和边界 SHA 见 JSON。

### c1-00-single_pass-0

- 源端正确固定构建：原评分未确认。
- 消费端正确固定构建：原评分未确认。
- 消费端固定版本检查：原评分未确认。
- 维护者最终再验证：原评分未确认。
- 未达成或未知原因：正确源端固定交付；正确消费端固定交付；双向消费与最终再验证。
- seq 41，consumer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 110，consumer → handoff_information，工具返回=True。
- seq 215，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Catalog Error: Table with name source_meta does not exist!\nDid you mean \"sqlite_schema\"?\n\nLINE 1: CREATE TABLE \"interface_meta\" AS SELECT amount_unit FROM source_meta\n                                                                 ^", "phase": "model:interface_meta", "type": "CatalogException"}。
- seq 238，maintainer → sql_query，工具返回=False，错误={"message": "SQL code/output alias is outside this work's declared execution scope", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "sql_query"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 295，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 318，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 376，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 387，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 456，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 491，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Catalog Error: Table with name source_meta does not exist!\nDid you mean \"sqlite_schema\"?\n\nLINE 1: CREATE TABLE \"interface_meta\" AS SELECT amount_unit FROM source_meta\n                                                                 ^", "phase": "model:interface_meta", "type": "CatalogException"}。
- seq 548，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- 协作层次 seq 110：运输/可访问证据 3 条；maintainer entity_in_input 进入seq 117的生成输入；maintainer reference_in_input 进入seq 117的生成输入；maintainer exact_read_content_in_later_input 进入seq 140的生成输入；maintainer exact_read_content_in_later_input 进入seq 301的生成输入；显式引用使用 4 条。计数仅作索引，不作协作收益。
- [原角色事件](/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v026-c1-r2/worker-0/actual/c1-00-single_pass-0/runtime.json)；评分和边界 SHA 见 JSON。

### c1-01-normal-0

- 源端正确固定构建：原评分未确认。
- 消费端正确固定构建：原评分未确认。
- 消费端固定版本检查：原评分未确认。
- 维护者最终再验证：原评分未确认。
- 未达成或未知原因：正确源端固定交付；正确消费端固定交付；双向消费与最终再验证。
- seq 41，consumer → handoff_information，工具返回=True。
- seq 65，consumer → request_information，工具返回=True。
- seq 88，consumer → handoff_information，工具返回=False，错误={"message": "Handoff requires the declared manual provider and exact work lineage", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 146，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Catalog Error: Table with name \"raw.retail\" does not exist because schema \"raw\" does not exist.\n\nLINE 3:   FROM raw.retail\n               ^", "phase": "model:m_invoice_view", "type": "CatalogException"}。
- seq 192，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 203，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 215，maintainer → adopt_version，工具返回=False，错误={"message": "Fixed adoption requires a new work declaration", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt_version"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 261，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Catalog Error: Table with name \"raw.retail\" does not exist because schema \"raw\" does not exist.\n\nLINE 2: FROM raw.retail r\n             ^", "phase": "model:invoice_view", "type": "CatalogException"}。
- seq 272，consumer → request_information，工具返回=True。
- seq 284，maintainer → sql_query，工具返回=False，错误={"message": "SQL code/output alias is outside this work's declared execution scope", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "sql_query"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 318，consumer → handoff_information，工具返回=True。
- seq 341，consumer → request_information，工具返回=True。
- seq 364，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 376，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 422，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Catalog Error: Table with name source_meta does not exist!\nDid you mean \"sqlite_schema\"?\n\nLINE 1: CREATE TABLE \"interface_meta\" AS SELECT amount_unit FROM source_meta\n                                                                 ^", "phase": "model:interface_meta", "type": "CatalogException"}。
- seq 433，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 468，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Exports must select actual model names", "phase": "model:interface_meta", "type": "ValueError"}。
- seq 479，consumer → request_information，工具返回=True。
- seq 502，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 525，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- 协作层次 seq 41：运输/可访问证据 3 条；maintainer entity_in_input 进入seq 48的生成输入；maintainer reference_in_input 进入seq 48的生成输入；maintainer exact_read_content_in_later_input 进入seq 94的生成输入；maintainer exact_read_content_in_later_input 进入seq 117的生成输入；显式引用使用 3 条。计数仅作索引，不作协作收益。
- 协作层次 seq 65：运输/可访问证据 0 条；maintainer entity_in_input 进入seq 71的生成输入；显式引用使用 0 条。计数仅作索引，不作协作收益。
- 协作层次 seq 272：运输/可访问证据 0 条；maintainer entity_in_input 进入seq 278的生成输入；显式引用使用 0 条。计数仅作索引，不作协作收益。
- 协作层次 seq 318：运输/可访问证据 1 条；maintainer entity_in_input 进入seq 324的生成输入；maintainer reference_in_input 进入seq 324的生成输入；显式引用使用 3 条。计数仅作索引，不作协作收益。
- 协作层次 seq 341：运输/可访问证据 0 条；maintainer entity_in_input 进入seq 347的生成输入；显式引用使用 0 条。计数仅作索引，不作协作收益。
- 协作层次 seq 479：运输/可访问证据 0 条；maintainer entity_in_input 进入seq 485的生成输入；显式引用使用 0 条。计数仅作索引，不作协作收益。
- [原角色事件](/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v026-c1-r2/worker-1/actual/c1-01-normal-0/runtime.json)；评分和边界 SHA 见 JSON。

### c1-01-single_pass-0

- 源端正确固定构建：原评分未确认。
- 消费端正确固定构建：原评分未确认。
- 消费端固定版本检查：原评分未确认。
- 维护者最终再验证：原评分未确认。
- 未达成或未知原因：正确源端固定交付；正确消费端固定交付；双向消费与最终再验证。
- seq 41，consumer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 110，consumer → handoff_information，工具返回=True。
- seq 134，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 249，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 339，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 351，maintainer → sql_build，工具返回=True，SQL执行=success。
- seq 374，maintainer → submit，工具返回=True。
- seq 397，maintainer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 530，consumer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Code needs one to eight models", "phase": "load_inputs", "type": "ValueError"}。
- 协作层次 seq 110：运输/可访问证据 4 条；maintainer entity_in_input 进入seq 117的生成输入；maintainer reference_in_input 进入seq 117的生成输入；maintainer exact_read_content_in_later_input 进入seq 140的生成输入；maintainer exact_read_content_in_later_input 进入seq 186的生成输入；maintainer exact_read_content_in_later_input 进入seq 322的生成输入；显式引用使用 4 条。计数仅作索引，不作协作收益。
- 协作层次 seq 374：运输/可访问证据 0 条；consumer entity_in_input 进入seq 379的生成输入；显式引用使用 2 条。计数仅作索引，不作协作收益。
- [原角色事件](/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v026-c1-r2/worker-1/actual/c1-01-single_pass-0/runtime.json)；评分和边界 SHA 见 JSON。

### c1-02-normal-0

- 源端正确固定构建：原评分未确认。
- 消费端正确固定构建：原评分未确认。
- 消费端固定版本检查：原评分未确认。
- 维护者最终再验证：原评分未确认。
- 未达成或未知原因：正确源端固定交付；正确消费端固定交付；双向消费与最终再验证。
- seq 30，maintainer → adopt，工具返回=False，错误={"message": "Exact object version is not shared with this actor and project", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 41，consumer → handoff_information，工具返回=True。
- seq 65，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 134，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 157，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 169，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 226，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 284，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Code declares only models/tests/config", "phase": "load_inputs", "type": "ValueError"}。
- seq 295，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 318，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 330，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Catalog Error: Table with name raw does not exist!\nDid you mean \"raw_customers\"?\n\nLINE 3:   FROM raw\n               ^", "phase": "model:invoice_view", "type": "CatalogException"}。
- seq 364，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 376，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Catalog Error: Table with name source_meta does not exist!\nDid you mean \"sqlite_schema\"?\n\nLINE 1: ... TABLE \"interface_meta\" AS SELECT 'GBP' AS amount_unit FROM source_meta\n                                                                       ^", "phase": "model:interface_meta", "type": "CatalogException"}。
- seq 387，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 410，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 422，maintainer → sql_build，工具返回=True，SQL执行=success。
- seq 445，maintainer → submit，工具返回=True。
- seq 534，consumer → sql_query，工具返回=False，错误={"message": "SQL code/output alias is outside this work's declared execution scope", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "sql_query"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- 协作层次 seq 41：运输/可访问证据 3 条；maintainer entity_in_input 进入seq 48的生成输入；maintainer reference_in_input 进入seq 48的生成输入；maintainer exact_read_content_in_later_input 进入seq 232的生成输入；maintainer exact_read_content_in_later_input 进入seq 485的生成输入；显式引用使用 1 条。计数仅作索引，不作协作收益。
- 协作层次 seq 445：运输/可访问证据 0 条；consumer entity_in_input 进入seq 450的生成输入；显式引用使用 2 条。计数仅作索引，不作协作收益。
- [原角色事件](/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v026-c1-r2/worker-0/actual/c1-02-normal-0/runtime.json)；评分和边界 SHA 见 JSON。

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

### c1-03-normal-0

- 源端正确固定构建：原评分未确认。
- 消费端正确固定构建：原评分未确认。
- 消费端固定版本检查：原评分未确认。
- 维护者最终再验证：原评分未确认。
- 未达成或未知原因：正确源端固定交付；正确消费端固定交付；双向消费与最终再验证。
- seq 30，maintainer → adopt，工具返回=False，错误={"message": "Exact object version is not shared with this actor and project", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 41，consumer → handoff_information，工具返回=True。
- seq 65，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 134，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 169，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 203，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 238，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 272，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 284，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 330，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 353，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 399，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 410，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 468，maintainer → sql_build，工具返回=True，SQL执行=success。
- seq 479，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 491，maintainer → submit，工具返回=True。
- 协作层次 seq 41：运输/可访问证据 3 条；maintainer entity_in_input 进入seq 48的生成输入；maintainer reference_in_input 进入seq 48的生成输入；maintainer exact_read_content_in_later_input 进入seq 232的生成输入；maintainer exact_read_content_in_later_input 进入seq 278的生成输入；显式引用使用 3 条。计数仅作索引，不作协作收益。
- 协作层次 seq 491：运输/可访问证据 0 条；consumer entity_in_input 进入seq 496的生成输入；显式引用使用 1 条。计数仅作索引，不作协作收益。
- [原角色事件](/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v026-c1-r2/worker-1/actual/c1-03-normal-0/runtime.json)；评分和边界 SHA 见 JSON。

### c1-03-single_pass-0

- 源端正确固定构建：原评分未确认。
- 消费端正确固定构建：原评分未确认。
- 消费端固定版本检查：原评分未确认。
- 维护者最终再验证：原评分未确认。
- 未达成或未知原因：正确源端固定交付；正确消费端固定交付；双向消费与最终再验证。
- seq 53，maintainer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 87，consumer → handoff_information，工具返回=True。
- seq 180，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 226，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 272，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 284，maintainer → sql_build，工具返回=False，错误={"message": "SQL input requires this work's exact adoption: source_contract", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "sql_build"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 295，consumer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 318，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 376，maintainer → submit，工具返回=True。
- seq 422，maintainer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 475，consumer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 501，consumer → adopt_version，工具返回=False，错误={"message": "Exact object version is not shared with this actor and project", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt_version"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 514，consumer → adopt_version，工具返回=False，错误={"message": "Exact object version is not shared with this actor and project", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt_version"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- 协作层次 seq 87：运输/可访问证据 2 条；maintainer entity_in_input 进入seq 94的生成输入；maintainer reference_in_input 进入seq 94的生成输入；maintainer exact_read_content_in_later_input 进入seq 140的生成输入；显式引用使用 3 条。计数仅作索引，不作协作收益。
- 协作层次 seq 376：运输/可访问证据 0 条；consumer entity_in_input 进入seq 381的生成输入；显式引用使用 1 条。计数仅作索引，不作协作收益。
- [原角色事件](/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v026-c1-r2/worker-1/actual/c1-03-single_pass-0/runtime.json)；评分和边界 SHA 见 JSON。

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

### c1-01-normal-1

- 源端正确固定构建：原评分未确认。
- 消费端正确固定构建：原评分未确认。
- 消费端固定版本检查：原评分未确认。
- 维护者最终再验证：原评分未确认。
- 未达成或未知原因：正确源端固定交付；正确消费端固定交付；双向消费与最终再验证。
- seq 53，maintainer → request_information，工具返回=True。
- seq 87，consumer → handoff_information，工具返回=False，错误={"message": "Handoff requires the declared manual provider and exact work lineage", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 99，maintainer → handoff_information，工具返回=False，错误={"message": "Handoff requires the declared manual provider and exact work lineage", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 110，consumer → handoff_information，工具返回=True。
- seq 238，maintainer → sql_build，工具返回=False，错误={"message": "SQL source must expose explicit typed tables", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "sql_build"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 249，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 261，maintainer → sql_query，工具返回=False，错误={"message": "SQL code/output alias is outside this work's declared execution scope", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "sql_query"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 307，maintainer → sql_build，工具返回=True，SQL执行=execution_error，错误={"message": "Catalog Error: Table with name source_meta does not exist!\nDid you mean \"sqlite_schema\"?\n\nLINE 1: CREATE TABLE \"interface_meta\" AS SELECT amount_unit FROM source_meta\n                                                                 ^", "phase": "model:interface_meta", "type": "CatalogException"}。
- seq 330，maintainer → submit，工具返回=True。
- seq 376，maintainer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 410，consumer → sql_query，工具返回=False，错误={"message": "SQL code/output alias is outside this work's declared execution scope", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "sql_query"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 422，maintainer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 502，consumer → sql_query，工具返回=False，错误={"message": "SQL code/output alias is outside this work's declared execution scope", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "sql_query"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 521，consumer → sql_query，工具返回=False，错误={"message": "Only the exact work owner may execute its SQL query", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "sql_query"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- 协作层次 seq 53：运输/可访问证据 0 条；consumer entity_in_input 进入seq 58的生成输入；显式引用使用 1 条。计数仅作索引，不作协作收益。
- 协作层次 seq 110：运输/可访问证据 2 条；maintainer entity_in_input 进入seq 117的生成输入；maintainer reference_in_input 进入seq 117的生成输入；maintainer exact_read_content_in_later_input 进入seq 140的生成输入；显式引用使用 1 条。计数仅作索引，不作协作收益。
- 协作层次 seq 330：运输/可访问证据 0 条；consumer entity_in_input 进入seq 335的生成输入；显式引用使用 1 条。计数仅作索引，不作协作收益。
- [原角色事件](/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v026-c1-r2/worker-1/actual/c1-01-normal-1/runtime.json)；评分和边界 SHA 见 JSON。

### c1-01-single_pass-1

- 源端正确固定构建：原评分未确认。
- 消费端正确固定构建：原评分未确认。
- 消费端固定版本检查：原评分未确认。
- 维护者最终再验证：原评分未确认。
- 未达成或未知原因：正确源端固定交付；正确消费端固定交付；双向消费与最终再验证。
- seq 87，consumer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 156，consumer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 225，consumer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 248，consumer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 317，consumer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 386，consumer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 444，maintainer → adopt，工具返回=False，错误={"message": "Exact object version is not shared with this actor and project", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 467，maintainer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 501，consumer → handoff_information，工具返回=True。
- 协作层次 seq 501：运输/可访问证据 2 条；maintainer entity_in_input 进入seq 508的生成输入；maintainer reference_in_input 进入seq 508的生成输入；maintainer exact_read_content_in_later_input 进入seq 531的生成输入；显式引用使用 1 条。计数仅作索引，不作协作收益。
- [原角色事件](/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v026-c1-r2/worker-1/actual/c1-01-single_pass-1/runtime.json)；评分和边界 SHA 见 JSON。

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

### c1-03-normal-1

- 源端正确固定构建：原评分未确认。
- 消费端正确固定构建：原评分未确认。
- 消费端固定版本检查：原评分未确认。
- 维护者最终再验证：原评分未确认。
- 未达成或未知原因：正确源端固定交付；正确消费端固定交付；双向消费与最终再验证。
- seq 53，maintainer → request_information，工具返回=True。
- seq 64，consumer → handoff_information，工具返回=True。
- seq 100，maintainer → handoff_information，工具返回=False，错误={"message": "Handoff requires the declared manual provider and exact work lineage", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 111，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 134，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 192，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 203，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 215，maintainer → adopt_version，工具返回=False，错误={"message": "Fixed adoption requires a new work declaration", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt_version"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 226，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 261，maintainer → adopt，工具返回=False，错误={"message": "This exact work already has an adoption; use its version update", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 284，maintainer → adopt_version，工具返回=False，错误={"message": "Fixed adoption requires a new work declaration", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "adopt_version"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 353，maintainer → sql_build，工具返回=True，SQL执行=success。
- seq 376，maintainer → submit，工具返回=False，错误={"message": "Work is not open for submission by this actor", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "submit"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 399，maintainer → handoff_information，工具返回=False，错误={"message": "Handoff requires the declared manual provider and exact work lineage", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 410，consumer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 445，maintainer → submit，工具返回=False，错误={"message": "Work is not open for submission by this actor", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "submit"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 491，maintainer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- seq 537，maintainer → inspect_submission，工具返回=False，错误={"message": "Issue reference must name an actual submission of this work", "rejection": {"category": "unknown", "code": "unclassified_exception", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "inspect_submission"}, "version": "tool-rejection-v0.9"}, "type": "ValueError"}。
- 协作层次 seq 53：运输/可访问证据 0 条；consumer entity_in_input 进入seq 58的生成输入；显式引用使用 0 条。计数仅作索引，不作协作收益。
- 协作层次 seq 64：运输/可访问证据 2 条；maintainer entity_in_input 进入seq 71的生成输入；maintainer reference_in_input 进入seq 71的生成输入；maintainer exact_read_content_in_later_input 进入seq 94的生成输入；显式引用使用 1 条。计数仅作索引，不作协作收益。
- [原角色事件](/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v026-c1-r2/worker-1/actual/c1-03-normal-1/runtime.json)；评分和边界 SHA 见 JSON。

### c1-03-single_pass-1

- 源端正确固定构建：原评分未确认。
- 消费端正确固定构建：原评分未确认。
- 消费端固定版本检查：原评分未确认。
- 维护者最终再验证：原评分未确认。
- 未达成或未知原因：正确源端固定交付；正确消费端固定交付；双向消费与最终再验证。
- seq 53，maintainer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 248，consumer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "consumer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 260，maintainer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 352，maintainer → handoff_information，工具返回=False，错误={"message": "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.", "rejection": {"category": "policy_error", "code": "single_pass_communication", "context": {"action": "project_action", "actor_id": "maintainer", "arguments_type": "dict", "project_id": "TEAM", "tool": "handoff_information"}, "version": "tool-rejection-v0.9"}, "type": "ToolRejection"}。
- seq 455，consumer → handoff_information，工具返回=True。
- 协作层次 seq 455：运输/可访问证据 2 条；maintainer entity_in_input 进入seq 462的生成输入；maintainer reference_in_input 进入seq 462的生成输入；maintainer exact_read_content_in_later_input 进入seq 508的生成输入；显式引用使用 1 条。计数仅作索引，不作协作收益。
- [原角色事件](/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v026-c1-r2/worker-1/actual/c1-03-single_pass-1/runtime.json)；评分和边界 SHA 见 JSON。

## 参数身份、成本与限制

全部已观察 worker 的 actor/critic 实际步数增量均为 0：未知 / 未取得。
已知闭合槽的完整学习状态与 RNG 保护：16 个通过，0 个缺失或失败。这是保存的 guard 结果，报告不重新加载张量。

| Worker | Actor 前→后 | Critic 前→后 | 完整恢复/原标记不变 | 已终止 GPU 小时 |
|---|---|---|---|---|
| original-worker-0 | 3→None | 3→None | 是 / 是 | 0.5744 |
| original-worker-1 | 3→3 | 3→3 | 是 / 是 | 1.1701 |
| recovery-recovery | 3→3 | 3→3 | 是 / 是 | 0.7102 |

3 个 worker 已终止阶段成本合计 **2.4547 GPU 小时**；快照中尚在运行的额外成本 0.0000 GPU 小时。加载、异常和停止耗时保留；并行墙钟时间未当作 GPU 小时。

实际请求 760；响应 754；其中带实际输出 token trace 754；上下文拒绝 6；工具拒绝 247。

本轮没有参数学习或经验配置干预。消息更多、工具成功更多或出现闭环，都不能单独证明成员经历更值得训练。C2/C3 需要另行冻结当前策略支持及共同学习状态的配置对照；本报告不自动启动后继。

全部源路径、SHA、逐组件结果、精确初始输入比较、动作序号和各协作层次保存在同名 JSON。

原C1加载失败另耗 51.144731 GPU秒；本次按每worker向上取整扣除，共 52 秒。原尝试与本恢复已终止部分累计 **2.468925 GPU小时**，本次有效累计预算上限为8 GPU小时。两次加载失败没有产生业务episode，不增加16槽分母。

运行中按用户授权扩展资源时间预算；原模型进程、业务源码、固定槽及原计划引用均保留。新增资源监督和授权引用见JSON的budget_extension。
