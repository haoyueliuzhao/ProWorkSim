# 数据契约与扩展接口

## 世界对象

新世界带有 `schema_version: "0.2"`；保留对 0.1 历史实例的读取与复核。`WorldSpec` 包含 `ProjectSpec`、`RoleSpec`、种子、来源与情景配置；完整规格仅供编译器和独立验证器使用。

| 对象 | 关键字段与语义 |
| --- | --- |
| `ProjectSpec` | 项目 ID、来源谱系、分组、业务对象、初始状态、信息获取方式、核心操作、交付粒度、连续性、采样池 |
| `RoleSpec` | 身份、职责、固定策略标识、是否目标执行者、是否有批准权 |
| `WorkItem` | 所属项目、起因事件、责任者、目标、可见要求、输入、工作依赖、交付物、状态、要求版本、提交历史 |
| `ArtifactVersion` | 产物与版本 ID、所有者、文件 SHA-256、逻辑时间、`derived_from`、交付与审阅状态 |
| `InteractionRecord` | 行动 ID、角色、输入、实际输出或错误、读写对象及前后版本、逻辑时间、真实耗时 |
| `WorldSnapshot` | 实例、分支、逻辑时间、状态校验和；目录内包含完整真实文件版本 |
| `EvaluationRecord` | 提交、需求版本、分项检查、通过情况、奖励、有效性、不确定项、评价器版本 |

`acceptance_spec_ref` 不进入工作人员观察。已接受状态绑定具体 submission 与 artifact versions，不代表所有后续文件版本自动获批。

## 工具协议

```python
from proworksim.compiler import compile_world
from proworksim.designer import design
from proworksim.kernel import World

compile_world(design(seed=4, delivery="file"), "runs/world-4")
session = World("runs/world-4").session("analyst")
observation = session.observe()
result = session.call("sheet_read", artifact_id="model")
```

返回包始终包含 `ok`、`action_id`、`logical_time`，以及 `result` 或 `error`。业务错误、无权操作和不支持的公式会成为可记录的工具反馈。业务工作人员不能读取 evaluator。

写入依赖的格式为：

```json
[
  {"artifact_id": "financials", "version_id": "v2"}
]
```

绑定版本是一项真实工作动作。模型更新工作簿时若未重新绑定来源，系统会保留旧依赖，不替它猜测来源已经变了。对于用户指定的某个历史版本，读取仍服从身份和逻辑时间约束。

## 三个复杂度维度

当前模板可以明确区分输入材料、实际状态修改与最终交付。它们不是已经测得的通用难度分数。

| 模式 | 输入材料复杂度 | 执行与状态修改 | 最终交付 |
| --- | --- | --- | --- |
| short | 已有模型 + 指定披露来源 | 检索和组合计算；不要求改模型 | 数值与来源列表 |
| file | 已有模型 + 披露 + 邮件或口径回复 | 更新输入、重算、增加情景分析区域 | 一个 XLSX |
| continuous | 前述材料 + 旧备忘录 + 新需求版本 | 跨产物同步、审阅、继续处理第二轮 | 两个相互依赖的文件及接受记录 |

在 short 模式下，口径消息配置不构成必需实时澄清；不能因为编译参数带有 `clarification` 就声称该短任务测量了协作能力。现有实现只有有限结构模板，名称和数值多样性不等于结构多样性。

## 导出包

```text
export/
  manifest.json
  calls.jsonl
  interactions.jsonl
  evaluations.jsonl
  candidates.jsonl
  sft.jsonl
  rl.jsonl
  world/                   # 可恢复快照，含后台文件，仅供实验/训练系统
```

`calls.jsonl` 记录模型实际请求与返回。请求中含原始 messages 与 tools；没有 API 密钥或 HTTP Authorization。usage 来源于服务端响应，不用字符数伪造 token 数。

`candidates.jsonl` 保留目标执行者的全部候选监督记录，包括不合格记录。`sft.jsonl` 只包含当前规则判定可用于监督的记录：

```json
{
  "lineage_id": "synthetic-operating-101",
  "split": "train",
  "branch_id": "...",
  "call_id": "...",
  "messages": ["原始请求消息...", "本次目标模型返回..."],
  "tools": ["当时使用的工具定义..."],
  "message_loss_mask": [0, 0, 1],
  "eligible": true,
  "token_ids": null
}
```

上例仅示意结构，实际 `messages`、`tools` 是完整对象。所有历史消息和环境输出的掩码为零，仅本次目标模型输出可为一。错误提交之前的动作不作为本次成功修订的正向示范；实际错误仍留在后续模型当时看到的上下文中。

`rl.jsonl` 把 `observation`、目标 `action` 与 `tool_observations` 分开。`verified_segment_reward` 表示动作所在已验证提交区间的结果，不是经过证明的逐步最优奖励。`on_policy_training_ready: false` 提醒训练适配层需要真实 token 和行为概率协议。

## 分组、分支和重复数据

同一 seed 的所有变体使用同一 `lineage_id`，按稳定 SHA-256 划分 train/dev/test。`assert_disjoint` 会拒绝相同谱系跨不同分组的 manifest。

快照默认恢复成新 `branch_id`；继承的调用仍保留原始分支归属，可作为上下文，不重复编译为新分支的监督目标。`--same-branch` 面向恢复原实验，操作者应避免将两个同分支恢复副本都计为独立样本。

v0.1 没有实现跨外部公开来源的聚类，也没有专门保留未见结构组合。使用真实材料或增加模板时，需要扩展谱系关系和划分协议，再开展泛化实验。

## 接入新的模型或训练后端

运行器接受提供 `provider`、`model`、`payload(messages)`、`complete(request)` 的后端。返回应保留模型原始 message、tools、usage 与可用概率信息；不要事后改写成更整齐的示范。

新的训练后端应读取原始 messages/tools，使用对应模型的 tokenizer 和 chat template，严格落实消息级掩码。当前包是中间格式，不宣称可以不经转换直接送入所有 SFT/RL 框架。参数训练器应运行在世界外部，固定一批 rollout 的目标模型版本，再进行更新。

Archipelago、Harbor 和 Agent Lightning 目前均未接入；核心世界对象没有依赖其目录格式。后续可在边界增加适配层，而无需改变当前任务和产物的概念。


## 审计后扩展

新增 `WorkflowSpec / WorkNode / EventRule / LayoutMap / CitationRequirement / ArtifactContract`。
公开引用指南与评价来自同一要求对象，参考数值仍独立计算。freshness 分为 current、stale、unknown；新写入不会自动证明来源关系完整。

导出增加 `episode.json`，分别保存 artifact_valid、business_accepted、explanation_assessed、trajectory_supervision_status。各次模型 run 的 manifest 位于 `control/runs/<run_id>/manifest.json`；调用记录内 `attempts` 独立描述底层 HTTP 尝试。未知失败 usage 为 null。

新增 source_family_id、template_id、topology_id、layout_id、role_information_id、scenario_id 作为结构标注。当前谱系分组仍不能独立证明结构泛化。

本地训练适配将 message mask 转为真实 tokenizer 的 token labels，训练工具参数以目标 chat template 要求的对象表示。`reasoning_content` 不转入另一模型的隐藏思考格式。Teacher 来源和目标权重分开记录，训练/重载/后续执行结果见本轮实验报告。
