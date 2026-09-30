# v0.26 C0：v0.25 原 16 条联合经历的协作证据复核

本报告只读原支持窗口，不调用模型，不重演世界或评分，不更改原 V、Mapper 与支持池。诊断标签仅用于审阅，不进入训练类别。

覆盖 16 条经历、302 次请求、283 次实际生成、258 个世界动作。原合格经历仍只有 train-00-5；原结果不变。

## 证据规则

发出/写入、送达/可访问、进入实际输入、执行使用、再次验证分别保留。首次输入以 projection 中保存的真实请求为准，给出原 team-rollout 的 model_call start 序号与角色 decision index；JSON 另保存 input_event_sequence（可能为空）、call_id 和精确字段路径。

输入匹配仅检查 user/tool 消息的结构化实体或确切版本，不把 assistant 自述当成已经收到信息。因上下文限制未生成的请求仍保留输入证据，但不能视为模型已处理反馈。产物引用可见与完整内容读取分开；B 初始 submission 和 prepared-basis 是继承准备状态，即使其历史 actor_id/origin 写有角色名，也不算当前模型交付。

使用关系限定为明确引用/采用/问题处理等可核对执行证据。反馈之后发生写代码、构建或提交，只列为时间顺序候选；没有受控反事实，不能据此宣称因果作用。问题是否有效直接引用原判定，工具 ok 不替代业务有效性。自然语言的条件化回应不以文本相似度自动判定。交接正文与先前读得的完整 JSON 完全相等仅标为精确全量转发（本批 2 条）；其余摘要或引用交付保留原文，不因此推断内容条件化。

## 16 条概览

| 经历 | 原 R / V | 当前交接 / 绑定回复 | issue：记录 / 原有效 | 当前新固定提交 | 原方法 |
|---|---|---|---|---|---|
| [train-00-0](../reviews/v025-joint-experiences/episodes/train-00-0.html) | 0.2 / False | 1 / 0 | 0 / 0 | 1 | 未映射 |
| [train-01-0](../reviews/v025-joint-experiences/episodes/train-01-0.html) | 0.0 / False | 0 / 0 | 0 / 0 | 0 | 未映射 |
| [train-00-1](../reviews/v025-joint-experiences/episodes/train-00-1.html) | 0.2 / False | 1 / 1 | 0 / 0 | 0 | 未映射 |
| [train-01-1](../reviews/v025-joint-experiences/episodes/train-01-1.html) | 0.0 / False | 0 / 0 | 0 / 0 | 0 | 未映射 |
| [train-00-2](../reviews/v025-joint-experiences/episodes/train-00-2.html) | 0.2 / False | 1 / 0 | 0 / 0 | 0 | 未映射 |
| [train-01-2](../reviews/v025-joint-experiences/episodes/train-01-2.html) | 0.0 / False | 0 / 0 | 1 / 0 | 0 | 未映射 |
| [train-00-3](../reviews/v025-joint-experiences/episodes/train-00-3.html) | 0.2 / False | 1 / 0 | 0 / 0 | 0 | 未映射 |
| [train-01-3](../reviews/v025-joint-experiences/episodes/train-01-3.html) | 0.0 / False | 0 / 0 | 1 / 1 | 0 | 未映射 |
| [train-00-4](../reviews/v025-joint-experiences/episodes/train-00-4.html) | 0.2 / False | 1 / 0 | 0 / 0 | 0 | 未映射 |
| [train-01-4](../reviews/v025-joint-experiences/episodes/train-01-4.html) | 0.0 / False | 0 / 0 | 0 / 0 | 0 | 未映射 |
| [train-00-5](../reviews/v025-joint-experiences/episodes/train-00-5.html) | 1.0 / True | 1 / 0 | 0 / 0 | 1 | a_active_handoff |
| [train-01-5](../reviews/v025-joint-experiences/episodes/train-01-5.html) | 0.0 / False | 0 / 0 | 1 / 0 | 0 | 未映射 |
| [train-00-6](../reviews/v025-joint-experiences/episodes/train-00-6.html) | 0.2 / False | 1 / 0 | 0 / 0 | 0 | 未映射 |
| [train-01-6](../reviews/v025-joint-experiences/episodes/train-01-6.html) | 0.3 / False | 0 / 0 | 1 / 0 | 1 | 未映射 |
| [train-00-7](../reviews/v025-joint-experiences/episodes/train-00-7.html) | 0.2 / False | 1 / 0 | 0 / 0 | 0 | 未映射 |
| [train-01-7](../reviews/v025-joint-experiences/episodes/train-01-7.html) | 0.0 / False | 0 / 0 | 0 / 0 | 0 | 未映射 |

## 关键时序与解释边界

本批当前模型产生的 code/result 等产物版本共 34 个；其中 6 个版本标识进入过对方实际输入，0 个版本的完整内容经实际读取后进入对方输入。这是产物可见性统计，不含已单列的 basis 消息正文，也不把版本目录可见当作产物已被复核。

- **train-00-5**：唯一完整有效 A。提供者一次交接之后由实现者完成后续工作。准确来源、采用与固定产物使用见下表及原 saved_facts；不能据此宣称存在持续双向内容适配。
- **train-00-1**：唯一正式 request_id 绑定的当前交接；请求绑定真实成立，仍不等于实现与完整职责成功。
- **train-01-3**：实现者 #145、#168 写代码早于 reviewer #179 的有效 issue；下一实现者请求 #185 保存了该问题，但因上下文限制未开始生成。不能把前两次修改归因于后来的问题，也没有问题后模型修复或再验证闭环。
- **train-01-6**：issue #131 进入后续实现者输入，后有撤回/改写/构建/新提交，但原 issue 有效性为 False、V 为 False、R=0.3。时间上后续改变与正确新产物均可保留；没有明确问题处理和最终核准，不能提升为有效反馈修复方法。

上述判断不证明协作无用；它说明当前证据的层次与限制。条件化回应、信息的必要性与分配价值，需要后继受控实验分别判断。

## train-00-0

| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |
|---|---|---|---|---|---|
| 资料交接 `handoff-693cdaf1c385027b4fdd1b01`；当前模型，来源 provider；核查接收者 implementer | #30 handoff_information | #36 exact_entity_in_actual_request；#32 applied_environment_handoff | implementer: #36 / decision 2 | #42 read_alias、#103 adopt | 无 |
| 固定产物 `TEAM::build-submission-1`；当前模型，来源 implementer；核查接收者 provider | #194 submit | 未见已送达证据 | provider: 未见 | 无 | 无 |

产物版本的来源与首次内容输入：

| 产物版本 | 来源 / 写入 | 对方首次内容输入 |
|---|---|---|
| code v1 | 继承 | provider: 未见；implementer: #84 / decision 5 |
| code v2 | #116 write_object | provider: 未见 |
| code v3 | #168 write_object | provider: 未见 |
| result v1 | 继承 | provider: 未见；implementer: 未见 |
| result v2 | #181 sql_build | provider: 未见 |
| basis v1 | 继承 | provider: #24 / decision 2；implementer: #58 / decision 3 |
| audit_basis v1 | 继承 | provider: 未见；implementer: 未见 |

诊断标签：one_way_current_material_handoff、not_complete_method_support。

原结果：`{"reward": 0.2, "completed": false, "V": false, "mapper_status": "unmapped", "mapper_class": null}`。

## train-01-0

| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |
|---|---|---|---|---|---|
| 资料交接 `handoff-3a4829408cac58a6fdbf8318`；继承准备，来源 provider；核查接收者 implementer | 采样前 | #2 exact_entity_in_actual_request；start_state_inherited_delivery | implementer: #2 / decision 1 | #53 read_version | 无 |
| 固定产物 `TEAM::build-submission-1`；继承准备，来源 implementer；核查接收者 reviewer | 采样前 | #12 exact_entity_in_actual_request | reviewer: #12 / decision 1 | #18 inspect_submission | 无 |

产物版本的来源与首次内容输入：

| 产物版本 | 来源 / 写入 | 对方首次内容输入 |
|---|---|---|
| code v1 | 继承 | implementer: 未见；reviewer: 未见 |
| code v2 | 继承 | implementer: #93 / decision 5；reviewer: #127 / decision 6 |
| code v3 | #145 write_object | reviewer: 未见 |
| result v1 | 继承 | implementer: 未见；reviewer: 未见 |
| result v2 | 继承 | implementer: #116 / decision 6；reviewer: #150 / decision 7 |
| result v3 | #167 sql_build | reviewer: 未见 |
| basis v1 | 继承 | implementer: #70 / decision 4；reviewer: 未见 |
| audit_basis v1 | 继承 | implementer: 未见；reviewer: #104 / decision 5 |

诊断标签：not_complete_method_support。

原结果：`{"reward": 0.0, "completed": false, "V": false, "mapper_status": "unmapped", "mapper_class": null}`。

## train-00-1

| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |
|---|---|---|---|---|---|
| 资料交接 `handoff-693cdaf1c385027b4fdd1b01`；当前模型，来源 provider；核查接收者 implementer | #30 handoff_information | #36 exact_entity_in_actual_request；#32 applied_environment_handoff | implementer: #36 / decision 2 | #42 read_alias、#77 adopt | 无 |
| 正式请求 `mail-1`；当前模型，来源 implementer；核查接收者 provider | #18 request_information | #24 exact_entity_in_actual_request | provider: #24 / decision 2 | #30 handoff_information | 无 |

产物版本的来源与首次内容输入：

| 产物版本 | 来源 / 写入 | 对方首次内容输入 |
|---|---|---|
| code v1 | 继承 | provider: 未见；implementer: 未见 |
| code v2 | #103 write_object | provider: 未见 |
| code v3 | #129 write_object | provider: 未见 |
| code v4 | #155 write_object | provider: 未见 |
| code v5 | #233 write_object | provider: 未见 |
| result v1 | 继承 | provider: 未见；implementer: 未见 |
| result v2 | #116 sql_build | provider: 未见 |
| result v3 | #142 sql_build | provider: 未见 |
| basis v1 | 继承 | provider: #24 / decision 2；implementer: #58 / decision 3 |
| audit_basis v1 | 继承 | provider: 未见；implementer: 未见 |

诊断标签：one_way_current_material_handoff、request_bound_reply、not_complete_method_support。

原结果：`{"reward": 0.2, "completed": false, "V": false, "mapper_status": "unmapped", "mapper_class": null}`。

## train-01-1

| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |
|---|---|---|---|---|---|
| 资料交接 `handoff-3a4829408cac58a6fdbf8318`；继承准备，来源 provider；核查接收者 implementer | 采样前 | #2 exact_entity_in_actual_request；start_state_inherited_delivery | implementer: #2 / decision 1 | #53 read_version | 无 |
| 固定产物 `TEAM::build-submission-1`；继承准备，来源 implementer；核查接收者 reviewer | 采样前 | #12 exact_entity_in_actual_request | reviewer: #12 / decision 1 | #18 inspect_submission | #129 approve（原判无效） |

产物版本的来源与首次内容输入：

| 产物版本 | 来源 / 写入 | 对方首次内容输入 |
|---|---|---|
| code v1 | 继承 | implementer: 未见；reviewer: 未见 |
| code v2 | 继承 | implementer: #93 / decision 5；reviewer: 未见 |
| result v1 | 继承 | implementer: 未见；reviewer: 未见 |
| result v2 | 继承 | implementer: #135 / decision 7（未开始生成）；reviewer: #103 / decision 5 |
| basis v1 | 继承 | implementer: #70 / decision 4；reviewer: 未见 |
| audit_basis v1 | 继承 | implementer: 未见；reviewer: #81 / decision 4 |

诊断标签：not_complete_method_support。

原结果：`{"reward": 0.0, "completed": false, "V": false, "mapper_status": "unmapped", "mapper_class": null}`。

## train-00-2

| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |
|---|---|---|---|---|---|
| 资料交接 `handoff-693cdaf1c385027b4fdd1b01`；当前模型，来源 provider；核查接收者 implementer | #76 handoff_information | #82 exact_entity_in_actual_request；#78 applied_environment_handoff | implementer: #82 / decision 4 | #111 read_version、#163 adopt | 无 |
| 正式请求 `mail-1`；当前模型，来源 implementer；核查接收者 provider | #18 request_information | #24 exact_entity_in_actual_request | provider: #24 / decision 2 | 无 | 无 |

产物版本的来源与首次内容输入：

| 产物版本 | 来源 / 写入 | 对方首次内容输入 |
|---|---|---|
| code v1 | 继承 | provider: 未见；implementer: #157 / decision 8 |
| result v1 | 继承 | provider: 未见；implementer: 未见 |
| basis v1 | 继承 | provider: #47 / decision 3；implementer: #128 / decision 6 |
| audit_basis v1 | 继承 | provider: 未见；implementer: 未见 |

未形成新交付/有效核准的尝试（包含幂等重复）：#8 handoff_information（工具拒绝）。

诊断标签：one_way_current_material_handoff、not_complete_method_support。

原结果：`{"reward": 0.2, "completed": false, "V": false, "mapper_status": "unmapped", "mapper_class": null}`。

## train-01-2

| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |
|---|---|---|---|---|---|
| 资料交接 `handoff-3a4829408cac58a6fdbf8318`；继承准备，来源 provider；核查接收者 implementer | 采样前 | #2 exact_entity_in_actual_request；start_state_inherited_delivery | implementer: #2 / decision 1 | #162 read_version | 无 |
| 固定产物 `TEAM::build-submission-1`；继承准备，来源 implementer；核查接收者 reviewer | 采样前 | #12 exact_entity_in_actual_request | reviewer: #12 / decision 1 | #18 inspect_submission | #131 raise_issue（原判无效） |
| 问题反馈 `issue-dbd42cfc33d0081ca5ed78c3`；当前模型，来源 reviewer；核查接收者 implementer | #131 raise_issue | #137 exact_entity_in_actual_request | implementer: #137 / decision 7 | 无 | 无 |

产物版本的来源与首次内容输入：

| 产物版本 | 来源 / 写入 | 对方首次内容输入 |
|---|---|---|
| code v1 | 继承 | implementer: 未见；reviewer: 未见 |
| code v2 | 继承 | implementer: #93 / decision 5；reviewer: 未见 |
| result v1 | 继承 | implementer: 未见；reviewer: 未见 |
| result v2 | 继承 | implementer: #115 / decision 6；reviewer: #58 / decision 3 |
| basis v1 | 继承 | implementer: #169 / decision 9（未开始生成）；reviewer: 未见 |
| audit_basis v1 | 继承 | implementer: 未见；reviewer: #104 / decision 5 |

诊断标签：not_complete_method_support。

原结果：`{"reward": 0.0, "completed": false, "V": false, "mapper_status": "unmapped", "mapper_class": null}`。

## train-00-3

| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |
|---|---|---|---|---|---|
| 资料交接 `handoff-693cdaf1c385027b4fdd1b01`；当前模型，来源 provider；核查接收者 implementer | #30 handoff_information | #36 exact_entity_in_actual_request；#32 applied_environment_handoff | implementer: #36 / decision 2 | #42 read_alias、#111 adopt | 无 |

产物版本的来源与首次内容输入：

| 产物版本 | 来源 / 写入 | 对方首次内容输入 |
|---|---|---|
| code v1 | 继承 | provider: #117 / decision 6；implementer: #105 / decision 5 |
| code v2 | #172 write_object | provider: 未见 |
| code v3 | #224 write_object | provider: 未见 |
| result v1 | 继承 | provider: 未见；implementer: 未见 |
| result v2 | #198 sql_build | provider: 未见 |
| result v3 | #237 sql_build | provider: 未见 |
| basis v1 | 继承 | provider: #24 / decision 2；implementer: #59 / decision 3 |
| audit_basis v1 | 继承 | provider: 未见；implementer: 未见 |

诊断标签：one_way_current_material_handoff、not_complete_method_support。

原结果：`{"reward": 0.2, "completed": false, "V": false, "mapper_status": "unmapped", "mapper_class": null}`。

## train-01-3

| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |
|---|---|---|---|---|---|
| 资料交接 `handoff-3a4829408cac58a6fdbf8318`；继承准备，来源 provider；核查接收者 implementer | 采样前 | #2 exact_entity_in_actual_request；start_state_inherited_delivery | implementer: #2 / decision 1 | #76 read_alias | 无 |
| 固定产物 `TEAM::build-submission-1`；继承准备，来源 implementer；核查接收者 reviewer | 采样前 | #12 exact_entity_in_actual_request | reviewer: #12 / decision 1 | #41 inspect_submission | #179 raise_issue |
| 问题反馈 `issue-3f0159f5e445e70c035694fa`；当前模型，来源 reviewer；核查接收者 implementer | #179 raise_issue | #185 exact_entity_in_actual_request | implementer: #185 / decision 9（未开始生成） | 无 | 无 |

产物版本的来源与首次内容输入：

| 产物版本 | 来源 / 写入 | 对方首次内容输入 |
|---|---|---|
| code v1 | 继承 | implementer: 未见；reviewer: 未见 |
| code v2 | 继承 | implementer: #70 / decision 4；reviewer: #150 / decision 7 |
| code v3 | #145 write_object | reviewer: 未见 |
| code v4 | #168 write_object | reviewer: 未见 |
| result v1 | 继承 | implementer: 未见；reviewer: 未见 |
| result v2 | 继承 | implementer: #139 / decision 7；reviewer: #173 / decision 8 |
| basis v1 | 继承 | implementer: #93 / decision 5；reviewer: 未见 |
| audit_basis v1 | 继承 | implementer: 未见；reviewer: #127 / decision 6 |

诊断标签：valid_issue_discovery、not_complete_method_support。

原结果：`{"reward": 0.0, "completed": false, "V": false, "mapper_status": "unmapped", "mapper_class": null}`。

## train-00-4

| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |
|---|---|---|---|---|---|
| 资料交接 `handoff-693cdaf1c385027b4fdd1b01`；当前模型，来源 provider；核查接收者 implementer | #30 handoff_information | #36 exact_entity_in_actual_request；#32 applied_environment_handoff | implementer: #36 / decision 2 | #42 read_version、#88 adopt、#163 read_alias | 无 |
| 正式请求 `mail-1`；当前模型，来源 implementer；核查接收者 provider | #18 request_information | #24 exact_entity_in_actual_request | provider: #24 / decision 2 | 无 | 无 |

产物版本的来源与首次内容输入：

| 产物版本 | 来源 / 写入 | 对方首次内容输入 |
|---|---|---|
| code v1 | 继承 | provider: #94 / decision 5；implementer: #128 / decision 6 |
| code v2 | #134 write_object | provider: 未见 |
| result v1 | 继承 | provider: 未见；implementer: 未见 |
| result v2 | #189 sql_build | provider: 未见 |
| basis v1 | 继承 | provider: #24 / decision 2；implementer: #59 / decision 3 |
| audit_basis v1 | 继承 | provider: 未见；implementer: 未见 |

未形成新交付/有效核准的尝试（包含幂等重复）：#202 submit（工具拒绝）、#241 submit（工具拒绝）。

诊断标签：one_way_current_material_handoff、not_complete_method_support。

原结果：`{"reward": 0.2, "completed": false, "V": false, "mapper_status": "unmapped", "mapper_class": null}`。

## train-01-4

| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |
|---|---|---|---|---|---|
| 资料交接 `handoff-3a4829408cac58a6fdbf8318`；继承准备，来源 provider；核查接收者 implementer | 采样前 | #2 exact_entity_in_actual_request；start_state_inherited_delivery | implementer: #2 / decision 1 | #76 read_version | 无 |
| 固定产物 `TEAM::build-submission-1`；继承准备，来源 implementer；核查接收者 reviewer | 采样前 | #12 exact_entity_in_actual_request | reviewer: #12 / decision 1 | #18 inspect_submission | 无 |

产物版本的来源与首次内容输入：

| 产物版本 | 来源 / 写入 | 对方首次内容输入 |
|---|---|---|
| code v1 | 继承 | implementer: 未见；reviewer: 未见 |
| code v2 | 继承 | implementer: #70 / decision 4；reviewer: #126 / decision 6 |
| result v1 | 继承 | implementer: 未见；reviewer: 未见 |
| result v2 | 继承 | implementer: #116 / decision 6；reviewer: #144 / decision 7 |
| basis v1 | 继承 | implementer: #93 / decision 5；reviewer: 未见 |
| audit_basis v1 | 继承 | implementer: 未见；reviewer: #104 / decision 5 |

诊断标签：not_complete_method_support。

原结果：`{"reward": 0.0, "completed": false, "V": false, "mapper_status": "unmapped", "mapper_class": null}`。

## train-00-5

| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |
|---|---|---|---|---|---|
| 资料交接 `handoff-693cdaf1c385027b4fdd1b01`；当前模型，来源 provider；核查接收者 implementer | #30 handoff_information | #36 exact_entity_in_actual_request；#32 applied_environment_handoff | implementer: #36 / decision 2 | #42 read_version、#103 adopt | 无 |
| 固定产物 `TEAM::build-submission-1`；当前模型，来源 implementer；核查接收者 provider | #207 submit | 未见已送达证据 | provider: 未见 | 无 | 无 |

产物版本的来源与首次内容输入：

| 产物版本 | 来源 / 写入 | 对方首次内容输入 |
|---|---|---|
| code v1 | 继承 | provider: 未见；implementer: #71 / decision 4 |
| code v2 | #116 write_object | provider: 未见 |
| code v3 | #181 write_object | provider: 未见 |
| result v1 | 继承 | provider: 未见；implementer: #84 / decision 5 |
| result v2 | #142 sql_build | provider: 未见 |
| result v3 | #194 sql_build | provider: 未见 |
| basis v1 | 继承 | provider: #24 / decision 2；implementer: #58 / decision 3 |
| audit_basis v1 | 继承 | provider: 未见；implementer: 未见 |

诊断标签：one_way_current_material_handoff。

原结果：`{"reward": 1.0, "completed": true, "V": true, "mapper_status": "mapped", "mapper_class": "a_active_handoff"}`。

## train-01-5

| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |
|---|---|---|---|---|---|
| 资料交接 `handoff-3a4829408cac58a6fdbf8318`；继承准备，来源 provider；核查接收者 implementer | 采样前 | #2 exact_entity_in_actual_request；start_state_inherited_delivery | implementer: #2 / decision 1 | #99 read_version | 无 |
| 固定产物 `TEAM::build-submission-1`；继承准备，来源 implementer；核查接收者 reviewer | 采样前 | #12 exact_entity_in_actual_request | reviewer: #12 / decision 1 | #18 inspect_submission | #110 raise_issue（原判无效） |
| 问题反馈 `issue-10abf20f6285140d9289b985`；当前模型，来源 reviewer；核查接收者 implementer | #110 raise_issue | #116 exact_entity_in_actual_request | implementer: #116 / decision 6 | 无 | 无 |

产物版本的来源与首次内容输入：

| 产物版本 | 来源 / 写入 | 对方首次内容输入 |
|---|---|---|
| code v1 | 继承 | implementer: 未见；reviewer: 未见 |
| code v2 | 继承 | implementer: #70 / decision 4；reviewer: 未见 |
| result v1 | 继承 | implementer: 未见；reviewer: 未见 |
| result v2 | 继承 | implementer: #161 / decision 8（未开始生成）；reviewer: #58 / decision 3 |
| basis v1 | 继承 | implementer: #116 / decision 6；reviewer: 未见 |
| audit_basis v1 | 继承 | implementer: 未见；reviewer: #104 / decision 5 |

未形成新交付/有效核准的尝试（包含幂等重复）：#195 request_information（工具拒绝）。

诊断标签：not_complete_method_support。

原结果：`{"reward": 0.0, "completed": false, "V": false, "mapper_status": "unmapped", "mapper_class": null}`。

## train-00-6

| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |
|---|---|---|---|---|---|
| 资料交接 `handoff-693cdaf1c385027b4fdd1b01`；当前模型，来源 provider；核查接收者 implementer | #30 handoff_information | #36 exact_entity_in_actual_request；#32 applied_environment_handoff | implementer: #36 / decision 2 | #42 read_version、#111 adopt、#263 read_alias | 无 |
| 正式请求 `mail-1`；当前模型，来源 implementer；核查接收者 provider | #18 request_information | #24 exact_entity_in_actual_request | provider: #24 / decision 2 | 无 | 无 |

产物版本的来源与首次内容输入：

| 产物版本 | 来源 / 写入 | 对方首次内容输入 |
|---|---|---|
| code v1 | 继承 | provider: #117 / decision 6；implementer: #105 / decision 5 |
| code v2 | #163 write_object | provider: 未见 |
| code v3 | #189 write_object | provider: 未见 |
| result v1 | 继承 | provider: 未见；implementer: 未见 |
| result v2 | #176 sql_build | provider: 未见 |
| result v3 | #202 sql_build | provider: 未见 |
| basis v1 | 继承 | provider: #24 / decision 2；implementer: #59 / decision 3 |
| audit_basis v1 | 继承 | provider: 未见；implementer: 未见 |

未形成新交付/有效核准的尝试（包含幂等重复）：#215 submit（工具拒绝）。

诊断标签：one_way_current_material_handoff、not_complete_method_support。

原结果：`{"reward": 0.2, "completed": false, "V": false, "mapper_status": "unmapped", "mapper_class": null}`。

## train-01-6

| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |
|---|---|---|---|---|---|
| 资料交接 `handoff-3a4829408cac58a6fdbf8318`；继承准备，来源 provider；核查接收者 implementer | 采样前 | #2 exact_entity_in_actual_request；start_state_inherited_delivery | implementer: #2 / decision 1 | #53 read_version | 无 |
| 固定产物 `TEAM::build-submission-1`；继承准备，来源 implementer；核查接收者 reviewer | 采样前 | #12 exact_entity_in_actual_request | reviewer: #12 / decision 1 | #18 inspect_submission | #131 raise_issue（原判无效） |
| 固定产物 `TEAM::build-submission-2`；当前模型，来源 implementer；核查接收者 reviewer | #201 submit | 未见已送达证据 | reviewer: 未见 | 无 | 无 |
| 问题反馈 `issue-55cb02f64b41bf140fe5c290`；当前模型，来源 reviewer；核查接收者 implementer | #131 raise_issue | #137 exact_entity_in_actual_request | implementer: #137 / decision 7 | 无；时间候选（非因果）#162 withdraw、#175 write_object、#188 sql_build、#201 submit | 无 |

产物版本的来源与首次内容输入：

| 产物版本 | 来源 / 写入 | 对方首次内容输入 |
|---|---|---|
| code v1 | 继承 | implementer: 未见；reviewer: 未见 |
| code v2 | 继承 | implementer: #93 / decision 5；reviewer: 未见 |
| code v3 | #175 write_object | reviewer: 未见 |
| result v1 | 继承 | implementer: 未见；reviewer: 未见 |
| result v2 | 继承 | implementer: 未见；reviewer: #58 / decision 3 |
| result v3 | #188 sql_build | reviewer: 未见 |
| basis v1 | 继承 | implementer: #70 / decision 4；reviewer: 未见 |
| audit_basis v1 | 继承 | implementer: 未见；reviewer: #104 / decision 5 |

诊断标签：changes_after_issue_input_not_causal_proof、not_complete_method_support。

原结果：`{"reward": 0.3, "completed": false, "V": false, "mapper_status": "unmapped", "mapper_class": null}`。

## train-00-7

| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |
|---|---|---|---|---|---|
| 资料交接 `handoff-5ce5739bf044a3d316aa3bd3`；当前模型，来源 provider；核查接收者 implementer | #30 handoff_information | #36 exact_entity_in_actual_request；#32 applied_environment_handoff | implementer: #36 / decision 2 | #42 read_version、#65 adopt | 无 |
| 正式请求 `mail-1`；当前模型，来源 implementer；核查接收者 provider | #18 request_information | #24 exact_entity_in_actual_request | provider: #24 / decision 2 | 无 | 无 |

产物版本的来源与首次内容输入：

| 产物版本 | 来源 / 写入 | 对方首次内容输入 |
|---|---|---|
| code v1 | 继承 | provider: 未见；implementer: #128 / decision 6 |
| code v2 | #185 write_object | provider: 未见 |
| result v1 | 继承 | provider: 未见；implementer: 未见 |
| result v2 | #198 sql_build | provider: 未见 |
| result v3 | #224 write_object | provider: 未见 |
| basis v1 | 继承 | provider: #24 / decision 2；implementer: #59 / decision 3 |
| audit_basis v1 | 继承 | provider: 未见；implementer: 未见 |

未形成新交付/有效核准的尝试（包含幂等重复）：#100 handoff_information、#237 submit（工具拒绝）、#250 respond_issue（工具拒绝）。

诊断标签：one_way_current_material_handoff、not_complete_method_support。

原结果：`{"reward": 0.2, "completed": false, "V": false, "mapper_status": "unmapped", "mapper_class": null}`。

## train-01-7

| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |
|---|---|---|---|---|---|
| 资料交接 `handoff-3a4829408cac58a6fdbf8318`；继承准备，来源 provider；核查接收者 implementer | 采样前 | #2 exact_entity_in_actual_request；start_state_inherited_delivery | implementer: #2 / decision 1 | #76 read_version | 无 |
| 固定产物 `TEAM::build-submission-1`；继承准备，来源 implementer；核查接收者 reviewer | 采样前 | #12 exact_entity_in_actual_request | reviewer: #12 / decision 1 | #18 inspect_submission | #133 approve（工具拒绝） |

产物版本的来源与首次内容输入：

| 产物版本 | 来源 / 写入 | 对方首次内容输入 |
|---|---|---|
| code v1 | 继承 | implementer: 未见；reviewer: 未见 |
| code v2 | 继承 | implementer: #47 / decision 3；reviewer: 未见 |
| code v3 | #145 write_object | reviewer: 未见 |
| result v1 | 继承 | implementer: 未见；reviewer: 未见 |
| result v2 | 继承 | implementer: #70 / decision 4；reviewer: #127 / decision 6 |
| result v3 | #167 sql_build | reviewer: 未见 |
| basis v1 | 继承 | implementer: #93 / decision 5；reviewer: 未见 |
| audit_basis v1 | 继承 | implementer: 未见；reviewer: #104 / decision 5 |

未形成新交付/有效核准的尝试（包含幂等重复）：#133 approve（工具拒绝）。

诊断标签：not_complete_method_support。

原结果：`{"reward": 0.0, "completed": false, "V": false, "mapper_status": "unmapped", "mapper_class": null}`。

## 可复现与来源

运行：`.venv/bin/python scripts/collaboration_evidence_v026.py`。输出 JSON 保留原文件路径与 SHA256、逐实体输入定位、所有捕获产物版本来源及原 saved_facts。只产生本报告，不写入 runs。

[机器可核对证据表](collaboration-v026-c0.json)；[原 16 条全文审阅](../reviews/v025-joint-experiences/index.html)。
