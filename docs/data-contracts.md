# 数据契约与扩展接口（v0.3）

本文对应软件包版本 `0.3.1`、`schema_version: "0.3"`、`contract_version: "operating-world-v0.3"` 与独立评价器 `operating-world-v0.3.1`。工作世界语义及设计边界见 [world-semantics-v03.md](world-semantics-v03.md)。实现仍允许读取 0.1、0.2 历史世界；读取旧格式不代表旧实例已具备新依据、阻塞或生命周期记录，不应将其缺失字段补解为已验证事实。

## 世界对象与规格

`WorldSpec` 保存 `ProjectSpec`、`RoleSpec`、种子、来源事实、情景假设、工作流、布局、`lifecycle_events` 和 `unavailable_topics`。完整规格仅供编译器、实验系统与独立评价器使用，不作为分析师观察内容。

| 对象 | 字段与语义 |
| --- | --- |
| `ProjectSpec` | 项目、谱系、划分、业务对象、交付粒度、信息方式与结构标注；不包含经过实验证明的通用难度分数 |
| `RoleSpec` | 身份、职责、策略标识、`trainable`、`can_approve`、`can_confirm_basis`；交付批准权与假设确认权分开 |
| `WorkItem` | 工作实例 ID、逻辑节点、责任者、目标、要求版本、输入、前驱、交付物、提交历史、阻塞与当前适用性 |
| `ApprovedBasis` | 已批准分析假设、适用范围与期间、确认者、确认记录、生效时间和被替代版本 |
| `ArtifactVersion` | 产物与版本 ID、所有者、SHA-256、逻辑时间、`derived_from`、交付及审阅状态；真实文件版本独立保存 |
| `InteractionRecord` | 行动 ID、身份、输入、输出或错误、实际读写及前后版本、逻辑时间和真实耗时 |
| `WorldSnapshot` | schema、实例、分支、逻辑时间及状态校验和；快照目录包含完整文件版本 |
| `EvaluationRecord` | 指定提交及要求版本的检查、通过状态、奖励、有效性、不确定项和评价器版本；运行时另附适用性与传播诊断字段 |

`acceptance_spec_ref` 不进入工作人员观察。状态中的部分生命周期字段由编译器、工作流或内核运行时补充，不能仅依据 `WorkItem` dataclass 的基础字段判断序列化对象是否完整。

结构标注分开保存：

| 字段 | 当前含义 |
| --- | --- |
| `configuration_id` | chain、fork、selective、coordination 四种工作配置 |
| `work_graph_id` / `topology_id` | chain、fork、selective 三种工作图；coordination 使用 chain 图 |
| `role_information_id` | mail 或 clarification |
| `scenario_id` | standard、basis_only、during_update、waiting_reply、during_review、unavailable |
| `event_policy_id` | 当前事件策略标识 |
| `error_injection_id` | 世界的错误注入标注；程序策略额外注入需另记实验条件 |
| `layout_id` | standard 或 shifted；均提供对应语义位置指南 |
| `source_family_id` / `template_id` | 来源族与业务模板；目前仍是有限的合成经营分析族 |

## 批准依据与采用关系

`basis` 是可引用的真实 JSON 产物，内容为 `ApprovedBasis`。`scope` 仍是经理私有工作材料，分析师不能直接读取。

| `ApprovedBasis` 字段 | 合同 |
| --- | --- |
| `basis_id` / `version_id` | 依据产物及文件版本，例如 `basis` / `v2` |
| `project_id` | 适用项目 |
| `requirement_version` | 分析假设的需求版本，正整数；不等于文件版本字符串 |
| `requirement_dimension` | 当前固定为 `analytical_assumptions` |
| `applicable_work_nodes` | 适用的逻辑工作节点 ID，按 `node_id` 匹配；不要求改写为每次 replacement 的实例 ID |
| `period` / `effective_at` | 适用期间、生效逻辑时间 |
| `confirmed_by` / `confirmation_ref` | 确认角色与可追溯确认 ID；当前由具有 `can_confirm_basis` 的 manager 签发 |
| `assumptions` | 增长率、利润率变化、税率、估值倍数等实际确认内容 |
| `supersedes` / `status` | 被替代的依据文件版本；正常记录状态为 `approved` |

`state.basis_approvals` 保存确认 ID、角色、依据版本、逻辑时间、分析需求版本和工作节点；独立评价同时检查该记录，不能只相信文件里自称 `confirmed_by: "manager"` 的字段。`basis_by_scenario` 将分析阶段映射到所需依据引用。

每项工作保存：

```json
{
  "node_id": "work-1",
  "work_item_id": "work-1",
  "requirement_version": 1,
  "basis_requirement_version": 1,
  "required_basis": {"artifact_id": "basis", "version_id": "v2"},
  "source_period": "FY2025"
}
```

示例中的 `v2` 是文件版本，整数 `1` 是分析需求版本。仅受众变更可以提高整体 `requirement_version`，同时保留 `basis_requirement_version`。依据适用性检查确认记录、项目、逻辑节点、分析需求版本、期间及生效时间；没有 `required_basis` 或无法确认适用时，不推定已有批准。

产物的实际采用由写入时的 `dependencies` 声明，最终保存于 `ArtifactVersion.derived_from`。模型的必要输入为 `financials` 和 `basis`，例如：

```json
[
  {"artifact_id": "financials", "version_id": "v2"},
  {"artifact_id": "basis", "version_id": "v2"}
]
```

memo 需要绑定 financials/model；note 需要绑定 model/brief。公开引用要求由 `CitationRequirement` 表达，区分同时必需的 `required_all_of` 与任选其一的 `required_any_of`。正文的 `source_versions`、声明依赖和引用版本仍需一致。

读取历史、获得访问权和声明采用是三个不同动作。写入未提供新依赖时保留原声明，后台不会把所有已读材料自动加入采用来源，也不会替工作人员更新模型输入。声明了最新依据同样不证明实际计算正确，评价还会比对输入值并独立重算。

## 版本权限与新鲜度

产物拥有整体 `readers` / `writers`，另可通过 `version_readers[version_id]` 授予单个版本访问权。读取同时要求版本存在、逻辑时间已到及该角色具有整体或该版本权限。未指定版本时，工具返回该角色可见的最新版本，可能早于产物后台的 `current_version`；实际返回的 `version_id` 才是本次读到的版本。

mail 配置公开适用依据；clarification 配置通过定向回复授权请求时绑定的依据版本。`basis_visibility` 记录角色、版本、确认凭据及授权时间。v2 的晚到回复只授权 v2，不会开放私有 v3。已有可读且适用的凭据可以直接使用，不要求重复发送 scope 请求。附件的接收者也必须具有对应版本的访问权。

| 产物字段 | 值与计算范围 |
| --- | --- |
| `freshness` | `current` / `stale` / `unknown`，根据实际声明依赖与必要输入边递归计算 |
| `data_freshness` | 同三种状态，沿依赖链计算时排除 basis 输入，用于区分数据变化与假设变化 |
| `basis_applicability` | `current` / `stale` / `unknown` / `not_applicable`，沿声明依赖链检查采用的 basis 版本与当前所需确认；缺少当前适用确认时为 `unknown`，没有相关依据要求或依赖边时为 `not_applicable` |
| `possibly_stale` | `freshness != "current"` 的便捷标记，包含 unknown |
| `freshness_basis` | 当前为 `declared_dependencies_and_required_edges`，显式记录判断依据 |

`basis_applicability` 根据依据依赖链与当前工作所需确认判断，不替代独立评价中的完整确认者、工作范围与期间适用性检查。当前工作 `required_basis: null` 时，不能将历史 basis 中最新的文件版本当成当前适用确认；相关状态为 unknown。`current` 也不代表数值正确或内容已经专业审阅。

仅修订批准假设时，financials 可保持原版本和字节，model/memo 的 `data_freshness` 可保持 current，而 `basis_applicability` 和总体 freshness 变为 stale。新鲜度变化不自动修改产物。仅 brief 受众变化时，未依赖 brief 的 model/memo 保持其版本及适用状态。

## 工作、发布与生命周期

`WorkflowSpec` 包含 `WorkNode` 和 `EventRule`。工作要求前驱全部接受且发布组开放；事件要求 `after_accepted` 全部满足，同一发布组的不同生产者按 OR 处理。验证器从 `initial` 开始交替扩展工作和事件至不动点，拒绝未知引用、无入口循环和相互等待，并列出不可达节点及原因。空接受条件的启动规则也会实际排程。该检查假设可激活的工作能够被正确完成，只保证有限语言下的乐观结构可达性。

`lifecycle_events` 是另一个有限事件入口，每条包含 `event_id`、`trigger`、`effect` 和可选 `delay`。当前触发动作包括 sheet_update、write_file、mail_send、submit、wait，可按角色、工作或 topic 过滤；仅成功动作会触发。当前效果为 `revise_basis`，包含目标工作与增长率变化。它与完成后的 `EventRule` 分开记录，支持编辑中、等待回复中及待审阅期间发生变化。

运行时工作还保存 `node_id`、`activated_at`、`source_period`、`required_basis`、`basis_requirement_version`、`applicability`，替代时增加 `supersedes` / `superseded_by`。`state.work_replacements` 链将逻辑前驱和事件 guard 解析到当前实例。

| 状态或字段 | 后果 |
| --- | --- |
| `open` / `in_progress` / `revision_required` | 可在前置条件满足时提交 |
| `blocked` | 尚有需要回应或明确不可得的条件；不能直接提交 |
| `waiting_dependencies` | 替代工作仍等待前驱重新接受，不当作已就绪 |
| `in_review` | 待审具体 submission；可由责任者撤回 |
| `accepted` | 某次具体 submission 已获业务批准，未自动批准后续版本 |
| `superseded` | 尚未完成的旧实例已被新要求替代 |
| `cancelled` | 保留的非活动状态枚举；当前无通用取消工具 |
| `applicability` | 工作级 `current` 或 `superseded_requirements`，与历史 accepted 状态分开 |

经理修订会签发新 basis 并创建如 `work-1@r2` 的新实例，清空新实例的提交及 blocker 引用，保留原实例与文件。未审提交标记失效；已接受提交的批准者、时间和产物版本不改写，仅将其 `current_applicability` 设为 `superseded_requirements`。已解决 blocker 的记录保留；仍未解决的旧 blocker 标为 superseded。

本领域共享一个经营模型，因此依据修订按同一当前分析阶段整体处理；不支持跨阶段拼接修订。另一分析阶段已经激活时，拒绝向旧阶段回写，并要求修订当前阶段。该范围是明确领域限制，不表示已实现通用字段级因果传播。

submission 保存 `requirement_version`、`artifact_versions`、`context_versions`、`required_basis`、`review`、`invalidated` 和 `current_applicability`。`context_versions` 是提交时可见的上下文版本快照，不是实际采用来源清单。`withdraw` 保留提交及文件，将该提交标记失效、记录 `review.decision: "withdrawn"` 与撤回原因；工作回到 in_progress，可重新提交。

## 结构化阻塞与定向回复

`state.blockers` 以 `blocker_id` 为键保存记录；工作通过 `blocker_ids` 引用多个条件。旧 `blocker` 文本仅供展示，不决定回复能否解除阻塞。

| blocker 字段 | 合同 |
| --- | --- |
| `blocker_id` / `work_item_id` | 阻塞与具体工作实例 |
| `kind` / `requested_role` | scope、audience 或 evidence；需要回应的角色 |
| `required_scope_version` | 分析需求版本整数；scope 必须明确，其他类型可为 null；不是 `v2` 字符串 |
| `creation_requirement_version` | 创建时整体工作需求版本，用于拒绝过期回复 |
| `detail` / `created_at` | 非空问题描述、逻辑时间 |
| `status` | open、resolved、unavailable、superseded |
| `request_id` / `resolution_ref` | 绑定的实际请求与可见解决凭据；可见消息引用不等于已满足条件 |
| `history` | 逐次状态、时间及变化详情，原记录保留 |

请求绑定保存在 `state.requests`，包含工作实例、整体及分析需求版本、topic、角色、请求时 basis/brief 引用及可选 blocker ID。回复按请求所绑定的版本产生，不临时替换为世界最新版本。scope 的有效回应角色是 manager，audience 是 client；错误角色不会确认对应业务条件。

只有请求、工作、类型、角色、版本均匹配的 open blocker 才能 resolved。单个请求不能跨工作复用；工作全部条件已解决或退休，且前驱已接受，才会重新开放。无关消息、旧回复、错角色回复都不能把所有 blocked 工作一并打开。

信息不可得时，记录 unavailable 与实际回复引用，工作继续 blocked。支持先声明 blocker 再请求，也支持先收到定向不可得回复，再通过 `request_id` 关联 blocker。若没有事件仍待处理，所有当前未接受工作均为 blocked 且各有 unavailable blocker，观察返回 `terminal_reason: "blocked_unavailable"`，运行器可据此结束 episode；`complete` 仍为 false。这是合法世界结果，不是业务成功或模型通过。

## 工具协议

```python
from proworksim.compiler import compile_world
from proworksim.designer import design
from proworksim.kernel import World

compile_world(design(seed=4, delivery="file", scenario="standard"), "runs/world-4")
session = World("runs/world-4").session("analyst")
observation = session.observe()
result = session.call("sheet_read", artifact_id="model")
```

行动返回包含 `ok`、`action_id`、`logical_time`，以及 `result` 或 `error`。业务错误、无权操作和不支持的公式成为真实工具反馈。身份由 session 绑定，不能通过工具参数冒用 manager/reviewer。

新增或扩展的接口：

| 工具 | 参数及结果 |
| --- | --- |
| `mail_send` | 新增 `work_item_id`、可选 `blocker_id`；返回请求 `message_id` 与工作 ID。存在多个可能工作时必须明确工作；单一候选可推断，但调用者应优先明确绑定 |
| `block_work` | `work_item_id`、`reason`、`kind`、`requested_role`、`required_scope_version`、可选 `request_id`；返回 `blocker_id`、完整 blocker 和工作观察 |
| `withdraw` | `work_item_id`、`submission_id`、`reason`；只允许责任者撤回当前待审提交 |
| `revise_requirements` | 内核 manager 接口；输入 `work_item_ids`、`growth_delta`、`reason`，返回 `replacements`；分析师无权调用 |

`block_work(kind="scope")` 未显式提供版本时使用该工作 `basis_requirement_version`，缺失时退回 `requirement_version`。如果显式提供，必须是匹配的正整数；填写 `required_basis.version_id` 是合同错误。

## 独立评价与诊断

评价针对指定提交及当时绑定需求，不将世界最新要求强加给所有历史文件。评价记录新增：

| 字段 | 含义 |
| --- | --- |
| `artifact_valid` / `passed` | 提交相对于其要求版本的检查结果 |
| `currently_applicable` | 是否为 replacement 解析后的当前工作，且该提交未失效；与历史正确性分开 |
| `assessment_scope` | `pinned_submission_against_its_requirement_version` |
| `numerical_assessment` | `not_submitted`、`available` 或 `blocked_missing_approved_basis`，区分未提交、具备数值评价条件及缺少适用批准依据 |
| `unassessed_checks` | 未能评价的检查数组，每项含 `name`、`category`、`reason: "missing_applicable_approved_basis"`；这些项不混入二值 `checks` |
| `business_accepted` | 指定提交的业务 review 是否 accepted；独立数值检查可能仍失败 |
| `explanation_assessed` | 当前为 false，未声称完成专业解释质量审查 |
| `root_causes` | 依据或假设输入错误的有限分组，每项含 `code` 和 `evidence_checks` |
| `propagated_failures` | 存在上述分组时，列出 calculation、consistency、recalculability 的连带失败检查 |
| `diagnostic_interpretation` | 明确是依赖分组，不解释工作人员心理原因或多个独立能力缺口 |
| `verified_dependencies` | 通过评价的提交产物实际声明依赖 |

对于需要批准假设的 file/continuous 提交，若当前绑定要求没有适用批准依据，`approved_basis_applicable` 与 `model_basis_binding` 仍判失败，披露来源输入、文件完整性及依赖等可验证条件继续检查。假设输入、目标输出、敏感性分析、扰动重算和 memo/note 目标数值进入 `unassessed_checks`，不使用隐藏 spec 中的假设回填可取得的工作依据，也不将无法评价记作数值正确或数值错误。short 基于指定已有模型和披露的问答保持其自身评价条件；没有提交时标记 `not_submitted`。

当前根因代码为 `approved_basis_not_applicable_or_unbound` 和 `approved_assumptions_not_applied`。依据检查失败优先记录前者；否则已批准假设与实际输入不符时记录后者。它们是针对已知依赖链的诊断，不是完备因果归因系统。只替换依赖标签而沿用旧增长率仍会被输入与计算检查识别。

## 交付粒度与导出包

| 模式 | 输入与操作 | 最终交付 |
| --- | --- | --- |
| short | 已有模型与指定披露，检索和组合计算；不要求改模型 | 数值与来源列表 |
| file | 披露、模型与适用依据，更新输入、重算及敏感性分析 | 一个 XLSX |
| continuous | 多个版本、依赖产物、事件及后续要求 | 按工作配置提交 model/memo/note，并保存各次审阅 |

short 的口径消息配置不构成必需实时澄清。移动布局提供指南，selective 明示只改 note；这些条件分别检验语义位置映射和执行指定影响范围，不等于任意布局理解或自主发现所有影响范围。

```text
export/
  manifest.json
  episode.json
  calls.jsonl
  interactions.jsonl
  evaluations.jsonl
  candidates.jsonl
  sft.jsonl
  rl.jsonl
  world/                   # 完整可恢复快照，供实验/训练系统使用
```

`episode.json` 保留全部工作、评价和调用，按当前工作集合汇总 `artifact_valid`、`business_accepted`、`world_outcome`、`archived_work_count` 与 `trajectory_supervision_status`。`world_outcome` 为 accepted、blocked_unavailable 或 unfinished。历史工作仍在记录中；`professional_gold` 和 `explanation_assessed` 均为 false。

`calls.jsonl` 保存模型真实 messages/tools、原始响应、usage 及底层 `attempts`；不记录 API 密钥或 Authorization。usage 来自服务端，未知失败 usage 为 null，不由字符数补造。各次模型运行的 manifest 位于 `control/runs/<run_id>/manifest.json`，记录版本、预算、快照和停止原因。

`candidates.jsonl` 保留有响应的分析师调用候选，包括不合格记录。当前 SFT 准入要求调用落在已通过独立评价、业务 accepted 且未 invalidated 的提交区间内，实际工具调用完整且成功、属于当前分支，并排除 rule_based/fixture 来源。后续被替代但当时正确且已接受的历史提交仍可作为对应旧要求的候选；没有把历史批准自动用作新要求的监督标签。

监督样本保存原始 messages/tools、谱系、分支、call/submission ID 与 `message_loss_mask`。历史消息和环境输出掩码为零，仅本次合格目标模型输出可为一。错误提交前的动作不计为后来成功修订的正向目标；真实错误仍保留在模型当时看到的上下文。准入描述为 `outcome_conditioned_candidate`，不等于逐步推理已验证或专业金标。

`rl.jsonl` 分开保存 observation、目标 action 和 tool_observations。`verified_segment_reward` 是已验证提交区间的结果，不是证明过的逐步最优奖励。`on_policy_training_ready: false` 表示仍需真实 token 与行为概率协议；缺失 token ID 或概率保持 null。

## 分组、分支与后端边界

同 seed 的变体共享 `lineage_id`，按稳定 SHA-256 划分 train/dev/test；`assert_disjoint` 拒绝同谱系跨不同划分。当前没有外部公开来源聚类或专门的未见结构组合留出，结构标注本身不证明结构泛化。

快照默认恢复为新 `branch_id`。继承调用保留原分支身份，可作上下文，不重复成为新分支目标；同分支恢复的两个副本也不能作为独立样本重复计数。

运行器后端提供 `provider`、`model`、`payload(messages)`、`complete(request)`，保留原始 message/tools、usage 与可用概率信息。训练适配器须使用对应 tokenizer/chat template，将消息掩码转换为真实 token labels；不将 `reasoning_content` 改写成另一模型的隐藏思考格式。teacher 来源和目标权重版本分别记录。

当前包是中间交换格式，未接入 Archipelago、Harbor 或 Agent Lightning。参数训练器位于世界之外；旧 LoRA 冒烟仅证明训练/重载接口，本轮 v0.3 世界修订与固定模型试跑不构成新的参数学习收益证据。
