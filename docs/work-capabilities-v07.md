# v0.7 工作能力与成果使用：实现说明

依据：[审计](reference/work-capabilities-audit.md)和[两阶段计划](work-capabilities-v07-plan.md)。本文件随两个阶段分别收口；正式结果独立归档，不将开发试跑与冻结实验混计。

## 阶段 A：权限路径与共享文件能力

WorldCore 新状态格式为 `world-core-v0.7`，工作语义为 `work-world-v0.7`，阶段回执继续沿用 `phase-deltas-v0.5`。不隐式重写旧 v0.6 世界；其历史格式和发布政策使用对应冻结版本解读。

同项目的基础 ACL 与精确分享共同决定读取。分享一个版本不会将接收者加入全版本 readers；其他版本、其他人仍独立检查。初次采用及采用更新都从可信项目上下文解析对象和工作集合，逐工作传递真实 object_id。初次跨项目采用在确认实际精确可读后，以仅含候选别名的只读权限上下文核对既有授权，不增加权力。fixed 政策、错误项目/对象/工作与不可读版本继续拒绝。

`adapters.capabilities` 是有限能力注册表，目前只支持：

| kind / application | 工具与数据 | 边界 |
| --- | --- | --- |
| json / files | create_object、read_object、write_object；data 为 JSON object | 受控别名与相对文件名 |
| xlsx / spreadsheets | create_object(kind=xlsx)、sheet_read、sheet_update、sheet_recalculate | 复用现有 Spreadsheet 的有限公式、范围与规模限制 |

WorldSpec.applications 明确启用能力。工具发现和实际准入使用同一能力选择；`ProjectSession.tools()` 返回参数定义，scope 和身份仍由会话绑定，不进入工具参数。未启用表格能力时不会展示或执行 sheet 工具。

项目包初始对象与工作人员动态创建使用相同编码、Store 与世界级对象身份。XLSX 在受控空间内保存真实字节，编辑和重算生成不可变版本。ZIP 时间戳与文档创建/修改时间规范化，使同一输入重试有稳定序列化；单元格、公式及错误缓存不在比较时删去。`=1/0` 等错误是可以落盘的工作错误，不被当成不合法文件操作。

### 固定提交的独立评价

工作合同可声明 `allowed_kinds`、`allowed_roles`、文件数量及 `required_fields`，再选择有限 `content_checks`：

- json_field_equals：实际 JSON 字段与明确标量比较。
- xlsx_cell_equals：不可变工作簿中指定单元格缓存与明确标量比较。
- xlsx_no_formula_errors：实际公式缓存不可缺失或为错误值。
- json_matches_source_cell / json_matches_source_field：JSON 的正文来源引用、实际数值与提交时采用的精确输入接口一致。

评价通过 version_path 读取固定提交版本并核对 sha256，不从当前镜像或隐藏正确模型读答案，也不调用被测公式引擎生成期望。内容评价不反向写入 review 或修复产物。来源接口核对只说明 B 与所消费成果一致；A 的计算是否正确需要自己的独立合同。

提交另保存 adoption_snapshot，包括明确采用版本与提交时政策目标，受历史保持检查保护。后续采用或发布不能改变旧提交的判据。当前字段齐全或 adoption_view=current 不能替代正文和输入关系检查。

## 使用示例

```python
from proworksim import WorldSpec
from proworksim.world_core import WorldCore

world = WorldCore.create("runs/capability-demo", WorldSpec(
    world_id="capability-demo", actors={"operator": {}, "worker": {}},
    applications=["files", "spreadsheets"],
    bootstrap_grants=[{"actor_id": "operator", "power": "*", "scope": "world"}],
))
# 项目包通过operator的install_project装载；工作人员使用绑定项目会话。
# create_object(kind="xlsx", alias="analysis", filename="analysis.xlsx",
#   data={"Report!A1":10,"Report!A2":4,"Report!A3":"=A1-A2"},
#   deliverable_role="model")
# sheet_update(alias="analysis", cells={"Report!A1":12})
# sheet_read(alias="analysis", version_id="v2")
```

本阶段不接入 GUI、宿主 Shell、任意插件或全部 Excel 函数。金融期间、单位、允许假设及指标定义仍由领域合同描述，不能成为通用世界分支。真实材料来源的四种标记与不得捏造过程历史的要求继续保持。

## 阶段 B：发布、采用与内容

新世界的 publication_policy 默认为 explicit，项目包可以明确覆盖为 explicit 或 implicit_write。当前公开配置入口为世界／项目级；底层政策查询预留对象字段，不将其说成已经存在对象级配置工具。

显式政策下，创建/保存/重算只生成真实草稿版本，不创建 release，不自动扩展订阅读取权或推送更新通知。`publish` 必须另有发布权，绑定精确版本与明确目标项目；可额外限定源工作范围。拥有写 ACL 不能因此发布，但仍可以保存自己的草稿。旧 implicit_write 政策按声明在写入后记录发布后果；它不为旧历史补造 release。原 v0.6 回归夹具在新格式中显式选择旧政策，历史报告不改。

release 包含 release_id、object_id、version_id、actor_id、source_project、at、policy 和 scope（target_projects/work_ids）。其记录受追加保持保护。相同精确版本和范围重复发布无新增效果；发布本身不代表其他项目已经读取或采用。只有已明确选择 follow_updates 的分享路线，且目标项目在发布范围内，才获得该版分享及通知；上游私有对象不会递归授权。

current_published 的政策目标取该消费项目范围内最后发布版本；没有发布时为 unassessed。fixed 保持明确版本。兼容的 current_applicable 仍表达旧“当前版本指针”政策，不能与 current_published 混用结论。采用工具改标签，不改文件；提交保存采用及目标快照，历史评价不随后续发布变化。

来源内容检查还要求实际提供结果字段/来源字段的每份 JSON 固定版本，在 derived_from 中声明该精确输入。无关草稿不强制添加来源，B 不必读取 A 的上游材料。如果正文来源、采用和依赖都变为 v2，但内容仍是 v1 数字，独立数值检查仍拒绝。

A 的独立标量检查与 B 的成果接口检查分别解释：A 的错误计算可能得到合法正式批准；B 忠实消费这个错误接口可以满足自己的接口合同，但不能据此将 A 的结果称为正确。

## 公开会话、资料路线与程序工作人员

`ProjectSession.tools/observe/call` 是工作人员的唯一环境入口。观察提供公开合同、需求版本、可读别名/版本、适用的 release、采用状态和本项目条件；私有文件内容不进入观察。

项目包可声明 information_routes：route_id、work_id、provider、object_alias、purpose、delay、availability。当前有限路线只提供同包实际初始版本 v1，provider 必须是对象实际 writer，并拥有对应工作/对象的 provide 权。路线是客户端明确配置的取得机会，不是自动发现任意外部资料。

`request_information(route_id, work_id)` 从可信配置解析精确证据；工作人员不用猜后台对象 ID、金额或事件时间。真实延迟事件记录 delivered/unavailable，只有明确 available 路线才精确分享该版给工作责任者；ordinary request/reply 不会凭空授权。没有路线时可以合理等待并标出能力缺口，不补写隐藏请求参数。

`public_worker.run_public_worker()` 是透明、有限程序策略：只支持一个当前责任工作，以及一项 json_matches_source_cell/field 合同。它发现工具和资料，必要时请求并按单步逻辑时间等待，再实际读取、声明采用、创建并提交 JSON。每次工作人员运行使用独立 run_id，工具动作的 request_key 包含该 run_id 和动作序号；完整保存当时返回的工具定义、观察、请求和响应。不保存模型推理，也不是通用规划 Agent 或自动续跑策略恢复器。

CLI `world-tools` 可查看工具，`world-worker --actor ... --project ... --output NEW_JSON` 运行此程序工作人员，要求轨迹文件位于世界外且不覆盖已有文件。缺资料、不可得、合同不支持和预算耗尽分别保留出口；合理等待不计完成。

## 新能力恢复边界

表格写入 after_apply 和显式发布 after_command_commit 是本轮新增的两个实际进程终止点。前者需隔离未提交 XLSX 并恢复正式版本，后者需保持 release/分享/通知且重试不重复。字节比较使用真实规范化序列化后的 XLSX，错误公式不在恢复时修复。状态比较仅排除执行时长与诊断摘要；实际版本、注册、分享、采用、发布、观察和正式结果均需一致。

这不是断电、任意并发或任意插件事务验证。模型调用、GPU、训练与真实金融数据采集不属于本轮。

旧 implicit_write 在后续保存/编辑工具中触发发布；创建/项目装载不会为初始材料自动补造发布历史。新政策需要使用者明确发布初始版本，发布记录不存在时不能用 current_version 伪造 current_published 的目标。
