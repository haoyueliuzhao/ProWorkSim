# 数据合同与扩展接口（v0.4）

本文对应软件包 `0.4.0`、`schema_version: "0.4"`、经营模板 `contract_version: "operating-world-v0.4"` 及独立评价器 `operating-world-v0.4`。文稿微模板复用相同 schema，但使用独立的 `publication-micro-v0.1` 合同；它不是经营评价器的另一套输入，也不是第二个行业基准。

内核规范、状态归属和行动效果分别见 [CORE_SEMANTICS.md](../CORE_SEMANTICS.md)、[STATE_OWNERSHIP.md](../STATE_OWNERSHIP.md)、[ACTION_CONTRACTS.md](../ACTION_CONTRACTS.md)。[v0.3 设计](world-semantics-v03.md)和既有实验保持历史含义：能够读取旧 schema，不表示旧世界自动具有 v0.4 的凭据、条件和转换收据。未取得记录的旧事实不能补解为已验证。

## 层次与基本对象

`core/` 负责引用、版本可见性、凭据适用关系、回应满足条件、工作义务和转换保持；`policies/` 配置组织权力；`domains/` 规定经营或文稿内容；`adapters/` 连接文件、表格、通信与行动作用域。专业计算、特定角色名称、经营增长率和交付物名称不成为通用条件判断的分支。

| 对象 | 数据与语义 |
| --- | --- |
| Actor / organization | 角色 ID 是身份；`positions` 是模板岗位映射；`grants` 表达 `actor_id`、`power`、`subject`、`work_nodes`。确认、提供资料、修订和批准交付分别检查权限 |
| VersionRef | 核心格式为 `{"object_id": "…", "version_id": "…"}`，文件适配器也接受 `artifact_id` 别名。必须引用真实存在的版本；`current_version` 只是当前指针 |
| Fact / Claim / Assumption | 各有明确 `kind`，分别记录来源材料、主体主张和条件假设。Fact 不声称现实真理，Claim 不因写入而获正式效力 |
| Credential / Attestation | 凭据绑定明确版本、需求维度及组织效力；正式签发记录支持其效力，不证明其内容或工作人员计算正确 |
| Work / Requirement | 责任者、要求版本、用途、范围、输入、前驱与交付物。工作图表达前置关系，不代替其他制度规则 |
| Request / Response / Condition | 请求身份、回复送达和工作条件满足是不同记录 |
| Submission / Review | 提交固定版本；业务审阅可批准错误产物，独立评价可以另行拒绝 |

经营规格还保存 seed、来源事实、合成假设、工作图、布局、事件政策与完整接受要求。完整规格和 `acceptance_spec_ref` 不作为工作人员可见答案；公开工作要求可以进入观察。

## 正式凭据的唯一依据

v0.4 的正式凭据保存在对应不可变版本的 `artifacts[object_id].versions[version_id].credential`。签发凭证以 `state.attestations[attestation_id]` 为唯一登记来源。经营 `basis` 的 JSON 正文仍提供可读假设；`basis_approvals`、`basis_visibility` 是历史兼容或展示投影，不能作为第二套权威来覆盖正式登记。

`Credential` 的实际字段为：

```text
reference, project_id, requirement_dimension, requirement_version,
work_nodes, period, purpose, effective_at, confirmed_by,
attestation_ref, status, expires_at, kind="credential"
```

`Attestation` 保存 `attestation_id`、`actor_id`、准确版本 `reference`、`requirement_dimension`、`requirement_version`、`work_nodes`、签发时间 `at` 及 `power` / `subject`。`confirm_credential` 校验真实版本、确认者身份、该主题和节点的权力以及未冲突的签发 ID；相同确认重复执行为无变化，不可把同一版本的既有凭据改写为另一份。

`registered_applicability` 从版本元数据和登记表读取证据。响应中的 `approved: true`、产物正文自称被批准、某个旧兼容列表或收信事实，都不能代替登记。新 schema 缺少整个 attestations 或 organization 容器也不会静默降级信任旧投影或取得旧权限；兼容判断只用于明确的历史格式。查询上下文完整包含：

```text
project_id, work_id, requirement_dimension, requirement_version,
work_node, period, purpose, at
```

检查参考、签发关系、范围、项目、需求维度、需求版本、用途、期间、有效时刻与确认权。缺确认或证据不足返回 `UNASSESSED`；已经可评但与上下文不匹配返回 `FAIL`。相对最新版本较旧的凭据仍可能适用于旧工作；新凭据也可能不适用于另一项工作。

经营适配器的需求维度是 `analytical_assumptions`，用途是 `analytical_input`。工作另保存 `basis_requirement_version`、`required_basis`、`source_period`；整体 `requirement_version` 与分析需求版本分开。因此仅修改受众要求，不要求自动撤销原分析假设。`ApprovedBasis` 的 `assumptions`、`period`、适用节点等仍是经营数据，不是通用内核的固定字段。

## 可访问、已观察、声明采用与支持

| 关系 | 真实记录 | 不能据此推断什么 |
| --- | --- | --- |
| Access | 产物 `readers` / `writers`，或 `version_readers[version_id]`；新单版本授权记 `access_grants` | 可访问不等于已经提供、阅读或采用 |
| Observation | 真实工具返回、调用记录、交互的读引用与 `knowledge` 索引 | 不表示模型“相信”、理解或记住了信息 |
| Adoption | 新版本写入时的 `dependencies`，存于版本 `derived_from` | 声明来源不证明单元格实际采用正确值，也不把全部阅读历史变成来源 |
| Support | 指定上下文的凭据适用性、独立计算或有限内容检查 | 制度支持不等于现实真实性或专业表达质量 |

授予版本访问先确认对象版本存在，只修改该版本权限。角色已能通过整体 `readers` 或该版本授权访问时，不重复新增授权记录。旧 v2 回复不会开放私有 v3。未指定版本读取时，返回该角色在当前逻辑时间可访问的最新版本；不一定是后台 `current_version`。

经营模型需要显式声明 `financials` 和 `basis` 输入；memo 声明 financials/model，note 声明 model/brief。引用合同与正文来源字段另行校验。写入未提供新依赖时保留旧声明；Derive 不自动替工作人员更新数字或来源。`context_versions` 是提交时可见版本快照，也不是实际采用清单。

## 按工作判断适用性，谨慎折叠为摘要

经营 `freshness` 仍是面向界面的便捷字段，不能替代关系查询：

| 字段 | v0.4 合同 |
| --- | --- |
| `data_freshness` | 沿数据声明依赖计算 `current` / `stale` / `unknown`，排除批准依据因素 |
| `basis_applicability_by_work` | `{work_item_id: current/stale/unknown/not_applicable}`；保留每项相关当前义务的结果 |
| `basis_applicability_relations` | 每项含 `artifact_id`、实际当前 `version_id`、`work_item_id`、分析 `requirement_version` 与 `applicability` |
| `basis_applicability` | 各工作结果一致时使用共同值；多个工作结果不一致时为 `unknown`，不选择某一工作掩盖冲突 |
| `freshness` | 汇总数据与依据状态；有 stale 时 stale，否则有 unknown 时 unknown，否则 current |
| `freshness_basis` | `declared_dependencies_and_per_work_approval` |
| `possibly_stale` | `freshness != "current"`，包含未知 |

没有当前适用批准时不能拿最新历史 basis 补出已知目标。只换依赖标签却不更新数值，可能得到 current 的版本摘要，同时被独立评价拒绝。假设变化或受众变化可以只改变关系状态而不改变文件字节；哪些产物受影响由实际依赖和领域规则决定。

文稿模板用 `publication_applicability` 保存其工作与 `required_credentials` 的查询结果；不把经营 `basis` 作为隐藏的通用要求。

## 可扩展条件与回复满足

`state.condition_specs[condition_id]` 是通用条件协议；`state.blockers` 保留经营工具的展示与绑定适配。条件不是固定三种枚举。经营 `communication_policies` 把 scope/audience/evidence 翻译为权力、主题、证据来源、用途及版本要求；微模板可声明另一种条件而不修改 `core.conditions`。

| 条件字段 | 语义 |
| --- | --- |
| `condition_id` / `work_item_id` / `requirement_version` | 具体义务及其需求版本；可有投影 `blocker_id` |
| `request_id` | 真实且当前绑定的请求，不能凭 topic 自行关联其他工作 |
| `providers` / `unavailable_providers` | 配置的提供者与已经报告当前不可得的提供者 |
| `expected_version` / `purpose` | 回应必须满足的版本与用途；需求整数不等于文件 `v2` |
| `required_power` / `subject` | 提供者需要的组织权力与主题 |
| `evidence_spec` | 实际版本证据或正式 credential，按配置可固定精确 reference |
| `context` | 凭据适用性所需工作、需求、期间、用途和时间上下文 |
| `status` / `history` | open、resolved、unavailable、superseded，保留变化历史 |

`match_response` 是纯判断；`apply_response` 才更新匹配条件和其工作就绪状态。二者不发送邮件。通用检查同时核对实际请求消息的发送者/收件者、登记请求、工作和需求、提供者、版本、用途、组织权力及真实证据。新 schema 的凭据条件通过正式登记核验，不相信响应自行填写的“已核验”。无 schema 的旧内存协议夹具有明确的兼容路径，不能作为真实证据支持测试。

```text
PASS             当前证据满足该条件
FAIL             条件可判断，但回应身份、要求或证据不匹配
UNASSESSED       缺证据、缺登记，或提供者本次明确不能提供
NOT_APPLICABLE   其他请求、关闭条件或已过时工作/需求，不对当前义务生效
```

经营请求固定 `work_item_id`、整体及分析需求版本、收件角色、topic、证据引用和可选 blocker。`delivery_status` 记录回复已经送达；`response_status` 区分 delivered、unavailable、wrong_role。`status` 另可标记 outdated_reply；`condition_checks` 与 `conditions_satisfied` 记录满足判断。收到有内容的消息不必然满足条件，没有绑定条件的资料请求也不必虚构“已解除阻塞”。

重复处理已经有 `reply_message_id` 的请求不再追加邮件、授权、条件或工作人员历史。`condition_responses` 对真正产生条件效果的 response ID 保存结果，重复应用无新增效果。无关工作、无关 blocker、模型和文稿字节保持。

单项工作全部条件已 resolved 或 superseded、前驱的当前替代实例已接受时，才可从 blocked 重开。提交与批准共用该当前依赖查询；公开 `dependency_readiness` 显示当前前驱与就绪结果，粗粒度 activity status 不等于完整执行前置条件。superseded 表示义务撤换，不表示旧问题被答对。经营 blocker 的 `condition_id` 指向该规则；`required_scope_version` 只是旧工具参数名称，仍使用分析需求整数。

## 不可得、后续机会与显式恢复

unavailable 只记录本次提供者无法提供。存在尚未耗尽的另一个 provider，或匹配的 `future_opportunities`（status 为 pending/available），或仍有事件待处理时，不能把它视为永远不可完成。未来机会记录至少含 `opportunity_id`、`condition_id`、可选 provider 和 status；核心终态同时支持纯条件及经营 blocker 投影。

当前未接受工作全部阻塞、各有不可得条件且没有配置的剩余取得路径时，观察可返回 `terminal_reason: "blocked_unavailable"`。它表示当前有限 episode 可以结束，`complete` 仍为 false，不是交付成功或工作人员通过。

`restore_information` 是受组织 `restore_information` 权力控制的环境接口，未列入分析师工具集。它要求已有真实版本、提供者能读取、符合当前条件及凭据要求；本身不签发批准、不放宽需求、不替代已有不同绑定。可将当前缺失的 `required_basis` 绑定到已经独立验证的同需求凭据。恢复写入：

- `provider_availability[provider][topic][work_item_id]`，仅对指定工作生效；
- 条件的信息到达历史与具体证据引用；
- `information_restorations`，记录行为者、提供者、范围、reference、原因与时间；
- 对应未来机会的 consumed 状态，以及给责任者的真实到达通知。

通知只说明请求路线已恢复，不附未授权的私有证据正文。`information_arrival` 可作为明确排程事件调用相同接口。环境控制器创建和签发资料、预设机会与排程，必须在实验中作为初始条件或环境操作说明，不能表述为模型自行创造了可得信息。

资料到达不会自动解除旧 blocker。需要新真实请求和符合条件的回复；旧 unavailable 请求重放仍无效果。经营重绑保留 `prior_request_ids` 和旧回复，条件/工作恢复与最终业务完成仍分别判断。

## 行动效果、保持与时间

每次实际工具或事件经 `execute_transition` 执行 Apply → Derive，并比较允许路径。Apply 可以写真实文件或产生业务记录；Derive 只能修改声明的关系投影。越界改变或改写历史会使直接变更回滚；文件适配器通过存储恢复保持可见文件与已提交状态一致。

成功转换收据保存 `contract`、`allowed_business_paths`、`direct_changes`、`derived_changes`、`history_preserved` 和 `frame_respected`。失败直接操作记 `rolled_back: true` 和空直接/派生变化。日志、逻辑时间与随后到期事件另行处理：一次被拒动作仍可能推进时间，使已经排期的合法事件发生，不能把它报告为失败动作修改了业务文件，也不能宣称失败后整个世界绝对不变。

实际强制保持包括：

| 历史对象 | 不允许改写的事实 |
| --- | --- |
| 既有产物版本 | ID、所有者、哈希、逻辑时间、`derived_from` 和已存 credential；不得删除版本 |
| 追加历史 | messages、interactions、basis_approvals、requirement_events 的既有前缀 |
| 正式登记 | 既有 attestations 的内容 |
| 既有工作/提交 | 不得删除；submission ID、需求版本、行为者、固定产物版本、回答、时间、可见上下文、required_credentials、requirement_snapshot、required_basis 保持 |
| 已完成审阅 | 既有 review 内容保持；另用 invalidation/current applicability 记录后续效力 |

条件历史与回复幂等由条件转换维护。当前实现没有通用事件溯源数据库，不保证仅从日志重建所有文件。相同时刻到期的事件按入队顺序串行处理；针对独立动作的顺序比较只比较业务状态，不要求日志字面顺序一致，也不证明任意并发组织过程可交换。

## 义务、修订和业务审阅

通用 `revise_requirement(state, targets, updates, actor, reason)` 只接收显式工作目标及声明性要求，不接受 growth_delta 等领域计算参数。它创建 replacement，保存 `work_replacements`、`requirement_events` 与旧事实，不创建新文件或替工作人员修正内容。引用的新凭据应先存在。

通用提交通过 `submit_work` 固定交付版本、上下文、`required_credentials` 和 `requirement_snapshot`；适配器负责取得真实可读版本。修改已提交文件、撤回或修订可以使待审提交失效，但不改写旧回答和固定文件。被新需求替代的历史 accepted 工作仍可保留 accepted，另以 `current_applicability` 表明已不承担当前义务。

经营适配器仍有共享模型的范围限制：分析假设修订按同一当前分析阶段处理，growth_delta 由该领域适配器解释；不假装是通用字段级因果传播。工作—发布联合可达性检查仍是有限语言下的乐观结构可达性，不是业务可解性证明。

公开受众字段、引用和经营数值约束由领域合同说明。工作人员可以写错公式、错误采用或过早提交；有权审阅者可能接受错误结果。无权签发或伪造提交版本属于不能执行的行为；可执行但不合适、业务拒收、独立评价失败必须分开记录。

## 模板和接口范围

经营配置保留 chain、fork、selective、coordination 四种配置，对应 chain、fork、selective 三种工作图；coordination 是 chain 加信息协调。standard、basis_only、during_update、waiting_reply、during_review、unavailable 是该模板已有情境，未提升为内核枚举。shifted 布局附位置指南，selective 明确给出应改范围；不能据此声称无指南布局泛化或自主影响分析。

经营 `World.session(actor)` 绑定身份，行动返回 `ok`、`action_id`、`logical_time` 和 result/error。mail_send、block_work、withdraw 保持工具参数；`revise_requirements` 是经营修订适配入口；`restore_information` 是有权限环境主体的恢复入口，分析师越权尝试返回错误。

微模板通过 `domains.publication.compile_publication` 和 `PublicationWorld` 构建 source_note、editorial_policy、draft。它配置 author/editor 的岗位与权力，可替换员工 ID，复用 `confirm_credential`、版本授权、条件满足、通用提交/撤回/修订/批准和转换检查。独立检查只针对来源引用、字段、采用声明与政策要求短语，业务审阅有意较窄；既不检查真实出版专业质量，也不将业务接受当作独立正确。

## 独立评价与实验导出

经营评价针对指定提交及其固定要求，保留 `passed` / `artifact_valid`、`business_accepted`、`currently_applicable` 的区别。缺少适用批准时，文件与依赖等可检查要求继续评价，依赖隐藏假设的数值目标进入 `unassessed_checks`，不借完整生成规格回填业务上尚未确定的目标。

四态是内核检查格式；现有经营评价的二值 `checks` 与单独 `unassessed_checks` 是输出适配，未评不会折算为通过。`numerical_assessment` 区分未提交、可评和缺批准；`assessment_scope` 固定为提交自身需求版本。`root_causes` 和 `propagated_failures` 是有限的依据传播分组，不是模型心理归因或完备因果证明。

文稿独立评价返回 checks 的 PASS/FAIL/UNASSESSED、`passed`、`business_accepted`、`currently_applicable` 和有限 `evaluation_scope`；其世界合同单独标为 `publication-micro-v0.1`，没有声称经营评价器覆盖文稿质量。

既有导出仍包含 manifest、episode、calls、interactions、evaluations、candidates、sft、rl 和完整 world 快照。调用保留真实 messages/tools、原始返回、服务端 usage 与 attempts，不纳入 API 密钥；未知 usage 不用字符估算填充。快照分支、谱系划分、历史候选与 message loss mask 的归档接口保留，后续被替代的旧提交不自动变成新要求的监督。

SFT 候选仍是 `outcome_conditioned_candidate`，不是逐步专业金标；RL 中未提供的 token ID 和行为概率保持缺失，不能视为已完成在线训练协议。本阶段验证的是有限工作世界语义和跨模板机制复用，没有新增参数训练、扩大上下文效果或证明训练收益。内核自洽也不证明合成经营假设与真实专业实践一致。
