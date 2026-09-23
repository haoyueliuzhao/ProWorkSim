# 数据合同与扩展接口（v0.8）

当前软件包 `0.8.0`，WorldCore schema 为 `world-core-v0.8`、语义为 `work-world-v0.8`，共用回执为 `phase-deltas-v0.5`。阶段 A 内容评价为 `finite-products-v0.8`；阶段 B 多源扩展为 `finite-products-v0.8.1`。旧 schema 世界使用其冻结运行时，不隐式迁移采用表、历史观察或评价结果。两阶段设计见 [v0.8 合同](continuous-work-v08.md)与[推进计划](continuous-work-v08-plan.md)。

## v0.8 工作上下文、持续义务和公开执行

### 别名、采用与提交

| 字段／接口 | 当前语义 |
| --- | --- |
| `workspaces[project_id][alias]` | 项目内发现入口，指向世界对象，不表示某项工作采用了最新版本 |
| `adoptions[work_id + "::" + alias]` | 一项确切工作／需求版本的绑定；含 project_id、work_id、work_ids=[work_id]、requirement_version、alias、object_id、version_id、policy、actor_id、at、history |
| `adoption_view[key]` | 可重建的 adopted_version、target_version、policy、status；没有正式目标时为 unassessed |
| `submission.adoption_snapshot[key]` | 深拷贝该工作绑定以及提交时 target_version、allowed_policies；新发布不追溯改写旧提交要求 |
| `adopt(..., work_ids=[...])` | 非空显式工作集合；逐项核对确切可读对象和工作范围。相同 alias 可为另一项工作创建不同绑定 |
| `adopt_version(alias, version_id, work_id=...)` | 更新明确当前工作自己的 current 政策绑定并追加历史；不转绑旧工作、不改文件；省略 work_id 仅接受唯一无歧义当前绑定 |

`requirements.input_policy` 为共同默认，`input_policies[alias]` 为逐输入覆盖；字符串声明唯一政策，非空无重复列表声明允许选择范围。支持 fixed、current_published、current_applicable。`input_version`／`input_versions[alias]` 可限定 fixed 的精确版本。项目安装、正式需求修订和维护规则更新检查同一合同；评价器使用固定 `requirement_snapshot` 复核，不在事后替工作人员选择政策。

需求替代保留同一稳定 node，但创建新的 work ID／requirement_version；新工作必须显式采用。旧绑定不会转给替代工作。原 submission 的固定内容／答案、采用快照、凭据与已有 review 保持；current_applicability 等明确生命周期注记可以变化。

### 发布影响与后继工作

项目包新增 `maintenance_rules`。每条包含 rule_id、source（alias 或 object_id，可加 source_project）、本项目稳定 work_nodes、when 阶段集合、effect、actor 和 updates。只允许声明性 goal、visible_requirements、requirements 更新，不支持权限修改、任意文件操作或代码回调。revise／successor 须有目标节点的 revise_requirement 权，且更新后输入政策合法。

`core.maintenance.work_stage` 按 accepted、pending、output_ready、after_read、before_read 优先判定。读取／编辑进展要求真实记录带确切 work ID 和 requirement_version；after_read 另要求当前责任者读过所选来源。output_ready 只表示发生过工作上下文编辑，不保证内容完成。创建／读写／表格工具可显式带 work_id；工作范围权限从可信工作解析传入，不能由字符串同名跨项目扩权。

发布时捕获候选的真实版本、工作和阶段，并排入独立 `maintenance_impact` 事件。notice 发后果通知；ignore 登记忽略；revise 建立需求替代；successor 只在 accepted 阶段建立新维护义务，前一工作仍保持接受。未匹配规则不产生义务，也不存在通用“新发布使所有任务失效”的规则。

影响 ID 由 release／项目／规则／稳定节点决定。`maintenance_impacts` 保存固定 payload 和 result；`projects[pid].maintenance_heads` 保存谱系的新头。后继工作保存 previous_obligation_id、maintenance_trigger，继承原稳定节点和未被覆盖的声明合同，取得递增需求版本，清空提交／编辑／条件缓存。采用需重新声明；内容需实际重做。重复影响不增第二义务，已被替代的目标记录 stale_target，非活动项目记录 project_inactive。

### 路线可重用与资料恢复

路线定义保存稳定 work_node，公开观察按当前义务展开 work_id。请求独立固定 work_item_id、requirement_version、route_id、route_revision 和证据版本。路线 version_policy=fixed 使用声明版；current_published 要求正式目标；work_requirement 依次查该 alias 的精确要求、允许的正式发布目标、路线声明版。这个后备版仍须满足实际采用政策，不能替代 current_published 的内容评价要求。

`set_information_availability(route_id, available, reason)` 只允许声明 provider 在真实 provide 范围内调用。变化增加 availability_revision，追加 information_updates，并公开通知，不直接满足条件或改文件。责任者随后通过同一路线给同一当前工作发新请求；较旧可用性版本的未满足请求条件会被明确 supersede，新的实际回复再独立判断满足并按路线授予精确版本读取。旧回复与旧不可用记录保留；被需求替代工作的迟到回复不会替新工作授予资料。

### 内容合同与公开策略

递归 JSON 比较在对象与数组内同样区分布尔／数值；保留有限 int／float 等价，不新增浮点容差。多文件仍按完整顶层字段合并，冲突不选择覆盖赢家、不深层合并。

`json_linear_sources` 在原单源检查之外接受 2 至 8 个不同 alias，各声明 JSON source_path 或 XLSX sheet/cell、正文 reference_path 和有限 coefficient，另有有限 constant。独立标量计算期待值，拒绝布尔／字符串数值化及溢出，不调用被测表格引擎。各来源都复用确切工作／需求／政策目标验证；每个对数值或某项来源引用有贡献的文件，必须声明对应精确 derived_from。与该检查无关的交付文件不强制增加来源依赖。单文件与两个顶层字段拆分文件可共同满足合同。示例与责任评价分离见 [详细合同](continuous-work-v08.md)。

`ContinuousWorker` 使用多端口 tools／observe／call，按 port 与精确 work ID 保存进度并轮转。它支持一项单源或有限线性多源合同、一个组合 JSON 产物，发现替代／后继工作后重新绑定输入。完整真实观察与调用返回保存在 transcript；不读取 Store、隐藏规格或模型答案。

结果单列 worker_waiting、world_blocked、budget_exhausted、environment_error、submitted、completed。存在世界条件与策略等待不是同一事实；最后两项也不是内容质量标签。worker checkpoint 只包含已返回步骤的公开进度／transcript，在同 label／顺序的 ports 上显式恢复；它不是世界快照、任意进程故障恢复或跨世界可移植性承诺。运行器 command/event 的持久恢复仍是独立协议。

本阶段实验范围为一个世界、两个项目、单写者交错执行。以下旧阶段章节保留原模板、接口和历史语义，不据此扩大为完整经营模型迁移、通用工作人员或训练收益。

## v0.7 新增合同（历史阶段）

- WorldSpec.applications 限定 files/spreadsheets；create_object 支持 kind=json/xlsx，sheet_read/update/recalculate 处理真实受限工作簿。ProjectSession.tools 与执行使用同一能力选择。
- publication_policy 在世界/项目级配置 explicit（默认）或 implicit_write。publish 精确绑定版本与目标项目；release 追加记录独立于草稿、分享和采用。
- 同项目精确 shares 与原 ACL 共同生效；adopt/adopt_version 对真实对象及逐工作传递范围，不通过通配授权修复合法路径。
- current_published 与 fixed 分开；提交 adoption_snapshot 固定当时已采用版和政策目标。没有发布的目标是不可评，不从 current_version 猜正式输入。
- content_checks 只接受声明的有限类型：JSON 标量、XLSX 单元格标量、公式缓存错误，以及 JSON 对精确输入 JSON/XLSX 接口的对应关系。期望数值不由被测引擎生成；实际内容来自 immutable version_path 且校验哈希。
- 来源检查核对正文 reference、采用快照/目标、贡献文件 derived_from 与实际接口值；B 不必取得 A 的所有私有上游。
- information_routes 只声明同包的真实初始 v1、对象 writer/provider、对应 provide 权以及延迟/availability。request_information 公开参数仅 route_id/work_id；unknown 路线拒绝，unavailable 等待出口保留。
- 透明程序 worker 只支持一个当前责任任务与一项有限来源合同，通过工具发现、观察和真实读取推进；实际原始往返另存，不能作为通用模型能力结论。

以上记录 v0.7 阶段能力，其中单工作程序策略与初始路线边界已由 v0.8 新接口明确扩展。以下继续保留 v0.6/v0.5 阶段合同；纯 JSON 能力限制、默认写入发布和旧 schema 均为历史边界，当前 WorldCore 行为以上述 v0.8 合同为准。


v0.6 阶段软件包为 `0.6.0`。新增世界运行时的 schema 为 `world-core-v0.6`、语义版本为 `work-world-v0.6`；经营与文稿单项目运行时继续使用 schema `0.5`。两者共用 `core.runner.WorldRunner` 和 `phase-deltas-v0.5` 回执格式。完整世界合同与 CLI 见 [v0.6 设计](world-core-v06.md)，推进与验收见 [执行计划](world-core-v06-plan.md)。

## v0.6 新世界接口（历史阶段）

`proworksim.WorldSpec` / `core.world.WorldSpec` 允许零项目，无金融事实和假设字段。旧 `schema.WorldSpec` 已明确改名 `OperatingTemplateSpec`，由经营编译器使用；本轮没有隐式转换旧世界。

- `WorldCore.create(path, WorldSpec(...))`：在新目录初始化稳定主体、文件应用和显式世界权力。
- `WorldCore.session(actor, project_id=None)`：可信调用方绑定上下文；`call(tool, request_key=..., **arguments)` 不允许模型覆盖 actor/project。
- `install_project(package=...)`：完整预检后，项目注册、初始版本、别名、义务和局部授权同一提交；不能携入预制审批历史或世界管理员。
- `create_object(alias, filename, data, deliverable_role, dependencies)`：限定 JSON object、相对安全文件名和可读精确引用。实际对象身份来自无歧义的项目/别名元组；镜像位于 artifacts 专用空间。
- `share(object_id, version_id, target_project, actor_ids, follow_updates=False)`：单版读取和持续发布分开；不开放上游。世界操作者可为未来项目准备明确授权。
- `adopt(alias, object_id, version_id, policy, work_ids)`：current_applicable 或 fixed；`adopt_version(alias, version_id)` 仅更新 current 声明并记录历史，不改产物字节。
- `submit(work_id, artifacts=[aliases], answer=None)`：合同可按类型/角色/文件数声明，不列死路径；required_credentials 在提交与批准时都必须可读、已签发且适用；公开使能使用同样门槛。
- `close_project(mode, reason)` 与 episode 起止：项目、工作、世界及实验切片分离。retain/cancel 对待处理义务的行为必须由项目包声明。

`WorkContext` 包含 world/project/work/requirement/purpose/period；实际授权同时核对明确 project 与无歧义 work node，可另限定 object。原角色名或同名 work-1 不产生跨项目权力。当前 grants 为固定配置，未实现运行时任意组织重构。

项目包 provenance 支持 observed/reconstructed/synthetic/unknown；observed 必须有 source_evidence_refs。来源标记是证据声明，不自动验证外部真实性。没有实际过程证据时，不得从财报与最终文件推造历史批准或返工。当前 `required_fields` 仅检查 JSON 聚合字段和冲突；未实现的 `content_rules` 明确拒绝。

以下 v0.5 章节保留两套单项目适配器及共用机制的详细合同。其单 project、预制 XLSX、经营 freshness 和模型导出接口不自动等于 v0.6 的动态项目能力。

## v0.5 单项目适配器与共用机制

以下章节对应冻结实现 `fe80b02a69df7cfe8eabf4a62cce2031c4e3035c`、软件包 `0.5.0`、`schema_version: "0.5"`、经营模板 `contract_version: "operating-world-v0.5"` 及独立评价器 `operating-world-v0.5`。转换语义版本为 `work-world-v0.5`，阶段收据版本为 `phase-deltas-v0.5`。文稿微模板复用相同 schema，但使用独立的 `publication-micro-v0.1` 合同；它不是经营评价器的另一套输入，也不是第二个行业基准。

内核规范、状态归属和行动效果分别见 [CORE_SEMANTICS.md](../CORE_SEMANTICS.md)、[STATE_OWNERSHIP.md](../STATE_OWNERSHIP.md)、[ACTION_CONTRACTS.md](../ACTION_CONTRACTS.md)。[v0.3 设计](world-semantics-v03.md)和既有实验保持历史含义。

当前 `World`（包括继承该入口的 `PublicationWorld`）在打开时要求准确的当前 schema，拒绝直接运行旧世界。历史格式仍可由明确支持它的归档或评价接口读取，但这不构成运行时迁移；旧世界需使用对应冻结运行时；若以后迁移，必须另行实现显式、可信的检查点导入，本轮未提供导入工具。当前没有自动把旧状态、旧收据或旧 status 转成新事实的路径，未取得的原始回应和中间快照不能补写为已验证。

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

## 基础事实、可丢弃投影与查询

v0.5 使用可信检查点、声明性定义和原始事件事实。它没有要求从任意旧日志重建整个世界，也不从界面 status 反推曾经发生的行动。

| 归属 | 字段与写入来源 |
| --- | --- |
| 基础事实 B | 不可变产物版本、当前正式版本指针、credential/attestation；工作定义与替代；固定提交、审阅、撤回和 invalidation；真实 `artifact_edits`；条件定义、绑定及接收事件 |
| 原始接收事实 B/O | `raw_condition_responses` 的回应正文、接收时间/序号和接收时正式事实快照；真实消息、交互与读取记录 |
| 可重算投影 P | 工作 `status`、`blocker`、`blocker_ids`、`applicability`；条件 `status`、`unavailable_providers`、`resolution_ref`、`response_checks`；整个 `blockers` 和 `condition_responses`；来源新鲜度及适用关系 |
| 执行协议 Q | `state_revision`、`operation_commits`、待处理事件、事件处理记录及失败尝试诊断；不得当成专业正确性标签 |
| 世界外评价 | 独立评价结果与已核验支持关系；不反向生成批准、修改错误成果或删除原审阅 |

`derive_condition_view(state)` 和 `derive_current_work_view(state)` 是纯查询，不依赖上述状态缓存。`rebuild_projections(state)` 只写预声明缓存，从正式条件单向生成兼容 blocker；不能让 condition.status 与 blocker.status 相互纠正。缺少已引用的原始回应等必要事实会报错。`projection_paths(state)` 展开具体缓存路径；新对象的 frame 只以固定字段通配允许缓存，不能放开整个工作或条件对象。

工作查询保留独立维度：`status` 是活动摘要；`submission_state` 为 none/pending/accepted/revision_required/withdrawn/invalidated；`pending_submission_id` 指向真实未失效待审提交；`submission_versions_current` 检查提交需求、凭据引用及交付物当前指针；前驱就绪和未满足条件另行计算。前驱被替代可以使摘要成为 waiting_dependencies，同时保留 pending，责任者仍能撤回。批准需当前义务、当前前驱已接受、无未满足条件、存在待审提交且固定版本仍匹配；写错内容本身不自动禁用制度批准。

`enabled_actions` 是当前制度状态下的行动查询，公开观察再按绑定身份过滤：submit/withdraw 仅对责任者可见，approve 另需批准权。它不代替调用时的参数和版本检查。`World.observe` 在内存中重建并过滤视图，不保存状态、不推进时钟、不追加消息、批准或阅读收据；这不改变真实 read/mail_read 工具会记录已提供内容的合同。

E1 缓存实验只删除或破坏 `projection_paths` 声明的条件/工作缓存，不表示清除了整个系统的一切派生数据。正式历史和文件字节均保留。

## 正式凭据的唯一依据

v0.5 的正式凭据保存在对应不可变版本的 `artifacts[object_id].versions[version_id].credential`。签发凭证以 `state.attestations[attestation_id]` 为唯一登记来源。经营 `basis` 的 JSON 正文仍提供可读假设；`basis_approvals`、`basis_visibility` 是历史兼容或展示投影，不能作为第二套权威来覆盖正式登记。

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

经营适配器的需求维度是 `analytical_assumptions`，用途是 `analytical_input`。工作另保存 `basis_requirement_version`、`required_basis`、`source_period`；经营依据同步映射为通用 `required_credentials`，提交固定这份列表；整体 `requirement_version` 与分析需求版本分开。因此仅修改受众要求，不要求自动撤销原分析假设。`ApprovedBasis` 的 `assumptions`、`period`、适用节点等仍是经营数据，不是通用内核的固定字段。

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

| 字段 | v0.5 合同 |
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

`state.condition_specs[condition_id]` 中的定义与事件历史是通用条件依据；`state.blockers` 是单向兼容展示，绑定操作必须修改正式条件，不能把 blocker 缓存当成绑定或满足的依据。条件不是固定三种枚举。经营 `communication_policies` 把 scope/audience/evidence 翻译为权力、主题、证据来源、用途及版本要求；微模板可声明另一种条件而不修改 `core.conditions`。

| 条件字段 | 语义 |
| --- | --- |
| `condition_id` / `work_item_id` / `requirement_version` | 具体义务及其需求版本；可有投影 `blocker_id` |
| `request_id` | 真实且当前绑定的请求，不能凭 topic 自行关联其他工作 |
| `providers` / `unavailable_providers` | 前者是正式配置；后者由实际不可得回应及信息恢复事件重算 |
| `expected_version` / `purpose` | 回应必须满足的版本与用途；需求整数不等于文件 `v2` |
| `required_power` / `subject` | 提供者需要的组织权力与主题 |
| `evidence_spec` | 实际版本证据或正式 credential，按配置可固定精确 reference |
| `context` | 凭据适用性所需工作、需求、期间、用途和时间上下文 |
| `history` | 基础事件：created、bound、response_received、superseded、information_available、unavailability_recorded；列表顺序保留实际发生次序 |
| `status` / `resolution_ref` / `response_checks` | 从原始事实重算的 open/resolved/unavailable/superseded 及证据、检查摘要，不是新的事实来源 |

`match_response` 是纯判断；`apply_response` 保存原始响应和 response_received 事件，再重建条件与工作投影。二者不发送邮件。通用检查同时核对实际请求消息的发送者/收件者、登记请求、工作和需求、提供者、版本、用途、组织权力及真实证据。新 schema 的凭据条件通过正式登记核验，不相信响应自行填写的“已核验”。无 schema 的旧内存协议夹具有明确的兼容路径，不能作为真实证据支持测试。

```text
PASS             当前证据满足该条件
FAIL             条件可判断，但回应身份、要求或证据不匹配
UNASSESSED       缺证据、缺登记，或提供者本次明确不能提供
NOT_APPLICABLE   其他请求、关闭条件或已过时工作/需求，不对当前义务生效
```

经营请求固定 `work_item_id`、整体及分析需求版本、收件角色、topic、证据引用和可选 blocker。`delivery_status` 记录回复已经送达；`response_status` 区分 delivered、unavailable、wrong_role。`status` 另可标记 outdated_reply；`condition_checks` 与 `conditions_satisfied` 记录满足判断。收到有内容的消息不必然满足条件，没有绑定条件的资料请求也不必虚构“已解除阻塞”。

`raw_condition_responses` 保留实际接收的正确、错误、过时和 unavailable 响应；不能因为没有解除条件就删除该次接收事实。每条含 `received_at`、跨响应的 `received_sequence` 和不能由响应调用者伪造覆盖的 `receipt_context`。上下文固定接收时的替代映射、需求版本、已有批准/取消事实、实际引用版本元数据、签发登记、组织配置和条件证据定义。重建仍重新做匹配，不把历史 PASS/FAIL 当成事实；同一逻辑时刻晚签的凭据、后续需求替代或批准，不能倒改早先回复的含义。

`condition_responses` 是可替换的检查结果缓存，包含未满足响应；`blockers`、条件和工作摘要均由同一事实来源计算。相同 response ID 与相同内容重复应用不新增接收事实；同 ID 换内容会被拒绝。通信适配器对已有 `reply_message_id` 的请求不再追加邮件、授权或工作人员历史。原始回应已经留下的新接收事实，应与“没有产生条件满足效果”分开表述，不能把错误回复概括为世界全状态完全未变。

单项工作全部条件已 resolved 或 superseded、前驱的当前替代实例已接受时，才可重新获得提交使能。提交与批准共用该当前依赖查询；公开 `dependency_readiness` 显示当前前驱与就绪结果。条件已满足但前驱未就绪时摘要可为 waiting_dependencies；既有 pending 不因该摘要而消失。superseded 表示义务撤换，不表示旧问题被答对。经营 blocker 的 `condition_id` 指向该规则；`required_scope_version` 只是旧工具参数名称，仍使用分析需求整数。

## 不可得、后续机会与显式恢复

unavailable 只记录本次提供者无法提供。存在尚未耗尽的另一个 provider，或匹配的 `future_opportunities`（status 为 pending/available），或仍有事件待处理时，不能把它视为永远不可完成。未来机会记录至少含 `opportunity_id`、`condition_id`、可选 provider 和 status；核心终态同时支持纯条件及经营 blocker 投影。

当前未接受工作全部阻塞、各有不可得条件且没有配置的剩余取得路径时，观察可返回 `terminal_reason: "blocked_unavailable"`。它表示当前有限 episode 可以结束，`complete` 仍为 false，不是交付成功或工作人员通过。

`restore_information` 是受组织 `restore_information` 权力控制的环境接口，未列入分析师工具集。它要求已有真实版本、提供者能读取、符合当前条件及凭据要求；本身不签发批准、不放宽需求、不替代已有不同绑定。可将当前缺失的 `required_basis` 绑定到已经独立验证的同需求凭据，并同步当前义务的 `required_credentials`；不覆盖原提交固定的要求或凭据列表。恢复写入：

- `provider_availability[provider][topic][work_item_id]`，仅对指定工作生效；
- 条件的信息到达历史与具体证据引用；
- `information_restorations`，记录行为者、提供者、范围、reference、原因与时间；
- 对应未来机会的 consumed 状态，以及给责任者的真实到达通知。

通知只说明请求路线已恢复，不附未授权的私有证据正文。`information_arrival` 可作为明确排程事件调用相同接口。环境控制器创建和签发资料、预设机会与排程，必须在实验中作为初始条件或环境操作说明，不能表述为模型自行创造了可得信息。

资料到达不会自动解除旧 blocker。需要新真实请求和符合条件的回复；旧 unavailable 请求重放仍无效果。经营重绑保留 `prior_request_ids` 和旧回复，条件/工作恢复与最终业务完成仍分别判断。

## 行动阶段、区域净变化与收据

`execute_transition` 捕获三个真实端点：S0 为业务 Apply 前，S1 为 Apply 成功返回后，S2 为 Derive 返回后；随后校验 frame 和历史保持。它记录阶段差分与区域分类两个独立维度：

| 字段 | 比较口径 |
| --- | --- |
| `apply_delta` | S0 → S1 的实际路径差异；Apply 自己写入缓存也属于这里 |
| `derive_delta` | S1 → S2 的实际路径差异；Derive 无变化时为空 |
| `net_delta` | S0 → S2 的最终路径差异；中途写入又恢复的字段可能不在其中 |
| `primary_region_changes` | `net_delta` 中不属于 frame 声明投影区域的路径 |
| `projection_region_changes` | `net_delta` 中属于声明投影区域的路径；不等于 derive_delta |
| `state_digests` | before、after_apply、after_derive 三份状态的规范 JSON SHA256；用于诊断 |
| `effect_refs` | 本次转换新增的产物/版本引用；不是所有业务效果的完整列表 |

差分是路径列表，不含旧值/新值，不是可直接重放的值 patch。列表变化可以落在整个列表路径；字段变化数量也不是实际写入次数。例如 Apply 写 view、Derive 什么也不做，则 `apply_delta` 包含 view、`derive_delta` 为空，而 `projection_region_changes` 仍包含 view。不能通过“该字段属于投影区”把 Apply 的写入归给 Derive。

收据还包含 `receipt_version`、`semantics_version`、`contract`、`allowed_business_paths`、`history_preserved`、`frame_respected`。正常业务阶段结束时只标记 `applied_uncommitted`，`committed_revision` 仍为空；后续正式登记才填写 `transition_id`、`bound_actor`、`request_digest`、`pre_state_revision`、`committed_revision` 与最终 `execution_outcome`。

若阶段未完成，收据用 `failed_phase` 和 null 表示没有对应的完成端点；`attempted_delta` 记录异常前可见的尝试差异。回滚后的 `net_delta` 为空，不把部分执行假装为已完成的空 Apply/Derive。进入协议的拒绝尝试还可能被单独提交，形成 `rejected_attempt_committed`：业务变更已回滚与尝试记录已提交并不矛盾。

行动前缓存重建的差异另记 `preflight_projection_delta`，不混入 Apply。运行器在业务 S2 之后追加的时钟推进、调用日志、生命周期排程和 journal 登记不属于上述阶段差分；命令记录和环境事件也分别提交。工具或事件 handler 内明确执行的消息、排程、wait 等状态效果，仍按其实际发生阶段出现在差分中。因此不能把收据解释为整个 `World.act` 返回前所有副作用的完整 diff。

Apply 可以创建真实文件或业务事实，Derive 只允许声明的投影路径；若 Derive 改基础事实、动作超出 frame 或改写受保护历史，则业务状态回滚。文件适配器从正确的已提交状态恢复版本与物化文件。当前强制保持范围包括：

| 历史对象 | 不允许改写的事实 |
| --- | --- |
| 既有产物版本 | ID、所有者、哈希、逻辑时间、`derived_from` 和已存 credential；不得删除版本 |
| 追加历史 | messages、interactions、requirement_events 以及 frame 声明的追加扩展的既有前缀 |
| 原始回应和正式登记 | 既有 `raw_condition_responses`、attestations 的内容 |
| 既有工作/提交 | 不得删除；submission ID、需求版本、行为者、固定产物版本、回答、时间、可见上下文、required_credentials、requirement_snapshot 以及固定扩展保持 |
| 已完成审阅 | 既有 review 内容保持；另用 invalidation/current applicability 记录后续效力 |

条件历史由对应转换追加并供纯投影解释。当前没有通用日志溯源数据库或任意状态 patch 重放承诺。

## 命令、环境事件与单写者提交

新世界初始有 `state_revision: 0` 和 `operation_commits: {}`。每个世界目录在单写者文件锁内工作，原子替换的 `control/state.json` 同时决定正式业务状态、版本指针、操作登记与已提交结果。

命令 ID 为 `command:{actor}:{request_key}`；不提供 request_key 时生成新身份，不能用重新发起的无身份请求声称已经实现重试去重。`request_digest` 是 action 和完整有限 JSON arguments 的规范摘要，绑定角色另行校验。相同身份、相同角色、相同摘要重试，读取已登记 `public_result`，不重跑原 handler；相同身份换 action/arguments 则返回 `CommandConflict`。非有限 JSON、无效请求身份和身份冲突在进入动作前拒绝，`command_committed: false`，不推进逻辑时间。

`operation_commits[operation_id]` 保存 operation_id、kind、bound_actor、request_digest、pre_state_revision、committed_revision、public_result 和 receipt。revision 逐次增加，记录需从 `checkpoint_revision`（缺省 0）之后形成连续后缀。当前字段与原子快照共同构成有限提交协议，不是外部数据库事务或完整事件溯源。

一个已进入协议的工具错误仍可保存拒绝尝试、推进逻辑时间并提交其记录。因此 `ok: false` 与 `command_committed: true` 可以同时成立；这不表示被拒业务内容落盘。成功命令的结果也在处理后续到期事件之前提交。

环境事件用独立 `event:{event_id}`、绑定环境角色及 event_id/kind/at/payload 摘要，逐项运行相同转换检查。每项事件把业务效果、队列移除、event_history、receipt 和 operation_commits 一起提交。相同到期时刻按原入队顺序执行，已登记事件不会再次产生正式效果。它们不并入触发它们的用户命令，也不使用工作人员策略重新决策。

| 返回或诊断字段 | 准确含义 |
| --- | --- |
| `command_committed` / `committed_revision` | 本次命令或已登记重试所对应的正式提交；不由后续事件成败改写 |
| `pending_event_errors` | `event_committed: false`，stage 为 pre_commit；事件效果未提交，原事件留待后续明确重试 |
| `event_delivery_errors` | `event_committed: true`，stage 为 post_commit_delivery；事件已经提交，仅提交后的交付/确认阶段异常，不能回滚到旧文件前缀 |
| `event_attempts` | 持久化失败诊断，含事件身份、主体、摘要、已知提交前缀与可取得的阶段收据；不会据此增加第二次正式效果 |

失败事件之后暂停本轮队列处理，保留有序待处理后缀。命令返回中的事件错误是本次交付信息，并非把该命令已登记的结果改成失败；相同命令重试仍可能继续处理尚未完成的到期事件。原命令效果去重、事件恢复和回复是否送达需要分别判断。

## 文件恢复与验证边界

`Store.put` 先写新的不可变版本文件，再写当前物化镜像；只有正式状态快照引用该版本，它才进入已提交前缀。暂存阶段存在文件不等于版本已经提交。

`Store.recover(state)` 校验提交登记的连续性和所有已提交版本的实际字节哈希，把未被提交状态引用的版本目录移入 `control/uncommitted/`，并按正式 current_version 恢复缺失或不匹配的物化镜像。若已提交的不可变版本缺失或损坏，则报错，不能重新计算一个替代内容来冒充原版本。隔离暂存文件也不等于已经证明介质级销毁。

打开当前 `World` 会完成存储恢复；显式 `World.recover()` 还在锁内重建视图并继续处理到期事件，返回 state_revision、两类事件错误与 pending_events。恢复不重新采样员工策略、不重新计算错误公式、不改写原错误内容。事件提交后的普通异常必须从最新已提交快照恢复，不能拿旧内存快照撤掉已经登记的版本。

E4 在冻结 `fe80b02` 上覆盖同一可信检查点分出的 4 个动作族和 10 个真实 `os._exit` 切点，另保留 1 个提交后普通异常探针。其口径为完整持久状态（仅排除 wall_seconds 和诊断 state_digests）、登记的全部不可变版本及物化镜像字节、正式结果与重试效果；详见 [v0.5 恢复证据](experiments/v05-recovery.json)。这些是单目录、单写者、现有文件系统和声明切点下的有限证据，不证明多写者、任意插件事务、分布式 exactly-once、机器丢失或断电持久性；JSON 原子替换和文件 fsync 本身不足以推出这些保证。

## 义务、修订和业务审阅

通用 `revise_requirement(state, targets, updates, actor, reason)` 只接收显式工作目标及声明性要求，不接受 growth_delta 等领域计算参数。它创建 replacement，保存 `work_replacements`、`requirement_events` 与旧事实，不创建新文件或替工作人员修正内容。引用的新凭据应先存在。

通用提交通过 `submit_work` 固定交付版本、上下文、`required_credentials` 和 `requirement_snapshot`；适配器负责取得真实可读版本。修改已提交文件、撤回或修订可以使待审提交失效，但不改写旧回答和固定文件。被新需求替代的历史 accepted 工作仍可保留 accepted，另以 `current_applicability` 表明已不承担当前义务。

经营适配器仍有共享模型的范围限制：分析假设修订按同一当前分析阶段处理，growth_delta 由该领域适配器解释；不假装是通用字段级因果传播。工作—发布联合可达性检查仍是有限语言下的乐观结构可达性，不是业务可解性证明。

公开受众字段、引用和经营数值约束由领域合同说明。工作人员可以写错公式、错误采用或过早提交；有权审阅者可能接受错误结果。无权签发或伪造提交版本属于不能执行的行为；可执行但不合适、业务拒收、独立评价失败必须分开记录。

## 模板和接口范围

经营配置保留 chain、fork、selective、coordination 四种配置，对应 chain、fork、selective 三种工作图；coordination 是 chain 加信息协调。standard、basis_only、during_update、waiting_reply、during_review、unavailable 是该模板已有情境，未提升为内核枚举。shifted 布局附位置指南，selective 明确给出应改范围；不能据此声称无指南布局泛化或自主影响分析。

经营 `World.session(actor)` 绑定身份；进入提交协议的行动返回 `ok`、`action_id`、`logical_time`、`command_id`、`command_committed`、`committed_revision` 和 result/error，后续事件异常另附对应字段。mail_send、block_work、withdraw 保持工具参数；`revise_requirements` 是经营修订适配入口；`restore_information` 是有权限环境主体的恢复入口，分析师越权尝试返回错误。

微模板通过 `domains.publication.compile_publication` 和 `PublicationWorld` 构建 source_note、editorial_policy、draft。它配置 author/editor 的岗位与权力，可替换员工 ID，复用 `confirm_credential`、版本授权、条件满足、通用提交/撤回/修订/批准和转换检查。独立检查只针对来源引用、字段、采用声明与政策要求短语，业务审阅有意较窄；既不检查真实出版专业质量，也不将业务接受当作独立正确。

## 独立评价与实验导出

经营评价针对指定提交及其固定要求，保留 `passed` / `artifact_valid`、`business_accepted`、`currently_applicable` 的区别。缺少适用批准时，文件与依赖等可检查要求继续评价，依赖隐藏假设的数值目标进入 `unassessed_checks`，不借完整生成规格回填业务上尚未确定的目标。

四态是内核检查格式；现有经营评价的二值 `checks` 与单独 `unassessed_checks` 是输出适配，未评不会折算为通过。`numerical_assessment` 区分未提交、可评和缺批准；`assessment_scope` 固定为提交自身需求版本。`root_causes` 和 `propagated_failures` 是有限的依据传播分组，不是模型心理归因或完备因果证明。

文稿独立评价返回 checks 的 PASS/FAIL/UNASSESSED、`passed`、`business_accepted`、`currently_applicable` 和有限 `evaluation_scope`；其世界合同单独标为 `publication-micro-v0.1`，没有声称经营评价器覆盖文稿质量。

既有导出仍包含 manifest、episode、calls、interactions、evaluations、candidates、sft、rl 和完整 world 快照。调用保留真实 messages/tools、原始返回、服务端 usage 与 attempts，不纳入 API 密钥；未知 usage 不用字符估算填充。快照分支、谱系划分、历史候选与 message loss mask 的归档接口保留，后续被替代的旧提交不自动变成新要求的监督。

SFT 候选仍是 `outcome_conditioned_candidate`，不是逐步专业金标；RL 中未提供的 token ID 和行为概率保持缺失，不能视为已完成在线训练协议。本阶段验证的是有限工作世界语义、纯投影、跨模板条件复用及有界提交恢复，没有新增参数训练、扩大上下文效果或证明训练收益。内核自洽也不证明合成经营假设与真实专业实践一致。
